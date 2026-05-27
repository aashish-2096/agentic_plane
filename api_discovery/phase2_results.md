# Phase 2 Results — Semantic Retrieval

**Date:** 2026-05-27  
**Scope:** Natural language search over registered API capabilities  
**Target:** Precision@1 ≥ 80% on a 20-query golden evaluation set

---

## What was built

A natural language query layer on top of the Phase 1 capability registry.
A developer or agent types a plain English intent and gets back the matching API capability — with its curl command or a live JSON response — without reading any Swagger file.

```
"get all books"
        ↓
  vector embedding (all-MiniLM-L6-v2, 384-dim)
        ↓
  Qdrant cosine similarity search (top-5)
        ↓
  MongoDB hydration → ranked Capability objects
        ↓
  mode=curl → capability card + curl command
  mode=results → live API call → JSON payload
```

---

## CLI commands added

### `aacr search`

```bash
python cli.py search "fetch a book by its id" --mode curl
```

```
  Query: fetch a book by its id   mode=curl   org=default

  #1  get_api_v1_books_{id}   confidence: 0.7052   domain: books
       GET  /api/v1/Books/{id}
       GET /api/v1/Books/{id}
       curl -X GET 'https://fakerestapi.azurewebsites.net/api/v1/Books/{id}'
       input:  id:integer
```

```bash
python cli.py search "get all activities" --mode results
```

```
  Executing get_api_v1_activities   confidence: 0.6056

  [
    { "id": 1, "title": "Activity 1", "dueDate": "...", "completed": false },
    { "id": 2, "title": "Activity 2", "dueDate": "...", "completed": true },
    ...
  ]
```

### `aacr list`

```bash
python cli.py list --domain books
```

```
  tool_name                  domain   method   path
  create_book                books    POST✗    /api/v1/Books
  delete_api_v1_books_{id}   books    DELETE✗  /api/v1/Books/{id}
  get_api_v1_books           books    GET      /api/v1/Books
  get_api_v1_books_{id}      books    GET      /api/v1/Books/{id}
  put_api_v1_books_{id}      books    PUT✗     /api/v1/Books/{id}
```

### `aacr inspect`

```bash
python cli.py inspect update_user
```

```
  update_user   default:fakerestapi:PUT_api_v1_Users_{id}
  domain:      users
  description: Update user details.
  intent:      update user | edit user

  Execution
    method:   PUT
    path:     /api/v1/Users/{id}
    curl:     curl -X PUT 'https://.../api/v1/Users/{id}' -H 'Content-Type: application/json' -d '{}'

  Operational metadata
    safe=False  idempotent=True  requires_auth=False  destructive=False

  Input schema
    *id: integer  (path)
```

---

## Evaluation — 20-query golden set

Each query was issued in natural language against 27 registered capabilities with no hints about domain or HTTP method.

