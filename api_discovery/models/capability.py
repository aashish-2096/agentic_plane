from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone


class ExecutionInfo(BaseModel):
    method: str
    path: str
    base_url: str
    curl: str


class OperationalMeta(BaseModel):
    safe: bool = True
    idempotent: bool = True
    requires_auth: bool = False
    destructive: bool = False


class Capability(BaseModel):
    capability_id: str
    org_id: str = "default"
    source_id: str
    tool_name: str
    description: str
    domain: str
    intent_examples: list[str] = Field(default_factory=list)
    input_schema: dict = Field(default_factory=dict)
    output_schema: dict = Field(default_factory=dict)
    response_fields: list[str] = Field(default_factory=list)
    execution: ExecutionInfo
    operational_meta: OperationalMeta = Field(default_factory=OperationalMeta)
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class IngestionSource(BaseModel):
    source_id: str
    org_id: str = "default"
    url: str
    status: str = "pending"          # pending | done | error
    capability_count: int = 0
    ingested_at: Optional[datetime] = None
    error_detail: Optional[str] = None


class SearchResult(BaseModel):
    capability: Capability
    score: float
    rank: int
