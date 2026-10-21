from __future__ import annotations

from decimal import Decimal
from typing import Any, NamedTuple

from mcp_stock_markets.structures.portfolio import Portfolio
from mcp_stock_markets.structures.position import Position
from mcp_stock_markets.structures.wire import Wire


class PortfolioView(NamedTuple):
    """The portfolio as the page and the agent see it: its cash, each
    position at its latest price, the total, and the market the agent may
    buy from."""

    portfolio: Portfolio
    positions: tuple[Position, ...]
    holdings_value: Decimal
    total_value: Decimal
    universe: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "portfolio": self.portfolio.to_dict(),
            "positions": [position.to_dict() for position in self.positions],
            "holdings_value": str(self.holdings_value),
            "total_value": str(self.total_value),
            "universe": list(self.universe),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PortfolioView:
        return cls(
            portfolio=Portfolio.from_dict(data["portfolio"]),
            positions=tuple(Position.from_dict(position) for position in data["positions"]),
            holdings_value=Wire.money(data["holdings_value"]),
            total_value=Wire.money(data["total_value"]),
            universe=tuple(str(symbol) for symbol in data["universe"]),
        )
