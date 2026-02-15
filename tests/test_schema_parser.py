"""Tests for the schema_parser module."""

from generator.schema_parser import (
    get_response_type,
    parse_parameters,
    resolve_schema_type,
)


# Minimal spec with components for $ref resolution
_SPEC: dict = {
    "components": {
        "schemas": {
            "SearchRequest": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "readOnly": True},
                    "searchText": {"type": "string"},
                    "token": {"type": "integer"},
                },
                "required": ["searchText"],
            },
            "SearchState": {
                "type": "string",
                "enum": ["InProgress", "Completed", "TimedOut"],
            },
            "QueueDownloadRequest": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "size": {"type": "integer"},
                },
            },
            "ComposedObject": {
                "allOf": [
                    {"$ref": "#/components/schemas/SearchRequest"},
                    {
                        "type": "object",
                        "properties": {
                            "extra": {"type": "boolean"},
                        },
                    },
                ],
            },
        }
    }
}


class TestResolveSchemaType:
    """Test OpenAPI schema → Python type conversion."""

    def test_string(self):
        assert resolve_schema_type(_SPEC, {"type": "string"}) == "str"

    def test_integer(self):
        assert resolve_schema_type(_SPEC, {"type": "integer"}) == "int"

    def test_number(self):
        assert resolve_schema_type(_SPEC, {"type": "number"}) == "float"

    def test_boolean(self):
        assert resolve_schema_type(_SPEC, {"type": "boolean"}) == "bool"

    def test_array_of_strings(self):
        assert resolve_schema_type(_SPEC, {"type": "array", "items": {"type": "string"}}) == "list[str]"

    def test_array_of_objects(self):
        assert resolve_schema_type(_SPEC, {"type": "array", "items": {"type": "object"}}) == "list[dict]"

    def test_array_of_refs(self):
        """$ref in array items must resolve to dict, not str."""
        schema = {"type": "array", "items": {"$ref": "#/components/schemas/SearchRequest"}}
        assert resolve_schema_type(_SPEC, schema) == "list[dict]"

    def test_object(self):
        assert resolve_schema_type(_SPEC, {"type": "object"}) == "dict"

    def test_ref(self):
        assert resolve_schema_type(_SPEC, {"$ref": "#/components/schemas/SearchRequest"}) == "dict"

    def test_enum(self):
        assert resolve_schema_type(_SPEC, {"type": "string", "enum": ["a", "b"]}) == "str"

    def test_enum_ref(self):
        assert resolve_schema_type(_SPEC, {"$ref": "#/components/schemas/SearchState"}) == "str"

    def test_allof(self):
        assert resolve_schema_type(_SPEC, {"$ref": "#/components/schemas/ComposedObject"}) == "dict"

    def test_empty_schema(self):
        assert resolve_schema_type(_SPEC, {}) == "Any"


class TestParseParameters:
    """Test parameter extraction from operations."""

    def test_path_params(self):
        op = {
            "_method": "get",
            "parameters": [
                {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}},
            ],
        }
        params = parse_parameters(_SPEC, op, "/api/v0/searches/{id}")
        assert len(params) == 1
        assert params[0]["name"] == "id"
        assert params[0]["location"] == "path"
        assert params[0]["required"] is True

    def test_query_params(self):
        op = {
            "_method": "get",
            "parameters": [
                {"name": "includeInactive", "in": "query", "schema": {"type": "boolean"}},
            ],
        }
        params = parse_parameters(_SPEC, op, "/api/v0/conversations")
        assert len(params) == 1
        assert params[0]["location"] == "query"
        assert params[0]["required"] is False

    def test_body_params_from_object(self):
        """Flattened object body params."""
        op = {
            "_method": "post",
            "requestBody": {
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/SearchRequest"},
                    }
                }
            },
        }
        params = parse_parameters(_SPEC, op, "/api/v0/searches")
        names = [p["name"] for p in params]
        # id is readOnly and should be excluded
        assert "id" not in names
        assert "searchText" in names
        assert "token" in names
        text_param = next(p for p in params if p["name"] == "searchText")
        assert text_param["location"] == "body"

    def test_body_array_creates_single_body_param(self):
        """Array request body → single 'body' param with list type."""
        op = {
            "_method": "post",
            "parameters": [
                {"name": "username", "in": "path", "required": True, "schema": {"type": "string"}},
            ],
            "requestBody": {
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/QueueDownloadRequest"},
                        },
                    }
                }
            },
        }
        params = parse_parameters(_SPEC, op, "/api/v0/transfers/downloads/{username}")
        body_params = [p for p in params if p["location"] == "body"]
        assert len(body_params) == 1
        assert body_params[0]["name"] == "body"
        assert body_params[0]["type"] == "list[dict]"
        assert body_params[0]["required"] is True

    def test_readonly_fields_excluded(self):
        """readOnly fields must not appear as parameters."""
        op = {
            "_method": "post",
            "requestBody": {
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/SearchRequest"},
                    }
                }
            },
        }
        params = parse_parameters(_SPEC, op, "/api/v0/searches")
        names = [p["name"] for p in params]
        assert "id" not in names

    def test_update_defaults_to_none(self):
        """PATCH/PUT body fields should default to None to avoid overwriting."""
        op = {
            "_method": "patch",
            "requestBody": {
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "default": "test"},
                                "count": {"type": "integer", "default": 5},
                            },
                        },
                    }
                }
            },
        }
        params = parse_parameters(_SPEC, op, "/api/v0/something")
        for p in params:
            assert p["default"] is None, f"{p['name']} should default to None for PATCH"
            assert p["required"] is False

    def test_enum_values_in_description(self):
        """Enum values should be included in parameter descriptions."""
        op = {
            "_method": "get",
            "parameters": [
                {
                    "name": "state",
                    "in": "query",
                    "schema": {"$ref": "#/components/schemas/SearchState"},
                },
            ],
        }
        params = parse_parameters(_SPEC, op, "/api/v0/searches")
        state_param = params[0]
        assert "InProgress" in state_param["description"]
        assert "Completed" in state_param["description"]
        assert "TimedOut" in state_param["description"]

    def test_large_integer_default_sanitized(self):
        """Integers >= 2^53 must be replaced with None."""
        op = {
            "_method": "get",
            "parameters": [
                {
                    "name": "bignum",
                    "in": "query",
                    "schema": {"type": "integer", "default": 2**53},
                },
            ],
        }
        params = parse_parameters(_SPEC, op, "/api/v0/something")
        assert params[0]["default"] is None


class TestGetResponseType:
    """Test response type detection."""

    def test_array_response(self):
        op = {
            "responses": {
                "200": {
                    "content": {
                        "application/json": {
                            "schema": {"type": "array", "items": {"type": "object"}},
                        }
                    }
                }
            }
        }
        assert get_response_type(_SPEC, op) == "array"

    def test_paging_response(self):
        op = {
            "responses": {
                "200": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "records": {"type": "array"},
                                    "totalRecords": {"type": "integer"},
                                    "page": {"type": "integer"},
                                },
                            },
                        }
                    }
                }
            }
        }
        assert get_response_type(_SPEC, op) == "paging"

    def test_object_response(self):
        op = {
            "responses": {
                "200": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/SearchRequest"},
                        }
                    }
                }
            }
        }
        assert get_response_type(_SPEC, op) == "object"

    def test_no_content(self):
        """Endpoints without response content return 'none'."""
        op = {"responses": {"200": {"description": "OK"}}}
        assert get_response_type(_SPEC, op) == "none"
