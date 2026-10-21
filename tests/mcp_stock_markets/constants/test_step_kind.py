from __future__ import annotations

from mcp_stock_markets.constants.step_kind import StepKind


def test_enum() -> None:
    tested = StepKind
    expected = {"THINKING": "thinking", "MODEL": "model", "TOOL": "tool"}
    assert {member.name: member.value for member in tested} == expected
