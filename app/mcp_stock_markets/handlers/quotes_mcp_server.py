from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations

from mcp_stock_markets.commands.quote_command import QuoteCommand
from mcp_stock_markets.constants.market_constants import MarketConstants
from mcp_stock_markets.constants.mcp_server_name import McpServerName
from mcp_stock_markets.handlers.mcp_server_handler import McpServerHandler


class QuotesMcpServer(McpServerHandler):
    """The `quotes` MCP server: the market's hours, live prices (Google
    Finance, Alpaca as a fallback) and daily history (Alpaca)."""

    def __init__(self, token: str, quotes: QuoteCommand) -> None:
        super().__init__(token)
        self._quotes = quotes

    @property
    def name(self) -> McpServerName:
        return McpServerName.QUOTES

    @property
    def instructions(self) -> str:
        return "US stock prices: whether the market is open, the latest price of a stock, and its daily history."

    def registered(self, server: MCPServer[Any]) -> None:
        # Prices come from the web: the world they describe moves between calls.
        reading = ToolAnnotations(read_only_hint=True, open_world_hint=True)
        self.added(server, self.get_market_status, reading)
        self.added(server, self.get_quote, reading)
        self.added(server, self.get_daily_history, reading)

    def get_market_status(self) -> dict[str, Any]:
        """Whether the US stock market is open now (New York time), when today's
        session closes if it is, and when the next one opens."""
        return self.answered(lambda: self._quotes.market(datetime.now(UTC)).to_dict())

    def get_quote(self, symbol: str) -> dict[str, Any]:
        """The latest price of a stock in US dollars, the time of the trade it
        comes from (as_of), its age in seconds, and its source."""
        return self.answered(lambda: self.quoted(symbol, datetime.now(UTC)))

    def quoted(self, symbol: str, now: datetime) -> dict[str, Any]:
        quote = self._quotes.quote(symbol, now)
        return quote.to_dict() | {"age_seconds": round(quote.age_seconds(now))}

    # MCP tool boundary: a default here is the argument's default in the tool's JSON Schema.
    def get_daily_history(self, symbol: str, days: int = MarketConstants.history_default_days) -> dict[str, Any]:
        """A stock's last trading days, oldest first: open, high, low, close and
        volume of each (1 to 100 days)."""
        return self.answered(
            lambda: {
                "symbol": symbol.strip().upper(),
                "bars": [bar.to_dict() for bar in self._quotes.history(symbol, days, datetime.now(UTC))],
            }
        )
