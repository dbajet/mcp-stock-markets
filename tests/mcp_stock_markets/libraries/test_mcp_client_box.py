from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any
from unittest.mock import call, patch

import httpx2
import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import CallToolResult, ImageContent, TextContent
from starlette.applications import Starlette
from starlette.routing import Mount

from mcp_stock_markets.constants.mcp_server_name import McpServerName
from mcp_stock_markets.handlers.mcp_guard import McpGuard
from mcp_stock_markets.libraries.mcp_client_box import McpClientBox
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.settings import Settings
from mcp_stock_markets.structures.tool_result import ToolResult
from mcp_stock_markets.structures.tool_spec import ToolSpec

BASE_URL = "http://127.0.0.1:8000"
TOKEN = "mcp-token"


def helper_settings() -> Settings:
    return Settings(
        environment="dev",
        database_url="postgresql://u:p@h/d",
        app_version="v",
        build_time="b",
        app_commit="c",
        app_base_url="https://stocks.example.com",
        data_key="Zm9yLXRlc3RzLW9ubHktZm9yLXRlc3RzLW9ubHktMzI=",
        smtp_host="",
        smtp_port=587,
        smtp_user="",
        smtp_password="",
        email_from="",
        bootstrap_admin_email="",
        starting_budget=Decimal("500.00"),
        max_companies=5,
        alpha_vantage_key="",
        agent_interval_minutes=30,
        mcp_base_url=BASE_URL,
        mcp_token=TOKEN,
    )


def helper_server() -> MCPServer[Any]:
    """A real MCP server, built per test: its session manager runs only once."""
    result: MCPServer[Any] = MCPServer(name="quotes", log_level="WARNING")

    def get_quote(symbol: str) -> dict[str, Any]:
        """The latest price of a stock."""
        return {"symbol": symbol, "price": "512.2500"}

    def refuse() -> dict[str, Any]:
        """Always refused."""
        raise ToolError("The market is closed.")

    def say(text: str) -> str:
        """Says the text back."""
        return text

    def picture() -> ImageContent:
        """A picture."""
        return ImageContent(type="image", data="AAAA", mime_type="image/png")

    def long_text() -> str:
        """More than a context holds."""
        return "x" * 13_000

    result.add_tool(get_quote)
    result.add_tool(refuse)
    result.add_tool(say, structured_output=False)
    result.add_tool(picture, structured_output=False)
    result.add_tool(long_text, structured_output=False)
    return result


@asynccontextmanager
async def helper_connected(server: MCPServer[Any], token: str) -> AsyncIterator[httpx2.AsyncClient]:
    """The HTTP client the box would open, reaching the server in process: the
    server mounted as the app mounts it, behind its guard, with its session
    manager running on the box's own loop. No socket."""
    guarded = McpGuard(
        server.streamable_http_app(streamable_http_path="/", json_response=True, stateless_http=True), token
    )
    app = Starlette(routes=[Mount("/mcp/quotes", app=guarded)])
    async with server.session_manager.run():
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url=BASE_URL,
            headers={"authorization": f"Bearer {TOKEN}", "x-agent-run": "3"},
        ) as client:
            yield client


@asynccontextmanager
async def helper_unreachable() -> AsyncIterator[httpx2.AsyncClient]:
    """A server that refuses the connection, as a stopped process does."""

    def refused(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("All connection attempts failed", request=request)

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(refused)) as client:
        yield client


def helper_called(tool: str, arguments: dict[str, Any]) -> tuple[ToolResult, list[Any]]:
    tested = McpClientBox(helper_settings())
    server = helper_server()
    with patch.object(
        McpClientBox, "_http_client", side_effect=lambda run_id: helper_connected(server, TOKEN)
    ) as mock_http_client:
        result = tested.called(McpServerName.QUOTES, tool, arguments, "call-1", 3)
    return result, mock_http_client.mock_calls


def test___init__() -> None:
    tested = McpClientBox(helper_settings())
    result = (tested._base_url, tested._token)
    expected = (BASE_URL, TOKEN)
    assert result == expected


