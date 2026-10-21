from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import call, patch

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from mcp_stock_markets.commands.company_command import CompanyCommand
from mcp_stock_markets.constants.mcp_server_name import McpServerName
from mcp_stock_markets.handlers.mcp_server_handler import McpServerHandler
from mcp_stock_markets.handlers.sp500_mcp_server import Sp500McpServer
from mcp_stock_markets.libraries.company_store import CompanyStore
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.libraries.web_box import WebBox
from mcp_stock_markets.libraries.wikipedia_box import WikipediaBox
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.company import Company
from mcp_stock_markets.structures.settings import Settings


def helper_settings() -> Settings:
    return Settings(
        environment="dev",
        database_url="postgresql://u:p@h/d",
        app_version="v",
        build_time="b",
        app_commit="c",
        app_base_url="https://stocks.example.com",
        data_key="Zm9yLXRlc3RzLW9ubHktZm9yLXRlc3RzLW9ubHktMzI=",
        smtp_host="",
        smtp_port=587,
        smtp_user="",
        smtp_password="",
        email_from="",
        bootstrap_admin_email="",
        starting_budget=Decimal("500.00"),
        max_companies=5,
        alpha_vantage_key="",
        agent_interval_minutes=30,
        mcp_base_url="http://127.0.0.1:8000",
        mcp_token="mcp-token",
    )


def helper_companies() -> CompanyCommand:
    settings = helper_settings()
    return CompanyCommand(settings, CompanyStore(Database(settings.database_url)), WikipediaBox(WebBox()))


def helper_company(symbol: str, name: str) -> Company:
    return Company(
        symbol=symbol,
        name=name,
        sector="Information Technology",
        sub_industry="Technology Hardware, Storage & Peripherals",
        headquarters="Cupertino, California",
        exchange="NASDAQ",
    )


def helper_company_dict(symbol: str, name: str) -> dict[str, str]:
    return {
        "symbol": symbol,
        "name": name,
        "sector": "Information Technology",
        "sub_industry": "Technology Hardware, Storage & Peripherals",
        "headquarters": "Cupertino, California",
        "exchange": "NASDAQ",
    }


def test_inheritance() -> None:
    tested = Sp500McpServer
    result = issubclass(tested, McpServerHandler)
    assert result is True


def test___init__() -> None:
    companies = helper_companies()
    tested = Sp500McpServer("tok-1", companies)
    result = (tested._token, tested._companies, tested._server)
    expected = ("tok-1", companies, None)
    assert result == expected


def test_name() -> None:
    tested = Sp500McpServer("tok-1", helper_companies())
    result = tested.name
    expected = McpServerName.SP500
    assert result == expected


def test_instructions() -> None:
    tested = Sp500McpServer("tok-1", helper_companies())
    result = tested.instructions
    expected = "The members of the S&P 500 index: their symbol, name, GICS sector and sub-industry, and exchange."
    assert result == expected


def test_registered() -> None:
    """The listing the model reads: names, descriptions (the docstrings), schemas, hints."""
    tested = Sp500McpServer("tok-1", helper_companies())
    server: MCPServer[None] = MCPServer(name="probe")
    tested.registered(server)
    result = [tool.model_dump(exclude_none=True) for tool in asyncio.run(server.list_tools())]
    reading = {"read_only_hint": True, "open_world_hint": False}
    expected = [
        {
            "name": "list_sectors",
            "description": "The GICS sectors of the S&P 500 and how many of its companies each holds.",
            "input_schema": {"properties": {}, "title": "list_sectorsArguments", "type": "object"},
            "output_schema": {"additionalProperties": True, "title": "list_sectorsDictOutput", "type": "object"},
            "annotations": reading,
        },
        {
            "name": "search_companies",
            "description": (
                "S&P 500 companies whose symbol or name contains the query (any case),\n"
                "within one GICS sector when one is named; at most 25, symbols that start\n"
                "with the query first."
            ),
            "input_schema": {
                "properties": {
                    "query": {"default": "", "title": "Query", "type": "string"},
                    "sector": {"default": "", "title": "Sector", "type": "string"},
                },
                "title": "search_companiesArguments",
                "type": "object",
            },
            "output_schema": {"additionalProperties": True, "title": "search_companiesDictOutput", "type": "object"},
            "annotations": reading,
        },
        {
            "name": "get_company",
            "description": "One S&P 500 company by its ticker symbol (BRK.B for a share class).",
            "input_schema": {
                "properties": {"symbol": {"title": "Symbol", "type": "string"}},
                "required": ["symbol"],
                "title": "get_companyArguments",
                "type": "object",
            },
            "output_schema": {"additionalProperties": True, "title": "get_companyDictOutput", "type": "object"},
            "annotations": reading,
        },
    ]
    assert result == expected


def test_list_sectors() -> None:
    tested = Sp500McpServer("tok-1", helper_companies())
    sectors = [{"sector": "Energy", "companies": 22}, {"sector": "Utilities", "companies": 31}]
    with (
        patch.object(CompanyCommand, "sectors", side_effect=[sectors]) as mock_sectors,
        patch.object(CompanyCommand, "count", side_effect=[503]) as mock_count,
    ):
        result = tested.list_sectors()
    expected = {
        "sectors": [{"sector": "Energy", "companies": 22}, {"sector": "Utilities", "companies": 31}],
        "companies": 503,
    }
    assert result == expected
    exp_calls = [call()]
    assert mock_sectors.mock_calls == exp_calls
    assert mock_count.mock_calls == exp_calls


def test_search_companies() -> None:
    tested = Sp500McpServer("tok-1", helper_companies())
    found = [helper_company("AAPL", "Apple Inc."), helper_company("APH", "Amphenol")]
    with patch.object(CompanyCommand, "searched", side_effect=[found]) as mock_searched:
        result = tested.search_companies("ap", "Information Technology")
    expected = {"companies": [helper_company_dict("AAPL", "Apple Inc."), helper_company_dict("APH", "Amphenol")]}
    assert result == expected
    exp_calls = [call("ap", "Information Technology")]
    assert mock_searched.mock_calls == exp_calls


def test_get_company() -> None:
    tested = Sp500McpServer("tok-1", helper_companies())
    with patch.object(CompanyCommand, "company", side_effect=[helper_company("AAPL", "Apple Inc.")]) as mock_company:
        result = tested.get_company("aapl")
    expected = helper_company_dict("AAPL", "Apple Inc.")
    assert result == expected
    exp_calls = [call("aapl")]
    assert mock_company.mock_calls == exp_calls


def test_get_company__unknown_symbol_is_a_tool_error() -> None:
    tested = Sp500McpServer("tok-1", helper_companies())
    with (
        patch.object(
            CompanyCommand, "company", side_effect=[AppException(404, "ZZZZ is not in the S&P 500.")]
        ) as mock_company,
        pytest.raises(ToolError) as exc_info,
    ):
        tested.get_company("zzzz")
    result = str(exc_info.value)
    expected = "ZZZZ is not in the S&P 500."
    assert result == expected
    exp_calls = [call("zzzz")]
    assert mock_company.mock_calls == exp_calls
