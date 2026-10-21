from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import call, patch

from starlette.requests import Request

from mcp_stock_markets.commands.llm_connection_command import LlmConnectionCommand
from mcp_stock_markets.commands.session_command import SessionCommand
from mcp_stock_markets.constants.llm_kind import LlmKind
from mcp_stock_markets.handlers.llm_connection_request import LlmConnectionRequest
from mcp_stock_markets.handlers.llm_connection_router import LlmConnectionRouter
from mcp_stock_markets.handlers.llm_models_request import LlmModelsRequest
from mcp_stock_markets.handlers.llm_routing_request import LlmRoutingRequest
from mcp_stock_markets.handlers.session_guard import SessionGuard
from mcp_stock_markets.libraries.blind_index import BlindIndex
from mcp_stock_markets.libraries.claude_box import ClaudeBox
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.libraries.llm_connection_store import LlmConnectionStore
from mcp_stock_markets.libraries.llm_gateway import LlmGateway
from mcp_stock_markets.libraries.openai_chat_box import OpenAiChatBox
from mcp_stock_markets.libraries.secret_sealer import SecretSealer
from mcp_stock_markets.libraries.session_store import SessionStore
from mcp_stock_markets.libraries.user_store import UserStore
from mcp_stock_markets.structures.connection_health import ConnectionHealth
from mcp_stock_markets.structures.llm_connection import LlmConnection
from mcp_stock_markets.structures.llm_routing import LlmRouting
from mcp_stock_markets.structures.settings import Settings
from mcp_stock_markets.structures.user_account import UserAccount

KEY = "Zm9yLXRlc3RzLW9ubHktZm9yLXRlc3RzLW9ubHktMzI="


def helper_parts() -> tuple[SessionGuard, LlmConnectionCommand]:
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
    sealer = SecretSealer(KEY)
    guard = SessionGuard(settings, SessionCommand(UserStore(database, sealer, BlindIndex(KEY)), SessionStore(database)))
    store = LlmConnectionStore(database, sealer)
    return guard, LlmConnectionCommand(store, LlmGateway(store, OpenAiChatBox(), ClaudeBox()))


def helper_user() -> UserAccount:
    return UserAccount(1, "owner@example.com", "Owner", False)


def helper_request(method: str) -> Request:
    return Request({"type": "http", "method": method, "path": "/api/llm/connections", "headers": []})


def helper_claude(connection_id: int, api_key: str) -> LlmConnection:
    return LlmConnection(connection_id, "Claude", LlmKind.CLAUDE, "", api_key, "claude-opus-5-5", True)


def helper_public(connection_id: int) -> dict[str, Any]:
    return {
        "connection_id": connection_id,
        "name": "Claude",
        "kind": "claude",
        "base_url": "",
        "has_key": True,
        "model": "claude-opus-5-5",
        "disable_thinking": True,
    }


def helper_body() -> LlmConnectionRequest:
    return LlmConnectionRequest(
        name="Claude",
        kind=LlmKind.CLAUDE,
        api_key="sk-ant",
        model="claude-opus-5-5",
    )


def test___init__() -> None:
    guard, connections = helper_parts()
    tested = LlmConnectionRouter(guard, connections)
    result = (tested._guard, tested._connections)
    expected = (guard, connections)
    assert result == expected


def test_router() -> None:
    tested = LlmConnectionRouter(*helper_parts())
    result = [(route.path, tuple(sorted(route.methods)), route.name) for route in tested.router().routes]  # type: ignore[attr-defined]
    expected = [
        ("/api/llm/connections", ("GET",), "listed"),
        ("/api/llm/connections", ("POST",), "created"),
        ("/api/llm/connections/{connection_id}", ("PUT",), "updated"),
        ("/api/llm/connections/{connection_id}", ("DELETE",), "deleted"),
        ("/api/llm/connections/{connection_id}/health", ("GET",), "health"),
        ("/api/llm/models", ("POST",), "models"),
        ("/api/llm/routing", ("PUT",), "routed"),
    ]
    assert result == expected


def test_listed() -> None:
    """Keys never leave: each connection says only whether it has one."""
    tested = LlmConnectionRouter(*helper_parts())
    request = helper_request("GET")
    with (
        patch.object(SessionGuard, "user", side_effect=[helper_user()]) as mock_user,
        patch.object(
            LlmConnectionCommand, "connections", side_effect=[[helper_claude(2, "sk-ant")]]
        ) as mock_connections,
        patch.object(LlmConnectionCommand, "routing", side_effect=[LlmRouting(2)]) as mock_routing,
    ):
        result = tested.listed(request)
    expected = {"connections": [helper_public(2)], "routing": {"agent": 2}}
    assert result == expected
    exp_calls = [call(request)]
    assert mock_user.mock_calls == exp_calls
    exp_calls = [call()]
    assert mock_connections.mock_calls == exp_calls
    assert mock_routing.mock_calls == exp_calls


