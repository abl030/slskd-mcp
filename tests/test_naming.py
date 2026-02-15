"""Tests for the naming module."""

from generator.naming import build_tool_name


class TestBuildToolName:
    """Test tool name generation from HTTP method + path."""

    def test_list_searches(self):
        assert build_tool_name("get", "/api/v0/searches") == "slskd_list_searches"

    def test_get_search(self):
        assert build_tool_name("get", "/api/v0/searches/{id}") == "slskd_get_search"

    def test_create_search(self):
        assert build_tool_name("post", "/api/v0/searches") == "slskd_create_search"

    def test_delete_search(self):
        assert build_tool_name("delete", "/api/v0/searches/{id}") == "slskd_delete_search"

    def test_list_transfers_downloads(self):
        assert build_tool_name("get", "/api/v0/transfers/downloads") == "slskd_list_transfers_downloads"

    def test_get_user_browse(self):
        assert build_tool_name("get", "/api/v0/users/{username}/browse") == "slskd_get_users_browse"

    def test_list_rooms_joined(self):
        assert build_tool_name("get", "/api/v0/rooms/joined") == "slskd_list_rooms_joined"

    def test_get_server(self):
        assert build_tool_name("get", "/api/v0/server") == "slskd_list_server"

    def test_create_conversation_message(self):
        assert build_tool_name("post", "/api/v0/conversations/{username}") == "slskd_create_conversations"

    def test_list_search_responses(self):
        assert build_tool_name("get", "/api/v0/searches/{id}/responses") == "slskd_get_searches_responses"

    def test_prefix_only(self):
        """All tool names should start with slskd_."""
        name = build_tool_name("get", "/api/v0/application")
        assert name.startswith("slskd_")

    def test_valid_python_identifier(self):
        """Tool names must be valid Python identifiers."""
        name = build_tool_name("get", "/api/v0/files/downloads/directories/{base64SubdirectoryName}")
        assert name.isidentifier()
