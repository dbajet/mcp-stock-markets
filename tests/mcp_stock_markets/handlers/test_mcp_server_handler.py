from __future__ import annotations

import asyncio
from abc import ABC
from typing import Any

import pytest
from fastapi.testclient import TestClient
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations

from mcp_stock_markets.constants.mcp_server_name import McpServerName
from mcp_stock_markets.handlers.mcp_guard import McpGuard
from mcp_stock_markets.handlers.mcp_server_handler import McpServerHandler
from mcp_stock_markets.structures.app_exception import AppException


class _ProbeServer(McpServerHandler):
    """The smallest concrete server: the base class is what is tested."""

    @property
    def name(self) -> McpServerName:
        return McpServerName.QUOTES

    @property
    def instructions(self) -> str:
        return "A probe."

    def registered(self, server: MCPServer[Any]) -> None:
        server.add_tool(self.echo)

    def echo(self, text: str) -> dict[str, Any]:
        """Says the text back."""
        return {"text": text}


def helper_indented() -> dict[str, Any]:
    """First line,
    second line."""
    return {}


def helper_rpc(method: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": 1, "method": method}


def test_inheritance() -> None:
    tested = McpServerHandler
    result = (issubclass(tested, ABC), tested.__abstractmethods__)
    expected = (True, frozenset({"name", "instructions", "registered"}))
    assert result == expected


def test___init__() -> None:
    tested = _ProbeServer("tok-1")
    result = (tested._token, tested._server)
    expected = ("tok-1", None)
    assert result == expected


def test_server() -> None:
    tested = _ProbeServer("tok-1")
    server = tested.server
    result = (
        type(server),
        server.name,
        server.instructions,
        server.version,
        server.settings.log_level,
        [tool.name for tool in asyncio.run(server.list_tools())],
    )
    expected = (MCPServer, "quotes", "A probe.", "1.0", "WARNING", ["echo"])
    assert result == expected
    assert tested._server is server


def test_server__built_once() -> None:
    """The session manager the lifespan runs must be the one the mounted app uses."""
    tested = _ProbeServer("tok-1")
    first = tested.server
    result = tested.server
    assert result is first


def test_app() -> None:
    tested = _ProbeServer("tok-1")
    app = tested.app()
    headers = {"authorization": "Bearer tok-1", "accept": "application/json, text/event-stream"}
    # The lifespan on: it runs the server's session manager, as the app's does.
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        response = client.post("/", json=helper_rpc("tools/list"), headers=headers)
    result = (type(app), app._expected, response.status_code, response.headers["content-type"], response.json())
    expected = (
        McpGuard,
        b"Bearer tok-1",
        200,
        "application/json",
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "tools": [
                    {
                        "name": "echo",
                        "description": "Says the text back.",
                        "inputSchema": {
                            "properties": {"text": {"title": "Text", "type": "string"}},
                            "required": ["text"],
                            "title": "echoArguments",
                            "type": "object",
                        },
                        "outputSchema": {"additionalProperties": True, "title": "echoDictOutput", "type": "object"},
                    }
                ]
            },
        },
    )
    assert result == expected


def test_app__without_the_token() -> None:
    tested = _ProbeServer("tok-1")
    with TestClient(tested.app(), base_url="http://127.0.0.1:8000") as client:
        response = client.post("/", json=helper_rpc("tools/list"), headers={"authorization": "Bearer other"})
    result = (response.status_code, response.json())
    expected = (401, {"detail": "This MCP server needs the app's bearer token."})
    assert result == expected


def test_added() -> None:
    """The description is the docstring dedented, as the model should read it."""
    tested = _ProbeServer
    server: MCPServer[None] = MCPServer(name="probe")
    tested.added(server, helper_indented, ToolAnnotations(read_only_hint=True))
    result = [tool.model_dump(exclude_none=True) for tool in asyncio.run(server.list_tools())]
    expected = [
        {
            "name": "helper_indented",
            "description": "First line,\nsecond line.",
            "input_schema": {"properties": {}, "title": "helper_indentedArguments", "type": "object"},
            "output_schema": {"additionalProperties": True, "title": "helper_indentedDictOutput", "type": "object"},
            "annotations": {"read_only_hint": True},
        }
    ]
    assert result == expected


def test_answered() -> None:
    tested = _ProbeServer
    result = tested.answered(lambda: {"ok": True})
    expected = {"ok": True}
    assert result == expected


def test_answered__app_exception_becomes_a_tool_error() -> None:
    tested = _ProbeServer

    def refused() -> dict[str, Any]:
        raise AppException(409, "The market is closed.")

    with pytest.raises(ToolError) as exc_info:
        tested.answered(refused)
    result = (str(exc_info.value), exc_info.value.__cause__, exc_info.value.__suppress_context__)
    expected = ("The market is closed.", None, True)
    assert result == expected
