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

# Workflow hints appended to tool docstrings
_WORKFLOW_HINTS: dict[str, str] = {
    "slskd_create_search": (
        "Note: Search is async. Poll slskd_get_search to check if state is"
        " 'Completed', then call slskd_get_search_results to get filtered results."
        " Tip: Soulseek matches ALL search terms against file paths. Use fewer,"
        " more distinctive terms (e.g. 'ElectroSoul mp3' not"
        " 'DJ Harrison ElectroSoul mp3 320'). Format words like 'mp3' help,"
        " but bitrate numbers rarely appear in filenames."
    ),
    "slskd_get_searches_responses": (
        "Note: For filtered and ranked results, use slskd_get_search_results"
        " instead, which supports extension filtering, bitrate filtering,"
        " and source ranking."
    ),
    "slskd_create_transfers_downloads": (
        "Note: After queueing, monitor progress with slskd_list_transfers_downloads."
        " Clear completed downloads with slskd_delete_transfers_downloads_all_completed."
    ),
    "slskd_get_users_browse": (
        "Note: To download files from results, pass them to"
        " slskd_create_transfers_downloads with the username."
    ),
    "slskd_create_rooms_joined": (
        "Note: After joining, send messages with slskd_create_rooms_joined_messages"
        " and read messages with slskd_get_rooms_joined_messages."
    ),
    "slskd_create_conversations": (
        "Note: Read replies with slskd_get_conversations_messages."
        " Acknowledge messages with slskd_update_conversation."
    ),
    "slskd_list_transfers_downloads": (
        "Note: Transfer states: Requested, Queued, Initializing, InProgress,"
        " Completed, Succeeded, Cancelled, TimedOut, Errored, Rejected, Aborted."
    ),
    "slskd_list_transfers_uploads": (
        "Note: Transfer states: Requested, Queued, Initializing, InProgress,"
        " Completed, Succeeded, Cancelled, TimedOut, Errored, Rejected, Aborted."
    ),
    "slskd_list_server": (
        "Note: Server states: Disconnected, Connected, LoggedIn,"
        " Connecting, LoggingIn, Disconnecting."
    ),
    "slskd_list_events": (
        "Note: Event types: DownloadFileComplete, DownloadDirectoryComplete,"
        " UploadFileComplete, PrivateMessageReceived, RoomMessageReceived."
    ),
    "slskd_get_users_status": (
        "Note: Presence values: Offline, Away, Online."
    ),
}

# Name overrides for collision cases where dedup produces ugly suffixes.
# Pattern: (method, path) -> desired tool name.
_NAME_OVERRIDES: dict[tuple[str, str], str] = {
    ("get", "/api/v0/transfers/downloads/{username}/{id}"): "slskd_get_transfer_download",
    ("get", "/api/v0/transfers/uploads/{username}/{id}"): "slskd_get_transfer_upload",
    ("put", "/api/v0/conversations/{username}/{id}"): "slskd_update_conversation_message",
}

# Override response types for endpoints whose spec lacks response schemas.
# slskd's ASP.NET generator often omits array response schemas.
_RESPONSE_TYPE_OVERRIDES: dict[str, str] = {
    "GET /api/v0/searches": "array",
    "GET /api/v0/transfers/downloads": "array",
    "GET /api/v0/transfers/uploads": "array",
    "GET /api/v0/logs": "array",
}

# Override parameter descriptions where the spec is wrong or misleading.
# Key: (tool_name, param_name) → corrected description string.
_PARAM_DESCRIPTION_OVERRIDES: dict[tuple[str, str], str] = {
    ("slskd_create_search", "searchTimeout"): (
        "Gets or sets the search timeout value, in milliseconds,"
        " used to determine when the search is complete. (Default = 15000)."
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

    doc = doc.rstrip(". ")
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

            name = _NAME_OVERRIDES.get((method, path)) or build_tool_name(method, path)
            module = path_to_module(path)
            params = parse_parameters(spec, operation, path)
            response_type = get_response_type(spec, operation)

            # Apply overrides for endpoints with undocumented response types
            override_key = f"{method.upper()} {path}"
            if response_type == "none" and override_key in _RESPONSE_TYPE_OVERRIDES:
                response_type = _RESPONSE_TYPE_OVERRIDES[override_key]

            # Apply parameter description overrides
            for param in params:
                override_key = (name, param["name"])
                if override_key in _PARAM_DESCRIPTION_OVERRIDES:
                    param["description"] = _PARAM_DESCRIPTION_OVERRIDES[override_key]

            is_list = response_type in ("array", "paging")
            is_mutation = method in _MUTATION_METHODS

            description = _make_description(method, path, operation, response_type, name)

            tags = operation.get("tags", [])

            # Flag params that need base64 encoding
            has_base64_params = any(
                p["name"] in _BASE64_PARAMS for p in params
            )

            # Flag tools whose request body is a raw array (not flattened object).
            # These need json_body=body instead of json_body={"body": body}.
            body_params = [p for p in params if p["location"] == "body"]
            is_array_body = (
                len(body_params) == 1
                and body_params[0]["name"] == "body"
                and body_params[0]["type"].startswith("list[")
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
                "is_array_body": is_array_body,
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
