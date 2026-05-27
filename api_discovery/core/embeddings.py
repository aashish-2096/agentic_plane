from __future__ import annotations
import config
from models.capability import Capability

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(config.EMBEDDING_MODEL)
    return _model


def embed_text(text: str) -> list[float]:
    return _get_model().encode(text).tolist()


def build_embedding_text(cap: Capability) -> str:
    parts = [
        cap.tool_name,
        cap.description,
        ", ".join(cap.intent_examples),
        ", ".join(cap.response_fields),
    ]
    return ". ".join(p for p in parts if p)
