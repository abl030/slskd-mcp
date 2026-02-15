# Integration Testing Findings

Detailed findings from Sprint 3 integration testing of the slskd MCP server against a live Docker instance. These supplement the [best practices](mcp-server-best-practices.md) with slskd-specific API behavior.

**Test environment:** Docker `slskd/slskd:latest` with `SLSKD_NO_AUTH=true`, `SLSKD_SLSK_NO_CONNECT=true`, `SLSKD_SWAGGER=true`. Port 15030 mapped to internal 5030.

## Test Infrastructure Lessons

### FastMCP `@mcp.tool()` wraps functions in FunctionTool objects

The `@mcp.tool()` decorator from FastMCP does not return the original async function. It returns a `FunctionTool` pydantic model. To call the underlying function directly in tests, access the `.fn` attribute:

```python
# Wrong — FunctionTool is not callable
result = await server.slskd_list_server()  # TypeError

# Correct — unwrap the original async function
result = await server.slskd_list_server.fn()
```

This affects any test that imports the generated server module and tries to call tools directly. The test fixture handles this:

```python
def _get_tool(name: str):
    obj = getattr(server, name, None)
    return getattr(obj, "fn", obj)  # unwrap FunctionTool
```

### Module-level env var reading requires import ordering

The generated server reads `SLSKD_URL`, `SLSKD_API_KEY`, `SLSKD_MODULES`, and `SLSKD_READ_ONLY` at module top level (lines 23-26). Environment variables must be set *before* importing the module. The fixture chain is:

```
slskd_available → slskd_env → server → tool
    (health)       (env vars)   (import)  (accessor)
```

Using `importlib.import_module()` with `sys.modules` cache clearing ensures a fresh import with the test environment variables.

### Session-scoped autouse fixtures affect all tests

A `scope="session", autouse=True` health check fixture in `tests/conftest.py` will skip ALL tests (including unit tests) when Docker is down. Fix: make the health check non-autouse and chain it as a dependency of the `server` fixture. Only tests that use `tool` or `raw_client` fixtures trigger the health check.

## API Behavior Discoveries

### 1. Non-JSON response: `/api/v0/telemetry/metrics`

**Status:** Bug in generator (unhandled content type)

The metrics endpoint returns Prometheus exposition format (`text/plain`), not JSON:

```
# HELP dotnet_contention_total The number of locks contended
# TYPE dotnet_contention_total counter
dotnet_contention_total 40
```

The generated server calls `response.json()` unconditionally, which raises `json.JSONDecodeError`. This exception is NOT caught by the tool's error handlers (which only catch `httpx.HTTPStatusError` and `httpx.RequestError`).

**Impact:** Calling `slskd_list_telemetry_metrics` crashes with an unhandled exception instead of returning a structured error dict.

**Fix (for generator):** Either:
- Add `json.JSONDecodeError` to the exception chain in the template
- Or add a content-type check before calling `response.json()`, falling back to `{"raw_text": response.text}` for non-JSON responses
- Or add an override/blocklist for known non-JSON endpoints

**Priority:** Medium — the KPIs endpoint (`/api/v0/telemetry/metrics/kpis`) returns JSON and works correctly, so LLMs have an alternative.

### 2. Missing Content-Type on body-less POST: `/api/v0/events/{type}`

**Status:** Bug in generator (missing empty body for POST with only path params)

When a POST endpoint has no request body (only path parameters), the generated server passes `json_body=None` to httpx. This means httpx sends the request without a `Content-Type` header. slskd's ASP.NET backend returns 415 Unsupported Media Type.

Sending an empty JSON body (`json={}`) or any value with `Content-Type: application/json` resolves the issue:

```python
# Fails (415) — no Content-Type header
await client.post("/api/v0/events/DownloadFileComplete")

# Works (201) — Content-Type: application/json is set
await client.post("/api/v0/events/DownloadFileComplete", json={})
```

**Impact:** All POST endpoints with only path parameters and no request body will fail with 415. In the current spec, this affects only `slskd_create_events`.

**Fix (for generator):** In the template, when `is_mutation` and method is POST but there are no body params, pass `json_body={}` instead of omitting it.

### 3. Admin-only endpoints return 403 even with NO_AUTH

**Status:** Expected behavior (not a bug)

Three options endpoints require admin-level access that `SLSKD_NO_AUTH=true` mode doesn't grant:

| Endpoint | HTTP Status | Notes |
|----------|-------------|-------|
| `GET /api/v0/options/debug` | 403 | Debug view of options |
| `GET /api/v0/options/yaml` | 403 | Raw YAML config |
| `GET /api/v0/options/yaml/location` | 403 | Config file path |

These are admin-only endpoints even in no-auth mode. The standard `GET /api/v0/options` works fine and returns the full configuration as JSON.

**Impact:** Three tools return structured 403 errors. LLMs should use `slskd_list_options` for configuration inspection.

### 4. Application dump requires pre-generated dump file

**Status:** Expected behavior (environmental)

`GET /api/v0/application/dump` returns 500 with message "Could not find file '/tmp/slskd_*.dmp'". The dump file must be triggered/created before it can be read. In a fresh Docker container, no dump exists.

**Impact:** `slskd_list_application_dump` returns a 500 error on fresh instances. Not a realistic user scenario (dumps are generated on crash or explicit trigger).

### 5. Search requires Soulseek connection

