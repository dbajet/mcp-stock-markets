from __future__ import annotations

from typing import Any

import pytest

from mcp_stock_markets.structures.agent_exchange import AgentExchange
from mcp_stock_markets.structures.agent_reply import AgentReply
from mcp_stock_markets.structures.tool_call import ToolCall
from mcp_stock_markets.structures.tool_result import ToolResult
from tests.conftest import is_namedtuple


def helper_instance() -> AgentExchange:
    return AgentExchange(
        reply=AgentReply(
            text="Let me check the price.",
            reasoning="",
            tool_calls=(ToolCall(call_id="toolu_01", name="quotes__get_quote", arguments={"symbol": "AAPL"}),),
            model="claude-opus-5-5",
            raw=({"type": "text", "text": "Let me check the price."},),
        ),
        results=(
            ToolResult(call_id="toolu_01", content='{"price": "187.43"}', is_error=False),
            ToolResult(call_id="toolu_02", content="Unknown symbol.", is_error=True),
        ),
    )


def helper_json() -> dict[str, Any]:
    return {
        "reply": {
            "text": "Let me check the price.",
            "reasoning": "",
            "tool_calls": [{"call_id": "toolu_01", "name": "quotes__get_quote", "arguments": {"symbol": "AAPL"}}],
            "model": "claude-opus-5-5",
            "raw": [{"type": "text", "text": "Let me check the price."}],
        },
        "results": [
            {"call_id": "toolu_01", "content": '{"price": "187.43"}', "is_error": False},
            {"call_id": "toolu_02", "content": "Unknown symbol.", "is_error": True},
        ],
    }


def test_class() -> None:
    tested = AgentExchange
    fields = {"reply": "AgentReply", "results": "tuple[ToolResult, ...]"}
    assert is_namedtuple(tested, fields)


def test_to_dict() -> None:
    tested = helper_instance()
    result = tested.to_dict()
    expected = {
        "reply": {
            "text": "Let me check the price.",
            "reasoning": "",
            "tool_calls": [{"call_id": "toolu_01", "name": "quotes__get_quote", "arguments": {"symbol": "AAPL"}}],
            "model": "claude-opus-5-5",
            "raw": [{"type": "text", "text": "Let me check the price."}],
        },
        "results": [
            {"call_id": "toolu_01", "content": '{"price": "187.43"}', "is_error": False},
            {"call_id": "toolu_02", "content": "Unknown symbol.", "is_error": True},
        ],
    }
    assert result == expected


def test_from_dict() -> None:
    tested = AgentExchange
    result = tested.from_dict(helper_json())
    expected = helper_instance()
    assert result == expected


@pytest.mark.parametrize(
    "field",
    [
        pytest.param("reply", id="reply"),
        pytest.param("results", id="results"),
    ],
)
def test_from_dict__a_missing_field_raises(field: str) -> None:
    tested = AgentExchange
    data = {key: value for key, value in helper_json().items() if key != field}
    with pytest.raises(KeyError) as exc_info:
        tested.from_dict(data)
    expected = (field,)
    assert exc_info.value.args == expected
