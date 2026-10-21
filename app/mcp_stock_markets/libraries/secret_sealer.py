from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from mcp_stock_markets.constants.constants import Constants
from mcp_stock_markets.structures.app_exception import AppException


class SecretSealer:
    """Seals what a person entrusts to the app before it is stored, and opens
    it when they ask for it: their documents, the
    documents' names, and their email.

    Sealed on the server, not in the browser: the server must read a document
    to index it for search later, which an end-to-end scheme would forbid. A
    value in a table is a value in every backup of that table; sealed with the
    data key from the environment, a dump is worthless without the `.env`,
    which a backup never contains. Fernet is authenticated, so a tampered row
    is refused rather than decoded into something else."""

    _UNREADABLE = "A stored value could not be opened: the data key has changed since it was stored."

    def __init__(self, key: str) -> None:
        try:
            self._fernet = Fernet(key.encode(Constants.text_encoding))
        except ValueError as error:
            raise AppException(500, f"{Constants.env_data_key} is not a Fernet key") from error

    def sealed(self, value: str) -> bytes:
        return self.sealed_bytes(value.encode(Constants.text_encoding))

    def opened(self, sealed: bytes) -> str:
        return self.opened_bytes(sealed).decode(Constants.text_encoding)

    def sealed_bytes(self, content: bytes) -> bytes:
        return self._fernet.encrypt(content)

    def opened_bytes(self, sealed: bytes) -> bytes:
        try:
            return self._fernet.decrypt(sealed)
        except InvalidToken as error:
            raise AppException(500, self._UNREADABLE) from error
