from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import call, patch

import pytest

from mcp_stock_markets.commands.quote_command import QuoteCommand
from mcp_stock_markets.constants.quote_source import QuoteSource
from mcp_stock_markets.libraries.alpha_vantage_box import AlphaVantageBox
from mcp_stock_markets.libraries.company_store import CompanyStore
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.libraries.google_finance_box import GoogleFinanceBox
from mcp_stock_markets.libraries.market_clock import MarketClock
from mcp_stock_markets.libraries.quote_store import QuoteStore
from mcp_stock_markets.libraries.web_box import WebBox
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.company import Company
from mcp_stock_markets.structures.daily_bar import DailyBar
from mcp_stock_markets.structures.market_status import MarketStatus
from mcp_stock_markets.structures.quote import Quote

NOW = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
NEW_YORK = timezone(timedelta(hours=-4))


def helper_parts() -> tuple[QuoteStore, CompanyStore, GoogleFinanceBox, AlphaVantageBox, MarketClock]:
    database = Database("postgresql://u:p@h/d")
    return (
        QuoteStore(database),
        CompanyStore(database),
        GoogleFinanceBox(WebBox()),
        AlphaVantageBox(WebBox(), "av-key"),
        MarketClock(),
    )


def helper_instance() -> QuoteCommand:
    return QuoteCommand(*helper_parts())


def helper_status(is_open: bool, now: datetime) -> MarketStatus:
    return MarketStatus(
        is_open=is_open,
        now=now,
        closes_at=datetime(2026, 10, 21, 16, 0, tzinfo=NEW_YORK) if is_open else None,
        next_open=datetime(2026, 10, 22, 9, 30, tzinfo=NEW_YORK),
    )


def helper_quote(fetched_at: datetime, source: QuoteSource) -> Quote:
    return Quote(
        symbol="AAPL",
        price=Decimal("231.4500"),
        currency="USD",
        as_of=datetime(2026, 10, 21, 14, 58, tzinfo=UTC),
        source=source,
        fetched_at=fetched_at,
    )


def helper_company(exchange: str) -> Company:
    return Company(
        symbol="AAPL",
        name="Apple Inc.",
        sector="Information Technology",
        sub_industry="Technology Hardware, Storage & Peripherals",
        headquarters="Cupertino, California",
        exchange=exchange,
    )


def helper_bar(day: date) -> DailyBar:
    return DailyBar(
        symbol="AAPL",
        day=day,
        open=Decimal("230.0000"),
        high=Decimal("233.0000"),
        low=Decimal("229.5000"),
        close=Decimal("231.4500"),
        volume=51_234_000,
    )


def test___init__() -> None:
    store, companies, google, alpha_vantage, clock = helper_parts()
    tested = QuoteCommand(store, companies, google, alpha_vantage, clock)
    result = (tested._store, tested._companies, tested._google, tested._alpha_vantage, tested._clock)
    expected = (store, companies, google, alpha_vantage, clock)
    assert result == expected


