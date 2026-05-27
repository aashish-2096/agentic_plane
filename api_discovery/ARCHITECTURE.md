# AACR — Architecture

**Agentic API Capability Registry**

Transforms raw Swagger/OpenAPI specifications into semantic operational primitives
that AI agents and developers can discover using natural language.

---

## The problem in one paragraph

Modern enterprises expose hundreds of APIs. Agents cannot navigate them semantically.
Swagger documentation is fragmented, transport-level, and unreadable to an agent
without deep engineering context. AACR sits between raw API specs and agent consumers —
converting REST endpoints into named, described, indexed capabilities that can be
found by intent rather than by path.

---

## System overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        External API Sources                         │
│   https://fakerestapi.../swagger.json   (any OpenAPI 2.0 / 3.0)    │
└───────────────────────────┬─────────────────────────────────────────┘
                            │  HTTP fetch
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       Ingestion Layer                               │
│   prance ($ref resolver) → operation extraction → base_url detect  │
└───────────────────────────┬─────────────────────────────────────────┘
                            │  list[operation dict]
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Extraction Layer                               │
│                                                                     │
│   ┌─────────────────────┐     ┌───────────────────────────────┐    │
│   │   Rule-based        │     │   LLM Enrichment              │    │
│   │  - op_id → snake    │  +  │  - tool_name (clean)          │    │
│   │  - domain from tags │     │  - description (semantic)     │    │
│   │  - curl generation  │     │  - intent_examples (3-5)      │    │
│   │  - input/output     │     │  Ollama / Anthropic / OpenAI  │    │
│   │    schema extract   │     │  Falls back if LLM fails      │    │
│   └─────────────────────┘     └───────────────────────────────┘    │
│                                                                     │
│   → Capability (Pydantic model)                                     │
└───────────────────────────┬─────────────────────────────────────────┘
                            │  Capability + embedding text
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Embedding Layer                                 │
│   sentence-transformers (all-MiniLM-L6-v2, 384-dim)                │
│   Input: "tool_name. description. intent_examples. response_fields"│
│   Output: float[384]                                               │
└──────────────┬────────────────────────────┬────────────────────────┘
               │ model_dump()               │ float[384]
               ▼                            ▼
┌──────────────────────┐     ┌──────────────────────────────────────┐
│     MongoDB          │     │             Qdrant                   │
│  capabilities        │     │  capability_vectors collection        │
│  ingestion_sources   │     │  cosine distance, 384-dim            │
│  (full documents)    │     │  payload: capability_id, org_id,     │
│                      │     │           domain, tool_name          │
└──────────────────────┘     └──────────────────────────────────────┘
               ▲                            ▲
               │ hydrate                    │ vector search
               │                            │
┌─────────────────────────────────────────────────────────────────────┐
│                      Retrieval Layer                                │
│                                                                     │
│   NL query → embed → Qdrant search (top-k, org_id filter)          │
│            → capability_ids + scores                               │
│            → MongoDB hydrate → ranked SearchResult list            │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
               ┌────────────┴────────────┐
               ▼                         ▼
   ┌─────────────────────┐   ┌────────────────────────────┐
   │   mode=curl         │   │   mode=results             │
   │  capability card    │   │  executor.py               │
   │  + curl command     │   │  httpx GET (safe only)     │
   │  + input schema     │   │  → live JSON payload       │
   └─────────────────────┘   └────────────────────────────┘
               │                         │
               └────────────┬────────────┘
                            ▼
                   Terminal CLI (Typer + Rich)
               aacr search / list / inspect / ingest
