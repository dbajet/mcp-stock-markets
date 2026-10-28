from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request

from mcp_stock_markets.commands.agent_command import AgentCommand
from mcp_stock_markets.constants.agent_constants import AgentConstants
from mcp_stock_markets.constants.run_trigger import RunTrigger
from mcp_stock_markets.handlers.session_guard import SessionGuard


class AgentRouter:
    """The agent page: its runs with their transcripts, Run now, and the MCP
    servers with the tools they list."""

    def __init__(self, guard: SessionGuard, agent: AgentCommand) -> None:
        self._guard = guard
        self._agent = agent

    def router(self) -> APIRouter:
        result = APIRouter(prefix="/api/agent")
        result.add_api_route("/runs", self.runs, methods=["GET"])
        result.add_api_route("/runs", self.started, methods=["POST"])
        result.add_api_route("/runs/{run_id}", self.run, methods=["GET"])
        result.add_api_route("/servers", self.servers, methods=["GET"])
        return result

    def runs(self, request: Request, start: datetime, end: datetime) -> dict[str, Any]:
        """The runs started from `start` up to `end` (ISO moments), and the most
        a range lists, so the page can say when it shows only the latest."""
        self._guard.user(request)
        return {
            "runs": [run.to_dict() for run in self._agent.runs(start, end)],
            "limit": AgentConstants.runs_page,
        }

    def started(self, request: Request) -> dict[str, Any]:
        """Queued, not run: a run takes minutes, longer than a request may."""
        self._guard.user(request)
        self._agent.queued(RunTrigger.MANUAL)
        return {"ok": True, "detail": AgentConstants.queued}

    def run(self, request: Request, run_id: int) -> dict[str, Any]:
        self._guard.user(request)
        run, steps = self._agent.run(run_id)
        return {"run": run.to_dict(), "steps": [step.to_dict() for step in steps]}

    def servers(self, request: Request) -> dict[str, Any]:
        self._guard.user(request)
        return {"servers": self._agent.catalog()}
