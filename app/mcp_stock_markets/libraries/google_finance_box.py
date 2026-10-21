from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from mcp_stock_markets.constants.market_constants import MarketConstants
from mcp_stock_markets.constants.quote_source import QuoteSource
from mcp_stock_markets.libraries.web_box import WebBox
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.quote import Quote


class GoogleFinanceBox:
    """The live price of a stock, read from its Google Finance page.

    Google Finance has no API: the page carries its data as JSON arrays in
    `AF_initDataCallback({key: 'ds:N', hash: …, data: […]})` calls, one of
    which describes the quote — `[id, [symbol, exchange], name, kind,
    currency, [price, change, change %, …], …]`, with the time of the
    regular session's last trade at index 17. The parser looks for that
    shape rather than a `ds:` number, which moves between pages. A page that
    changes shape is a failure (502), and the fallback source is asked."""

    def __init__(self, web: WebBox) -> None:
        self._web = web

    def quote(self, symbol: str, exchange: str, now: datetime) -> Quote:
        page = self._web.text(
            f"{MarketConstants.google_finance_url}{symbol}:{exchange}{MarketConstants.google_finance_query}",
            {"User-Agent": MarketConstants.browser_user_agent, "Accept-Language": "en-US,en;q=0.8"},
        )
        # Google writes a share class with a dot, as Wikipedia does (BRK.B).
        entry = self.entry(page, symbol, exchange)
        if entry is None:
            raise AppException(502, f"Google Finance shows no quote for {symbol}.")
        return self.quote_of(symbol, entry, now)

    @classmethod
    def entry(cls, page: str, symbol: str, exchange: str) -> list[Any] | None:
        """The quote's array in the page, or None: every data block is read,
        and the first array naming [symbol, exchange] with a price wins."""
        decoder = json.JSONDecoder()
        position = page.find(MarketConstants.google_data_marker)
        while position != -1:
            start = page.find(MarketConstants.google_data_start, position)
            if start == -1:
                return None
            try:
                data, _ = decoder.raw_decode(page, start + len(MarketConstants.google_data_start))
            except ValueError:
                data = None
            if (found := cls.found(data, [symbol, exchange])) is not None:
                return found
            position = page.find(MarketConstants.google_data_marker, start)
        return None

    @classmethod
    def found(cls, data: Any, pair: list[str]) -> list[Any] | None:
        """Depth-first through nested lists: the quote array is three levels down today."""
        if not isinstance(data, list):
            return None
        if (
            len(data) >= MarketConstants.google_entry_min_length
            and data[MarketConstants.google_pair_index] == pair
            and isinstance(data[MarketConstants.google_price_index], list)
        ):
            return data
        for item in data:
            if (result := cls.found(item, pair)) is not None:
                return result
        return None

    @classmethod
    def quote_of(cls, symbol: str, entry: list[Any], now: datetime) -> Quote:
        try:
            price = Decimal(str(entry[MarketConstants.google_price_index][0])).quantize(
                Decimal(MarketConstants.price_places)
            )
            traded = entry[MarketConstants.google_trade_time_index] or entry[MarketConstants.google_updated_index]
            as_of = datetime.fromtimestamp(int(traded[0]), UTC)
            currency = str(entry[MarketConstants.google_currency_index])
        except (ArithmeticError, IndexError, TypeError, ValueError):
            raise AppException(502, f"Google Finance's quote of {symbol} has an unexpected shape.") from None
        if price <= 0:
            raise AppException(502, f"Google Finance's quote of {symbol} has no price.")
        return Quote(
            symbol=symbol,
            price=price,
            currency=currency,
            as_of=as_of,
            source=QuoteSource.GOOGLE_FINANCE,
            fetched_at=now,
        )
