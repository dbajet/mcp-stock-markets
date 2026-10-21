from __future__ import annotations

import hashlib
import hmac

from mcp_stock_markets.constants.auth_constants import AuthConstants
from mcp_stock_markets.constants.constants import Constants


class BlindIndex:
    """The lookup key of a sealed email.

    Fernet is randomised, so the same address seals differently every time
    and cannot be searched. Its keyed hash can: equal inputs give equal
    digests, and without the data key a digest cannot be tested against a
    guessed address, which a plain hash could be. The key is derived from the
    data key under a label of its own, so the index key and the sealing key
    are never the same bytes, and a restore needs only the one key kept off
    the server."""

    def __init__(self, data_key: str) -> None:
        self._key = hmac.new(
            data_key.encode(Constants.text_encoding),
            AuthConstants.blind_index_label.encode(Constants.text_encoding),
            hashlib.sha256,
        ).digest()

    def digest(self, email: str) -> str:
        """Of the address as a person means it: a capital or a trailing space is still the same address."""
        return hmac.new(self._key, email.strip().lower().encode(Constants.text_encoding), hashlib.sha256).hexdigest()
