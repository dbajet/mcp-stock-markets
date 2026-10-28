from __future__ import annotations

import urllib.error
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from mcp_stock_markets.constants.quote_source import QuoteSource
from mcp_stock_markets.libraries.alpaca_box import AlpacaBox
from mcp_stock_markets.libraries.web_box import WebBox
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.daily_bar import DailyBar
from mcp_stock_markets.structures.quote import Quote
from tests.support.fake_alpaca import FakeAlpaca

NOW = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
STOCKS = "https://data.alpaca.markets/v2/stocks"
HEADERS = {"Apca-api-key-id": "the-id", "Apca-api-secret-key": "the-secret"}


def helper_instance(key_id: str, secret_key: str) -> AlpacaBox:
    return AlpacaBox(WebBox(), key_id, secret_key)


def helper_bars_query() -> dict[str, str]:
    """160 calendar days back from New York's today, to 16 minutes ago."""
    return {
        "timeframe": "1Day",
        "start": "2026-05-14",
        "end": "2026-10-21T14:44:00Z",
        "feed": "sip",
        "adjustment": "split",
        "limit": "1000",
    }


def test___init__() -> None:
    web = WebBox()
    tested = AlpacaBox(web, "the-id", "the-secret")
    result = (tested._web is web, tested._key_id, tested._secret_key, tested._zone)
    expected = (True, "the-id", "the-secret", ZoneInfo("America/New_York"))
    assert result == expected


@pytest.mark.parametrize(
    "key_id, secret_key, expected",
    [
        pytest.param("the-id", "the-secret", True, id="a-pair"),
        pytest.param("", "the-secret", False, id="no-id"),
        pytest.param("the-id", "", False, id="no-secret"),
    ],
)
def test_is_configured(key_id: str, secret_key: str, expected: bool) -> None:
    tested = helper_instance(key_id, secret_key)
    result = tested.is_configured()
    assert result is expected


def test_quote() -> None:
    tested = helper_instance("the-id", "the-secret")
    fake = FakeAlpaca(
        [
            FakeAlpaca.latest_trade("AAPL", 343.99, "2026-10-21T14:58:01.123456789Z"),
            FakeAlpaca.latest_trade("BRK.B", 512.12345, "2026-10-21T14:59:59Z"),
        ]
    )
    with fake.installed():
        result = (tested.quote("AAPL", NOW), tested.quote("BRK.B", NOW))
    expected = (
        Quote(
            symbol="AAPL",
            price=Decimal("343.9900"),
            currency="USD",
            as_of=datetime(2026, 10, 21, 14, 58, 1, 123456, tzinfo=UTC),
            source=QuoteSource.ALPACA,
            fetched_at=NOW,
        ),
        Quote(
            symbol="BRK.B",
            # Four places, half to even.
            price=Decimal("512.1234"),
            currency="USD",
            as_of=datetime(2026, 10, 21, 14, 59, 59, tzinfo=UTC),
            source=QuoteSource.ALPACA,
            fetched_at=NOW,
        ),
    )
    assert result == expected
    # The key pair in headers, never in the URL; IEX, the plan's live feed.
    exp_requests = [
        (f"{STOCKS}/AAPL/trades/latest", {"feed": "iex"}, "GET", 15.0, HEADERS),
        (f"{STOCKS}/BRK.B/trades/latest", {"feed": "iex"}, "GET", 15.0, HEADERS),
    ]
    assert fake.requests == exp_requests


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param({"message": "not found"}, id="no-trade"),
        pytest.param({"trade": None}, id="a-null-trade"),
        pytest.param({"trade": {"t": "2026-10-21T14:58:01Z"}}, id="no-price"),
        pytest.param({"trade": {"p": "n/a", "t": "2026-10-21T14:58:01Z"}}, id="a-price-not-a-number"),
        pytest.param({"trade": {"p": 343.99, "t": "yesterday"}}, id="a-moment-not-iso"),
        pytest.param(FakeAlpaca.latest_trade("AAPL", 0, "2026-10-21T14:58:01Z"), id="a-zero-price"),
    ],
)
def test_quote__no_trade(answer: dict[str, Any]) -> None:
    tested = helper_instance("the-id", "the-secret")
    fake = FakeAlpaca([answer])
    with fake.installed(), pytest.raises(AppException) as exc_info:
        tested.quote("AAPL", NOW)
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (502, "Alpaca has no trade for AAPL.")
    assert result == expected
    exp_requests = [(f"{STOCKS}/AAPL/trades/latest", {"feed": "iex"}, "GET", 15.0, HEADERS)]
    assert fake.requests == exp_requests


