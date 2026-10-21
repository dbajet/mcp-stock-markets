from __future__ import annotations

import smtplib
import socket
import ssl
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from email.message import EmailMessage
from typing import Any
from unittest.mock import patch


class FakeSMTP:
    """A hand-written stand-in for `smtplib.SMTP`: no socket,
    no wait, the same calls in and the same kind of failures out.

    It reproduces the vendor's shape as `EmailBox` meets it: the class is
    called with `(host, port, timeout=...)` to open a session, the session is a
    context manager whose exit sends QUIT (even when the body raised),
    `starttls(*, context=None)`, `login(user, password, *, initial_response_ok=True)`
    and `send_message(msg, from_addr=None, to_addrs=None, ...)`.

    It fails the way smtplib fails, on demand: an unreachable relay raises an
    `OSError` (ConnectionRefusedError) from the constructor, before any session
    exists; a refusing relay raises smtplib's own exception at the step named
    by `failing_step`. Every call is recorded in order in `calls`."""

    _TARGET = "mcp_stock_markets.libraries.email_box.smtplib.SMTP"
    # What SES answers at each step, as smtplib raises it: a fresh exception per failure.
    _FAILURES: dict[str, Callable[[], smtplib.SMTPException]] = {
        "connect": lambda: smtplib.SMTPConnectError(421, b"Service not available"),
        "starttls": lambda: smtplib.SMTPNotSupportedError("STARTTLS extension not supported by server."),
        "login": lambda: smtplib.SMTPAuthenticationError(535, b"Authentication Credentials Invalid"),
        "send_message": lambda: smtplib.SMTPDataError(554, b"Message rejected: Email address is not verified."),
    }

    def __init__(self, failing_step: str = "", unreachable: bool = False) -> None:
        if failing_step and failing_step not in self._FAILURES:
            raise ValueError(f"unknown step: {failing_step}")
        self.failing_step = failing_step
        self.unreachable = unreachable
        self.calls: list[tuple[Any, ...]] = []

    @contextmanager
    def installed(self) -> Iterator[FakeSMTP]:
        """In place of the class at the name `EmailBox` resolves at call time."""
        with patch(self._TARGET, new=self):
            yield self

    def __call__(
        self,
        host: str = "",
        port: int = 0,
        local_hostname: str | None = None,
        timeout: float = socket._GLOBAL_DEFAULT_TIMEOUT,  # type: ignore[attr-defined]
        source_address: tuple[str, int] | None = None,
    ) -> FakeSMTP:
        self.calls.append(("connect", host, port, timeout))
        if self.unreachable:
            raise ConnectionRefusedError(111, "Connection refused")
        self._failed_at("connect")
        return self

    def __enter__(self) -> FakeSMTP:
        return self

    def __exit__(self, *args: object) -> None:
        self.quit()

    def starttls(self, *, context: ssl.SSLContext | None = None) -> tuple[int, bytes]:
        if context is None:
            self.calls.append(("starttls", None, None))
        else:
            self.calls.append(("starttls", context.verify_mode.name, context.check_hostname))
        self._failed_at("starttls")
        return (220, b"Ready to start TLS")

    def login(self, user: str, password: str, *, initial_response_ok: bool = True) -> tuple[int, bytes]:
        self.calls.append(("login", user, password))
        self._failed_at("login")
        return (235, b"Authentication successful")

    def send_message(
        self,
        msg: EmailMessage,
        from_addr: str | None = None,
        to_addrs: str | list[str] | None = None,
        mail_options: tuple[str, ...] = (),
        rcpt_options: tuple[str, ...] = (),
    ) -> dict[str, tuple[int, bytes]]:
        self.calls.append(("send_message", msg["From"], msg["To"], msg["Subject"], msg.get_content()))
        self._failed_at("send_message")
        return {}

    def quit(self) -> tuple[int, bytes]:
        self.calls.append(("quit",))
        return (221, b"Bye")

    def _failed_at(self, step: str) -> None:
        if self.failing_step == step:
            raise self._FAILURES[step]()
