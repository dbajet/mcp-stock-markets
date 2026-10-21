from __future__ import annotations

from typing import Any

import pytest

from mcp_stock_markets.structures.agent_reply import AgentReply
from mcp_stock_markets.structures.tool_call import ToolCall
from tests.conftest import is_namedtuple


def helper_instance() -> AgentReply:
    return AgentReply(
        text="Let me check the price.",
        reasoning="The portfolio holds cash.",
        tool_calls=(
            ToolCall(call_id="toolu_01", name="quotes__get_quote", arguments={"symbol": "AAPL"}),
            ToolCall(call_id="toolu_02", name="broker__get_portfolio", arguments=None),
        ),
        model="claude-opus-5-5",
        raw=(
            {"type": "thinking", "thinking": "The portfolio holds cash.", "signature": "sig"},
            {"type": "text", "text": "Let me check the price."},
        ),
    )


def helper_json() -> dict[str, Any]:
    return {
        "text": "Let me check the price.",
        "reasoning": "The portfolio holds cash.",
        "tool_calls": [
            {"call_id": "toolu_01", "name": "quotes__get_quote", "arguments": {"symbol": "AAPL"}},
            {"call_id": "toolu_02", "name": "broker__get_portfolio", "arguments": None},
        ],
        "model": "claude-opus-5-5",
        "raw": [
            {"type": "thinking", "thinking": "The portfolio holds cash.", "signature": "sig"},
            {"type": "text", "text": "Let me check the price."},
        ],
    }


def test_class() -> None:
    tested = AgentReply
    fields = {
        "text": "str",
        "reasoning": "str",
        "tool_calls": "tuple[ToolCall, ...]",
        "model": "str",
        "raw": "tuple[dict[str, Any], ...]",
    }
    assert is_namedtuple(tested, fields)


def test_to_dict() -> None:
    tested = helper_instance()
    result = tested.to_dict()
    expected = {
        "text": "Let me check the price.",
        "reasoning": "The portfolio holds cash.",
        "tool_calls": [
            {"call_id": "toolu_01", "name": "quotes__get_quote", "arguments": {"symbol": "AAPL"}},
            {"call_id": "toolu_02", "name": "broker__get_portfolio", "arguments": None},
        ],
        "model": "claude-opus-5-5",
        "raw": [
            {"type": "thinking", "thinking": "The portfolio holds cash.", "signature": "sig"},
            {"type": "text", "text": "Let me check the price."},
        ],
    }
    assert result == expected


def test_from_dict() -> None:
    tested = AgentReply
    result = tested.from_dict(helper_json())
    expected = AgentReply(
        text="Let me check the price.",
        reasoning="The portfolio holds cash.",
        tool_calls=(
            ToolCall(call_id="toolu_01", name="quotes__get_quote", arguments={"symbol": "AAPL"}),
            ToolCall(call_id="toolu_02", name="broker__get_portfolio", arguments=None),
        ),
        model="claude-opus-5-5",
        raw=(
            {"type": "thinking", "thinking": "The portfolio holds cash.", "signature": "sig"},
            {"type": "text", "text": "Let me check the price."},
        ),
    )
    assert result == expected


@pytest.mark.parametrize(
    "field",
    [
        pytest.param("text", id="text"),
        pytest.param("reasoning", id="reasoning"),
        pytest.param("tool_calls", id="tool_calls"),
        pytest.param("model", id="model"),
        pytest.param("raw", id="raw"),
    ],
)
def test_from_dict__a_missing_field_raises(field: str) -> None:
    tested = AgentReply
    data = {key: value for key, value in helper_json().items() if key != field}
    with pytest.raises(KeyError) as exc_info:
        tested.from_dict(data)
    expected = (field,)
    assert exc_info.value.args == expected
