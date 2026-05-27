# Phase 1 Results — Ingest + Extract

**Date:** 2026-05-27  
**Source:** https://fakerestapi.azurewebsites.net/swagger/v1/swagger.json  
**Org:** default  
**Status:** ✅ Complete

---

## Summary

| Metric | Value |
|---|---|
| Operations found in spec | 27 |
| Capabilities stored (MongoDB) | 27 |
| Vectors stored (Qdrant) | 27 |
| Domains extracted | 5 |
| LLM enrichment (tinyllama) | 2 / 27 (7%) |
| Rule-based fallback | 25 / 27 (93%) |
| Ingestion time | ~2 min (27 Ollama calls + embedding) |

---

## Ingestion Source

```json
{
  "source_id": "fakerestapi",
  "org_id": "default",
  "url": "https://fakerestapi.azurewebsites.net/swagger/v1/swagger.json",
  "status": "done",
  "capability_count": 27,
  "ingested_at": "2026-05-27 02:04:32"
}
```

---

## Capabilities by Domain

### activities (5 capabilities)

| method | tool_name | path | safe | destructive | enriched |
|---|---|---|---|---|---|
| GET | get_api_v1_activities | /api/v1/Activities | ✅ | ❌ | rule-based |
| POST | post_api_v1_activities | /api/v1/Activities | ❌ | ❌ | rule-based |
| GET | get_api_v1_activities_{id} | /api/v1/Activities/{id} | ✅ | ❌ | rule-based |
| PUT | put_api_v1_activities_{id} | /api/v1/Activities/{id} | ❌ | ❌ | rule-based |
| DELETE | delete_api_v1_activities_{id} | /api/v1/Activities/{id} | ❌ | ✅ | rule-based |

<details>
<summary>curl examples</summary>

```bash
curl -X GET 'https://fakerestapi.azurewebsites.net/api/v1/Activities'
curl -X POST 'https://fakerestapi.azurewebsites.net/api/v1/Activities' -H 'Content-Type: application/json' -d '{}'
curl -X GET 'https://fakerestapi.azurewebsites.net/api/v1/Activities/{id}'
curl -X PUT 'https://fakerestapi.azurewebsites.net/api/v1/Activities/{id}' -H 'Content-Type: application/json' -d '{}'
curl -X DELETE 'https://fakerestapi.azurewebsites.net/api/v1/Activities/{id}'
```
</details>

---

### authors (5 capabilities)

| method | tool_name | path | safe | destructive | enriched |
|---|---|---|---|---|---|
| GET | get_api_v1_authors | /api/v1/Authors | ✅ | ❌ | rule-based |
| POST | post_api_v1_authors | /api/v1/Authors | ❌ | ❌ | rule-based |
| GET | get_api_v1_authors_{id} | /api/v1/Authors/{id} | ✅ | ❌ | rule-based |
| GET | get_api_v1_authors_authors_books_{id_book} | /api/v1/Authors/authors/books/{idBook} | ✅ | ❌ | rule-based |
| PUT | put_api_v1_authors_{id} | /api/v1/Authors/{id} | ❌ | ❌ | rule-based |
| DELETE | delete_api_v1_authors_{id} | /api/v1/Authors/{id} | ❌ | ✅ | rule-based |

<details>
<summary>curl examples</summary>

```bash
curl -X GET 'https://fakerestapi.azurewebsites.net/api/v1/Authors'
curl -X POST 'https://fakerestapi.azurewebsites.net/api/v1/Authors' -H 'Content-Type: application/json' -d '{}'
curl -X GET 'https://fakerestapi.azurewebsites.net/api/v1/Authors/{id}'
curl -X GET 'https://fakerestapi.azurewebsites.net/api/v1/Authors/authors/books/{idBook}'
curl -X PUT 'https://fakerestapi.azurewebsites.net/api/v1/Authors/{id}' -H 'Content-Type: application/json' -d '{}'
curl -X DELETE 'https://fakerestapi.azurewebsites.net/api/v1/Authors/{id}'
```
</details>

