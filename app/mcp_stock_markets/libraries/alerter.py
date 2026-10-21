from __future__ import annotations

import logging
import threading
import time

from mcp_stock_markets.constants.constants import Constants
from mcp_stock_markets.libraries.email_box import EmailBox
from mcp_stock_markets.structures.app_exception import AppException


class Alerter:
    """Tells a person that a background job failed: a log nobody reads
    is a silent failure. At most one email per job per interval, so a job
    failing every second does not become a flood."""

    def __init__(self, email_box: EmailBox, recipient: str) -> None:
        self._email_box = email_box
        self._recipient = recipient
        self._last_sent: dict[str, float] = {}
        self._lock = threading.Lock()

    def alerted(self, job: str, problem: str) -> None:
        if not self._recipient or not self._is_due(job):
            return
        try:
            self._email_box.send(
                self._recipient,
                Constants.alert_subject,
                [
                    f"The background job '{job}' failed: {problem}.",
                    "The details are in the logs: docker logs mcp_stock_markets-app-<color>.",
                ],
            )
        except AppException:
            logging.getLogger(Constants.logger_name).warning("[ALERT] could not send the alert for %s", job)

    def _is_due(self, job: str) -> bool:
        now = time.monotonic()
        with self._lock:
            last = self._last_sent.get(job)
            if last is not None and now - last < Constants.alert_interval_seconds:
                return False
            # The alerter's own memory of what it sent: the one mutable thing here.
            self._last_sent[job] = now
            return True
