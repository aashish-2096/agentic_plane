# Agentic API Capability Registry (AACR)

## What this is

AACR converts raw Swagger/OpenAPI specifications into semantic capabilities that AI agents and developers can discover using natural language — without ever reading a Swagger file.

Instead of:
```
GET /api/v1/Books/{id}
```

You get:
```
get_book_by_id — Fetch a single book by its ID
curl -X GET 'https://.../api/v1/Books/{id}'
confidence: 0.94
```

---

## Problem being solved

Modern enterprises expose hundreds of APIs. Agents cannot semantically navigate them. Swagger docs are fragmented, transport-level, and not agent-readable. AACR sits between raw API specs and agent/developer consumers — transforming endpoints into semantic operational primitives.

---

## Architecture

```
Swagger/OpenAPI spec
        ↓
  Ingestion layer       — fetch, parse, normalize
        ↓
  Extraction layer      — doc description + LLM enrichment → tool_name, domain, intent_examples
        ↓
  Capability registry   — MongoDB (full docs) + Qdrant (vectors)
        ↓
  Retrieval layer       — NL query → embed → vector search → hydrate from Mongo
        ↓
  Response mode router  — mode=curl (capability + curl) | mode=results (live payload)
        ↓
  Terminal CLI          — aacr ingest / search / list / inspect
```

---

## Tech stack

| Concern | Choice | Reason |
|---|---|---|
| Language | Python 3.11+ | AI ecosystem, fast prototyping |
| CLI | Typer | Clean, typed CLI with zero boilerplate |
| API parsing | prance + pydantic | Resolves $ref, validated models |
| HTTP client | httpx | Async-capable, used for both fetch and mode=results execution |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) | Local, fast, 384-dim, no API key needed |
| LLM enrichment | Anthropic claude-haiku / OpenAI gpt-4o-mini | Configurable via env var |
| Capability store | MongoDB | Native document model, no schema migrations |
| Vector store | Qdrant | Purpose-built, payload filtering by org_id/domain |
| Infra | Docker Compose | Single command local startup |

---

## Document schemas

### MongoDB — `capabilities` collection

```json
{
  "capability_id": "default:fakerestapi:GetBookById",
  "org_id": "default",
  "source_id": "fakerestapi",
  "tool_name": "get_book_by_id",
  "description": "Fetch a single book by its ID including title, author and publish date",
  "domain": "books",
  "intent_examples": ["fetch book", "get book details", "retrieve publication by id"],
  "input_schema": { "id": { "type": "integer", "required": true } },
  "output_schema": { "type": "Book" },
  "response_fields": ["Book.id", "Book.title", "Book.description", "Book.publishDate"],
  "execution": {
    "method": "GET",
    "path": "/api/v1/Books/{id}",
    "base_url": "https://fakerestapi.azurewebsites.net",
    "curl": "curl -X GET 'https://fakerestapi.azurewebsites.net/api/v1/Books/{id}'"
  },
  "operational_meta": {
    "safe": true,
    "idempotent": true,
    "requires_auth": false,
    "destructive": false
  },
  "ingested_at": "2025-05-26T10:32:00Z"
}
```

### MongoDB — `ingestion_sources` collection

```json
{
  "source_id": "fakerestapi",
  "org_id": "default",
  "url": "https://fakerestapi.azurewebsites.net/swagger/v1/swagger.json",
  "status": "done",
  "capability_count": 23,
  "ingested_at": "2025-05-26T10:32:00Z",
  "error_detail": null
}
```

### Qdrant — `capability_vectors` collection

```
Point:
  id:      uuid (generated)
  vector:  float[384]  — all-MiniLM-L6-v2 on concatenated text
  payload:
    capability_id: "default:fakerestapi:GetBookById"
    org_id:        "default"
    domain:        "books"
    tool_name:     "get_book_by_id"
```

**Embedding input text** (order matters — model weights earlier tokens):
```
"{tool_name}. {description}. {intent_examples joined with comma}. {response_fields joined with comma}"
```

