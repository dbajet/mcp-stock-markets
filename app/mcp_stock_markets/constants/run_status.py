from __future__ import annotations

from enum import Enum


class RunStatus(Enum):
    RUNNING = "running"
    # The model ended with a summary.
    COMPLETED = "completed"
    # The model used every round without ending.
    EXHAUSTED = "exhausted"
    # The model or an MCP server failed; the run says why.
    FAILED = "failed"
