from pymongo import MongoClient, ASCENDING
from pymongo.errors import ConnectionFailure
import config
from models.capability import Capability, IngestionSource

_client: MongoClient | None = None


def _get_db():
    global _client
    if _client is None:
        _client = MongoClient(config.MONGO_URI)
        _ensure_indexes(_client[config.MONGO_DB])
    return _client[config.MONGO_DB]


def _ensure_indexes(db):
    caps = db["capabilities"]
    caps.create_index([("org_id", ASCENDING), ("domain", ASCENDING)])
    caps.create_index("capability_id", unique=True)

    sources = db["ingestion_sources"]
    sources.create_index([("org_id", ASCENDING), ("status", ASCENDING)])
    sources.create_index("source_id", unique=True)


# ── capabilities ──────────────────────────────────────────────────────────────

def upsert_capability(cap: Capability) -> None:
    db = _get_db()
    data = cap.model_dump()
    db["capabilities"].replace_one({"capability_id": cap.capability_id}, data, upsert=True)


def get_capabilities_by_ids(ids: list[str]) -> list[Capability]:
    db = _get_db()
    docs = list(db["capabilities"].find({"capability_id": {"$in": ids}}))
    id_order = {cid: i for i, cid in enumerate(ids)}
    docs.sort(key=lambda d: id_order.get(d["capability_id"], 999))
    return [Capability(**d) for d in docs]


def get_capability_by_tool_name(tool_name: str, org_id: str) -> Capability | None:
    db = _get_db()
    doc = db["capabilities"].find_one({"tool_name": tool_name, "org_id": org_id})
    return Capability(**doc) if doc else None


def list_capabilities(org_id: str, domain: str | None = None) -> list[Capability]:
    db = _get_db()
    query: dict = {"org_id": org_id}
    if domain:
        query["domain"] = domain
    return [Capability(**d) for d in db["capabilities"].find(query)]


def count_capabilities(org_id: str) -> int:
    return _get_db()["capabilities"].count_documents({"org_id": org_id})


def delete_by_source(source_id: str, org_id: str) -> int:
    result = _get_db()["capabilities"].delete_many({"source_id": source_id, "org_id": org_id})
    return result.deleted_count


# ── ingestion sources ──────────────────────────────────────────────────────────

def upsert_source(source: IngestionSource) -> None:
    db = _get_db()
    db["ingestion_sources"].replace_one(
        {"source_id": source.source_id}, source.model_dump(), upsert=True
    )


def get_source(source_id: str) -> IngestionSource | None:
    doc = _get_db()["ingestion_sources"].find_one({"source_id": source_id})
    return IngestionSource(**doc) if doc else None


def list_sources(org_id: str) -> list[IngestionSource]:
    return [IngestionSource(**d) for d in _get_db()["ingestion_sources"].find({"org_id": org_id})]


def count_sources(org_id: str) -> int:
    return _get_db()["ingestion_sources"].count_documents({"org_id": org_id})


# ── health ─────────────────────────────────────────────────────────────────────

def ping() -> bool:
    try:
        c = MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=3000)
        c.admin.command("ping")
        c.close()
        return True
    except (ConnectionFailure, Exception):
        return False
