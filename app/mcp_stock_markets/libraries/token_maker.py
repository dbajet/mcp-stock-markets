from __future__ import annotations

import hashlib
import secrets

from mcp_stock_markets.constants.auth_constants import AuthConstants
from mcp_stock_markets.constants.constants import Constants


class TokenMaker:
    """The secrets handed to a browser or an inbox (sign-in links, sessions)
    and the digests the database keeps instead: a dump of the tables opens
    no door. A plain SHA-256 suffices, unlike for emails: a token has 256
    bits of entropy, so there is nothing to guess."""

    @classmethod
    def token(cls) -> str:
        return secrets.token_urlsafe(AuthConstants.token_bytes)

    @classmethod
    def digest(cls, token: str) -> str:
        return hashlib.sha256(token.encode(Constants.text_encoding)).hexdigest()
