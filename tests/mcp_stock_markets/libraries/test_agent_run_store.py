from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from mcp_stock_markets.constants.run_status import RunStatus
from mcp_stock_markets.constants.run_trigger import RunTrigger
from mcp_stock_markets.constants.step_kind import StepKind
from mcp_stock_markets.libraries.agent_run_store import AgentRunStore
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.structures.agent_run import AgentRun
from mcp_stock_markets.structures.agent_step import AgentStep
from tests.conftest import helper_database

STARTED = datetime(2026, 10, 21, 14, 0, tzinfo=UTC)


def helper_is_recent(moment: datetime | None) -> bool:
    return moment is not None and abs(datetime.now(UTC) - moment) < timedelta(minutes=5)


def helper_run(run_id: int, trigger: RunTrigger, started_at: datetime) -> AgentRun:
    return AgentRun(
        run_id=run_id,
        trigger=trigger,
        status=RunStatus.RUNNING,
        started_at=started_at,
        finished_at=None,
        connection_name="Local",
        model="good",
        turns=0,
        summary="",
        error="",
    )


def helper_started(database: Database, runs: list[tuple[RunTrigger, datetime]]) -> AgentRunStore:
    """The runs started, each dated for the test."""
    result = AgentRunStore(database)
    for trigger, started_at in runs:
        run = result.started(trigger, "Local", "good")
        database.executed("UPDATE agent_runs SET started_at = %s WHERE id = %s", (started_at, run.run_id))
    return result


def test___init__() -> None:
    database = Database("postgresql://u:p@h/d")
    tested = AgentRunStore(database)
    result = tested._database is database
    assert result is True


@pytest.mark.database
def test_started() -> None:
    database = helper_database()
    tested = AgentRunStore(database)
    first = tested.started(RunTrigger.SCHEDULE, "Local", "good")
    second = tested.started(RunTrigger.MANUAL, "Claude", "claude-opus-5-5")
    result = (first._replace(started_at=STARTED), second._replace(started_at=STARTED))
    expected = (
        helper_run(1, RunTrigger.SCHEDULE, STARTED),
        helper_run(2, RunTrigger.MANUAL, STARTED)._replace(connection_name="Claude", model="claude-opus-5-5"),
    )
    assert result == expected
    exp_recent = (True, True)
    assert (helper_is_recent(first.started_at), helper_is_recent(second.started_at)) == exp_recent


@pytest.mark.database
def test_stepped() -> None:
    """Numbered after the last step of the same run; arguments kept as JSON."""
    database = helper_database()
    tested = helper_started(database, [(RunTrigger.MANUAL, STARTED), (RunTrigger.MANUAL, STARTED)])
    first = tested.stepped(1, StepKind.MODEL, "", "", None, "Let me look at the market.", False, 812.5)
    second = tested.stepped(
        1, StepKind.TOOL, "quotes", "get_quote", {"symbol": "AAPL", "fresh": True}, '{"price": "343.99"}', False, 95.0
    )
    other = tested.stepped(2, StepKind.THINKING, "", "", None, "Thinking.", True, 1.0)
    result = [step._replace(created_at=STARTED) for step in (first, second, other)]
    expected = [
        AgentStep(1, 1, 1, StepKind.MODEL, "", "", None, "Let me look at the market.", False, 812.5, STARTED),
        AgentStep(
            2,
            1,
            2,
            StepKind.TOOL,
            "quotes",
            "get_quote",
            {"symbol": "AAPL", "fresh": True},
            '{"price": "343.99"}',
            False,
            95.0,
            STARTED,
        ),
        AgentStep(3, 2, 1, StepKind.THINKING, "", "", None, "Thinking.", True, 1.0, STARTED),
    ]
    assert result == expected
    exp_recent = [True, True, True]
    assert [helper_is_recent(step.created_at) for step in (first, second, other)] == exp_recent


@pytest.mark.database
def test_finished() -> None:
    database = helper_database()
    tested = helper_started(database, [(RunTrigger.MANUAL, STARTED), (RunTrigger.MANUAL, STARTED)])
    result = tested.finished(1, RunStatus.COMPLETED, 4, "Bought 2 AAPL.", "")
    assert result is None
    finished = tested.run(1)
    assert finished is not None
    expected = helper_run(1, RunTrigger.MANUAL, STARTED)._replace(
        status=RunStatus.COMPLETED, finished_at=STARTED, turns=4, summary="Bought 2 AAPL."
    )
    assert finished._replace(finished_at=STARTED) == expected
    exp_recent = True
    assert helper_is_recent(finished.finished_at) is exp_recent
    # The other run is untouched.
    exp_other = helper_run(2, RunTrigger.MANUAL, STARTED)
    assert tested.run(2) == exp_other


