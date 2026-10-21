from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

from tests.support.frozen_datetime import FrozenDatetime

MOMENT = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)


def test_inheritance() -> None:
    result = issubclass(FrozenDatetime, datetime)
    assert result is True


def test_now() -> None:
    module = SimpleNamespace(datetime=datetime)
    with FrozenDatetime.installed(MOMENT, [module]) as frozen:  # type: ignore[list-item]
        result = (frozen.now(UTC), frozen.now(timezone(timedelta(hours=-4))).isoformat(), frozen.now())
    expected = (MOMENT, "2026-10-21T11:00:00-04:00", MOMENT)
    assert result == expected


def test_installed() -> None:
    first = SimpleNamespace(datetime=datetime)
    second = SimpleNamespace(datetime=datetime)
    with FrozenDatetime.installed(MOMENT, [first, second]) as frozen:  # type: ignore[list-item]
        during = (first.datetime is frozen, second.datetime is frozen, issubclass(frozen, FrozenDatetime))
        parsed = first.datetime.fromisoformat("2026-01-02T03:04:05+00:00")
    result = (during, first.datetime is datetime, second.datetime is datetime, parsed)
    expected = ((True, True, True), True, True, datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC))
    assert result == expected
