from __future__ import annotations

from typing import Any, NamedTuple

from mcp_stock_markets.structures.agent_reply import AgentReply
from mcp_stock_markets.structures.tool_result import ToolResult


class AgentExchange(NamedTuple):
    """One round of a run: the model's reply, and the answers of the MCP
    servers to the tools it called. A run's conversation is its task and
    these rounds, which each provider's box writes in its own format."""

    reply: AgentReply
    results: tuple[ToolResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"reply": self.reply.to_dict(), "results": [result.to_dict() for result in self.results]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentExchange:
        return cls(
            reply=AgentReply.from_dict(data["reply"]),
            results=tuple(ToolResult.from_dict(result) for result in data["results"]),
        )
