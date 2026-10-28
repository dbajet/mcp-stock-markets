from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from mcp_stock_markets.commands.quote_command import QuoteCommand
from mcp_stock_markets.constants.mcp_server_name import McpServerName
from mcp_stock_markets.constants.quote_source import QuoteSource
from mcp_stock_markets.handlers.mcp_server_handler import McpServerHandler
from mcp_stock_markets.handlers.quotes_mcp_server import QuotesMcpServer
from mcp_stock_markets.libraries.alpaca_box import AlpacaBox
from mcp_stock_markets.libraries.company_store import CompanyStore
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.libraries.google_finance_box import GoogleFinanceBox
from mcp_stock_markets.libraries.market_clock import MarketClock
from mcp_stock_markets.libraries.quote_store import QuoteStore
from mcp_stock_markets.libraries.web_box import WebBox
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.daily_bar import DailyBar
from mcp_stock_markets.structures.market_status import MarketStatus
from mcp_stock_markets.structures.quote import Quote

NOW = datetime(2026, 10, 21, 14, 30, 0, tzinfo=UTC)
MODULE = "mcp_stock_markets.handlers.quotes_mcp_server.datetime"


def helper_quotes() -> QuoteCommand:
    database = Database("postgresql://u:p@h/d")
    web = WebBox()
    return QuoteCommand(
        QuoteStore(database), CompanyStore(database), GoogleFinanceBox(web), AlpacaBox(web, "", ""), MarketClock()
    )


def helper_quote() -> Quote:
    return Quote(
        symbol="AAPL",
        price=Decimal("231.5000"),
        currency="USD",
        as_of=datetime(2026, 10, 21, 14, 27, 30, 400000, tzinfo=UTC),
        source=QuoteSource.GOOGLE_FINANCE,
        fetched_at=datetime(2026, 10, 21, 14, 29, 0, tzinfo=UTC),
    )


def helper_quote_dict(age_seconds: int) -> dict[str, Any]:
    return {
        "symbol": "AAPL",
        "price": "231.5000",
        "currency": "USD",
        "as_of": "2026-10-21T14:27:30.400000+00:00",
        "source": "google_finance",
        "fetched_at": "2026-10-21T14:29:00+00:00",
        "age_seconds": age_seconds,
    }


def helper_bar(day: date, close: str) -> DailyBar:
    return DailyBar(
        symbol="AAPL",
        day=day,
        open=Decimal("230.0000"),
        high=Decimal("233.0000"),
        low=Decimal("229.0000"),
        close=Decimal(close),
        volume=51_000_000,
    )


def helper_bar_dict(day: str, close: str) -> dict[str, Any]:
    return {
        "symbol": "AAPL",
        "day": day,
        "open": "230.0000",
        "high": "233.0000",
        "low": "229.0000",
        "close": close,
        "volume": 51_000_000,
    }


def test_inheritance() -> None:
    tested = QuotesMcpServer
    result = issubclass(tested, McpServerHandler)
    assert result is True


def test___init__() -> None:
    quotes = helper_quotes()
    tested = QuotesMcpServer("tok-1", quotes)
    result = (tested._token, tested._quotes, tested._server)
    expected = ("tok-1", quotes, None)
    assert result == expected


def test_name() -> None:
    tested = QuotesMcpServer("tok-1", helper_quotes())
    result = tested.name
    expected = McpServerName.QUOTES
    assert result == expected


def test_instructions() -> None:
    tested = QuotesMcpServer("tok-1", helper_quotes())
    result = tested.instructions
    expected = "US stock prices: whether the market is open, the latest price of a stock, and its daily history."
    assert result == expected


def test_registered() -> None:
    """The listing the model reads: names, descriptions (the docstrings), schemas, hints."""
    tested = QuotesMcpServer("tok-1", helper_quotes())
    server: MCPServer[None] = MCPServer(name="probe")
    tested.registered(server)
    result = [tool.model_dump(exclude_none=True) for tool in asyncio.run(server.list_tools())]
    reading = {"read_only_hint": True, "open_world_hint": True}
    expected = [
        {
            "name": "get_market_status",
            "description": (
                "Whether the US stock market is open now (New York time), when today's\n"
                "session closes if it is, and when the next one opens."
            ),
            "input_schema": {"properties": {}, "title": "get_market_statusArguments", "type": "object"},
            "output_schema": {"additionalProperties": True, "title": "get_market_statusDictOutput", "type": "object"},
            "annotations": reading,
        },
        {
            "name": "get_quote",
            "description": (
                "The latest price of a stock in US dollars, the time of the trade it\n"
                "comes from (as_of), its age in seconds, and its source."
            ),
            "input_schema": {
                "properties": {"symbol": {"title": "Symbol", "type": "string"}},
                "required": ["symbol"],
                "title": "get_quoteArguments",
                "type": "object",
            },
            "output_schema": {"additionalProperties": True, "title": "get_quoteDictOutput", "type": "object"},
            "annotations": reading,
        },
        {
            "name": "get_daily_history",
            "description": (
                "A stock's last trading days, oldest first: open, high, low, close and\nvolume of each (1 to 100 days)."
            ),
            "input_schema": {
                "properties": {
                    "symbol": {"title": "Symbol", "type": "string"},
                    "days": {"default": 20, "title": "Days", "type": "integer"},
                },
                "required": ["symbol"],
                "title": "get_daily_historyArguments",
                "type": "object",
            },
            "output_schema": {"additionalProperties": True, "title": "get_daily_historyDictOutput", "type": "object"},
            "annotations": reading,
        },
    ]
    assert result == expected


