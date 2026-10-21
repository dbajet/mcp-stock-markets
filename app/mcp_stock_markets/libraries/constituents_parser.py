from __future__ import annotations

from html.parser import HTMLParser

from mcp_stock_markets.constants.market_constants import MarketConstants


class ConstituentsParser(HTMLParser):
    """The rows of Wikipedia's S&P 500 table (`id="constituents"`), each a
    list of its cells' text, and the exchange each first cell's quote link
    names (nyse.com or nasdaq.com). A stateful reader, as HTMLParser is:
    one instance per page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self.exchanges: list[str] = []
        self._depth = 0
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._link = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "table":
            if self._depth or attributes.get("id") == MarketConstants.sp500_table_id:
                self._depth += 1
            return
        if not self._depth:
            return
        if tag == "tr":
            self._row = []
            self._link = ""
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        elif tag == "a" and self._row is not None and not self._row and not self._link:
            self._link = attributes.get("href") or ""

    def handle_endtag(self, tag: str) -> None:
        if not self._depth:
            return
        if tag == "table":
            self._depth -= 1
        elif tag in ("td", "th") and self._row is not None and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            is_nasdaq = MarketConstants.nasdaq_link_marker in self._link
            self.exchanges.append(MarketConstants.exchange_nasdaq if is_nasdaq else MarketConstants.exchange_nyse)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)