```

---

## Components

### Ingestion Layer — `core/ingestion.py`

Fetches a Swagger/OpenAPI spec from a URL, resolves all `$ref` references,
and extracts a flat list of operations.

**Key functions:**
- `fetch_spec(url)` — prance.ResolvingParser, handles 2.0 and 3.0
- `extract_base_url(spec, fallback)` — reads `servers[]` (3.0) or `host`+`basePath` (2.0)
- `extract_operations(spec, base_url)` — iterates all paths × methods, merges path-level params

**Output per operation:**
```python
{
  "method": "GET",
  "path": "/api/v1/Books/{id}",
  "operation_id": "ApiV1BooksByIdGet",
  "summary": "...",
  "description": "...",
  "tags": ["Books"],
  "parameters": [...],
  "request_body": {...},
  "responses": {...},
  "base_url": "https://fakerestapi.azurewebsites.net"
}
```

---

### Extraction Layer — `core/extraction.py`

Converts a raw operation dict into a typed `Capability` model.
Two-stage pipeline: rule-based always runs, LLM enrichment runs on top if available.

**Stage 1 — Rule-based (always)**

| Field | Rule |
|---|---|
| `tool_name` | operationId → CamelCase → snake_case |
| `domain` | first tag (lowercased), or first meaningful path segment |
| `description` | operation `description` or `summary` or `METHOD /path` |
| `input_schema` | extracted from path + query params + requestBody |
| `output_schema` | extracted from 200/201 response content schema |
| `response_fields` | flattened schema property paths (e.g. `Book.title`) |
| `curl` | method-appropriate template with base_url + path |
| `operational_meta` | safe ← GET, idempotent ← GET/PUT, destructive ← DELETE |

**Stage 2 — LLM enrichment (optional, falls back on failure)**

Sends a few-shot prompt to the configured LLM. Returns:
- `tool_name` — clean snake_case semantic name (e.g. `get_book_by_id`)
- `domain` — single lowercase word
- `description` — 1-2 sentence capability description
- `intent_examples` — 3-5 natural language queries an agent would use

Provider priority: `ollama` → `anthropic` → `openai`.
Any result that fails validation (`_is_valid_enrichment`) is discarded and rule-based values are kept.

---

### Embedding Layer — `core/embeddings.py`

Generates a 384-dimensional dense vector for each capability.

**Embedding input text (order matters — model weights earlier tokens):**
```
"{tool_name}. {description}. {intent_examples joined by comma}. {response_fields joined by comma}"
```

Fields with richer semantic content (intent_examples, response_fields) dramatically
improve recall for field-level queries like "who completed an activity" or
"what is the publish date of a book."

**Model:** `all-MiniLM-L6-v2` via sentence-transformers.
Local, no API key, 384-dim, ~90 MB download (cached after first run).

---

### Capability Registry

**MongoDB — `capabilities` collection**

```json
{
  "capability_id": "default:fakerestapi:GET_api_v1_Books",
  "org_id": "default",
  "source_id": "fakerestapi",
  "tool_name": "get_api_v1_books",
  "description": "GET /api/v1/Books",
  "domain": "books",
  "intent_examples": [],
  "input_schema": {},
  "output_schema": {},
  "response_fields": [],
  "execution": {
    "method": "GET",
    "path": "/api/v1/Books",
    "base_url": "https://fakerestapi.azurewebsites.net",
    "curl": "curl -X GET 'https://fakerestapi.azurewebsites.net/api/v1/Books'"
  },
  "operational_meta": {
    "safe": true,
    "idempotent": true,
    "requires_auth": false,
    "destructive": false
  },
  "ingested_at": "2026-05-27T00:30:01Z"
}
```

**MongoDB — `ingestion_sources` collection**

```json
{
  "source_id": "fakerestapi",
  "org_id": "default",
  "url": "https://fakerestapi.azurewebsites.net/swagger/v1/swagger.json",
  "status": "done",
  "capability_count": 27,
  "ingested_at": "2026-05-27T02:04:32Z",
  "error_detail": null
}
```

**MongoDB indexes:**
- `capabilities`: `{org_id, domain}` compound · `{capability_id}` unique
- `ingestion_sources`: `{org_id, status}` compound · `{source_id}` unique

**Qdrant — `capability_vectors` collection**

```
Point:
  id:      uuid5(NAMESPACE_DNS, capability_id)   — deterministic, enables idempotent upsert
  vector:  float[384]
  payload:
    capability_id: "default:fakerestapi:GET_api_v1_Books"
    org_id:        "default"
    domain:        "books"
    tool_name:     "get_api_v1_books"
    source_id:     "fakerestapi"
```

The `org_id` filter on every Qdrant search provides namespace isolation —
multiple tenants or API sources can coexist in the same collection.

---

### Retrieval Layer — `core/retrieval.py`

```
query string
  → embed_text(query)          # float[384]
  → qdrant.query_points(       # cosine similarity, filtered by org_id
      vector, org_id, top_k
    )                          # → [(capability_id, score), ...]
  → mongo.get_capabilities_by_ids(ids)   # preserves score order
  → [SearchResult(capability, score, rank), ...]
```

The Qdrant result order is preserved through MongoDB hydration by sorting
the returned documents against the original score-ranked ID list.

---

### Execution Layer — `core/executor.py`

Handles `mode=results` — takes the top `SearchResult` and executes it live.

**Safety gate:** only `operational_meta.safe = true` capabilities are executed
(GET-only in MVP). POST/PUT/DELETE always fall back to curl output regardless
of the flag passed.

**Path parameter resolution:** unfilled `{id}` placeholders are substituted
with `1` to produce a valid URL for exploration.

---

## Data flow

### Ingestion

```
aacr ingest <url> [--source-id] [--org-id] [--dry-run]
  ↓
fetch_spec(url)                     # prance + HTTP
  ↓
extract_operations(spec, base_url)  # flat list of op dicts
  ↓
for each operation:
  build_capability(op, source_id, org_id)
    ├── rule-based fields           # always
    └── _llm_enrich(op)             # if provider configured + validates
  embed_text(build_embedding_text(cap))   # float[384]
  mongo.upsert_capability(cap)
  qdrant.upsert_vector(cap.capability_id, vector, payload)
  ↓
mongo.upsert_source(status=done, count=N)
```

### Retrieval

```
aacr search "<query>" --mode <curl|results>
  ↓
embed_text(query)                    # float[384]
  ↓
qdrant.query_points(vector, org_id)  # cosine top-k
  ↓
