from __future__ import annotations

import urllib.error

import pytest

from mcp_stock_markets.libraries.web_box import WebBox
from mcp_stock_markets.libraries.wikipedia_box import WikipediaBox
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.company import Company
from tests.support.fake_wikipedia import FakeWikipedia

URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
AGENT = "mcp-stock-markets/0.1 (a demo of MCP; https://github.com/dbajet/mcp-stock-markets)"
HEADER = [
    "Symbol",
    "Security",
    "GICS Sector",
    "GICS Sub-Industry",
    "Headquarters Location",
    "Date added",
    "CIK",
    "Founded",
]


def test___init__() -> None:
    web = WebBox()
    tested = WikipediaBox(web)
    result = tested._web is web
    assert result is True


def test_constituents() -> None:
    tested = WikipediaBox(WebBox())
    fake = FakeWikipedia([FakeWikipedia.page(FakeWikipedia.members(503))])
    with fake.installed():
        result = tested.constituents()
    # Each member as the fake's input lists it, in the table's order.
    expected = [
        Company(
            symbol=symbol,
            name=name,
            sector=sector,
            sub_industry=sub_industry,
            headquarters=headquarters,
            exchange=exchange,
        )
        for symbol, name, sector, sub_industry, headquarters, exchange in FakeWikipedia.members(503)
    ]
    assert result == expected
    exp_head = [
        Company("MMM", "3M", "Industrials", "Industrial Conglomerates", "Saint Paul, Minnesota", "NYSE"),
        Company("AOS", "A. O. Smith", "Industrials", "Building Products", "Milwaukee, Wisconsin", "NYSE"),
        Company(
            "ABT", "Abbott Laboratories", "Health Care", "Health Care Equipment", "North Chicago, Illinois", "NYSE"
        ),
        Company(
            "ADBE", "Adobe Inc.", "Information Technology", "Application Software", "San Jose, California", "NASDAQ"
        ),
        Company("BRK.B", "Berkshire Hathaway", "Financials", "Multi-Sector Holdings", "Omaha, Nebraska", "NYSE"),
    ]
    assert result[:5] == exp_head
    exp_count = 503
    assert len(result) == exp_count
    exp_requests = [(URL, "GET", AGENT, 15.0)]
    assert fake.requests == exp_requests


@pytest.mark.parametrize(
    "page",
    [
        pytest.param(FakeWikipedia.page(FakeWikipedia.members(449)), id="fewer-than-450"),
        pytest.param("<html><body><p>Wikimedia Error</p></body></html>", id="no-table"),
    ],
)
def test_constituents__a_page_that_changed_shape(page: str) -> None:
    tested = WikipediaBox(WebBox())
    fake = FakeWikipedia([page])
    with fake.installed():
        with pytest.raises(AppException) as exc_info:
            tested.constituents()
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (502, "The S&P 500 list could not be read.")
    assert result == expected
    exp_requests = [(URL, "GET", AGENT, 15.0)]
    assert fake.requests == exp_requests


def test_constituents__wikipedia_refuses() -> None:
    tested = WikipediaBox(WebBox())
    fake = FakeWikipedia([urllib.error.HTTPError(URL, 403, "Forbidden", None, None)])  # type: ignore[arg-type]
    with fake.installed():
        with pytest.raises(AppException) as exc_info:
            tested.constituents()
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (502, "en.wikipedia.org answered HTTP 403.")
    assert result == expected
    exp_requests = [(URL, "GET", AGENT, 15.0)]
    assert fake.requests == exp_requests


@pytest.mark.parametrize(
    "rows, exchanges, expected",
    [
        pytest.param([], [], [], id="no-rows"),
        pytest.param(
            [
                HEADER,
                [
                    "MMM",
                    "3M",
                    "Industrials",
                    "Industrial Conglomerates",
                    "Saint Paul, Minnesota",
                    "1957",
                    "66740",
                    "1902",
                ],
                [
                    "adbe",
                    "Adobe Inc.",
                    "Information Technology",
                    "Application Software",
                    "San Jose",
                    "1997",
                    "1",
                    "1982",
                ],
            ],
            ["NYSE", "NYSE", "NASDAQ"],
            [
                Company("MMM", "3M", "Industrials", "Industrial Conglomerates", "Saint Paul, Minnesota", "NYSE"),
                Company("ADBE", "Adobe Inc.", "Information Technology", "Application Software", "San Jose", "NASDAQ"),
            ],
            id="symbols-upper-cased",
        ),
        pytest.param(
            [
                ["Founded", "GICS Sub-Industry", "Security", "Symbol", "GICS Sector"],
                ["1902", "Industrial Conglomerates", "3M", "MMM", "Industrials"],
            ],
            ["NYSE", "NYSE"],
            [Company("MMM", "3M", "Industrials", "Industrial Conglomerates", "", "NYSE")],
            id="columns-found-by-header-headquarters-optional",
        ),
        pytest.param(
            [
                HEADER,
                ["MMM", "3M", "Industrials"],
                ["", "Vacant", "Industrials", "Building Products", "Milwaukee", "2017", "91142", "1916"],
                ["AOS", "A. O. Smith", "Industrials", "Building Products", "Milwaukee", "2017", "91142", "1916"],
            ],
            ["NYSE", "NYSE", "NYSE", "NYSE"],
            [Company("AOS", "A. O. Smith", "Industrials", "Building Products", "Milwaukee", "NYSE")],
            id="short-rows-and-empty-symbols-skipped",
        ),
    ],
)
def test_companies(rows: list[list[str]], exchanges: list[str], expected: list[Company]) -> None:
    tested = WikipediaBox
    result = tested.companies(rows, exchanges)
    assert result == expected


@pytest.mark.parametrize(
    "header",
    [
        pytest.param(["Ticker", "Security", "GICS Sector", "GICS Sub-Industry"], id="no-symbol"),
        pytest.param(["Symbol", "Company", "GICS Sector", "GICS Sub-Industry"], id="no-security"),
        pytest.param(["Symbol", "Security", "Sector", "GICS Sub-Industry"], id="no-sector"),
        pytest.param(["Symbol", "Security", "GICS Sector", "Industry"], id="no-sub-industry"),
    ],
)
def test_companies__a_table_that_lost_a_column(header: list[str]) -> None:
    tested = WikipediaBox
    with pytest.raises(AppException) as exc_info:
        tested.companies([header, ["MMM", "3M", "Industrials", "Industrial Conglomerates"]], ["NYSE", "NYSE"])
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (502, "The S&P 500 list could not be read.")
    assert result == expected
