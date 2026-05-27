import uuid
import config
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)

_client: QdrantClient | None = None


def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=config.QDRANT_URL)
        _ensure_collection()
    return _client


def _ensure_collection() -> None:
    existing = {c.name for c in _client.get_collections().collections}
    if config.QDRANT_COLLECTION not in existing:
        _client.create_collection(
            collection_name=config.QDRANT_COLLECTION,
            vectors_config=VectorParams(size=config.VECTOR_DIM, distance=Distance.COSINE),
        )


def _capability_uuid(capability_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, capability_id))


# ── write ──────────────────────────────────────────────────────────────────────

def upsert_vector(capability_id: str, vector: list[float], payload: dict) -> None:
    c = _get_client()
    point = PointStruct(
        id=_capability_uuid(capability_id),
        vector=vector,
        payload={"capability_id": capability_id, **payload},
    )
    c.upsert(collection_name=config.QDRANT_COLLECTION, points=[point])


def delete_by_source(source_id: str, org_id: str) -> None:
    c = _get_client()
    c.delete(
        collection_name=config.QDRANT_COLLECTION,
        points_selector=Filter(
            must=[
                FieldCondition(key="source_id", match=MatchValue(value=source_id)),
                FieldCondition(key="org_id", match=MatchValue(value=org_id)),
            ]
        ),
    )


# ── read ───────────────────────────────────────────────────────────────────────

def search_vectors(
    query_vector: list[float], org_id: str, top_k: int = 5
) -> list[tuple[str, float]]:
    c = _get_client()
    response = c.query_points(
        collection_name=config.QDRANT_COLLECTION,
        query=query_vector,
        query_filter=Filter(
            must=[FieldCondition(key="org_id", match=MatchValue(value=org_id))]
        ),
        limit=top_k,
        with_payload=True,
    )
    return [(r.payload["capability_id"], r.score) for r in response.points]


def count_vectors() -> int:
    try:
        info = _get_client().get_collection(config.QDRANT_COLLECTION)
        return info.vectors_count or 0
    except Exception:
        return 0


# ── health ─────────────────────────────────────────────────────────────────────

def ping() -> bool:
    try:
        QdrantClient(url=config.QDRANT_URL, timeout=3).get_collections()
        return True
    except Exception:
        return False
