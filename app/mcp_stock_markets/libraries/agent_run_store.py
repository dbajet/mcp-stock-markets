from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg.types.json import Jsonb

from mcp_stock_markets.constants.run_status import RunStatus
from mcp_stock_markets.constants.run_trigger import RunTrigger
from mcp_stock_markets.constants.step_kind import StepKind
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.structures.agent_run import AgentRun
from mcp_stock_markets.structures.agent_step import AgentStep


class AgentRunStore:
    """The agent's runs and their transcripts, written as they happen so the
    page can follow a run in progress."""

    _RUN = "id AS run_id, trigger, status, started_at, finished_at, connection_name, model, turns, summary, error"
    _STEP = """id AS step_id, run_id, position, kind, server, tool, arguments, content, is_error,
               elapsed_ms, created_at"""

    def __init__(self, database: Database) -> None:
        self._database = database

    def started(self, trigger: RunTrigger, connection_name: str, model: str) -> AgentRun:
        row = self._database.returned(
            f"""INSERT INTO agent_runs (trigger, status, connection_name, model) VALUES (%s, %s, %s, %s)
                RETURNING {self._RUN}""",
            (trigger.value, RunStatus.RUNNING.value, connection_name, model),
        )
        return AgentRun.from_dict(row)

    def stepped(
        self,
        run_id: int,
        kind: StepKind,
        server: str,
        tool: str,
        arguments: dict[str, Any] | None,
        content: str,
        is_error: bool,
        elapsed_ms: float,
    ) -> AgentStep:
        """The next step of the run, numbered after the last one."""
        row = self._database.returned(
            f"""INSERT INTO agent_steps (run_id, position, kind, server, tool, arguments, content, is_error, elapsed_ms)
                VALUES (%s, (SELECT coalesce(max(position), 0) + 1 FROM agent_steps WHERE run_id = %s),
                        %s, %s, %s, %s, %s, %s, %s)
                RETURNING {self._STEP}""",
            (
                run_id,
                run_id,
                kind.value,
                server,
                tool,
                None if arguments is None else Jsonb(arguments),
                content,
                is_error,
                elapsed_ms,
            ),
        )
        return AgentStep.from_dict(row)

    def finished(self, run_id: int, status: RunStatus, turns: int, summary: str, error: str) -> None:
        self._database.executed(
            """UPDATE agent_runs SET status = %s, finished_at = now(), turns = %s, summary = %s, error = %s
               WHERE id = %s""",
            (status.value, turns, summary, error, run_id),
        )

    def abandoned(self, error: str) -> int:
        """Runs left `running` by a process that stopped mid-run, marked
        failed; the caller holds the run lock, so none is really running."""
        return self._database.executed(
            "UPDATE agent_runs SET status = %s, finished_at = now(), error = %s WHERE status = %s",
            (RunStatus.FAILED.value, error, RunStatus.RUNNING.value),
        )

    def runs(self, start: datetime, end: datetime, limit: int) -> list[AgentRun]:
        """Started from `start` up to, not including, `end`; newest first."""
        rows = self._database.rows(
            f"""SELECT {self._RUN} FROM agent_runs WHERE started_at >= %s AND started_at < %s
                ORDER BY started_at DESC, id DESC LIMIT %s""",
            (start, end, limit),
        )
        return [AgentRun.from_dict(row) for row in rows]

    def run(self, run_id: int) -> AgentRun | None:
        row = self._database.row(f"SELECT {self._RUN} FROM agent_runs WHERE id = %s", (run_id,))
        return None if row is None else AgentRun.from_dict(row)

    def steps(self, run_id: int) -> list[AgentStep]:
        rows = self._database.rows(
            f"SELECT {self._STEP} FROM agent_steps WHERE run_id = %s ORDER BY position", (run_id,)
        )
        return [AgentStep.from_dict(row) for row in rows]

    def last_started(self, trigger: RunTrigger) -> datetime | None:
        row = self._database.row(
            "SELECT max(started_at) AS started_at FROM agent_runs WHERE trigger = %s", (trigger.value,)
        )
        return None if row is None else row["started_at"]
