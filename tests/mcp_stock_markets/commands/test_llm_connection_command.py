from __future__ import annotations

from unittest.mock import call, patch

import pytest

from mcp_stock_markets.commands.llm_connection_command import LlmConnectionCommand
from mcp_stock_markets.constants.llm_kind import LlmKind
from mcp_stock_markets.libraries.claude_box import ClaudeBox
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.libraries.llm_connection_store import LlmConnectionStore
from mcp_stock_markets.libraries.llm_gateway import LlmGateway
from mcp_stock_markets.libraries.openai_chat_box import OpenAiChatBox
from mcp_stock_markets.libraries.secret_sealer import SecretSealer
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.connection_health import ConnectionHealth
from mcp_stock_markets.structures.llm_connection import LlmConnection
from mcp_stock_markets.structures.llm_routing import LlmRouting

KEY = "Zm9yLXRlc3RzLW9ubHktZm9yLXRlc3RzLW9ubHktMzI="


def helper_parts() -> tuple[LlmConnectionStore, LlmGateway]:
    store = LlmConnectionStore(Database("postgresql://u:p@h/d"), SecretSealer(KEY))
    return store, LlmGateway(store, OpenAiChatBox(), ClaudeBox())


def helper_instance() -> LlmConnectionCommand:
    return LlmConnectionCommand(*helper_parts())


def helper_local(connection_id: int, api_key: str) -> LlmConnection:
    return LlmConnection(
        connection_id,
        "Local",
        LlmKind.OPENAI,
        "https://llm.example.com/v1",
        api_key,
        "local-model",
        True,
    )


def test___init__() -> None:
    store, gateway = helper_parts()
    tested = LlmConnectionCommand(store, gateway)
    result = (tested._store, tested._gateway)
    expected = (store, gateway)
    assert result == expected


def test_connections() -> None:
    tested = helper_instance()
    with patch.object(LlmConnectionStore, "connections", side_effect=[[helper_local(1, "k")]]) as mock_connections:
        result = tested.connections()
    expected = [helper_local(1, "k")]
    assert result == expected
    exp_calls = [call()]
    assert mock_connections.mock_calls == exp_calls


def test_routing() -> None:
    tested = helper_instance()
    with patch.object(LlmConnectionStore, "routing", side_effect=[LlmRouting(1)]) as mock_routing:
        result = tested.routing()
    expected = LlmRouting(1)
    assert result == expected
    exp_calls = [call()]
    assert mock_routing.mock_calls == exp_calls


def test_created() -> None:
    tested = helper_instance()
    with patch.object(LlmConnectionStore, "created", side_effect=[helper_local(1, "k")]) as mock_created:
        result = tested.created(
            helper_local(0, "k")._replace(name="   Local  ", base_url="https://llm.example.com/v1/")
        )
    expected = helper_local(1, "k")
    assert result == expected
    exp_calls = [call(helper_local(0, "k"))]
    assert mock_created.mock_calls == exp_calls


def test_updated() -> None:
    """An empty key keeps the stored one."""
    tested = helper_instance()
    with (
        patch.object(LlmConnectionStore, "connection", side_effect=[helper_local(1, "stored-key")]) as mock_connection,
        patch.object(LlmConnectionStore, "updated", side_effect=[True]) as mock_updated,
    ):
        result = tested.updated(helper_local(1, "")._replace(name="Local GPU"))
    expected = helper_local(1, "stored-key")._replace(name="Local GPU")
    assert result == expected
    exp_calls = [call(1)]
    assert mock_connection.mock_calls == exp_calls
    exp_calls = [call(helper_local(1, "stored-key")._replace(name="Local GPU"))]
    assert mock_updated.mock_calls == exp_calls


def test_updated__not_found() -> None:
    tested = helper_instance()
    with (
        patch.object(LlmConnectionStore, "connection", side_effect=[None]) as mock_connection,
        patch.object(LlmConnectionStore, "updated", side_effect=[]) as mock_updated,
        pytest.raises(AppException) as exc_info,
    ):
        tested.updated(helper_local(9, ""))
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (404, "This connection does not exist.")
    assert result == expected
    exp_calls = [call(9)]
    assert mock_connection.mock_calls == exp_calls
    exp_calls = []
    assert mock_updated.mock_calls == exp_calls


def test_deleted() -> None:
    tested = helper_instance()
    with patch.object(LlmConnectionStore, "deleted", side_effect=[True]) as mock_deleted:
        result = tested.deleted(3)
    assert result is None
    exp_calls = [call(3)]
    assert mock_deleted.mock_calls == exp_calls


def test_deleted__not_found() -> None:
    tested = helper_instance()
    with (
        patch.object(LlmConnectionStore, "deleted", side_effect=[False]) as mock_deleted,
        pytest.raises(AppException) as exc_info,
    ):
        tested.deleted(3)
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (404, "This connection does not exist.")
    assert result == expected
    exp_calls = [call(3)]
    assert mock_deleted.mock_calls == exp_calls


