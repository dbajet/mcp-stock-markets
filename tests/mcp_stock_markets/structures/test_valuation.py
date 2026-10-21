from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from mcp_stock_markets.structures.valuation import Valuation
from tests.conftest import is_namedtuple


def helper_instance() -> Valuation:
    return Valuation(
        taken_at=datetime(2026, 10, 21, 15, 0, 0, tzinfo=UTC),
        cash=Decimal("125.14"),
        holdings_value=Decimal("380.00"),
        total_value=Decimal("505.14"),
    )


def helper_json() -> dict[str, Any]:
    return {
        "taken_at": "2026-10-21T15:00:00+00:00",
        "cash": "125.14",
        "holdings_value": "380.00",
        "total_value": "505.14",
    }


def test_class() -> None:
    tested = Valuation
    fields = {
        "taken_at": "datetime",
        "cash": "Decimal",
        "holdings_value": "Decimal",
        "total_value": "Decimal",
    }
    assert is_namedtuple(tested, fields)


def test_to_dict() -> None:
    tested = helper_instance()
    result = tested.to_dict()
    expected = {
        "taken_at": "2026-10-21T15:00:00+00:00",
        "cash": "125.14",
        "holdings_value": "380.00",
        "total_value": "505.14",
    }
    assert result == expected


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(
            {
                "taken_at": datetime(2026, 10, 21, 15, 0, 0, tzinfo=UTC),
                "cash": Decimal("125.14"),
                "holdings_value": Decimal("380.00"),
                "total_value": Decimal("505.14"),
            },
            id="database-row",
        ),
        pytest.param(helper_json(), id="json-form"),
    ],
)
def test_from_dict(data: dict[str, Any]) -> None:
    tested = Valuation
    result = tested.from_dict(data)
    expected = Valuation(
        taken_at=datetime(2026, 10, 21, 15, 0, 0, tzinfo=UTC),
        cash=Decimal("125.14"),
        holdings_value=Decimal("380.00"),
        total_value=Decimal("505.14"),
    )
    assert result == expected


@pytest.mark.parametrize(
    "field",
    [
        pytest.param("taken_at", id="taken_at"),
        pytest.param("cash", id="cash"),
        pytest.param("holdings_value", id="holdings_value"),
        pytest.param("total_value", id="total_value"),
    ],
)
def test_from_dict__a_missing_field_raises(field: str) -> None:
    tested = Valuation
    data = {key: value for key, value in helper_json().items() if key != field}
    with pytest.raises(KeyError) as exc_info:
        tested.from_dict(data)
    expected = (field,)
    assert exc_info.value.args == expected
