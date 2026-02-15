"""Render templates and write generated output.

Takes the context from context_builder and produces generated/server.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import jinja2

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
OUTPUT_DIR = Path(__file__).parent.parent / "generated"


def generate(context: dict[str, Any]) -> None:
    """Render the server template and write to generated/server.py."""
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATE_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("server.py.j2")
    output = template.render(**context)

    OUTPUT_DIR.mkdir(exist_ok=True)
    output_path = OUTPUT_DIR / "server.py"
    output_path.write_text(output)

    print(f"Generated {output_path} ({context['tool_count']} tools)")
