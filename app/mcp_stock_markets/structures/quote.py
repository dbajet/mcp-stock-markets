from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, NamedTuple

from mcp_stock_markets.constants.quote_source import QuoteSource
from mcp_stock_markets.structures.wire import Wire


class Quote(NamedTuple):
    """A stock's price, the moment of the trade it comes from, and where
    it was read. `as_of` is the trade, `fetched_at` the reading: an order
    is priced only on a recent trade, however recently it was read."""

    symbol: str
    price: Decimal
    currency: str
    as_of: datetime
    source: QuoteSource
    fetched_at: datetime

    def age_seconds(self, now: datetime) -> float:
        return (now - self.as_of).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "price": str(self.price),
            "currency": self.currency,
            "as_of": self.as_of.isoformat(),
            "source": self.source.value,
            "fetched_at": self.fetched_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Quote:
        return cls(
            symbol=str(data["symbol"]),
            price=Wire.money(data["price"]),
            currency=str(data["currency"]),
            as_of=Wire.moment(data["as_of"]),
            source=QuoteSource(data["source"]),
            fetched_at=Wire.moment(data["fetched_at"]),
        )
