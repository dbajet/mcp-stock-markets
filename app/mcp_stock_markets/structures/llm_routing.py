from __future__ import annotations

from typing import Any, NamedTuple


class LlmRouting(NamedTuple):
    """Which connection the agent trades with; None while none is chosen."""

    agent: int | None

    def to_dict(self) -> dict[str, Any]:
        return {"agent": self.agent}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LlmRouting:
        return cls(agent=None if data["agent"] is None else int(data["agent"]))
