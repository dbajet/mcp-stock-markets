from __future__ import annotations

import dataclasses

from mcp_stock_markets.constants.mcp_constants import McpConstants
from tests.conftest import is_dataclass


def test_class() -> None:
    tested = McpConstants
    fields = {
        "mount_prefix": "str",
        "tool_separator": "str",
        "run_header": "str",
        "authorization_header": "str",
        "bearer_prefix": "str",
        "call_timeout_seconds": "float",
        "server_version": "str",
        "refused": "str",
    }
    assert is_dataclass(tested, fields)


def test_values() -> None:
    tested = McpConstants
    result = dataclasses.asdict(tested)
    expected = {
        "mount_prefix": "/mcp",
        "tool_separator": "__",
        "run_header": "x-agent-run",
        "authorization_header": "authorization",
        "bearer_prefix": "Bearer ",
        "call_timeout_seconds": 30.0,
        "server_version": "1.0",
        "refused": "This MCP server needs the app's bearer token.",
    }
    assert result == expected