def test_tools() -> None:
    tested = McpClientBox(helper_settings())
    server = helper_server()
    with patch.object(
        McpClientBox, "_http_client", side_effect=lambda run_id: helper_connected(server, TOKEN)
    ) as mock_http_client:
        result = tested.tools(McpServerName.QUOTES)
    quotes = McpServerName.QUOTES
    expected = [
        ToolSpec(
            server=quotes,
            name="get_quote",
            description="The latest price of a stock.",
            input_schema={
                "type": "object",
                "properties": {"symbol": {"title": "Symbol", "type": "string"}},
                "required": ["symbol"],
                "title": "get_quoteArguments",
            },
        ),
        ToolSpec(
            server=quotes,
            name="refuse",
            description="Always refused.",
            input_schema={"type": "object", "properties": {}, "title": "refuseArguments"},
        ),
        ToolSpec(
            server=quotes,
            name="say",
            description="Says the text back.",
            input_schema={
                "type": "object",
                "properties": {"text": {"title": "Text", "type": "string"}},
                "required": ["text"],
                "title": "sayArguments",
            },
        ),
        ToolSpec(
            server=quotes,
            name="picture",
            description="A picture.",
            input_schema={"type": "object", "properties": {}, "title": "pictureArguments"},
        ),
        ToolSpec(
            server=quotes,
            name="long_text",
            description="More than a context holds.",
            input_schema={"type": "object", "properties": {}, "title": "long_textArguments"},
        ),
    ]
    assert result == expected
    exp_calls = [call(0)]
    assert mock_http_client.mock_calls == exp_calls


@pytest.mark.parametrize(
    "connected",
    [
        pytest.param(lambda: helper_unreachable(), id="connection_refused"),
        pytest.param(lambda: helper_connected(helper_server(), "other-token"), id="token_refused"),
    ],
)
def test_tools__server_that_does_not_answer(connected: Any) -> None:
    tested = McpClientBox(helper_settings())
    with (
        patch.object(McpClientBox, "_http_client", side_effect=lambda run_id: connected()) as mock_http_client,
        pytest.raises(AppException) as exc_info,
    ):
        tested.tools(McpServerName.QUOTES)
    result = (exc_info.value.status_code, exc_info.value.message, exc_info.value.__cause__)
    expected = (503, "The MCP server quotes did not answer.", None)
    assert result == expected
    exp_calls = [call(0)]
    assert mock_http_client.mock_calls == exp_calls


def test_called() -> None:
    """A structured answer reaches the model as its JSON."""
    result = helper_called("get_quote", {"symbol": "MSFT"})
    expected = (
        ToolResult(call_id="call-1", content='{"symbol": "MSFT", "price": "512.2500"}', is_error=False),
        [call(3)],
    )
    assert result == expected


def test_called__tool_error_tells_the_model_why() -> None:
    result = helper_called("refuse", {})
    expected = (
        ToolResult(call_id="call-1", content="Error executing tool refuse: The market is closed.", is_error=True),
        [call(3)],
    )
    assert result == expected


def test_called__unknown_tool() -> None:
    result = helper_called("missing", {})
    expected = (ToolResult(call_id="call-1", content="Unknown tool: missing", is_error=True), [call(3)])
    assert result == expected


def test_called__text_answer() -> None:
    result = helper_called("say", {"text": "Hello, model."})
    expected = (ToolResult(call_id="call-1", content="Hello, model.", is_error=False), [call(3)])
    assert result == expected


def test_called__non_text_answer_is_named() -> None:
    result = helper_called("picture", {})
    expected = (ToolResult(call_id="call-1", content="[image content]", is_error=False), [call(3)])
    assert result == expected


def test_called__long_answer_is_cut() -> None:
    result = helper_called("long_text", {})
    expected = (ToolResult(call_id="call-1", content="x" * 12_000, is_error=False), [call(3)])
    assert result == expected


def test_called__unreachable_server_is_an_error_result() -> None:
    tested = McpClientBox(helper_settings())
    with patch.object(
        McpClientBox, "_http_client", side_effect=lambda run_id: helper_unreachable()
    ) as mock_http_client:
        result = tested.called(McpServerName.BROKER, "buy", {"symbol": "MSFT"}, "call-1", 3)
    expected = ToolResult(call_id="call-1", content="The MCP server broker did not answer.", is_error=True)
    assert result == expected
    exp_calls = [call(3)]
    assert mock_http_client.mock_calls == exp_calls


