from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest
from starlette.requests import Request

from mcp_stock_markets.commands.broker_command import BrokerCommand
from mcp_stock_markets.commands.quote_command import QuoteCommand
from mcp_stock_markets.commands.session_command import SessionCommand
from mcp_stock_markets.constants.quote_source import QuoteSource
from mcp_stock_markets.constants.trade_side import TradeSide
from mcp_stock_markets.handlers.portfolio_router import PortfolioRouter
from mcp_stock_markets.handlers.session_guard import SessionGuard
from mcp_stock_markets.libraries.alpha_vantage_box import AlphaVantageBox
from mcp_stock_markets.libraries.blind_index import BlindIndex
from mcp_stock_markets.libraries.company_store import CompanyStore
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.libraries.google_finance_box import GoogleFinanceBox
from mcp_stock_markets.libraries.market_clock import MarketClock
from mcp_stock_markets.libraries.portfolio_store import PortfolioStore
from mcp_stock_markets.libraries.quote_store import QuoteStore
from mcp_stock_markets.libraries.secret_sealer import SecretSealer
from mcp_stock_markets.libraries.session_store import SessionStore
from mcp_stock_markets.libraries.user_store import UserStore
from mcp_stock_markets.libraries.web_box import WebBox
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.portfolio import Portfolio
from mcp_stock_markets.structures.portfolio_view import PortfolioView
from mcp_stock_markets.structures.settings import Settings
from mcp_stock_markets.structures.trade import Trade
from mcp_stock_markets.structures.user_account import UserAccount
from mcp_stock_markets.structures.valuation import Valuation

KEY = "Zm9yLXRlc3RzLW9ubHktZm9yLXRlc3RzLW9ubHktMzI="
NOW = datetime(2026, 10, 21, 14, 30, 0, tzinfo=UTC)


