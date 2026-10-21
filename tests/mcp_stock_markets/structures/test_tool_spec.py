from __future__ import annotations

import pytest

from mcp_stock_markets.constants.mcp_server_name import McpServerName
from mcp_stock_markets.structures.tool_spec import ToolSpec
from tests.conftest import is_namedtuple


def helper_instance(server: McpServerName) -> ToolSpec:
    return ToolSpec(
        server=server,
        name="get_quote",
        description="The latest price of a stock.",
        input_schema={"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
    )


def test_class() -> None:
    tested = ToolSpec
    fields = {
        "server": "McpServerName",
        "name": "str",
        "description": "str",
        "input_schema": "dict[str, Any]",
    }
    assert is_namedtuple(tested, fields)


@pytest.mark.parametrize(
    "server, expected",
    [
        pytest.param(McpServerName.SP500, "sp500__get_quote", id="sp500"),
        pytest.param(McpServerName.QUOTES, "quotes__get_quote", id="quotes"),
        pytest.param(McpServerName.BROKER, "broker__get_quote", id="broker"),
    ],
)
def test_qualified_name(server: McpServerName, expected: str) -> None:
    tested = helper_instance(server)
    result = tested.qualified_name()
    assert result == expected


def test_to_dict() -> None:
    tested = helper_instance(McpServerName.QUOTES)
    result = tested.to_dict()
    expected = {
        "server": "quotes",
        "name": "get_quote",
        "description": "The latest price of a stock.",
        "input_schema": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
    }
    assert result == expected


def test_from_dict() -> None:
    tested = ToolSpec
    result = tested.from_dict(
        {
            "server": "quotes",
            "name": "get_quote",
            "description": "The latest price of a stock.",
            "input_schema": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
        }
    )
    expected = ToolSpec(
        server=McpServerName.QUOTES,
        name="get_quote",
        description="The latest price of a stock.",
        input_schema={"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
    )
    assert result == expected


@pytest.mark.parametrize(
    "field",
    [
        pytest.param("server", id="server"),
        pytest.param("name", id="name"),
        pytest.param("description", id="description"),
        pytest.param("input_schema", id="input_schema"),
    ],
)
def test_from_dict__a_missing_field_raises(field: str) -> None:
    tested = ToolSpec
    complete = {
        "server": "quotes",
        "name": "get_quote",
        "description": "The latest price of a stock.",
        "input_schema": {"type": "object"},
    }
    data = {key: value for key, value in complete.items() if key != field}
    with pytest.raises(KeyError) as exc_info:
        tested.from_dict(data)
    expected = (field,)
    assert exc_info.value.args == expected
