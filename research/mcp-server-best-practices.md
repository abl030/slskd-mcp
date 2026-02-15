# MCP Server Best Practices

Findings from building three MCP servers (pfSense 677 tools, UniFi 286 tools, Loki 42 tools) and testing them with AI consumers (Claude via bank tester). These are hard-won lessons applicable to any MCP server project.

**Source:** Originally from `pfsense-mcp/research/mcp-server-best-practices.md`, expanded with learnings from UniFi and Loki builds.

**TODO:** Further fill this out during LLM testing of the Lidarr MCP. Reference this document when making generator decisions.

## Tool Schema Constraints

### 1. Return type annotations must cover all response shapes
FastMCP validates tool return values against the function's return type annotation. If your API returns both objects and arrays, the return type must be `dict[str, Any] | list[Any] | str` — not just `dict[str, Any] | str`. A `list` response against a `dict`-only annotation triggers an `Output validation error` that confuses the consumer even though the data was successfully retrieved.

### 2. Sanitize large integers from OpenAPI specs
The Anthropic API rejects tool schemas containing integers that exceed safe serialization limits (e.g., `9223372036854775807` / int64 max). OpenAPI specs commonly use these as sentinel values meaning "no limit". The generator must detect values where `abs(value) >= 2**53` and replace them with `None` defaults. Without this, the entire MCP server fails to register with `tools.N.custom.input_schema: int too big to convert`.

### 3. One bad tool schema poisons the whole server
When the Anthropic API rejects a single tool's schema, ALL tools become unavailable for that request — not just the broken one. This makes schema validation bugs critical-severity, since a single overlooked field can take down the entire server.

## Tool Discoverability

### 4. Consistent naming conventions are highly discoverable
The pattern `{service}_{verb}_{resource}` (e.g., `lidarr_create_artist`, `lidarr_list_albums`, `lidarr_get_queue`) lets the consumer find every tool on the first attempt. Verbs: `get` (singular), `list` (plural), `create`, `update`, `delete`.

### 5. Apply-pattern reminders in docstrings work
Adding `"Note: Call {related_tool} after this for {reason}."` to mutation tool docstrings means the consumer never forgets follow-up steps. For Lidarr: "Call lidarr_search_album after monitoring to trigger a download search."

### 6. Confirmation gates (`confirm=True`) work smoothly
The preview-then-execute pattern for mutations caused zero confusion in testing. The consumer naturally uses `confirm=True` on first attempt. The preview message showing the HTTP method and path provides useful context.

## Tool Count Challenges

### 7. 677 tools is at the edge of API limits
With this many tools, some API calls intermittently fail. Lidarr has ~236 operations which is manageable, but module filtering is still valuable for keeping context windows clean.

## Error Handling

### 8. Distinguish API errors from schema validation errors
When FastMCP's output validation rejects a valid API response, the error message is indistinguishable from an actual API failure. Error messages should clearly indicate the failure source.

### 9. Sibling tool call error propagation is overly aggressive
When one tool in a parallel batch triggers a validation error, FastMCP cancels all sibling calls. For read-only operations, this is unnecessarily conservative.

## OpenAPI-to-MCP Generation Lessons

### 10. Undocumented route differences cause silent failures
OpenAPI specs may document routes that behave differently on the real server. Test generated tools against a live instance.

### 11. `readOnly` schema fields must be excluded from request parameters
Including response-only fields as tool parameters confuses the consumer into thinking they're settable.

### 12. Enum values belong in parameter descriptions
When an API field accepts a fixed set of values, listing them in the parameter description eliminates the most common failure category. Don't rely on the consumer guessing valid values.

### 13. Default values from specs need validation
Not all OpenAPI defaults are safe to use as Python defaults. Sentinel values (int64 max/min), empty objects that should be `None`, and values that depend on server state should all be sanitized during generation.

### 14. Array parameters that are actually sub-resources cause failures
Some APIs expose array fields in the create schema, but passing JSON arrays triggers validation errors. Tool docstrings should note when an array parameter must be managed via sub-resources.

### 15. Conditional required fields must be downgraded to optional
OpenAPI 3.0 can't express "required when X=Y". The generator should detect conditional notes in descriptions and downgrade matching required fields to optional (`default=None`).

### 16. Strip HTML and don't truncate conditional field docs
OpenAPI descriptions often contain HTML tags. Strip HTML, collapse whitespace, preserve full descriptions.

### 17. Conditional field defaults cause type mismatches
Detect conditional fields and set their defaults to `None` so they're only sent when explicitly specified.

### 18. `allOf`/`$ref` in array items must resolve to `dict`, not `str`
When an array's `items` schema uses `allOf` with a `$ref`, the type resolver must recognize this as `list[dict[str, Any]]`, not `list[str]`.

### 19. PATCH/PUT operations must default optional fields to `None`
When an OpenAPI spec defines defaults for optional fields, using those as Python function parameter defaults causes updates to overwrite existing server values with spec defaults. For update operations, all non-required body fields should default to `None`.

### 20. Sub-resource parent_id fields need consistent typing
Normalize to `str | int` everywhere to prevent type errors.

## Testing Methodology

### 21. AI-driven integration testing validates what unit tests can't
A "tester Claude" consumes the MCP server as a real client, executing structured task files against a live instance. This validates tool naming, parameter descriptions, docstrings, and error messages.

### 22. "Worked first try" is the key QA metric
Every tool should succeed on its first invocation with correct parameters. Tools that fail on first attempt waste tokens and context window.

### 23. Independent diagnosis validates analysis
Having a fresh LLM classify all failures independently achieves high agreement with manual analysis and catches wrong assumptions.

### 24. Always re-validate assumed-broken endpoints
Old assumptions carried forward without validation waste coverage points. Never mark an endpoint as permanently broken without running it through a diagnostic loop.

## Lidarr-Specific Notes (to be expanded during testing)

### Unicode normalization
MusicBrainz stores artist names with exotic Unicode characters (U+2011 NON-BREAKING HYPHEN, various dashes). Lidarr's release parser splits on ASCII hyphens only, causing "Unknown Artist" rejections. The MCP should normalize Unicode hyphens in lookup/search tools.

### Command endpoint polymorphism
`POST /api/v1/command` accepts different `name` values (AlbumSearch, RescanArtist, RefreshArtist, ManualImport, etc.). Each command type has different body parameters. The generator should create separate tools per command type rather than one generic `run_command` tool.

### Quality profile workflow
The typical workflow is: add artist -> set quality profile -> monitor album -> search. The `add_artist` tool should accept quality profile and root folder as parameters with sensible defaults from env vars.
