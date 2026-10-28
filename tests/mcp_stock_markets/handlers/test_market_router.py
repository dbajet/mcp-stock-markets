from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest
from starlette.requests import Request

from mcp_stock_markets.commands.company_command import CompanyCommand
from mcp_stock_markets.commands.quote_command import QuoteCommand
from mcp_stock_markets.commands.session_command import SessionCommand
from mcp_stock_markets.constants.quote_source import QuoteSource
from mcp_stock_markets.handlers.market_router import MarketRouter
from mcp_stock_markets.handlers.session_guard import SessionGuard
from mcp_stock_markets.handlers.universe_request import UniverseRequest
from mcp_stock_markets.libraries.alpaca_box import AlpacaBox
from mcp_stock_markets.libraries.blind_index import BlindIndex
from mcp_stock_markets.libraries.company_store import CompanyStore
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.libraries.google_finance_box import GoogleFinanceBox
from mcp_stock_markets.libraries.market_clock import MarketClock
from mcp_stock_markets.libraries.quote_store import QuoteStore
from mcp_stock_markets.libraries.secret_sealer import SecretSealer
from mcp_stock_markets.libraries.session_store import SessionStore
from mcp_stock_markets.libraries.user_store import UserStore
from mcp_stock_markets.libraries.web_box import WebBox
from mcp_stock_markets.libraries.wikipedia_box import WikipediaBox
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.company import Company
from mcp_stock_markets.structures.market_status import MarketStatus
from mcp_stock_markets.structures.quote import Quote
from mcp_stock_markets.structures.settings import Settings
from mcp_stock_markets.structures.user_account import UserAccount

KEY = "Zm9yLXRlc3RzLW9ubHktZm9yLXRlc3RzLW9ubHktMzI="
NOW = datetime(2026, 10, 21, 14, 30, 0, tzinfo=UTC)


def helper_parts() -> tuple[SessionGuard, CompanyCommand, QuoteCommand]:
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
        alpaca_key_id="",
        alpaca_secret_key="",
        agent_interval_minutes=30,
        mcp_base_url="http://127.0.0.1:8000",
        mcp_token="mcp-token",
    )
    database = Database(settings.database_url)
    users = UserStore(database, SecretSealer(KEY), BlindIndex(KEY))
    guard = SessionGuard(settings, SessionCommand(users, SessionStore(database)))
    web = WebBox()
    company_store = CompanyStore(database)
    companies = CompanyCommand(settings, company_store, WikipediaBox(web))
    quotes = QuoteCommand(
        QuoteStore(database), company_store, GoogleFinanceBox(web), AlpacaBox(web, "", ""), MarketClock()
    )
    return guard, companies, quotes


def helper_tested() -> MarketRouter:
    return MarketRouter(*helper_parts())


def helper_user() -> UserAccount:
    return UserAccount(user_id=7, email="owner@example.com", display_name="Owner", is_disabled=False)


def helper_request(method: str, path: str) -> Request:
    return Request({"type": "http", "method": method, "path": path, "headers": []})


def helper_company(symbol: str, name: str) -> Company:
    return Company(
        symbol=symbol,
        name=name,
        sector="Information Technology",
        sub_industry="Systems Software",
        headquarters="Redmond, Washington",
        exchange="NASDAQ",
    )


def helper_company_dict(symbol: str, name: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "name": name,
        "sector": "Information Technology",
        "sub_industry": "Systems Software",
        "headquarters": "Redmond, Washington",
        "exchange": "NASDAQ",
    }


def helper_quote() -> Quote:
    return Quote(
        symbol="MSFT",
        price=Decimal("512.2500"),
        currency="USD",
        as_of=datetime(2026, 10, 21, 14, 28, 0, tzinfo=UTC),
        source=QuoteSource.GOOGLE_FINANCE,
        fetched_at=datetime(2026, 10, 21, 14, 29, 0, tzinfo=UTC),
    )


def helper_quote_dict() -> dict[str, Any]:
    return {
        "symbol": "MSFT",
        "price": "512.2500",
        "currency": "USD",
        "as_of": "2026-10-21T14:28:00+00:00",
        "source": "google_finance",
        "fetched_at": "2026-10-21T14:29:00+00:00",
    }


def helper_denied(work: Callable[[Request], object], request: Request) -> tuple[int, str, list[Any]]:
    """What a handler does for nobody signed in: the guard's refusal, before any command."""
    with (
        patch.object(SessionGuard, "user", side_effect=[AppException(401, "Please sign in.")]) as mock_user,
        pytest.raises(AppException) as exc_info,
    ):
        work(request)
    return exc_info.value.status_code, exc_info.value.message, mock_user.mock_calls


def test___init__() -> None:
    guard, companies, quotes = helper_parts()
    tested = MarketRouter(guard, companies, quotes)
    result = (tested._guard, tested._companies, tested._quotes)
    expected = (guard, companies, quotes)
    assert result == expected