def test_daily() -> None:
    tested = helper_instance("the-id", "the-secret")
    answer = FakeAlpaca.bars(
        "AAPL",
        {
            "2026-10-19": (336.1, 338.9, 335.5, 338.2, 39000000),
            "2026-10-20": (338.0, 340.0, 337.0, 339.5, 41000000),
            # Today's, still being made at 11:00 in New York: left out.
            "2026-10-21": (339.4, 341.0, 339.0, 340.2, 3300000),
        },
    )
    # Newest first here, to show the bars come back oldest first whatever the order.
    answer["bars"].reverse()
    fake = FakeAlpaca([answer])
    with fake.installed():
        result = tested.daily("AAPL", NOW)
    expected = [
        DailyBar(
            symbol="AAPL",
            day=date(2026, 10, 19),
            open=Decimal("336.1"),
            high=Decimal("338.9"),
            low=Decimal("335.5"),
            close=Decimal("338.2"),
            volume=39000000,
        ),
        DailyBar(
            symbol="AAPL",
            day=date(2026, 10, 20),
            open=Decimal("338.0"),
            high=Decimal("340.0"),
            low=Decimal("337.0"),
            close=Decimal("339.5"),
            volume=41000000,
        ),
    ]
    assert result == expected
    exp_requests = [(f"{STOCKS}/AAPL/bars", helper_bars_query(), "GET", 15.0, HEADERS)]
    assert fake.requests == exp_requests


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param({"bars": None, "symbol": "ZZZZ", "next_page_token": None}, id="an-unknown-symbol"),
        pytest.param({"bars": [], "symbol": "AAPL", "next_page_token": None}, id="no-bar"),
        pytest.param(FakeAlpaca.bars("AAPL", {"2026-10-21": (1, 1, 1, 1, 1)}), id="only-today-s-bar"),
        pytest.param({"message": "forbidden"}, id="no-bars"),
        pytest.param({"bars": [{"t": "2026-10-20T04:00:00Z"}]}, id="a-bar-without-prices"),
        pytest.param(
            {"bars": [{"t": "2026-10-20T04:00:00Z", "o": 1, "h": 1, "l": 1, "c": 1, "v": "many"}]},
            id="a-volume-not-a-number",
        ),
        pytest.param(
            {"bars": [{"t": "20/10/2026", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}]},
            id="a-moment-not-iso",
        ),
    ],
)
def test_daily__no_history(answer: dict[str, Any]) -> None:
    tested = helper_instance("the-id", "the-secret")
    fake = FakeAlpaca([answer])
    with fake.installed(), pytest.raises(AppException) as exc_info:
        tested.daily("AAPL", NOW)
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (502, "Alpaca has no daily history for AAPL.")
    assert result == expected
    exp_requests = [(f"{STOCKS}/AAPL/bars", helper_bars_query(), "GET", 15.0, HEADERS)]
    assert fake.requests == exp_requests


@pytest.mark.parametrize(
    "symbol, expected",
    [
        pytest.param("AAPL", f"{STOCKS}/AAPL", id="plain"),
        pytest.param("BRK.B", f"{STOCKS}/BRK.B", id="a-share-class-keeps-its-dot"),
        pytest.param("A/B C", f"{STOCKS}/A%2FB%20C", id="escaped"),
    ],
)
def test_stock_url(symbol: str, expected: str) -> None:
    tested = AlpacaBox
    result = tested.stock_url(symbol)
    assert result == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        pytest.param(
            "2026-10-21T14:58:01.123456789Z", datetime(2026, 10, 21, 14, 58, 1, 123456, tzinfo=UTC), id="nanoseconds"
        ),
        pytest.param(
            "2026-10-21T14:58:01.5Z", datetime(2026, 10, 21, 14, 58, 1, 500000, tzinfo=UTC), id="a-short-fraction"
        ),
        pytest.param("2026-10-21T04:00:00Z", datetime(2026, 10, 21, 4, 0, tzinfo=UTC), id="whole-seconds"),
    ],
)
def test_moment(text: str, expected: datetime) -> None:
    tested = AlpacaBox
    result = tested.moment(text)
    assert result == expected


def test_answer() -> None:
    tested = helper_instance("the-id", "the-secret")
    fake = FakeAlpaca([{"trade": {"p": 1.0}}])
    with fake.installed():
        result = tested.answer(f"{STOCKS}/AAPL/trades/latest?feed=iex")
    expected = {"trade": {"p": 1.0}}
    assert result == expected
    exp_requests = [(f"{STOCKS}/AAPL/trades/latest", {"feed": "iex"}, "GET", 15.0, HEADERS)]
    assert fake.requests == exp_requests


@pytest.mark.parametrize(
    "key_id, secret_key",
    [
        pytest.param("", "the-secret", id="no-id"),
        pytest.param("the-id", "", id="no-secret"),
    ],
)
def test_answer__not_configured(key_id: str, secret_key: str) -> None:
    tested = helper_instance(key_id, secret_key)
    fake = FakeAlpaca([])
    with fake.installed(), pytest.raises(AppException) as exc_info:
        tested.answer(f"{STOCKS}/AAPL/trades/latest?feed=iex")
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (503, "Daily history needs an Alpaca key (ALPACA_KEY_ID and ALPACA_SECRET_KEY).")
    assert result == expected
    # Refused before any request.
    exp_requests: list[tuple[Any, ...]] = []
    assert fake.requests == exp_requests


@pytest.mark.parametrize(
    "outcome, exp_status, exp_message",
    [
        pytest.param(b"<html>Bad gateway</html>", 502, "Alpaca's answer is not JSON.", id="not-json"),
        pytest.param(b'["AAPL"]', 502, "Alpaca's answer is not a JSON object.", id="not-an-object"),
        pytest.param(
            urllib.error.HTTPError(f"{STOCKS}/AAPL/trades/latest", 403, "Forbidden", None, None),  # type: ignore[arg-type]
            502,
            "data.alpaca.markets answered HTTP 403.",
            id="a-refused-key",
        ),
        pytest.param(
            urllib.error.HTTPError(f"{STOCKS}/AAPL/trades/latest", 429, "Too Many Requests", None, None),  # type: ignore[arg-type]
            502,
            "data.alpaca.markets answered HTTP 429.",
            id="over-the-limit",
        ),
    ],
)
def test_answer__a_failure(outcome: bytes | BaseException, exp_status: int, exp_message: str) -> None:
    tested = helper_instance("the-id", "the-secret")
    fake = FakeAlpaca([outcome])
    with fake.installed(), pytest.raises(AppException) as exc_info:
        tested.answer(f"{STOCKS}/AAPL/trades/latest?feed=iex")
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (exp_status, exp_message)
    assert result == expected
    exp_requests = [(f"{STOCKS}/AAPL/trades/latest", {"feed": "iex"}, "GET", 15.0, HEADERS)]
    assert fake.requests == exp_requests
