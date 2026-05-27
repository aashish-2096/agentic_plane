from __future__ import annotations
from core.embeddings import embed_text
from stores.qdrant import search_vectors
from stores.mongo import get_capabilities_by_ids
from models.capability import SearchResult


def search(query: str, org_id: str = "default", top_k: int = 5) -> list[SearchResult]:
    vector = embed_text(query)
    hits = search_vectors(vector, org_id=org_id, top_k=top_k)
    if not hits:
        return []
    capability_ids = [cid for cid, _ in hits]
    score_map = {cid: score for cid, score in hits}
    capabilities = get_capabilities_by_ids(capability_ids)
    return [
        SearchResult(capability=cap, score=round(score_map[cap.capability_id], 4), rank=i + 1)
        for i, cap in enumerate(capabilities)
    ]
