from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from mcp_stock_markets.commands.broker_command import BrokerCommand
from mcp_stock_markets.commands.company_command import CompanyCommand
from mcp_stock_markets.commands.quote_command import QuoteCommand
from mcp_stock_markets.constants.mcp_server_name import McpServerName
from mcp_stock_markets.constants.quote_source import QuoteSource
from mcp_stock_markets.constants.trade_side import TradeSide
from mcp_stock_markets.handlers.broker_mcp_server import BrokerMcpServer
from mcp_stock_markets.handlers.mcp_server_handler import McpServerHandler
from mcp_stock_markets.libraries.alpha_vantage_box import AlphaVantageBox
from mcp_stock_markets.libraries.company_store import CompanyStore
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.libraries.google_finance_box import GoogleFinanceBox
from mcp_stock_markets.libraries.market_clock import MarketClock
from mcp_stock_markets.libraries.portfolio_store import PortfolioStore
from mcp_stock_markets.libraries.quote_store import QuoteStore
from mcp_stock_markets.libraries.web_box import WebBox
from mcp_stock_markets.libraries.wikipedia_box import WikipediaBox
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.company import Company
from mcp_stock_markets.structures.portfolio import Portfolio
from mcp_stock_markets.structures.portfolio_view import PortfolioView
from mcp_stock_markets.structures.settings import Settings
from mcp_stock_markets.structures.trade import Trade

NOW = datetime(2026, 10, 21, 14, 30, 0, tzinfo=UTC)
MODULE = "mcp_stock_markets.handlers.broker_mcp_server.datetime"


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
        mcp_base_url="http://127.0.0.1:8000",
        mcp_token="mcp-token",
    )


def helper_parts() -> tuple[BrokerCommand, CompanyCommand]:
    settings = helper_settings()
    database = Database(settings.database_url)
    web = WebBox()
    company_store = CompanyStore(database)
    quotes = QuoteCommand(
        QuoteStore(database), company_store, GoogleFinanceBox(web), AlphaVantageBox(web, ""), MarketClock()
    )
    broker = BrokerCommand(settings, database, PortfolioStore(database), company_store, quotes)
    return broker, CompanyCommand(settings, company_store, WikipediaBox(WebBox()))


def helper_tested() -> BrokerMcpServer:
    return BrokerMcpServer("tok-1", *helper_parts())


def helper_portfolio() -> Portfolio:
    return Portfolio(
        portfolio_id=1,
        user_id=7,
        starting_budget=Decimal("500.00"),
        cash=Decimal("268.50"),
        created_at=datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
    )


def helper_trade(side: TradeSide, run_id: int | None) -> Trade:
    return Trade(
        trade_id=4,
        executed_at=NOW,
        symbol="AAPL",
        side=side,
        quantity=1,
        price=Decimal("231.5000"),
        amount=Decimal("231.50"),
        cash_after=Decimal("268.50"),
        quote_source=QuoteSource.GOOGLE_FINANCE,
        quote_as_of=datetime(2026, 10, 21, 14, 28, 0, tzinfo=UTC),
        agent_run_id=run_id,
        reason="Strong quarter.",
    )


def helper_trade_dict(side: str, run_id: int | None) -> dict[str, Any]:
    return {
        "trade_id": 4,
        "executed_at": "2026-10-21T14:30:00+00:00",
        "symbol": "AAPL",
        "side": side,
        "quantity": 1,
        "price": "231.5000",
        "amount": "231.50",
        "cash_after": "268.50",
        "quote_source": "google_finance",
        "quote_as_of": "2026-10-21T14:28:00+00:00",
        "agent_run_id": run_id,
        "reason": "Strong quarter.",
    }


def helper_ctx(headers: dict[str, str] | None) -> SimpleNamespace:
    return SimpleNamespace(headers=headers)


def test_inheritance() -> None:
    tested = BrokerMcpServer
    result = issubclass(tested, McpServerHandler)
    assert result is True


def test___init__() -> None:
    broker, companies = helper_parts()
    tested = BrokerMcpServer("tok-1", broker, companies)
    result = (tested._token, tested._broker, tested._companies, tested._server)
    expected = ("tok-1", broker, companies, None)
    assert result == expected


def test_name() -> None:
    tested = helper_tested()
    result = tested.name
    expected = McpServerName.BROKER
    assert result == expected


def test_instructions() -> None:
    tested = helper_tested()
    result = tested.instructions
    expected = (
        "A virtual brokerage account: its cash, its positions, its transactions, and buy and sell orders "
        "at the latest price, in whole shares, while the US market is open. Cash never goes below zero."
    )
    assert result == expected


