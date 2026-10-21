from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations

from mcp_stock_markets.commands.company_command import CompanyCommand
from mcp_stock_markets.constants.mcp_server_name import McpServerName
from mcp_stock_markets.handlers.mcp_server_handler import McpServerHandler


class Sp500McpServer(McpServerHandler):
    """The `sp500` MCP server: the companies of the S&P 500, from Wikipedia's list."""

    def __init__(self, token: str, companies: CompanyCommand) -> None:
        super().__init__(token)
        self._companies = companies

    @property
    def name(self) -> McpServerName:
        return McpServerName.SP500

    @property
    def instructions(self) -> str:
        return "The members of the S&P 500 index: their symbol, name, GICS sector and sub-industry, and exchange."

    def registered(self, server: MCPServer[Any]) -> None:
        reading = ToolAnnotations(read_only_hint=True, open_world_hint=False)
        self.added(server, self.list_sectors, reading)
        self.added(server, self.search_companies, reading)
        self.added(server, self.get_company, reading)

    def list_sectors(self) -> dict[str, Any]:
        """The GICS sectors of the S&P 500 and how many of its companies each holds."""
        return self.answered(lambda: {"sectors": self._companies.sectors(), "companies": self._companies.count()})

    # MCP tool boundary: a default here is the argument's default in the tool's
    # JSON Schema, as FastAPI's are for a route's parameters.
    def search_companies(self, query: str = "", sector: str = "") -> dict[str, Any]:
        """S&P 500 companies whose symbol or name contains the query (any case),
        within one GICS sector when one is named; at most 25, symbols that start
        with the query first."""
        return self.answered(
            lambda: {"companies": [company.to_dict() for company in self._companies.searched(query, sector)]}
        )

    def get_company(self, symbol: str) -> dict[str, Any]:
        """One S&P 500 company by its ticker symbol (BRK.B for a share class)."""
        return self.answered(lambda: self._companies.company(symbol).to_dict())
