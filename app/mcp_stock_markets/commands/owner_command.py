from __future__ import annotations

import logging

from mcp_stock_markets.constants.constants import Constants
from mcp_stock_markets.libraries.user_store import UserStore
from mcp_stock_markets.structures.user_account import UserAccount


class OwnerCommand:
    """The one person who may sign in: the address in BOOTSTRAP_ADMIN_EMAIL.
    Its account is made at startup when missing, and every other account is
    disabled, so their sessions end and their links stop working. The
    documents are a fixed corpus kept under this account."""

    def __init__(self, users: UserStore) -> None:
        self._users = users

    def owner(self, email: str) -> UserAccount | None:
        """None without an address: nobody can sign in, and no corpus is loaded."""
        if not email:
            logging.getLogger(Constants.logger_name).warning("[USERS] no owner address: nobody can sign in")
            return None
        result = self._users.owned(email, email.split("@")[0])
        disabled = self._users.others_disabled(result.user_id)
        if disabled:
            logging.getLogger(Constants.logger_name).warning("[USERS] %s other accounts disabled", disabled)
        return result
