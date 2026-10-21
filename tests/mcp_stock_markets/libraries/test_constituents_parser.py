from __future__ import annotations

from html.parser import HTMLParser

import pytest

from mcp_stock_markets.libraries.constituents_parser import ConstituentsParser
from tests.support.fake_wikipedia import FakeWikipedia


def helper_parsed(page: str) -> ConstituentsParser:
    result = ConstituentsParser()
    result.feed(page)
    result.close()
    return result


def test_inheritance() -> None:
    result = issubclass(ConstituentsParser, HTMLParser)
    assert result is True


def test___init__() -> None:
    tested = ConstituentsParser()
    result = (
        tested.rows,
        tested.exchanges,
        tested._depth,
        tested._row,
        tested._cell,
        tested._link,
        tested.convert_charrefs,
    )
    expected = ([], [], 0, None, None, "", True)
    assert result == expected


def test_handle_starttag() -> None:
    """Only inside the constituents table: a row starts, a cell starts, and
    the first cell's first link is kept."""
    tested = ConstituentsParser()
    tested.handle_starttag("tr", [])
    tested.handle_starttag("table", [("id", "changes")])
    outside = (tested._depth, tested._row)
    tested.handle_starttag("table", [("class", "wikitable"), ("id", "constituents")])
    tested.handle_starttag("table", [("class", "nested")])
    tested.handle_starttag("td", [])
    no_row = tested._cell
    tested.handle_starttag("tr", [])
    tested.handle_starttag("td", [])
    tested.handle_starttag("a", [("href", "https://www.nasdaq.com/market-activity/stocks/adbe")])
    tested.handle_starttag("a", [("href", "https://en.wikipedia.org/wiki/Adobe_Inc.")])
    result = (outside, no_row, tested._depth, tested._row, tested._cell, tested._link)
    expected = ((0, None), None, 2, [], [], "https://www.nasdaq.com/market-activity/stocks/adbe")
    assert result == expected


@pytest.mark.parametrize(
    "attrs, expected",
    [
        pytest.param([("href", None)], "", id="an-empty-href"),
        pytest.param([("name", "anchor")], "", id="no-href"),
    ],
)
def test_handle_starttag__a_link_without_a_target(attrs: list[tuple[str, str | None]], expected: str) -> None:
    tested = ConstituentsParser()
    tested.handle_starttag("table", [("id", "constituents")])
    tested.handle_starttag("tr", [])
    tested.handle_starttag("td", [])
    tested.handle_starttag("a", attrs)
    result = tested._link
    assert result == expected


def test_handle_starttag__a_link_after_the_first_cell_is_ignored() -> None:
    tested = ConstituentsParser()
    tested._depth = 1
    tested._row = ["MMM"]
    tested.handle_starttag("a", [("href", "https://www.nasdaq.com/market-activity/stocks/x")])
    result = tested._link
    expected = ""
    assert result == expected


def test_handle_endtag() -> None:
    tested = ConstituentsParser()
    tested.handle_endtag("tr")
    outside = (list(tested.rows), list(tested.exchanges))
    tested._depth = 2
    tested._row = []
    tested._cell = ["  Saint ", "Paul,\n Minnesota "]
    tested.handle_endtag("td")
    tested.handle_endtag("th")
    after_cell = (tested._row, tested._cell)
    tested._link = "https://www.nasdaq.com/market-activity/stocks/adbe"
    tested.handle_endtag("tr")
    tested._row = ["MMM"]
    tested._link = "https://www.nyse.com/quote/XNYS:MMM"
    tested.handle_endtag("tr")
    tested.handle_endtag("tr")
    tested.handle_endtag("table")
    result = (outside, after_cell, tested.rows, tested.exchanges, tested._row, tested._depth)
    expected = (
        ([], []),
        (["Saint Paul, Minnesota"], None),
        [["Saint Paul, Minnesota"], ["MMM"]],
        ["NASDAQ", "NYSE"],
        None,
        1,
    )
    assert result == expected


def test_handle_data() -> None:
    tested = ConstituentsParser()
    tested.handle_data("before any cell")
    before = tested._cell
    tested._cell = ["Saint Paul"]
    tested.handle_data(", Minnesota")
    result = (before, tested._cell)
    expected = (None, ["Saint Paul", ", Minnesota"])
    assert result == expected


def test_feed__a_whole_page() -> None:
    """The page as FakeWikipedia serves it: the header row, then each
    member with its exchange; the changes table after it is not read."""
    tested = helper_parsed(FakeWikipedia.page(FakeWikipedia.members(5)))
    result = (tested.rows, tested.exchanges)
    expected = (
        [
            [
                "Symbol",
                "Security",
                "GICS Sector",
                "GICS Sub-Industry",
                "Headquarters Location",
                "Date added",
                "CIK",
                "Founded",
            ],
            [
                "MMM",
                "3M",
                "Industrials",
                "Industrial Conglomerates",
                "Saint Paul, Minnesota",
                "2001-08-07",
                "0001000000",
                "1927",
            ],
            [
                "AOS",
                "A. O. Smith",
                "Industrials",
                "Building Products",
                "Milwaukee, Wisconsin",
                "2001-08-07",
                "0001000001",
                "1927",
            ],
            [
                "ABT",
                "Abbott Laboratories",
                "Health Care",
                "Health Care Equipment",
                "North Chicago, Illinois",
                "2001-08-07",
                "0001000002",
                "1927",
            ],
            [
                "ADBE",
                "Adobe Inc.",
                "Information Technology",
                "Application Software",
                "San Jose, California",
                "2001-08-07",
                "0001000003",
                "1927",
            ],
            [
                "BRK.B",
                "Berkshire Hathaway",
                "Financials",
                "Multi-Sector Holdings",
                "Omaha, Nebraska",
                "2001-08-07",
                "0001000004",
                "1927",
            ],
        ],
        ["NYSE", "NYSE", "NYSE", "NYSE", "NASDAQ", "NYSE"],
    )
    assert result == expected


def test_feed__a_table_nested_in_a_cell() -> None:
    """A table inside the list's table does not end the list when it closes:
    its rows are read as the list's, and the row around it ends with it."""
    page = (
        '<table id="constituents"><tr><th>Symbol</th></tr>'
        "<tr><td>MMM<table><tr><td>note</td></tr></table></td></tr>"
        '<tr><td><a href="https://www.nasdaq.com/market-activity/stocks/adbe">ADBE</a> &amp; co</td></tr>'
        "</table><table><tr><td>after</td></tr></table>"
    )
    tested = helper_parsed(page)
    result = (tested.rows, tested.exchanges, tested._depth)
    expected = ([["Symbol"], ["note"], ["ADBE & co"]], ["NYSE", "NYSE", "NASDAQ"], 0)
    assert result == expected