**MongoDB indexes:**
- `capabilities`: `{org_id, domain}` compound + `{capability_id}` unique
- `ingestion_sources`: `{org_id, status}` compound + `{source_id}` unique

---

## CLI commands

```bash
# Ingest a Swagger spec
aacr ingest <url>
aacr ingest https://fakerestapi.azurewebsites.net/swagger/v1/swagger.json

# Search — mode=curl returns capability + curl (developer / agent builder)
aacr search "fetch publication details" --mode curl

# Search — mode=results executes the capability and returns live data
aacr search "get all books" --mode results

# List all capabilities, optionally filtered by domain
aacr list
aacr list --domain books

# Inspect a single capability in full detail
aacr inspect get_book_by_id

# System status
aacr status

# List all ingested sources
aacr sources

# Remove all capabilities for a source
aacr flush --source fakerestapi
```

---

## Project structure

```
api_discovery/
├── docker-compose.yml        — MongoDB + Qdrant + optional mongo-express
├── .env                      — connection strings, LLM API key
├── .env.example              — committed to repo, no secrets
├── requirements.txt
├── cli.py                    — Typer entry point: aacr <command>
├── config.py                 — env var loading, constants
├── core/
│   ├── ingestion.py          — fetch + parse OpenAPI via httpx + prance
│   ├── extraction.py         — doc-driven capability extraction + LLM enrichment
│   ├── embeddings.py         — sentence-transformers wrapper, embed_text()
│   ├── retrieval.py          — Qdrant search → capability_ids → MongoDB hydrate
│   └── executor.py           — mode=results: live httpx call using execution fields
├── stores/
│   ├── mongo.py              — MongoDB motor client, capability CRUD
│   └── qdrant.py             — Qdrant client, upsert_vector(), search_vectors()
└── models/
    └── capability.py         — Pydantic models: Capability, IngestionSource, SearchResult
```

---

## Data flow

### Ingestion
```
aacr ingest <url>
  → httpx.get(url) → raw OpenAPI JSON
  → prance.resolve() → dereferenced spec
  → for each operation:
      extract description, operationId, method, path, parameters, responses
      → LLM enrichment call → tool_name, domain, intent_examples, clean description
      → build Capability pydantic model
      → sentence-transformers.encode(embedding_text) → float[384]
      → mongo.upsert_capability(capability)
      → qdrant.upsert_vector(capability_id, vector, payload)
  → update ingestion_sources status=done
  → print summary to terminal
```

### Retrieval
```
aacr search "<query>" --mode <curl|results>
  → sentence-transformers.encode(query) → float[384]
  → qdrant.search(vector, filter={org_id}, top_k=5) → [(capability_id, score), ...]
  → mongo.get_capabilities_by_ids([capability_id, ...]) → [Capability, ...]
  → if mode=curl:  print ranked capabilities with curl + schema
  → if mode=results:
      take top match
      → executor.run(capability) → httpx.request(method, url) → response JSON
      → print response payload
```

---

## Phase plan

### Phase 1 — Ingest + extract (weeks 1–3)
**Goal:** `aacr ingest` works end to end. 23 capabilities extracted from fakerestapi, stored in MongoDB and Qdrant.

Deliverables:
- `docker-compose.yml` with MongoDB + Qdrant
- `core/ingestion.py` — fetch and parse fakerestapi Swagger
- `core/extraction.py` — rule-based + LLM enrichment
- `stores/mongo.py` + `stores/qdrant.py`
- `models/capability.py`
- `cli.py` with `ingest` command
- `aacr status` shows connection health

**Bottleneck:** LLM enrichment quality. If extraction produces bad `tool_name` or `domain`, everything downstream is wrong. Build a `--dry-run` flag that prints extracted capabilities without writing to stores.

**Success signal:** `aacr ingest <url>` completes and `aacr list` shows 23 capabilities with clean names and domains.

---

### Phase 2 — Semantic retrieval (weeks 4–6)
**Goal:** `aacr search "fetch publication details" --mode curl` returns relevant capabilities ranked by confidence.

