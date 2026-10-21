from __future__ import annotations

from decimal import Decimal
from typing import Any, NamedTuple

from mcp_stock_markets.structures.holding import Holding
from mcp_stock_markets.structures.quote import Quote
from mcp_stock_markets.structures.wire import Wire


class Position(NamedTuple):
    """A holding valued at its latest quote. Without a quote it is valued at
    what it cost, and says so (`quote` is None)."""

    holding: Holding
    quote: Quote | None
    value: Decimal

    def to_dict(self) -> dict[str, Any]:
        return {
            "holding": self.holding.to_dict(),
            "quote": None if self.quote is None else self.quote.to_dict(),
            "value": str(self.value),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Position:
        return cls(
            holding=Holding.from_dict(data["holding"]),
            quote=None if data["quote"] is None else Quote.from_dict(data["quote"]),
            value=Wire.money(data["value"]),
        )
