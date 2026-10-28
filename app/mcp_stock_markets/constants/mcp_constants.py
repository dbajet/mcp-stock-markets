from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class _McpConstants:
    # Each server is mounted under this prefix, at /mcp/<name>/.
    mount_prefix: str = "/mcp"
    # A tool the model sees is "<server>__<tool>": two servers may name a tool alike.
    tool_separator: str = "__"
    # The header carrying the agent run an order belongs to, on the broker's requests.
    run_header: str = "x-agent-run"
    authorization_header: str = "authorization"
    bearer_prefix: str = "Bearer "
    # One MCP request: the slowest tool fetches a page from Google or Alpaca.
    call_timeout_seconds: float = 30.0
    server_version: str = "1.0"

    # --- messages ---------------------------------------------------------------------
    refused: str = "This MCP server needs the app's bearer token."


McpConstants = _McpConstants()