@pytest.mark.parametrize(
    "server, expected",
    [
        pytest.param(McpServerName.SP500, "http://127.0.0.1:8000/mcp/sp500/", id="sp500"),
        pytest.param(McpServerName.QUOTES, "http://127.0.0.1:8000/mcp/quotes/", id="quotes"),
        pytest.param(McpServerName.BROKER, "http://127.0.0.1:8000/mcp/broker/", id="broker"),
    ],
)
def test_url(server: McpServerName, expected: str) -> None:
    tested = McpClientBox(helper_settings())
    result = tested.url(server)
    assert result == expected


def test__listed() -> None:
    tested = McpClientBox(helper_settings())
    server = helper_server()
    with patch.object(
        McpClientBox, "_http_client", side_effect=lambda run_id: helper_connected(server, TOKEN)
    ) as mock_http_client:
        listing = asyncio.run(tested._listed(McpServerName.QUOTES))
    result = [(tool.server, tool.name, tool.description) for tool in listing]
    expected = [
        (McpServerName.QUOTES, "get_quote", "The latest price of a stock."),
        (McpServerName.QUOTES, "refuse", "Always refused."),
        (McpServerName.QUOTES, "say", "Says the text back."),
        (McpServerName.QUOTES, "picture", "A picture."),
        (McpServerName.QUOTES, "long_text", "More than a context holds."),
    ]
    assert result == expected
    exp_calls = [call(0)]
    assert mock_http_client.mock_calls == exp_calls


def test__invoked() -> None:
    tested = McpClientBox(helper_settings())
    server = helper_server()
    with patch.object(
        McpClientBox, "_http_client", side_effect=lambda run_id: helper_connected(server, TOKEN)
    ) as mock_http_client:
        answer = asyncio.run(tested._invoked(McpServerName.QUOTES, "get_quote", {"symbol": "MSFT"}, 3))
    result = (type(answer), answer.structured_content, answer.is_error)
    expected = (CallToolResult, {"symbol": "MSFT", "price": "512.2500"}, False)
    assert result == expected
    exp_calls = [call(3)]
    assert mock_http_client.mock_calls == exp_calls


def test__session() -> None:
    tested = McpClientBox(helper_settings())
    server = helper_server()

    async def scenario() -> tuple[type, list[str]]:
        async with tested._session(McpServerName.QUOTES, 5) as client:
            listing = await client.list_tools()
        return type(client), [tool.name for tool in listing.tools]

    with patch.object(
        McpClientBox, "_http_client", side_effect=lambda run_id: helper_connected(server, TOKEN)
    ) as mock_http_client:
        result = asyncio.run(scenario())
    expected = (Client, ["get_quote", "refuse", "say", "picture", "long_text"])
    assert result == expected
    exp_calls = [call(5)]
    assert mock_http_client.mock_calls == exp_calls


def test__http_client() -> None:
    tested = McpClientBox(helper_settings())
    client = tested._http_client(7)
    try:
        result = (
            client.headers["authorization"],
            client.headers["x-agent-run"],
            client.timeout,
        )
    finally:
        asyncio.run(client.aclose())
    expected = ("Bearer mcp-token", "7", httpx2.Timeout(30.0))
    assert result == expected


@pytest.mark.parametrize(
    "answer, expected",
    [
        pytest.param(
            CallToolResult(
                content=[TextContent(type="text", text="ignored")],
                structured_content={"price": "512.2500", "name": "Société Générale"},
            ),
            '{"price": "512.2500", "name": "Société Générale"}',
            id="structured_first_unescaped",
        ),
        pytest.param(
            CallToolResult(content=[TextContent(type="text", text="one"), TextContent(type="text", text="two")]),
            "one\ntwo",
            id="text_blocks_joined",
        ),
        pytest.param(
            CallToolResult(
                content=[
                    TextContent(type="text", text="see"),
                    ImageContent(type="image", data="AAAA", mime_type="image/png"),
                ]
            ),
            "see\n[image content]",
            id="non_text_named",
        ),
        pytest.param(CallToolResult(content=[]), "", id="nothing"),
        pytest.param(
            CallToolResult(content=[TextContent(type="text", text="y" * 12_001)]), "y" * 12_000, id="text_cut"
        ),
        pytest.param(
            CallToolResult(content=[], structured_content={"text": "z" * 12_000}),
            '{"text": "' + "z" * 11_990,
            id="structured_cut",
        ),
    ],
)
def test_text_of(answer: CallToolResult, expected: str) -> None:
    tested = McpClientBox
    result = tested.text_of(answer)
    assert result == expected
