"""Convert HTTP method + path to MCP tool names.

Pattern: slskd_{verb}_{resource}
  - GET collection      -> list_{plural}
  - GET collection/{id} -> get_{singular}
  - POST collection     -> create_{singular}
  - PUT collection/{id} -> update_{singular}
  - DELETE col/{id}     -> delete_{singular}

slskd API prefix: /api/v0/

Examples:
  GET  /api/v0/searches           -> slskd_list_searches
  GET  /api/v0/searches/{id}      -> slskd_get_search
  POST /api/v0/searches           -> slskd_create_search
  DELETE /api/v0/searches/{id}    -> slskd_delete_search
  GET  /api/v0/transfers/downloads -> slskd_list_transfers_downloads
  POST /api/v0/transfers/downloads/{username} -> slskd_create_transfers_download
  GET  /api/v0/users/{username}/browse -> slskd_get_user_browse
  GET  /api/v0/rooms/joined       -> slskd_list_rooms_joined
"""

from __future__ import annotations

import re

# Standard HTTP method to verb mapping
_METHOD_VERBS: dict[str, str] = {
    "get": "list",
    "post": "create",
    "put": "update",
    "delete": "delete",
    "patch": "update",
}

# Known plural/singular mappings for slskd resources
_PLURALS: dict[str, str] = {
    "search": "searches",
    "conversation": "conversations",
    "transfer": "transfers",
    "download": "downloads",
    "upload": "uploads",
    "room": "rooms",
    "share": "shares",
    "user": "users",
    "file": "files",
    "event": "events",
    "log": "logs",
    "message": "messages",
    "member": "members",
    "directory": "directories",
    "option": "options",
    "report": "reports",
    "metric": "metrics",
    "response": "responses",
}

_SINGULARS: dict[str, str] = {v: k for k, v in _PLURALS.items()}


def _pluralize(word: str) -> str:
    """Return the plural form of a resource name."""
    return _PLURALS.get(word, word + "s")


def _singularize(word: str) -> str:
    """Return the singular form of a resource name."""
    if word in _SINGULARS:
        return _SINGULARS[word]
    if word in _PLURALS:
        return word
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith("ses"):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _camel_to_snake(name: str) -> str:
    """Convert camelCase or PascalCase to snake_case."""
    s1 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    return re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s1).lower()


def _sanitize_segment(segment: str) -> str:
    """Sanitize a path segment for use in a Python identifier."""
    name = _camel_to_snake(segment)
    name = re.sub(r"[.\-]", "_", name)
    name = re.sub(r"[^a-z0-9_]", "", name)
    name = re.sub(r"_+", "_", name)
    return name.strip("_")


def _extract_path_parts(path: str) -> list[str]:
    """Extract meaningful path segments, stripping /api/v0/ prefix and {params}."""
    for prefix in ("/api/v0/", "/api/"):
        if path.startswith(prefix):
            path = path[len(prefix):]
            break
    else:
        path = path.lstrip("/")

    parts = [p for p in path.split("/") if p and not p.startswith("{")]
    return parts


def build_tool_name(method: str, path: str, operation_id: str | None = None) -> str:
    """Build a tool name from HTTP method and path.

    Returns a name like 'slskd_list_searches' or 'slskd_get_search'.
    """
    method_lower = method.lower()
    parts = _extract_path_parts(path)
    has_id = any(p.startswith("{") for p in path.split("/") if p)

    if not parts:
        return f"slskd_{_METHOD_VERBS.get(method_lower, method_lower)}_root"

    # Sanitize all parts
    clean_parts = [_sanitize_segment(p) for p in parts]

    # Determine verb
    if method_lower == "get":
        verb = "get" if has_id else "list"
    else:
        verb = _METHOD_VERBS.get(method_lower, method_lower)

    # Single-segment paths: standard CRUD
    if len(clean_parts) == 1:
        resource = clean_parts[0]
        if verb == "list":
            resource = _pluralize(resource)
        elif verb in ("get", "create", "update", "delete"):
            if has_id:
                resource = _singularize(resource)
            elif verb == "create":
                resource = _singularize(resource)
            else:
                resource = _pluralize(resource) if verb == "list" else resource
        return f"slskd_{verb}_{resource}"

    # Multi-segment paths: join with underscores
    resource = "_".join(clean_parts)
    return f"slskd_{verb}_{resource}"
