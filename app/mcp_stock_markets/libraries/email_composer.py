from __future__ import annotations

from mcp_stock_markets.constants.auth_constants import AuthConstants


class EmailComposer:
    """The words of every email. Plain text, built as lines: a
    sign-in link is a line to click."""

    def sign_in_subject(self) -> str:
        return "Your MCP Stock Markets sign-in link"

    def sign_in_lines(self, name: str, link: str) -> list[str]:
        return [
            f"Hello {name},",
            "",
            "To sign in to MCP Stock Markets, open this link:",
            link,
            "",
            f"It works once, for {AuthConstants.magic_link_minutes} minutes.",
            "If you did not ask for it, ignore this message.",
        ]
