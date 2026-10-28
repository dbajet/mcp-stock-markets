from __future__ import annotations

import dataclasses

from mcp_stock_markets.constants.broker_constants import BrokerConstants
from tests.conftest import is_dataclass


def test_class() -> None:
    tested = BrokerConstants
    fields = {
        "max_order_quantity": "int",
        "max_reason_chars": "int",
        "transactions_page": "int",
        "max_transactions_page": "int",
        "order_lock_key": "int",
        "valuation_interval_minutes": "int",
        "valuations_page": "int",
        "pricing_threads": "int",
        "no_portfolio": "str",
    }
    assert is_dataclass(tested, fields)


def test_values() -> None:
    tested = BrokerConstants
    result = dataclasses.asdict(tested)
    expected = {
        "max_order_quantity": 10000,
        "max_reason_chars": 500,
        "transactions_page": 50,
        "max_transactions_page": 500,
        "order_lock_key": 7310402,
        "valuation_interval_minutes": 30,
        "valuations_page": 2000,
        "pricing_threads": 10,
        "no_portfolio": "There is no portfolio: set BOOTSTRAP_ADMIN_EMAIL and restart.",
    }
    assert result == expected
