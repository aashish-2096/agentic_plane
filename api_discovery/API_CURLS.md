# AACR — API Curl Reference

Base URL: `http://localhost:8000`  
Interactive docs: `http://localhost:8000/docs`

---

## Start / Stop

### Start all services

Open three terminal tabs in order:

```bash
# Tab 1 — MongoDB (skip if running as a brew service)
mongod --dbpath ~/data/db
```

```bash
# Tab 2 — Qdrant
~/qdrant
```

```bash
# Tab 3 — FastAPI server
conda activate aacr
cd ~/Documents/agentic_plane/api_discovery
uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```

### Stop all services

```bash
# Stop FastAPI — Ctrl+C in Tab 3

# Stop Qdrant — Ctrl+C in Tab 2, or kill by port:
lsof -ti :6333 | xargs kill

# Stop MongoDB — Ctrl+C in Tab 1, or:
mongosh --eval "db.adminCommand({ shutdown: 1 })"
```

### Check what's running

```bash
# MongoDB
mongosh --eval "db.runCommand({ ping: 1 })"

# Qdrant
curl -s http://localhost:6333/healthz

# FastAPI
curl -s http://localhost:8000/health | python3 -m json.tool
```

### MongoDB as a background service (macOS Homebrew)

```bash
# Start
brew services start mongodb-community

# Stop
brew services stop mongodb-community

# Status
brew services list | grep mongodb
```

---

## System

### Health check

```bash
curl -s http://localhost:8000/health | python3 -m json.tool
```

Expected:
```json
{
    "mongodb": "connected",
    "qdrant": "connected",
    "capabilities": 27,
    "sources": 1,
    "org_id": "default"
}
```

---

## Discovery

### Search — mode=curl (ranked capabilities + curl commands)

```bash
curl -s -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "fetch a book by its id",
    "mode": "curl",
    "top_k": 3,
    "org_id": "default"
  }' | python3 -m json.tool
```

### Search — mode=results (live API execution)

```bash
curl -s -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "get all activities",
    "mode": "results",
    "top_k": 1
  }' | python3 -m json.tool
```

> `live_payload` is populated with the real API response.  
> `execution_note` is null when execution succeeds.

### Search — mode=results against an unsafe capability (safety gate)

```bash
curl -s -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "delete a book",
    "mode": "results"
  }' | python3 -m json.tool
```

> `live_payload` will be null.  
> `execution_note` will read: _"Top match '...' is DELETE — not safe to execute. Returning curl only."_

### Search — custom top_k and org_id

```bash
curl -s -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "update user details",
    "mode": "curl",
    "top_k": 5,
    "org_id": "default"
  }' | python3 -m json.tool
```

---

### List all capabilities

```bash
curl -s "http://localhost:8000/capabilities" | python3 -m json.tool
```

### List capabilities filtered by domain

```bash
curl -s "http://localhost:8000/capabilities?domain=books" | python3 -m json.tool
```

```bash
curl -s "http://localhost:8000/capabilities?domain=authors" | python3 -m json.tool
```

```bash
curl -s "http://localhost:8000/capabilities?domain=activities" | python3 -m json.tool
```

```bash
curl -s "http://localhost:8000/capabilities?domain=users" | python3 -m json.tool
```

```bash
curl -s "http://localhost:8000/capabilities?domain=coverphotos" | python3 -m json.tool
```

### Get a single capability by tool_name

```bash
curl -s "http://localhost:8000/capabilities/update_user" | python3 -m json.tool
```

```bash
curl -s "http://localhost:8000/capabilities/create_book" | python3 -m json.tool
```

```bash
curl -s "http://localhost:8000/capabilities/get_api_v1_activities" | python3 -m json.tool
```

> Returns 404 if the tool_name does not exist:
```bash
curl -s "http://localhost:8000/capabilities/nonexistent_tool" | python3 -m json.tool
```

---

## Ingestion

### List ingested sources

```bash
curl -s "http://localhost:8000/sources" | python3 -m json.tool
```

### Ingest a new Swagger spec (live write)

```bash
curl -s -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://fakerestapi.azurewebsites.net/swagger/v1/swagger.json",
    "source_id": "fakerestapi",
    "org_id": "default",
    "dry_run": false
  }' | python3 -m json.tool
```

> Re-ingesting the same spec is idempotent — existing vectors and documents are updated in place.

### Dry-run ingest (preview without writing)

```bash
curl -s -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://fakerestapi.azurewebsites.net/swagger/v1/swagger.json",
    "source_id": "fakerestapi",
    "dry_run": true
  }' | python3 -m json.tool
```

> Returns extracted capabilities in `capabilities[]` without touching MongoDB or Qdrant.

### Flush a source (delete all its capabilities)

```bash
curl -s -X DELETE "http://localhost:8000/sources/fakerestapi?org_id=default" | python3 -m json.tool
```

Expected:
```json
{
    "source_id": "fakerestapi",
    "org_id": "default",
    "capabilities_removed": 27
}
```

> After flushing, re-ingest to restore capabilities.

---

## Quick reference

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Connection health + registry counts |
| POST | `/search` | Natural language search (mode=curl or mode=results) |
| GET | `/capabilities` | List all capabilities, optional `?domain=` filter |
| GET | `/capabilities/{tool_name}` | Full detail for one capability |
| GET | `/sources` | List all ingested sources |
| POST | `/ingest` | Ingest a Swagger/OpenAPI spec |
| DELETE | `/sources/{source_id}` | Remove all capabilities for a source |
