from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from mcp_stock_markets.structures.portfolio import Portfolio
from tests.conftest import is_namedtuple


def helper_instance() -> Portfolio:
    return Portfolio(
        portfolio_id=3,
        user_id=7,
        starting_budget=Decimal("500.00"),
        cash=Decimal("123.45"),
        created_at=datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC),
    )


def helper_row() -> dict[str, Any]:
    return {
        "portfolio_id": 3,
        "user_id": 7,
        "starting_budget": Decimal("500.00"),
        "cash": Decimal("123.45"),
        "created_at": datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC),
    }


def helper_json() -> dict[str, Any]:
    return {
        "portfolio_id": 3,
        "user_id": 7,
        "starting_budget": "500.00",
        "cash": "123.45",
        "created_at": "2026-10-01T09:00:00+00:00",
    }


def test_class() -> None:
    tested = Portfolio
    fields = {
        "portfolio_id": "int",
        "user_id": "int",
        "starting_budget": "Decimal",
        "cash": "Decimal",
        "created_at": "datetime",
    }
    assert is_namedtuple(tested, fields)


def test_to_dict() -> None:
    tested = helper_instance()
    result = tested.to_dict()
    expected = {
        "portfolio_id": 3,
        "user_id": 7,
        "starting_budget": "500.00",
        "cash": "123.45",
        "created_at": "2026-10-01T09:00:00+00:00",
    }
    assert result == expected


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(helper_row(), id="database-row"),
        pytest.param(helper_json(), id="json-form"),
    ],
)
def test_from_dict(data: dict[str, Any]) -> None:
    tested = Portfolio
    result = tested.from_dict(data)
    expected = Portfolio(
        portfolio_id=3,
        user_id=7,
        starting_budget=Decimal("500.00"),
        cash=Decimal("123.45"),
        created_at=datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC),
    )
    assert result == expected


@pytest.mark.parametrize(
    "field",
    [
        pytest.param("portfolio_id", id="portfolio_id"),
        pytest.param("user_id", id="user_id"),
        pytest.param("starting_budget", id="starting_budget"),
        pytest.param("cash", id="cash"),
        pytest.param("created_at", id="created_at"),
    ],
)
def test_from_dict__a_missing_field_raises(field: str) -> None:
    tested = Portfolio
    data = {key: value for key, value in helper_json().items() if key != field}
    with pytest.raises(KeyError) as exc_info:
        tested.from_dict(data)
    expected = (field,)
    assert exc_info.value.args == expected