def test_market() -> None:
    tested = helper_instance()
    status = helper_status(True, datetime(2026, 10, 21, 11, 0, tzinfo=NEW_YORK))
    with patch.object(MarketClock, "status", side_effect=[status]) as mock_status:
        result = tested.market(NOW)
    expected = helper_status(True, datetime(2026, 10, 21, 11, 0, tzinfo=NEW_YORK))
    assert result == expected
    exp_calls = [call(datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_status.mock_calls == exp_calls


def test_quote__cached_within_the_minute() -> None:
    tested = helper_instance()
    cached = helper_quote(datetime(2026, 10, 21, 14, 59, 0, 1, tzinfo=UTC), QuoteSource.GOOGLE_FINANCE)
    with (
        patch.object(QuoteStore, "latest", side_effect=[cached]) as mock_latest,
        patch.object(QuoteCommand, "fetched", side_effect=[]) as mock_fetched,
        patch.object(QuoteStore, "stored", side_effect=[]) as mock_stored,
    ):
        result = tested.quote(" aapl ", NOW)
    expected = helper_quote(datetime(2026, 10, 21, 14, 59, 0, 1, tzinfo=UTC), QuoteSource.GOOGLE_FINANCE)
    assert result == expected
    exp_calls = [call("AAPL")]
    assert mock_latest.mock_calls == exp_calls
    exp_calls = []
    assert mock_fetched.mock_calls == exp_calls
    assert mock_stored.mock_calls == exp_calls


@pytest.mark.parametrize(
    "cached, exp_ask_alpha_vantage",
    [
        pytest.param(None, True, id="never-read"),
        pytest.param(
            helper_quote(datetime(2026, 10, 21, 14, 59, tzinfo=UTC), QuoteSource.GOOGLE_FINANCE),
            False,
            id="a-minute-old",
        ),
    ],
)
def test_quote(cached: Quote | None, exp_ask_alpha_vantage: bool) -> None:
    tested = helper_instance()
    fresh = helper_quote(NOW, QuoteSource.GOOGLE_FINANCE)
    with (
        patch.object(QuoteStore, "latest", side_effect=[cached]) as mock_latest,
        patch.object(QuoteCommand, "fetched", side_effect=[fresh]) as mock_fetched,
        patch.object(QuoteStore, "stored", side_effect=[fresh]) as mock_stored,
    ):
        result = tested.quote("aapl", NOW)
    expected = helper_quote(datetime(2026, 10, 21, 15, 0, tzinfo=UTC), QuoteSource.GOOGLE_FINANCE)
    assert result == expected
    exp_calls = [call("AAPL")]
    assert mock_latest.mock_calls == exp_calls
    exp_calls = [call("AAPL", datetime(2026, 10, 21, 15, 0, tzinfo=UTC), exp_ask_alpha_vantage)]
    assert mock_fetched.mock_calls == exp_calls
    exp_calls = [call(helper_quote(datetime(2026, 10, 21, 15, 0, tzinfo=UTC), QuoteSource.GOOGLE_FINANCE))]
    assert mock_stored.mock_calls == exp_calls


def test_quote__the_last_price_when_no_new_one_comes() -> None:
    tested = helper_instance()
    cached = helper_quote(datetime(2026, 10, 20, 19, 59, tzinfo=UTC), QuoteSource.GOOGLE_FINANCE)
    with (
        patch.object(QuoteStore, "latest", side_effect=[cached]) as mock_latest,
        patch.object(
            QuoteCommand, "fetched", side_effect=[AppException(502, "No price could be fetched for AAPL right now.")]
        ) as mock_fetched,
        patch.object(QuoteStore, "stored", side_effect=[]) as mock_stored,
    ):
        result = tested.quote("AAPL", NOW)
    expected = helper_quote(datetime(2026, 10, 20, 19, 59, tzinfo=UTC), QuoteSource.GOOGLE_FINANCE)
    assert result == expected
    exp_calls = [call("AAPL")]
    assert mock_latest.mock_calls == exp_calls
    exp_calls = [call("AAPL", datetime(2026, 10, 21, 15, 0, tzinfo=UTC), False)]
    assert mock_fetched.mock_calls == exp_calls
    exp_calls = []
    assert mock_stored.mock_calls == exp_calls


def test_quote__never_priced_and_no_price_comes() -> None:
    tested = helper_instance()
    with (
        patch.object(QuoteStore, "latest", side_effect=[None]) as mock_latest,
        patch.object(
            QuoteCommand, "fetched", side_effect=[AppException(502, "No price could be fetched for AAPL right now.")]
        ) as mock_fetched,
        patch.object(QuoteStore, "stored", side_effect=[]) as mock_stored,
        pytest.raises(AppException) as exc_info,
    ):
        tested.quote("AAPL", NOW)
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (502, "No price could be fetched for AAPL right now.")
    assert result == expected
    exp_calls = [call("AAPL")]
    assert mock_latest.mock_calls == exp_calls
    exp_calls = [call("AAPL", datetime(2026, 10, 21, 15, 0, tzinfo=UTC), True)]
    assert mock_fetched.mock_calls == exp_calls
    exp_calls = []
    assert mock_stored.mock_calls == exp_calls


@pytest.mark.parametrize(
    "company, exp_exchange",
    [
        pytest.param(helper_company("NASDAQ"), "NASDAQ", id="member"),
        pytest.param(None, "NYSE", id="left-the-index"),
    ],
)
def test_fetched(company: Company | None, exp_exchange: str) -> None:
    tested = helper_instance()
    with (
        patch.object(CompanyStore, "company", side_effect=[company]) as mock_company,
        patch.object(
            GoogleFinanceBox, "quote", side_effect=[helper_quote(NOW, QuoteSource.GOOGLE_FINANCE)]
        ) as mock_google,
        patch.object(AlphaVantageBox, "is_configured", side_effect=[]) as mock_is_configured,
        patch.object(AlphaVantageBox, "quote", side_effect=[]) as mock_alpha_vantage,
    ):
        result = tested.fetched("AAPL", NOW, True)
    expected = helper_quote(datetime(2026, 10, 21, 15, 0, tzinfo=UTC), QuoteSource.GOOGLE_FINANCE)
    assert result == expected
    exp_calls = [call("AAPL")]
    assert mock_company.mock_calls == exp_calls
    exp_calls = [call("AAPL", exp_exchange, datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_google.mock_calls == exp_calls
    exp_calls = []
    assert mock_is_configured.mock_calls == exp_calls
    assert mock_alpha_vantage.mock_calls == exp_calls


def test_fetched__alpha_vantage_when_google_fails(caplog: pytest.LogCaptureFixture) -> None:
    tested = helper_instance()
    with (
        caplog.at_level(logging.WARNING, logger="mcp_stock_markets"),
        patch.object(CompanyStore, "company", side_effect=[helper_company("NASDAQ")]) as mock_company,
        patch.object(
            GoogleFinanceBox, "quote", side_effect=[AppException(502, "www.google.com did not answer.")]
        ) as mock_google,
        patch.object(AlphaVantageBox, "is_configured", side_effect=[True]) as mock_is_configured,
        patch.object(
            AlphaVantageBox, "quote", side_effect=[helper_quote(NOW, QuoteSource.ALPHA_VANTAGE)]
        ) as mock_alpha_vantage,
    ):
        result = tested.fetched("AAPL", NOW, True)
    expected = helper_quote(datetime(2026, 10, 21, 15, 0, tzinfo=UTC), QuoteSource.ALPHA_VANTAGE)
    assert result == expected
    exp_messages = ["[QUOTES] Google for AAPL: www.google.com did not answer."]
    assert caplog.messages == exp_messages
    exp_calls = [call("AAPL")]
    assert mock_company.mock_calls == exp_calls
    exp_calls = [call("AAPL", "NASDAQ", datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_google.mock_calls == exp_calls
    exp_calls = [call()]
    assert mock_is_configured.mock_calls == exp_calls
    exp_calls = [call("AAPL", datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_alpha_vantage.mock_calls == exp_calls


def test_fetched__google_fails_without_alpha_vantage(caplog: pytest.LogCaptureFixture) -> None:
    tested = helper_instance()
    with (
        caplog.at_level(logging.WARNING, logger="mcp_stock_markets"),
        patch.object(CompanyStore, "company", side_effect=[helper_company("NASDAQ")]) as mock_company,
        patch.object(
            GoogleFinanceBox, "quote", side_effect=[AppException(502, "www.google.com did not answer.")]
        ) as mock_google,
        patch.object(AlphaVantageBox, "is_configured", side_effect=[False]) as mock_is_configured,
        patch.object(AlphaVantageBox, "quote", side_effect=[]) as mock_alpha_vantage,
        pytest.raises(AppException) as exc_info,
    ):
        tested.fetched("AAPL", NOW, True)
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (502, "No price could be fetched for AAPL right now.")
    assert result == expected
    exp_messages = ["[QUOTES] Google for AAPL: www.google.com did not answer."]
    assert caplog.messages == exp_messages
    exp_calls = [call("AAPL")]
    assert mock_company.mock_calls == exp_calls
    exp_calls = [call("AAPL", "NASDAQ", datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_google.mock_calls == exp_calls
    exp_calls = [call()]
    assert mock_is_configured.mock_calls == exp_calls
    exp_calls = []
    assert mock_alpha_vantage.mock_calls == exp_calls


def test_fetched__google_fails_alpha_vantage_not_asked(caplog: pytest.LogCaptureFixture) -> None:
    tested = helper_instance()
    with (
        caplog.at_level(logging.WARNING, logger="mcp_stock_markets"),
        patch.object(CompanyStore, "company", side_effect=[helper_company("NASDAQ")]) as mock_company,
        patch.object(
            GoogleFinanceBox, "quote", side_effect=[AppException(502, "www.google.com did not answer.")]
        ) as mock_google,
        patch.object(AlphaVantageBox, "is_configured", side_effect=[]) as mock_is_configured,
        patch.object(AlphaVantageBox, "quote", side_effect=[]) as mock_alpha_vantage,
        pytest.raises(AppException) as exc_info,
    ):
        tested.fetched("AAPL", NOW, False)
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (502, "No price could be fetched for AAPL right now.")
    assert result == expected
    exp_messages = ["[QUOTES] Google for AAPL: www.google.com did not answer."]
    assert caplog.messages == exp_messages
    exp_calls = [call("AAPL")]
    assert mock_company.mock_calls == exp_calls
    exp_calls = [call("AAPL", "NASDAQ", datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_google.mock_calls == exp_calls
    exp_calls = []
    assert mock_is_configured.mock_calls == exp_calls
    assert mock_alpha_vantage.mock_calls == exp_calls


def test_fetched__both_fail(caplog: pytest.LogCaptureFixture) -> None:
    tested = helper_instance()
    with (
        caplog.at_level(logging.WARNING, logger="mcp_stock_markets"),
        patch.object(CompanyStore, "company", side_effect=[None]) as mock_company,
        patch.object(
            GoogleFinanceBox, "quote", side_effect=[AppException(502, "www.google.com did not answer.")]
        ) as mock_google,
        patch.object(AlphaVantageBox, "is_configured", side_effect=[True]) as mock_is_configured,
        patch.object(
            AlphaVantageBox, "quote", side_effect=[AppException(502, "www.alphavantage.co answered HTTP 500.")]
        ) as mock_alpha_vantage,
        pytest.raises(AppException) as exc_info,
    ):
        tested.fetched("AAPL", NOW, True)
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (502, "No price could be fetched for AAPL right now.")
    assert result == expected
    exp_messages = [
        "[QUOTES] Google for AAPL: www.google.com did not answer.",
        "[QUOTES] Alpha Vantage for AAPL: www.alphavantage.co answered HTTP 500.",
    ]
    assert caplog.messages == exp_messages
    exp_calls = [call("AAPL")]
    assert mock_company.mock_calls == exp_calls
    exp_calls = [call("AAPL", "NYSE", datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_google.mock_calls == exp_calls
    exp_calls = [call()]
    assert mock_is_configured.mock_calls == exp_calls
    exp_calls = [call("AAPL", datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_alpha_vantage.mock_calls == exp_calls


@pytest.mark.parametrize(
    "found",
    [
        pytest.param(helper_quote(datetime(2026, 10, 20, 20, 0, tzinfo=UTC), QuoteSource.GOOGLE_FINANCE), id="read"),
        pytest.param(None, id="never-read"),
    ],
)
def test_latest(found: Quote | None) -> None:
    tested = helper_instance()
    with patch.object(QuoteStore, "latest", side_effect=[found]) as mock_latest:
        result = tested.latest("AAPL")
    expected = found
    assert result == expected
    exp_calls = [call("AAPL")]
    assert mock_latest.mock_calls == exp_calls


@pytest.mark.parametrize(
    "days, exp_days",
    [
        pytest.param(20, 20, id="as-asked"),
        pytest.param(0, 1, id="at-least-one"),
        pytest.param(-5, 1, id="negative"),
        pytest.param(100, 100, id="the-most"),
        pytest.param(500, 100, id="at-most-100"),
    ],
)
def test_history__fetched_today_already(days: int, exp_days: int) -> None:
    """The bars of today's fetch serve; the day is New York's."""
    tested = helper_instance()
    status = helper_status(False, datetime(2026, 10, 20, 22, 0, tzinfo=NEW_YORK))
    with (
        patch.object(MarketClock, "status", side_effect=[status]) as mock_status,
        patch.object(QuoteStore, "fetched_on", side_effect=[date(2026, 10, 20)]) as mock_fetched_on,
        patch.object(AlphaVantageBox, "daily", side_effect=[]) as mock_daily,
        patch.object(QuoteStore, "bars_replaced", side_effect=[]) as mock_bars_replaced,
        patch.object(QuoteStore, "bars", side_effect=[[helper_bar(date(2026, 10, 20))]]) as mock_bars,
    ):
        result = tested.history(" aapl ", days, datetime(2026, 10, 21, 2, 0, tzinfo=UTC))
    expected = [helper_bar(date(2026, 10, 20))]
    assert result == expected
    exp_calls = [call(datetime(2026, 10, 21, 2, 0, tzinfo=UTC))]
    assert mock_status.mock_calls == exp_calls
    exp_calls = [call("AAPL")]
    assert mock_fetched_on.mock_calls == exp_calls
    exp_calls = []
    assert mock_daily.mock_calls == exp_calls
    assert mock_bars_replaced.mock_calls == exp_calls
    exp_calls = [call("AAPL", exp_days)]
    assert mock_bars.mock_calls == exp_calls


@pytest.mark.parametrize(
    "fetched_on",
    [
        pytest.param(None, id="never-fetched"),
        pytest.param(date(2026, 10, 20), id="fetched-yesterday"),
    ],
)
def test_history(fetched_on: date | None) -> None:
    tested = helper_instance()
    status = helper_status(True, datetime(2026, 10, 21, 11, 0, tzinfo=NEW_YORK))
    bars = [helper_bar(date(2026, 10, 19)), helper_bar(date(2026, 10, 20))]
    with (
        patch.object(MarketClock, "status", side_effect=[status]) as mock_status,
        patch.object(QuoteStore, "fetched_on", side_effect=[fetched_on]) as mock_fetched_on,
        patch.object(AlphaVantageBox, "daily", side_effect=[bars]) as mock_daily,
        patch.object(QuoteStore, "bars_replaced", side_effect=[None]) as mock_bars_replaced,
        patch.object(QuoteStore, "bars", side_effect=[bars]) as mock_bars,
    ):
        result = tested.history("AAPL", 20, NOW)
    expected = [helper_bar(date(2026, 10, 19)), helper_bar(date(2026, 10, 20))]
    assert result == expected
    exp_calls = [call(datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_status.mock_calls == exp_calls
    exp_calls = [call("AAPL")]
    assert mock_fetched_on.mock_calls == exp_calls
    exp_calls = [call("AAPL", date(2026, 10, 21))]
    assert mock_daily.mock_calls == exp_calls
    exp_calls = [
        call("AAPL", [helper_bar(date(2026, 10, 19)), helper_bar(date(2026, 10, 20))], date(2026, 10, 21)),
    ]
    assert mock_bars_replaced.mock_calls == exp_calls
    exp_calls = [call("AAPL", 20)]
    assert mock_bars.mock_calls == exp_calls


def test_history__stale_bars_serve_when_the_fetch_fails(caplog: pytest.LogCaptureFixture) -> None:
    tested = helper_instance()
    status = helper_status(True, datetime(2026, 10, 21, 11, 0, tzinfo=NEW_YORK))
    with (
        caplog.at_level(logging.WARNING, logger="mcp_stock_markets"),
        patch.object(MarketClock, "status", side_effect=[status]) as mock_status,
        patch.object(QuoteStore, "fetched_on", side_effect=[date(2026, 10, 20), date(2026, 10, 20)]) as mock_fetched_on,
        patch.object(
            AlphaVantageBox, "daily", side_effect=[AppException(502, "www.alphavantage.co did not answer.")]
        ) as mock_daily,
        patch.object(QuoteStore, "bars_replaced", side_effect=[]) as mock_bars_replaced,
        patch.object(QuoteStore, "bars", side_effect=[[helper_bar(date(2026, 10, 19))]]) as mock_bars,
    ):
        result = tested.history("AAPL", 20, NOW)
    expected = [helper_bar(date(2026, 10, 19))]
    assert result == expected
    exp_messages = ["[HISTORY] AAPL: www.alphavantage.co did not answer."]
    assert caplog.messages == exp_messages
    exp_calls = [call(datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_status.mock_calls == exp_calls
    exp_calls = [call("AAPL"), call("AAPL")]
    assert mock_fetched_on.mock_calls == exp_calls
    exp_calls = [call("AAPL", date(2026, 10, 21))]
    assert mock_daily.mock_calls == exp_calls
    exp_calls = []
    assert mock_bars_replaced.mock_calls == exp_calls
    exp_calls = [call("AAPL", 20)]
    assert mock_bars.mock_calls == exp_calls


def test_history__never_any_bars(caplog: pytest.LogCaptureFixture) -> None:
    tested = helper_instance()
    status = helper_status(True, datetime(2026, 10, 21, 11, 0, tzinfo=NEW_YORK))
    with (
        caplog.at_level(logging.WARNING, logger="mcp_stock_markets"),
        patch.object(MarketClock, "status", side_effect=[status]) as mock_status,
        patch.object(QuoteStore, "fetched_on", side_effect=[None, None]) as mock_fetched_on,
        patch.object(
            AlphaVantageBox,
            "daily",
            side_effect=[AppException(503, "Daily history needs an Alpha Vantage key (ALPHA_VANTAGE_API_KEY).")],
        ) as mock_daily,
        patch.object(QuoteStore, "bars_replaced", side_effect=[]) as mock_bars_replaced,
        patch.object(QuoteStore, "bars", side_effect=[]) as mock_bars,
        pytest.raises(AppException) as exc_info,
    ):
        tested.history("AAPL", 20, NOW)
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (503, "Daily history needs an Alpha Vantage key (ALPHA_VANTAGE_API_KEY).")
    assert result == expected
    exp_messages = ["[HISTORY] AAPL: Daily history needs an Alpha Vantage key (ALPHA_VANTAGE_API_KEY)."]
    assert caplog.messages == exp_messages
    exp_calls = [call(datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_status.mock_calls == exp_calls
    exp_calls = [call("AAPL"), call("AAPL")]
    assert mock_fetched_on.mock_calls == exp_calls
    exp_calls = [call("AAPL", date(2026, 10, 21))]
    assert mock_daily.mock_calls == exp_calls
    exp_calls = []
    assert mock_bars_replaced.mock_calls == exp_calls
    assert mock_bars.mock_calls == exp_calls
