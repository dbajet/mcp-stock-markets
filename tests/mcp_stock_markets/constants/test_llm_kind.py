from __future__ import annotations

from mcp_stock_markets.constants.llm_kind import LlmKind


def test_enum() -> None:
    tested = LlmKind
    expected = {"CLAUDE": "claude", "OPENAI": "openai"}
    assert {member.name: member.value for member in tested} == expected
