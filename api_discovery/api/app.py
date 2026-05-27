from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import config
import stores.mongo as mongo
import stores.qdrant as qdrant

app = FastAPI(
    title="Agentic API Capability Registry",
    description=(
        "Semantic capability discovery over Swagger/OpenAPI specs. "
        "Ingest any API spec, then search capabilities using natural language."
    ),
    version="0.2.0",
)


# ── request / response models ──────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    mode: str = "curl"       # curl | results
    top_k: int = 5
    org_id: str = "default"

class IngestRequest(BaseModel):
    url: str
    source_id: Optional[str] = None
    org_id: str = "default"
    dry_run: bool = False

class CapabilityCard(BaseModel):
    capability_id: str
    tool_name: str
    domain: str
    description: str
    intent_examples: list[str]
    method: str
    path: str
    base_url: str
    curl: str
    input_schema: dict
    output_schema: dict
    response_fields: list[str]
    safe: bool
    idempotent: bool
    requires_auth: bool
    destructive: bool
    ingested_at: str

class SearchHit(BaseModel):
    rank: int
    score: float
    capability: CapabilityCard

class SearchResponse(BaseModel):
    query: str
    mode: str
    org_id: str
    hits: list[SearchHit]
    # populated only when mode=results and top hit is safe
    live_payload: Optional[Any] = None
    execution_note: Optional[str] = None

class SourceCard(BaseModel):
    source_id: str
    org_id: str
    url: str
    status: str
    capability_count: int
    ingested_at: Optional[str]
    error_detail: Optional[str]

class HealthResponse(BaseModel):
    mongodb: str
    qdrant: str
    capabilities: int
    sources: int
    org_id: str

class IngestResponse(BaseModel):
    source_id: str
    org_id: str
    capability_count: int
    status: str
    dry_run: bool
    capabilities: Optional[list[CapabilityCard]] = None   # populated on dry_run


# ── helpers ────────────────────────────────────────────────────────────────────

def _to_card(cap) -> CapabilityCard:
    return CapabilityCard(
        capability_id=cap.capability_id,
        tool_name=cap.tool_name,
        domain=cap.domain,
        description=cap.description,
        intent_examples=cap.intent_examples,
        method=cap.execution.method,
        path=cap.execution.path,
        base_url=cap.execution.base_url,
        curl=cap.execution.curl,
        input_schema=cap.input_schema,
        output_schema=cap.output_schema,
        response_fields=cap.response_fields,
        safe=cap.operational_meta.safe,
        idempotent=cap.operational_meta.idempotent,
        requires_auth=cap.operational_meta.requires_auth,
        destructive=cap.operational_meta.destructive,
        ingested_at=cap.ingested_at.isoformat(),
    )


# ── routes ─────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["System"])
def health():
    """Connection health and registry counts."""
    mongo_ok = mongo.ping()
    qdrant_ok = qdrant.ping()
    return HealthResponse(
        mongodb="connected" if mongo_ok else "unreachable",
        qdrant="connected" if qdrant_ok else "unreachable",
        capabilities=mongo.count_capabilities(config.DEFAULT_ORG_ID) if mongo_ok else 0,
        sources=mongo.count_sources(config.DEFAULT_ORG_ID) if mongo_ok else 0,
        org_id=config.DEFAULT_ORG_ID,
    )


@app.post("/search", response_model=SearchResponse, tags=["Discovery"])
def search(req: SearchRequest):
    """
    Search capabilities using natural language.

    - **mode=curl** — returns ranked capabilities with curl commands (default)
    - **mode=results** — executes the top safe match and returns the live API payload
    """
    from core.retrieval import search as do_search
    from core.executor import execute

    results = do_search(req.query, org_id=req.org_id, top_k=req.top_k)
    hits = [SearchHit(rank=r.rank, score=r.score, capability=_to_card(r.capability)) for r in results]

    live_payload = None
    note = None

    if req.mode == "results" and results:
        top = results[0].capability
        if top.operational_meta.safe:
            try:
                live_payload = execute(top)
            except Exception as e:
                note = f"Execution failed: {e}"
        else:
            note = f"Top match '{top.tool_name}' is {top.execution.method} — not safe to execute. Returning curl only."

    return SearchResponse(
        query=req.query,
        mode=req.mode,
        org_id=req.org_id,
        hits=hits,
        live_payload=live_payload,
        execution_note=note,
    )


