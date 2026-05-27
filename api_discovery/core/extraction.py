from __future__ import annotations
import re
import json
import config
from models.capability import Capability, ExecutionInfo, OperationalMeta


def build_capability(op: dict, source_id: str, org_id: str) -> Capability:
    tool_name = _op_id_to_snake(op["operation_id"])
    domain = _infer_domain(op)
    description = op["description"] or op["summary"] or f"{op['method']} {op['path']}"
    intent_examples: list[str] = []

    enriched = _llm_enrich(op)
    if enriched:
        tool_name = enriched.get("tool_name") or tool_name
        domain = enriched.get("domain") or domain
        description = enriched.get("description") or description
        intent_examples = enriched.get("intent_examples") or []

    return Capability(
        capability_id=f"{org_id}:{source_id}:{op['operation_id']}",
        org_id=org_id,
        source_id=source_id,
        tool_name=tool_name,
        description=description,
        domain=domain,
        intent_examples=intent_examples,
        input_schema=_extract_input_schema(op),
        output_schema=_extract_output_schema(op),
        response_fields=_extract_response_fields(op),
        execution=ExecutionInfo(
            method=op["method"],
            path=op["path"],
            base_url=op["base_url"],
            curl=_build_curl(op),
        ),
        operational_meta=OperationalMeta(
            safe=op["method"] == "GET",
            idempotent=op["method"] in ("GET", "PUT"),
            requires_auth=bool(op.get("security")),
            destructive=op["method"] == "DELETE",
        ),
    )


# ── rule-based helpers ─────────────────────────────────────────────────────────

def _op_id_to_snake(operation_id: str) -> str:
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", operation_id)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
    return s.lower().strip("_")


def _infer_domain(op: dict) -> str:
    tags = op.get("tags") or []
    if tags:
        return tags[0].lower()
    parts = [p for p in op["path"].split("/") if p and not p.startswith("{")]
    for part in parts:
        if part.lower() not in ("api", "v1", "v2", "v3"):
            return part.lower()
    return "general"


def _extract_input_schema(op: dict) -> dict:
    schema: dict = {}
    for param in op.get("parameters") or []:
        name = param.get("name", "")
        if not name:
            continue
        p_schema = param.get("schema") or {}
        schema[name] = {
            "type": p_schema.get("type", "string"),
            "in": param.get("in", "query"),
            "required": param.get("required", False),
            "description": param.get("description", ""),
        }
    body = op.get("request_body") or {}
    if body:
        json_content = (body.get("content") or {}).get("application/json") or {}
        body_schema = json_content.get("schema")
        if body_schema:
            schema["body"] = body_schema
    return schema


def _extract_output_schema(op: dict) -> dict:
    success = (op.get("responses") or {}).get("200") or (op.get("responses") or {}).get("201") or {}
    json_content = (success.get("content") or {}).get("application/json") or {}
    return json_content.get("schema") or {}


def _extract_response_fields(op: dict) -> list[str]:
    schema = _extract_output_schema(op)
    return _flatten_schema(schema)


def _flatten_schema(schema: dict, prefix: str = "", depth: int = 0) -> list[str]:
    if depth > 3 or not schema:
        return []

    if schema.get("type") == "array":
        return _flatten_schema(schema.get("items") or {}, prefix, depth)

    properties = schema.get("properties") or {}
    parent = prefix or schema.get("title", "")
    fields = []

    for name, field_schema in properties.items():
        full = f"{parent}.{name}" if parent else name
        fields.append(full)
        if field_schema.get("type") == "object" or field_schema.get("properties"):
            fields.extend(_flatten_schema(field_schema, full, depth + 1))

    return fields


def _build_curl(op: dict) -> str:
    url = op["base_url"].rstrip("/") + op["path"]
    method = op["method"]
    if method in ("POST", "PUT", "PATCH"):
        return f"curl -X {method} '{url}' -H 'Content-Type: application/json' -d '{{}}'"
    return f"curl -X {method} '{url}'"


# ── LLM enrichment ─────────────────────────────────────────────────────────────

def _llm_enrich(op: dict) -> dict | None:
    has_anthropic = bool(config.ANTHROPIC_API_KEY)
    has_openai = bool(config.OPENAI_API_KEY)
    has_ollama = config.LLM_PROVIDER == "ollama"

    if not has_anthropic and not has_openai and not has_ollama:
        return None

    prompt = _build_prompt(op)
    try:
        if has_ollama:
            result = _call_ollama(prompt)
        elif config.LLM_PROVIDER == "anthropic" and has_anthropic:
            result = _call_anthropic(prompt)
        elif has_openai:
            result = _call_openai(prompt)
        else:
            return None
        return result if _is_valid_enrichment(result) else None
    except Exception:
        return None


