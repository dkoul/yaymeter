"""Load and validate OpenAPI 3.x specifications."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from openapi_spec_validator import validate
from openapi_spec_validator.readers import read_from_filename

from api_test_agent.models import ApiInventory, OperationModel, ParameterModel, ResponseModel


class OpenApiLoadError(Exception):
    pass


def spec_hash_from_dict(spec: dict[str, Any]) -> str:
    raw = json.dumps(spec, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def load_spec(path: Path | str) -> tuple[dict[str, Any], str]:
    p = Path(path)
    if not p.exists():
        raise OpenApiLoadError(f"Spec not found: {p}")
    try:
        spec, _ = read_from_filename(str(p))
    except Exception as exc:
        raise OpenApiLoadError(f"Failed to read spec: {exc}") from exc
    try:
        validate(spec)
    except Exception as exc:
        raise OpenApiLoadError(f"OpenAPI validation failed: {exc}") from exc
    version = str(spec.get("openapi", ""))
    if not version.startswith("3."):
        raise OpenApiLoadError(f"Unsupported OpenAPI version: {version!r}; only 3.x is supported")
    return spec, spec_hash_from_dict(spec)


def _resolve_local_ref(spec: dict[str, Any], ref: str) -> dict[str, Any] | None:
    if not ref.startswith("#/"):
        return None
    parts = ref.lstrip("#/").split("/")
    node: Any = spec
    for part in parts:
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, dict) else None


def _schema_type(schema: dict[str, Any] | None) -> str | None:
    if not schema:
        return None
    if "type" in schema:
        return str(schema["type"])
    if "enum" in schema:
        return "string"
    return None


def _inline_or_ref_schema(spec: dict[str, Any], schema: dict[str, Any] | None) -> dict[str, Any] | None:
    if not schema:
        return None
    ref = schema.get("$ref")
    if ref:
        resolved = _resolve_local_ref(spec, ref)
        if resolved is None:
            raise OpenApiLoadError(f"Unsupported or external $ref: {ref}")
        return resolve_schema_refs(spec, resolved)
    return resolve_schema_refs(spec, schema)


def resolve_schema_refs(spec: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """Deep-copy schema tree with local #/$ref resolved."""
    if "$ref" in schema:
        resolved = _resolve_local_ref(spec, schema["$ref"])
        if resolved is None:
            raise OpenApiLoadError(f"Unsupported or external $ref: {schema['$ref']}")
        return resolve_schema_refs(spec, resolved)

    out: dict[str, Any] = {}
    for key, value in schema.items():
        if key == "$ref":
            continue
        if key == "properties" and isinstance(value, dict):
            out[key] = {k: resolve_schema_refs(spec, v) for k, v in value.items() if isinstance(v, dict)}
        elif key == "items" and isinstance(value, dict):
            out[key] = resolve_schema_refs(spec, value)
        elif key in ("allOf", "anyOf", "oneOf") and isinstance(value, list):
            out[key] = [resolve_schema_refs(spec, v) for v in value if isinstance(v, dict)]
        else:
            out[key] = value
    return out


def operation_key(method: str, path: str) -> str:
    return f"{method.upper()} {path}"


def build_inventory(spec: dict[str, Any], spec_hash: str) -> ApiInventory:
    servers = [s.get("url", "") for s in spec.get("servers", []) if isinstance(s, dict)]
    operations: list[OperationModel] = []

    paths = spec.get("paths", {})
    if not isinstance(paths, dict):
        raise OpenApiLoadError("paths must be an object")

    for path, path_item in sorted(paths.items()):
        if not isinstance(path_item, dict):
            continue
        for method in ("get", "post", "put", "patch", "delete", "head", "options"):
            op = path_item.get(method)
            if not op or not isinstance(op, dict):
                continue
            op_id = op.get("operationId") or operation_key(method, path)
            params: list[ParameterModel] = []
            for raw in op.get("parameters", []) + path_item.get("parameters", []):
                if not isinstance(raw, dict):
                    continue
                if "$ref" in raw:
                    resolved = _resolve_local_ref(spec, raw["$ref"])
                    if resolved is None:
                        raise OpenApiLoadError(f"Unresolved parameter ref: {raw['$ref']}")
                    raw = resolved
                schema = raw.get("schema") or {}
                if "$ref" in schema:
                    schema = _inline_or_ref_schema(spec, schema) or {}
                params.append(
                    ParameterModel(
                        name=raw.get("name", "unknown"),
                        location=raw.get("in", "query"),
                        required=bool(raw.get("required", False)),
                        schema_type=_schema_type(schema),
                        format=schema.get("format"),
                        enum=schema.get("enum"),
                        minimum=schema.get("minimum"),
                        maximum=schema.get("maximum"),
                        min_length=schema.get("minLength"),
                        max_length=schema.get("maxLength"),
                    )
                )

            req_body_types: list[str] = []
            req_body_schema: dict[str, Any] | None = None
            rb = op.get("requestBody")
            if isinstance(rb, dict):
                content = rb.get("content", {})
                if isinstance(content, dict):
                    req_body_types = sorted(content.keys())
                    if "application/json" in content:
                        req_body_schema = _inline_or_ref_schema(
                            spec, content["application/json"].get("schema")
                        )

            responses: list[ResponseModel] = []
            for status, resp in sorted(op.get("responses", {}).items(), key=lambda x: x[0]):
                if not isinstance(resp, dict):
                    continue
                ctypes: list[str] = []
                schema_ref = None
                inline = None
                content = resp.get("content", {})
                if isinstance(content, dict) and "application/json" in content:
                    ctypes = ["application/json"]
                    sch = content["application/json"].get("schema")
                    if isinstance(sch, dict):
                        if "$ref" in sch:
                            schema_ref = sch["$ref"]
                        inline = _inline_or_ref_schema(spec, sch)
                responses.append(
                    ResponseModel(
                        status_code=str(status),
                        description=resp.get("description"),
                        content_types=ctypes,
                        schema_ref=schema_ref,
                        inline_schema=inline,
                    )
                )

            security = op.get("security", spec.get("security", []))
            operations.append(
                OperationModel(
                    operation_id=op_id,
                    method=method.upper(),
                    path=path,
                    summary=op.get("summary"),
                    parameters=params,
                    request_body_content_types=req_body_types,
                    request_body_schema=req_body_schema,
                    responses=responses,
                    security=security if isinstance(security, list) else [],
                    tags=op.get("tags", []) or [],
                )
            )

    operations.sort(key=lambda o: (o.path, o.method))
    return ApiInventory(
        title=spec.get("info", {}).get("title") if isinstance(spec.get("info"), dict) else None,
        openapi_version=str(spec.get("openapi", "")),
        spec_hash=spec_hash,
        servers=servers,
        operations=operations,
    )


def load_inventory(path: Path | str) -> ApiInventory:
    spec, spec_hash = load_spec(path)
    return build_inventory(spec, spec_hash)