def helper_parts() -> tuple[SessionGuard, BrokerCommand]:
    settings = Settings(
        environment="dev",
        database_url="postgresql://u:p@h/d",
        app_version="v",
        build_time="b",
        app_commit="c",
        app_base_url="https://stocks.example.com",
        data_key=KEY,
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
    database = Database(settings.database_url)
    users = UserStore(database, SecretSealer(KEY), BlindIndex(KEY))
    guard = SessionGuard(settings, SessionCommand(users, SessionStore(database)))
    web = WebBox()
    company_store = CompanyStore(database)
    quotes = QuoteCommand(
        QuoteStore(database), company_store, GoogleFinanceBox(web), AlphaVantageBox(web, ""), MarketClock()
    )
    return guard, BrokerCommand(settings, database, PortfolioStore(database), company_store, quotes)


def helper_user() -> UserAccount:
    return UserAccount(user_id=7, email="owner@example.com", display_name="Owner", is_disabled=False)


def helper_request(path: str) -> Request:
    return Request({"type": "http", "method": "GET", "path": path, "headers": []})


def helper_portfolio() -> Portfolio:
    return Portfolio(
        portfolio_id=1,
        user_id=7,
        starting_budget=Decimal("500.00"),
        cash=Decimal("268.50"),
        created_at=datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
    )


def helper_portfolio_dict() -> dict[str, Any]:
    return {
        "portfolio_id": 1,
        "user_id": 7,
        "starting_budget": "500.00",
        "cash": "268.50",
        "created_at": "2026-10-01T12:00:00+00:00",
    }


def helper_trade() -> Trade:
    return Trade(
        trade_id=4,
        executed_at=NOW,
        symbol="AAPL",
        side=TradeSide.BUY,
        quantity=1,
        price=Decimal("231.5000"),
        amount=Decimal("231.50"),
        cash_after=Decimal("268.50"),
        quote_source=QuoteSource.GOOGLE_FINANCE,
        quote_as_of=datetime(2026, 10, 21, 14, 28, 0, tzinfo=UTC),
        agent_run_id=3,
        reason="Strong quarter.",
    )


def helper_denied(work: Callable[[Request], object], request: Request) -> tuple[int, str, list[Any]]:
    """What a handler does for nobody signed in: the guard's refusal, before any command."""
    with (
        patch.object(SessionGuard, "user", side_effect=[AppException(401, "Please sign in.")]) as mock_user,
        pytest.raises(AppException) as exc_info,
    ):
        work(request)
    return exc_info.value.status_code, exc_info.value.message, mock_user.mock_calls


def test___init__() -> None:
    guard, broker = helper_parts()
    tested = PortfolioRouter(guard, broker)
    result = (tested._guard, tested._broker)
    expected = (guard, broker)
    assert result == expected


def test_router() -> None:
    tested = PortfolioRouter(*helper_parts())
    result = [(route.path, tuple(sorted(route.methods)), route.name) for route in tested.router().routes]  # type: ignore[attr-defined]
    expected = [
        ("/api/portfolio", ("GET",), "portfolio"),
        ("/api/trades", ("GET",), "trades"),
        ("/api/valuations", ("GET",), "valuations"),
    ]
    assert result == expected


@patch("mcp_stock_markets.handlers.portfolio_router.datetime", wraps=datetime)
def test_portfolio(mock_datetime: MagicMock) -> None:
    mock_datetime.now.side_effect = [NOW]
    tested = PortfolioRouter(*helper_parts())
    request = helper_request("/api/portfolio")
    view = PortfolioView(
        portfolio=helper_portfolio(),
        positions=(),
        holdings_value=Decimal("0.00"),
        total_value=Decimal("268.50"),
        universe=("AAPL", "MSFT"),
    )
    with (
        patch.object(SessionGuard, "user", side_effect=[helper_user()]) as mock_user,
        patch.object(BrokerCommand, "portfolio_for", side_effect=[helper_portfolio()]) as mock_portfolio_for,
        patch.object(BrokerCommand, "view", side_effect=[view]) as mock_view,
    ):
        result = tested.portfolio(request)
    expected = {
        "portfolio": helper_portfolio_dict(),
        "positions": [],
        "holdings_value": "0.00",
        "total_value": "268.50",
        "universe": ["AAPL", "MSFT"],
    }
    assert result == expected
    exp_calls = [call(request)]
    assert mock_user.mock_calls == exp_calls
    exp_calls = [call(7)]
    assert mock_portfolio_for.mock_calls == exp_calls
    exp_calls = [call(helper_portfolio(), NOW)]
    assert mock_view.mock_calls == exp_calls
    exp_calls = [call.now(UTC)]
    assert mock_datetime.mock_calls == exp_calls


def test_portfolio__denied_without_a_session() -> None:
    tested = PortfolioRouter(*helper_parts())
    request = helper_request("/api/portfolio")
    result = helper_denied(lambda req: tested.portfolio(req), request)
    expected = (401, "Please sign in.", [call(request)])
    assert result == expected


def test_trades() -> None:
    tested = PortfolioRouter(*helper_parts())
    request = helper_request("/api/trades")
    with (
        patch.object(SessionGuard, "user", side_effect=[helper_user()]) as mock_user,
        patch.object(BrokerCommand, "portfolio_for", side_effect=[helper_portfolio()]) as mock_portfolio_for,
        patch.object(BrokerCommand, "trades", side_effect=[[helper_trade()]]) as mock_trades,
    ):
        result = tested.trades(request, 20)
    expected = {
        "trades": [
            {
                "trade_id": 4,
                "executed_at": "2026-10-21T14:30:00+00:00",
                "symbol": "AAPL",
                "side": "buy",
                "quantity": 1,
                "price": "231.5000",
                "amount": "231.50",
                "cash_after": "268.50",
                "quote_source": "google_finance",
                "quote_as_of": "2026-10-21T14:28:00+00:00",
                "agent_run_id": 3,
                "reason": "Strong quarter.",
            }
        ]
    }
    assert result == expected
    exp_calls = [call(request)]
    assert mock_user.mock_calls == exp_calls
    exp_calls = [call(7)]
    assert mock_portfolio_for.mock_calls == exp_calls
    exp_calls = [call(helper_portfolio(), 20)]
    assert mock_trades.mock_calls == exp_calls


def test_trades__denied_without_a_session() -> None:
    tested = PortfolioRouter(*helper_parts())
    request = helper_request("/api/trades")
    result = helper_denied(lambda req: tested.trades(req, 20), request)
    expected = (401, "Please sign in.", [call(request)])
    assert result == expected


def test_valuations() -> None:
    tested = PortfolioRouter(*helper_parts())
    request = helper_request("/api/valuations")
    valuations = [
        Valuation(
            taken_at=datetime(2026, 10, 21, 14, 0, tzinfo=UTC),
            cash=Decimal("268.50"),
            holdings_value=Decimal("231.50"),
            total_value=Decimal("500.00"),
        ),
        Valuation(
            taken_at=NOW,
            cash=Decimal("268.50"),
            holdings_value=Decimal("233.00"),
            total_value=Decimal("501.50"),
        ),
    ]
    with (
        patch.object(SessionGuard, "user", side_effect=[helper_user()]) as mock_user,
        patch.object(BrokerCommand, "portfolio_for", side_effect=[helper_portfolio()]) as mock_portfolio_for,
        patch.object(BrokerCommand, "valuations", side_effect=[valuations]) as mock_valuations,
    ):
        result = tested.valuations(request)
    expected = {
        "starting_budget": "500.00",
        "valuations": [
            {
                "taken_at": "2026-10-21T14:00:00+00:00",
                "cash": "268.50",
                "holdings_value": "231.50",
                "total_value": "500.00",
            },
            {
                "taken_at": "2026-10-21T14:30:00+00:00",
                "cash": "268.50",
                "holdings_value": "233.00",
                "total_value": "501.50",
            },
        ],
    }
    assert result == expected
    exp_calls = [call(request)]
    assert mock_user.mock_calls == exp_calls
    exp_calls = [call(7)]
    assert mock_portfolio_for.mock_calls == exp_calls
    exp_calls = [call(helper_portfolio())]
    assert mock_valuations.mock_calls == exp_calls


def test_valuations__denied_without_a_session() -> None:
    tested = PortfolioRouter(*helper_parts())
    request = helper_request("/api/valuations")
    result = helper_denied(lambda req: tested.valuations(req), request)
    expected = (401, "Please sign in.", [call(request)])
    assert result == expected
