from __future__ import annotations

from unittest.mock import call, patch

import pytest

from mcp_stock_markets.constants.llm_kind import LlmKind
from mcp_stock_markets.constants.mcp_server_name import McpServerName
from mcp_stock_markets.libraries.claude_box import ClaudeBox
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.libraries.llm_connection_store import LlmConnectionStore
from mcp_stock_markets.libraries.llm_gateway import LlmGateway
from mcp_stock_markets.libraries.openai_chat_box import OpenAiChatBox
from mcp_stock_markets.libraries.secret_sealer import SecretSealer
from mcp_stock_markets.structures.agent_exchange import AgentExchange
from mcp_stock_markets.structures.agent_reply import AgentReply
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.connection_health import ConnectionHealth
from mcp_stock_markets.structures.llm_connection import LlmConnection
from mcp_stock_markets.structures.llm_routing import LlmRouting
from mcp_stock_markets.structures.tool_call import ToolCall
from mcp_stock_markets.structures.tool_result import ToolResult
from mcp_stock_markets.structures.tool_spec import ToolSpec

KEY = "Zm9yLXRlc3RzLW9ubHktZm9yLXRlc3RzLW9ubHktMzI="


def helper_instance() -> LlmGateway:
    return LlmGateway(
        LlmConnectionStore(Database("postgresql://u:p@h/d"), SecretSealer(KEY)), OpenAiChatBox(), ClaudeBox()
    )


def helper_connection(connection_id: int, kind: LlmKind) -> LlmConnection:
    return LlmConnection(connection_id, f"c{connection_id}", kind, "", "k", "good", True)


def test___init__() -> None:
    store = LlmConnectionStore(Database("postgresql://u:p@h/d"), SecretSealer(KEY))
    openai_box = OpenAiChatBox()
    claude_box = ClaudeBox()
    tested = LlmGateway(store, openai_box, claude_box)
    result = (tested._store, tested._openai_box, tested._claude_box)
    expected = (store, openai_box, claude_box)
    assert result == expected


def helper_reply() -> AgentReply:
    return AgentReply(
        text="Bought.",
        reasoning="",
        tool_calls=(ToolCall("c1", "broker__buy", {"symbol": "AAPL"}),),
        model="good",
        raw=({"type": "text", "text": "Bought."},),
    )


def helper_exchanges() -> list[AgentExchange]:
    return [AgentExchange(reply=helper_reply(), results=(ToolResult("c1", "Bought 1 AAPL.", False),))]


def helper_tools() -> list[ToolSpec]:
    return [ToolSpec(McpServerName.BROKER, "buy", "Buy whole shares.", {"type": "object"})]


def test_agent_connection() -> None:
    tested = helper_instance()
    with (
        patch.object(LlmConnectionStore, "routing", side_effect=[LlmRouting(4)]) as mock_routing,
        patch.object(
            LlmConnectionStore, "connection", side_effect=[helper_connection(4, LlmKind.OPENAI)]
        ) as mock_connection,
    ):
        result = tested.agent_connection()
    expected = helper_connection(4, LlmKind.OPENAI)
    assert result == expected
    exp_calls = [call()]
    assert mock_routing.mock_calls == exp_calls
    exp_calls = [call(4)]
    assert mock_connection.mock_calls == exp_calls


@pytest.mark.parametrize(
    "routing, found, exp_calls",
    [
        pytest.param(LlmRouting(None), [], [], id="none-chosen"),
        pytest.param(LlmRouting(9), [None], [call(9)], id="deleted-meanwhile"),
    ],
)
def test_agent_connection__none(routing: LlmRouting, found: list[None], exp_calls: list[object]) -> None:
    tested = helper_instance()
    with (
        patch.object(LlmConnectionStore, "routing", side_effect=[routing]) as mock_routing,
        patch.object(LlmConnectionStore, "connection", side_effect=found) as mock_connection,
        pytest.raises(AppException) as exc_info,
    ):
        tested.agent_connection()
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (503, "The agent needs a language model: choose one in Settings › Language models.")
    assert result == expected
    exp_routing = [call()]
    assert mock_routing.mock_calls == exp_routing
    assert mock_connection.mock_calls == exp_calls


def test_agent_reply__claude() -> None:
    tested = helper_instance()
    with (
        patch.object(ClaudeBox, "agent_reply", side_effect=[helper_reply()]) as mock_claude,
        patch.object(OpenAiChatBox, "agent_reply", side_effect=[]) as mock_openai,
    ):
        result = tested.agent_reply(
            helper_connection(2, LlmKind.CLAUDE), "Trade.", "Run.", helper_exchanges(), helper_tools()
        )
    expected = helper_reply()
    assert result == expected
    exp_calls = [
        call(
            helper_connection(2, LlmKind.CLAUDE),
            "Trade.",
            "Run.",
            helper_exchanges(),
            helper_tools(),
            16000,
            "medium",
            180.0,
        )
    ]
    assert mock_claude.mock_calls == exp_calls
    exp_none: list[object] = []
    assert mock_openai.mock_calls == exp_none


def test_agent_reply__openai() -> None:
    tested = helper_instance()
    with (
        patch.object(ClaudeBox, "agent_reply", side_effect=[]) as mock_claude,
        patch.object(OpenAiChatBox, "agent_reply", side_effect=[helper_reply()]) as mock_openai,
    ):
        result = tested.agent_reply(
            helper_connection(2, LlmKind.OPENAI), "Trade.", "Run.", helper_exchanges(), helper_tools()
        )
    expected = helper_reply()
    assert result == expected
    exp_calls = [
        call(helper_connection(2, LlmKind.OPENAI), "Trade.", "Run.", helper_exchanges(), helper_tools(), 4000, 180.0)
    ]
    assert mock_openai.mock_calls == exp_calls
    exp_none: list[object] = []
    assert mock_claude.mock_calls == exp_none


@pytest.mark.parametrize(
    "kind, box",
    [
        pytest.param(LlmKind.CLAUDE, ClaudeBox, id="claude"),
        pytest.param(LlmKind.OPENAI, OpenAiChatBox, id="openai"),
    ],
)
def test_health(kind: LlmKind, box: type[ClaudeBox] | type[OpenAiChatBox]) -> None:
    tested = helper_instance()
    light = ConnectionHealth(1, True, "Connected.", 10.0)
    with patch.object(box, "health", side_effect=[light]) as mock_health:
        result = tested.health(helper_connection(1, kind))
    expected = ConnectionHealth(1, True, "Connected.", 10.0)
    assert result == expected
    exp_calls = [call(helper_connection(1, kind), 8.0)]
    assert mock_health.mock_calls == exp_calls


@pytest.mark.parametrize(
    "kind, box",
    [
        pytest.param(LlmKind.CLAUDE, ClaudeBox, id="claude"),
        pytest.param(LlmKind.OPENAI, OpenAiChatBox, id="openai"),
    ],
)
def test_models(kind: LlmKind, box: type[ClaudeBox] | type[OpenAiChatBox]) -> None:
    tested = helper_instance()
    with patch.object(box, "models", side_effect=[["fast", "good"]]) as mock_models:
        result = tested.models(helper_connection(1, kind))
    expected = ["fast", "good"]
    assert result == expected
    exp_calls = [call(helper_connection(1, kind), 8.0)]
    assert mock_models.mock_calls == exp_calls
