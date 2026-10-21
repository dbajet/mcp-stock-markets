from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from mcp_stock_markets.constants.quote_source import QuoteSource
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.libraries.quote_store import QuoteStore
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.daily_bar import DailyBar
from mcp_stock_markets.structures.quote import Quote
from tests.conftest import helper_database


def helper_quote(symbol: str, price: str, fetched_minute: int) -> Quote:
    return Quote(
        symbol=symbol,
        price=Decimal(price),
        currency="USD",
        as_of=datetime(2026, 10, 21, 15, 0, tzinfo=UTC),
        source=QuoteSource.GOOGLE_FINANCE,
        fetched_at=datetime(2026, 10, 21, 15, fetched_minute, tzinfo=UTC),
    )


def helper_bar(symbol: str, day: int, close: str) -> DailyBar:
    return DailyBar(
        symbol=symbol,
        day=date(2026, 10, day),
        open=Decimal("339.3600"),
        high=Decimal("345.2500"),
        low=Decimal("338.8300"),
        close=Decimal(close),
        volume=35586943,
    )


def test___init__() -> None:
    database = Database("postgresql://u:p@h/d")
    tested = QuoteStore(database)
    result = tested._database is database
    assert result is True


@pytest.mark.database
def test_stored() -> None:
    database = helper_database()
    tested = QuoteStore(database)
    quote = Quote(
        symbol="AAPL",
        price=Decimal("343.99"),
        currency="USD",
        as_of=datetime(2026, 10, 21, 16, 0, tzinfo=UTC),
        source=QuoteSource.ALPHA_VANTAGE,
        fetched_at=datetime(2026, 10, 21, 23, 0, tzinfo=UTC),
    )
    result = tested.stored(quote)
    assert result is quote
    expected = [
        {
            "id": 1,
            "symbol": "AAPL",
            "price": Decimal("343.9900"),
            "currency": "USD",
            "as_of": datetime(2026, 10, 21, 16, 0, tzinfo=UTC),
            "source": "alpha_vantage",
            "fetched_at": datetime(2026, 10, 21, 23, 0, tzinfo=UTC),
        }
    ]
    assert database.rows("SELECT id, symbol, price, currency, as_of, source, fetched_at FROM quotes", ()) == expected


@pytest.mark.database
def test_stored__a_price_not_above_zero_is_refused() -> None:
    database = helper_database()
    tested = QuoteStore(database)
    with pytest.raises(AppException) as exc_info:
        tested.stored(helper_quote("AAPL", "0", 1))
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (503, "The database is unavailable.")
    assert result == expected
    exp_count = {"quotes": 0}
    assert database.row("SELECT count(*) AS quotes FROM quotes", ()) == exp_count


@pytest.mark.database
def test_latest() -> None:
    """The last fetched; two fetched at the same moment, the last stored."""
    database = helper_database()
    tested = QuoteStore(database)
    tested.stored(helper_quote("AAPL", "343.0000", 5))
    tested.stored(helper_quote("AAPL", "344.0000", 9))
    tested.stored(helper_quote("AAPL", "341.0000", 1))
    tested.stored(helper_quote("MSFT", "501.0000", 30))
    tested.stored(helper_quote("MMM", "150.0000", 7))
    tested.stored(helper_quote("MMM", "151.0000", 7))
    result = (tested.latest("AAPL"), tested.latest("MMM"), tested.latest("ZZZ"))
    expected = (helper_quote("AAPL", "344.0000", 9), helper_quote("MMM", "151.0000", 7), None)
    assert result == expected


@pytest.mark.database
def test_latest_before() -> None:
    database = helper_database()
    tested = QuoteStore(database)
    tested.stored(helper_quote("AAPL", "343.0000", 5))
    tested.stored(helper_quote("AAPL", "344.0000", 9))
    tested.stored(helper_quote("MSFT", "501.0000", 6))
    result = (
        tested.latest_before("AAPL", datetime(2026, 10, 21, 15, 8, tzinfo=UTC)),
        tested.latest_before("AAPL", datetime(2026, 10, 21, 15, 9, tzinfo=UTC)),
        tested.latest_before("AAPL", datetime(2026, 10, 21, 15, 4, tzinfo=UTC)),
    )
    # At or before the moment.
    expected = (helper_quote("AAPL", "343.0000", 5), helper_quote("AAPL", "344.0000", 9), None)
    assert result == expected


