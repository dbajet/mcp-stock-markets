from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import call, patch
from zoneinfo import ZoneInfo

import pytest

from mcp_stock_markets.libraries.market_clock import MarketClock
from mcp_stock_markets.structures.market_status import MarketStatus

NEW_YORK = ZoneInfo("America/New_York")


def test___init__() -> None:
    tested = MarketClock()
    result = (tested._zone, sorted(tested._holidays), sorted(tested._early_closes))
    expected = (
        ZoneInfo("America/New_York"),
        [
            date(2026, 1, 1),
            date(2026, 1, 19),
            date(2026, 2, 16),
            date(2026, 4, 3),
            date(2026, 5, 25),
            date(2026, 6, 19),
            date(2026, 7, 3),
            date(2026, 9, 7),
            date(2026, 11, 26),
            date(2026, 12, 25),
            date(2027, 1, 1),
            date(2027, 1, 18),
            date(2027, 2, 15),
            date(2027, 3, 26),
            date(2027, 5, 31),
            date(2027, 6, 18),
            date(2027, 7, 5),
            date(2027, 9, 6),
            date(2027, 11, 25),
            date(2027, 12, 24),
        ],
        [date(2026, 11, 27), date(2026, 12, 24), date(2027, 11, 26)],
    )
    assert result == expected


@pytest.mark.parametrize(
    "now, expected",
    [
        pytest.param(
            datetime(2026, 10, 21, 14, 0, tzinfo=UTC),
            MarketStatus(
                is_open=True,
                now=datetime(2026, 10, 21, 10, 0, tzinfo=NEW_YORK),
                closes_at=datetime(2026, 10, 21, 16, 0, tzinfo=NEW_YORK),
                next_open=datetime(2026, 10, 22, 9, 30, tzinfo=NEW_YORK),
            ),
            id="open-in-daylight-time",
        ),
        pytest.param(
            datetime(2026, 10, 21, 13, 29, tzinfo=UTC),
            MarketStatus(
                is_open=False,
                now=datetime(2026, 10, 21, 9, 29, tzinfo=NEW_YORK),
                closes_at=None,
                next_open=datetime(2026, 10, 21, 9, 30, tzinfo=NEW_YORK),
            ),
            id="a-minute-before-the-opening",
        ),
        pytest.param(
            datetime(2026, 10, 21, 13, 30, tzinfo=UTC),
            MarketStatus(
                is_open=True,
                now=datetime(2026, 10, 21, 9, 30, tzinfo=NEW_YORK),
                closes_at=datetime(2026, 10, 21, 16, 0, tzinfo=NEW_YORK),
                next_open=datetime(2026, 10, 22, 9, 30, tzinfo=NEW_YORK),
            ),
            id="at-the-opening",
        ),
        pytest.param(
            datetime(2026, 10, 21, 20, 0, tzinfo=UTC),
            MarketStatus(
                is_open=False,
                now=datetime(2026, 10, 21, 16, 0, tzinfo=NEW_YORK),
                closes_at=None,
                next_open=datetime(2026, 10, 22, 9, 30, tzinfo=NEW_YORK),
            ),
            id="at-the-closing",
        ),
        pytest.param(
            datetime(2026, 11, 2, 14, 29, tzinfo=UTC),
            MarketStatus(
                is_open=False,
                now=datetime(2026, 11, 2, 9, 29, tzinfo=NEW_YORK),
                closes_at=None,
                next_open=datetime(2026, 11, 2, 9, 30, tzinfo=NEW_YORK),
            ),
            id="standard-time-14-29-utc-is-before-the-opening",
        ),
        pytest.param(
            datetime(2026, 11, 2, 14, 30, tzinfo=UTC),
            MarketStatus(
                is_open=True,
                now=datetime(2026, 11, 2, 9, 30, tzinfo=NEW_YORK),
                closes_at=datetime(2026, 11, 2, 16, 0, tzinfo=NEW_YORK),
                next_open=datetime(2026, 11, 3, 9, 30, tzinfo=NEW_YORK),
            ),
            id="standard-time-14-30-utc-is-the-opening",
        ),
        pytest.param(
            datetime(2026, 11, 26, 15, 0, tzinfo=UTC),
            MarketStatus(
                is_open=False,
                now=datetime(2026, 11, 26, 10, 0, tzinfo=NEW_YORK),
                closes_at=None,
                next_open=datetime(2026, 11, 27, 9, 30, tzinfo=NEW_YORK),
            ),
            id="thanksgiving",
        ),
        pytest.param(
            datetime(2026, 11, 27, 17, 59, tzinfo=UTC),
            MarketStatus(
                is_open=True,
                now=datetime(2026, 11, 27, 12, 59, tzinfo=NEW_YORK),
                closes_at=datetime(2026, 11, 27, 13, 0, tzinfo=NEW_YORK),
                next_open=datetime(2026, 11, 30, 9, 30, tzinfo=NEW_YORK),
            ),
            id="early-close-still-open",
        ),
        pytest.param(
            datetime(2026, 11, 27, 18, 0, tzinfo=UTC),
            MarketStatus(
                is_open=False,
                now=datetime(2026, 11, 27, 13, 0, tzinfo=NEW_YORK),
                closes_at=None,
                next_open=datetime(2026, 11, 30, 9, 30, tzinfo=NEW_YORK),
            ),
            id="early-close-closed-at-13",
        ),
        pytest.param(
            datetime(2026, 10, 24, 15, 0, tzinfo=UTC),
            MarketStatus(
                is_open=False,
                now=datetime(2026, 10, 24, 11, 0, tzinfo=NEW_YORK),
                closes_at=None,
                next_open=datetime(2026, 10, 26, 9, 30, tzinfo=NEW_YORK),
            ),
            id="saturday",
        ),
    ],
)
def test_status(now: datetime, expected: MarketStatus) -> None:
    tested = MarketClock()
    result = tested.status(now)
    assert result == expected
    # Read in New York time, whatever zone the moment came in.
    exp_zone = "America/New_York"
    assert str(result.now.tzinfo) == exp_zone


