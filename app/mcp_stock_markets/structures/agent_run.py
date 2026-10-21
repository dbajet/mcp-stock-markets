from __future__ import annotations

from datetime import datetime
from typing import Any, NamedTuple

from mcp_stock_markets.constants.run_status import RunStatus
from mcp_stock_markets.constants.run_trigger import RunTrigger
from mcp_stock_markets.structures.wire import Wire


class AgentRun(NamedTuple):
    """One session of the agent: what started it, which model it used, how
    it ended, and the summary it wrote."""

    run_id: int
    trigger: RunTrigger
    status: RunStatus
    started_at: datetime
    finished_at: datetime | None
    connection_name: str
    model: str
    turns: int
    summary: str
    error: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "trigger": self.trigger.value,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "finished_at": None if self.finished_at is None else self.finished_at.isoformat(),
            "connection_name": self.connection_name,
            "model": self.model,
            "turns": self.turns,
            "summary": self.summary,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentRun:
        return cls(
            run_id=int(data["run_id"]),
            trigger=RunTrigger(data["trigger"]),
            status=RunStatus(data["status"]),
            started_at=Wire.moment(data["started_at"]),
            finished_at=None if data["finished_at"] is None else Wire.moment(data["finished_at"]),
            connection_name=str(data["connection_name"]),
            model=str(data["model"]),
            turns=int(data["turns"]),
            summary=str(data["summary"]),
            error=str(data["error"]),
        )