mongo.get_capabilities_by_ids(ids)   # hydrate full documents
  ↓
mode=curl    → print ranked capability cards with curl
mode=results → executor.execute(results[0]) → httpx.get() → JSON
```

---

## Capability ID design

```
{org_id}:{source_id}:{operation_id}
   │          │             │
   │          │             └── operationId from OpenAPI spec
   │          │                 (e.g. GET_api_v1_Books_{id})
   │          └── slug for the ingested spec (e.g. fakerestapi)
   └── tenant namespace (default in MVP, multi-tenant in Phase 4)
```

Human-readable, collision-safe across orgs and sources.
Enables scoped flush by prefix match (`delete where capability_id starts with org:source:`).

---

## Tech stack

| Concern | Choice | Reason |
|---|---|---|
| Language | Python 3.11 | AI/ML ecosystem, fast iteration |
| CLI | Typer + Rich | Typed CLI, zero boilerplate, beautiful terminal output |
| OpenAPI parsing | prance | Resolves `$ref`, handles 2.0 and 3.0 |
| Data models | Pydantic v2 | Strict validation, serialisation, schema generation |
| HTTP client | httpx | Sync and async, used for spec fetch + mode=results execution |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) | Local, 384-dim, no API key, fast inference on CPU/MPS |
| LLM enrichment | Ollama (local) / Anthropic / OpenAI | Pluggable via `LLM_PROVIDER` env var |
| Capability store | MongoDB + pymongo | Native document model, no schema migrations |
| Vector store | Qdrant | Purpose-built, payload filtering, deterministic upsert via uuid5 |
| Infra (Phase 4) | Docker Compose | Single-command reproducible environment |

---

## Key design decisions

### Capability-centric, not endpoint-centric

The unit of the system is a **capability** (what the API can do), not an **endpoint** (how it's addressed). An endpoint is an implementation detail. A capability is a semantic operational primitive.

```
❌  GET /api/v1/Books/{id}
✅  get_book_by_id — "Fetch a single book by its ID"
```

### Extraction is doc-description-first

The LLM reads the OpenAPI `description` field, not a blank path. Extraction quality is bounded by documentation quality. Poor extraction is a signal to improve docs, not to improve the extractor.

### Embedding input concatenates multiple fields

```
"{tool_name}. {description}. {intent, intent, intent}. {field.path, field.path}"
```

Embedding `description` alone undershoots. Including `intent_examples` and `response_fields` dramatically improves recall for field-level queries ("who completed an activity", "what is the publish date").

### Qdrant point IDs are deterministic

```python
id = str(uuid.uuid5(uuid.NAMESPACE_DNS, capability_id))
```

Re-ingesting the same spec updates existing vectors in-place (upsert) rather than creating duplicates. No cleanup required between ingestion runs.

### LLM enrichment is optional and validated

The enrichment pipeline always has a rule-based fallback. Any LLM output that fails `_is_valid_enrichment` (missing fields, prose in tool_name, etc.) is discarded silently. The system degrades gracefully with no LLM configured.

### org_id isolation is built in from day one

Every document in MongoDB and every vector payload in Qdrant carries an `org_id`. Every query filters by it. Multi-tenancy in Phase 4 is a routing change, not a schema migration.

### mode=results is GET-only

The system checks `operational_meta.safe` before executing. Destructive operations (POST/PUT/DELETE) always return curl output, regardless of the flag. This is a hard safety gate, not a configurable option.

---

## Evaluation

Phase 2 was validated against a 20-query golden evaluation set.
Each query was issued in natural language with no domain or method hints.

| Metric | Score |
|---|---|
| Precision@1 | **85%** (17/20) |
| Precision@3 | **95%** (19/20) |

The 3 misses are caused by missing `intent_examples` on rule-based records
(no LLM enrichment for those capabilities). Upgrading from tinyllama to `phi`
or `mistral` is expected to push P@1 to 95%+.

---

## Extension points

| What | Where | Notes |
|---|---|---|
| New LLM provider | `core/extraction.py` `_llm_enrich` | Add a `_call_<provider>()` function and a branch in `_llm_enrich` |
| Different embedding model | `config.py` `EMBEDDING_MODEL` + `VECTOR_DIM` | Flush + re-ingest required if dim changes |
| MCP exposure | new `mcp/server.py` | Expose capabilities as MCP tools — Phase 5 |
| Auth-aware execution | `core/executor.py` | Pass headers/tokens when `operational_meta.requires_auth = true` |
| Schema drift detection | `core/ingestion.py` | Hash operation signatures, flag changed ones on re-ingest |
| Multi-source federation | already in data model | `org_id` + `source_id` isolation is already wired; Phase 4 adds routing |
| REST/FastAPI exposure | new `api/app.py` | Thin wrapper over `core/retrieval.py` |

---

## Out of scope (V1)

- MCP / REST API exposure (Phase 5)
- Full workflow orchestration
- Authentication brokers
- Human-centric documentation portals
- Multi-agent orchestration
- Production execution runtime
- Docker Compose (Phase 4)
