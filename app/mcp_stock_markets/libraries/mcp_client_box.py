from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError
from mcp_types import CallToolResult, TextContent

from mcp_stock_markets.constants.agent_constants import AgentConstants
from mcp_stock_markets.constants.constants import Constants
from mcp_stock_markets.constants.mcp_constants import McpConstants
from mcp_stock_markets.constants.mcp_server_name import McpServerName
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.settings import Settings
from mcp_stock_markets.structures.tool_result import ToolResult
from mcp_stock_markets.structures.tool_spec import ToolSpec


class McpClientBox:
    """The agent's side of the Model Context Protocol: it lists an MCP
    server's tools and calls them, over Streamable HTTP, through the
    official SDK's `Client`.

    The servers are this very process, reached on its own port as any MCP
    client would reach them — the point of the demo is the protocol, so
    the agent takes no shortcut into the code behind it. Each request
    carries the bearer token the servers check (McpGuard) and, for the
    broker's orders, the run they belong to.

    The SDK is asynchronous; the app is not. Each call is one short
    `asyncio.run` on the calling thread — the agent's — and one MCP
    session, opened and closed around it: the servers are stateless, and a
    session per call costs a millisecond on the loopback."""

    _UNREACHABLE: tuple[type[BaseException], ...] = (httpx2.HTTPError, MCPError, OSError, ExceptionGroup)

    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.mcp_base_url
        self._token = settings.mcp_token

    def tools(self, server: McpServerName) -> list[ToolSpec]:
        try:
            return asyncio.run(self._listed(server))
        except self._UNREACHABLE as error:
            logging.getLogger(Constants.logger_name).warning(
                "[MCP] %s unreachable: %s", server.value, type(error).__name__
            )
            raise AppException(503, f"The MCP server {server.value} did not answer.") from None

    def called(
        self,
        server: McpServerName,
        tool: str,
        arguments: dict[str, Any],
        call_id: str,
        run_id: int,
    ) -> ToolResult:
        """The server's answer, an error included: a tool that fails tells the
        model why (`isError`), and so does a server that does not answer."""
        try:
            answer = asyncio.run(self._invoked(server, tool, arguments, run_id))
        except self._UNREACHABLE as error:
            logging.getLogger(Constants.logger_name).warning(
                "[MCP] %s.%s failed: %s", server.value, tool, type(error).__name__
            )
            return ToolResult(call_id=call_id, content=f"The MCP server {server.value} did not answer.", is_error=True)
        return ToolResult(call_id=call_id, content=self.text_of(answer), is_error=answer.is_error)

    def url(self, server: McpServerName) -> str:
        return f"{self._base_url}{McpConstants.mount_prefix}/{server.value}/"

    async def _listed(self, server: McpServerName) -> list[ToolSpec]:
        async with self._session(server, 0) as client:
            listing = await client.list_tools()
        return [
            ToolSpec(
                server=server, name=tool.name, description=tool.description or "", input_schema=dict(tool.input_schema)
            )
            for tool in listing.tools
        ]

    async def _invoked(
        self, server: McpServerName, tool: str, arguments: dict[str, Any], run_id: int
    ) -> CallToolResult:
        async with self._session(server, run_id) as client:
            return await client.call_tool(tool, arguments, read_timeout_seconds=McpConstants.call_timeout_seconds)

    @asynccontextmanager
    async def _session(self, server: McpServerName, run_id: int) -> AsyncIterator[Client]:
        """One MCP session over its own HTTP client; the transport does not
        close a client it was handed, so the session's end closes both."""
        async with self._http_client(run_id) as http_client:
            async with Client(streamable_http_client(self.url(server), http_client=http_client)) as client:
                yield client

    def _http_client(self, run_id: int) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(
            headers={
                McpConstants.authorization_header: f"{McpConstants.bearer_prefix}{self._token}",
                McpConstants.run_header: str(run_id),
            },
            timeout=McpConstants.call_timeout_seconds,
        )

    @classmethod
    def text_of(cls, answer: CallToolResult) -> str:
        """What the model reads: the structured result as JSON when the tool
        gave one, its text otherwise, cut to a length a context can hold."""
        if answer.structured_content is not None:
            result = json.dumps(answer.structured_content, ensure_ascii=False)
        else:
            result = "\n".join(
                block.text if isinstance(block, TextContent) else f"[{block.type} content]" for block in answer.content
            )
        return result[: AgentConstants.max_tool_result_chars]
