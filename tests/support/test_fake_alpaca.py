from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request

import pytest

from mcp_stock_markets.libraries import web_box as web_box_module
from tests.support.fake_alpaca import FakeAlpaca

URL = "https://data.alpaca.markets/v2/stocks/AAPL/trades/latest?feed=iex"


def helper_request() -> urllib.request.Request:
    return urllib.request.Request(URL, headers={"APCA-API-KEY-ID": "the-id"}, method="GET")


def test___init__() -> None:
    tested = FakeAlpaca([{"trade": {}}])
    result = (tested.outcomes, tested.requests)
    expected = ([{"trade": {}}], [])
    assert result == expected


def test_installed() -> None:
    tested = FakeAlpaca([])
    original = web_box_module.urllib.request.urlopen
    with tested.installed() as installed:
        result = (installed is tested, web_box_module.urllib.request.urlopen is tested)
    expected = (True, True)
    assert result == expected
    exp_restored = original
    assert web_box_module.urllib.request.urlopen is exp_restored


def test___call__() -> None:
    tested = FakeAlpaca([{"trade": {}}, b"<html>Bad gateway</html>"])
    with tested(helper_request(), timeout=15.0) as first, tested(URL) as second:
        result = (json.loads(first.read()), second.read())
    expected = ({"trade": {}}, b"<html>Bad gateway</html>")
    assert result == expected
    exp_requests = [
        (
            "https://data.alpaca.markets/v2/stocks/AAPL/trades/latest",
            {"feed": "iex"},
            "GET",
            15.0,
            {"Apca-api-key-id": "the-id"},
        ),
        (
            "https://data.alpaca.markets/v2/stocks/AAPL/trades/latest",
            {"feed": "iex"},
            "GET",
            socket._GLOBAL_DEFAULT_TIMEOUT,  # type: ignore[attr-defined]
            {},
        ),
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
    tested = FakeAlpaca([error])
    with pytest.raises(type(error)) as exc_info:
        tested(helper_request(), timeout=15.0)
    assert exc_info.value is error
    expected = [
        (
            "https://data.alpaca.markets/v2/stocks/AAPL/trades/latest",
            {"feed": "iex"},
            "GET",
            15.0,
            {"Apca-api-key-id": "the-id"},
        )
    ]
    assert tested.requests == expected


def test_latest_trade() -> None:
    tested = FakeAlpaca
    result = tested.latest_trade("AAPL", 343.99, "2026-10-21T14:58:01.123456789Z")
    expected = {
        "symbol": "AAPL",
        "trade": {
            "t": "2026-10-21T14:58:01.123456789Z",
            "x": "V",
            "p": 343.99,
            "s": 100,
            "c": ["@"],
            "i": 52983525029461,
            "z": "C",
        },
    }
    assert result == expected


def test_bars() -> None:
    tested = FakeAlpaca
    result = tested.bars(
        "AAPL",
        {
            "2026-10-21": (339.36, 345.25, 338.83, 343.99, 35586943),
            "2026-10-20": (338.0, 340.0, 337.0, 339.5, 41000000),
        },
    )
    expected = {
        "bars": [
            {
                "t": "2026-10-20T04:00:00Z",
                "o": 338.0,
                "h": 340.0,
                "l": 337.0,
                "c": 339.5,
                "v": 41000000,
                "n": 632426,
                "vw": 339.5,
            },
            {
                "t": "2026-10-21T04:00:00Z",
                "o": 339.36,
                "h": 345.25,
                "l": 338.83,
                "c": 343.99,
                "v": 35586943,
                "n": 632426,
                "vw": 343.99,
            },
        ],
        "symbol": "AAPL",
        "next_page_token": None,
    }
    assert result == expected
