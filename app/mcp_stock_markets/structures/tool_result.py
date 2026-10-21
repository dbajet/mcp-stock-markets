from __future__ import annotations

from typing import Any, NamedTuple


class ToolResult(NamedTuple):
    """An MCP server's answer to one call, as the model will read it: text,
    and whether the tool failed (`isError`), which the model can act on."""

    call_id: str
    content: str
    is_error: bool

    def to_dict(self) -> dict[str, Any]:
        return {"call_id": self.call_id, "content": self.content, "is_error": self.is_error}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolResult:
        return cls(
            call_id=str(data["call_id"]),
            content=str(data["content"]),
            is_error=bool(data["is_error"]),
        )
