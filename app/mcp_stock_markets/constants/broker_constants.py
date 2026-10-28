from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class _BrokerConstants:
    # One order of more shares than this is a model's slip, not a decision.
    max_order_quantity: int = 10_000
    max_reason_chars: int = 500
    transactions_page: int = 50
    max_transactions_page: int = 500
    # pg_advisory_xact_lock key serializing orders: the cash read and the cash
    # written belong to one order at a time, whichever color takes it.
    order_lock_key: int = 7_310_402
    # A valuation (cash + holdings at the latest prices) is recorded this often
    # while the market is open, for the chart of the portfolio's value.
    valuation_interval_minutes: int = 30
    valuations_page: int = 2000
    # The holdings are priced at once, not one after another: each lookup may
    # wait up to the web timeout, and the agent's MCP call allows 30 s in all.
    pricing_threads: int = 10

    # --- messages --------------------------------------------------------------------
    no_portfolio: str = "There is no portfolio: set BOOTSTRAP_ADMIN_EMAIL and restart."


BrokerConstants = _BrokerConstants()