def _is_valid_enrichment(result: dict | None) -> bool:
    if not isinstance(result, dict):
        return False
    required = {"tool_name", "domain", "description", "intent_examples"}
    if not required.issubset(result.keys()):
        return False
    tn = result.get("tool_name", "")
    # reject if tool_name looks like prose or a placeholder
    if not tn or " " in tn or len(tn) > 60:
        return False
    return True


_FEW_SHOT = [
    ("GET",    "/api/v1/Books",         "Books",      "none",       "list_books",          "books",       "Retrieve all books.",                  ["get all books","list books","fetch publications"]),
    ("GET",    "/api/v1/Books/id",      "Books",      "id:integer", "get_book_by_id",       "books",       "Fetch a single book by its ID.",        ["get book by id","fetch book details","find book"]),
    ("POST",   "/api/v1/Books",         "Books",      "none",       "create_book",          "books",       "Create a new book.",                    ["add a book","create book","new publication"]),
    ("DELETE", "/api/v1/Books/id",      "Books",      "id:integer", "delete_book",          "books",       "Delete a book by its ID.",              ["delete book","remove book","delete publication"]),
    ("GET",    "/api/v1/Authors",       "Authors",    "none",       "list_authors",         "authors",     "Retrieve all authors.",                 ["get all authors","list authors","fetch author list"]),
    ("GET",    "/api/v1/Authors/id",    "Authors",    "id:integer", "get_author_by_id",     "authors",     "Fetch a single author by their ID.",    ["get author","find author by id","fetch author details"]),
    ("GET",    "/api/v1/Activities",    "Activities", "none",       "list_activities",      "activities",  "Retrieve all activities.",              ["get activities","list activities","fetch activity list"]),
    ("GET",    "/api/v1/Users",         "Users",      "none",       "list_users",           "users",       "Retrieve all users.",                   ["get all users","list users","fetch user list"]),
    ("DELETE", "/api/v1/Users/id",      "Users",      "id:integer", "delete_user",          "users",       "Delete a user by their ID.",            ["delete user","remove user by id"]),
]


def _build_prompt(op: dict) -> str:
    params_summary = ", ".join(
        f"{p.get('name')}:{(p.get('schema') or {}).get('type', '?')}"
        for p in (op.get("parameters") or [])[:6]
    ) or "none"
    tags = ", ".join(op.get("tags") or []) or "none"

    # normalise path params to "id" so few-shot examples match cleanly
    norm_path = op["path"].replace("{", "").replace("}", "")

    examples = "\n".join(
        f'Operation: {m} {p}  tags={t}  params={pm}\n'
        f'Output: {{"tool_name":"{tn}","domain":"{d}","description":"{desc}","intent_examples":{json.dumps(ie)}}}'
        for m, p, t, pm, tn, d, desc, ie in _FEW_SHOT
    )
    return (
        f"Extract API metadata as JSON. Follow the exact format shown.\n\n"
        f"{examples}\n\n"
        f"Operation: {op['method']} {norm_path}  tags={tags}  params={params_summary}\n"
        f'Output: {{"'
    )


def _call_ollama(prompt: str) -> dict | None:
    import ollama
    client = ollama.Client(host=config.OLLAMA_URL)
    response = client.generate(model=config.OLLAMA_MODEL, prompt=prompt)
    # model continues from the primed `{"` — prepend it back
    raw = response.response
    return _parse_json('{"' + raw)


def _call_anthropic(prompt: str) -> dict | None:
    import anthropic
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_json(response.content[0].text)


def _call_openai(prompt: str) -> dict | None:
    from openai import OpenAI
    client = OpenAI(api_key=config.OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=512,
    )
    return _parse_json(response.choices[0].message.content or "")


def _parse_json(text: str) -> dict | None:
    text = text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    # find the last {...} block — avoids false matches on path params like {id}
    end = text.rfind("}") + 1
    if end == 0:
        return None
    start = text.rfind("{", 0, end)
    if start == -1:
        return None
    candidate = text[start:end]

    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
            parsed = parsed[0]
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None
