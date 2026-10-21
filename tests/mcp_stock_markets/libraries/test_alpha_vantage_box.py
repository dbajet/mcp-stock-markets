from __future__ import annotations

import threading
import urllib.error
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from mcp_stock_markets.constants.quote_source import QuoteSource
from mcp_stock_markets.libraries import alpha_vantage_box as alpha_vantage_box_module
from mcp_stock_markets.libraries.alpha_vantage_box import AlphaVantageBox
from mcp_stock_markets.libraries.web_box import WebBox
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.daily_bar import DailyBar
from mcp_stock_markets.structures.quote import Quote
from tests.support.fake_alpha_vantage import FakeAlphaVantage
from tests.support.fake_clock import FakeClock

NOW = datetime(2026, 10, 21, 23, 0, tzinfo=UTC)
URL = "https://www.alphavantage.co/query"


def helper_instance(key: str) -> AlphaVantageBox:
    return AlphaVantageBox(WebBox(), key)


def helper_query(function: str, symbol: str) -> dict[str, str]:
    return {"function": function, "symbol": symbol, "apikey": "the-key"}


def test___init__() -> None:
    web = WebBox()
    tested = AlphaVantageBox(web, "the-key")
    result = (
        tested._web is web,
        tested._key,
        tested._zone,
        type(tested._spacing),
        tested._last_request,
    )
    expected = (True, "the-key", ZoneInfo("America/New_York"), type(threading.Lock()), 0.0)
    assert result == expected


@pytest.mark.parametrize(
    "key, expected",
    [
        pytest.param("the-key", True, id="a-key"),
        pytest.param("", False, id="no-key"),
    ],
)
def test_is_configured(key: str, expected: bool) -> None:
    tested = helper_instance(key)
    result = tested.is_configured()
    assert result is expected


def test_quote() -> None:
    tested = helper_instance("the-key")
    fake = FakeAlphaVantage(
        [
            FakeAlphaVantage.global_quote("AAPL", "343.9900", "2026-10-21"),
            FakeAlphaVantage.global_quote("BRK-B", "512.12345", "2026-10-20"),
        ]
    )
    clock = FakeClock(1000.0)
    with fake.installed(), clock.installed(alpha_vantage_box_module):
        result = (tested.quote("AAPL", NOW), tested.quote("BRK.B", NOW))
    # Dated by its trading day, read as that day's close in New York.
    expected = (
        Quote(
            symbol="AAPL",
            price=Decimal("343.9900"),
            currency="USD",
            as_of=datetime(2026, 10, 21, 16, 0, tzinfo=ZoneInfo("America/New_York")),
            source=QuoteSource.ALPHA_VANTAGE,
            fetched_at=NOW,
        ),
        Quote(
            symbol="BRK.B",
            price=Decimal("512.1234"),
            currency="USD",
            as_of=datetime(2026, 10, 20, 16, 0, tzinfo=ZoneInfo("America/New_York")),
            source=QuoteSource.ALPHA_VANTAGE,
            fetched_at=NOW,
        ),
    )
    assert result == expected
    exp_requests = [
        (URL, helper_query("GLOBAL_QUOTE", "AAPL"), "GET", 15.0),
        (URL, helper_query("GLOBAL_QUOTE", "BRK-B"), "GET", 15.0),
    ]
    assert fake.requests == exp_requests


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param({"Global Quote": {}}, id="an-unknown-symbol"),
        pytest.param({"Global Quote": "AAPL"}, id="not-an-object"),
        pytest.param(FakeAlphaVantage.global_quote("AAPL", "0.0000", "2026-10-21"), id="a-zero-price"),
        pytest.param(FakeAlphaVantage.global_quote("AAPL", "n/a", "2026-10-21"), id="a-price-not-a-number"),
        pytest.param(FakeAlphaVantage.global_quote("AAPL", "343.9900", "21/10/2026"), id="a-day-not-iso"),
    ],
)
def test_quote__no_quote(answer: dict[str, Any]) -> None:
    tested = helper_instance("the-key")
    fake = FakeAlphaVantage([answer])
    with fake.installed(), FakeClock(1000.0).installed(alpha_vantage_box_module):
        with pytest.raises(AppException) as exc_info:
            tested.quote("AAPL", NOW)
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (502, "Alpha Vantage has no quote for AAPL.")
    assert result == expected
    exp_requests = [(URL, helper_query("GLOBAL_QUOTE", "AAPL"), "GET", 15.0)]
    assert fake.requests == exp_requests


