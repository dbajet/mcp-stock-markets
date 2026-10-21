from __future__ import annotations

from mcp_stock_markets.constants.link_purpose import LinkPurpose
from mcp_stock_markets.libraries.database import Database


class MagicLinkStore:
    """Single-use sign-in links, kept as hashes."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def created(self, user_id: int, token_hash: str, purpose: LinkPurpose, minutes: int) -> None:
        """Expired links go as a new one comes: spent or not, they open nothing."""
        with self._database.transaction():
            self._database.executed("DELETE FROM magic_links WHERE expires_at < now()", ())
            self._database.executed(
                """INSERT INTO magic_links (user_id, token_hash, purpose, expires_at)
                   VALUES (%s, %s, %s, now() + make_interval(mins => %s))""",
                (user_id, token_hash, purpose.value, minutes),
            )

    def redeemed(self, token_hash: str) -> int | None:
        """The user the link was for, once: one atomic UPDATE, so two
        simultaneous uses cannot both win."""
        row = self._database.row(
            """UPDATE magic_links SET used_at = now()
               WHERE token_hash = %s AND used_at IS NULL AND expires_at > now()
               RETURNING user_id""",
            (token_hash,),
        )
        return None if row is None else int(row["user_id"])
