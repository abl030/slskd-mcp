"""Integration tests for the slskd MCP generated server.

These tests exercise generated tool functions against a live Docker slskd
instance (docker/docker-compose.yml). They validate:
- Read-only endpoints return expected data shapes
- List tool features (fields, filter) work correctly
- Search CRUD workflow functions end-to-end
- All 38 mutation tools respect confirm=False preview gates
- Safe mutations execute without error
- Error responses have the correct shape
- Tool output matches raw API responses
- API behavior discoveries documented as tests

Skipped automatically when Docker is not running (via conftest.py fixtures).

Known API behaviors discovered during integration testing:
- /api/v0/application/dump returns 500 (dump file not generated in Docker)
- /api/v0/options/debug, /yaml, /yaml/location return 403 (admin-only even with NO_AUTH)
- /api/v0/telemetry/metrics returns Prometheus text/plain (not JSON) — causes JSONDecodeError
- POST /api/v0/events/{type} returns 415 without Content-Type header (generator issue)
- DELETE /api/v0/shares returns 404 when no scan is running
- POST /api/v0/searches returns 409 when Soulseek is disconnected
"""

from __future__ import annotations

from json import JSONDecodeError
from typing import Any

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def assert_no_error(result: Any, tool_name: str = "") -> None:
    """Assert the result is not an error dict from the generated server."""
    if isinstance(result, dict) and result.get("error"):
        pytest.fail(
            f"Tool {tool_name} returned error: "
            f"status={result.get('status')}, message={result.get('message')!r}"
        )


# ===========================================================================
# Always-registered tools
# ===========================================================================

class TestAlwaysRegisteredTools:
    """Tools registered outside module gates: overview, search_tools, report_issue."""

    async def test_get_overview(self, tool):
        result = await tool("slskd_get_overview")()
        assert isinstance(result, dict)
        assert "server" in result
        assert "downloadCount" in result
        assert "uploadCount" in result
        assert "searchCount" in result

    async def test_search_tools_finds_matches(self, tool):
        result = await tool("slskd_search_tools")(keyword="search")
        assert isinstance(result, dict)
        assert result["matches"], "Expected at least one match for 'search'"
        names = [m["name"] for m in result["matches"]]
        assert any("search" in n for n in names)

    async def test_search_tools_no_matches(self, tool):
        result = await tool("slskd_search_tools")(keyword="zzz_nonexistent_zzz")
        assert isinstance(result, dict)
        assert result["matches"] == []

    async def test_report_issue(self, tool):
        result = await tool("slskd_report_issue")(
            tool_name="slskd_test_tool",
            error_message="test error",
        )
        assert isinstance(result, str)
        assert "gh issue create" in result
        assert "slskd_test_tool" in result


# ===========================================================================
# Read-only endpoints
# ===========================================================================

