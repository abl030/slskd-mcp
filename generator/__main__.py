"""Entry point: python -m generator

Reads spec/openapi.json, generates generated/server.py.
"""

from __future__ import annotations

from .loader import load_spec
from .naming import build_tool_name
from .schema_parser import parse_parameters
from .context_builder import build_context
from .codegen import generate

def main() -> None:
    spec = load_spec()
    context = build_context(spec)
    generate(context)

if __name__ == "__main__":
    main()