def test_routed() -> None:
    tested = helper_instance()
    with (
        patch.object(LlmConnectionStore, "connection", side_effect=[helper_local(1, "k")]) as mock_connection,
        patch.object(LlmConnectionStore, "routed", side_effect=[None]) as mock_routed,
    ):
        result = tested.routed(LlmRouting(agent=1))
    assert result is None
    exp_calls = [call(1)]
    assert mock_connection.mock_calls == exp_calls
    exp_calls = [call(LlmRouting(agent=1))]
    assert mock_routed.mock_calls == exp_calls


def test_routed__an_unknown_connection_is_refused() -> None:
    tested = helper_instance()
    with (
        patch.object(LlmConnectionStore, "connection", side_effect=[None]) as mock_connection,
        patch.object(LlmConnectionStore, "routed", side_effect=[]) as mock_routed,
        pytest.raises(AppException) as exc_info,
    ):
        tested.routed(LlmRouting(agent=8))
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (404, "This connection does not exist.")
    assert result == expected
    exp_calls = [call(8)]
    assert mock_connection.mock_calls == exp_calls
    exp_calls = []
    assert mock_routed.mock_calls == exp_calls


def test_health() -> None:
    tested = helper_instance()
    light = ConnectionHealth(1, False, "The API key was refused.", 90.0)
    with (
        patch.object(LlmConnectionStore, "connection", side_effect=[helper_local(1, "k")]) as mock_connection,
        patch.object(LlmGateway, "health", side_effect=[light]) as mock_health,
    ):
        result = tested.health(1)
    expected = ConnectionHealth(1, False, "The API key was refused.", 90.0)
    assert result == expected
    exp_calls = [call(1)]
    assert mock_connection.mock_calls == exp_calls
    exp_calls = [call(helper_local(1, "k"))]
    assert mock_health.mock_calls == exp_calls


@pytest.mark.parametrize(
    "connection_id, kind, found, exp_endpoint, exp_found",
    [
        pytest.param(
            0,
            LlmKind.OPENAI,
            [],
            LlmConnection(0, "", LlmKind.OPENAI, "https://llm.example.com/v1", "typed-key", "", False),
            [],
            id="new-with-the-typed-key",
        ),
        pytest.param(
            1,
            LlmKind.OPENAI,
            [helper_local(1, "stored-key")],
            LlmConnection(1, "", LlmKind.OPENAI, "https://llm.example.com/v1", "typed-key", "", False),
            [call(1)],
            id="edited-typed-key-wins",
        ),
    ],
)
def test_models(
    connection_id: int,
    kind: LlmKind,
    found: list[LlmConnection],
    exp_endpoint: LlmConnection,
    exp_found: list[object],
) -> None:
    tested = helper_instance()
    with (
        patch.object(LlmConnectionStore, "connection", side_effect=found) as mock_connection,
        patch.object(LlmGateway, "models", side_effect=[["fast", "good"]]) as mock_models,
    ):
        result = tested.models(connection_id, kind, " https://llm.example.com/v1/ ", " typed-key ")
    expected = ["fast", "good"]
    assert result == expected
    assert mock_connection.mock_calls == exp_found
    exp_calls = [call(exp_endpoint)]
    assert mock_models.mock_calls == exp_calls


def test_models__the_stored_key_when_none_is_typed() -> None:
    tested = helper_instance()
    with (
        patch.object(LlmConnectionStore, "connection", side_effect=[helper_local(1, "stored-key")]) as mock_connection,
        patch.object(LlmGateway, "models", side_effect=[["local-model"]]) as mock_models,
    ):
        result = tested.models(1, LlmKind.OPENAI, "https://llm.example.com/v1", "")
    expected = ["local-model"]
    assert result == expected
    exp_calls = [call(1)]
    assert mock_connection.mock_calls == exp_calls
    exp_calls = [call(LlmConnection(1, "", LlmKind.OPENAI, "https://llm.example.com/v1", "stored-key", "", False))]
    assert mock_models.mock_calls == exp_calls


def test_models__a_claude_key_is_never_sent_to_a_typed_address() -> None:
    tested = helper_instance()
    claude = LlmConnection(2, "Claude", LlmKind.CLAUDE, "", "sk-ant-key", "b", True)
    with (
        patch.object(LlmConnectionStore, "connection", side_effect=[claude]) as mock_connection,
        patch.object(LlmGateway, "models", side_effect=[["other"]]) as mock_models,
    ):
        result = tested.models(2, LlmKind.OPENAI, "https://elsewhere.example.com/v1", "")
    expected = ["other"]
    assert result == expected
    exp_calls = [call(2)]
    assert mock_connection.mock_calls == exp_calls
    exp_calls = [call(LlmConnection(2, "", LlmKind.OPENAI, "https://elsewhere.example.com/v1", "", "", False))]
    assert mock_models.mock_calls == exp_calls


def test_models__refused_before_any_call() -> None:
    tested = helper_instance()
    with (
        patch.object(LlmGateway, "models", side_effect=[]) as mock_models,
        pytest.raises(AppException) as exc_info,
    ):
        tested.models(0, LlmKind.CLAUDE, "", " ")
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (400, "A Claude connection needs an API key.")
    assert result == expected
    exp_calls = []
    assert mock_models.mock_calls == exp_calls


