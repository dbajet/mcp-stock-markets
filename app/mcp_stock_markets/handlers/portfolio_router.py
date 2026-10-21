from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request

from mcp_stock_markets.commands.broker_command import BrokerCommand
from mcp_stock_markets.constants.broker_constants import BrokerConstants
from mcp_stock_markets.handlers.session_guard import SessionGuard


class PortfolioRouter:
    """The portfolio page: the signed-in owner's own portfolio, its
    transactions and the points of its chart. Read only: orders are the
    agent's, through the broker MCP server."""

    def __init__(self, guard: SessionGuard, broker: BrokerCommand) -> None:
        self._guard = guard
        self._broker = broker

    def router(self) -> APIRouter:
        result = APIRouter(prefix="/api")
        result.add_api_route("/portfolio", self.portfolio, methods=["GET"])
        result.add_api_route("/trades", self.trades, methods=["GET"])
        result.add_api_route("/valuations", self.valuations, methods=["GET"])
        return result

    def portfolio(self, request: Request) -> dict[str, Any]:
        portfolio = self._broker.portfolio_for(self._guard.user(request).user_id)
        return self._broker.view(portfolio, datetime.now(UTC)).to_dict()

    def trades(self, request: Request, limit: int = BrokerConstants.max_transactions_page) -> dict[str, Any]:
        portfolio = self._broker.portfolio_for(self._guard.user(request).user_id)
        return {"trades": [trade.to_dict() for trade in self._broker.trades(portfolio, limit)]}

    def valuations(self, request: Request) -> dict[str, Any]:
        portfolio = self._broker.portfolio_for(self._guard.user(request).user_id)
        return {
            "starting_budget": str(portfolio.starting_budget),
            "valuations": [valuation.to_dict() for valuation in self._broker.valuations(portfolio)],
        }
