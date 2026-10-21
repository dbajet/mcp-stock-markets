from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from mcp_stock_markets.constants.quote_source import QuoteSource
from mcp_stock_markets.structures.holding import Holding
from mcp_stock_markets.structures.portfolio import Portfolio
from mcp_stock_markets.structures.portfolio_view import PortfolioView
from mcp_stock_markets.structures.position import Position
from mcp_stock_markets.structures.quote import Quote
from tests.conftest import is_namedtuple


def helper_instance() -> PortfolioView:
    return PortfolioView(
        portfolio=Portfolio(
            portfolio_id=3,
            user_id=7,
            starting_budget=Decimal("500.00"),
            cash=Decimal("25.14"),
            created_at=datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC),
        ),
        positions=(
            Position(
                holding=Holding(symbol="AAPL", quantity=2, cost=Decimal("374.86")),
                quote=Quote(
                    symbol="AAPL",
                    price=Decimal("190.0000"),
                    currency="USD",
                    as_of=datetime(2026, 10, 21, 14, 30, 0, tzinfo=UTC),
                    source=QuoteSource.GOOGLE_FINANCE,
                    fetched_at=datetime(2026, 10, 21, 14, 31, 0, tzinfo=UTC),
                ),
                value=Decimal("380.00"),
            ),
            Position(
                holding=Holding(symbol="KO", quantity=1, cost=Decimal("100.00")),
                quote=None,
                value=Decimal("100.00"),
            ),
        ),
        holdings_value=Decimal("480.00"),
        total_value=Decimal("505.14"),
        universe=("AAPL", "KO", "MSFT"),
    )


def helper_json() -> dict[str, Any]:
    return {
        "portfolio": {
            "portfolio_id": 3,
            "user_id": 7,
            "starting_budget": "500.00",
            "cash": "25.14",
            "created_at": "2026-10-01T09:00:00+00:00",
        },
        "positions": [
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
            {
                "holding": {"symbol": "KO", "quantity": 1, "cost": "100.00"},
                "quote": None,
                "value": "100.00",
            },
        ],
        "holdings_value": "480.00",
        "total_value": "505.14",
        "universe": ["AAPL", "KO", "MSFT"],
    }


def helper_native() -> dict[str, Any]:
    return {
        "portfolio": {
            "portfolio_id": 3,
            "user_id": 7,
            "starting_budget": Decimal("500.00"),
            "cash": Decimal("25.14"),
            "created_at": datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC),
        },
        "positions": (
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
            {
                "holding": {"symbol": "KO", "quantity": 1, "cost": Decimal("100.00")},
                "quote": None,
                "value": Decimal("100.00"),
            },
        ),
        "holdings_value": Decimal("480.00"),
        "total_value": Decimal("505.14"),
        "universe": ("AAPL", "KO", "MSFT"),
    }


def test_class() -> None:
    tested = PortfolioView
    fields = {
        "portfolio": "Portfolio",
        "positions": "tuple[Position, ...]",
        "holdings_value": "Decimal",
        "total_value": "Decimal",
        "universe": "tuple[str, ...]",
    }
    assert is_namedtuple(tested, fields)


def test_to_dict() -> None:
    tested = helper_instance()
    result = tested.to_dict()
    expected = {
        "portfolio": {
            "portfolio_id": 3,
            "user_id": 7,
            "starting_budget": "500.00",
            "cash": "25.14",
            "created_at": "2026-10-01T09:00:00+00:00",
        },
        "positions": [
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
            {
                "holding": {"symbol": "KO", "quantity": 1, "cost": "100.00"},
                "quote": None,
                "value": "100.00",
            },
        ],
        "holdings_value": "480.00",
        "total_value": "505.14",
        "universe": ["AAPL", "KO", "MSFT"],
    }
    assert result == expected


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(helper_native(), id="native"),
        pytest.param(helper_json(), id="json-form"),
    ],
)
def test_from_dict(data: dict[str, Any]) -> None:
    tested = PortfolioView
    result = tested.from_dict(data)
    expected = helper_instance()
    assert result == expected


@pytest.mark.parametrize(
    "field",
    [
        pytest.param("portfolio", id="portfolio"),
        pytest.param("positions", id="positions"),
        pytest.param("holdings_value", id="holdings_value"),
        pytest.param("total_value", id="total_value"),
        pytest.param("universe", id="universe"),
    ],
)
def test_from_dict__a_missing_field_raises(field: str) -> None:
    tested = PortfolioView
    data = {key: value for key, value in helper_json().items() if key != field}
    with pytest.raises(KeyError) as exc_info:
        tested.from_dict(data)
    expected = (field,)
    assert exc_info.value.args == expected
