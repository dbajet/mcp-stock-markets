from __future__ import annotations

from mcp_stock_markets.constants.run_trigger import RunTrigger


def test_enum() -> None:
    tested = RunTrigger
    expected = {"SCHEDULE": "schedule", "MANUAL": "manual"}
    assert {member.name: member.value for member in tested} == expected
