from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from mcp_stock_markets.structures.daily_bar import DailyBar
from tests.conftest import is_namedtuple


def helper_instance() -> DailyBar:
    return DailyBar(
        symbol="MSFT",
        day=date(2026, 10, 20),
        open=Decimal("410.1000"),
        high=Decimal("415.2500"),
        low=Decimal("408.0050"),
        close=Decimal("414.9900"),
        volume=21_345_678,
    )


def helper_row() -> dict[str, Any]:
    return {
        "symbol": "MSFT",
        "day": date(2026, 10, 20),
        "open": Decimal("410.1000"),
        "high": Decimal("415.2500"),
        "low": Decimal("408.0050"),
        "close": Decimal("414.9900"),
        "volume": 21_345_678,
    }


def helper_json() -> dict[str, Any]:
    return {
        "symbol": "MSFT",
        "day": "2026-10-20",
        "open": "410.1000",
        "high": "415.2500",
        "low": "408.0050",
        "close": "414.9900",
        "volume": 21_345_678,
    }


def test_class() -> None:
    tested = DailyBar
    fields = {
        "symbol": "str",
        "day": "date",
        "open": "Decimal",
        "high": "Decimal",
        "low": "Decimal",
        "close": "Decimal",
        "volume": "int",
    }
    assert is_namedtuple(tested, fields)


def test_to_dict() -> None:
    tested = helper_instance()
    result = tested.to_dict()
    expected = {
        "symbol": "MSFT",
        "day": "2026-10-20",
        "open": "410.1000",
        "high": "415.2500",
        "low": "408.0050",
        "close": "414.9900",
        "volume": 21_345_678,
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
    tested = DailyBar
    result = tested.from_dict(data)
    expected = DailyBar(
        symbol="MSFT",
        day=date(2026, 10, 20),
        open=Decimal("410.1000"),
        high=Decimal("415.2500"),
        low=Decimal("408.0050"),
        close=Decimal("414.9900"),
        volume=21_345_678,
    )
    assert result == expected


@pytest.mark.parametrize(
    "field",
    [
        pytest.param("symbol", id="symbol"),
        pytest.param("day", id="day"),
        pytest.param("open", id="open"),
        pytest.param("high", id="high"),
        pytest.param("low", id="low"),
        pytest.param("close", id="close"),
        pytest.param("volume", id="volume"),
    ],
)
def test_from_dict__a_missing_field_raises(field: str) -> None:
    tested = DailyBar
    data = {key: value for key, value in helper_json().items() if key != field}
    with pytest.raises(KeyError) as exc_info:
        tested.from_dict(data)
    expected = (field,)
    assert exc_info.value.args == expected
