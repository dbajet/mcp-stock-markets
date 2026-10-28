from __future__ import annotations

import logging
import queue
from decimal import Decimal
from unittest.mock import Mock, call, patch

import pytest

from mcp_stock_markets.libraries.alerter import Alerter
from mcp_stock_markets.libraries.email_box import EmailBox
from mcp_stock_markets.libraries.job_queue import JobQueue
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


def helper_instance() -> JobQueue:
    return JobQueue("emails", helper_alerter())


def test___init__() -> None:
    alerter = helper_alerter()
    tested = JobQueue("emails", alerter)
    result = (tested._name, tested._alerter is alerter, tested._jobs.empty(), tested._stopping.is_set(), tested._thread)
    expected = ("emails", True, True, False, None)
    assert result == expected


def test_started() -> None:
    tested = helper_instance()
    tested._stopping.set()
    tested.started()
    try:
        thread = tested._thread
        assert thread is not None
        result = (thread.name, thread.daemon, thread.is_alive(), tested._stopping.is_set())
    finally:
        tested.stopped()
    expected = ("emails", True, True, False)
    assert result == expected


def test_stopped() -> None:
    """The jobs still queued leave before the thread is joined."""
    tested = helper_instance()
    job = Mock(side_effect=[None, None])
    tested.started()
    thread = tested._thread
    try:
        tested.queued(job, ("ada@example.com",))
        tested.queued(job, ("bob@example.com",))
    finally:
        tested.stopped()
    assert thread is not None
    result = (tested._thread, thread.is_alive(), tested._stopping.is_set(), tested._jobs.empty())
    expected = (None, False, True, True)
    assert result == expected
    exp_calls = [call("ada@example.com"), call("bob@example.com")]
    assert job.mock_calls == exp_calls


def test_stopped__never_started() -> None:
    tested = helper_instance()
    tested.stopped()
    result = (tested._thread, tested._stopping.is_set())
    expected = (None, True)
    assert result == expected


def test_queued() -> None:
    tested = helper_instance()
    job = Mock(side_effect=[])
    tested.queued(job, ("ada@example.com", "tok"))
    result = tested._jobs.get_nowait()
    expected = (job, ("ada@example.com", "tok"))
    assert result == expected
    exp_calls: list[object] = []
    assert job.mock_calls == exp_calls


def test_ran() -> None:
    """A stopping loop drains what is queued, then returns."""
    tested = helper_instance()
    job = Mock(side_effect=[])
    tested.queued(job, ("a",))
    tested.queued(job, ("b",))
    tested._stopping.set()
    with patch.object(JobQueue, "performed", side_effect=[None, None]) as mock_performed:
        result = tested.ran()
    assert result is None
    exp_calls = [call(job, ("a",)), call(job, ("b",))]
    assert mock_performed.mock_calls == exp_calls
    exp_empty = True
    assert tested._jobs.empty() is exp_empty


def test_ran__waits_through_an_idle_poll() -> None:
    tested = helper_instance()
    job = Mock(side_effect=[])
    with (
        patch.object(queue.Queue, "get", side_effect=[queue.Empty(), (job, ("a",))]) as mock_get,
        patch.object(JobQueue, "performed", side_effect=lambda *_: tested._stopping.set()) as mock_performed,
    ):
        tested.ran()
    exp_calls = [call(timeout=1.0), call(timeout=1.0)]
    assert mock_get.mock_calls == exp_calls
    exp_calls = [call(job, ("a",))]
    assert mock_performed.mock_calls == exp_calls


def test_performed(caplog: pytest.LogCaptureFixture) -> None:
    tested = helper_instance()
    job = Mock(side_effect=[None])
    with (
        patch.object(Alerter, "alerted", side_effect=[]) as mock_alerted,
        caplog.at_level(logging.WARNING, logger="mcp_stock_markets"),
    ):
        result = tested.performed(job, ("ada@example.com", "tok"))
    assert result is None
    exp_calls = [call("ada@example.com", "tok")]
    assert job.mock_calls == exp_calls
    exp_calls = []
    assert mock_alerted.mock_calls == exp_calls
    exp_messages: list[str] = []
    assert [record.getMessage() for record in caplog.records] == exp_messages


def test_performed__a_failing_job_is_logged_and_alerted(caplog: pytest.LogCaptureFixture) -> None:
    tested = helper_instance()
    job = Mock(side_effect=[ValueError("boom")])
    with (
        patch.object(Alerter, "alerted", side_effect=[None]) as mock_alerted,
        caplog.at_level(logging.WARNING, logger="mcp_stock_markets"),
    ):
        result = tested.performed(job, ("ada@example.com",))
    assert result is None
    exp_calls = [call("ada@example.com")]
    assert job.mock_calls == exp_calls
    exp_calls = [call("emails", "ValueError")]
    assert mock_alerted.mock_calls == exp_calls
    exp_records = [("ERROR", "[JOBS] a emails job failed", ValueError)]
    result_records = [
        (record.levelname, record.getMessage(), record.exc_info[0] if record.exc_info else None)
        for record in caplog.records
    ]
    assert result_records == exp_records
