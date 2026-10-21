from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from mcp_stock_markets.constants.run_status import RunStatus
from mcp_stock_markets.constants.run_trigger import RunTrigger
from mcp_stock_markets.structures.agent_run import AgentRun
from tests.conftest import is_namedtuple


def helper_instance(status: RunStatus, finished_at: datetime | None) -> AgentRun:
    return AgentRun(
        run_id=5,
        trigger=RunTrigger.SCHEDULE,
        status=status,
        started_at=datetime(2026, 10, 21, 14, 30, 0, tzinfo=UTC),
        finished_at=finished_at,
        connection_name="Claude",
        model="claude-opus-5-5",
        turns=4,
        summary="Bought two shares of AAPL.",
        error="",
    )


def helper_json(status: str, finished_at: str | None) -> dict[str, Any]:
    return {
        "run_id": 5,
        "trigger": "schedule",
        "status": status,
        "started_at": "2026-10-21T14:30:00+00:00",
        "finished_at": finished_at,
        "connection_name": "Claude",
        "model": "claude-opus-5-5",
        "turns": 4,
        "summary": "Bought two shares of AAPL.",
        "error": "",
    }


def test_class() -> None:
    tested = AgentRun
    fields = {
        "run_id": "int",
        "trigger": "RunTrigger",
        "status": "RunStatus",
        "started_at": "datetime",
        "finished_at": "datetime | None",
        "connection_name": "str",
        "model": "str",
        "turns": "int",
        "summary": "str",
        "error": "str",
    }
    assert is_namedtuple(tested, fields)


@pytest.mark.parametrize(
    "status, finished_at, exp_status, exp_finished_at",
    [
        pytest.param(
            RunStatus.COMPLETED,
            datetime(2026, 10, 21, 14, 33, 0, tzinfo=UTC),
            "completed",
            "2026-10-21T14:33:00+00:00",
            id="finished",
        ),
        pytest.param(RunStatus.RUNNING, None, "running", None, id="running"),
    ],
)
def test_to_dict(
    status: RunStatus,
    finished_at: datetime | None,
    exp_status: str,
    exp_finished_at: str | None,
) -> None:
    tested = helper_instance(status, finished_at)
    result = tested.to_dict()
    expected = {
        "run_id": 5,
        "trigger": "schedule",
        "status": exp_status,
        "started_at": "2026-10-21T14:30:00+00:00",
        "finished_at": exp_finished_at,
        "connection_name": "Claude",
        "model": "claude-opus-5-5",
        "turns": 4,
        "summary": "Bought two shares of AAPL.",
        "error": "",
    }
    assert result == expected


@pytest.mark.parametrize(
    "data, expected",
    [
        pytest.param(
            {
                "run_id": 5,
                "trigger": "schedule",
                "status": "completed",
                "started_at": datetime(2026, 10, 21, 14, 30, 0, tzinfo=UTC),
                "finished_at": datetime(2026, 10, 21, 14, 33, 0, tzinfo=UTC),
                "connection_name": "Claude",
                "model": "claude-opus-5-5",
                "turns": 4,
                "summary": "Bought two shares of AAPL.",
                "error": "",
            },
            helper_instance(RunStatus.COMPLETED, datetime(2026, 10, 21, 14, 33, 0, tzinfo=UTC)),
            id="database-row",
        ),
        pytest.param(
            helper_json("completed", "2026-10-21T14:33:00+00:00"),
            helper_instance(RunStatus.COMPLETED, datetime(2026, 10, 21, 14, 33, 0, tzinfo=UTC)),
            id="json-form",
        ),
        pytest.param(
            helper_json("running", None),
            helper_instance(RunStatus.RUNNING, None),
            id="json-running",
        ),
    ],
)
def test_from_dict(data: dict[str, Any], expected: AgentRun) -> None:
    tested = AgentRun
    result = tested.from_dict(data)
    assert result == expected


@pytest.mark.parametrize(
    "field",
    [
        pytest.param("run_id", id="run_id"),
        pytest.param("trigger", id="trigger"),
        pytest.param("status", id="status"),
        pytest.param("started_at", id="started_at"),
        pytest.param("finished_at", id="finished_at"),
        pytest.param("connection_name", id="connection_name"),
        pytest.param("model", id="model"),
        pytest.param("turns", id="turns"),
        pytest.param("summary", id="summary"),
        pytest.param("error", id="error"),
    ],
)
def test_from_dict__a_missing_field_raises(field: str) -> None:
    tested = AgentRun
    data = {key: value for key, value in helper_json("running", None).items() if key != field}
    with pytest.raises(KeyError) as exc_info:
        tested.from_dict(data)
    expected = (field,)
    assert exc_info.value.args == expected
