from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, NamedTuple

from mcp_stock_markets.structures.wire import Wire


class DailyBar(NamedTuple):
    """One trading day of a stock: its open, high, low, close and volume."""

    symbol: str
    day: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "day": self.day.isoformat(),
            "open": str(self.open),
            "high": str(self.high),
            "low": str(self.low),
            "close": str(self.close),
            "volume": self.volume,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DailyBar:
        return cls(
            symbol=str(data["symbol"]),
            day=Wire.day(data["day"]),
            open=Wire.money(data["open"]),
            high=Wire.money(data["high"]),
            low=Wire.money(data["low"]),
            close=Wire.money(data["close"]),
            volume=int(data["volume"]),
        )
