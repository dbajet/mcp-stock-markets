from __future__ import annotations

from mcp_stock_markets.constants.market_constants import MarketConstants
from mcp_stock_markets.libraries.constituents_parser import ConstituentsParser
from mcp_stock_markets.libraries.web_box import WebBox
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.company import Company


class WikipediaBox:
    """The S&P 500's members, from Wikipedia's "List of S&P 500 companies":
    the table its editors keep current within a day of each index change.
    The columns are found by their header, not their position, so a column
    added to the table moves nothing; a table that lost one is a failure."""

    _SYMBOL = "Symbol"
    _NAME = "Security"
    _SECTOR = "GICS Sector"
    _SUB_INDUSTRY = "GICS Sub-Industry"
    _HEADQUARTERS = "Headquarters Location"

    def __init__(self, web: WebBox) -> None:
        self._web = web

    def constituents(self) -> list[Company]:
        parser = ConstituentsParser()
        parser.feed(self._web.text(MarketConstants.sp500_url, {"User-Agent": MarketConstants.wikipedia_user_agent}))
        parser.close()
        result = self.companies(parser.rows, parser.exchanges)
        if len(result) < MarketConstants.sp500_min_companies:
            raise AppException(502, MarketConstants.sp500_unavailable)
        return result

    @classmethod
    def companies(cls, rows: list[list[str]], exchanges: list[str]) -> list[Company]:
        if not rows:
            return []
        header = rows[0]
        try:
            columns = [header.index(name) for name in (cls._SYMBOL, cls._NAME, cls._SECTOR, cls._SUB_INDUSTRY)]
        except ValueError:
            raise AppException(502, MarketConstants.sp500_unavailable) from None
        headquarters = header.index(cls._HEADQUARTERS) if cls._HEADQUARTERS in header else None
        result: list[Company] = []
        for row, exchange in zip(rows[1:], exchanges[1:], strict=True):
            if len(row) < len(header) or not row[columns[0]]:
                continue
            result.append(
                Company(
                    symbol=row[columns[0]].upper(),
                    name=row[columns[1]],
                    sector=row[columns[2]],
                    sub_industry=row[columns[3]],
                    headquarters="" if headquarters is None else row[headquarters],
                    exchange=exchange,
                )
            )
        return result