class TestReadOnlyEndpoints:
    """GET endpoints that return data without Soulseek network connection."""

    async def test_list_application(self, tool):
        result = await tool("slskd_list_application")()
        assert_no_error(result, "slskd_list_application")
        assert isinstance(result, dict)

    async def test_list_application_version(self, tool):
        result = await tool("slskd_list_application_version")()
        assert_no_error(result, "slskd_list_application_version")
        # Returns version string or dict
        assert result is not None

    async def test_list_application_version_latest(self, tool):
        result = await tool("slskd_list_application_version_latest")()
        assert_no_error(result, "slskd_list_application_version_latest")
        assert result is not None

    async def test_list_application_dump(self, tool):
        """Dump endpoint returns 500 in Docker (no dump file generated)."""
        result = await tool("slskd_list_application_dump")()
        # API returns 500 because dump file doesn't exist in clean Docker
        assert isinstance(result, dict)
        assert result.get("error") is True
        assert result["source"] == "slskd_api"
        assert result["tool"] == "slskd_list_application_dump"

    async def test_list_server(self, tool):
        result = await tool("slskd_list_server")()
        assert_no_error(result, "slskd_list_server")
        assert isinstance(result, dict)

    async def test_list_session(self, tool):
        result = await tool("slskd_list_session")()
        assert_no_error(result, "slskd_list_session")

    async def test_list_session_enabled(self, tool):
        result = await tool("slskd_list_session_enabled")()
        assert_no_error(result, "slskd_list_session_enabled")

    async def test_list_options(self, tool):
        result = await tool("slskd_list_options")()
        assert_no_error(result, "slskd_list_options")
        assert isinstance(result, dict)

    async def test_list_options_startup(self, tool):
        result = await tool("slskd_list_options_startup")()
        assert_no_error(result, "slskd_list_options_startup")

    async def test_list_options_debug(self, tool):
        """Debug options return 403 (admin-only even with NO_AUTH mode)."""
        result = await tool("slskd_list_options_debug")()
        assert isinstance(result, dict)
        assert result.get("error") is True
        assert result["status"] == 403

    async def test_list_options_yaml(self, tool):
        """YAML options return 403 (admin-only even with NO_AUTH mode)."""
        result = await tool("slskd_list_options_yaml")()
        assert isinstance(result, dict)
        assert result.get("error") is True
        assert result["status"] == 403

    async def test_list_options_yaml_location(self, tool):
        """YAML location returns 403 (admin-only even with NO_AUTH mode)."""
        result = await tool("slskd_list_options_yaml_location")()
        assert isinstance(result, dict)
        assert result.get("error") is True
        assert result["status"] == 403

    async def test_list_logs(self, tool):
        result = await tool("slskd_list_logs")()
        assert_no_error(result, "slskd_list_logs")
        # Wrapped in _filter_response
        assert isinstance(result, dict)
        assert "count" in result

    async def test_list_shares(self, tool):
        result = await tool("slskd_list_shares")()
        assert_no_error(result, "slskd_list_shares")

    async def test_list_shares_contents(self, tool):
        result = await tool("slskd_list_shares_contents")()
        assert_no_error(result, "slskd_list_shares_contents")
        # List tool → _filter_response wrapper
        assert isinstance(result, dict)
        assert "count" in result

    async def test_list_telemetry_metrics(self, tool):
        """Metrics endpoint returns Prometheus text/plain, not JSON.

        The generated server calls response.json() which raises JSONDecodeError.
        This is a known generator limitation for non-JSON endpoints.
        """
        with pytest.raises(JSONDecodeError):
            await tool("slskd_list_telemetry_metrics")()

    async def test_list_telemetry_metrics_kpis(self, tool):
        result = await tool("slskd_list_telemetry_metrics_kpis")()
        assert_no_error(result, "slskd_list_telemetry_metrics_kpis")

    async def test_list_rooms_joined(self, tool):
        result = await tool("slskd_list_rooms_joined")()
        assert_no_error(result, "slskd_list_rooms_joined")

    async def test_list_files_downloads_directories(self, tool):
        result = await tool("slskd_list_files_downloads_directories")()
        assert_no_error(result, "slskd_list_files_downloads_directories")

    async def test_list_files_incomplete_directories(self, tool):
        result = await tool("slskd_list_files_incomplete_directories")()
        assert_no_error(result, "slskd_list_files_incomplete_directories")


# ===========================================================================
# List tool features: fields and filter params
# ===========================================================================

# Tools that return lists and support fields/filter, and work without network.
_LIST_TOOLS = [
    "slskd_list_searches",
    "slskd_list_transfers_downloads",
    "slskd_list_transfers_uploads",
    "slskd_list_logs",
    "slskd_list_conversations",
    "slskd_list_events",
]


