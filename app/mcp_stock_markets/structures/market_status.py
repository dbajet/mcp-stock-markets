from __future__ import annotations

from datetime import datetime
from typing import Any, NamedTuple

from mcp_stock_markets.structures.wire import Wire


class MarketStatus(NamedTuple):
    """Whether the US market is open now, by the exchange calendar; when
    today's session closes if it is, and when the next one opens."""

    is_open: bool
    now: datetime
    closes_at: datetime | None
    next_open: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_open": self.is_open,
            "now": self.now.isoformat(),
            "closes_at": None if self.closes_at is None else self.closes_at.isoformat(),
            "next_open": self.next_open.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MarketStatus:
        return cls(
            is_open=bool(data["is_open"]),
            now=Wire.moment(data["now"]),
            closes_at=None if data["closes_at"] is None else Wire.moment(data["closes_at"]),
            next_open=Wire.moment(data["next_open"]),
        )
