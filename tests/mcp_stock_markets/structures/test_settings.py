from __future__ import annotations

from decimal import Decimal

import pytest

from mcp_stock_markets.structures.settings import Settings
from tests.conftest import is_namedtuple


def helper_instance(environment: str) -> Settings:
    return Settings(
        environment=environment,
        database_url="postgresql://u:p@h:5432/d",
        app_version="2026-10-19.1",
        build_time="20261019-120000Z",
        app_commit="abc123",
        app_base_url="https://docs.example.com",
        data_key="the-data-key",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="smtp-user",
        smtp_password="smtp-password",
        email_from="MCP Stock Markets <noreply@example.com>",
        bootstrap_admin_email="ada@example.com",
        starting_budget=Decimal("500.00"),
        max_companies=5,
        alpha_vantage_key="",
        agent_interval_minutes=30,
        mcp_base_url="http://127.0.0.1:8000",
        mcp_token="mcp-token",
    )


def helper_with_base_url(app_base_url: str) -> Settings:
    return helper_instance("dev")._replace(app_base_url=app_base_url)


def test_class() -> None:
    tested = Settings
    fields = {
        "environment": "str",
        "database_url": "str",
        "app_version": "str",
        "build_time": "str",
        "app_commit": "str",
        "app_base_url": "str",
        "data_key": "str",
        "smtp_host": "str",
        "smtp_port": "int",
        "smtp_user": "str",
        "smtp_password": "str",
        "email_from": "str",
        "bootstrap_admin_email": "str",
        "starting_budget": "Decimal",
        "max_companies": "int",
        "alpha_vantage_key": "str",
        "agent_interval_minutes": "int",
        "mcp_base_url": "str",
        "mcp_token": "str",
    }
    assert is_namedtuple(tested, fields)


@pytest.mark.parametrize(
    "environment, expected",
    [
        pytest.param("production", True, id="production"),
        pytest.param("dev", False, id="dev"),
    ],
)
def test_is_production(environment: str, expected: bool) -> None:
    tested = helper_instance(environment)
    result = tested.is_production()
    assert result is expected


@pytest.mark.parametrize(
    "app_base_url, expected",
    [
        pytest.param("https://docs.example.com", "https://docs.example.com", id="plain"),
        pytest.param("http://localhost:8150", "http://localhost:8150", id="with-port"),
        pytest.param("https://docs.example.com/some/path?q=1", "https://docs.example.com", id="path-dropped"),
    ],
)
def test_origin(app_base_url: str, expected: str) -> None:
    tested = helper_with_base_url(app_base_url)
    result = tested.origin()
    assert result == expected


def test_to_dict() -> None:
    tested = helper_instance("dev")
    result = tested.to_dict()
    expected = {
        "environment": "dev",
        "database_url": "postgresql://u:p@h:5432/d",
        "app_version": "2026-10-19.1",
        "build_time": "20261019-120000Z",
        "app_commit": "abc123",
        "app_base_url": "https://docs.example.com",
        "data_key": "the-data-key",
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_user": "smtp-user",
        "smtp_password": "smtp-password",
        "email_from": "MCP Stock Markets <noreply@example.com>",
        "bootstrap_admin_email": "ada@example.com",
        "starting_budget": "500.00",
        "max_companies": 5,
        "alpha_vantage_key": "",
        "agent_interval_minutes": 30,
        "mcp_base_url": "http://127.0.0.1:8000",
        "mcp_token": "mcp-token",
    }
    assert result == expected


def test_from_dict() -> None:
    tested = Settings
    result = tested.from_dict(
        {
            "environment": "production",
            "database_url": "postgresql://u:p@h:5432/d",
            "app_version": "2026-10-19.1",
            "build_time": "20261019-120000Z",
            "app_commit": "abc123",
            "app_base_url": "https://docs.example.com",
            "data_key": "the-data-key",
            "smtp_host": "smtp.example.com",
            "smtp_port": "587",
            "smtp_user": "smtp-user",
            "smtp_password": "smtp-password",
            "email_from": "MCP Stock Markets <noreply@example.com>",
            "bootstrap_admin_email": "ada@example.com",
            "starting_budget": "500.00",
            "max_companies": "5",
            "alpha_vantage_key": "",
            "agent_interval_minutes": "30",
            "mcp_base_url": "http://127.0.0.1:8000",
            "mcp_token": "mcp-token",
        }
    )
    expected = helper_instance("production")
    assert result == expected
    exp_budget = Decimal("500.00")
    assert (type(result.starting_budget), result.starting_budget) == (Decimal, exp_budget)


def test_from_dict__a_missing_field_raises() -> None:
    tested = Settings
    with pytest.raises(KeyError):
        tested.from_dict({"environment": "dev"})
