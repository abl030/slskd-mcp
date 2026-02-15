"""Build Jinja2 template context from parsed OpenAPI spec.

Assigns each operation to a module, builds tool definitions,
and assembles the full context dict for server.py.j2.
"""

from __future__ import annotations

from typing import Any

from .loader import get_paths
from .naming import build_tool_name
from .schema_parser import get_response_type, parse_parameters

# Module assignment by API path prefix (longest prefix match)
_PATH_TO_MODULE: dict[str, str] = {
    "/api/v0/searches": "searches",
    "/api/v0/transfers": "transfers",
    "/api/v0/users": "users",
    "/api/v0/files": "files",
    "/api/v0/conversations": "conversations",
    "/api/v0/rooms": "rooms",
    "/api/v0/server": "server",
    "/api/v0/application": "application",
    "/api/v0/options": "options",
    "/api/v0/shares": "shares",
    "/api/v0/session": "session",
    "/api/v0/telemetry": "telemetry",
    "/api/v0/relay": "relay",
    "/api/v0/events": "events",
    "/api/v0/logs": "logs",
}

# HTTP methods considered mutations (require confirm gate)
_MUTATION_METHODS = {"post", "put", "patch", "delete"}

# Workflow hints appended to mutation tool docstrings
_WORKFLOW_HINTS: dict[str, str] = {
    "slskd_create_search": (
        "Note: Search is async. Poll slskd_get_search to check if state is"
        " 'Completed', then call slskd_list_searches_responses to get results."
    ),
    "slskd_create_transfers_download": (
        "Note: After queueing, monitor progress with slskd_list_transfers_downloads."
        " Clear completed downloads with slskd_delete_transfers_downloads_all_completed."
    ),
}

# Paths to skip (non-API endpoints)
_SKIP_PATHS: set[str] = set()

# Path params that need base64 encoding
_BASE64_PARAMS = {"base64SubdirectoryName", "base64FileName"}


def path_to_module(path: str) -> str:
    """Map an API path to its module using longest prefix match."""
    best_match = "application"  # default
    best_len = 0
    for prefix, module in _PATH_TO_MODULE.items():
        if path.startswith(prefix) and len(prefix) > best_len:
            best_match = module
            best_len = len(prefix)
    return best_match


def _should_skip_path(path: str) -> bool:
    """Check if a path should be skipped during generation."""
    return path in _SKIP_PATHS


def _make_description(
    method: str, path: str, operation: dict, response_type: str, tool_name: str,
) -> str:
    """Build a tool description/docstring."""
    summary = operation.get("summary", "")
    description = operation.get("description", "")

    if summary:
        doc = summary
    elif description:
        doc = description.split(".")[0]
    else:
        parts = tool_name.replace("slskd_", "").split("_")
        verb = parts[0].capitalize()
        resource = " ".join(parts[1:])
        has_id = any(p.startswith("{") for p in path.split("/") if p)
        if has_id and method == "get":
            doc = f"Get {resource} by ID"
        elif has_id and method == "delete":
            doc = f"Delete {resource} by ID"
        elif has_id and method in ("put", "patch"):
            doc = f"Update {resource} by ID"
        else:
            doc = f"{verb} {resource}"

    if response_type == "array":
        doc += ". Returns a list."
    elif response_type == "paging":
        doc += ". Returns paginated results."

    doc += " If unexpected errors occur, call slskd_report_issue."

    hint = _WORKFLOW_HINTS.get(tool_name)
    if hint:
        doc += f" {hint}"

    return doc


def _deduplicate_tool_names(tools: list[dict[str, Any]]) -> None:
    """Ensure all tool names are unique by appending method suffix if needed."""
    seen: dict[str, int] = {}
    for tool in tools:
        name = tool["name"]
        if name in seen:
            seen[name] += 1
            tool["name"] = f"{name}_{tool['method']}"
        else:
            seen[name] = 1

    final_seen: dict[str, int] = {}
    for tool in tools:
        name = tool["name"]
        if name in final_seen:
            final_seen[name] += 1
            tool["name"] = f"{name}_{final_seen[name]}"
        else:
            final_seen[name] = 1


def build_context(spec: dict[str, Any]) -> dict[str, Any]:
    """Build the full template context from the OpenAPI spec."""
    paths = get_paths(spec)
    tools: list[dict[str, Any]] = []
    modules: dict[str, list[str]] = {}

    for path, path_item in sorted(paths.items()):
        if _should_skip_path(path):
            continue

        for method in ("get", "post", "put", "delete", "patch"):
            if method not in path_item:
                continue

            operation = path_item[method]
            operation["_method"] = method

            name = build_tool_name(method, path)
            module = path_to_module(path)
            params = parse_parameters(spec, operation, path)
            response_type = get_response_type(spec, operation)

            is_list = response_type in ("array", "paging")
            is_mutation = method in _MUTATION_METHODS

            description = _make_description(method, path, operation, response_type, name)

            tags = operation.get("tags", [])

            # Flag params that need base64 encoding
            has_base64_params = any(
                p["name"] in _BASE64_PARAMS for p in params
            )

            tool = {
                "name": name,
                "method": method,
                "path": path,
                "params": params,
                "module": module,
                "is_mutation": is_mutation,
                "is_list": is_list,
                "is_lookup": False,
                "has_base64_params": has_base64_params,
                "response_type": response_type,
                "description": description,
                "tags": tags,
            }
            tools.append(tool)

            if module not in modules:
                modules[module] = []
            modules[module].append(name)

    _deduplicate_tool_names(tools)

    return {
        "tools": tools,
        "modules": modules,
        "tool_count": len(tools),
        "slskd_version": spec.get("info", {}).get("version", "unknown"),
    }
