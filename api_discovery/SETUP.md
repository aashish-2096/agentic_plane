# AACR — Setup Guide

This guide gets the Agentic API Capability Registry running from scratch on any machine.
Follow it top to bottom; every command is copy-pasteable.

---

## Prerequisites

| Requirement | Version | Check |
|---|---|---|
| macOS (Apple Silicon / Intel) or Linux | any recent | `uname -m` |
| conda / miniforge3 | any | `conda --version` |
| Git | any | `git --version` |
| curl | any | `curl --version` |

> **Windows:** use WSL2 (Ubuntu 22.04+). All commands below work inside WSL2.

---

## 1. Clone the repo

```bash
git clone <repo-url>
cd agentic_plane/api_discovery
```

---

## 2. Python environment

```bash
conda create -n aacr python=3.11 -y
conda activate aacr
pip install -r requirements.txt
```

> The first `pip install` downloads ~2 GB (PyTorch for sentence-transformers).
> Subsequent installs use the pip cache and are fast.

---

## 3. MongoDB

### macOS (Homebrew)

```bash
brew tap mongodb/brew
brew install mongodb-community
brew services start mongodb-community
```

### macOS (manual / Homebrew unavailable)

```bash
# Download and extract
curl -L https://fastdl.mongodb.org/osx/mongodb-macos-arm64-8.0.4.tgz -o /tmp/mongodb.tgz
tar -xzf /tmp/mongodb.tgz -C ~/
mkdir -p ~/data/db

# Start
~/mongodb-macos-arm64-8.0.4/bin/mongod --dbpath ~/data/db --fork --logpath ~/data/db/mongod.log
```

### Linux

```bash
# Ubuntu / Debian
wget -qO - https://www.mongodb.org/static/pgp/server-8.0.asc | sudo apt-key add -
echo "deb [ arch=amd64,arm64 ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/8.0 multiverse" \
  | sudo tee /etc/apt/sources.list.d/mongodb-org-8.0.list
sudo apt-get update && sudo apt-get install -y mongodb-org
sudo systemctl start mongod
```

### Verify

```bash
mongosh --eval "db.runCommand({ ping: 1 })"
# → { ok: 1 }
```

---

## 4. Qdrant

Qdrant ships as a single binary — no package manager needed.

### macOS Apple Silicon (ARM64)

```bash
curl -L https://github.com/qdrant/qdrant/releases/download/v1.18.1/qdrant-aarch64-apple-darwin.tar.gz \
  -o /tmp/qdrant.tar.gz
tar -xzf /tmp/qdrant.tar.gz -C ~/
chmod +x ~/qdrant
```

### macOS Intel (x86_64)

```bash
curl -L https://github.com/qdrant/qdrant/releases/download/v1.18.1/qdrant-x86_64-apple-darwin.tar.gz \
  -o /tmp/qdrant.tar.gz
tar -xzf /tmp/qdrant.tar.gz -C ~/
chmod +x ~/qdrant
```

### Linux (x86_64)

```bash
curl -L https://github.com/qdrant/qdrant/releases/download/v1.18.1/qdrant-x86_64-unknown-linux-musl.tar.gz \
  -o /tmp/qdrant.tar.gz
tar -xzf /tmp/qdrant.tar.gz -C ~/
chmod +x ~/qdrant
```

### Start Qdrant

```bash
# Background (recommended for development)
~/qdrant &>/tmp/qdrant.log &

# Foreground (to watch logs)
~/qdrant
```

### Verify

```bash
curl http://localhost:6333/healthz
# → healthz check passed
```

---

## 5. Ollama (local LLM enrichment)

Ollama provides the LLM that generates clean `tool_name`, `domain`, and `intent_examples`
during ingestion. This step is optional — the system falls back to rule-based extraction
if Ollama is not available.

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Start the server
ollama serve &

# Pull a model (choose one)
ollama pull phi        # 2.7B — recommended, ~1.6 GB, good JSON output
ollama pull mistral    # 7B  — best quality, ~4 GB
ollama pull tinyllama  # 1.1B — fastest, lower quality
```

Update `.env` to match your chosen model (see step 6).

---

## 6. Environment variables

```bash
cp .env.example .env
```

Edit `.env`:

```bash
# MongoDB
MONGO_URI=mongodb://localhost:27017
MONGO_DB=aacr

# Qdrant
QDRANT_URL=http://localhost:6333

# LLM enrichment (set LLM_PROVIDER=ollama if using Ollama, else leave blank)
LLM_PROVIDER=ollama
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=phi          # or mistral, tinyllama

