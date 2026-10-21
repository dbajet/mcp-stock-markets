from __future__ import annotations

from enum import Enum


class McpServerName(Enum):
    """The MCP servers this app mounts, each at /mcp/<value>/."""

    SP500 = "sp500"
    QUOTES = "quotes"
    BROKER = "broker"