**Status:** Expected behavior (network-dependent)

`POST /api/v0/searches` returns 409 Conflict with message "The server connection must be connected and logged in to perform a search (currently: Disconnected)" when `SLSKD_SLSK_NO_CONNECT=true`.

**Impact:** Full search CRUD workflow (create → poll → get responses → delete) cannot be tested without a Soulseek connection. Preview (`confirm=False`), list, and 404 error handling are testable.

### 6. Share scan cancel returns 404 when idle

**Status:** Expected behavior (state-dependent)

`DELETE /api/v0/shares` returns 404 when no share scan is currently running. This is a no-op scenario — there's nothing to cancel.

**Impact:** `slskd_delete_shares` returns 404 error when called without an active scan. The tool's docstring should note this: "Returns 404 if no scan is running."

## Coverage Analysis

### Tools exercised against live API (by test class)

| Test Class | Count | What's Tested |
|-----------|-------|---------------|
| TestAlwaysRegisteredTools | 4 | `slskd_get_overview`, `slskd_search_tools`, `slskd_report_issue` |
| TestReadOnlyEndpoints | 21 | All GET endpoints (15 succeed, 6 validate expected errors) |
| TestListToolFeatures | 12 | `_filter_response` on 6 list tools (shape + filter) |
| TestSearchWorkflow | 4 | Preview, 409 error, list, 404 error |
| TestConfirmGates | 38 | All 38 mutations with `confirm=False` |
| TestSafeMutations | 5 | GC, clear transfers, cancel scan, sample event |
| TestErrorHandling | 3 | 404 shape, tool name, user-scoped errors |
| TestCrossVerification | 3 | Raw httpx vs tool output for 3 endpoints |
| TestEmptyCollections | 5 | Empty list validation for 5 resources |
| **Total** | **94** | |

### Tools NOT tested with live execution

| Category | Tools | Reason | Confirm Gate Tested? |
|----------|-------|--------|---------------------|
| Peer browsing | `slskd_get_users_browse`, `slskd_get_users_browse_status`, `slskd_get_users_endpoint`, `slskd_get_users_info`, `slskd_get_users_status` | Require Soulseek network | N/A (GET, no confirm) |
| User directory | `slskd_create_users_directory` | Requires peer connection | Yes |
| Room discovery | `slskd_list_rooms_available` | Requires server connection | N/A (GET) |
| Room operations | `slskd_create_rooms_joined`, `slskd_delete_rooms_joined`, `slskd_create_rooms_joined_members`, `slskd_create_rooms_joined_messages`, `slskd_create_rooms_joined_ticker` | Requires server connection | Yes (all 5) |
| Relay | `slskd_update_relay_agent`, `slskd_delete_relay_agent`, `slskd_get_relay_controller_downloads`, `slskd_create_relay_controller_files`, `slskd_create_relay_controller_shares` | Require relay controller | Yes (4 mutations) |
| Destructive app | `slskd_update_application` (restart), `slskd_delete_application` (stop) | Would kill test instance | Yes |
| Server connect | `slskd_update_server`, `slskd_delete_server` | Would change Soulseek state | Yes |
| Download/upload CRUD | `slskd_create_transfers_downloads`, `slskd_delete_transfers_downloads`, `slskd_delete_transfers_uploads` | Require peer transfers | Yes |
| Conversation CRUD | `slskd_create_conversations`, `slskd_update_conversation`, `slskd_delete_conversation`, `slskd_update_conversation_message` | Require peer messaging | Yes |
| Session login | `slskd_create_session` | Auth mutation | Yes |
| Options mutations | `slskd_create_options_yaml`, `slskd_create_options_yaml_validate` | Admin-only | Yes |
| Share scan | `slskd_update_shares` | Would trigger scan | Yes |

### Cross-verification results

Three endpoints compared tool output against raw httpx. All matched exactly:

- `slskd_list_server` = `GET /api/v0/server` (dict with state, version, etc.)
- `slskd_list_application` = `GET /api/v0/application` (dict with server info)
- `slskd_list_options` = `GET /api/v0/options` (full config dict)

This validates that the generated `SlskdClient` class correctly passes parameters, parses responses, and returns data without transformation for non-list endpoints.

## Recommendations for Future Sprints

### Generator fixes to address in Sprint 4+

1. **Add JSONDecodeError handling** — Catch `json.JSONDecodeError` in the template's exception chain and return a structured error dict. Alternatively, check `Content-Type` header before calling `response.json()`.

2. **Send empty body for body-less POST** — When generating a POST tool with no request body parameters, pass `json_body={}` to ensure `Content-Type: application/json` is sent. ASP.NET backends commonly require this.

3. **Document stateful error codes** — Tools like `slskd_delete_shares` return 404 when there's nothing to cancel. Add docstring hints: "Returns 404 if no scan is currently running."

### Testing gaps to address

1. **Full search CRUD** — Requires a Soulseek connection test environment (not `NO_CONNECT` mode). Could use a mock Soulseek server or a dedicated test network.

2. **Transfer workflow** — Cannot test download/upload without peer connections. Same constraint as search.

3. **Room operations** — Need server connection for room list, join, message, leave cycle.

4. **Relay operations** — Need relay controller infrastructure.

5. **Concurrent tool calls** — No tests for calling multiple tools simultaneously. The `asyncio.gather` in `slskd_get_overview` is the only concurrency pattern.
