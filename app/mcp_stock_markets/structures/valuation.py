from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, NamedTuple

from mcp_stock_markets.structures.wire import Wire


class Valuation(NamedTuple):
    """What the portfolio was worth at a moment: one point of its chart."""

    taken_at: datetime
    cash: Decimal
    holdings_value: Decimal
    total_value: Decimal

    def to_dict(self) -> dict[str, Any]:
        return {
            "taken_at": self.taken_at.isoformat(),
            "cash": str(self.cash),
            "holdings_value": str(self.holdings_value),
            "total_value": str(self.total_value),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Valuation:
        return cls(
            taken_at=Wire.moment(data["taken_at"]),
            cash=Wire.money(data["cash"]),
            holdings_value=Wire.money(data["holdings_value"]),
            total_value=Wire.money(data["total_value"]),
        )
