from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from mcp_stock_markets.constants.quote_source import QuoteSource
from mcp_stock_markets.structures.holding import Holding
from mcp_stock_markets.structures.position import Position
from mcp_stock_markets.structures.quote import Quote
from tests.conftest import is_namedtuple


def helper_quote() -> Quote:
    return Quote(
        symbol="AAPL",
        price=Decimal("190.0000"),
        currency="USD",
        as_of=datetime(2026, 10, 21, 14, 30, 0, tzinfo=UTC),
        source=QuoteSource.GOOGLE_FINANCE,
        fetched_at=datetime(2026, 10, 21, 14, 31, 0, tzinfo=UTC),
    )


def helper_instance(quote: Quote | None, value: str) -> Position:
    return Position(
        holding=Holding(symbol="AAPL", quantity=2, cost=Decimal("374.86")),
        quote=quote,
        value=Decimal(value),
    )


def helper_json(quote: dict[str, Any] | None, value: str) -> dict[str, Any]:
    return {
        "holding": {"symbol": "AAPL", "quantity": 2, "cost": "374.86"},
        "quote": quote,
        "value": value,
    }


def test_class() -> None:
    tested = Position
    fields = {"holding": "Holding", "quote": "Quote | None", "value": "Decimal"}
    assert is_namedtuple(tested, fields)


@pytest.mark.parametrize(
    "quote, value, expected",
    [
        pytest.param(
            helper_quote(),
            "380.00",
            {
                "holding": {"symbol": "AAPL", "quantity": 2, "cost": "374.86"},
                "quote": {
                    "symbol": "AAPL",
                    "price": "190.0000",
                    "currency": "USD",
                    "as_of": "2026-10-21T14:30:00+00:00",
                    "source": "google_finance",
                    "fetched_at": "2026-10-21T14:31:00+00:00",
                },
                "value": "380.00",
            },
            id="quoted",
        ),
        pytest.param(
            None,
            "374.86",
            {
                "holding": {"symbol": "AAPL", "quantity": 2, "cost": "374.86"},
                "quote": None,
                "value": "374.86",
            },
            id="unquoted",
        ),
    ],
)
def test_to_dict(quote: Quote | None, value: str, expected: dict[str, Any]) -> None:
    tested = helper_instance(quote, value)
    result = tested.to_dict()
    assert result == expected


@pytest.mark.parametrize(
    "data, expected",
    [
        pytest.param(
            {
                "holding": {"symbol": "AAPL", "quantity": 2, "cost": Decimal("374.86")},
                "quote": {
                    "symbol": "AAPL",
                    "price": Decimal("190.0000"),
                    "currency": "USD",
                    "as_of": datetime(2026, 10, 21, 14, 30, 0, tzinfo=UTC),
                    "source": "google_finance",
                    "fetched_at": datetime(2026, 10, 21, 14, 31, 0, tzinfo=UTC),
                },
                "value": Decimal("380.00"),
            },
            helper_instance(helper_quote(), "380.00"),
            id="native-quoted",
        ),
        pytest.param(
            helper_json(
                {
                    "symbol": "AAPL",
                    "price": "190.0000",
                    "currency": "USD",
                    "as_of": "2026-10-21T14:30:00+00:00",
                    "source": "google_finance",
                    "fetched_at": "2026-10-21T14:31:00+00:00",
                },
                "380.00",
            ),
            helper_instance(helper_quote(), "380.00"),
            id="json-quoted",
        ),
        pytest.param(
            helper_json(None, "374.86"),
            helper_instance(None, "374.86"),
            id="json-unquoted",
        ),
    ],
)
def test_from_dict(data: dict[str, Any], expected: Position) -> None:
    tested = Position
    result = tested.from_dict(data)
    assert result == expected


@pytest.mark.parametrize(
    "field",
    [
        pytest.param("holding", id="holding"),
        pytest.param("quote", id="quote"),
        pytest.param("value", id="value"),
    ],
)
def test_from_dict__a_missing_field_raises(field: str) -> None:
    tested = Position
    data = {key: value for key, value in helper_json(None, "374.86").items() if key != field}
    with pytest.raises(KeyError) as exc_info:
        tested.from_dict(data)
    expected = (field,)
    assert exc_info.value.args == expected
