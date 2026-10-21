from __future__ import annotations

from typing import Any

import pytest

from mcp_stock_markets.structures.tool_call import ToolCall
from tests.conftest import is_namedtuple


def test_class() -> None:
    tested = ToolCall
    fields = {"call_id": "str", "name": "str", "arguments": "dict[str, Any] | None"}
    assert is_namedtuple(tested, fields)


@pytest.mark.parametrize(
    "arguments, expected",
    [
        pytest.param(
            {"symbol": "AAPL"},
            {"call_id": "toolu_01", "name": "quotes__get_quote", "arguments": {"symbol": "AAPL"}},
            id="arguments",
        ),
        pytest.param(
            None,
            {"call_id": "toolu_01", "name": "quotes__get_quote", "arguments": None},
            id="malformed-arguments",
        ),
    ],
)
def test_to_dict(arguments: dict[str, Any] | None, expected: dict[str, Any]) -> None:
    tested = ToolCall(call_id="toolu_01", name="quotes__get_quote", arguments=arguments)
    result = tested.to_dict()
    assert result == expected


@pytest.mark.parametrize(
    "data, expected",
    [
        pytest.param(
            {"call_id": "toolu_01", "name": "quotes__get_quote", "arguments": {"symbol": "AAPL"}},
            ToolCall(call_id="toolu_01", name="quotes__get_quote", arguments={"symbol": "AAPL"}),
            id="arguments",
        ),
        pytest.param(
            {"call_id": "toolu_01", "name": "quotes__get_quote", "arguments": None},
            ToolCall(call_id="toolu_01", name="quotes__get_quote", arguments=None),
            id="malformed-arguments",
        ),
    ],
)
def test_from_dict(data: dict[str, Any], expected: ToolCall) -> None:
    tested = ToolCall
    result = tested.from_dict(data)
    assert result == expected


@pytest.mark.parametrize(
    "field",
    [
        pytest.param("call_id", id="call_id"),
        pytest.param("name", id="name"),
        pytest.param("arguments", id="arguments"),
    ],
)
def test_from_dict__a_missing_field_raises(field: str) -> None:
    tested = ToolCall
    complete = {"call_id": "toolu_01", "name": "quotes__get_quote", "arguments": None}
    data = {key: value for key, value in complete.items() if key != field}
    with pytest.raises(KeyError) as exc_info:
        tested.from_dict(data)
    expected = (field,)
    assert exc_info.value.args == expected
