from __future__ import annotations

import json
import threading
import time
from datetime import date, datetime
from datetime import time as day_time
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from mcp_stock_markets.constants.market_constants import MarketConstants
from mcp_stock_markets.constants.quote_source import QuoteSource
from mcp_stock_markets.libraries.web_box import WebBox
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.daily_bar import DailyBar
from mcp_stock_markets.structures.quote import Quote


class AlphaVantageBox:
    """Alpha Vantage's free API: the latest trading day's quote, and a
    stock's daily bars.

    A free key allows one request a second and 25 a day, so requests are
    spaced and the callers cache what they read. Alpha Vantage answers a
    refused request with HTTP 200 and a JSON note ("Information", "Note" or
    "Error Message") instead of data: that note is a failure here, never
    read as an empty answer."""

    _NOTES = ("Information", "Note", "Error Message")

    def __init__(self, web: WebBox, key: str) -> None:
        self._web = web
        self._key = key
        self._zone = ZoneInfo(MarketConstants.timezone)
        self._spacing = threading.Lock()
        self._last_request = 0.0

    def is_configured(self) -> bool:
        return self._key != ""

    def quote(self, symbol: str, now: datetime) -> Quote:
        """GLOBAL_QUOTE: a price dated by its trading day, read as that day's close."""
        data = self.answer(
            {"function": MarketConstants.alpha_vantage_quote_function, "symbol": self.api_symbol(symbol)}
        )
        try:
            fields = data["Global Quote"]
            price = Decimal(fields["05. price"]).quantize(Decimal(MarketConstants.price_places))
            day = date.fromisoformat(fields["07. latest trading day"])
        except (KeyError, TypeError, ValueError, ArithmeticError):
            raise AppException(502, f"Alpha Vantage has no quote for {symbol}.") from None
        if price <= 0:
            raise AppException(502, f"Alpha Vantage has no quote for {symbol}.")
        return Quote(
            symbol=symbol,
            price=price,
            currency=MarketConstants.currency,
            as_of=datetime.combine(day, day_time.fromisoformat(MarketConstants.close_time), self._zone),
            source=QuoteSource.ALPHA_VANTAGE,
            fetched_at=now,
        )

    def daily(self, symbol: str) -> list[DailyBar]:
        """The last hundred trading days ("compact"), oldest first."""
        data = self.answer(
            {"function": MarketConstants.alpha_vantage_daily_function, "symbol": self.api_symbol(symbol)}
        )
        try:
            series = data["Time Series (Daily)"]
            result = [
                DailyBar(
                    symbol=symbol,
                    day=date.fromisoformat(day),
                    open=Decimal(bar["1. open"]),
                    high=Decimal(bar["2. high"]),
                    low=Decimal(bar["3. low"]),
                    close=Decimal(bar["4. close"]),
                    volume=int(bar["5. volume"]),
                )
                for day, bar in series.items()
            ]
        except (KeyError, TypeError, ValueError, AttributeError, ArithmeticError):
            raise AppException(502, f"Alpha Vantage has no daily history for {symbol}.") from None
        return sorted(result, key=lambda bar: bar.day)

    @classmethod
    def api_symbol(cls, symbol: str) -> str:
        """Alpha Vantage writes a share class with a dash (BRK-B), where Wikipedia has a dot."""
        return symbol.replace(".", "-")

    def answer(self, query: dict[str, str]) -> dict[str, Any]:
        if not self._key:
            raise AppException(503, MarketConstants.history_needs_key)
        self._spaced()
        # The key travels in the query string, as Alpha Vantage requires: it is never logged.
        text = self._web.text(f"{MarketConstants.alpha_vantage_url}?{urlencode(query | {'apikey': self._key})}", {})
        try:
            result = json.loads(text)
        except ValueError:
            raise AppException(502, "Alpha Vantage's answer is not JSON.") from None
        if not isinstance(result, dict):
            raise AppException(502, "Alpha Vantage's answer is not a JSON object.")
        for note in self._NOTES:
            if note in result:
                raise AppException(503, f"Alpha Vantage refused the request: {str(result[note])[:200]}")
        return result

    def _spaced(self) -> None:
        """At most one request per spacing interval, across threads."""
        with self._spacing:
            wait = self._last_request + MarketConstants.alpha_vantage_spacing_seconds - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()
