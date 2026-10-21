from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from starlette.types import ASGIApp

from mcp_stock_markets.constants.mcp_constants import McpConstants
from mcp_stock_markets.constants.mcp_server_name import McpServerName
from mcp_stock_markets.handlers.mcp_guard import McpGuard
from mcp_stock_markets.structures.app_exception import AppException


class McpServerHandler(ABC):
    """An MCP server of this app, built with the official SDK (`MCPServer`)
    and mounted inside FastAPI at /mcp/<name>/, as the routers are: it is
    one more way in to the same commands, for a model rather than a page.

    Its tools are methods; the SDK reads each one's signature for the JSON
    Schema of its arguments and its docstring for its description, so the
    docstrings here are written for the model. A sync tool runs on a worker
    thread, which suits the synchronous commands. Stateless and JSON-only:
    each request stands alone, so either color answers any of them."""

    def __init__(self, token: str) -> None:
        self._token = token
        self._server: MCPServer[Any] | None = None

    @property
    @abstractmethod
    def name(self) -> McpServerName: ...

    @property
    @abstractmethod
    def instructions(self) -> str: ...

    @abstractmethod
    def registered(self, server: MCPServer[Any]) -> None:
        """The server's tools, added with `server.add_tool`."""

    @property
    def server(self) -> MCPServer[Any]:
        """Built once: the session manager the app's lifespan runs belongs to it."""
        if self._server is None:
            self._server = MCPServer(
                name=self.name.value,
                instructions=self.instructions,
                version=McpConstants.server_version,
                log_level="WARNING",
            )
            self.registered(self._server)
        return self._server

    def app(self) -> ASGIApp:
        return McpGuard(
            self.server.streamable_http_app(streamable_http_path="/", json_response=True, stateless_http=True),
            self._token,
        )

    @classmethod
    def added(cls, server: MCPServer[Any], tool: Callable[..., dict[str, Any]], annotations: ToolAnnotations) -> None:
        """A tool whose description is its docstring as a person reads it: the
        SDK passes the raw docstring on, source indentation and all, and the
        model would read that indentation as part of the text."""
        server.add_tool(tool, description=inspect.getdoc(tool), annotations=annotations)

    @classmethod
    def answered(cls, work: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        """The command's answer, or its refusal as a tool error the model
        reads (`isError` with the message), never as a crash."""
        try:
            return work()
        except AppException as error:
            raise ToolError(error.message) from None