| # | Query | Expected | Top Match | Score | Hit |
|---|---|---|---|---|---|
| 1 | get all books | GET /Books | get_api_v1_books | 0.558 | ✅ P@1 |
| 2 | fetch a book by its id | GET /Books/{id} | get_api_v1_books_{id} | 0.705 | ✅ P@1 |
| 3 | retrieve publication details | GET /Books/{id} | get_api_v1_authors_authors_books | 0.327 | ❌ MISS |
| 4 | create a new book | POST /Books | create_book | 0.768 | ✅ P@1 |
| 5 | update book information | PUT /Books/{id} | create_book | 0.572 | ✅ P@3 |
| 6 | delete a book | DELETE /Books/{id} | delete_api_v1_books_{id} | 0.659 | ✅ P@1 |
| 7 | list all authors | GET /Authors | get_api_v1_authors | 0.534 | ✅ P@1 |
| 8 | get author details by id | GET /Authors/{id} | get_api_v1_authors_{id} | 0.621 | ✅ P@1 |
| 9 | fetch books written by an author | GET /Authors/books | get_api_v1_authors_authors_books | 0.621 | ✅ P@1 |
| 10 | add a new author | POST /Authors | create_book | 0.422 | ✅ P@3 |
| 11 | remove an author | DELETE /Authors/{id} | delete_api_v1_authors_{id} | 0.505 | ✅ P@1 |
| 12 | get all activities | GET /Activities | get_api_v1_activities | 0.606 | ✅ P@1 |
| 13 | fetch activity by id | GET /Activities/{id} | get_api_v1_activities_{id} | 0.694 | ✅ P@1 |
| 14 | get all users | GET /Users | get_api_v1_users | 0.525 | ✅ P@1 |
| 15 | fetch user profile by id | GET /Users/{id} | get_api_v1_users_{id} | 0.565 | ✅ P@1 |
| 16 | update user details | PUT /Users/{id} | update_user | **0.807** | ✅ P@1 |
| 17 | delete a user account | DELETE /Users/{id} | delete_api_v1_users_{id} | 0.532 | ✅ P@1 |
| 18 | get all cover photos | GET /CoverPhotos | get_api_v1_cover_photos | 0.683 | ✅ P@1 |
| 19 | fetch cover photo by id | GET /CoverPhotos/{id} | get_api_v1_cover_photos_{id} | 0.753 | ✅ P@1 |
| 20 | get book cover image | GET /CoverPhotos/books/covers | get_api_v1_cover_photos_books_covers | 0.651 | ✅ P@1 |

### Score summary

| Metric | Score | Target | Status |
|---|---|---|---|
| **Precision@1** | **85%** (17/20) | ≥ 80% | ✅ PASS |
| **Precision@3** | **95%** (19/20) | — | — |
| Avg confidence (hits) | 0.630 | — | — |
| Avg confidence (misses) | 0.441 | — | — |

---

## Miss analysis

Only 1 hard miss (Q3) and 2 soft misses (Q5, Q10 hit P@3 not P@1).

**Root cause: missing intent_examples on rule-based records.**

25 of 27 capabilities were extracted without LLM enrichment (tinyllama was too small to produce reliable output). Without intent_examples, the embedding only covers the path-derived tool_name, which is weak for semantic generalisation.

| Query | Miss type | Root cause | Fix |
|---|---|---|---|
| Q3 "retrieve publication details" | Hard — not in top 5 | No synonym coverage for "publication" | Add intent_examples via better LLM model |
| Q5 "update book information" | Soft — P@3 | `create_book` stole the slot (has intent_examples) | Add intent_examples to PUT record |
| Q10 "add a new author" | Soft — P@3 | `create_book` matches "add" and "new" semantically | Add intent_examples to POST /Authors |

**Expected P@1 with `phi` or `mistral` enrichment: 95%+**

---

## Safety guard — mode=results

Queries that resolve to a non-GET capability fall back to curl output automatically.

```bash
python cli.py search "create a book" --mode results

# → Top match create_book is POST (not safe). Returning curl instead.
#   curl -X POST 'https://.../api/v1/Books' -H 'Content-Type: application/json' -d '{}'
```

Only `operational_meta.safe = true` capabilities execute live calls.

---

## Infrastructure at end of Phase 2

| Component | Version | Role |
|---|---|---|
| MongoDB | v8.0.4 | Capability document store |
| Qdrant | v1.18.1 | 384-dim cosine vector index |
| sentence-transformers | 5.5.1 | all-MiniLM-L6-v2 embeddings |
| Ollama + tinyllama | 0.1.17 / 1.1B | LLM enrichment (upgrade to phi/mistral recommended) |
| Python | 3.11 (conda `aacr`) | Runtime |

**Registry state:** 27 capabilities · 5 domains · 1 source · 27 vectors

---

## What's next — Phase 3

- Multi-source ingestion: ingest a second Swagger spec alongside fakerestapi
- `--source-id` isolation: queries scoped by source or org
- Schema drift detection: re-ingest detects changed endpoints
- Docker Compose: single-command startup for MongoDB + Qdrant
- MCP exposure layer: expose capabilities as MCP-compatible tools
