from __future__ import annotations

from enum import Enum


class RunTrigger(Enum):
    # The scheduler, every AGENT_INTERVAL_MINUTES while the market is open.
    SCHEDULE = "schedule"
    # The owner's Run now.
    MANUAL = "manual"