# Cloud LLM (alternative to Ollama — set one or the other, not both)
# LLM_PROVIDER=anthropic
# ANTHROPIC_API_KEY=sk-ant-...
# LLM_PROVIDER=openai
# OPENAI_API_KEY=sk-...

# Registry defaults
DEFAULT_ORG_ID=default
EMBEDDING_MODEL=all-MiniLM-L6-v2
```

---

## 7. Verify all services

```bash
conda activate aacr
cd api_discovery
python cli.py status
```

Expected output:

```
  MongoDB   connected   mongodb://localhost:27017
  Qdrant    connected   http://localhost:6333

  Capabilities: 0   Sources: 0   Org: default
```

Both must show `connected` before proceeding.

---

## 8. Ingest a Swagger spec

```bash
python cli.py ingest https://fakerestapi.azurewebsites.net/swagger/v1/swagger.json \
  --source-id fakerestapi
```

The first run downloads the sentence-transformers model (~90 MB, cached after that).
Expect ~2-3 minutes with Ollama enrichment, ~30 seconds with rule-based only.

```
  Done. 27 capabilities ingested from fakerestapi.
```

---

## 9. Explore the registry

```bash
# Check counts
python cli.py status

# List all capabilities
python cli.py list

# Filter by domain
python cli.py list --domain books

# Full detail on one capability
python cli.py inspect get_api_v1_books

# Natural language search → curl output
python cli.py search "fetch all books" --mode curl

# Natural language search → live JSON response
python cli.py search "get all activities" --mode results

# Show ingested sources
python cli.py sources
```

---

## 10. Run the evaluation

```bash
python eval/run_eval.py
```

Expected output (with phi or better model):

```
  Precision@1  85%+   (17+/20)
  Precision@3  95%+   (19+/20)
  Phase 2 target: P@1 ≥ 80%  PASS
```

---

## Startup reference (daily dev)

Open three terminal tabs:

```bash
# Tab 1 — MongoDB (skip if already running as a service)
mongod --dbpath ~/data/db

# Tab 2 — Qdrant
~/qdrant

# Tab 3 — Project
conda activate aacr
cd agentic_plane/api_discovery
python cli.py status
```

---

## Flush and re-ingest

```bash
# Remove all capabilities for a source
python cli.py flush --source fakerestapi

# Re-ingest
python cli.py ingest https://fakerestapi.azurewebsites.net/swagger/v1/swagger.json \
  --source-id fakerestapi
```

---

## Preview without writing (dry run)

```bash
python cli.py ingest <url> --dry-run
```

Prints the extracted capability table to the terminal without touching MongoDB or Qdrant.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `MongoDB: unreachable` | mongod not running | Run `mongod --dbpath ~/data/db` |
| `Qdrant: unreachable` | qdrant process not running | Run `~/qdrant &` |
| `No LLM configured` | No API key and no Ollama | Set `LLM_PROVIDER=ollama` and start `ollama serve` |
| Ingest completes but tool names are verbose | LLM enrichment failed validation | Switch to `phi` or `mistral` via `OLLAMA_MODEL=phi` |
| `AttributeError: QdrantClient has no attribute search` | qdrant-client version mismatch | Run `pip install qdrant-client>=1.18.0` and upgrade the server binary to match |
| Embedding download hangs | HuggingFace rate limit | Set `HF_TOKEN=<your_token>` in `.env` or wait and retry |
| `conda: command not found` | conda not on PATH | Run `source ~/miniforge3/etc/profile.d/conda.sh` |

---

## Docker (Phase 4)

A `docker-compose.yml` covering MongoDB + Qdrant is planned for Phase 4.
Until then, run services natively as described above.

---

## Project layout

```
api_discovery/
├── cli.py                  entry point  — python cli.py <command>
├── config.py               env var loading
├── requirements.txt
├── .env.example            template — copy to .env
├── SETUP.md                this file
├── ARCHITECTURE.md         system design
├── LOCAL_SETUP.md          macOS-specific native setup notes
├── phase1_results.md       Phase 1 ingest validation report
├── phase2_results.md       Phase 2 retrieval validation report
├── core/
│   ├── ingestion.py        fetch + parse OpenAPI spec
│   ├── extraction.py       rule-based + LLM capability extraction
│   ├── embeddings.py       sentence-transformers wrapper
│   ├── retrieval.py        NL query → Qdrant → MongoDB
│   └── executor.py         mode=results live GET execution
├── stores/
│   ├── mongo.py            MongoDB CRUD
│   └── qdrant.py           Qdrant vector operations
├── models/
│   └── capability.py       Pydantic models
└── eval/
    ├── golden.json         20-query golden evaluation set
    └── run_eval.py         precision@1 / precision@3 runner
```
