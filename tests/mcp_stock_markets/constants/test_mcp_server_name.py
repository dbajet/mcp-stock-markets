from __future__ import annotations

from mcp_stock_markets.constants.mcp_server_name import McpServerName


def test_enum() -> None:
    tested = McpServerName
    expected = {"SP500": "sp500", "QUOTES": "quotes", "BROKER": "broker"}
    assert {member.name: member.value for member in tested} == expected
