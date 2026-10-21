from __future__ import annotations

from typing import Any, NamedTuple

from mcp_stock_markets.constants.mcp_constants import McpConstants
from mcp_stock_markets.constants.mcp_server_name import McpServerName


class ToolSpec(NamedTuple):
    """A tool an MCP server lists, as `tools/list` describes it: its name,
    what it does, and the JSON Schema of its arguments. The model sees it
    under `qualified_name`, which says which server answers it."""

    server: McpServerName
    name: str
    description: str
    input_schema: dict[str, Any]

    def qualified_name(self) -> str:
        return f"{self.server.value}{McpConstants.tool_separator}{self.name}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "server": self.server.value,
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolSpec:
        return cls(
            server=McpServerName(data["server"]),
            name=str(data["name"]),
            description=str(data["description"]),
            input_schema=dict(data["input_schema"]),
        )