def test_router() -> None:
    tested = helper_tested()
    result = [(route.path, tuple(sorted(route.methods)), route.name) for route in tested.router().routes]  # type: ignore[attr-defined]
    expected = [
        ("/api/market", ("GET",), "market"),
        ("/api/companies", ("GET",), "companies"),
        ("/api/companies/refresh", ("POST",), "refreshed"),
        ("/api/universe", ("POST",), "added"),
        ("/api/universe/{symbol}", ("DELETE",), "removed"),
    ]
    assert result == expected


@patch("mcp_stock_markets.handlers.market_router.datetime", wraps=datetime)
def test_market(mock_datetime: MagicMock) -> None:
    mock_datetime.now.side_effect = [NOW]
    tested = helper_tested()
    request = helper_request("GET", "/api/market")
    status = MarketStatus(
        is_open=False,
        now=NOW,
        closes_at=None,
        next_open=datetime(2026, 10, 22, 13, 30, tzinfo=UTC),
    )
    universe = [helper_company("MSFT", "Microsoft"), helper_company("ORCL", "Oracle")]
    priced = [
        helper_company_dict("MSFT", "Microsoft") | {"quote": helper_quote_dict()},
        helper_company_dict("ORCL", "Oracle") | {"quote": None, "quote_error": "No price."},
    ]
    with (
        patch.object(SessionGuard, "user", side_effect=[helper_user()]) as mock_user,
        patch.object(QuoteCommand, "market", side_effect=[status]) as mock_market,
        patch.object(CompanyCommand, "limit", side_effect=[5]) as mock_limit,
        patch.object(CompanyCommand, "universe", side_effect=[universe]) as mock_universe,
        patch.object(MarketRouter, "universe_priced", side_effect=[priced]) as mock_universe_priced,
        patch.object(CompanyCommand, "count", side_effect=[503]) as mock_count,
    ):
        result = tested.market(request)
    expected = {
        "status": {
            "is_open": False,
            "now": "2026-10-21T14:30:00+00:00",
            "closes_at": None,
            "next_open": "2026-10-22T13:30:00+00:00",
        },
        "limit": 5,
        "universe": [
            helper_company_dict("MSFT", "Microsoft") | {"quote": helper_quote_dict()},
            helper_company_dict("ORCL", "Oracle") | {"quote": None, "quote_error": "No price."},
        ],
        "sp500_companies": 503,
    }
    assert result == expected
    exp_calls = [call(request)]
    assert mock_user.mock_calls == exp_calls
    exp_calls = [call(NOW)]
    assert mock_market.mock_calls == exp_calls
    exp_calls = [call()]
    assert mock_limit.mock_calls == exp_calls
    assert mock_universe.mock_calls == exp_calls
    assert mock_count.mock_calls == exp_calls
    exp_calls = [call([helper_company("MSFT", "Microsoft"), helper_company("ORCL", "Oracle")], NOW)]
    assert mock_universe_priced.mock_calls == exp_calls
    exp_calls = [call.now(UTC)]
    assert mock_datetime.mock_calls == exp_calls


def test_market__denied_without_a_session() -> None:
    tested = helper_tested()
    request = helper_request("GET", "/api/market")
    result = helper_denied(lambda req: tested.market(req), request)
    expected = (401, "Please sign in.", [call(request)])
    assert result == expected


def test_universe_priced() -> None:
    tested = helper_tested()
    # Both lookups wait for each other: priced one after another, the first
    # would wait alone and break the barrier.
    both = threading.Barrier(2, timeout=5)
    priced = {
        "MSFT": helper_company_dict("MSFT", "Microsoft") | {"quote": helper_quote_dict()},
        "ORCL": helper_company_dict("ORCL", "Oracle") | {"quote": None, "quote_error": "No price."},
    }

    def helper_priced(company: dict[str, Any], symbol: str, now: datetime) -> dict[str, Any]:
        both.wait()
        return priced[symbol]

    with patch.object(MarketRouter, "priced", side_effect=helper_priced) as mock_priced:
        result = tested.universe_priced([helper_company("MSFT", "Microsoft"), helper_company("ORCL", "Oracle")], NOW)
    expected = [
        helper_company_dict("MSFT", "Microsoft") | {"quote": helper_quote_dict()},
        helper_company_dict("ORCL", "Oracle") | {"quote": None, "quote_error": "No price."},
    ]
    assert result == expected
    # The two threads call in either order.
    exp_calls = [
        call(helper_company_dict("MSFT", "Microsoft"), "MSFT", NOW),
        call(helper_company_dict("ORCL", "Oracle"), "ORCL", NOW),
    ]
    assert sorted(mock_priced.mock_calls, key=lambda made: made.args[1]) == exp_calls


def test_universe_priced__an_empty_market() -> None:
    tested = helper_tested()
    with patch.object(MarketRouter, "priced", side_effect=[]) as mock_priced:
        result = tested.universe_priced([], NOW)
    assert result == []
    exp_calls = []
    assert mock_priced.mock_calls == exp_calls


