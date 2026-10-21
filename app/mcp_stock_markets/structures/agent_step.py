from __future__ import annotations

from datetime import datetime
from typing import Any, NamedTuple

from mcp_stock_markets.constants.step_kind import StepKind
from mcp_stock_markets.structures.wire import Wire


class AgentStep(NamedTuple):
    """One thing that happened in a run, in order: the model's words, or a
    tool call sent to an MCP server with its arguments and the answer. The
    page shows them as the run's transcript."""

    step_id: int
    run_id: int
    position: int
    kind: StepKind
    server: str
    tool: str
    arguments: dict[str, Any] | None
    content: str
    is_error: bool
    elapsed_ms: float
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "run_id": self.run_id,
            "position": self.position,
            "kind": self.kind.value,
            "server": self.server,
            "tool": self.tool,
            "arguments": self.arguments,
            "content": self.content,
            "is_error": self.is_error,
            "elapsed_ms": self.elapsed_ms,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentStep:
        return cls(
            step_id=int(data["step_id"]),
            run_id=int(data["run_id"]),
            position=int(data["position"]),
            kind=StepKind(data["kind"]),
            server=str(data["server"]),
            tool=str(data["tool"]),
            arguments=None if data["arguments"] is None else dict(data["arguments"]),
            content=str(data["content"]),
            is_error=bool(data["is_error"]),
            elapsed_ms=float(data["elapsed_ms"]),
            created_at=Wire.moment(data["created_at"]),
        )
