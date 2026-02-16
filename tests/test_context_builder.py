"""Tests for the context_builder module."""

from generator.context_builder import build_context, path_to_module
from generator.loader import load_spec


class TestBuildContext:
    """Test the full context builder pipeline with the real spec."""

    @classmethod
    def setup_class(cls):
        """Load spec and build context once for all tests."""
        cls.spec = load_spec()
        cls.ctx = build_context(cls.spec)
        cls.tools_by_name = {t["name"]: t for t in cls.ctx["tools"]}

    def test_tool_count(self):
        """Should produce 93 tools from the slskd spec."""
        assert self.ctx["tool_count"] == 93

    def test_all_tool_names_unique(self):
        """Every tool name must be unique."""
        names = [t["name"] for t in self.ctx["tools"]]
        assert len(names) == len(set(names))

    def test_all_tool_names_valid_identifiers(self):
        """Every tool name must be a valid Python identifier."""
        for tool in self.ctx["tools"]:
            assert tool["name"].isidentifier(), f"{tool['name']} is not a valid identifier"

    def test_all_tool_names_prefixed(self):
        """Every tool name must start with slskd_."""
        for tool in self.ctx["tools"]:
            assert tool["name"].startswith("slskd_"), f"{tool['name']} missing slskd_ prefix"

    def test_modules_complete(self):
        """All expected modules should be present."""
        expected = {
            "application", "conversations", "events", "files", "logs",
            "options", "relay", "rooms", "searches", "server",
            "session", "shares", "telemetry", "transfers", "users",
        }
        assert set(self.ctx["modules"].keys()) == expected

    def test_every_tool_has_module(self):
        """Every tool should be assigned to a module."""
        for tool in self.ctx["tools"]:
            assert tool["module"], f"{tool['name']} has no module"

    def test_mutations_flagged(self):
        """POST/PUT/PATCH/DELETE tools should be flagged as mutations."""
        for tool in self.ctx["tools"]:
            if tool["method"] in ("post", "put", "patch", "delete"):
                assert tool["is_mutation"], f"{tool['name']} ({tool['method']}) should be a mutation"
            else:
                assert not tool["is_mutation"], f"{tool['name']} ({tool['method']}) should not be a mutation"

    def test_response_type_overrides_applied(self):
        """Undocumented array endpoints should have overridden response types."""
        for name in ("slskd_list_searches", "slskd_list_transfers_downloads",
                      "slskd_list_transfers_uploads", "slskd_list_logs"):
            tool = self.tools_by_name[name]
            assert tool["response_type"] == "array", f"{name} should be array"
            assert tool["is_list"], f"{name} should be is_list=True"

    def test_list_tools_have_list_params(self):
        """Tools with is_list=True should be documented with fields/filter in description."""
        for tool in self.ctx["tools"]:
            if tool["is_list"]:
                assert tool["response_type"] in ("array", "paging"), (
                    f"{tool['name']} is_list but response_type={tool['response_type']}"
                )

    def test_array_body_flagged(self):
        """Tools with array request bodies should have is_array_body=True."""
        dl = self.tools_by_name["slskd_create_transfers_downloads"]
        assert dl["is_array_body"] is True

    def test_non_array_body_not_flagged(self):
        """Tools with object request bodies should not have is_array_body=True."""
        search = self.tools_by_name["slskd_create_search"]
        assert search["is_array_body"] is False

    def test_base64_params_flagged(self):
        """Tools with base64-encoded path params should be flagged."""
        tool = self.tools_by_name["slskd_get_files_downloads_directories"]
        assert tool["has_base64_params"]
        b64_params = [p for p in tool["params"] if p["name"] == "base64SubdirectoryName"]
        assert len(b64_params) == 1

    def test_workflow_hints_in_descriptions(self):
        """Workflow hints should appear in tool descriptions."""
        expected = {
            "slskd_create_search": "slskd_get_searches_responses",
            "slskd_create_transfers_downloads": "slskd_list_transfers_downloads",
            "slskd_get_users_browse": "slskd_create_transfers_downloads",
            "slskd_create_rooms_joined": "slskd_create_rooms_joined_messages",
            "slskd_create_conversations": "slskd_get_conversations_messages",
        }
        for tool_name, hint_ref in expected.items():
            tool = self.tools_by_name[tool_name]
            assert hint_ref in tool["description"], (
                f"{tool_name} missing workflow hint referencing {hint_ref}"
            )

    def test_response_enum_docs(self):
        """Response enum values should be documented in relevant tool descriptions."""
        expected = {
            "slskd_list_transfers_downloads": "Transfer states",
            "slskd_list_transfers_uploads": "Transfer states",
            "slskd_list_server": "Server states",
            "slskd_list_events": "Event types",
            "slskd_get_users_status": "Presence values",
        }
        for tool_name, enum_label in expected.items():
            tool = self.tools_by_name[tool_name]
            assert enum_label in tool["description"], (
                f"{tool_name} missing response enum doc for '{enum_label}'"
            )

    def test_report_issue_nudge(self):
        """Every tool description should mention slskd_report_issue."""
        for tool in self.ctx["tools"]:
            assert "slskd_report_issue" in tool["description"], (
                f"{tool['name']} missing report_issue nudge"
            )

    def test_description_no_double_periods(self):
        """No description should have double periods (..)."""
        for tool in self.ctx["tools"]:
            assert ".." not in tool["description"], (
                f"{tool['name']} has double period in description: {tool['description'][:100]}"
            )

    def test_name_overrides_applied(self):
        """Collision overrides should produce clean names instead of _get/_put suffixes."""
        assert "slskd_get_transfer_download" in self.tools_by_name
        assert "slskd_get_transfer_upload" in self.tools_by_name
        assert "slskd_update_conversation_message" in self.tools_by_name
        # Old ugly names should be gone
        assert "slskd_get_transfers_downloads_get" not in self.tools_by_name
        assert "slskd_get_transfers_uploads_get" not in self.tools_by_name
        assert "slskd_update_conversation_put" not in self.tools_by_name

    def test_no_dedup_suffixes(self):
        """No tool should end with a bare _get or _put dedup suffix."""
        for tool in self.ctx["tools"]:
            name = tool["name"]
            assert not name.endswith("_get"), f"{name} has ugly _get dedup suffix"
            assert not name.endswith("_put"), f"{name} has ugly _put dedup suffix"

    def test_param_description_override_applied(self):
        """searchTimeout should say milliseconds, not seconds."""
        tool = self.tools_by_name["slskd_create_search"]
        st = [p for p in tool["params"] if p["name"] == "searchTimeout"]
        assert len(st) == 1
        assert "milliseconds" in st[0]["description"]
        assert "15000" in st[0]["description"]
        assert "in seconds" not in st[0]["description"]

    def test_non_overridden_params_retain_original(self):
        """Params without overrides should keep their spec descriptions."""
        tool = self.tools_by_name["slskd_create_search"]
        st = [p for p in tool["params"] if p["name"] == "searchText"]
        assert len(st) == 1
        # Should have original description from spec, not be empty or overridden
        assert st[0]["description"]

    def test_readonly_fields_excluded(self):
        """readOnly fields should not appear as parameters."""
        for tool in self.ctx["tools"]:
            for param in tool["params"]:
                # readOnly fields have location 'body' and would have been excluded
                # This is a sanity check — if any readOnly field leaks through, it's a bug
                assert param["name"] != "id" or param["location"] == "path", (
                    f"{tool['name']} has 'id' body param (should be excluded as readOnly)"
                )


class TestPathToModule:
    """Test module assignment edge cases."""

    def test_longest_prefix_wins(self):
        """Longer prefix should win over shorter."""
        # /api/v0/transfers/downloads should match transfers (not just transfers prefix)
        assert path_to_module("/api/v0/transfers/downloads") == "transfers"

    def test_unknown_path_defaults(self):
        """Unknown paths should default to 'application'."""
        assert path_to_module("/api/v0/unknown/endpoint") == "application"
