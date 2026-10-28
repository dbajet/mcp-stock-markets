from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from unittest.mock import call, patch

import pytest
from starlette.responses import HTMLResponse, Response

from mcp_stock_markets.commands.health_command import HealthCommand
from mcp_stock_markets.handlers.api_router import ApiRouter
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.libraries.page_renderer import PageRenderer
from mcp_stock_markets.structures.health import Health
from mcp_stock_markets.structures.settings import Settings


def helper_settings() -> Settings:
    return Settings(
        environment="dev",
        database_url="postgresql://u:p@h/d",
        app_version="v",
        build_time="b",
        app_commit="c",
        app_base_url="http://testserver",
        data_key="Zm9yLXRlc3RzLW9ubHktZm9yLXRlc3RzLW9ubHktMzI=",
        smtp_host="",
        smtp_port=587,
        smtp_user="",
        smtp_password="",
        email_from="",
        bootstrap_admin_email="",
        starting_budget=Decimal("500.00"),
        max_companies=5,
        alpaca_key_id="",
        alpaca_secret_key="",
        agent_interval_minutes=30,
        mcp_base_url="http://127.0.0.1:8000",
        mcp_token="mcp-token",
    )


def helper_instance() -> ApiRouter:
    settings = helper_settings()
    return ApiRouter(HealthCommand(settings, Database(settings.database_url)), PageRenderer(Path("/nowhere"), settings))


def test___init__() -> None:
    settings = helper_settings()
    health_command = HealthCommand(settings, Database(settings.database_url))
    page_renderer = PageRenderer(Path("/nowhere"), settings)
    tested = ApiRouter(health_command, page_renderer)
    result = (tested._health_command, tested._page_renderer)
    expected = (health_command, page_renderer)
    assert result == expected


def test_router() -> None:
    tested = helper_instance()
    result = [(route.path, tuple(sorted(route.methods)), route.name) for route in tested.router().routes]  # type: ignore[attr-defined]
    expected = [
        ("/healthz", ("GET", "HEAD"), "healthz"),
        ("/sw.js", ("GET",), "service_worker"),
        ("/", ("GET", "HEAD"), "page"),
        ("/auth/link", ("GET", "HEAD"), "page"),
    ]
    assert result == expected


@pytest.mark.parametrize(
    "health, expected",
    [
        pytest.param(
            Health(ok=True, version="v", commit="c"), (200, b'{"ok":true,"version":"v","commit":"c"}'), id="ok"
        ),
        pytest.param(
            Health(ok=False, version="v", commit="c"),
            (503, b'{"ok":false,"version":"v","commit":"c"}'),
            id="database_down",
        ),
    ],
)
def test_healthz(health: Health, expected: tuple[int, bytes]) -> None:
    tested = helper_instance()
    with patch.object(HealthCommand, "health", side_effect=[health]) as mock_health:
        response = tested.healthz()
    result = (response.status_code, response.body)
    assert result == expected
    exp_calls = [call()]
    assert mock_health.mock_calls == exp_calls


def test_page() -> None:
    tested = helper_instance()
    page = HTMLResponse("<p>shell</p>")
    with patch.object(PageRenderer, "page", side_effect=[page]) as mock_page:
        result = tested.page()
    assert result is page
    exp_calls = [call()]
    assert mock_page.mock_calls == exp_calls


def test_service_worker() -> None:
    tested = helper_instance()
    worker = Response("self;")
    with patch.object(PageRenderer, "service_worker", side_effect=[worker]) as mock_worker:
        result = tested.service_worker()
    assert result is worker
    exp_calls = [call()]
    assert mock_worker.mock_calls == exp_calls
