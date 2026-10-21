from __future__ import annotations

from typing import Any, NamedTuple

from mcp_stock_markets.structures.tool_call import ToolCall


class AgentReply(NamedTuple):
    """One answer of the model in a run: its text, a summary of its thinking
    when the provider gives one, the tools it calls, the model that wrote
    it, and the answer as the provider sent it (`raw`), which goes back
    unchanged in the next request — Claude's thinking blocks must, between
    tool calls."""

    text: str
    reasoning: str
    tool_calls: tuple[ToolCall, ...]
    model: str
    raw: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "reasoning": self.reasoning,
            "tool_calls": [call.to_dict() for call in self.tool_calls],
            "model": self.model,
            "raw": list(self.raw),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentReply:
        return cls(
            text=str(data["text"]),
            reasoning=str(data["reasoning"]),
            tool_calls=tuple(ToolCall.from_dict(call) for call in data["tool_calls"]),
            model=str(data["model"]),
            raw=tuple(dict(block) for block in data["raw"]),
        )
