from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from typing import Any

from mcp_stock_markets.constants.constants import Constants
from mcp_stock_markets.libraries.alerter import Alerter


class JobQueue:
    """Work nobody waits on — sending an email — done on one thread of its
    own, so a request answers at once and the same for every address.

    The queue is in memory: a crash loses the emails still waiting, and the
    person asks again. Nothing here has a database effect to repeat, so the
    two colors of a deploy never share a job. On shutdown the loop drains
    what is queued before the thread is joined, so a sign-in email accepted
    by the old color still leaves."""

    def __init__(self, name: str, alerter: Alerter) -> None:
        self._name = name
        self._alerter = alerter
        self._jobs: queue.Queue[tuple[Callable[..., None], tuple[Any, ...]]] = queue.Queue()
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

    def queued(self, job: Callable[..., None], args: tuple[Any, ...]) -> None:
        self._jobs.put((job, args))

    def ran(self) -> None:
        while not (self._stopping.is_set() and self._jobs.empty()):
            try:
                job, args = self._jobs.get(timeout=Constants.job_poll_seconds)
            except queue.Empty:
                continue
            self.performed(job, args)

    def performed(self, job: Callable[..., None], args: tuple[Any, ...]) -> None:
        try:
            job(*args)
        except Exception as error:  # never let the loop die
            logging.getLogger(Constants.logger_name).exception("[JOBS] a %s job failed", self._name)
            self._alerter.alerted(self._name, type(error).__name__)
