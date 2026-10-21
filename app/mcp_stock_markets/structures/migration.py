from __future__ import annotations

from typing import Any, NamedTuple


class Migration(NamedTuple):
    """One numbered change to the schema, applied once, recorded in
    `schema_migrations` in the transaction that applies it. Additive, or
    dropping only what the previous release no longer uses."""

    version: int
    description: str
    statements: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "description": self.description,
            "statements": list(self.statements),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Migration:
        return cls(
            version=int(data["version"]),
            description=str(data["description"]),
            statements=tuple(str(statement) for statement in data["statements"]),
        )
