from __future__ import annotations

import logging
from datetime import datetime, timedelta

from mcp_stock_markets.constants.constants import Constants
from mcp_stock_markets.constants.market_constants import MarketConstants
from mcp_stock_markets.libraries.alpaca_box import AlpacaBox
from mcp_stock_markets.libraries.company_store import CompanyStore
from mcp_stock_markets.libraries.google_finance_box import GoogleFinanceBox
from mcp_stock_markets.libraries.market_clock import MarketClock
from mcp_stock_markets.libraries.quote_store import QuoteStore
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.daily_bar import DailyBar
from mcp_stock_markets.structures.market_status import MarketStatus
from mcp_stock_markets.structures.quote import Quote


class QuoteCommand:
    """Prices and the market's hours. A price comes from Google Finance, live,
    or from Alpaca's latest IEX trade when Google fails; one read in the last
    minute is served again, and when neither answers, the last one read,
    however old. Daily history comes from Alpaca, once a day per stock."""

    def __init__(
        self,
        store: QuoteStore,
        companies: CompanyStore,
        google: GoogleFinanceBox,
        alpaca: AlpacaBox,
        clock: MarketClock,
    ) -> None:
        self._store = store
        self._companies = companies
        self._google = google
        self._alpaca = alpaca
        self._clock = clock

    def market(self, now: datetime) -> MarketStatus:
        return self._clock.status(now)

    def quote(self, symbol: str, now: datetime) -> Quote:
        wanted = symbol.strip().upper()
        cached = self._store.latest(wanted)
        if cached is not None and now - cached.fetched_at < timedelta(seconds=MarketConstants.quote_cache_seconds):
            return cached
        try:
            return self._store.stored(self.fetched(wanted, now))
        except AppException:
            if cached is None:
                raise
            # Its trade time says how old it is: the broker refuses a stale one.
            return cached

    def fetched(self, symbol: str, now: datetime) -> Quote:
        """Google first; Alpaca, when it has a key, if Google fails. Each says
        when its trade was made, which the broker's freshness rule reads."""
        company = self._companies.company(symbol)
        # A company that left the index since it was bought is still sold: its
        # exchange is then unknown, and the NYSE, where most members trade, is tried.
        exchange = MarketConstants.exchange_nyse if company is None else company.exchange
        try:
            return self._google.quote(symbol, exchange, now)
        except AppException as error:
            logging.getLogger(Constants.logger_name).warning("[QUOTES] Google for %s: %s", symbol, error.message)
            if not self._alpaca.is_configured():
                raise AppException(502, f"No price could be fetched for {symbol} right now.") from None
        try:
            return self._alpaca.quote(symbol, now)
        except AppException as error:
            logging.getLogger(Constants.logger_name).warning("[QUOTES] Alpaca for %s: %s", symbol, error.message)
            raise AppException(502, f"No price could be fetched for {symbol} right now.") from None

    def latest(self, symbol: str) -> Quote | None:
        """The last price read, however old, without reading a new one: for
        valuing the portfolio on a page load."""
        return self._store.latest(symbol)

    def history(self, symbol: str, days: int, now: datetime) -> list[DailyBar]:
        """The latest trading days, oldest first. Fetched from Alpaca at most
        once a day per stock; yesterday's bars serve when the fetch fails."""
        wanted = symbol.strip().upper()
        today = self._clock.status(now).now.date()
        if self._store.fetched_on(wanted) != today:
            try:
                self._store.bars_replaced(wanted, self._alpaca.daily(wanted, now), today)
            except AppException as error:
                logging.getLogger(Constants.logger_name).warning("[HISTORY] %s: %s", wanted, error.message)
                if self._store.fetched_on(wanted) is None:
                    raise
        return self._store.bars(wanted, max(1, min(days, MarketConstants.history_max_days)))