@pytest.mark.database
def test_bars() -> None:
    database = helper_database()
    tested = QuoteStore(database)
    tested.bars_replaced(
        "AAPL",
        [helper_bar("AAPL", 21, "343.9900"), helper_bar("AAPL", 19, "338.2000"), helper_bar("AAPL", 20, "339.5000")],
        date(2026, 10, 21),
    )
    tested.bars_replaced("MSFT", [helper_bar("MSFT", 21, "501.0000")], date(2026, 10, 21))
    result = (tested.bars("AAPL", 2), tested.bars("AAPL", 10), tested.bars("ZZZ", 10))
    # The latest days, oldest first.
    expected = (
        [helper_bar("AAPL", 20, "339.5000"), helper_bar("AAPL", 21, "343.9900")],
        [helper_bar("AAPL", 19, "338.2000"), helper_bar("AAPL", 20, "339.5000"), helper_bar("AAPL", 21, "343.9900")],
        [],
    )
    assert result == expected


@pytest.mark.database
def test_bars_replaced() -> None:
    """A day already stored is overwritten; the fetch day moves with the bars."""
    database = helper_database()
    tested = QuoteStore(database)
    tested.bars_replaced("AAPL", [helper_bar("AAPL", 20, "339.5000")], date(2026, 10, 20))
    result = tested.bars_replaced(
        "AAPL", [helper_bar("AAPL", 20, "340.0000"), helper_bar("AAPL", 21, "343.9900")], date(2026, 10, 21)
    )
    assert result is None
    expected = [
        {
            "symbol": "AAPL",
            "day": date(2026, 10, 20),
            "open": Decimal("339.3600"),
            "high": Decimal("345.2500"),
            "low": Decimal("338.8300"),
            "close": Decimal("340.0000"),
            "volume": 35586943,
        },
        {
            "symbol": "AAPL",
            "day": date(2026, 10, 21),
            "open": Decimal("339.3600"),
            "high": Decimal("345.2500"),
            "low": Decimal("338.8300"),
            "close": Decimal("343.9900"),
            "volume": 35586943,
        },
    ]
    assert (
        database.rows("SELECT symbol, day, open, high, low, close, volume FROM daily_bars ORDER BY day", ()) == expected
    )
    exp_fetches = [{"symbol": "AAPL", "fetched_on": date(2026, 10, 21)}]
    assert database.rows("SELECT symbol, fetched_on FROM history_fetches", ()) == exp_fetches


@pytest.mark.database
def test_bars_replaced__a_failure_keeps_neither() -> None:
    """The bars and the fetch day together: a failed write leaves neither."""
    database = helper_database()
    tested = QuoteStore(database)
    broken = helper_bar("AAPL", 21, "343.9900")._replace(volume=10**20)
    with pytest.raises(AppException) as exc_info:
        tested.bars_replaced("AAPL", [helper_bar("AAPL", 20, "339.5000"), broken], date(2026, 10, 21))
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (503, "The database is unavailable.")
    assert result == expected
    exp_counts = {"bars": 0, "fetches": 0}
    counts = database.row(
        "SELECT (SELECT count(*) FROM daily_bars) AS bars, (SELECT count(*) FROM history_fetches) AS fetches", ()
    )
    assert counts == exp_counts


@pytest.mark.database
def test_fetched_on() -> None:
    database = helper_database()
    tested = QuoteStore(database)
    tested.bars_replaced("AAPL", [], date(2026, 10, 21))
    result = (tested.fetched_on("AAPL"), tested.fetched_on("MSFT"))
    expected = (date(2026, 10, 21), None)
    assert result == expected
