from __future__ import annotations

from decimal import Decimal
from typing import Any, NamedTuple

from mcp_stock_markets.structures.wire import Wire


class Holding(NamedTuple):
    """Shares of one company the portfolio owns, and what they cost in all:
    a sale takes its share of the cost away at the average price."""

    symbol: str
    quantity: int
    cost: Decimal

    def to_dict(self) -> dict[str, Any]:
        return {"symbol": self.symbol, "quantity": self.quantity, "cost": str(self.cost)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Holding:
        return cls(
            symbol=str(data["symbol"]),
            quantity=int(data["quantity"]),
            cost=Wire.money(data["cost"]),
        )
