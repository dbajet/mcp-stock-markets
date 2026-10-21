from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from datetime import datetime, tzinfo
from types import ModuleType
from unittest.mock import patch


class FrozenDatetime(datetime):
    """A controlled clock for `datetime.now()`, installed as the modules' own
    `datetime` name: the app reads the hour of the US market from it, so an
    end-to-end test can trade on a Wednesday morning whenever it runs.
    Everything but `now` is the real `datetime`."""

    moment: datetime

    @classmethod
    def now(cls, tz: tzinfo | None = None) -> FrozenDatetime:  # type: ignore[override]
        frozen = cls.moment if tz is None else cls.moment.astimezone(tz)
        return cls.fromisoformat(frozen.isoformat())

    @classmethod
    @contextmanager
    def installed(cls, moment: datetime, modules: list[ModuleType]) -> Iterator[type[FrozenDatetime]]:
        """In place of each module's `datetime`, for the block, frozen at `moment`."""
        frozen = type("Frozen", (cls,), {"moment": moment})
        with ExitStack() as stack:
            for module in modules:
                stack.enter_context(patch.object(module, "datetime", new=frozen))
            yield frozen
