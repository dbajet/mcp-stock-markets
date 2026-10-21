from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from mcp_stock_markets.structures.holding import Holding
from tests.conftest import is_namedtuple


def test_class() -> None:
    tested = Holding
    fields = {"symbol": "str", "quantity": "int", "cost": "Decimal"}
    assert is_namedtuple(tested, fields)


def test_to_dict() -> None:
    tested = Holding(symbol="AAPL", quantity=2, cost=Decimal("374.86"))
    result = tested.to_dict()
    expected = {"symbol": "AAPL", "quantity": 2, "cost": "374.86"}
    assert result == expected


@pytest.mark.parametrize(
    "data",
    [
        pytest.param({"symbol": "AAPL", "quantity": 2, "cost": Decimal("374.86")}, id="database-row"),
        pytest.param({"symbol": "AAPL", "quantity": 2, "cost": "374.86"}, id="json-form"),
    ],
)
def test_from_dict(data: dict[str, Any]) -> None:
    tested = Holding
    result = tested.from_dict(data)
    expected = Holding(symbol="AAPL", quantity=2, cost=Decimal("374.86"))
    assert result == expected


@pytest.mark.parametrize(
    "field",
    [
        pytest.param("symbol", id="symbol"),
        pytest.param("quantity", id="quantity"),
        pytest.param("cost", id="cost"),
    ],
)
def test_from_dict__a_missing_field_raises(field: str) -> None:
    tested = Holding
    complete = {"symbol": "AAPL", "quantity": 2, "cost": "374.86"}
    data = {key: value for key, value in complete.items() if key != field}
    with pytest.raises(KeyError) as exc_info:
        tested.from_dict(data)
    expected = (field,)
    assert exc_info.value.args == expected
