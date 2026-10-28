from __future__ import annotations

import re
from decimal import Decimal
from unittest.mock import call, patch

import pytest
from starlette.requests import Request

from mcp_stock_markets.commands.session_command import SessionCommand
from mcp_stock_markets.handlers.session_guard import SessionGuard
from mcp_stock_markets.libraries.blind_index import BlindIndex
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.libraries.secret_sealer import SecretSealer
from mcp_stock_markets.libraries.session_store import SessionStore
from mcp_stock_markets.libraries.user_store import UserStore
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.settings import Settings
from mcp_stock_markets.structures.user_account import UserAccount


def helper_settings(environment: str) -> Settings:
    return Settings(
        environment=environment,
        database_url="postgresql://u:p@h/d",
        app_version="v",
        build_time="b",
        app_commit="c",
        app_base_url="https://docs.example.com",
        data_key="Zm9yLXRlc3RzLW9ubHktZm9yLXRlc3RzLW9ubHktMzI=",
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


def helper_sessions() -> SessionCommand:
    key = "Zm9yLXRlc3RzLW9ubHktZm9yLXRlc3RzLW9ubHktMzI="
    database = Database("postgresql://u:p@h/d")
    return SessionCommand(UserStore(database, SecretSealer(key), BlindIndex(key)), SessionStore(database))


def helper_instance(environment: str) -> SessionGuard:
    return SessionGuard(helper_settings(environment), helper_sessions())


def helper_request(method: str, headers: list[tuple[bytes, bytes]]) -> Request:
    return Request({"type": "http", "method": method, "path": "/api/x", "headers": headers})


def helper_user() -> UserAccount:
    return UserAccount(
        user_id=7,
        email="ada@example.com",
        display_name="Ada",
        is_disabled=False,
    )


def test___init__() -> None:
    settings = helper_settings("dev")
    sessions = helper_sessions()
    tested = SessionGuard(settings, sessions)
    result = (tested._settings, tested._sessions)
    expected = (settings, sessions)
    assert result == expected


@pytest.mark.parametrize(
    "method, headers",
    [
        pytest.param("GET", [], id="get_without_origin"),
        pytest.param("GET", [(b"origin", b"https://evil.example.com")], id="get_from_elsewhere"),
        pytest.param("HEAD", [(b"origin", b"https://evil.example.com")], id="head_from_elsewhere"),
        pytest.param("POST", [(b"origin", b"https://docs.example.com")], id="post_same_origin"),
        pytest.param("PUT", [(b"origin", b"https://docs.example.com")], id="put_same_origin"),
        pytest.param("PATCH", [(b"origin", b"https://docs.example.com")], id="patch_same_origin"),
        pytest.param("DELETE", [(b"origin", b"https://docs.example.com")], id="delete_same_origin"),
    ],
)
def test_same_origin(method: str, headers: list[tuple[bytes, bytes]]) -> None:
    tested = helper_instance("production")
    result = tested.same_origin(helper_request(method, headers))
    assert result is None


@pytest.mark.parametrize(
    "method, headers",
    [
        pytest.param("POST", [], id="post_without_origin"),
        pytest.param("POST", [(b"origin", b"https://evil.example.com")], id="post_from_elsewhere"),
        pytest.param("POST", [(b"origin", b"http://docs.example.com")], id="post_other_scheme"),
        pytest.param("POST", [(b"origin", b"https://docs.example.com:8443")], id="post_other_port"),
        pytest.param("POST", [(b"origin", b"null")], id="post_null_origin"),
        pytest.param("PUT", [(b"origin", b"https://evil.example.com")], id="put_from_elsewhere"),
        pytest.param("PATCH", [], id="patch_without_origin"),
        pytest.param("DELETE", [(b"origin", b"https://evil.example.com")], id="delete_from_elsewhere"),
    ],
)
def test_same_origin__refused(method: str, headers: list[tuple[bytes, bytes]]) -> None:
    tested = helper_instance("production")
    with pytest.raises(AppException) as exc_info:
        tested.same_origin(helper_request(method, headers))
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (403, "This request did not come from MCP Stock Markets.")
    assert result == expected


@pytest.mark.parametrize(
    "method, headers, exp_calls",
    [
        pytest.param("GET", [(b"cookie", b"mcp_stock_markets_session=tok-1")], [call("tok-1")], id="get"),
        pytest.param(
            "POST",
            [(b"origin", b"https://docs.example.com"), (b"cookie", b"other=x; mcp_stock_markets_session=tok-1")],
            [call("tok-1")],
            id="post_same_origin",
        ),
    ],
)
def test_user(method: str, headers: list[tuple[bytes, bytes]], exp_calls: list) -> None:
    tested = helper_instance("production")
    with patch.object(SessionCommand, "current", side_effect=[helper_user()]) as mock_current:
        result = tested.user(helper_request(method, headers))
    expected = helper_user()
    assert result == expected
    assert mock_current.mock_calls == exp_calls


@pytest.mark.parametrize(
    "headers, exp_calls",
    [
        pytest.param([], [call("")], id="no_cookie"),
        pytest.param([(b"cookie", b"mcp_stock_markets_session=stale")], [call("stale")], id="unknown_session"),
    ],
)
def test_user__not_signed_in(headers: list[tuple[bytes, bytes]], exp_calls: list) -> None:
    tested = helper_instance("production")
    with patch.object(SessionCommand, "current", side_effect=[None]) as mock_current:
        with pytest.raises(AppException) as exc_info:
            tested.user(helper_request("GET", headers))
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (401, "Please sign in.")
    assert result == expected
    assert mock_current.mock_calls == exp_calls


def test_user__another_site_is_refused_before_the_session() -> None:
    tested = helper_instance("production")
    headers = [(b"origin", b"https://evil.example.com"), (b"cookie", b"mcp_stock_markets_session=tok-1")]
    with patch.object(SessionCommand, "current", side_effect=[]) as mock_current:
        with pytest.raises(AppException) as exc_info:
            tested.user(helper_request("POST", headers))
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (403, "This request did not come from MCP Stock Markets.")
    assert result == expected
    exp_calls: list = []
    assert mock_current.mock_calls == exp_calls


@pytest.mark.parametrize(
    "environment, expected",
    [
        pytest.param(
            "production",
            (
                200,
                b'{"ok":true}',
                "mcp_stock_markets_session=tok-1; HttpOnly; Max-Age=2592000; Path=/; SameSite=lax; Secure",
            ),
            id="production_is_secure",
        ),
        pytest.param(
            "dev",
            (200, b'{"ok":true}', "mcp_stock_markets_session=tok-1; HttpOnly; Max-Age=2592000; Path=/; SameSite=lax"),
            id="dev_over_plain_http",
        ),
    ],
)
def test_signed_in(environment: str, expected: tuple[int, bytes, str]) -> None:
    tested = helper_instance(environment)
    response = tested.signed_in("tok-1", {"ok": True})
    result = (response.status_code, response.body, response.headers["set-cookie"])
    assert result == expected


def test_signed_out() -> None:
    tested = SessionGuard
    response = tested.signed_out()
    # The expiry is the clock's: masked, so the rest of the cookie is asserted whole.
    cookie = re.sub(r"expires=[^;]+", "expires=<now>", response.headers["set-cookie"])
    result = (response.status_code, response.body, cookie)
    expected = (200, b'{"ok":true}', 'mcp_stock_markets_session=""; expires=<now>; Max-Age=0; Path=/; SameSite=lax')
    assert result == expected


@pytest.mark.parametrize(
    "headers, expected",
    [
        pytest.param([(b"cookie", b"mcp_stock_markets_session=tok-1")], "tok-1", id="with_cookie"),
        pytest.param([(b"cookie", b"other=x")], "", id="other_cookie_only"),
        pytest.param([], "", id="no_cookie"),
    ],
)
def test_token_of(headers: list[tuple[bytes, bytes]], expected: str) -> None:
    tested = SessionGuard
    result = tested.token_of(helper_request("GET", headers))
    assert result == expected