@patch(MODULE, wraps=datetime)
def test_get_market_status(mock_datetime: MagicMock) -> None:
    mock_datetime.now.side_effect = [NOW]
    tested = QuotesMcpServer("tok-1", helper_quotes())
    status = MarketStatus(
        is_open=True,
        now=datetime(2026, 10, 21, 10, 30, tzinfo=UTC),
        closes_at=datetime(2026, 10, 21, 20, 0, tzinfo=UTC),
        next_open=datetime(2026, 10, 22, 13, 30, tzinfo=UTC),
    )
    with patch.object(QuoteCommand, "market", side_effect=[status]) as mock_market:
        result = tested.get_market_status()
    expected = {
        "is_open": True,
        "now": "2026-10-21T10:30:00+00:00",
        "closes_at": "2026-10-21T20:00:00+00:00",
        "next_open": "2026-10-22T13:30:00+00:00",
    }
    assert result == expected
    exp_calls = [call(NOW)]
    assert mock_market.mock_calls == exp_calls
    exp_calls = [call.now(UTC)]
    assert mock_datetime.mock_calls == exp_calls


@patch(MODULE, wraps=datetime)
def test_get_quote(mock_datetime: MagicMock) -> None:
    mock_datetime.now.side_effect = [NOW]
    tested = QuotesMcpServer("tok-1", helper_quotes())
    with patch.object(QuotesMcpServer, "quoted", side_effect=[helper_quote_dict(150)]) as mock_quoted:
        result = tested.get_quote("aapl")
    expected = helper_quote_dict(150)
    assert result == expected
    exp_calls = [call("aapl", NOW)]
    assert mock_quoted.mock_calls == exp_calls
    exp_calls = [call.now(UTC)]
    assert mock_datetime.mock_calls == exp_calls


@patch(MODULE, wraps=datetime)
def test_get_quote__no_price_is_a_tool_error(mock_datetime: MagicMock) -> None:
    mock_datetime.now.side_effect = [NOW]
    tested = QuotesMcpServer("tok-1", helper_quotes())
    error = AppException(502, "No price could be fetched for AAPL right now.")
    with (
        patch.object(QuoteCommand, "quote", side_effect=[error]) as mock_quote,
        pytest.raises(ToolError) as exc_info,
    ):
        tested.get_quote("aapl")
    result = str(exc_info.value)
    expected = "No price could be fetched for AAPL right now."
    assert result == expected
    exp_calls = [call("aapl", NOW)]
    assert mock_quote.mock_calls == exp_calls
    exp_calls = [call.now(UTC)]
    assert mock_datetime.mock_calls == exp_calls


def test_quoted() -> None:
    """The age is rounded to whole seconds: 149.6 is 150."""
    tested = QuotesMcpServer("tok-1", helper_quotes())
    with patch.object(QuoteCommand, "quote", side_effect=[helper_quote()]) as mock_quote:
        result = tested.quoted("aapl", NOW)
    expected = helper_quote_dict(150)
    assert result == expected
    exp_calls = [call("aapl", NOW)]
    assert mock_quote.mock_calls == exp_calls


@patch(MODULE, wraps=datetime)
def test_get_daily_history(mock_datetime: MagicMock) -> None:
    mock_datetime.now.side_effect = [NOW]
    tested = QuotesMcpServer("tok-1", helper_quotes())
    bars = [helper_bar(date(2026, 10, 19), "231.0000"), helper_bar(date(2026, 10, 20), "232.0000")]
    with patch.object(QuoteCommand, "history", side_effect=[bars]) as mock_history:
        result = tested.get_daily_history(" aapl ", 2)
    expected = {
        "symbol": "AAPL",
        "bars": [helper_bar_dict("2026-10-19", "231.0000"), helper_bar_dict("2026-10-20", "232.0000")],
    }
    assert result == expected
    exp_calls = [call(" aapl ", 2, NOW)]
    assert mock_history.mock_calls == exp_calls
    exp_calls = [call.now(UTC)]
    assert mock_datetime.mock_calls == exp_calls
