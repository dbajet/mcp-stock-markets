from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from mcp_stock_markets.constants.constants import Constants
from mcp_stock_markets.constants.market_constants import MarketConstants
from mcp_stock_markets.libraries.company_store import CompanyStore
from mcp_stock_markets.libraries.wikipedia_box import WikipediaBox
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.company import Company
from mcp_stock_markets.structures.settings import Settings


class CompanyCommand:
    """The S&P 500, read from Wikipedia once a day, and the market the owner
    chooses from it for the agent: at most MAX_COMPANIES companies."""

    def __init__(self, settings: Settings, store: CompanyStore, wikipedia: WikipediaBox) -> None:
        self._limit = settings.max_companies
        self._store = store
        self._wikipedia = wikipedia

    def refreshed(self) -> int:
        """The list read again and stored; how many companies it holds."""
        return self._store.replaced(self._wikipedia.constituents())

    def is_stale(self, now: datetime) -> bool:
        refreshed_at = self._store.refreshed_at()
        return refreshed_at is None or now - refreshed_at > timedelta(hours=MarketConstants.sp500_refresh_hours)

    def refreshed_if_stale(self, now: datetime) -> None:
        """For the scheduler: a failed read keeps yesterday's list and is tried
        again at the next tick."""
        if not self.is_stale(now):
            return
        try:
            count = self.refreshed()
        except AppException as error:
            logging.getLogger(Constants.logger_name).warning("[SP500] not refreshed: %s", error.message)
            return
        logging.getLogger(Constants.logger_name).info("[SP500] %s companies", count)

    def company(self, symbol: str) -> Company:
        if (result := self._store.company(self.normalized(symbol))) is None:
            raise AppException(404, f"{self.normalized(symbol)} is not in the S&P 500.")
        return result

    def searched(self, query: str, sector: str) -> list[Company]:
        return self._store.searched(query.strip(), sector.strip(), MarketConstants.search_max_results)

    def listed(self) -> list[Company]:
        """Every member: the page has them all, where the agent's search has
        a page of results to keep its context small."""
        return self._store.listed()

    def sectors(self) -> list[dict[str, Any]]:
        return self._store.sectors()

    def count(self) -> int:
        return self._store.count()

    def universe(self) -> list[Company]:
        return self._store.universe_companies()

    def symbols(self) -> list[str]:
        return self._store.universe()

    def limit(self) -> int:
        return self._limit

    def added(self, symbol: str) -> Company:
        """A member of the index, in the market once, while there is room."""
        result = self.company(symbol)
        if result.symbol in self._store.universe():
            raise AppException(409, f"{result.symbol} is already in the agent's market.")
        if not self._store.added(result.symbol, self._limit):
            raise AppException(409, f"The agent's market holds at most {self._limit} companies: remove one first.")
        return result

    def removed(self, symbol: str) -> None:
        """Out of the market: the agent may no longer buy it, and may still
        sell the shares it holds."""
        if not self._store.removed(self.normalized(symbol)):
            raise AppException(404, f"{self.normalized(symbol)} is not in the agent's market.")

    @classmethod
    def normalized(cls, symbol: str) -> str:
        return symbol.strip().upper()