@pytest.mark.database
def test_abandoned() -> None:
    """Only the runs still `running` are marked failed."""
    database = helper_database()
    tested = helper_started(database, [(RunTrigger.MANUAL, STARTED)] * 3)
    tested.finished(2, RunStatus.COMPLETED, 1, "Done.", "")
    result = (tested.abandoned("The process stopped mid-run."), tested.abandoned("again"))
    expected = (2, 0)
    assert result == expected
    exp_rows = [
        {"id": 1, "status": "failed", "error": "The process stopped mid-run.", "is_finished": True},
        {"id": 2, "status": "completed", "error": "", "is_finished": True},
        {"id": 3, "status": "failed", "error": "The process stopped mid-run.", "is_finished": True},
    ]
    rows = database.rows(
        "SELECT id, status, error, finished_at IS NOT NULL AS is_finished FROM agent_runs ORDER BY id", ()
    )
    assert rows == exp_rows


@pytest.mark.database
def test_runs() -> None:
    """Newest first, up to the limit; two started at the same moment, the later id first."""
    database = helper_database()
    tested = helper_started(
        database,
        [
            (RunTrigger.SCHEDULE, datetime(2026, 10, 21, 14, 0, tzinfo=UTC)),
            (RunTrigger.MANUAL, datetime(2026, 10, 21, 15, 0, tzinfo=UTC)),
            (RunTrigger.SCHEDULE, datetime(2026, 10, 21, 15, 0, tzinfo=UTC)),
        ],
    )
    result = (tested.runs(2), tested.runs(10))
    expected = (
        [
            helper_run(3, RunTrigger.SCHEDULE, datetime(2026, 10, 21, 15, 0, tzinfo=UTC)),
            helper_run(2, RunTrigger.MANUAL, datetime(2026, 10, 21, 15, 0, tzinfo=UTC)),
        ],
        [
            helper_run(3, RunTrigger.SCHEDULE, datetime(2026, 10, 21, 15, 0, tzinfo=UTC)),
            helper_run(2, RunTrigger.MANUAL, datetime(2026, 10, 21, 15, 0, tzinfo=UTC)),
            helper_run(1, RunTrigger.SCHEDULE, datetime(2026, 10, 21, 14, 0, tzinfo=UTC)),
        ],
    )
    assert result == expected


@pytest.mark.database
def test_run() -> None:
    database = helper_database()
    tested = helper_started(database, [(RunTrigger.MANUAL, STARTED)])
    result = (tested.run(1), tested.run(2))
    expected = (helper_run(1, RunTrigger.MANUAL, STARTED), None)
    assert result == expected


@pytest.mark.database
def test_steps() -> None:
    database = helper_database()
    tested = helper_started(database, [(RunTrigger.MANUAL, STARTED), (RunTrigger.MANUAL, STARTED)])
    tested.stepped(1, StepKind.MODEL, "", "", None, "First.", False, 1.0)
    tested.stepped(2, StepKind.MODEL, "", "", None, "Elsewhere.", False, 1.0)
    tested.stepped(1, StepKind.TOOL, "broker", "buy", {"symbol": "MMM", "quantity": 1}, "Bought.", False, 2.0)
    database.executed("UPDATE agent_steps SET created_at = %s", (STARTED,))
    result = (tested.steps(1), tested.steps(3))
    expected = (
        [
            AgentStep(1, 1, 1, StepKind.MODEL, "", "", None, "First.", False, 1.0, STARTED),
            AgentStep(
                3,
                1,
                2,
                StepKind.TOOL,
                "broker",
                "buy",
                {"symbol": "MMM", "quantity": 1},
                "Bought.",
                False,
                2.0,
                STARTED,
            ),
        ],
        [],
    )
    assert result == expected


@pytest.mark.database
def test_last_started() -> None:
    database = helper_database()
    tested = helper_started(
        database,
        [
            (RunTrigger.SCHEDULE, datetime(2026, 10, 21, 14, 0, tzinfo=UTC)),
            (RunTrigger.SCHEDULE, datetime(2026, 10, 21, 14, 30, tzinfo=UTC)),
            (RunTrigger.MANUAL, datetime(2026, 10, 21, 15, 0, tzinfo=UTC)),
        ],
    )
    result = (tested.last_started(RunTrigger.SCHEDULE), tested.last_started(RunTrigger.MANUAL))
    expected = (datetime(2026, 10, 21, 14, 30, tzinfo=UTC), datetime(2026, 10, 21, 15, 0, tzinfo=UTC))
    assert result == expected


@pytest.mark.database
def test_last_started__none_yet() -> None:
    database = helper_database()
    tested = AgentRunStore(database)
    result = tested.last_started(RunTrigger.SCHEDULE)
    assert result is None