@pytest.mark.parametrize(
    "day, expected, exp_offsets",
    [
        pytest.param(
            date(2026, 10, 21),
            (datetime(2026, 10, 21, 9, 30, tzinfo=NEW_YORK), datetime(2026, 10, 21, 16, 0, tzinfo=NEW_YORK)),
            (timedelta(hours=-4), timedelta(hours=-4)),
            id="a-wednesday-in-daylight-time",
        ),
        pytest.param(
            date(2026, 11, 2),
            (datetime(2026, 11, 2, 9, 30, tzinfo=NEW_YORK), datetime(2026, 11, 2, 16, 0, tzinfo=NEW_YORK)),
            (timedelta(hours=-5), timedelta(hours=-5)),
            id="a-monday-in-standard-time",
        ),
        pytest.param(
            date(2026, 12, 24),
            (datetime(2026, 12, 24, 9, 30, tzinfo=NEW_YORK), datetime(2026, 12, 24, 13, 0, tzinfo=NEW_YORK)),
            (timedelta(hours=-5), timedelta(hours=-5)),
            id="christmas-eve-closes-early",
        ),
        pytest.param(date(2026, 12, 25), None, None, id="christmas"),
        pytest.param(date(2026, 10, 24), None, None, id="saturday"),
        pytest.param(date(2026, 10, 25), None, None, id="sunday"),
    ],
)
def test_session(
    day: date,
    expected: tuple[datetime, datetime] | None,
    exp_offsets: tuple[timedelta, timedelta] | None,
) -> None:
    tested = MarketClock()
    result = tested.session(day)
    assert result == expected
    offsets = None if result is None else (result[0].utcoffset(), result[1].utcoffset())
    assert offsets == exp_offsets


@pytest.mark.parametrize(
    "local, expected",
    [
        pytest.param(
            datetime(2026, 10, 21, 8, 0, tzinfo=NEW_YORK),
            datetime(2026, 10, 21, 9, 30, tzinfo=NEW_YORK),
            id="today-still-ahead",
        ),
        pytest.param(
            datetime(2026, 10, 21, 9, 30, tzinfo=NEW_YORK),
            datetime(2026, 10, 22, 9, 30, tzinfo=NEW_YORK),
            id="today-just-opened",
        ),
        pytest.param(
            datetime(2026, 10, 23, 17, 0, tzinfo=NEW_YORK),
            datetime(2026, 10, 26, 9, 30, tzinfo=NEW_YORK),
            id="friday-evening-to-monday",
        ),
        pytest.param(
            datetime(2026, 12, 24, 14, 0, tzinfo=NEW_YORK),
            datetime(2026, 12, 28, 9, 30, tzinfo=NEW_YORK),
            id="over-christmas-and-a-weekend",
        ),
        pytest.param(
            datetime(2026, 10, 30, 17, 0, tzinfo=NEW_YORK),
            datetime(2026, 11, 2, 9, 30, tzinfo=NEW_YORK),
            id="across-the-end-of-daylight-time",
        ),
    ],
)
def test_next_open(local: datetime, expected: datetime) -> None:
    tested = MarketClock()
    result = tested.next_open(local)
    assert result == expected


def test_next_open__no_trading_day_in_two_weeks() -> None:
    tested = MarketClock()
    with patch.object(MarketClock, "session", side_effect=[None] * 14) as mock_session:
        with pytest.raises(RuntimeError) as exc_info:
            tested.next_open(datetime(2026, 10, 21, 8, 0, tzinfo=NEW_YORK))
    expected = "no trading day in two weeks: the holiday calendar is wrong"
    assert str(exc_info.value) == expected
    exp_calls = [
        call(date(2026, 10, 21)),
        call(date(2026, 10, 22)),
        call(date(2026, 10, 23)),
        call(date(2026, 10, 24)),
        call(date(2026, 10, 25)),
        call(date(2026, 10, 26)),
        call(date(2026, 10, 27)),
        call(date(2026, 10, 28)),
        call(date(2026, 10, 29)),
        call(date(2026, 10, 30)),
        call(date(2026, 10, 31)),
        call(date(2026, 11, 1)),
        call(date(2026, 11, 2)),
        call(date(2026, 11, 3)),
    ]
    assert mock_session.mock_calls == exp_calls


@pytest.mark.parametrize(
    "is_open, expected",
    [
        pytest.param(True, True, id="open"),
        pytest.param(False, False, id="closed"),
    ],
)
def test_is_open(is_open: bool, expected: bool) -> None:
    tested = MarketClock()
    status = MarketStatus(
        is_open=is_open,
        now=datetime(2026, 10, 21, 10, 0, tzinfo=NEW_YORK),
        closes_at=None,
        next_open=datetime(2026, 10, 22, 9, 30, tzinfo=NEW_YORK),
    )
    with patch.object(MarketClock, "status", side_effect=[status]) as mock_status:
        result = tested.is_open(datetime(2026, 10, 21, 14, 0, tzinfo=UTC))
    assert result is expected
    exp_calls = [call(datetime(2026, 10, 21, 14, 0, tzinfo=UTC))]
    assert mock_status.mock_calls == exp_calls