Deliverables:
- `core/embeddings.py` with consistent embed function
- `core/retrieval.py` with Qdrant search + MongoDB hydration
- `cli.py` with `search`, `list`, `inspect` commands
- Golden eval set: 20 NL queries → expected capability → measured hit rate

**Bottleneck:** Retrieval relevance. Embedding description alone undershoots. Ensure `intent_examples` and `response_fields` are concatenated into the embedding input. Measure precision@1 and precision@3 against the eval set.

**Success signal:** 80%+ precision@1 on the golden eval set.

---

### Phase 3 — Mode split + execution (weeks 7–9)
**Goal:** `mode=curl` and `mode=results` both work. Terminal is the only consumer.

Deliverables:
- `core/executor.py` — live httpx execution for `mode=results`
- `cli.py` updated with `--mode` flag on `search`
- End-to-end test: NL query → live data payload in terminal

**Bottleneck:** `mode=results` is the first live API call in the system. Scope to GET-only endpoints in MVP (fakerestapi is all safe/idempotent). Do not execute destructive operations.

**Success signal:** `aacr search "who are all the authors" --mode results` returns a live JSON payload without touching the Swagger file.

---

### Phase 4 — Multi-source + enterprise hardening (weeks 10–14)
**Goal:** Support N API sources. Namespace isolation per org. Schema drift detection.

Deliverables:
- Multi-source ingestion with `--source-id` flag
- `aacr flush --source <id>` scoped removal
- Schema drift: re-ingest detects changed endpoints
- `org_id` isolation in all queries (already in data model from Phase 1)
- Vector DB upgrade path evaluation

**Note:** `org_id` scoping was built into the data model from day one. Phase 4 is mostly configuration and routing, not schema migration.

---

## Key design decisions

**`capability_id` is a composite string** — `{org_id}:{source_id}:{operation_id}`. Human-readable, collision-safe, enables scoped flush by prefix match.

**Extraction is doc-description-first** — the LLM reads the existing description field from the OpenAPI spec, not a blank endpoint path. Quality of extraction is bounded by quality of documentation. Bad extraction = signal to improve docs.

**Embedding strategy** — description + intent_examples + response_fields concatenated in one text block. Field-level content dramatically improves retrieval for queries like "who enrolled in last 30 mins" which are field-level intent queries, not just capability-level.

**MVP ingestion is synchronous** — no Redis, no background worker. The CLI blocks until done. Redis slot is reserved in docker-compose but commented out. Add it when a source with 200+ endpoints makes the wait intolerable.

**mode=results is GET-only in MVP** — the system checks `operational_meta.safe` before executing. Destructive operations (POST/PUT/DELETE) are returned as `mode=curl` output only, regardless of the flag passed.

**org_id defaults to "default"** — MVP is single-tenant. The field exists on every document from day one. Multi-tenancy in Phase 4 is a routing change, not a schema migration.

---

## Local setup

### Prerequisites
- Docker Desktop (docker.com/products/docker-desktop)
- Python 3.11+
- Git

### Start
```bash
git clone <repo>
cd api_discovery
cp .env.example .env          # add your LLM API key
docker compose up -d          # starts MongoDB + Qdrant
pip install -r requirements.txt
python cli.py ingest https://fakerestapi.azurewebsites.net/swagger/v1/swagger.json
```

### Verify
```bash
python cli.py status
# MongoDB: connected  |  Qdrant: connected
# Capabilities: 23   |  Sources: 1  |  Org: default
```

---

## MVP success signal

A natural language query resolves to the correct capability and returns either an executable curl command or a live data payload — without the user ever reading a Swagger file.

```bash
$ aacr search "who are all the authors" --mode results
→ live JSON payload from fakerestapi

$ aacr search "fetch publication by id" --mode curl
→ get_book_by_id  confidence: 0.94
  curl -X GET 'https://.../api/v1/Books/{id}'
```

---

## Out of scope (V1)

- MCP / REST API exposure (Phase 5 — after terminal MVP is validated)
- Full workflow orchestration
- Authentication brokers
- Human-centric documentation portals
- Multi-agent orchestration
- Production execution runtime
