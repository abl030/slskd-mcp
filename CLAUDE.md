# slskd MCP Server

Auto-generated MCP server for the slskd API v0. Tools generated from `spec/openapi.json` (OpenAPI 3.0.1, 70 paths, 93 operations). When slskd updates their API, pull a new spec and re-run the generator.

## Rules

1. **Never manually edit `generated/server.py`**. Fix the generator or templates instead.
2. **`spec/openapi.json` is the single source of truth**. All type information, parameter names, and endpoint structure come from the spec.
3. **Test against Docker, not production**. Use `docker/docker-compose.yml` for integration testing.
4. **Always use `nix develop -c`** as the default wrapper for repo commands.
5. **Testing must be automated**. Every feature/fix needs a pytest suite or equivalent.
6. **Add tests with features**. When adding new functionality, always write automated tests in the same change.
7. **Sprint progress lives in CLAUDE.md**. When work spans multiple sessions, document sprint plans, progress, and outcomes here.
8. **Reference `research/mcp-server-best-practices.md`** before making generator decisions. These are hard-won lessons from 4 prior MCP builds (pfSense 677 tools, UniFi 286 tools, Lidarr 235 tools, Loki 42 tools).
9. **Every new feature must include both tests AND docstring updates.** Tool docstrings are the primary way consuming LLMs discover and understand tools. If a feature isn't described in docstrings, it doesn't exist to the LLM. When adding or changing functionality: (a) add/update unit tests, (b) add/update integration tests where the feature touches the generated server, and (c) ensure tool docstrings clearly describe what the tool does, its parameters, expected return values, and any workflow hints.

## Repository Structure

```
spec/openapi.json              # slskd OpenAPI 3.0.1 spec (input)
generator/                     # Python generator
  __main__.py                  # Entry point: python -m generator
  loader.py                    # Load and parse the OpenAPI spec
  naming.py                    # Convert method+path to tool names
  schema_parser.py             # Extract parameter types from schemas
  context_builder.py           # Build template context, assign modules
  codegen.py                   # Render templates and write output
templates/
  server.py.j2                 # FastMCP server template
generated/
  server.py                    # The MCP server (never hand-edit)
tests/                         # Unit + integration tests
research/                      # Best practices, API notes
docker/                        # Integration test infrastructure
```

## Generator

Reads `spec/openapi.json`, builds tool definitions for each path+method, renders via Jinja2.

```bash
nix develop -c python -m generator    # regenerate generated/server.py
```

### Key patterns (matching pfSense/UniFi/Loki/Lidarr MCPs):
- **FastMCP** server with `SlskdClient` (httpx + X-Api-Key auth)
- **Module gating**: tools wrapped in `if "module" in _SLSKD_MODULES:` blocks
- **Read-only mode**: mutation tools additionally gated on `not _SLSKD_READ_ONLY`
- **Confirmation gates**: all mutations require `confirm=True`
- **List tool enhancements**: `fields` (field selection) and `filter` (row filtering) params
- **High-level tools**: `slskd_get_overview`, `slskd_search_tools`, `slskd_report_issue`
- **Error reporting nudge**: every docstring says to call `slskd_report_issue` on unexpected errors

### Generator best practices (from research/mcp-server-best-practices.md):
- Sanitize large integers (>= 2^53) — Anthropic API rejects them
- Exclude `readOnly` schema fields from request parameters
- Put enum values in parameter descriptions
- Strip HTML from descriptions
- PATCH defaults to `None` (not spec defaults) to avoid overwriting
- `allOf`/`$ref` in array items must resolve to `dict`, not `str`
- Consistent naming: `slskd_{verb}_{resource}` (get/list/create/update/delete)

### Module system:
- Each API path maps to a module via prefix matching
- `codegen.py` groups tools by `(module, is_mutation)` and wraps in `if` blocks
- `slskd_get_overview`, `slskd_search_tools`, `slskd_report_issue` always registered

### slskd-specific notes:
- Auth is via `X-Api-Key` header (no securitySchemes in spec, middleware-handled)
- No `operationId` in spec — tool names derived from method + path
- Base64-encoded path params: `base64SubdirectoryName`, `base64FileName` need auto-encoding helper
- Swagger is a feature flag (`SLSKD_SWAGGER=true` or `--swagger`) — not exposed by default
- The `/api/v0/searches` POST creates a search, GET lists all. `/api/v0/searches/{id}/responses` returns search results.
- Downloads are queued per-user: `POST /api/v0/transfers/downloads/{username}` with file list in body
- Several endpoints use `{username}` as path param — these are Soulseek peer usernames, not slskd users

## Sprint Progress

### Sprint 1: Generator Core
Status: NOT STARTED

### Sprint 2: Quality & Correctness
Status: NOT STARTED

### Sprint 3: Integration Testing
Status: NOT STARTED

### Sprint 4: LLM Testing
Status: NOT STARTED

### Sprint 5: Documentation & Release
Status: NOT STARTED
