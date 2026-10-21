from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from mcp_stock_markets.libraries.page_renderer import PageRenderer
from mcp_stock_markets.structures.settings import Settings

PAGE = '<link href="/static/ui.css?v=__BUILD__"><span>v__VERSION__</span>'
WORKER = 'const CACHE = "mcp_stock_markets-__BUILD__";\nself.addEventListener("install", () => self.skipWaiting());\n'


def helper_settings() -> Settings:
    return Settings(
        environment="dev",
        database_url="postgresql://u:p@h/d",
        app_version="2026-10-19.3",
        build_time="20261019-130000Z",
        app_commit="abc",
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


def helper_directory(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text(PAGE, encoding="utf-8")
    (tmp_path / "sw.js").write_text(WORKER, encoding="utf-8")
    return tmp_path


def test___init__(tmp_path: Path) -> None:
    settings = helper_settings()
    tested = PageRenderer(tmp_path, settings)
    result = (tested._directory, tested._settings)
    expected = (tmp_path, settings)
    assert result == expected


def test_page(tmp_path: Path) -> None:
    tested = PageRenderer(helper_directory(tmp_path), helper_settings())
    response = tested.page()
    result = response.body.decode("utf-8")
    expected = '<link href="/static/ui.css?v=20261019-130000Z"><span>v2026-10-19.3</span>'
    assert result == expected
    exp_headers = ("text/html; charset=utf-8", "no-cache")
    assert (response.headers["Content-Type"], response.headers["Cache-Control"]) == exp_headers


def test_service_worker(tmp_path: Path) -> None:
    tested = PageRenderer(helper_directory(tmp_path), helper_settings())
    response = tested.service_worker()
    result = response.body.decode("utf-8")
    expected = 'const CACHE = "mcp_stock_markets-20261019-130000Z";\nself.addEventListener("install", () => self.skipWaiting());\n'
    assert result == expected
    exp_headers = ("text/javascript; charset=utf-8", "no-cache")
    assert (response.headers["Content-Type"], response.headers["Cache-Control"]) == exp_headers
