from __future__ import annotations

import pytest

from mcp_stock_markets.structures.llm_routing import LlmRouting
from tests.conftest import is_namedtuple


def test_class() -> None:
    tested = LlmRouting
    fields = {"agent": "int | None"}
    assert is_namedtuple(tested, fields)


def test_to_dict() -> None:
    tested = LlmRouting(agent=1)
    result = tested.to_dict()
    expected = {"agent": 1}
    assert result == expected


@pytest.mark.parametrize(
    "data, expected",
    [
        pytest.param({"agent": "2"}, LlmRouting(2), id="chosen"),
        pytest.param({"agent": None}, LlmRouting(None), id="none"),
    ],
)
def test_from_dict(data: dict[str, object], expected: LlmRouting) -> None:
    tested = LlmRouting
    result = tested.from_dict(data)
    assert result == expected
