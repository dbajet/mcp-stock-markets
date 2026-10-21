from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, NamedTuple

from mcp_stock_markets.constants.quote_source import QuoteSource
from mcp_stock_markets.constants.trade_side import TradeSide
from mcp_stock_markets.structures.wire import Wire


class Trade(NamedTuple):
    """One virtual transaction, kept forever: when, which stock, its price
    then and where that price came from, buy or sell, how many shares, the
    amount, the cash left after it, and which agent run placed it and why."""

    trade_id: int
    executed_at: datetime
    symbol: str
    side: TradeSide
    quantity: int
    price: Decimal
    amount: Decimal
    cash_after: Decimal
    quote_source: QuoteSource
    quote_as_of: datetime
    agent_run_id: int | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "executed_at": self.executed_at.isoformat(),
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "price": str(self.price),
            "amount": str(self.amount),
            "cash_after": str(self.cash_after),
            "quote_source": self.quote_source.value,
            "quote_as_of": self.quote_as_of.isoformat(),
            "agent_run_id": self.agent_run_id,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Trade:
        return cls(
            trade_id=int(data["trade_id"]),
            executed_at=Wire.moment(data["executed_at"]),
            symbol=str(data["symbol"]),
            side=TradeSide(data["side"]),
            quantity=int(data["quantity"]),
            price=Wire.money(data["price"]),
            amount=Wire.money(data["amount"]),
            cash_after=Wire.money(data["cash_after"]),
            quote_source=QuoteSource(data["quote_source"]),
            quote_as_of=Wire.moment(data["quote_as_of"]),
            agent_run_id=None if data["agent_run_id"] is None else int(data["agent_run_id"]),
            reason=str(data["reason"]),
        )
