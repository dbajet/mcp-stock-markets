from __future__ import annotations

import pytest

from mcp_stock_markets.structures.tool_result import ToolResult
from tests.conftest import is_namedtuple


def test_class() -> None:
    tested = ToolResult
    fields = {"call_id": "str", "content": "str", "is_error": "bool"}
    assert is_namedtuple(tested, fields)


def test_to_dict() -> None:
    tested = ToolResult(call_id="toolu_01", content='{"price": "187.43"}', is_error=False)
    result = tested.to_dict()
    expected = {"call_id": "toolu_01", "content": '{"price": "187.43"}', "is_error": False}
    assert result == expected


def test_from_dict() -> None:
    tested = ToolResult
    result = tested.from_dict({"call_id": "toolu_01", "content": "The market is closed.", "is_error": True})
    expected = ToolResult(call_id="toolu_01", content="The market is closed.", is_error=True)
    assert result == expected


@pytest.mark.parametrize(
    "field",
    [
        pytest.param("call_id", id="call_id"),
        pytest.param("content", id="content"),
        pytest.param("is_error", id="is_error"),
    ],
)
def test_from_dict__a_missing_field_raises(field: str) -> None:
    tested = ToolResult
    complete = {"call_id": "toolu_01", "content": "The market is closed.", "is_error": True}
    data = {key: value for key, value in complete.items() if key != field}
    with pytest.raises(KeyError) as exc_info:
        tested.from_dict(data)
    expected = (field,)
    assert exc_info.value.args == expected
