from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

from mcp_stock_markets.constants.market_constants import MarketConstants
from mcp_stock_markets.constants.quote_source import QuoteSource
from mcp_stock_markets.libraries.web_box import WebBox
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.daily_bar import DailyBar
from mcp_stock_markets.structures.quote import Quote


class AlpacaBox:
    """Alpaca's market data on its free Basic plan: a stock's latest trade on
    IEX, the one exchange whose live trades the plan carries, with the moment
    it was made; and daily bars of every exchange (SIP), which the plan serves
    once they are 15 minutes old. 200 requests a minute, no daily cap. The
    key pair travels in headers, never in a URL, and is never logged."""

    # Alpaca writes nanoseconds; Python reads at most microseconds.
    _NANOSECONDS = re.compile(r"(\.\d{6})\d+")

    def __init__(self, web: WebBox, key_id: str, secret_key: str) -> None:
        self._web = web
        self._key_id = key_id
        self._secret_key = secret_key
        self._zone = ZoneInfo(MarketConstants.timezone)

    def is_configured(self) -> bool:
        return self._key_id != "" and self._secret_key != ""

    def quote(self, symbol: str, now: datetime) -> Quote:
        """The latest IEX trade: its price, and when it was made."""
        data = self.answer(
            f"{self.stock_url(symbol)}/trades/latest?{urlencode({'feed': MarketConstants.alpaca_trade_feed})}"
        )
        try:
            trade = data["trade"]
            price = Decimal(str(trade["p"])).quantize(Decimal(MarketConstants.price_places))
            made = self.moment(str(trade["t"]))
        except (KeyError, TypeError, ValueError, ArithmeticError):
            raise AppException(502, f"Alpaca has no trade for {symbol}.") from None
        if price <= 0:
            raise AppException(502, f"Alpaca has no trade for {symbol}.")
        return Quote(
            symbol=symbol,
            price=price,
            currency=MarketConstants.currency,
            as_of=made,
            source=QuoteSource.ALPACA,
            fetched_at=now,
        )

    def daily(self, symbol: str, now: datetime) -> list[DailyBar]:
        """Some hundred trading days of daily bars, oldest first, split-adjusted,
        up to the delay the free plan asks of every-exchange data."""
        start = now.astimezone(self._zone).date() - timedelta(days=MarketConstants.alpaca_history_calendar_days)
        end = now - timedelta(minutes=MarketConstants.alpaca_bars_delay_minutes)
        query = {
            "timeframe": "1Day",
            "start": start.isoformat(),
            "end": end.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "feed": MarketConstants.alpaca_bars_feed,
            "adjustment": "split",
            "limit": str(MarketConstants.alpaca_bars_limit),
        }
        data = self.answer(f"{self.stock_url(symbol)}/bars?{urlencode(query)}")
        try:
            result = [
                DailyBar(
                    symbol=symbol,
                    day=self.moment(str(bar["t"])).astimezone(self._zone).date(),
                    open=Decimal(str(bar["o"])),
                    high=Decimal(str(bar["h"])),
                    low=Decimal(str(bar["l"])),
                    close=Decimal(str(bar["c"])),
                    volume=int(bar["v"]),
                )
                for bar in data["bars"]
            ]
        except (KeyError, TypeError, ValueError, ArithmeticError):
            # Alpaca answers `"bars": null` for a symbol it does not know.
            raise AppException(502, f"Alpaca has no daily history for {symbol}.") from None
        if not result:
            raise AppException(502, f"Alpaca has no daily history for {symbol}.")
        return sorted(result, key=lambda bar: bar.day)

    @classmethod
    def stock_url(cls, symbol: str) -> str:
        """A share class keeps its dot (BRK.B), as Wikipedia writes it."""
        return f"{MarketConstants.alpaca_data_url}/v2/stocks/{quote(symbol, safe='.')}"

    @classmethod
    def moment(cls, text: str) -> datetime:
        return datetime.fromisoformat(cls._NANOSECONDS.sub(r"\1", text))

    def answer(self, url: str) -> dict[str, Any]:
        if not self.is_configured():
            raise AppException(503, MarketConstants.history_needs_key)
        text = self._web.text(url, {"APCA-API-KEY-ID": self._key_id, "APCA-API-SECRET-KEY": self._secret_key})
        try:
            result = json.loads(text)
        except ValueError:
            raise AppException(502, "Alpaca's answer is not JSON.") from None
        if not isinstance(result, dict):
            raise AppException(502, "Alpaca's answer is not a JSON object.")
        return result
