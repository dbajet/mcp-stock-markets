from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from types import ModuleType
from typing import Any
from unittest.mock import patch


class FakeClock:
    """A controlled clock, installed as a module's own `time` name, so code
    that waits is watched without waiting: `monotonic()` reads the clock,
    `sleep(seconds)` moves it forward at once. It answers only the two calls
    of the `time` module the spaced code makes, and records them in order in
    `calls`."""

    def __init__(self, now: float) -> None:
        self.now = now
        self.calls: list[tuple[Any, ...]] = []

    @contextmanager
    def installed(self, module: ModuleType) -> Iterator[FakeClock]:
        """In place of the module's `time`, for the block."""
        with patch.object(module, "time", new=self):
            yield self

    def monotonic(self) -> float:
        self.calls.append(("monotonic",))
        return self.now

    def sleep(self, secs: float) -> None:
        self.calls.append(("sleep", secs))
        self.now += secs

    def advanced(self, seconds: float) -> None:
        """Time passing outside the code under test, between two of its calls."""
        self.now += seconds
