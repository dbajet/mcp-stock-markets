from __future__ import annotations

import urllib.error
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from mcp_stock_markets.constants.quote_source import QuoteSource
from mcp_stock_markets.libraries.google_finance_box import GoogleFinanceBox
from mcp_stock_markets.libraries.web_box import WebBox
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.quote import Quote
from tests.support.fake_google_finance import FakeGoogleFinance

NOW = datetime(2026, 10, 21, 23, 0, tzinfo=UTC)
AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"


def helper_entry(symbol: str, exchange: str, price: float, traded: int | None) -> list[Any]:
    return FakeGoogleFinance.quote_entry(symbol, exchange, "Apple Inc", price, traded)


def test___init__() -> None:
    web = WebBox()
    tested = GoogleFinanceBox(web)
    result = tested._web is web
    assert result is True


def test_quote() -> None:
    tested = GoogleFinanceBox(WebBox())
    fake = FakeGoogleFinance(
        [
            helper_entry("AAPL", "NASDAQ", 343.99, 1792612801),
            helper_entry("BRK.B", "NYSE", 512.3, 1792612800),
        ]
    )
    with fake.installed():
        result = (tested.quote("AAPL", "NASDAQ", NOW), tested.quote("BRK.B", "NYSE", NOW))
    expected = (
        Quote(
            symbol="AAPL",
            price=Decimal("343.9900"),
            currency="USD",
            as_of=datetime(2026, 10, 21, 20, 0, 1, tzinfo=UTC),
            source=QuoteSource.GOOGLE_FINANCE,
            fetched_at=NOW,
        ),
        Quote(
            symbol="BRK.B",
            price=Decimal("512.3000"),
            currency="USD",
            as_of=datetime(2026, 10, 21, 20, 0, 0, tzinfo=UTC),
            source=QuoteSource.GOOGLE_FINANCE,
            fetched_at=NOW,
        ),
    )
    assert result == expected
    exp_requests = [
        ("https://www.google.com/finance/quote/AAPL:NASDAQ?hl=en", "GET", AGENT, "en-US,en;q=0.8", 15.0),
        # A share class keeps its dot, as Google writes it.
        ("https://www.google.com/finance/quote/BRK.B:NYSE?hl=en", "GET", AGENT, "en-US,en;q=0.8", 15.0),
    ]
    assert fake.requests == exp_requests


def test_quote__a_page_without_the_quote() -> None:
    tested = GoogleFinanceBox(WebBox())
    # The page of another listing: the pair asked for is nowhere in it.
    fake = FakeGoogleFinance([helper_entry("AAPL", "NYSE", 343.99, 1792612801)])
    with fake.installed():
        with pytest.raises(AppException) as exc_info:
            tested.quote("AAPL", "NASDAQ", NOW)
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (502, "Google Finance shows no quote for AAPL.")
    assert result == expected
    exp_requests = [("https://www.google.com/finance/quote/AAPL:NASDAQ?hl=en", "GET", AGENT, "en-US,en;q=0.8", 15.0)]
    assert fake.requests == exp_requests


def test_quote__google_unreachable() -> None:
    tested = GoogleFinanceBox(WebBox())
    fake = FakeGoogleFinance([urllib.error.URLError("no route to host")])
    with fake.installed():
        with pytest.raises(AppException) as exc_info:
            tested.quote("AAPL", "NASDAQ", NOW)
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (502, "www.google.com did not answer.")
    assert result == expected
    exp_requests = [("https://www.google.com/finance/quote/AAPL:NASDAQ?hl=en", "GET", AGENT, "en-US,en;q=0.8", 15.0)]
    assert fake.requests == exp_requests


def test_entry() -> None:
    tested = GoogleFinanceBox
    page = FakeGoogleFinance.page(helper_entry("AAPL", "NASDAQ", 343.99, 1792612801))
    result = tested.entry(page, "AAPL", "NASDAQ")
    expected = helper_entry("AAPL", "NASDAQ", 343.99, 1792612801)
    assert result == expected


@pytest.mark.parametrize(
    "page",
    [
        pytest.param("<html><body>Before you continue to Google</body></html>", id="a-consent-page"),
        pytest.param("<script>AF_initDataCallback({key: 'ds:2', hash: '8'});</script>", id="a-block-without-data"),
        pytest.param(
            "<script>AF_initDataCallback({key: 'ds:2', hash: '8', data:[[[not json]]], sideChannel: {}});</script>",
            id="data-that-is-not-json",
        ),
        pytest.param(
            "<script>AF_initDataCallback({key: 'ds:4', hash: '1', data:[null,null,[[\"AAPL\",\"NASDAQ\"],0.26]], "
            "sideChannel: {}});</script>",
            id="only-other-shapes",
        ),
    ],
)
def test_entry__none(page: str) -> None:
    tested = GoogleFinanceBox
    result = tested.entry(page, "AAPL", "NASDAQ")
    assert result is None


