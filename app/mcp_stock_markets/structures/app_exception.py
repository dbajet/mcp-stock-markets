from __future__ import annotations


class AppException(RuntimeError):
    """The one exception of the application: a status code and a message a
    person may read, turned into JSON by the single handler in `main.py`."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
