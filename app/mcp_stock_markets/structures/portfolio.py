from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, NamedTuple

from mcp_stock_markets.structures.wire import Wire


class Portfolio(NamedTuple):
    """The owner's virtual account: the budget it started with and the cash
    it holds now, which the database keeps at or above zero."""

    portfolio_id: int
    user_id: int
    starting_budget: Decimal
    cash: Decimal
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "portfolio_id": self.portfolio_id,
            "user_id": self.user_id,
            "starting_budget": str(self.starting_budget),
            "cash": str(self.cash),
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Portfolio:
        return cls(
            portfolio_id=int(data["portfolio_id"]),
            user_id=int(data["user_id"]),
            starting_budget=Wire.money(data["starting_budget"]),
            cash=Wire.money(data["cash"]),
            created_at=Wire.moment(data["created_at"]),
        )
