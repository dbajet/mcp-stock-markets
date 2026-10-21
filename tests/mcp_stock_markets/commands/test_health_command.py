from __future__ import annotations

from decimal import Decimal
from unittest.mock import call, patch

import pytest

from mcp_stock_markets.commands.health_command import HealthCommand
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.structures.health import Health
from mcp_stock_markets.structures.settings import Settings


def helper_settings() -> Settings:
    return Settings(
        environment="production",
        database_url="postgresql://u:p@h/d",
        app_version="2026-10-19.4",
        build_time="20261019-140000Z",
        app_commit="f00dcafe",
        app_base_url="https://docs.example.com",
        data_key="Zm9yLXRlc3RzLW9ubHktZm9yLXRlc3RzLW9ubHktMzI=",
        smtp_host="",
        smtp_port=587,
        smtp_user="",
        smtp_password="",
        email_from="",
        bootstrap_admin_email="",
        starting_budget=Decimal("500.00"),
        max_companies=5,
        alpha_vantage_key="",
        agent_interval_minutes=30,
        mcp_base_url="http://127.0.0.1:8000",
        mcp_token="mcp-token",
    )


def test___init__() -> None:
    settings = helper_settings()
    database = Database("postgresql://u:p@h/d")
    tested = HealthCommand(settings, database)
    result = (tested._settings, tested._database)
    expected = (settings, database)
    assert result == expected


@pytest.mark.parametrize(
    "reachable, expected",
    [
        pytest.param(True, Health(ok=True, version="2026-10-19.4", commit="f00dcafe"), id="up"),
        pytest.param(False, Health(ok=False, version="2026-10-19.4", commit="f00dcafe"), id="down"),
    ],
)
def test_health(reachable: bool, expected: Health) -> None:
    tested = HealthCommand(helper_settings(), Database("postgresql://u:p@h/d"))
    with patch.object(Database, "is_reachable", side_effect=[reachable]) as mock_reachable:
        result = tested.health()
    assert result == expected
    exp_calls = [call()]
    assert mock_reachable.mock_calls == exp_calls