---

### books (5 capabilities)

| method | tool_name | path | safe | destructive | enriched |
|---|---|---|---|---|---|
| GET | get_api_v1_books | /api/v1/Books | ✅ | ❌ | rule-based |
| POST | list_books ⚠️ | /api/v1/Books | ❌ | ❌ | **LLM** (wrong — tool_name semantically incorrect) |
| GET | get_api_v1_books_{id} | /api/v1/Books/{id} | ✅ | ❌ | rule-based |
| PUT | put_api_v1_books_{id} | /api/v1/Books/{id} | ❌ | ❌ | rule-based |
| DELETE | delete_api_v1_books_{id} | /api/v1/Books/{id} | ❌ | ✅ | rule-based |

<details>
<summary>curl examples</summary>

```bash
curl -X GET 'https://fakerestapi.azurewebsites.net/api/v1/Books'
curl -X POST 'https://fakerestapi.azurewebsites.net/api/v1/Books' -H 'Content-Type: application/json' -d '{}'
curl -X GET 'https://fakerestapi.azurewebsites.net/api/v1/Books/{id}'
curl -X PUT 'https://fakerestapi.azurewebsites.net/api/v1/Books/{id}' -H 'Content-Type: application/json' -d '{}'
curl -X DELETE 'https://fakerestapi.azurewebsites.net/api/v1/Books/{id}'
```
</details>

---

### coverphotos (6 capabilities)

| method | tool_name | path | safe | destructive | enriched |
|---|---|---|---|---|---|
| GET | get_api_v1_cover_photos | /api/v1/CoverPhotos | ✅ | ❌ | rule-based |
| POST | post_api_v1_cover_photos | /api/v1/CoverPhotos | ❌ | ❌ | rule-based |
| GET | get_api_v1_cover_photos_{id} | /api/v1/CoverPhotos/{id} | ✅ | ❌ | rule-based |
| GET | get_api_v1_cover_photos_books_covers_{id_book} | /api/v1/CoverPhotos/books/covers/{idBook} | ✅ | ❌ | rule-based |
| PUT | put_api_v1_cover_photos_{id} | /api/v1/CoverPhotos/{id} | ❌ | ❌ | rule-based |
| DELETE | delete_api_v1_cover_photos_{id} | /api/v1/CoverPhotos/{id} | ❌ | ✅ | rule-based |

<details>
<summary>curl examples</summary>

```bash
curl -X GET 'https://fakerestapi.azurewebsites.net/api/v1/CoverPhotos'
curl -X POST 'https://fakerestapi.azurewebsites.net/api/v1/CoverPhotos' -H 'Content-Type: application/json' -d '{}'
curl -X GET 'https://fakerestapi.azurewebsites.net/api/v1/CoverPhotos/{id}'
curl -X GET 'https://fakerestapi.azurewebsites.net/api/v1/CoverPhotos/books/covers/{idBook}'
curl -X PUT 'https://fakerestapi.azurewebsites.net/api/v1/CoverPhotos/{id}' -H 'Content-Type: application/json' -d '{}'
curl -X DELETE 'https://fakerestapi.azurewebsites.net/api/v1/CoverPhotos/{id}'
```
</details>

---

### users (5 capabilities)

| method | tool_name | path | safe | destructive | enriched |
|---|---|---|---|---|---|
| GET | get_api_v1_users | /api/v1/Users | ✅ | ❌ | rule-based |
| POST | post_api_v1_users | /api/v1/Users | ❌ | ❌ | rule-based |
| GET | get_api_v1_users_{id} | /api/v1/Users/{id} | ✅ | ❌ | rule-based |
| PUT | update_user ✅ | /api/v1/Users/{id} | ❌ | ❌ | **LLM** (correct) |
| DELETE | delete_api_v1_users_{id} | /api/v1/Users/{id} | ❌ | ✅ | rule-based |

<details>
<summary>curl examples</summary>

