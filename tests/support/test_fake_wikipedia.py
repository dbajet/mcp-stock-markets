from __future__ import annotations

import hashlib
import socket
import urllib.error
import urllib.request

import pytest

from mcp_stock_markets.libraries import web_box as web_box_module
from tests.support.fake_wikipedia import FakeWikipedia

URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def helper_request() -> urllib.request.Request:
    return urllib.request.Request(URL, headers={"User-Agent": "mcp-stock-markets/0.1"}, method="GET")


def test___init__() -> None:
    tested = FakeWikipedia(["<html></html>"])
    result = (tested.outcomes, tested.requests)
    expected = (["<html></html>"], [])
    assert result == expected


def test_installed() -> None:
    tested = FakeWikipedia([])
    original = web_box_module.urllib.request.urlopen
    with tested.installed() as installed:
        result = (installed is tested, web_box_module.urllib.request.urlopen is tested)
    expected = (True, True)
    assert result == expected
    exp_restored = original
    assert web_box_module.urllib.request.urlopen is exp_restored


def test___call__() -> None:
    tested = FakeWikipedia(["<p>S&amp;P</p>", b"\xff"])
    with tested(helper_request(), timeout=15.0) as first, tested(URL) as second:
        result = (first.read(), second.read())
    expected = (b"<p>S&amp;P</p>", b"\xff")
    assert result == expected
    exp_requests = [
        (URL, "GET", "mcp-stock-markets/0.1", 15.0),
        (URL, "GET", None, socket._GLOBAL_DEFAULT_TIMEOUT),  # type: ignore[attr-defined]
    ]
    assert tested.requests == exp_requests
    exp_left: list[object] = []
    assert tested.outcomes == exp_left


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(urllib.error.HTTPError(URL, 403, "Forbidden", None, None), id="status"),  # type: ignore[arg-type]
        pytest.param(urllib.error.URLError("unreachable"), id="unreachable"),
        pytest.param(TimeoutError("timed out"), id="timeout"),
    ],
)
def test___call____fails_as_urllib_does(error: BaseException) -> None:
    tested = FakeWikipedia([error])
    with pytest.raises(type(error)) as exc_info:
        tested(helper_request(), timeout=15.0)
    assert exc_info.value is error
    expected = [(URL, "GET", "mcp-stock-markets/0.1", 15.0)]
    assert tested.requests == expected


@pytest.mark.parametrize(
    "count, expected",
    [
        pytest.param(
            2,
            [
                ("MMM", "3M", "Industrials", "Industrial Conglomerates", "Saint Paul, Minnesota", "NYSE"),
                ("AOS", "A. O. Smith", "Industrials", "Building Products", "Milwaukee, Wisconsin", "NYSE"),
            ],
            id="fewer-than-the-real-ones",
        ),
        pytest.param(
            9,
            [
                ("MMM", "3M", "Industrials", "Industrial Conglomerates", "Saint Paul, Minnesota", "NYSE"),
                ("AOS", "A. O. Smith", "Industrials", "Building Products", "Milwaukee, Wisconsin", "NYSE"),
                (
                    "ABT",
                    "Abbott Laboratories",
                    "Health Care",
                    "Health Care Equipment",
                    "North Chicago, Illinois",
                    "NYSE",
                ),
                (
                    "ADBE",
                    "Adobe Inc.",
                    "Information Technology",
                    "Application Software",
                    "San Jose, California",
                    "NASDAQ",
                ),
                ("BRK.B", "Berkshire Hathaway", "Financials", "Multi-Sector Holdings", "Omaha, Nebraska", "NYSE"),
                ("Z000", "Company 0", "Utilities", "Electric Utilities", "City 0, Ohio", "NASDAQ"),
                ("Z001", "Company 1", "Utilities", "Electric Utilities", "City 1, Ohio", "NYSE"),
                ("Z002", "Company 2", "Utilities", "Electric Utilities", "City 2, Ohio", "NYSE"),
                ("Z003", "Company 3", "Utilities", "Electric Utilities", "City 3, Ohio", "NASDAQ"),
            ],
            id="generated-after-the-real-ones",
        ),
    ],
)
def test_members(count: int, expected: list[tuple[str, ...]]) -> None:
    tested = FakeWikipedia
    result = tested.members(count)
    assert result == expected


def test_page() -> None:
    tested = FakeWikipedia
    result = tested.page(tested.members(4))
    expected = "68de815c58b1eea12ad1778c38175796"
    assert hashlib.md5(result.encode()).hexdigest() == expected, result
    exp_nasdaq_cell = (
        '<td><a rel="mw:ExtLink nofollow" href="https://www.nasdaq.com/market-activity/stocks/adbe" '
        'class="external text">ADBE</a></td>'
    )
    assert exp_nasdaq_cell in result


def test__row() -> None:
    tested = FakeWikipedia
    result = tested._row(
        2, ("ABT", "Abbott Laboratories", "Health Care", "Health Care Equipment", "North Chicago, Illinois", "NYSE")
    )
    expected = (
        '<tr>\n<td><a rel="mw:ExtLink nofollow" href="https://www.nyse.com/quote/XNYS:ABT" class="external text">'
        "ABT</a></td>\n"
        '<td><a rel="mw:WikiLink" href="https://en.wikipedia.org/wiki/Abbott_Laboratories">Abbott Laboratories</a>'
        "</td>\n<td>Health Care</td>\n<td>Health Care Equipment</td>\n"
        '<td><a rel="mw:WikiLink" href="https://en.wikipedia.org/wiki/North_Chicago">North Chicago</a>, '
        "Illinois</td>\n<td>2001-08-07</td>\n<td>0001000002</td>\n<td>1927</td></tr>\n"
    )
    assert result == expected