def test_existing() -> None:
    tested = helper_instance()
    with patch.object(LlmConnectionStore, "connection", side_effect=[helper_local(2, "k")]) as mock_connection:
        result = tested.existing(2)
    expected = helper_local(2, "k")
    assert result == expected
    exp_calls = [call(2)]
    assert mock_connection.mock_calls == exp_calls


@pytest.mark.parametrize(
    "connection, stored_key, expected",
    [
        pytest.param(
            LlmConnection(0, "  Local ", LlmKind.OPENAI, " http://192.0.2.7:8000/v1/ ", "", " local-model ", True),
            "",
            LlmConnection(0, "Local", LlmKind.OPENAI, "http://192.0.2.7:8000/v1", "", "local-model", True),
            id="local-without-key-trimmed",
        ),
        pytest.param(
            LlmConnection(0, "Claude", LlmKind.CLAUDE, "https://ignored", "", "claude-opus-5-5", True),
            "sk-stored",
            LlmConnection(0, "Claude", LlmKind.CLAUDE, "", "sk-stored", "claude-opus-5-5", True),
            id="claude-no-address-key-kept",
        ),
    ],
)
def test_checked(connection: LlmConnection, stored_key: str, expected: LlmConnection) -> None:
    tested = LlmConnectionCommand
    result = tested.checked(connection, stored_key)
    assert result == expected


@pytest.mark.parametrize(
    "connection, expected",
    [
        pytest.param(
            LlmConnection(0, "  ", LlmKind.CLAUDE, "", "k", "b", True),
            "Give the connection a name, of at most 80 characters.",
            id="no-name",
        ),
        pytest.param(
            LlmConnection(0, "x" * 81, LlmKind.CLAUDE, "", "k", "b", True),
            "Give the connection a name, of at most 80 characters.",
            id="long-name",
        ),
        pytest.param(
            LlmConnection(0, "C", LlmKind.CLAUDE, "", "k", " ", True),
            "Name the model that trades.",
            id="no-model",
        ),
        pytest.param(
            LlmConnection(0, "C", LlmKind.CLAUDE, "", " ", "b", True),
            "A Claude connection needs an API key.",
            id="claude-without-key",
        ),
        pytest.param(
            LlmConnection(0, "D", LlmKind.OPENAI, "ftp://llm/v1", "", "b", True),
            "An OpenAI-compatible connection needs an http:// or https:// address with a host.",
            id="not-http",
        ),
        pytest.param(
            LlmConnection(0, "D", LlmKind.OPENAI, "https:///v1", "", "b", True),
            "An OpenAI-compatible connection needs an http:// or https:// address with a host.",
            id="no-host",
        ),
    ],
)
def test_checked__refused(connection: LlmConnection, expected: str) -> None:
    tested = LlmConnectionCommand
    with pytest.raises(AppException) as exc_info:
        tested.checked(connection, "")
    result = (exc_info.value.status_code, exc_info.value.message)
    exp_error = (400, expected)
    assert result == exp_error


@pytest.mark.parametrize(
    "connection, stored_key, expected",
    [
        pytest.param(
            LlmConnection(0, "", LlmKind.OPENAI, " http://192.0.2.7:8000/v1/ ", " ", "", False),
            "",
            LlmConnection(0, "", LlmKind.OPENAI, "http://192.0.2.7:8000/v1", "", "", False),
            id="local-without-key",
        ),
        pytest.param(
            LlmConnection(0, " C ", LlmKind.CLAUDE, "https://ignored", "", "b", True),
            "sk-stored",
            LlmConnection(0, " C ", LlmKind.CLAUDE, "", "sk-stored", "b", True),
            id="claude-name-and-model-untouched",
        ),
    ],
)
def test_endpoint_checked(connection: LlmConnection, stored_key: str, expected: LlmConnection) -> None:
    tested = LlmConnectionCommand
    result = tested.endpoint_checked(connection, stored_key)
    assert result == expected


@pytest.mark.parametrize(
    "connection, exp_message",
    [
        pytest.param(
            LlmConnection(0, "", LlmKind.CLAUDE, "", "", "", True),
            "A Claude connection needs an API key.",
            id="claude-without-key",
        ),
        pytest.param(
            LlmConnection(0, "", LlmKind.OPENAI, "llm.example.com/v1", "k", "", True),
            "An OpenAI-compatible connection needs an http:// or https:// address with a host.",
            id="no-scheme",
        ),
    ],
)
def test_endpoint_checked__refused(connection: LlmConnection, exp_message: str) -> None:
    tested = LlmConnectionCommand
    with pytest.raises(AppException) as exc_info:
        tested.endpoint_checked(connection, "")
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (400, exp_message)
    assert result == expected


@pytest.mark.parametrize(
    "kind, expected",
    [
        pytest.param(LlmKind.OPENAI, "stored-key", id="same-kind"),
        pytest.param(LlmKind.CLAUDE, "", id="kind-changed"),
    ],
)
def test_kept_key(kind: LlmKind, expected: str) -> None:
    tested = LlmConnectionCommand
    result = tested.kept_key(helper_local(1, "stored-key"), kind)
    assert result == expected
