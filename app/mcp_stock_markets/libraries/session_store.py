from __future__ import annotations

from mcp_stock_markets.constants.auth_constants import AuthConstants
from mcp_stock_markets.libraries.database import Database


class SessionStore:
    """Server-side sessions: the cookie is only a key to a row, so
    signing out or disabling a person ends every copy of the cookie."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def created(self, user_id: int, token_hash: str) -> None:
        """Expired sessions go as a new one comes, so the table holds the live
        ones and little else, with no job to run."""
        with self._database.transaction():
            self._database.executed("DELETE FROM sessions WHERE expires_at < now()", ())
            self._database.executed(
                """INSERT INTO sessions (user_id, token_hash, expires_at)
                   VALUES (%s, %s, now() + make_interval(days => %s))""",
                (user_id, token_hash, AuthConstants.session_days),
            )

    def user_id_of(self, token_hash: str) -> int | None:
        row = self._database.row(
            """SELECT s.user_id FROM sessions s JOIN users u ON u.id = s.user_id
               WHERE s.token_hash = %s AND s.expires_at > now() AND u.disabled_at IS NULL""",
            (token_hash,),
        )
        return None if row is None else int(row["user_id"])

    def deleted(self, token_hash: str) -> None:
        self._database.executed("DELETE FROM sessions WHERE token_hash = %s", (token_hash,))

    def deleted_for(self, user_id: int) -> None:
        self._database.executed("DELETE FROM sessions WHERE user_id = %s", (user_id,))
