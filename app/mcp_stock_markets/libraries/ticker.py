from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from mcp_stock_markets.constants.constants import Constants
from mcp_stock_markets.libraries.alerter import Alerter


class Ticker:
    """A job run every interval on a thread of its own: the scheduler's.
    It waits on an Event rather than sleeping, so a stopping color ends it
    at once; a tick in progress finishes first (the join)."""

    def __init__(self, name: str, interval_seconds: float, tick: Callable[[], None], alerter: Alerter) -> None:
        self._name = name
        self._interval = interval_seconds
        self._tick = tick
        self._alerter = alerter
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None

    def started(self) -> None:
        self._stopping.clear()
        self._thread = threading.Thread(target=self.ran, name=self._name, daemon=True)
        self._thread.start()

    def stopped(self) -> None:
        self._stopping.set()
        if self._thread is not None:
            self._thread.join(Constants.job_shutdown_seconds)
            self._thread = None

    def ran(self) -> None:
        while not self._stopping.is_set():
            self.ticked()
            self._stopping.wait(self._interval)

    def ticked(self) -> None:
        try:
            self._tick()
        except Exception as error:  # never let the loop die
            logging.getLogger(Constants.logger_name).exception("[TICKER] the %s tick failed", self._name)
            self._alerter.alerted(self._name, type(error).__name__)
