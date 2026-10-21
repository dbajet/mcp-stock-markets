from __future__ import annotations

from typing import Any, NamedTuple


class UserAccount(NamedTuple):
    """A person who may sign in, with their email already opened. Only the
    owner is ever enabled; an account from before the app had one user stays,
    disabled."""

    user_id: int
    email: str
    display_name: str
    is_disabled: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "email": self.email,
            "display_name": self.display_name,
            "is_disabled": self.is_disabled,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserAccount:
        return cls(
            user_id=int(data["user_id"]),
            email=str(data["email"]),
            display_name=str(data["display_name"]),
            is_disabled=bool(data["is_disabled"]),
        )
