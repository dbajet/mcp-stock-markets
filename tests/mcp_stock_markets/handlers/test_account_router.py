from __future__ import annotations

from decimal import Decimal
from unittest.mock import call, patch

from starlette.requests import Request

from mcp_stock_markets.commands.session_command import SessionCommand
from mcp_stock_markets.handlers.account_router import AccountRouter
from mcp_stock_markets.handlers.session_guard import SessionGuard
from mcp_stock_markets.libraries.blind_index import BlindIndex
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.libraries.secret_sealer import SecretSealer
from mcp_stock_markets.libraries.session_store import SessionStore
from mcp_stock_markets.libraries.user_store import UserStore
from mcp_stock_markets.structures.settings import Settings
from mcp_stock_markets.structures.user_account import UserAccount

KEY = "Zm9yLXRlc3RzLW9ubHktZm9yLXRlc3RzLW9ubHktMzI="


def helper_guard() -> SessionGuard:
    settings = Settings(
        environment="dev",
        database_url="postgresql://u:p@h/d",
        app_version="v",
        build_time="b",
        app_commit="c",
        app_base_url="https://docs.example.com",
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
    return SessionGuard(settings, SessionCommand(users, SessionStore(database)))


def test___init__() -> None:
    guard = helper_guard()
    tested = AccountRouter(guard)
    result = tested._guard
    expected = guard
    assert result == expected


def test_router() -> None:
    tested = AccountRouter(helper_guard())
    result = [(route.path, tuple(sorted(route.methods)), route.name) for route in tested.router().routes]  # type: ignore[attr-defined]
    expected = [("/api/account", ("GET",), "account")]
    assert result == expected


def test_account() -> None:
    tested = AccountRouter(helper_guard())
    request = Request({"type": "http", "method": "GET", "path": "/api/account", "headers": []})
    user = UserAccount(user_id=7, email="owner@example.com", display_name="owner", is_disabled=False)
    with patch.object(SessionGuard, "user", side_effect=[user]) as mock_user:
        result = tested.account(request)
    expected = {"user_id": 7, "email": "owner@example.com", "display_name": "owner", "is_disabled": False}
    assert result == expected
    exp_calls = [call(request)]
    assert mock_user.mock_calls == exp_calls