class TestListToolFeatures:
    """Validate _filter_response wrapper on list endpoints."""

    @pytest.mark.parametrize("tool_name", _LIST_TOOLS)
    async def test_default_response_shape(self, tool, tool_name):
        """Default call returns summary/count/data structure."""
        result = await tool(tool_name)()
        assert_no_error(result, tool_name)
        assert isinstance(result, dict), f"{tool_name} should return dict"
        assert "summary" in result, f"{tool_name} missing 'summary'"
        assert "count" in result, f"{tool_name} missing 'count'"
        assert "data" in result, f"{tool_name} missing 'data'"
        assert isinstance(result["data"], list)

    @pytest.mark.parametrize("tool_name", _LIST_TOOLS)
    async def test_filter_nonexistent(self, tool, tool_name):
        """Filtering for a nonexistent value returns count=0."""
        result = await tool(tool_name)(filter="id=zzz_nonexistent_zzz")
        assert_no_error(result, tool_name)
        assert isinstance(result, dict)
        assert result["count"] == 0


# ===========================================================================
# Search CRUD workflow
# ===========================================================================

class TestSearchWorkflow:
    """Search workflow tests.

    With SLSKD_SLSK_NO_CONNECT=true, creating a search returns 409 Conflict
    because the Soulseek connection is Disconnected. We test the preview,
    list, and error behavior instead.
    """

    async def test_search_preview(self, tool):
        """Search preview (confirm=False) works without Soulseek connection."""
        preview = await tool("slskd_create_search")(
            searchText="integration-test", confirm=False,
        )
        assert isinstance(preview, dict)
        assert "preview" in preview
        assert "confirm" in preview

    async def test_search_create_returns_409_when_disconnected(self, tool):
        """Creating a search returns 409 when Soulseek is disconnected."""
        result = await tool("slskd_create_search")(
            searchText="integration-test", searchTimeout=5, confirm=True,
        )
        assert isinstance(result, dict)
        assert result.get("error") is True
        assert result["status"] == 409
        assert result["tool"] == "slskd_create_search"

    async def test_search_list_works(self, tool):
        """Listing searches works even without Soulseek connection."""
        result = await tool("slskd_list_searches")()
        assert_no_error(result, "slskd_list_searches")
        assert "count" in result
        assert "data" in result

    async def test_search_get_nonexistent_returns_404(self, tool):
        """Getting a non-existent search returns 404."""
        result = await tool("slskd_get_search")(id="nonexistent-id")
        assert isinstance(result, dict)
        assert result.get("error") is True
        assert result["status"] == 404


# ===========================================================================
# Confirm gates — every mutation tool tested with confirm=False
# ===========================================================================

# (tool_name, kwargs_without_confirm) for all 38 mutation tools.
_MUTATION_TOOLS = [
    ("slskd_update_application", {}),
    ("slskd_delete_application", {}),
    ("slskd_create_application_gc", {}),
    ("slskd_create_application_loopback", {}),
    ("slskd_create_conversations", {"username": "testuser"}),
    ("slskd_update_conversation", {"username": "testuser"}),
    ("slskd_delete_conversation", {"username": "testuser"}),
    ("slskd_update_conversation_message", {"username": "testuser", "id": 1}),
    ("slskd_create_events", {"type": "DownloadFileComplete"}),
    ("slskd_delete_files_downloads_directories", {"base64SubdirectoryName": "test"}),
    ("slskd_delete_files_downloads_files", {"base64FileName": "test.txt"}),
    ("slskd_delete_files_incomplete_directories", {"base64SubdirectoryName": "test"}),
    ("slskd_delete_files_incomplete_files", {"base64FileName": "test.txt"}),
    ("slskd_create_options_yaml", {}),
    ("slskd_create_options_yaml_validate", {}),
    ("slskd_update_relay_agent", {}),
    ("slskd_delete_relay_agent", {}),
    ("slskd_create_relay_controller_files", {"token": "test-token"}),
    ("slskd_create_relay_controller_shares", {"token": "test-token"}),
    ("slskd_create_rooms_joined", {}),
    ("slskd_delete_rooms_joined", {"roomName": "testroom"}),
    ("slskd_create_rooms_joined_members", {"roomName": "testroom"}),
    ("slskd_create_rooms_joined_messages", {"roomName": "testroom"}),
    ("slskd_create_rooms_joined_ticker", {"roomName": "testroom"}),
    ("slskd_create_search", {}),
    ("slskd_update_search", {"id": "nonexistent"}),
    ("slskd_delete_search", {"id": "nonexistent"}),
    ("slskd_update_server", {}),
    ("slskd_delete_server", {}),
    ("slskd_create_session", {}),
    ("slskd_update_shares", {}),
    ("slskd_delete_shares", {}),
    ("slskd_delete_transfers_downloads_all_completed", {}),
    ("slskd_create_transfers_downloads", {"username": "testuser", "body": []}),
    ("slskd_delete_transfers_downloads", {"username": "testuser", "id": "nonexistent"}),
    ("slskd_delete_transfers_uploads_all_completed", {}),
    ("slskd_delete_transfers_uploads", {"username": "testuser", "id": "nonexistent"}),
    ("slskd_create_users_directory", {"username": "testuser"}),
]


