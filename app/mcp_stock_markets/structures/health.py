from __future__ import annotations

from typing import Any, NamedTuple


class Health(NamedTuple):
    """What `/healthz` answers: `ok` only once the database answered, and the
    commit, which the deploy compares so an old container cannot pass for
    the new one."""

    ok: bool
    version: str
    commit: str

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "version": self.version, "commit": self.commit}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Health:
        return cls(
            ok=bool(data["ok"]),
            version=str(data["version"]),
            commit=str(data["commit"]),
        )
