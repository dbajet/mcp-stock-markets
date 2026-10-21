from __future__ import annotations

from typing import Any

from mcp_stock_markets.libraries.blind_index import BlindIndex
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.libraries.secret_sealer import SecretSealer
from mcp_stock_markets.structures.user_account import UserAccount


class UserStore:
    """The people who may sign in. Emails go in sealed and are found by
    their blind index."""

    _COLUMNS = "id, email_sealed, display_name, disabled_at"

    def __init__(self, database: Database, sealer: SecretSealer, index: BlindIndex) -> None:
        self._database = database
        self._sealer = sealer
        self._index = index

    def owned(self, email: str, display_name: str) -> UserAccount:
        """The address's account, made when missing, enabled either way; a
        second color starting at the same time finds the first one's row."""
        row = self._database.returned(
            f"""INSERT INTO users (email_sealed, email_hash, display_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (email_hash) DO UPDATE SET disabled_at = NULL
                RETURNING {self._COLUMNS}""",
            (self._sealer.sealed(email.strip().lower()), self._index.digest(email), display_name),
        )
        return self._account(row)

    def others_disabled(self, user_id: int) -> int:
        """Every other account disabled; how many were still enabled."""
        return self._database.executed(
            "UPDATE users SET disabled_at = now() WHERE id <> %s AND disabled_at IS NULL", (user_id,)
        )

    def by_id(self, user_id: int) -> UserAccount | None:
        row = self._database.row(f"SELECT {self._COLUMNS} FROM users WHERE id = %s", (user_id,))
        return None if row is None else self._account(row)

    def by_email(self, email: str) -> UserAccount | None:
        row = self._database.row(
            f"SELECT {self._COLUMNS} FROM users WHERE email_hash = %s", (self._index.digest(email),)
        )
        return None if row is None else self._account(row)

    def _account(self, row: dict[str, Any]) -> UserAccount:
        return UserAccount(
            user_id=int(row["id"]),
            email=self._sealer.opened(bytes(row["email_sealed"])),
            display_name=str(row["display_name"]),
            is_disabled=row["disabled_at"] is not None,
        )