class TestConfirmGates:
    """Every mutation tool must return a preview dict when confirm=False."""

    @pytest.mark.parametrize(
        "tool_name,kwargs",
        _MUTATION_TOOLS,
        ids=[t[0] for t in _MUTATION_TOOLS],
    )
    async def test_confirm_false_returns_preview(self, tool, tool_name, kwargs):
        result = await tool(tool_name)(confirm=False, **kwargs)
        assert isinstance(result, dict), (
            f"{tool_name} should return dict, got {type(result).__name__}"
        )
        assert "preview" in result, f"{tool_name} missing 'preview' key"
        assert "confirm" in result, f"{tool_name} missing 'confirm' key"


# ===========================================================================
# Safe mutations — actually execute against Docker
# ===========================================================================

class TestSafeMutations:
    """Mutations that are safe to run against the Docker test instance."""

    async def test_create_application_gc(self, tool):
        """Force garbage collection — harmless."""
        result = await tool("slskd_create_application_gc")(confirm=True)
        assert_no_error(result, "slskd_create_application_gc")

    async def test_delete_transfers_downloads_all_completed(self, tool):
        """Clear completed downloads — empty list, no-op."""
        result = await tool("slskd_delete_transfers_downloads_all_completed")(
            confirm=True,
        )
        assert_no_error(result, "slskd_delete_transfers_downloads_all_completed")

    async def test_delete_transfers_uploads_all_completed(self, tool):
        """Clear completed uploads — empty list, no-op."""
        result = await tool("slskd_delete_transfers_uploads_all_completed")(
            confirm=True,
        )
        assert_no_error(result, "slskd_delete_transfers_uploads_all_completed")

    async def test_delete_shares(self, tool):
        """Cancel share scan returns 404 when no scan is running."""
        result = await tool("slskd_delete_shares")(confirm=True)
        # slskd returns 404 when there's no active scan to cancel
        assert isinstance(result, dict)
        assert result.get("error") is True
        assert result["status"] == 404
        assert result["tool"] == "slskd_delete_shares"

    async def test_create_events(self, tool):
        """Raise sample event returns 415 — POST without body Content-Type.

        The generated server sends POST with no json_body, so httpx omits
        Content-Type header. slskd's ASP.NET backend rejects with 415.
        This is a known generator limitation for POST endpoints with only
        path parameters and no request body.
        """
        result = await tool("slskd_create_events")(
            type="DownloadFileComplete", confirm=True,
        )
        assert isinstance(result, dict)
        assert result.get("error") is True
        assert result["status"] == 415
        assert result["tool"] == "slskd_create_events"


# ===========================================================================
# Error handling
# ===========================================================================

class TestErrorHandling:
    """Validate error response shape for expected failures."""

    async def test_404_error_shape(self, tool):
        """Non-existent search ID should return structured error dict."""
        result = await tool("slskd_get_search")(id="nonexistent-id-12345")
        assert isinstance(result, dict)
        assert result.get("error") is True
        assert result["source"] == "slskd_api"
        assert result["status"] == 404
        assert "message" in result
        assert result["tool"] == "slskd_get_search"

    async def test_error_includes_tool_name(self, tool):
        """Error dict must include the originating tool name."""
        result = await tool("slskd_get_share")(id="nonexistent-share-xyz")
        assert isinstance(result, dict)
        assert result.get("error") is True
        assert result["tool"] == "slskd_get_share"

    async def test_user_scoped_404(self, tool):
        """User-scoped endpoints return 404 for unknown users."""
        result = await tool("slskd_get_transfers_downloads")(
            username="nonexistent_user_xyz",
        )
        assert isinstance(result, dict)
        assert result.get("error") is True
        assert result["source"] == "slskd_api"


