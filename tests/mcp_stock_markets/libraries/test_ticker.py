from __future__ import annotations

import logging
import threading
from decimal import Decimal
from unittest.mock import Mock, call, patch

import pytest

from mcp_stock_markets.libraries.alerter import Alerter
from mcp_stock_markets.libraries.email_box import EmailBox
from mcp_stock_markets.libraries.ticker import Ticker
from mcp_stock_markets.structures.settings import Settings


def helper_alerter() -> Alerter:
    settings = Settings(
        environment="dev",
        database_url="postgresql://u:p@h/d",
        app_version="dev",
        build_time="dev",
        app_commit="dev",
        app_base_url="http://localhost:8140",
        data_key="the-data-key",
        smtp_host="",
        smtp_port=587,
        smtp_user="",
        smtp_password="",
        email_from="",
        bootstrap_admin_email="",
        starting_budget=Decimal("500.00"),
        max_companies=5,
        alpaca_key_id="",
        alpaca_secret_key="",
        agent_interval_minutes=30,
        mcp_base_url="http://127.0.0.1:8000",
        mcp_token="mcp-token",
    )
    return Alerter(EmailBox(settings), "ops@example.com")


def test___init__() -> None:
    alerter = helper_alerter()
    tick = Mock(side_effect=[])
    tested = Ticker("valuations", 60.0, tick, alerter)
    result = (
        tested._name,
        tested._interval,
        tested._tick is tick,
        tested._alerter is alerter,
        tested._stopping.is_set(),
        tested._thread,
    )
    expected = ("valuations", 60.0, True, True, False, None)
    assert result == expected
    exp_calls: list[object] = []
    assert tick.mock_calls == exp_calls


def test_started() -> None:
    tested = Ticker("valuations", 60.0, Mock(side_effect=[]), helper_alerter())
    tested._stopping.set()
    with patch.object(Ticker, "ran", side_effect=[None]) as mock_ran:
        tested.started()
        thread = tested._thread
        assert thread is not None
        thread.join(5.0)
    result = (thread.name, thread.daemon, thread.is_alive(), tested._stopping.is_set())
    # A ticker stopped before starts again: the stop is forgotten.
    expected = ("valuations", True, False, False)
    assert result == expected
    exp_calls = [call()]
    assert mock_ran.mock_calls == exp_calls


def test_stopped() -> None:
    """A ticker waiting out an hour's interval stops at once."""
    ticked = threading.Event()
    tick = Mock(side_effect=lambda: ticked.set())
    tested = Ticker("valuations", 3600.0, tick, helper_alerter())
    tested.started()
    try:
        assert ticked.wait(5.0) is True
        thread = tested._thread
    finally:
        tested.stopped()
    result = (tested._thread, tested._stopping.is_set(), thread is not None and thread.is_alive())
    expected = (None, True, False)
    assert result == expected
    exp_calls = [call()]
    assert tick.mock_calls == exp_calls


def test_stopped__never_started() -> None:
    tested = Ticker("valuations", 60.0, Mock(side_effect=[]), helper_alerter())
    result = tested.stopped()
    assert result is None
    expected = (None, True)
    assert (tested._thread, tested._stopping.is_set()) == expected


def test_ran() -> None:
    """A tick, then the wait, until the stop is seen."""
    tested = Ticker("valuations", 60.0, Mock(side_effect=[]), helper_alerter())
    with (
        patch.object(tested._stopping, "is_set", side_effect=[False, False, True]) as mock_is_set,
        patch.object(tested._stopping, "wait", side_effect=[False, True]) as mock_wait,
        patch.object(Ticker, "ticked", side_effect=[None, None]) as mock_ticked,
    ):
        result = tested.ran()
    assert result is None
    exp_calls = [call(), call(), call()]
    assert mock_is_set.mock_calls == exp_calls
    exp_calls = [call(60.0), call(60.0)]
    assert mock_wait.mock_calls == exp_calls
    exp_calls = [call(), call()]
    assert mock_ticked.mock_calls == exp_calls


def test_ran__stopped_before_the_first_tick() -> None:
    tested = Ticker("valuations", 60.0, Mock(side_effect=[]), helper_alerter())
    tested._stopping.set()
    with patch.object(Ticker, "ticked", side_effect=[]) as mock_ticked:
        tested.ran()
    expected: list[object] = []
    assert mock_ticked.mock_calls == expected


def test_ticked() -> None:
    tick = Mock(side_effect=[None])
    tested = Ticker("valuations", 60.0, tick, helper_alerter())
    with patch.object(Alerter, "alerted", side_effect=[]) as mock_alerted:
        result = tested.ticked()
    assert result is None
    exp_calls = [call()]
    assert tick.mock_calls == exp_calls
    exp_calls = []
    assert mock_alerted.mock_calls == exp_calls


def test_ticked__a_failure_is_logged_and_alerted(caplog: pytest.LogCaptureFixture) -> None:
    """The loop never dies: the failure is logged and a person told."""
    tick = Mock(side_effect=[ValueError("bad price")])
    tested = Ticker("valuations", 60.0, tick, helper_alerter())
    with (
        patch.object(Alerter, "alerted", side_effect=[None]) as mock_alerted,
        caplog.at_level(logging.ERROR, logger="mcp_stock_markets"),
    ):
        result = tested.ticked()
    assert result is None
    exp_logs = ["[TICKER] the valuations tick failed"]
    assert [record.getMessage() for record in caplog.records] == exp_logs
    exp_calls = [call()]
    assert tick.mock_calls == exp_calls
    exp_calls = [call("valuations", "ValueError")]
    assert mock_alerted.mock_calls == exp_calls
