from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from mcp_stock_markets.constants.market_constants import MarketConstants
from mcp_stock_markets.structures.market_status import MarketStatus


class MarketClock:
    """The US market's hours by the exchange calendar: weekdays from 9:30 to
    16:00 New York time, but for holidays and the afternoons that close at
    13:00. New York time, not UTC, so the clock moves with daylight saving."""

    def __init__(self) -> None:
        self._zone = ZoneInfo(MarketConstants.timezone)
        self._holidays = frozenset(date.fromisoformat(day) for day in MarketConstants.holidays)
        self._early_closes = frozenset(date.fromisoformat(day) for day in MarketConstants.early_closes)

    def status(self, now: datetime) -> MarketStatus:
        local = now.astimezone(self._zone)
        session = self.session(local.date())
        is_open = session is not None and session[0] <= local < session[1]
        return MarketStatus(
            is_open=is_open,
            now=local,
            closes_at=session[1] if is_open and session is not None else None,
            next_open=self.next_open(local),
        )

    def session(self, day: date) -> tuple[datetime, datetime] | None:
        """The day's opening and closing, or None when the market does not trade."""
        if day.weekday() >= 5 or day in self._holidays:
            return None
        closing = MarketConstants.early_close_time if day in self._early_closes else MarketConstants.close_time
        return (
            datetime.combine(day, time.fromisoformat(MarketConstants.open_time), self._zone),
            datetime.combine(day, time.fromisoformat(closing), self._zone),
        )

    def next_open(self, local: datetime) -> datetime:
        """The next opening after this moment: today's, if it is still ahead.
        Two weeks always hold a trading day."""
        day = local.date()
        for _ in range(14):
            if (session := self.session(day)) is not None and session[0] > local:
                return session[0]
            day += timedelta(days=1)
        raise RuntimeError("no trading day in two weeks: the holiday calendar is wrong")

    def is_open(self, now: datetime) -> bool:
        return self.status(now).is_open
