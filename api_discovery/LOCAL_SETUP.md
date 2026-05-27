# Local Development Setup

Run everything natively on macOS before any Docker/containerisation step (Docker is Phase 4).

---

## Prerequisites

- macOS (Apple Silicon / ARM64)
- [miniforge3](https://github.com/conda-forge/miniforge) (already installed)
- MongoDB (already installed via Homebrew — v8.0.4)

---

## 1. Python environment

Create a dedicated conda environment with Python 3.11:

```bash
conda create -n aacr python=3.11 -y
conda activate aacr
```

Activate it every session before running any `aacr` commands:

```bash
conda activate aacr
```

---

## 2. MongoDB

MongoDB is already installed. Start it with a local data directory:

```bash
mkdir -p ~/data/db
mongod --dbpath ~/data/db --fork --logpath ~/data/db/mongod.log
```

Stop it:

```bash
mongod --dbpath ~/data/db --shutdown
```

Verify it is running:

```bash
mongosh --eval "db.runCommand({ ping: 1 })"
```

Default connection string (used in `.env`):

```
MONGO_URI=mongodb://localhost:27017
MONGO_DB=aacr
```

---

## 3. Qdrant

Qdrant is not available via Homebrew on this macOS version. Download the prebuilt ARM64 binary directly from GitHub releases:

```bash
curl -L https://github.com/qdrant/qdrant/releases/download/v1.13.6/qdrant-aarch64-apple-darwin.tar.gz \
  -o /tmp/qdrant.tar.gz
tar -xzf /tmp/qdrant.tar.gz -C ~/
```

Start it (runs on `localhost:6333` by default):

```bash
~/qdrant &
```

Or in a dedicated terminal tab (foreground, easier to monitor logs):

```bash
~/qdrant
```

Stop it:

```bash
pkill qdrant
```

Verify it is running:

```bash
curl http://localhost:6333/healthz
# → {"title":"qdrant - vector search engine","version":"..."}
```

Default connection string (used in `.env`):

```
QDRANT_URL=http://localhost:6333
```

---

## 4. Install Python dependencies

From the `api_discovery/` directory with the `aacr` conda env active:

```bash
pip install -r requirements.txt
```

---

## 5. Environment variables

Copy the example file and fill in your LLM API key:

```bash
cp .env.example .env
# edit .env — add ANTHROPIC_API_KEY or OPENAI_API_KEY
```

---

## 6. Verify everything is up

```bash
python cli.py status
# MongoDB: connected  |  Qdrant: connected
# Capabilities: 0     |  Sources: 0  |  Org: default
```

---

## Startup sequence (short form)

```bash
# Terminal 1 — MongoDB
mongod --dbpath ~/data/db

# Terminal 2 — Qdrant
~/qdrant

# Terminal 3 — project
conda activate aacr
cd ~/Documents/agentic_plane/api_discovery
python cli.py ingest https://fakerestapi.azurewebsites.net/swagger/v1/swagger.json
```

---

## Docker

Docker-based setup is deferred to **Phase 4** (multi-source + enterprise hardening). A `docker-compose.yml` covering MongoDB + Qdrant will be added at that stage.