def test_daily() -> None:
    tested = helper_instance("the-key")
    fake = FakeAlphaVantage(
        [
            FakeAlphaVantage.daily_series(
                "AAPL",
                {
                    "2026-10-19": ("336.1000", "338.9000", "335.5000", "338.2000", "39000000"),
                    "2026-10-21": ("339.3600", "345.2500", "338.8300", "343.9900", "35586943"),
                    "2026-10-20": ("338.0000", "340.0000", "337.0000", "339.5000", "41000000"),
                },
            )
        ]
    )
    with fake.installed(), FakeClock(1000.0).installed(alpha_vantage_box_module):
        result = tested.daily("BRK.B")
    # Oldest first, whatever order the answer has.
    expected = [
        DailyBar(
            symbol="BRK.B",
            day=date(2026, 10, 19),
            open=Decimal("336.1000"),
            high=Decimal("338.9000"),
            low=Decimal("335.5000"),
            close=Decimal("338.2000"),
            volume=39000000,
        ),
        DailyBar(
            symbol="BRK.B",
            day=date(2026, 10, 20),
            open=Decimal("338.0000"),
            high=Decimal("340.0000"),
            low=Decimal("337.0000"),
            close=Decimal("339.5000"),
            volume=41000000,
        ),
        DailyBar(
            symbol="BRK.B",
            day=date(2026, 10, 21),
            open=Decimal("339.3600"),
            high=Decimal("345.2500"),
            low=Decimal("338.8300"),
            close=Decimal("343.9900"),
            volume=35586943,
        ),
    ]
    assert result == expected
    exp_requests = [(URL, helper_query("TIME_SERIES_DAILY", "BRK-B"), "GET", 15.0)]
    assert fake.requests == exp_requests


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param({"Meta Data": {}}, id="no-series"),
        pytest.param({"Time Series (Daily)": ["2026-10-21"]}, id="a-series-not-an-object"),
        pytest.param({"Time Series (Daily)": {"2026-10-21": None}}, id="a-bar-not-an-object"),
        pytest.param({"Time Series (Daily)": {"2026-10-21": {"1. open": "339.3600"}}}, id="a-bar-missing-fields"),
        pytest.param(
            FakeAlphaVantage.daily_series("AAPL", {"2026-10-21": ("n/a", "345.25", "338.83", "343.99", "35586943")}),
            id="a-price-not-a-number",
        ),
        pytest.param(
            FakeAlphaVantage.daily_series("AAPL", {"2026-10-21": ("339.36", "345.25", "338.83", "343.99", "many")}),
            id="a-volume-not-a-number",
        ),
        pytest.param(
            FakeAlphaVantage.daily_series("AAPL", {"21/10/2026": ("339.36", "345.25", "338.83", "343.99", "1")}),
            id="a-day-not-iso",
        ),
    ],
)
def test_daily__no_history(answer: dict[str, Any]) -> None:
    tested = helper_instance("the-key")
    fake = FakeAlphaVantage([answer])
    with fake.installed(), FakeClock(1000.0).installed(alpha_vantage_box_module):
        with pytest.raises(AppException) as exc_info:
            tested.daily("AAPL")
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (502, "Alpha Vantage has no daily history for AAPL.")
    assert result == expected
    exp_requests = [(URL, helper_query("TIME_SERIES_DAILY", "AAPL"), "GET", 15.0)]
    assert fake.requests == exp_requests


@pytest.mark.parametrize(
    "symbol, expected",
    [
        pytest.param("AAPL", "AAPL", id="plain"),
        pytest.param("BRK.B", "BRK-B", id="a-share-class"),
    ],
)
def test_api_symbol(symbol: str, expected: str) -> None:
    tested = AlphaVantageBox
    result = tested.api_symbol(symbol)
    assert result == expected