# ===========================================================================
# Cross-verification against raw API
# ===========================================================================

class TestCrossVerification:
    """Compare tool output against direct httpx API calls."""

    async def test_list_server_matches_raw(self, tool, raw_client):
        tool_result = await tool("slskd_list_server")()
        raw_resp = await raw_client.get("/api/v0/server")
        raw_data = raw_resp.json()
        assert tool_result == raw_data

    async def test_list_application_matches_raw(self, tool, raw_client):
        tool_result = await tool("slskd_list_application")()
        raw_resp = await raw_client.get("/api/v0/application")
        raw_data = raw_resp.json()
        assert tool_result == raw_data

    async def test_list_options_matches_raw(self, tool, raw_client):
        tool_result = await tool("slskd_list_options")()
        raw_resp = await raw_client.get("/api/v0/options")
        raw_data = raw_resp.json()
        assert tool_result == raw_data


# ===========================================================================
# Empty collections
# ===========================================================================

class TestEmptyCollections:
    """Tools that return valid empty results without Soulseek network."""

    async def test_list_transfers_downloads_empty(self, tool):
        result = await tool("slskd_list_transfers_downloads")()
        assert_no_error(result, "slskd_list_transfers_downloads")
        assert result["count"] == 0

    async def test_list_transfers_uploads_empty(self, tool):
        result = await tool("slskd_list_transfers_uploads")()
        assert_no_error(result, "slskd_list_transfers_uploads")
        assert result["count"] == 0

    async def test_list_conversations_empty(self, tool):
        result = await tool("slskd_list_conversations")()
        assert_no_error(result, "slskd_list_conversations")
        assert result["count"] == 0

    async def test_list_events_valid(self, tool):
        """Event list may have startup events but should be valid."""
        result = await tool("slskd_list_events")()
        assert_no_error(result, "slskd_list_events")
        assert isinstance(result, dict)
        assert "data" in result
        assert isinstance(result["data"], list)

    async def test_list_searches_empty(self, tool):
        """Searches should be empty on a fresh instance (before workflow test)."""
        result = await tool("slskd_list_searches")()
        assert_no_error(result, "slskd_list_searches")
        assert isinstance(result, dict)
        assert isinstance(result["data"], list)


# ===========================================================================
# High-level tools: slskd_get_search_results, slskd_download_directory
# ===========================================================================

class TestHighLevelTools:
    """Tests for the new high-level search/download tools."""

    async def test_get_search_results_registered(self, tool):
        """slskd_get_search_results should be a registered tool."""
        fn = tool("slskd_get_search_results")
        assert fn is not None

    async def test_get_search_results_nonexistent_404(self, tool):
        """slskd_get_search_results with nonexistent search ID returns 404."""
        result = await tool("slskd_get_search_results")(id="nonexistent-id-xyz")
        assert isinstance(result, dict)
        assert result.get("error") is True
        assert result["status"] == 404
        assert result["tool"] == "slskd_get_search_results"

    async def test_download_directory_registered(self, tool):
        """slskd_download_directory should be a registered tool."""
        fn = tool("slskd_download_directory")
        assert fn is not None

    async def test_download_directory_confirm_false_preview(self, tool):
        """slskd_download_directory with confirm=False should return error (no search data)."""
        result = await tool("slskd_download_directory")(
            username="testuser",
            directory="@@testuser\\Music",
            search_id="nonexistent-id-xyz",
            confirm=False,
        )
        assert isinstance(result, dict)
        # With a nonexistent search ID, it will return a 404 error
        assert result.get("error") is True
        assert result["tool"] == "slskd_download_directory"
