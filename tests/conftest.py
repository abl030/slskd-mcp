"""Shared fixtures for slskd MCP integration tests.

Session-scoped fixtures ensure the server module is imported once with
correct env vars pointing at the Docker test instance.
"""

from __future__ import annotations

import importlib
import os
import sys
from typing import Any, Callable, Coroutine

import httpx
import pytest


# ---------------------------------------------------------------------------
# Health check — skip entire session if Docker isn't running
# ---------------------------------------------------------------------------

SLSKD_TEST_URL = "http://localhost:15030"
SLSKD_TEST_API_KEY = "test-api-key"


@pytest.fixture(scope="session")
def slskd_available():
    """Skip integration tests if the Docker slskd instance is unreachable."""
    try:
        resp = httpx.get(f"{SLSKD_TEST_URL}/health", timeout=5)
        if resp.status_code != 200:
            pytest.skip(f"slskd health check returned {resp.status_code}")
    except httpx.RequestError:
        pytest.skip(f"slskd not reachable at {SLSKD_TEST_URL}")


# ---------------------------------------------------------------------------
# Environment setup — must happen before any import of generated.server
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def slskd_env(slskd_available):
    """Set environment variables required by the generated server module.

    The generated server reads SLSKD_URL / SLSKD_API_KEY at module-level
    (lines 23-26), so we must set these *before* import.
    """
    old = {
        "SLSKD_URL": os.environ.get("SLSKD_URL"),
        "SLSKD_API_KEY": os.environ.get("SLSKD_API_KEY"),
        "SLSKD_MODULES": os.environ.get("SLSKD_MODULES"),
        "SLSKD_READ_ONLY": os.environ.get("SLSKD_READ_ONLY"),
    }
    os.environ["SLSKD_URL"] = SLSKD_TEST_URL
    os.environ["SLSKD_API_KEY"] = SLSKD_TEST_API_KEY
    os.environ.pop("SLSKD_MODULES", None)  # all modules enabled
    os.environ.pop("SLSKD_READ_ONLY", None)  # mutations allowed
    yield
    # Restore original env
    for key, val in old.items():
        if val is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = val


# ---------------------------------------------------------------------------
# Server module — fresh import after env is configured
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def server(slskd_env):
    """Import generated.server with a fresh module cache.

    Returns the module object so tests can getattr() tool functions.
    """
    # Clear any cached import so env vars take effect
    sys.modules.pop("generated.server", None)
    sys.modules.pop("generated", None)
    mod = importlib.import_module("generated.server")
    return mod


# ---------------------------------------------------------------------------
# Tool accessor — convenience wrapper
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def tool(server) -> Callable[[str], Callable[..., Coroutine[Any, Any, Any]]]:
    """Return a callable that looks up a tool function by name.

    Usage in tests::

        result = await tool("slskd_list_server")()
    """
    def _get_tool(name: str):
        obj = getattr(server, name, None)
        if obj is None:
            pytest.fail(f"Tool {name!r} not found in generated.server")
        # @mcp.tool() wraps functions in FunctionTool; unwrap to get the
        # raw async callable.
        return getattr(obj, "fn", obj)
    return _get_tool


# ---------------------------------------------------------------------------
# Raw HTTP client — for cross-verification tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
async def raw_client():
    """Direct httpx.AsyncClient for comparing tool output against raw API."""
    async with httpx.AsyncClient(
        base_url=SLSKD_TEST_URL,
        headers={"X-Api-Key": SLSKD_TEST_API_KEY},
        timeout=30.0,
    ) as client:
        yield client
