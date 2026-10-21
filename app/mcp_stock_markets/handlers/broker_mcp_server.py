from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from mcp.server.mcpserver import Context, MCPServer
from mcp_types import ToolAnnotations

from mcp_stock_markets.commands.broker_command import BrokerCommand
from mcp_stock_markets.commands.company_command import CompanyCommand
from mcp_stock_markets.constants.broker_constants import BrokerConstants
from mcp_stock_markets.constants.mcp_constants import McpConstants
from mcp_stock_markets.constants.mcp_server_name import McpServerName
from mcp_stock_markets.handlers.mcp_server_handler import McpServerHandler


class BrokerMcpServer(McpServerHandler):
    """The `broker` MCP server: the owner's virtual portfolio, its
    transactions, and orders. The broker command enforces every rule; this
    server only says which run an order belongs to, from the request's
    header (the agent sets it; a client header proves nothing, which is
    fine for a label)."""

    def __init__(self, token: str, broker: BrokerCommand, companies: CompanyCommand) -> None:
        super().__init__(token)
        self._broker = broker
        self._companies = companies

    @property
    def name(self) -> McpServerName:
        return McpServerName.BROKER

    @property
    def instructions(self) -> str:
        return (
            "A virtual brokerage account: its cash, its positions, its transactions, and buy and sell orders "
            "at the latest price, in whole shares, while the US market is open. Cash never goes below zero."
        )

    def registered(self, server: MCPServer[Any]) -> None:
        reading = ToolAnnotations(read_only_hint=True, open_world_hint=False)
        # An order changes the account, and another order would change it again.
        ordering = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False)
        self.added(server, self.get_portfolio, reading)
        self.added(server, self.get_transactions, reading)
        self.added(server, self.buy, ordering)
        self.added(server, self.sell, ordering)

    def get_portfolio(self) -> dict[str, Any]:
        """The account: its starting budget, its cash, each position (shares,
        what they cost, their value at the latest price), the total value, and
        the market — the only companies that may be bought."""
        return self.answered(self.portfolio)

    def portfolio(self) -> dict[str, Any]:
        view = self._broker.view(self._broker.owner_portfolio(), datetime.now(UTC))
        return view.to_dict() | {"market": [company.to_dict() for company in self._companies.universe()]}

    # MCP tool boundary: a default here is the argument's default in the tool's JSON Schema.
    def get_transactions(self, limit: int = BrokerConstants.transactions_page) -> dict[str, Any]:
        """The account's latest transactions, newest first: time, symbol, buy or
        sell, shares, price, amount, cash after, and the reason given."""
        return self.answered(
            lambda: {
                "transactions": [
                    trade.to_dict() for trade in self._broker.trades(self._broker.owner_portfolio(), limit)
                ]
            }
        )

    def buy(self, symbol: str, quantity: int, reason: str, ctx: Context) -> dict[str, Any]:
        """Buy whole shares of a company of the market at its latest price. Refused
        when the market is closed, the company is not in the market, the price is
        stale, or the cash does not cover it. Give a short reason."""
        return self.answered(
            lambda: self._broker.bought(symbol, quantity, reason, self.run_of(ctx), datetime.now(UTC)).to_dict()
        )

    def sell(self, symbol: str, quantity: int, reason: str, ctx: Context) -> dict[str, Any]:
        """Sell whole shares the account holds at their latest price. Refused when
        the market is closed, the account holds fewer shares, or the price is
        stale. Give a short reason."""
        return self.answered(
            lambda: self._broker.sold(symbol, quantity, reason, self.run_of(ctx), datetime.now(UTC)).to_dict()
        )

    @classmethod
    def run_of(cls, ctx: Context) -> int | None:
        """The agent run the order belongs to; none for another client."""
        raw = (ctx.headers or {}).get(McpConstants.run_header, "")
        return int(raw) if raw.isdigit() and int(raw) > 0 else None
