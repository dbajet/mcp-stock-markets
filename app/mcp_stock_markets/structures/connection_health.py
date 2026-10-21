from __future__ import annotations

from typing import Any, NamedTuple


class ConnectionHealth(NamedTuple):
    """A connection's light: green when its key is accepted and its models
    exist, red otherwise, with why in words a person can act on."""

    connection_id: int
    is_ok: bool
    detail: str
    elapsed_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "connection_id": self.connection_id,
            "is_ok": self.is_ok,
            "detail": self.detail,
            "elapsed_ms": self.elapsed_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConnectionHealth:
        return cls(
            connection_id=int(data["connection_id"]),
            is_ok=bool(data["is_ok"]),
            detail=str(data["detail"]),
            elapsed_ms=float(data["elapsed_ms"]),
        )