def test_created() -> None:
    tested = LlmConnectionRouter(*helper_parts())
    request = helper_request("POST")
    with (
        patch.object(SessionGuard, "user", side_effect=[helper_user()]) as mock_user,
        patch.object(LlmConnectionCommand, "created", side_effect=[helper_claude(3, "sk-ant")]) as mock_created,
    ):
        result = tested.created(request, helper_body())
    expected = helper_public(3)
    assert result == expected
    exp_calls = [call(request)]
    assert mock_user.mock_calls == exp_calls
    exp_calls = [call(helper_claude(0, "sk-ant"))]
    assert mock_created.mock_calls == exp_calls


def test_updated() -> None:
    tested = LlmConnectionRouter(*helper_parts())
    request = helper_request("PUT")
    with (
        patch.object(SessionGuard, "user", side_effect=[helper_user()]) as mock_user,
        patch.object(LlmConnectionCommand, "updated", side_effect=[helper_claude(3, "sk-ant")]) as mock_updated,
    ):
        result = tested.updated(request, 3, helper_body())
    expected = helper_public(3)
    assert result == expected
    exp_calls = [call(request)]
    assert mock_user.mock_calls == exp_calls
    exp_calls = [call(helper_claude(3, "sk-ant"))]
    assert mock_updated.mock_calls == exp_calls


def test_deleted() -> None:
    tested = LlmConnectionRouter(*helper_parts())
    request = helper_request("DELETE")
    with (
        patch.object(SessionGuard, "user", side_effect=[helper_user()]) as mock_user,
        patch.object(LlmConnectionCommand, "deleted", side_effect=[None]) as mock_deleted,
    ):
        result = tested.deleted(request, 3)
    expected = {"ok": True}
    assert result == expected
    exp_calls = [call(request)]
    assert mock_user.mock_calls == exp_calls
    exp_calls = [call(3)]
    assert mock_deleted.mock_calls == exp_calls


def test_health() -> None:
    tested = LlmConnectionRouter(*helper_parts())
    request = helper_request("GET")
    with (
        patch.object(SessionGuard, "user", side_effect=[helper_user()]) as mock_user,
        patch.object(
            LlmConnectionCommand, "health", side_effect=[ConnectionHealth(3, True, "Connected.", 120.5)]
        ) as mock_health,
    ):
        result = tested.health(request, 3)
    expected = {"connection_id": 3, "is_ok": True, "detail": "Connected.", "elapsed_ms": 120.5}
    assert result == expected
    exp_calls = [call(request)]
    assert mock_user.mock_calls == exp_calls
    exp_calls = [call(3)]
    assert mock_health.mock_calls == exp_calls


def test_models() -> None:
    tested = LlmConnectionRouter(*helper_parts())
    request = helper_request("POST")
    body = LlmModelsRequest(connection_id=2, kind=LlmKind.OPENAI, base_url="https://llm.example.com/v1")
    with (
        patch.object(SessionGuard, "user", side_effect=[helper_user()]) as mock_user,
        patch.object(LlmConnectionCommand, "models", side_effect=[["fast", "good"]]) as mock_models,
    ):
        result = tested.models(request, body)
    expected = {"models": ["fast", "good"]}
    assert result == expected
    exp_calls = [call(request)]
    assert mock_user.mock_calls == exp_calls
    exp_calls = [call(2, LlmKind.OPENAI, "https://llm.example.com/v1", "")]
    assert mock_models.mock_calls == exp_calls


def test_routed() -> None:
    tested = LlmConnectionRouter(*helper_parts())
    request = helper_request("PUT")
    with (
        patch.object(SessionGuard, "user", side_effect=[helper_user()]) as mock_user,
        patch.object(LlmConnectionCommand, "routed", side_effect=[None]) as mock_routed,
    ):
        result = tested.routed(request, LlmRoutingRequest(agent=1))
    expected = {"ok": True}
    assert result == expected
    exp_calls = [call(request)]
    assert mock_user.mock_calls == exp_calls
    exp_calls = [call(LlmRouting(agent=1))]
    assert mock_routed.mock_calls == exp_calls


def test_connection_of() -> None:
    tested = LlmConnectionRouter
    result = tested.connection_of(7, helper_body())
    expected = helper_claude(7, "sk-ant")
    assert result == expected
