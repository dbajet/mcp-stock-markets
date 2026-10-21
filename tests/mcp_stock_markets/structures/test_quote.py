from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from mcp_stock_markets.constants.quote_source import QuoteSource
from mcp_stock_markets.structures.quote import Quote
from tests.conftest import is_namedtuple


def helper_instance() -> Quote:
    return Quote(
        symbol="AAPL",
        price=Decimal("187.4321"),
        currency="USD",
        as_of=datetime(2026, 10, 21, 14, 30, 0, tzinfo=UTC),
        source=QuoteSource.GOOGLE_FINANCE,
        fetched_at=datetime(2026, 10, 21, 14, 31, 0, tzinfo=UTC),
    )


def helper_row() -> dict[str, Any]:
    return {
        "symbol": "AAPL",
        "price": Decimal("187.4321"),
        "currency": "USD",
        "as_of": datetime(2026, 10, 21, 14, 30, 0, tzinfo=UTC),
        "source": "google_finance",
        "fetched_at": datetime(2026, 10, 21, 14, 31, 0, tzinfo=UTC),
    }


def helper_json() -> dict[str, Any]:
    return {
        "symbol": "AAPL",
        "price": "187.4321",
        "currency": "USD",
        "as_of": "2026-10-21T14:30:00+00:00",
        "source": "google_finance",
        "fetched_at": "2026-10-21T14:31:00+00:00",
    }


def test_class() -> None:
    tested = Quote
    fields = {
        "symbol": "str",
        "price": "Decimal",
        "currency": "str",
        "as_of": "datetime",
        "source": "QuoteSource",
        "fetched_at": "datetime",
    }
    assert is_namedtuple(tested, fields)


@pytest.mark.parametrize(
    "now, expected",
    [
        pytest.param(datetime(2026, 10, 21, 14, 30, 0, tzinfo=UTC), 0.0, id="same-moment"),
        pytest.param(datetime(2026, 10, 21, 14, 45, 30, 500000, tzinfo=UTC), 930.5, id="later"),
        pytest.param(datetime(2026, 10, 21, 14, 29, 0, tzinfo=UTC), -60.0, id="earlier"),
    ],
)
def test_age_seconds(now: datetime, expected: float) -> None:
    tested = helper_instance()
    result = tested.age_seconds(now)
    assert result == expected


def test_to_dict() -> None:
    tested = helper_instance()
    result = tested.to_dict()
    expected = {
        "symbol": "AAPL",
        "price": "187.4321",
        "currency": "USD",
        "as_of": "2026-10-21T14:30:00+00:00",
        "source": "google_finance",
        "fetched_at": "2026-10-21T14:31:00+00:00",
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
    tested = Quote
    result = tested.from_dict(data)
    expected = Quote(
        symbol="AAPL",
        price=Decimal("187.4321"),
        currency="USD",
        as_of=datetime(2026, 10, 21, 14, 30, 0, tzinfo=UTC),
        source=QuoteSource.GOOGLE_FINANCE,
        fetched_at=datetime(2026, 10, 21, 14, 31, 0, tzinfo=UTC),
    )
    assert result == expected


@pytest.mark.parametrize(
    "field",
    [
        pytest.param("symbol", id="symbol"),
        pytest.param("price", id="price"),
        pytest.param("currency", id="currency"),
        pytest.param("as_of", id="as_of"),
        pytest.param("source", id="source"),
        pytest.param("fetched_at", id="fetched_at"),
    ],
)
def test_from_dict__a_missing_field_raises(field: str) -> None:
    tested = Quote
    data = {key: value for key, value in helper_json().items() if key != field}
    with pytest.raises(KeyError) as exc_info:
        tested.from_dict(data)
    expected = (field,)
    assert exc_info.value.args == expected