def test_entry__a_broken_block_before_the_quote_is_skipped() -> None:
    tested = GoogleFinanceBox
    entry = helper_entry("AAPL", "NASDAQ", 343.99, 1792612801)
    page = (
        "<script>AF_initDataCallback({key: 'ds:9', hash: '3', data:[oops], sideChannel: {}});</script>"
        f"{FakeGoogleFinance.page(entry)}"
    )
    result = tested.entry(page, "AAPL", "NASDAQ")
    expected = helper_entry("AAPL", "NASDAQ", 343.99, 1792612801)
    assert result == expected


@pytest.mark.parametrize(
    "data, expected",
    [
        pytest.param(None, None, id="not-a-list"),
        pytest.param({"1": ["AAPL", "NASDAQ"]}, None, id="an-object"),
        pytest.param(
            [[[helper_entry("AAPL", "NASDAQ", 343.99, 1792612801)]]],
            helper_entry("AAPL", "NASDAQ", 343.99, 1792612801),
            id="three-levels-down",
        ),
        pytest.param(
            helper_entry("AAPL", "NASDAQ", 343.99, 1792612801),
            helper_entry("AAPL", "NASDAQ", 343.99, 1792612801),
            id="the-array-itself",
        ),
        pytest.param([[helper_entry("MSFT", "NASDAQ", 501.2, 1792612801)]], None, id="another-stock"),
        pytest.param(
            [["/m/x", ["AAPL", "NASDAQ"], "Apple Inc", 2026, 4, None, *([None] * 12)]],
            None,
            id="the-pair-without-a-price-array",
        ),
        pytest.param([["/m/x", ["AAPL", "NASDAQ"], "Apple Inc", 0, "USD", [343.99]]], None, id="too-short"),
        pytest.param(
            [
                ["/m/x", ["AAPL", "NASDAQ"], "Apple Inc", 2026, 4, None, *([None] * 12)],
                [helper_entry("AAPL", "NASDAQ", 343.99, 1792612801)],
            ],
            helper_entry("AAPL", "NASDAQ", 343.99, 1792612801),
            id="after-a-decoy",
        ),
    ],
)
def test_found(data: Any, expected: list[Any] | None) -> None:
    tested = GoogleFinanceBox
    result = tested.found(data, ["AAPL", "NASDAQ"])
    assert result == expected


@pytest.mark.parametrize(
    "entry, expected",
    [
        pytest.param(
            helper_entry("AAPL", "NASDAQ", 343.99, 1792612801),
            Quote(
                symbol="AAPL",
                price=Decimal("343.9900"),
                currency="USD",
                as_of=datetime(2026, 10, 21, 20, 0, 1, tzinfo=UTC),
                source=QuoteSource.GOOGLE_FINANCE,
                fetched_at=NOW,
            ),
            id="the-regular-session-trade",
        ),
        pytest.param(
            helper_entry("AAPL", "NASDAQ", 0.123456, None),
            Quote(
                symbol="AAPL",
                price=Decimal("0.1235"),
                currency="USD",
                as_of=datetime(2026, 10, 21, 22, 52, 8, tzinfo=UTC),
                source=QuoteSource.GOOGLE_FINANCE,
                fetched_at=NOW,
            ),
            id="no-trade-time-reads-the-update-time",
        ),
    ],
)
def test_quote_of(entry: list[Any], expected: Quote) -> None:
    tested = GoogleFinanceBox
    result = tested.quote_of("AAPL", entry, NOW)
    assert result == expected


@pytest.mark.parametrize(
    "entry, exp_message",
    [
        pytest.param(
            helper_entry("AAPL", "NASDAQ", 343.99, 1792612801)[:6],
            "Google Finance's quote of AAPL has an unexpected shape.",
            id="cut-short",
        ),
        pytest.param(
            [*helper_entry("AAPL", "NASDAQ", 343.99, 1792612801)[:5], [], *([None] * 13)],
            "Google Finance's quote of AAPL has an unexpected shape.",
            id="an-empty-price-array",
        ),
        pytest.param(
            [*helper_entry("AAPL", "NASDAQ", 343.99, None)[:11], None, *([None] * 7)],
            "Google Finance's quote of AAPL has an unexpected shape.",
            id="no-time-at-all",
        ),
        pytest.param(
            [*helper_entry("AAPL", "NASDAQ", 343.99, None)[:5], ["n/a"], *([None] * 13)],
            "Google Finance's quote of AAPL has an unexpected shape.",
            id="a-price-that-is-not-a-number",
        ),
        pytest.param(
            [*helper_entry("AAPL", "NASDAQ", 343.99, None)[:17], ["soon"], None],
            "Google Finance's quote of AAPL has an unexpected shape.",
            id="a-time-that-is-not-a-number",
        ),
        pytest.param(
            helper_entry("AAPL", "NASDAQ", 0, 1792612801),
            "Google Finance's quote of AAPL has no price.",
            id="a-zero-price",
        ),
        pytest.param(
            helper_entry("AAPL", "NASDAQ", -1.5, 1792612801),
            "Google Finance's quote of AAPL has no price.",
            id="a-negative-price",
        ),
    ],
)
def test_quote_of__a_bad_gateway(entry: list[Any], exp_message: str) -> None:
    tested = GoogleFinanceBox
    with pytest.raises(AppException) as exc_info:
        tested.quote_of("AAPL", entry, NOW)
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (502, exp_message)
    assert result == expected
