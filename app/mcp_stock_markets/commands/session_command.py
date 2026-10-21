from __future__ import annotations

from mcp_stock_markets.libraries.session_store import SessionStore
from mcp_stock_markets.libraries.token_maker import TokenMaker
from mcp_stock_markets.libraries.user_store import UserStore
from mcp_stock_markets.structures.user_account import UserAccount


class SessionCommand:
    """Sessions begun by a sign-in link, and the person behind a cookie."""

    def __init__(self, users: UserStore, sessions: SessionStore) -> None:
        self._users = users
        self._sessions = sessions

    def started(self, user_id: int) -> str:
        """The token for the cookie; the table keeps only its hash."""
        result = TokenMaker.token()
        self._sessions.created(user_id, TokenMaker.digest(result))
        return result

    def current(self, token: str) -> UserAccount | None:
        if not token:
            return None
        user_id = self._sessions.user_id_of(TokenMaker.digest(token))
        return None if user_id is None else self._users.by_id(user_id)

    def ended(self, token: str) -> None:
        if token:
            self._sessions.deleted(TokenMaker.digest(token))