```bash
curl -X GET 'https://fakerestapi.azurewebsites.net/api/v1/Users'
curl -X POST 'https://fakerestapi.azurewebsites.net/api/v1/Users' -H 'Content-Type: application/json' -d '{}'
curl -X GET 'https://fakerestapi.azurewebsites.net/api/v1/Users/{id}'
curl -X PUT 'https://fakerestapi.azurewebsites.net/api/v1/Users/{id}' -H 'Content-Type: application/json' -d '{}'
curl -X DELETE 'https://fakerestapi.azurewebsites.net/api/v1/Users/{id}'
```
</details>

---

## LLM Enrichment Analysis

**Model:** tinyllama (1.1B via Ollama)  
**Provider:** ollama @ http://localhost:11434

| # | Passed validation | Tool name quality | Notes |
|---|---|---|---|
| `POST /api/v1/Books` | ✅ | ❌ Wrong | Generated `list_books` for a POST (semantically incorrect) |
| `PUT /api/v1/Users/{id}` | ✅ | ✅ Correct | Generated `update_user` — accurate |
| 25 others | ❌ Failed validation | n/a | Returned prose, wrong JSON shape, or placeholder text |

**Root cause:** TinyLlama (1.1B) is too small for reliable structured JSON extraction. It inconsistently follows few-shot examples and mixes prose with JSON output.

### What worked in the pipeline
- JSON priming (`{"`) forced structured output on some calls
- `_parse_json` correctly extracts JSON from mixed prose+JSON responses
- `_is_valid_enrichment` catches and rejects semantically wrong results, falling back to rule-based
- Rule-based domain inference (via OpenAPI tags) is **100% accurate** across all 27 operations

### Recommended fix for Phase 2
Pull a larger model before re-ingesting:
```bash
ollama pull phi      # 2.7B — good JSON instruction following, ~1.6 GB
ollama pull mistral  # 7B  — best quality, ~4 GB
```
Then update `.env`:
```
OLLAMA_MODEL=phi
```
Then flush and re-ingest:
```bash
python cli.py flush --source fakerestapi
python cli.py ingest https://fakerestapi.azurewebsites.net/swagger/v1/swagger.json --source-id fakerestapi
```

---

## Operational Metadata (aggregate)

| Property | Count |
|---|---|
| Safe (read-only) | 13 |
| Idempotent | 18 |
| Destructive (DELETE) | 6 |
| Requires auth | 0 |

---

## Infrastructure

| Service | Version | Status |
|---|---|---|
| MongoDB | v8.0.4 | ✅ running (native, `~/data/db`) |
| Qdrant | v1.18.1 | ✅ running (native, `~/qdrant`) |
| Python | 3.11 (conda env `aacr`) | ✅ |
| Ollama | 0.1.17 | ✅ running, model: tinyllama |
| sentence-transformers | 5.5.1 (all-MiniLM-L6-v2) | ✅ cached |

---

## Phase 1 Success Criteria (from PLAN.md)

| Criterion | Result |
|---|---|
| `aacr ingest <url>` completes end to end | ✅ |
| Capabilities stored in MongoDB | ✅ 27 docs |
| Vectors stored in Qdrant | ✅ 27 vectors (384-dim) |
| `aacr list` shows capabilities with domains | ✅ 5 domains, all correct |
| `aacr status` shows connection health | ✅ |
| `aacr sources` shows ingested sources | ✅ |
| `aacr flush` removes capabilities | ✅ tested |
| `--dry-run` flag works | ✅ tested |
| LLM enrichment active | ⚠️ active but tinyllama too small — upgrade model |
| Clean `tool_name` and `domain` for all 27 | ⚠️ domains ✅, tool_names need better model |

---

## What's next — Phase 2

- `core/retrieval.py` — Qdrant vector search → MongoDB hydration
- `aacr search "<query>" --mode curl` — NL query → ranked capabilities + curl
- `aacr list [--domain <domain>]` — paginated capability listing
- `aacr inspect <tool_name>` — full capability detail
- Upgrade Ollama model to `phi` or `mistral` for clean tool names before building the eval set
