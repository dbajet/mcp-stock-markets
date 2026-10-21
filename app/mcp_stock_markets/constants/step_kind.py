from __future__ import annotations

from enum import Enum


class StepKind(Enum):
    # A summary of the model's thinking, when its provider gives one.
    THINKING = "thinking"
    # What the model said, before calling tools or as its final summary.
    MODEL = "model"
    # A tool the model called, sent to an MCP server, with the server's answer.
    TOOL = "tool"
