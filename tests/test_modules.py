"""Tests for module assignment."""

from generator.context_builder import path_to_module


class TestModuleAssignment:
    """Test that API paths map to the correct modules."""

    def test_searches(self):
        assert path_to_module("/api/v0/searches") == "searches"
        assert path_to_module("/api/v0/searches/123") == "searches"
        assert path_to_module("/api/v0/searches/123/responses") == "searches"

    def test_transfers(self):
        assert path_to_module("/api/v0/transfers/downloads") == "transfers"
        assert path_to_module("/api/v0/transfers/uploads") == "transfers"

    def test_users(self):
        assert path_to_module("/api/v0/users/test/browse") == "users"

    def test_files(self):
        assert path_to_module("/api/v0/files/downloads/directories") == "files"

    def test_conversations(self):
        assert path_to_module("/api/v0/conversations") == "conversations"

    def test_rooms(self):
        assert path_to_module("/api/v0/rooms/joined") == "rooms"
        assert path_to_module("/api/v0/rooms/available") == "rooms"

    def test_server(self):
        assert path_to_module("/api/v0/server") == "server"

    def test_application(self):
        assert path_to_module("/api/v0/application") == "application"
        assert path_to_module("/api/v0/application/version") == "application"

    def test_shares(self):
        assert path_to_module("/api/v0/shares") == "shares"

    def test_telemetry(self):
        assert path_to_module("/api/v0/telemetry/metrics") == "telemetry"

    def test_default_module(self):
        """Unknown paths should fall back to 'application'."""
        assert path_to_module("/api/v0/unknown") == "application"