def test_registered() -> None:
    """The listing the model reads: names, descriptions (the docstrings), schemas,
    hints; the context argument of an order is the SDK's, not the model's."""
    tested = helper_tested()
    server: MCPServer[None] = MCPServer(name="probe")
    tested.registered(server)
    result = [tool.model_dump(exclude_none=True) for tool in asyncio.run(server.list_tools())]
    reading = {"read_only_hint": True, "open_world_hint": False}
    ordering = {"read_only_hint": False, "destructive_hint": False, "idempotent_hint": False}
    order_schema = {
        "properties": {
            "symbol": {"title": "Symbol", "type": "string"},
            "quantity": {"title": "Quantity", "type": "integer"},
            "reason": {"title": "Reason", "type": "string"},
        },
        "required": ["symbol", "quantity", "reason"],
        "type": "object",
    }
    expected = [
        {
            "name": "get_portfolio",
            "description": (
                "The account: its starting budget, its cash, each position (shares,\n"
                "what they cost, their value at the latest price), the total value, and\n"
                "the market — the only companies that may be bought."
            ),
            "input_schema": {"properties": {}, "title": "get_portfolioArguments", "type": "object"},
            "output_schema": {"additionalProperties": True, "title": "get_portfolioDictOutput", "type": "object"},
            "annotations": reading,
        },
        {
            "name": "get_transactions",
            "description": (
                "The account's latest transactions, newest first: time, symbol, buy or\n"
                "sell, shares, price, amount, cash after, and the reason given."
            ),
            "input_schema": {
                "properties": {"limit": {"default": 50, "title": "Limit", "type": "integer"}},
                "title": "get_transactionsArguments",
                "type": "object",
            },
            "output_schema": {"additionalProperties": True, "title": "get_transactionsDictOutput", "type": "object"},
            "annotations": reading,
        },
        {
            "name": "buy",
            "description": (
                "Buy whole shares of a company of the market at its latest price. Refused\n"
                "when the market is closed, the company is not in the market, the price is\n"
                "stale, or the cash does not cover it. Give a short reason."
            ),
            "input_schema": order_schema | {"title": "buyArguments"},
            "output_schema": {"additionalProperties": True, "title": "buyDictOutput", "type": "object"},
            "annotations": ordering,
        },
        {
            "name": "sell",
            "description": (
                "Sell whole shares the account holds at their latest price. Refused when\n"
                "the market is closed, the account holds fewer shares, or the price is\n"
                "stale. Give a short reason."
            ),
            "input_schema": order_schema | {"title": "sellArguments"},
            "output_schema": {"additionalProperties": True, "title": "sellDictOutput", "type": "object"},
            "annotations": ordering,
        },
    ]
    assert result == expected


def test_get_portfolio() -> None:
    tested = helper_tested()
    with patch.object(BrokerMcpServer, "portfolio", side_effect=[{"total_value": "500.00"}]) as mock_portfolio:
        result = tested.get_portfolio()
    expected = {"total_value": "500.00"}
    assert result == expected
    exp_calls = [call()]
    assert mock_portfolio.mock_calls == exp_calls


def test_get_portfolio__no_portfolio_is_a_tool_error() -> None:
    tested = helper_tested()
    error = AppException(503, "There is no portfolio: set BOOTSTRAP_ADMIN_EMAIL and restart.")
    with (
        patch.object(BrokerCommand, "owner_portfolio", side_effect=[error]) as mock_owner,
        pytest.raises(ToolError) as exc_info,
    ):
        tested.get_portfolio()
    result = str(exc_info.value)
    expected = "There is no portfolio: set BOOTSTRAP_ADMIN_EMAIL and restart."
    assert result == expected
    exp_calls = [call()]
    assert mock_owner.mock_calls == exp_calls


@patch(MODULE, wraps=datetime)
def test_portfolio(mock_datetime: MagicMock) -> None:
    mock_datetime.now.side_effect = [NOW]
    tested = helper_tested()
    view = PortfolioView(
        portfolio=helper_portfolio(),
        positions=(),
        holdings_value=Decimal("0.00"),
        total_value=Decimal("268.50"),
        universe=("AAPL",),
    )
    company = Company("AAPL", "Apple Inc.", "Information Technology", "Hardware", "Cupertino", "NASDAQ")
    with (
        patch.object(BrokerCommand, "owner_portfolio", side_effect=[helper_portfolio()]) as mock_owner,
        patch.object(BrokerCommand, "view", side_effect=[view]) as mock_view,
        patch.object(CompanyCommand, "universe", side_effect=[[company]]) as mock_universe,
    ):
        result = tested.portfolio()
    expected = {
        "portfolio": {
            "portfolio_id": 1,
            "user_id": 7,
            "starting_budget": "500.00",
            "cash": "268.50",
            "created_at": "2026-10-01T12:00:00+00:00",
        },
        "positions": [],
        "holdings_value": "0.00",
        "total_value": "268.50",
        "universe": ["AAPL"],
        "market": [
            {
                "symbol": "AAPL",
                "name": "Apple Inc.",
                "sector": "Information Technology",
                "sub_industry": "Hardware",
                "headquarters": "Cupertino",
                "exchange": "NASDAQ",
            }
        ],
    }
    assert result == expected
    exp_calls = [call()]
    assert mock_owner.mock_calls == exp_calls
    assert mock_universe.mock_calls == exp_calls
    exp_calls = [call(helper_portfolio(), NOW)]
    assert mock_view.mock_calls == exp_calls
    exp_calls = [call.now(UTC)]
    assert mock_datetime.mock_calls == exp_calls