def test_priced() -> None:
    tested = helper_tested()
    with patch.object(QuoteCommand, "quote", side_effect=[helper_quote()]) as mock_quote:
        result = tested.priced(helper_company_dict("MSFT", "Microsoft"), "MSFT", NOW)
    expected = helper_company_dict("MSFT", "Microsoft") | {"quote": helper_quote_dict()}
    assert result == expected
    exp_calls = [call("MSFT", NOW)]
    assert mock_quote.mock_calls == exp_calls


def test_priced__quote_error_says_why() -> None:
    """One company without a price does not hide the others."""
    tested = helper_tested()
    error = AppException(502, "No price could be fetched for MSFT right now.")
    with patch.object(QuoteCommand, "quote", side_effect=[error]) as mock_quote:
        result = tested.priced(helper_company_dict("MSFT", "Microsoft"), "MSFT", NOW)
    expected = helper_company_dict("MSFT", "Microsoft") | {
        "quote": None,
        "quote_error": "No price could be fetched for MSFT right now.",
    }
    assert result == expected
    exp_calls = [call("MSFT", NOW)]
    assert mock_quote.mock_calls == exp_calls


def test_companies() -> None:
    tested = helper_tested()
    request = helper_request("GET", "/api/companies")
    sectors = [{"sector": "Information Technology", "companies": 69}]
    with (
        patch.object(SessionGuard, "user", side_effect=[helper_user()]) as mock_user,
        patch.object(CompanyCommand, "listed", side_effect=[[helper_company("MSFT", "Microsoft")]]) as mock_listed,
        patch.object(CompanyCommand, "sectors", side_effect=[sectors]) as mock_sectors,
    ):
        result = tested.companies(request)
    expected = {
        "companies": [helper_company_dict("MSFT", "Microsoft")],
        "sectors": [{"sector": "Information Technology", "companies": 69}],
    }
    assert result == expected
    exp_calls = [call(request)]
    assert mock_user.mock_calls == exp_calls
    exp_calls = [call()]
    assert mock_listed.mock_calls == exp_calls
    exp_calls = [call()]
    assert mock_sectors.mock_calls == exp_calls


def test_companies__denied_without_a_session() -> None:
    tested = helper_tested()
    request = helper_request("GET", "/api/companies")
    result = helper_denied(tested.companies, request)
    expected = (401, "Please sign in.", [call(request)])
    assert result == expected


def test_refreshed() -> None:
    tested = helper_tested()
    request = helper_request("POST", "/api/companies/refresh")
    with (
        patch.object(SessionGuard, "user", side_effect=[helper_user()]) as mock_user,
        patch.object(CompanyCommand, "refreshed", side_effect=[503]) as mock_refreshed,
    ):
        result = tested.refreshed(request)
    expected = {"companies": 503}
    assert result == expected
    exp_calls = [call(request)]
    assert mock_user.mock_calls == exp_calls
    exp_calls = [call()]
    assert mock_refreshed.mock_calls == exp_calls


def test_refreshed__denied_without_a_session() -> None:
    tested = helper_tested()
    request = helper_request("POST", "/api/companies/refresh")
    result = helper_denied(lambda req: tested.refreshed(req), request)
    expected = (401, "Please sign in.", [call(request)])
    assert result == expected


def test_added() -> None:
    tested = helper_tested()
    request = helper_request("POST", "/api/universe")
    with (
        patch.object(SessionGuard, "user", side_effect=[helper_user()]) as mock_user,
        patch.object(CompanyCommand, "added", side_effect=[helper_company("MSFT", "Microsoft")]) as mock_added,
    ):
        result = tested.added(request, UniverseRequest(symbol="msft"))
    expected = helper_company_dict("MSFT", "Microsoft")
    assert result == expected
    exp_calls = [call(request)]
    assert mock_user.mock_calls == exp_calls
    exp_calls = [call("msft")]
    assert mock_added.mock_calls == exp_calls


def test_added__denied_without_a_session() -> None:
    tested = helper_tested()
    request = helper_request("POST", "/api/universe")
    result = helper_denied(lambda req: tested.added(req, UniverseRequest(symbol="msft")), request)
    expected = (401, "Please sign in.", [call(request)])
    assert result == expected


def test_removed() -> None:
    tested = helper_tested()
    request = helper_request("DELETE", "/api/universe/MSFT")
    with (
        patch.object(SessionGuard, "user", side_effect=[helper_user()]) as mock_user,
        patch.object(CompanyCommand, "removed", side_effect=[None]) as mock_removed,
    ):
        result = tested.removed(request, "MSFT")
    expected = {"ok": True}
    assert result == expected
    exp_calls = [call(request)]
    assert mock_user.mock_calls == exp_calls
    exp_calls = [call("MSFT")]
    assert mock_removed.mock_calls == exp_calls


def test_removed__denied_without_a_session() -> None:
    tested = helper_tested()
    request = helper_request("DELETE", "/api/universe/MSFT")
    result = helper_denied(lambda req: tested.removed(req, "MSFT"), request)
    expected = (401, "Please sign in.", [call(request)])
    assert result == expected
