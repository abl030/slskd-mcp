"""Load and parse the slskd OpenAPI spec.

Reads spec/openapi.json and extracts paths, operations, schemas.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SPEC_PATH = Path(__file__).parent.parent / "spec" / "openapi.json"


def load_spec(path: Path | None = None) -> dict[str, Any]:
    """Load the OpenAPI spec from disk."""
    spec_file = path or SPEC_PATH
    with open(spec_file) as f:
        return json.load(f)


def get_paths(spec: dict[str, Any]) -> dict[str, Any]:
    """Extract paths from the spec."""
    return spec.get("paths", {})


def get_schemas(spec: dict[str, Any]) -> dict[str, Any]:
    """Extract component schemas from the spec."""
    return spec.get("components", {}).get("schemas", {})


def resolve_ref(spec: dict[str, Any], ref: str) -> dict[str, Any]:
    """Resolve a $ref pointer in the spec."""
    parts = ref.lstrip("#/").split("/")
    node = spec
    for part in parts:
        node = node[part]
    return node