@app.get("/capabilities", response_model=list[CapabilityCard], tags=["Discovery"])
def list_capabilities(
    domain: Optional[str] = Query(None, description="Filter by domain"),
    org_id: str = Query("default"),
):
    """List all registered capabilities, optionally filtered by domain."""
    caps = mongo.list_capabilities(org_id, domain=domain)
    return sorted(
        [_to_card(c) for c in caps],
        key=lambda c: (c.domain, c.method, c.tool_name),
    )


@app.get("/capabilities/{tool_name}", response_model=CapabilityCard, tags=["Discovery"])
def get_capability(tool_name: str, org_id: str = Query("default")):
    """Full detail for a single capability by tool_name."""
    cap = mongo.get_capability_by_tool_name(tool_name, org_id)
    if not cap:
        raise HTTPException(status_code=404, detail=f"Capability '{tool_name}' not found")
    return _to_card(cap)


@app.get("/sources", response_model=list[SourceCard], tags=["Ingestion"])
def list_sources(org_id: str = Query("default")):
    """List all ingested API sources."""
    return [
        SourceCard(
            source_id=s.source_id,
            org_id=s.org_id,
            url=s.url,
            status=s.status,
            capability_count=s.capability_count,
            ingested_at=s.ingested_at.isoformat() if s.ingested_at else None,
            error_detail=s.error_detail,
        )
        for s in mongo.list_sources(org_id)
    ]


@app.post("/ingest", response_model=IngestResponse, tags=["Ingestion"])
def ingest(req: IngestRequest):
    """
    Ingest a Swagger/OpenAPI specification.

    Fetches the spec, extracts capabilities with LLM enrichment, embeds them,
    and writes to MongoDB + Qdrant. Blocks until complete (~30s–3min depending
    on spec size and LLM provider).

    Set **dry_run=true** to preview extracted capabilities without writing to stores.
    """
    from core.ingestion import fetch_spec, extract_base_url, extract_operations
    from core.extraction import build_capability
    from core.embeddings import embed_text, build_embedding_text
    from models.capability import IngestionSource

    source_id = req.source_id or urlparse(req.url).netloc.replace(".", "_").replace("-", "_")

    if not req.dry_run:
        mongo.upsert_source(IngestionSource(
            source_id=source_id, org_id=req.org_id, url=req.url, status="pending"
        ))

    try:
        spec = fetch_spec(req.url)
    except RuntimeError as e:
        if not req.dry_run:
            mongo.upsert_source(IngestionSource(
                source_id=source_id, org_id=req.org_id, url=req.url,
                status="error", error_detail=str(e)
            ))
        raise HTTPException(status_code=422, detail=str(e))

    base_url = extract_base_url(spec, req.url)
    operations = extract_operations(spec, base_url)
    capabilities = [build_capability(op, source_id=source_id, org_id=req.org_id) for op in operations]

    if req.dry_run:
        return IngestResponse(
            source_id=source_id,
            org_id=req.org_id,
            capability_count=len(capabilities),
            status="dry_run",
            dry_run=True,
            capabilities=[_to_card(c) for c in capabilities],
        )

    for cap in capabilities:
        vector = embed_text(build_embedding_text(cap))
        mongo.upsert_capability(cap)
        qdrant.upsert_vector(cap.capability_id, vector, payload={
            "org_id": cap.org_id,
            "source_id": cap.source_id,
            "domain": cap.domain,
            "tool_name": cap.tool_name,
        })

    mongo.upsert_source(IngestionSource(
        source_id=source_id, org_id=req.org_id, url=req.url,
        status="done", capability_count=len(capabilities),
        ingested_at=datetime.now(timezone.utc),
    ))

    return IngestResponse(
        source_id=source_id,
        org_id=req.org_id,
        capability_count=len(capabilities),
        status="done",
        dry_run=False,
    )


@app.delete("/sources/{source_id}", tags=["Ingestion"])
def flush_source(source_id: str, org_id: str = Query("default")):
    """Remove all capabilities for a given source from MongoDB and Qdrant."""
    n = mongo.delete_by_source(source_id, org_id)
    qdrant.delete_by_source(source_id, org_id)
    return {"source_id": source_id, "org_id": org_id, "capabilities_removed": n}
