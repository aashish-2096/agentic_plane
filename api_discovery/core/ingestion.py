from urllib.parse import urlparse
import prance


def fetch_spec(url: str) -> dict:
    try:
        parser = prance.ResolvingParser(url, lazy=False, strict=False)
        return parser.specification
    except Exception as e:
        raise RuntimeError(f"Failed to fetch/parse spec from {url}: {e}")


def extract_base_url(spec: dict, fallback_url: str) -> str:
    # OpenAPI 3.0
    servers = spec.get("servers") or []
    if servers:
        return servers[0].get("url", "").rstrip("/")

    # Swagger 2.0
    host = spec.get("host", "")
    if host:
        schemes = spec.get("schemes") or ["https"]
        base_path = spec.get("basePath", "").rstrip("/")
        return f"{schemes[0]}://{host}{base_path}"

    parsed = urlparse(fallback_url)
    return f"{parsed.scheme}://{parsed.netloc}"


def extract_operations(spec: dict, base_url: str) -> list[dict]:
    operations = []
    paths = spec.get("paths") or {}

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        path_params = path_item.get("parameters") or []

        for method in ("get", "post", "put", "patch", "delete"):
            op = path_item.get(method)
            if not op or not isinstance(op, dict):
                continue

            # Merge path-level and operation-level parameters
            params = path_params + (op.get("parameters") or [])

            operations.append({
                "method": method.upper(),
                "path": path,
                "operation_id": op.get("operationId") or f"{method.upper()}_{path.replace('/', '_').strip('_')}",
                "summary": op.get("summary") or "",
                "description": op.get("description") or op.get("summary") or "",
                "tags": op.get("tags") or [],
                "parameters": params,
                "request_body": op.get("requestBody") or {},
                "responses": op.get("responses") or {},
                "base_url": base_url,
            })

    return operations
