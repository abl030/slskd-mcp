"""Extract parameter types from OpenAPI schemas.

Handles:
- Path parameters ({id}, {username})
- Query parameters
- Request body (JSON)
- $ref resolution
- allOf/oneOf/anyOf composition
- readOnly field exclusion
- Large integer sanitization (>= 2^53)
- Enum value extraction into descriptions
- PATCH/PUT None defaults for optional body fields
"""

from __future__ import annotations

import re
from typing import Any

from .loader import resolve_ref

# Sentinel: integers >= 2^53 are unsafe for JSON serialization
MAX_SAFE_INT = 2**53


def _strip_html(text: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _sanitize_default(value: Any) -> Any:
    """Sanitize default values — replace unsafe large integers with None."""
    if isinstance(value, int) and abs(value) >= MAX_SAFE_INT:
        return None
    return value


def resolve_schema_type(
    spec: dict[str, Any],
    schema: dict[str, Any],
) -> str:
    """Resolve an OpenAPI schema to a Python type string."""
    if not schema:
        return "Any"

    if "$ref" in schema:
        resolved = resolve_ref(spec, schema["$ref"])
        return resolve_schema_type(spec, resolved)

    if "allOf" in schema:
        for sub in schema["allOf"]:
            resolved = sub
            if "$ref" in sub:
                resolved = resolve_ref(spec, sub["$ref"])
            if resolved.get("type") == "object" or "properties" in resolved:
                return "dict"
            if "enum" in resolved:
                return "str"
        return "dict"

    for key in ("oneOf", "anyOf"):
        if key in schema:
            for sub in schema[key]:
                t = resolve_schema_type(spec, sub)
                if t != "Any":
                    return t
            return "Any"

    if "enum" in schema:
        return "str"

    schema_type = schema.get("type")
    if schema_type == "string":
        return "str"
    if schema_type == "integer":
        return "int"
    if schema_type == "number":
        return "float"
    if schema_type == "boolean":
        return "bool"
    if schema_type == "array":
        items = schema.get("items", {})
        item_type = resolve_schema_type(spec, items)
        return f"list[{item_type}]"
    if schema_type == "object" or "properties" in schema:
        return "dict"

    return "Any"


def _get_enum_values(spec: dict[str, Any], schema: dict[str, Any]) -> list[str] | None:
    """Extract enum values from a schema, resolving $ref if needed."""
    if "$ref" in schema:
        resolved = resolve_ref(spec, schema["$ref"])
        return _get_enum_values(spec, resolved)
    if "enum" in schema:
        return [str(v) for v in schema["enum"]]
    if "allOf" in schema:
        for sub in schema["allOf"]:
            vals = _get_enum_values(spec, sub)
            if vals:
                return vals
    return None


def _is_read_only(schema: dict[str, Any]) -> bool:
    """Check if a schema field is readOnly."""
    return schema.get("readOnly", False)


def _flatten_object_schema(
    spec: dict[str, Any],
    schema: dict[str, Any],
    is_update: bool = False,
) -> list[dict[str, Any]]:
    """Flatten an object schema into a list of parameter dicts."""
    if "$ref" in schema:
        schema = resolve_ref(spec, schema["$ref"])

    if "allOf" in schema:
        merged_props: dict[str, Any] = {}
        merged_required: list[str] = []
        for sub in schema["allOf"]:
            if "$ref" in sub:
                sub = resolve_ref(spec, sub["$ref"])
            merged_props.update(sub.get("properties", {}))
            merged_required.extend(sub.get("required", []))
        schema = {
            "type": "object",
            "properties": merged_props,
            "required": merged_required,
        }

    properties = schema.get("properties", {})
    required_fields = set(schema.get("required", []))
    params = []

    for prop_name, prop_schema in properties.items():
        if _is_read_only(prop_schema):
            continue
        if prop_name == "id":
            continue

        param_type = resolve_schema_type(spec, prop_schema)
        description = prop_schema.get("description", "")
        if description:
            description = _strip_html(description)

        enum_values = _get_enum_values(spec, prop_schema)
        if enum_values:
            enum_str = ", ".join(enum_values)
            if description:
                description = f"{description} (values: {enum_str})"
            else:
                description = f"Values: {enum_str}"

        if param_type == "list[dict]":
            description += (
                " Pass as JSON array of objects. If creation fails,"
                " manage these via their dedicated sub-resource endpoints instead."
            )

        is_required = prop_name in required_fields
        default = prop_schema.get("default")
        nullable = prop_schema.get("nullable", False)

        if is_update:
            is_required = False
            default = None
        elif not is_required:
            if default is not None:
                default = _sanitize_default(default)
            else:
                default = None

        params.append({
            "name": prop_name,
            "type": param_type,
            "required": is_required and not is_update,
            "default": default,
            "description": description,
            "enum": enum_values,
            "location": "body",
            "nullable": nullable,
        })

    return params


def parse_parameters(
    spec: dict[str, Any],
    operation: dict[str, Any],
    path: str,
) -> list[dict[str, Any]]:
    """Parse all parameters for an operation."""
    params: list[dict[str, Any]] = []
    method = operation.get("_method", "get")
    is_update = method in ("put", "patch")

    for param in operation.get("parameters", []):
        schema = param.get("schema", {})
        param_type = resolve_schema_type(spec, schema)
        description = param.get("description", "")
        if description:
            description = _strip_html(description)

        enum_values = _get_enum_values(spec, schema)
        if enum_values:
            enum_str = ", ".join(enum_values)
            if description:
                description = f"{description} (values: {enum_str})"
            else:
                description = f"Values: {enum_str}"

        default = param.get("schema", {}).get("default")
        default = _sanitize_default(default)

        is_required = param.get("required", False)
        location = param.get("in", "query")

        params.append({
            "name": param["name"],
            "type": param_type,
            "required": is_required,
            "default": default if not is_required else None,
            "description": description,
            "enum": enum_values,
            "location": location,
            "nullable": schema.get("nullable", False),
        })

    request_body = operation.get("requestBody", {})
    content = request_body.get("content", {})
    json_content = content.get("application/json", {})
    body_schema = json_content.get("schema", {})

    if body_schema:
        resolved = body_schema
        if "$ref" in body_schema:
            resolved = resolve_ref(spec, body_schema["$ref"])

        if resolved.get("type") == "object" or "properties" in resolved or "allOf" in resolved:
            body_params = _flatten_object_schema(spec, body_schema, is_update=is_update)
            existing_names = {p["name"] for p in params}
            body_params = [p for p in body_params if p["name"] not in existing_names]
            params.extend(body_params)
        elif resolved.get("type") == "array":
            item_type = resolve_schema_type(spec, resolved.get("items", {}))
            params.append({
                "name": "body",
                "type": f"list[{item_type}]",
                "required": True,
                "default": None,
                "description": "Request body (array)",
                "enum": None,
                "location": "body",
                "nullable": False,
            })

    return params


def get_response_type(spec: dict[str, Any], operation: dict[str, Any]) -> str:
    """Determine the response type of an operation."""
    responses = operation.get("responses", {})
    success = responses.get("200", responses.get("201", {}))
    content = success.get("content", {})

    for ct in ("application/json", "text/json", "text/plain"):
        if ct in content:
            schema = content[ct].get("schema", {})
            if "$ref" in schema:
                schema = resolve_ref(spec, schema["$ref"])
            if schema.get("type") == "array":
                return "array"
            if "properties" in schema:
                if "records" in schema.get("properties", {}) and "totalRecords" in schema.get("properties", {}):
                    return "paging"
                return "object"
            if schema.get("type") == "object":
                return "object"
    return "none"
