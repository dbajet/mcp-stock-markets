from __future__ import annotations

from mcp_stock_markets.libraries import alpha_vantage_box as alpha_vantage_box_module
from tests.support.fake_clock import FakeClock


def test___init__() -> None:
    tested = FakeClock(100.0)
    result = (tested.now, tested.calls)
    expected = (100.0, [])
    assert result == expected


def test_installed() -> None:
    tested = FakeClock(100.0)
    original = alpha_vantage_box_module.time
    with tested.installed(alpha_vantage_box_module) as installed:
        result = (installed is tested, alpha_vantage_box_module.time is tested)
    expected = (True, True)
    assert result == expected
    exp_restored = original
    assert alpha_vantage_box_module.time is exp_restored


def test_monotonic() -> None:
    tested = FakeClock(100.0)
    result = (tested.monotonic(), tested.monotonic())
    expected = (100.0, 100.0)
    assert result == expected
    exp_calls = [("monotonic",), ("monotonic",)]
    assert tested.calls == exp_calls


def test_sleep() -> None:
    tested = FakeClock(100.0)
    result = tested.sleep(1.5)
    assert result is None
    expected = 101.5
    assert tested.now == expected
    exp_calls = [("sleep", 1.5)]
    assert tested.calls == exp_calls


def test_advanced() -> None:
    tested = FakeClock(100.0)
    result = tested.advanced(3.0)
    assert result is None
    expected = 103.0
    assert tested.now == expected
    exp_calls: list[tuple[object, ...]] = []
    assert tested.calls == exp_calls
