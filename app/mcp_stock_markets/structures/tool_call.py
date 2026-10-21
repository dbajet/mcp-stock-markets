from __future__ import annotations

from typing import Any, NamedTuple


class ToolCall(NamedTuple):
    """A tool the model asked for, in either provider's terms: the call's id
    (its answer must name it), the qualified tool name, and the arguments —
    None when the model wrote arguments that are not a JSON object."""

    call_id: str
    name: str
    arguments: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {"call_id": self.call_id, "name": self.name, "arguments": self.arguments}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolCall:
        return cls(
            call_id=str(data["call_id"]),
            name=str(data["name"]),
            arguments=None if data["arguments"] is None else dict(data["arguments"]),
        )
