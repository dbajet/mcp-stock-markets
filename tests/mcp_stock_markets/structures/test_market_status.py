from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from mcp_stock_markets.structures.market_status import MarketStatus
from tests.conftest import is_namedtuple


def helper_instance(closes_at: datetime | None) -> MarketStatus:
    return MarketStatus(
        is_open=closes_at is not None,
        now=datetime(2026, 10, 21, 14, 30, 0, tzinfo=UTC),
        closes_at=closes_at,
        next_open=datetime(2026, 10, 22, 13, 30, 0, tzinfo=UTC),
    )


def test_class() -> None:
    tested = MarketStatus
    fields = {
        "is_open": "bool",
        "now": "datetime",
        "closes_at": "datetime | None",
        "next_open": "datetime",
    }
    assert is_namedtuple(tested, fields)


@pytest.mark.parametrize(
    "closes_at, expected",
    [
        pytest.param(
            datetime(2026, 10, 21, 20, 0, 0, tzinfo=UTC),
            {
                "is_open": True,
                "now": "2026-10-21T14:30:00+00:00",
                "closes_at": "2026-10-21T20:00:00+00:00",
                "next_open": "2026-10-22T13:30:00+00:00",
            },
            id="open",
        ),
        pytest.param(
            None,
            {
                "is_open": False,
                "now": "2026-10-21T14:30:00+00:00",
                "closes_at": None,
                "next_open": "2026-10-22T13:30:00+00:00",
            },
            id="closed",
        ),
    ],
)
def test_to_dict(closes_at: datetime | None, expected: dict[str, Any]) -> None:
    tested = helper_instance(closes_at)
    result = tested.to_dict()
    assert result == expected


@pytest.mark.parametrize(
    "data, expected",
    [
        pytest.param(
            {
                "is_open": True,
                "now": datetime(2026, 10, 21, 14, 30, 0, tzinfo=UTC),
                "closes_at": datetime(2026, 10, 21, 20, 0, 0, tzinfo=UTC),
                "next_open": datetime(2026, 10, 22, 13, 30, 0, tzinfo=UTC),
            },
            MarketStatus(
                is_open=True,
                now=datetime(2026, 10, 21, 14, 30, 0, tzinfo=UTC),
                closes_at=datetime(2026, 10, 21, 20, 0, 0, tzinfo=UTC),
                next_open=datetime(2026, 10, 22, 13, 30, 0, tzinfo=UTC),
            ),
            id="native-open",
        ),
        pytest.param(
            {
                "is_open": True,
                "now": "2026-10-21T14:30:00+00:00",
                "closes_at": "2026-10-21T20:00:00+00:00",
                "next_open": "2026-10-22T13:30:00+00:00",
            },
            MarketStatus(
                is_open=True,
                now=datetime(2026, 10, 21, 14, 30, 0, tzinfo=UTC),
                closes_at=datetime(2026, 10, 21, 20, 0, 0, tzinfo=UTC),
                next_open=datetime(2026, 10, 22, 13, 30, 0, tzinfo=UTC),
            ),
            id="json-open",
        ),
        pytest.param(
            {
                "is_open": False,
                "now": "2026-10-21T14:30:00+00:00",
                "closes_at": None,
                "next_open": "2026-10-22T13:30:00+00:00",
            },
            MarketStatus(
                is_open=False,
                now=datetime(2026, 10, 21, 14, 30, 0, tzinfo=UTC),
                closes_at=None,
                next_open=datetime(2026, 10, 22, 13, 30, 0, tzinfo=UTC),
            ),
            id="json-closed",
        ),
    ],
)
def test_from_dict(data: dict[str, Any], expected: MarketStatus) -> None:
    tested = MarketStatus
    result = tested.from_dict(data)
    assert result == expected


@pytest.mark.parametrize(
    "field",
    [
        pytest.param("is_open", id="is_open"),
        pytest.param("now", id="now"),
        pytest.param("closes_at", id="closes_at"),
        pytest.param("next_open", id="next_open"),
    ],
)
def test_from_dict__a_missing_field_raises(field: str) -> None:
    tested = MarketStatus
    complete = {
        "is_open": False,
        "now": "2026-10-21T14:30:00+00:00",
        "closes_at": None,
        "next_open": "2026-10-22T13:30:00+00:00",
    }
    data = {key: value for key, value in complete.items() if key != field}
    with pytest.raises(KeyError) as exc_info:
        tested.from_dict(data)
    expected = (field,)
    assert exc_info.value.args == expected
