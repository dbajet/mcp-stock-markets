from __future__ import annotations

from mcp_stock_markets.constants.run_status import RunStatus


def test_enum() -> None:
    tested = RunStatus
    expected = {"RUNNING": "running", "COMPLETED": "completed", "EXHAUSTED": "exhausted", "FAILED": "failed"}
    assert {member.name: member.value for member in tested} == expected
