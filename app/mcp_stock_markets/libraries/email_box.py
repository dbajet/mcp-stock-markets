from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from mcp_stock_markets.constants.constants import Constants
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.settings import Settings


class EmailBox:
    """Sends plain-text mail through the SES SMTP relay over STARTTLS.

    Without a host there is no relay: on a laptop the message is written to
    the log instead (the settings loader refuses that in production)."""

    _REFUSED = "The mail relay refused the message."
    _UNREACHABLE = "The mail relay could not be reached."

    def __init__(self, settings: Settings) -> None:
        self._host = settings.smtp_host
        self._port = settings.smtp_port
        self._user = settings.smtp_user
        self._password = settings.smtp_password
        self._sender = settings.email_from

    def send(self, recipient: str, subject: str, lines: list[str]) -> None:
        if not self._host:
            # A laptop has no relay: the log is where a developer finds the link.
            logging.getLogger(Constants.logger_name).warning("[EMAIL] no relay: %s", " | ".join(lines))
            return
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self._sender
        message["To"] = recipient
        message.set_content("\n".join(lines))
        try:
            with smtplib.SMTP(self._host, self._port, timeout=Constants.smtp_timeout_seconds) as relay:
                relay.starttls(context=ssl.create_default_context())
                if self._user:
                    relay.login(self._user, self._password)
                relay.send_message(message)
        except (smtplib.SMTPException, ssl.SSLError) as error:
            logging.getLogger(Constants.logger_name).warning("[EMAIL] relay refused: %s", type(error).__name__)
            raise AppException(502, self._REFUSED) from error
        except OSError as error:
            logging.getLogger(Constants.logger_name).warning("[EMAIL] relay unreachable: %s", type(error).__name__)
            raise AppException(502, self._UNREACHABLE) from error
