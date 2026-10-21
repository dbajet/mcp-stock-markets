from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from mcp_stock_markets.constants.quote_source import QuoteSource
from mcp_stock_markets.constants.trade_side import TradeSide
from mcp_stock_markets.structures.trade import Trade
from tests.conftest import is_namedtuple


def helper_instance(agent_run_id: int | None) -> Trade:
    return Trade(
        trade_id=11,
        executed_at=datetime(2026, 10, 21, 14, 32, 0, tzinfo=UTC),
        symbol="AAPL",
        side=TradeSide.BUY,
        quantity=2,
        price=Decimal("187.4300"),
        amount=Decimal("374.86"),
        cash_after=Decimal("125.14"),
        quote_source=QuoteSource.GOOGLE_FINANCE,
        quote_as_of=datetime(2026, 10, 21, 14, 30, 0, tzinfo=UTC),
        agent_run_id=agent_run_id,
        reason="Strong quarter.",
    )


def helper_json(agent_run_id: int | None) -> dict[str, Any]:
    return {
        "trade_id": 11,
        "executed_at": "2026-10-21T14:32:00+00:00",
        "symbol": "AAPL",
        "side": "buy",
        "quantity": 2,
        "price": "187.4300",
        "amount": "374.86",
        "cash_after": "125.14",
        "quote_source": "google_finance",
        "quote_as_of": "2026-10-21T14:30:00+00:00",
        "agent_run_id": agent_run_id,
        "reason": "Strong quarter.",
    }


def test_class() -> None:
    tested = Trade
    fields = {
        "trade_id": "int",
        "executed_at": "datetime",
        "symbol": "str",
        "side": "TradeSide",
        "quantity": "int",
        "price": "Decimal",
        "amount": "Decimal",
        "cash_after": "Decimal",
        "quote_source": "QuoteSource",
        "quote_as_of": "datetime",
        "agent_run_id": "int | None",
        "reason": "str",
    }
    assert is_namedtuple(tested, fields)


@pytest.mark.parametrize(
    "agent_run_id, exp_agent_run_id",
    [
        pytest.param(5, 5, id="placed-by-a-run"),
        pytest.param(None, None, id="no-run"),
    ],
)
def test_to_dict(agent_run_id: int | None, exp_agent_run_id: int | None) -> None:
    tested = helper_instance(agent_run_id)
    result = tested.to_dict()
    expected = {
        "trade_id": 11,
        "executed_at": "2026-10-21T14:32:00+00:00",
        "symbol": "AAPL",
        "side": "buy",
        "quantity": 2,
        "price": "187.4300",
        "amount": "374.86",
        "cash_after": "125.14",
        "quote_source": "google_finance",
        "quote_as_of": "2026-10-21T14:30:00+00:00",
        "agent_run_id": exp_agent_run_id,
        "reason": "Strong quarter.",
    }
    assert result == expected


@pytest.mark.parametrize(
    "data, exp_agent_run_id",
    [
        pytest.param(
            {
                "trade_id": 11,
                "executed_at": datetime(2026, 10, 21, 14, 32, 0, tzinfo=UTC),
                "symbol": "AAPL",
                "side": "buy",
                "quantity": 2,
                "price": Decimal("187.4300"),
                "amount": Decimal("374.86"),
                "cash_after": Decimal("125.14"),
                "quote_source": "google_finance",
                "quote_as_of": datetime(2026, 10, 21, 14, 30, 0, tzinfo=UTC),
                "agent_run_id": 5,
                "reason": "Strong quarter.",
            },
            5,
            id="database-row",
        ),
        pytest.param(helper_json(5), 5, id="json-form"),
        pytest.param(helper_json(None), None, id="json-no-run"),
    ],
)
def test_from_dict(data: dict[str, Any], exp_agent_run_id: int | None) -> None:
    tested = Trade
    result = tested.from_dict(data)
    expected = Trade(
        trade_id=11,
        executed_at=datetime(2026, 10, 21, 14, 32, 0, tzinfo=UTC),
        symbol="AAPL",
        side=TradeSide.BUY,
        quantity=2,
        price=Decimal("187.4300"),
        amount=Decimal("374.86"),
        cash_after=Decimal("125.14"),
        quote_source=QuoteSource.GOOGLE_FINANCE,
        quote_as_of=datetime(2026, 10, 21, 14, 30, 0, tzinfo=UTC),
        agent_run_id=exp_agent_run_id,
        reason="Strong quarter.",
    )
    assert result == expected


@pytest.mark.parametrize(
    "field",
    [
        pytest.param("trade_id", id="trade_id"),
        pytest.param("executed_at", id="executed_at"),
        pytest.param("symbol", id="symbol"),
        pytest.param("side", id="side"),
        pytest.param("quantity", id="quantity"),
        pytest.param("price", id="price"),
        pytest.param("amount", id="amount"),
        pytest.param("cash_after", id="cash_after"),
        pytest.param("quote_source", id="quote_source"),
        pytest.param("quote_as_of", id="quote_as_of"),
        pytest.param("agent_run_id", id="agent_run_id"),
        pytest.param("reason", id="reason"),
    ],
)
def test_from_dict__a_missing_field_raises(field: str) -> None:
    tested = Trade
    data = {key: value for key, value in helper_json(5).items() if key != field}
    with pytest.raises(KeyError) as exc_info:
        tested.from_dict(data)
    expected = (field,)
    assert exc_info.value.args == expected
