from __future__ import annotations
import httpx
from models.capability import Capability


def execute(cap: Capability, timeout: int = 15) -> dict | list:
    if not cap.operational_meta.safe:
        raise ValueError(
            f"{cap.tool_name} is not safe (method={cap.execution.method}). "
            "mode=results is restricted to GET-only endpoints."
        )
    url = cap.execution.base_url.rstrip("/") + cap.execution.path
    # Resolve any unfilled path params to placeholder values so the request
    # at least returns a typed error rather than a 404 on the param itself.
    url = _resolve_path(url)
    resp = httpx.get(url, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    return resp.json()


def _resolve_path(url: str) -> str:
    import re
    return re.sub(r"\{[^}]+\}", "1", url)
