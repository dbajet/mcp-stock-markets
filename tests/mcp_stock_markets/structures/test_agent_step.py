from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from mcp_stock_markets.constants.step_kind import StepKind
from mcp_stock_markets.structures.agent_step import AgentStep
from tests.conftest import is_namedtuple


def helper_instance(arguments: dict[str, Any] | None) -> AgentStep:
    return AgentStep(
        step_id=21,
        run_id=5,
        position=3,
        kind=StepKind.TOOL,
        server="quotes",
        tool="get_quote",
        arguments=arguments,
        content='{"price": "187.43"}',
        is_error=False,
        elapsed_ms=412.5,
        created_at=datetime(2026, 10, 21, 14, 31, 0, tzinfo=UTC),
    )


def helper_json(arguments: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "step_id": 21,
        "run_id": 5,
        "position": 3,
        "kind": "tool",
        "server": "quotes",
        "tool": "get_quote",
        "arguments": arguments,
        "content": '{"price": "187.43"}',
        "is_error": False,
        "elapsed_ms": 412.5,
        "created_at": "2026-10-21T14:31:00+00:00",
    }


def test_class() -> None:
    tested = AgentStep
    fields = {
        "step_id": "int",
        "run_id": "int",
        "position": "int",
        "kind": "StepKind",
        "server": "str",
        "tool": "str",
        "arguments": "dict[str, Any] | None",
        "content": "str",
        "is_error": "bool",
        "elapsed_ms": "float",
        "created_at": "datetime",
    }
    assert is_namedtuple(tested, fields)


@pytest.mark.parametrize(
    "arguments, exp_arguments",
    [
        pytest.param({"symbol": "AAPL"}, {"symbol": "AAPL"}, id="arguments"),
        pytest.param(None, None, id="no-arguments"),
    ],
)
def test_to_dict(arguments: dict[str, Any] | None, exp_arguments: dict[str, Any] | None) -> None:
    tested = helper_instance(arguments)
    result = tested.to_dict()
    expected = {
        "step_id": 21,
        "run_id": 5,
        "position": 3,
        "kind": "tool",
        "server": "quotes",
        "tool": "get_quote",
        "arguments": exp_arguments,
        "content": '{"price": "187.43"}',
        "is_error": False,
        "elapsed_ms": 412.5,
        "created_at": "2026-10-21T14:31:00+00:00",
    }
    assert result == expected


@pytest.mark.parametrize(
    "data, exp_arguments",
    [
        pytest.param(
            {
                "step_id": 21,
                "run_id": 5,
                "position": 3,
                "kind": "tool",
                "server": "quotes",
                "tool": "get_quote",
                "arguments": {"symbol": "AAPL"},
                "content": '{"price": "187.43"}',
                "is_error": False,
                "elapsed_ms": 412.5,
                "created_at": datetime(2026, 10, 21, 14, 31, 0, tzinfo=UTC),
            },
            {"symbol": "AAPL"},
            id="database-row",
        ),
        pytest.param(helper_json({"symbol": "AAPL"}), {"symbol": "AAPL"}, id="json-form"),
        pytest.param(helper_json(None), None, id="json-no-arguments"),
    ],
)
def test_from_dict(data: dict[str, Any], exp_arguments: dict[str, Any] | None) -> None:
    tested = AgentStep
    result = tested.from_dict(data)
    expected = AgentStep(
        step_id=21,
        run_id=5,
        position=3,
        kind=StepKind.TOOL,
        server="quotes",
        tool="get_quote",
        arguments=exp_arguments,
        content='{"price": "187.43"}',
        is_error=False,
        elapsed_ms=412.5,
        created_at=datetime(2026, 10, 21, 14, 31, 0, tzinfo=UTC),
    )
    assert result == expected


@pytest.mark.parametrize(
    "field",
    [
        pytest.param("step_id", id="step_id"),
        pytest.param("run_id", id="run_id"),
        pytest.param("position", id="position"),
        pytest.param("kind", id="kind"),
        pytest.param("server", id="server"),
        pytest.param("tool", id="tool"),
        pytest.param("arguments", id="arguments"),
        pytest.param("content", id="content"),
        pytest.param("is_error", id="is_error"),
        pytest.param("elapsed_ms", id="elapsed_ms"),
        pytest.param("created_at", id="created_at"),
    ],
)
def test_from_dict__a_missing_field_raises(field: str) -> None:
    tested = AgentStep
    data = {key: value for key, value in helper_json(None).items() if key != field}
    with pytest.raises(KeyError) as exc_info:
        tested.from_dict(data)
    expected = (field,)
    assert exc_info.value.args == expected