def test_answer() -> None:
    tested = helper_instance("the-key")
    fake = FakeAlphaVantage([{"Global Quote": {"05. price": "1.0000"}}])
    clock = FakeClock(1000.0)
    with fake.installed(), clock.installed(alpha_vantage_box_module):
        result = tested.answer({"function": "GLOBAL_QUOTE", "symbol": "AAPL"})
    expected = {"Global Quote": {"05. price": "1.0000"}}
    assert result == expected
    # The key travels in the query string, as Alpha Vantage requires.
    exp_requests = [(URL, helper_query("GLOBAL_QUOTE", "AAPL"), "GET", 15.0)]
    assert fake.requests == exp_requests
    exp_clock = [("monotonic",), ("monotonic",)]
    assert clock.calls == exp_clock


def test_answer__no_key() -> None:
    tested = helper_instance("")
    fake = FakeAlphaVantage([])
    clock = FakeClock(1000.0)
    with fake.installed(), clock.installed(alpha_vantage_box_module):
        with pytest.raises(AppException) as exc_info:
            tested.answer({"function": "GLOBAL_QUOTE", "symbol": "AAPL"})
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (503, "Daily history needs an Alpha Vantage key (ALPHA_VANTAGE_API_KEY).")
    assert result == expected
    # Refused before any request, and before any waiting.
    exp_requests: list[tuple[Any, ...]] = []
    assert fake.requests == exp_requests
    exp_clock: list[tuple[Any, ...]] = []
    assert clock.calls == exp_clock


@pytest.mark.parametrize(
    "outcome, exp_status, exp_message",
    [
        pytest.param(b"<html>Bad gateway</html>", 502, "Alpha Vantage's answer is not JSON.", id="not-json"),
        pytest.param(b'["AAPL"]', 502, "Alpha Vantage's answer is not a JSON object.", id="not-an-object"),
        pytest.param(
            FakeAlphaVantage.refusal("Information"),
            503,
            "Alpha Vantage refused the request: We have detected your API key as demo and our standard API rate "
            "limit is 25 requests per day. Please subscribe to any of the premium plans at "
            "https://www.alphavantage.co/premium/ to instantly remove a",
            id="the-daily-limit-cut-to-200-characters",
        ),
        pytest.param(
            FakeAlphaVantage.refusal("Note"),
            503,
            "Alpha Vantage refused the request: Thank you for using Alpha Vantage! Our standard API call frequency "
            "is 5 calls per minute and 500 calls per day.",
            id="the-minute-limit",
        ),
        pytest.param(
            FakeAlphaVantage.refusal("Error Message"),
            503,
            "Alpha Vantage refused the request: Invalid API call. Please retry or visit the documentation "
            "(https://www.alphavantage.co/documentation/) for TIME_SERIES_DAILY.",
            id="a-bad-call",
        ),
        pytest.param(
            urllib.error.HTTPError(URL, 500, "Server Error", None, None),  # type: ignore[arg-type]
            502,
            "www.alphavantage.co answered HTTP 500.",
            id="a-server-error",
        ),
    ],
)
def test_answer__a_failure(outcome: dict[str, Any] | bytes | BaseException, exp_status: int, exp_message: str) -> None:
    tested = helper_instance("the-key")
    fake = FakeAlphaVantage([outcome])
    with fake.installed(), FakeClock(1000.0).installed(alpha_vantage_box_module):
        with pytest.raises(AppException) as exc_info:
            tested.answer({"function": "TIME_SERIES_DAILY", "symbol": "AAPL"})
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (exp_status, exp_message)
    assert result == expected
    exp_requests = [(URL, helper_query("TIME_SERIES_DAILY", "AAPL"), "GET", 15.0)]
    assert fake.requests == exp_requests


def test__spaced() -> None:
    """The first request goes at once; the next waits out the 1.2 s spacing
    from the last one, the time already passed counted."""
    tested = helper_instance("the-key")
    clock = FakeClock(1000.0)
    with clock.installed(alpha_vantage_box_module):
        tested._spaced()
        tested._spaced()
        clock.advanced(0.5)
        tested._spaced()
        clock.advanced(5.0)
        tested._spaced()
    exp_calls = [
        ("monotonic",),
        ("monotonic",),
        ("monotonic",),
        ("sleep", pytest.approx(1.2)),
        ("monotonic",),
        ("monotonic",),
        ("sleep", pytest.approx(0.7)),
        ("monotonic",),
        ("monotonic",),
        ("monotonic",),
    ]
    assert clock.calls == exp_calls
    expected = pytest.approx(1007.4)
    assert tested._last_request == expected
