# slskd MCP Server

An MCP (Model Context Protocol) server that gives AI agents full control over [slskd](https://github.com/slskd/slskd), a modern Soulseek client. Auto-generated from the slskd OpenAPI spec (70 paths, 93 operations).

Built because manually searching Soulseek via `podman exec wget` chains was [costing 60% of our tokens](https://github.com/abl030/nixosconfig/blob/master/docs/music-pipeline-postmortem.md). This gives agents direct access to search, download, browse peers, monitor transfers, and manage the slskd instance — the missing piece in the Lidarr → Soulseek → Plex music pipeline.

This entire project — the generator, the server, the test suite, and this README — was built by AI (Claude) and is designed to be installed and used by AI agents.

## Install

### Option 1: Nix Flake (recommended)

```nix
# flake.nix
{
  inputs.slskd-mcp.url = "github:abl030/slskd-mcp";
}
```

```nix
# Use the package
environment.systemPackages = [ inputs.slskd-mcp.packages.${pkgs.system}.default ];

# Or in an MCP server config
{
  command = "${inputs.slskd-mcp.packages.${pkgs.system}.default}/bin/slskd-mcp";
  env = {
    SLSKD_URL = "http://localhost:5030";
    SLSKD_API_KEY = "your-api-key";
  };
}
```

Quick test without installing:

```bash
SLSKD_URL=http://localhost:5030 SLSKD_API_KEY=your-key nix run github:abl030/slskd-mcp
```

### Option 2: uv (non-Nix)

```bash
git clone https://github.com/abl030/slskd-mcp.git
cd slskd-mcp
uv sync
uv run python -m generator    # produces generated/server.py
```

### Configure Your MCP Client

**Claude Code:**

```bash
# Nix
claude mcp add slskd -- \
  env SLSKD_URL=http://YOUR_SLSKD_HOST:5030 \
  SLSKD_API_KEY=YOUR_API_KEY \
  slskd-mcp

# Non-Nix
claude mcp add slskd -- \
  env SLSKD_URL=http://YOUR_SLSKD_HOST:5030 \
  SLSKD_API_KEY=YOUR_API_KEY \
  uv run --directory /path/to/slskd-mcp fastmcp run generated/server.py
```

**Claude Desktop** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "slskd": {
      "command": "slskd-mcp",
      "env": {
        "SLSKD_URL": "http://YOUR_SLSKD_HOST:5030",
        "SLSKD_API_KEY": "YOUR_API_KEY",
        "SLSKD_MODULES": "searches,transfers,users,files,rooms,server"
      }
    }
  }
}
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SLSKD_URL` | `http://localhost:5030` | slskd base URL |
| `SLSKD_API_KEY` | *(required)* | API key (Settings > General > API Keys) |
| `SLSKD_MODULES` | *(all modules)* | Comma-separated list of modules to enable |
| `SLSKD_READ_ONLY` | `false` | Strip all mutation tools (POST/PUT/DELETE) |

### Module Filtering

By default all tools are registered. Set `SLSKD_MODULES` to load only what you need:

| Module | What it covers |
|--------|----------------|
| `searches` | Create searches, list results, get responses, delete searches |
| `transfers` | Download/upload management, queue downloads, cancel, clear completed |
| `users` | Browse peer shares, get user info/status/endpoint, request directories |
| `files` | Download/incomplete file management, delete files/directories |
| `conversations` | Private messaging — send, read, acknowledge messages |
| `rooms` | Chat rooms — join, leave, list, send messages, view members |
| `server` | Server state — connect, disconnect, status |
| `application` | Application info, version, shutdown, restart, GC, dump |
| `options` | Runtime configuration — get/set YAML config |
| `shares` | Local share management — list, rescan, get contents |
| `session` | Authentication — login, session check |
| `telemetry` | Metrics, transfer reports, leaderboards |
| `relay` | Relay agent/controller management |
| `events` | Server-sent events, raise events |
| `logs` | Application logs |

`slskd_get_overview`, `slskd_search_tools`, and `slskd_report_issue` are always registered regardless of module selection.

**Example configurations:**

```bash
# Music pipeline (search + download + browse peers)
SLSKD_MODULES=searches,transfers,users,files

# Monitoring only
SLSKD_MODULES=server,transfers,telemetry
SLSKD_READ_ONLY=true

# Full control
# (default — all modules enabled)
```

## What You Get

**TODO: Tool counts will be filled after generator Sprint 1 completes.**

| Category | Examples |
|----------|---------|
| **Searches** | Create search, list active/completed searches, get responses, delete |
| **Transfers** | List downloads/uploads, queue download from peer, cancel, clear completed |
| **Users** | Browse peer shares, get user info/status, request directory listing |
| **Files** | List/delete downloaded files, list/delete incomplete files |
| **Conversations** | Send/read private messages, acknowledge messages |
| **Rooms** | Join/leave rooms, send messages, list members, available rooms |
| **Server** | Connect/disconnect Soulseek, get server state |
| **Shares** | List local shares, rescan shares, get share contents |
| **Telemetry** | Transfer stats, leaderboards, exception reports |

### High-Level Tools (no API knowledge needed)

| Tool | Description |
|------|-------------|
| `slskd_get_overview` | System summary: server state, transfer counts, search activity |
| `slskd_search_tools` | Keyword search across all tool names/descriptions |
| `slskd_report_issue` | Generate structured bug report |

### Safety: Confirmation Gate

All mutations require `confirm=True`. Without it, you get a dry-run preview:

