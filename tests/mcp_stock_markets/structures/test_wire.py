from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest

from mcp_stock_markets.structures.wire import Wire


@pytest.mark.parametrize(
    "value, expected",
    [
        pytest.param(Decimal("187.4321"), Decimal("187.4321"), id="decimal"),
        pytest.param("187.4321", Decimal("187.4321"), id="exact-string"),
        pytest.param(500, Decimal("500"), id="integer"),
    ],
)
def test_money(value: Any, expected: Decimal) -> None:
    tested = Wire
    result = tested.money(value)
    assert result == expected


def test_money__a_float_is_refused() -> None:
    tested = Wire
    with pytest.raises(TypeError) as exc_info:
        tested.money(187.43)
    expected = "money never travels as a float"
    assert str(exc_info.value) == expected


@pytest.mark.parametrize(
    "value, expected",
    [
        pytest.param(
            datetime(2026, 10, 21, 14, 30, 5, tzinfo=UTC),
            datetime(2026, 10, 21, 14, 30, 5, tzinfo=UTC),
            id="datetime",
        ),
        pytest.param(
            "2026-10-21T14:30:05+00:00",
            datetime(2026, 10, 21, 14, 30, 5, tzinfo=UTC),
            id="iso-utc",
        ),
        pytest.param(
            "2026-10-21T10:30:05-04:00",
            datetime(2026, 10, 21, 10, 30, 5, tzinfo=timezone(timedelta(hours=-4))),
            id="iso-offset",
        ),
    ],
)
def test_moment(value: Any, expected: datetime) -> None:
    tested = Wire
    result = tested.moment(value)
    assert result == expected
    exp_offset = expected.utcoffset()
    assert result.utcoffset() == exp_offset


@pytest.mark.parametrize(
    "value, expected",
    [
        pytest.param(date(2026, 10, 21), date(2026, 10, 21), id="date"),
        pytest.param("2026-10-21", date(2026, 10, 21), id="iso"),
    ],
)
def test_day(value: Any, expected: date) -> None:
    tested = Wire
    result = tested.day(value)
    assert result == expected
