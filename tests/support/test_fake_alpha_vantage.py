from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request

import pytest

from mcp_stock_markets.libraries import web_box as web_box_module
from tests.support.fake_alpha_vantage import FakeAlphaVantage

URL = "https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=AAPL&apikey=the-key"


def helper_request() -> urllib.request.Request:
    return urllib.request.Request(URL, headers={}, method="GET")


def test___init__() -> None:
    tested = FakeAlphaVantage([{"Global Quote": {}}])
    result = (tested.outcomes, tested.requests)
    expected = ([{"Global Quote": {}}], [])
    assert result == expected


def test_installed() -> None:
    tested = FakeAlphaVantage([])
    original = web_box_module.urllib.request.urlopen
    with tested.installed() as installed:
        result = (installed is tested, web_box_module.urllib.request.urlopen is tested)
    expected = (True, True)
    assert result == expected
    exp_restored = original
    assert web_box_module.urllib.request.urlopen is exp_restored


def test___call__() -> None:
    tested = FakeAlphaVantage([{"Global Quote": {}}, b"<html>Bad gateway</html>"])
    with tested(helper_request(), timeout=15.0) as first, tested(URL) as second:
        result = (json.loads(first.read()), second.read())
    expected = ({"Global Quote": {}}, b"<html>Bad gateway</html>")
    assert result == expected
    exp_query = {"function": "GLOBAL_QUOTE", "symbol": "AAPL", "apikey": "the-key"}
    exp_requests = [
        ("https://www.alphavantage.co/query", exp_query, "GET", 15.0),
        ("https://www.alphavantage.co/query", exp_query, "GET", socket._GLOBAL_DEFAULT_TIMEOUT),  # type: ignore[attr-defined]
    ]
    assert tested.requests == exp_requests
    exp_left: list[object] = []
    assert tested.outcomes == exp_left


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(urllib.error.HTTPError(URL, 500, "Server Error", None, None), id="status"),  # type: ignore[arg-type]
        pytest.param(urllib.error.URLError("unreachable"), id="unreachable"),
        pytest.param(TimeoutError("timed out"), id="timeout"),
    ],
)
def test___call____fails_as_urllib_does(error: BaseException) -> None:
    tested = FakeAlphaVantage([error])
    with pytest.raises(type(error)) as exc_info:
        tested(helper_request(), timeout=15.0)
    assert exc_info.value is error
    expected = [
        (
            "https://www.alphavantage.co/query",
            {"function": "GLOBAL_QUOTE", "symbol": "AAPL", "apikey": "the-key"},
            "GET",
            15.0,
        )
    ]
    assert tested.requests == expected


def test_global_quote() -> None:
    tested = FakeAlphaVantage
    result = tested.global_quote("AAPL", "343.9900", "2026-10-21")
    expected = {
        "Global Quote": {
            "01. symbol": "AAPL",
            "02. open": "339.3600",
            "03. high": "345.2500",
            "04. low": "338.8300",
            "05. price": "343.9900",
            "06. volume": "35586943",
            "07. latest trading day": "2026-10-21",
            "08. previous close": "339.5000",
            "09. change": "4.4900",
            "10. change percent": "1.3225%",
        }
    }
    assert result == expected


def test_daily_series() -> None:
    tested = FakeAlphaVantage
    result = tested.daily_series(
        "AAPL",
        {
            "2026-10-20": ("338.0000", "340.0000", "337.0000", "339.5000", "41000000"),
            "2026-10-21": ("339.3600", "345.2500", "338.8300", "343.9900", "35586943"),
        },
    )
    expected = {
        "Meta Data": {
            "1. Information": "Daily Prices (open, high, low, close) and Volumes",
            "2. Symbol": "AAPL",
            "3. Last Refreshed": "2026-10-21",
            "4. Output Size": "Compact",
            "5. Time Zone": "US/Eastern",
        },
        "Time Series (Daily)": {
            "2026-10-21": {
                "1. open": "339.3600",
                "2. high": "345.2500",
                "3. low": "338.8300",
                "4. close": "343.9900",
                "5. volume": "35586943",
            },
            "2026-10-20": {
                "1. open": "338.0000",
                "2. high": "340.0000",
                "3. low": "337.0000",
                "4. close": "339.5000",
                "5. volume": "41000000",
            },
        },
    }
    assert result == expected
    # Newest day first, as Alpha Vantage writes the series.
    exp_order = ["2026-10-21", "2026-10-20"]
    assert list(result["Time Series (Daily)"]) == exp_order


def test_daily_series__no_bars() -> None:
    tested = FakeAlphaVantage
    result = tested.daily_series("AAPL", {})
    expected = {
        "Meta Data": {
            "1. Information": "Daily Prices (open, high, low, close) and Volumes",
            "2. Symbol": "AAPL",
            "3. Last Refreshed": "",
            "4. Output Size": "Compact",
            "5. Time Zone": "US/Eastern",
        },
        "Time Series (Daily)": {},
    }
    assert result == expected


@pytest.mark.parametrize(
    "note, expected",
    [
        pytest.param(
            "Information",
            {
                "Information": "We have detected your API key as demo and our standard API rate limit is 25 "
                "requests per day. Please subscribe to any of the premium plans at "
                "https://www.alphavantage.co/premium/ to instantly remove all daily rate limits."
            },
            id="daily-limit",
        ),
        pytest.param(
            "Note",
            {
                "Note": "Thank you for using Alpha Vantage! Our standard API call frequency is 5 calls per "
                "minute and 500 calls per day."
            },
            id="minute-limit",
        ),
        pytest.param(
            "Error Message",
            {
                "Error Message": "Invalid API call. Please retry or visit the documentation "
                "(https://www.alphavantage.co/documentation/) for TIME_SERIES_DAILY."
            },
            id="bad-call",
        ),
    ],
)
def test_refusal(note: str, expected: dict[str, str]) -> None:
    tested = FakeAlphaVantage
    result = tested.refusal(note)
    assert result == expected