def test_get_transactions() -> None:
    tested = helper_tested()
    with (
        patch.object(BrokerCommand, "owner_portfolio", side_effect=[helper_portfolio()]) as mock_owner,
        patch.object(BrokerCommand, "trades", side_effect=[[helper_trade(TradeSide.BUY, 3)]]) as mock_trades,
    ):
        result = tested.get_transactions(10)
    expected = {"transactions": [helper_trade_dict("buy", 3)]}
    assert result == expected
    exp_calls = [call()]
    assert mock_owner.mock_calls == exp_calls
    exp_calls = [call(helper_portfolio(), 10)]
    assert mock_trades.mock_calls == exp_calls


@patch(MODULE, wraps=datetime)
def test_buy(mock_datetime: MagicMock) -> None:
    mock_datetime.now.side_effect = [NOW]
    tested = helper_tested()
    ctx = helper_ctx({"x-agent-run": "3"})
    with patch.object(BrokerCommand, "bought", side_effect=[helper_trade(TradeSide.BUY, 3)]) as mock_bought:
        result = tested.buy("aapl", 1, "Strong quarter.", ctx)  # type: ignore[arg-type]
    expected = helper_trade_dict("buy", 3)
    assert result == expected
    exp_calls = [call("aapl", 1, "Strong quarter.", 3, NOW)]
    assert mock_bought.mock_calls == exp_calls
    exp_calls = [call.now(UTC)]
    assert mock_datetime.mock_calls == exp_calls


@patch(MODULE, wraps=datetime)
def test_buy__refusal_is_a_tool_error(mock_datetime: MagicMock) -> None:
    mock_datetime.now.side_effect = [NOW]
    tested = helper_tested()
    ctx = helper_ctx({"x-agent-run": "3"})
    with (
        patch.object(BrokerCommand, "bought", side_effect=[AppException(409, "The market is closed.")]) as mock_bought,
        pytest.raises(ToolError) as exc_info,
    ):
        tested.buy("aapl", 1, "Strong quarter.", ctx)  # type: ignore[arg-type]
    result = str(exc_info.value)
    expected = "The market is closed."
    assert result == expected
    exp_calls = [call("aapl", 1, "Strong quarter.", 3, NOW)]
    assert mock_bought.mock_calls == exp_calls
    exp_calls = [call.now(UTC)]
    assert mock_datetime.mock_calls == exp_calls


@patch(MODULE, wraps=datetime)
def test_sell(mock_datetime: MagicMock) -> None:
    mock_datetime.now.side_effect = [NOW]
    tested = helper_tested()
    ctx = helper_ctx(None)
    with patch.object(BrokerCommand, "sold", side_effect=[helper_trade(TradeSide.SELL, None)]) as mock_sold:
        result = tested.sell("aapl", 1, "Strong quarter.", ctx)  # type: ignore[arg-type]
    expected = helper_trade_dict("sell", None)
    assert result == expected
    exp_calls = [call("aapl", 1, "Strong quarter.", None, NOW)]
    assert mock_sold.mock_calls == exp_calls
    exp_calls = [call.now(UTC)]
    assert mock_datetime.mock_calls == exp_calls


@pytest.mark.parametrize(
    "headers, expected",
    [
        pytest.param({"x-agent-run": "12"}, 12, id="a_run"),
        pytest.param({"x-agent-run": "0"}, None, id="zero_is_no_run"),
        pytest.param({"x-agent-run": "-3"}, None, id="negative"),
        pytest.param({"x-agent-run": "abc"}, None, id="not_a_number"),
        pytest.param({"x-agent-run": ""}, None, id="empty"),
        pytest.param({"authorization": "Bearer tok-1"}, None, id="no_run_header"),
        pytest.param(None, None, id="no_headers_at_all"),
    ],
)
def test_run_of(headers: dict[str, str] | None, expected: int | None) -> None:
    tested = BrokerMcpServer
    result = tested.run_of(helper_ctx(headers))  # type: ignore[arg-type]
    assert result == expected