```
# Preview only — nothing changes
slskd_create_search(searchText="xaviersobased Xavier")

# Actually creates the search
slskd_create_search(searchText="xaviersobased Xavier", confirm=True)
```

### List Tool Filtering

All `slskd_list_*` tools support optional parameters:

- **`fields`** — Comma-separated field names to return (e.g. `"username,state"`)
- **`filter`** — Comma-separated key=value pairs for row filtering (e.g. `"state=Completed"`)

### Error Reporting

Every tool's docstring nudges AI consumers to call `slskd_report_issue` on unexpected errors.

## How It Works

A Python **generator** reads the slskd OpenAPI 3.0.1 spec (70 paths, 93 operations) and produces the MCP server via Jinja2 templates. When slskd updates their API, run a temp container with `SLSKD_SWAGGER=true`, pull the new spec, and re-run:

```bash
# Pull new spec (slskd needs SLSKD_SWAGGER=true to expose it)
docker run -d --name slskd-swagger -e SLSKD_SWAGGER=true -p 15030:5030 slskd/slskd:latest
sleep 5
curl -sf http://localhost:15030/swagger/v0/swagger.json -o spec/openapi.json
docker rm -f slskd-swagger

# Regenerate
nix develop -c python -m generator
```

The generated server uses FastMCP with a single `SlskdClient` class (httpx + API key auth via `X-Api-Key` header). One async tool function per API operation.

### Architecture

```
spec/openapi.json              # slskd OpenAPI 3.0.1 spec (input, 70 paths)
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
```

## Testing

### Unit Tests (no slskd needed)

```bash
nix develop -c python -m pytest tests/ -v
```

### Integration Tests (needs slskd)

```bash
# Start slskd in Docker
docker compose -f docker/docker-compose.yml up -d

# Wait for ready
bash docker/wait-for-ready.sh

# Run integration tests
nix develop -c python -m pytest tests/test_integration.py -v --integration

# Tear down
docker compose -f docker/docker-compose.yml down
```

## Sprint Plan

### Sprint 1: Generator Core
- [ ] OpenAPI spec loader (`loader.py`) — parse paths, operations, schemas
- [ ] Naming conventions (`naming.py`) — `method+path` to `slskd_{verb}_{resource}`
- [ ] Schema parser (`schema_parser.py`) — extract parameter types, handle `$ref`, `allOf`
- [ ] Context builder (`context_builder.py`) — assign modules, build template context
- [ ] Code generator (`codegen.py`) — render server.py via Jinja2
- [ ] Server template (`server.py.j2`) — FastMCP server with SlskdClient, module gating, confirm gates
- [ ] Generate and verify tool count matches spec

### Sprint 2: Quality & Correctness
- [ ] Apply MCP best practices (see `research/mcp-server-best-practices.md`)
  - Sanitize large integers (>= 2^53)
  - Exclude readOnly fields from request parameters
  - Enum values in parameter descriptions
  - Strip HTML from descriptions
  - PATCH defaults to None
- [ ] List tool enhancements: `fields`, `filter` parameters
- [ ] High-level tools: `slskd_get_overview`, `slskd_search_tools`, `slskd_report_issue`
- [ ] Workflow hints for search → download → import pipeline
- [ ] Error wrapping with structured error dicts
- [ ] Base64 encoding helper for file/directory path parameters
- [ ] Unit tests: naming, modules, list tools

### Sprint 3: Integration Testing
- [ ] Docker compose for slskd test instance
- [ ] Integration tests against live slskd
- [ ] Makefile for orchestration
- [ ] Nix flake checks with unit tests

### Sprint 4: LLM Testing
- [ ] Task config and auto-generated task files
- [ ] Run bank tests against slskd in Docker
- [ ] Docstring improvements from test feedback

### Sprint 5: Documentation & Release
- [ ] Fill in tool counts in README
- [ ] Wire into nixosconfig `.mcp.json`
- [ ] PyPI packaging + MCP Registry submission

## slskd-Specific Notes

### Authentication
slskd uses API key authentication via `X-Api-Key` header. The spec doesn't define a security scheme — auth is handled by middleware. Generate an API key in slskd Settings > General > API Keys.

### Base64-Encoded Path Parameters
Several file/directory endpoints use base64-encoded path parameters (`base64SubdirectoryName`, `base64FileName`). The generator should add a helper that auto-encodes these.

### No operationIds in Spec
The slskd spec has no `operationId` fields — tool names must be derived entirely from HTTP method + path (same approach as lidarr-mcp).

### Swagger is a Feature Flag
slskd doesn't expose OpenAPI by default. To regenerate the spec, run slskd with `SLSKD_SWAGGER=true` (env var) or `--swagger` (CLI flag).

### Key Workflows for Music Pipeline

1. **Search and download**: `slskd_create_search` → poll `slskd_get_search` → browse results via `slskd_list_search_responses` → `slskd_create_transfer_download` (queue download from specific peer)
2. **Browse peer shares**: `slskd_get_user_browse` → `slskd_create_user_directory` (get directory listing)
3. **Monitor downloads**: `slskd_list_transfers_downloads` → check status → `slskd_delete_transfers_downloads_completed` (clear finished)

## Dependencies

**Nix users:** `nix run github:abl030/slskd-mcp` — everything bundled.

**Non-Nix users:** Python 3.11+, [uv](https://docs.astral.sh/uv/), fastmcp, httpx, jinja2 (installed by `uv sync`).

## License

MIT
