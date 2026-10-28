from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request

from mcp_stock_markets.commands.company_command import CompanyCommand
from mcp_stock_markets.commands.quote_command import QuoteCommand
from mcp_stock_markets.handlers.session_guard import SessionGuard
from mcp_stock_markets.handlers.universe_request import UniverseRequest
from mcp_stock_markets.structures.app_exception import AppException


class MarketRouter:
    """The market page: the market's hours, the companies the agent may buy
    with their latest price, and the S&P 500 to choose them from."""

    def __init__(self, guard: SessionGuard, companies: CompanyCommand, quotes: QuoteCommand) -> None:
        self._guard = guard
        self._companies = companies
        self._quotes = quotes

    def router(self) -> APIRouter:
        result = APIRouter(prefix="/api")
        result.add_api_route("/market", self.market, methods=["GET"])
        result.add_api_route("/companies", self.companies, methods=["GET"])
        result.add_api_route("/companies/refresh", self.refreshed, methods=["POST"])
        result.add_api_route("/universe", self.added, methods=["POST"])
        result.add_api_route("/universe/{symbol}", self.removed, methods=["DELETE"])
        return result

    def market(self, request: Request) -> dict[str, Any]:
        self._guard.user(request)
        now = datetime.now(UTC)
        return {
            "status": self._quotes.market(now).to_dict(),
            "limit": self._companies.limit(),
            "universe": [self.priced(company.to_dict(), company.symbol, now) for company in self._companies.universe()],
            "sp500_companies": self._companies.count(),
        }

    def priced(self, company: dict[str, Any], symbol: str, now: datetime) -> dict[str, Any]:
        """A company with its latest price, or with why there is none."""
        try:
            return company | {"quote": self._quotes.quote(symbol, now).to_dict()}
        except AppException as error:
            return company | {"quote": None, "quote_error": error.message}

    def companies(self, request: Request) -> dict[str, Any]:
        """The whole index, about 500 rows, read once by the page, which
        filters it by name and sector without asking again."""
        self._guard.user(request)
        return {
            "companies": [company.to_dict() for company in self._companies.listed()],
            "sectors": self._companies.sectors(),
        }

    def refreshed(self, request: Request) -> dict[str, Any]:
        self._guard.user(request)
        return {"companies": self._companies.refreshed()}

    def added(self, request: Request, body: UniverseRequest) -> dict[str, Any]:
        self._guard.user(request)
        return self._companies.added(body.symbol).to_dict()

    def removed(self, request: Request, symbol: str) -> dict[str, Any]:
        self._guard.user(request)
        self._companies.removed(symbol)
        return {"ok": True}
