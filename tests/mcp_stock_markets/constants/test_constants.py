from __future__ import annotations

import dataclasses

from mcp_stock_markets.constants.constants import Constants
from tests.conftest import is_dataclass


def test_class() -> None:
    tested = Constants
    fields = {
        "app_name": "str",
        "logger_name": "str",
        "text_encoding": "str",
        "env_environment": "str",
        "env_database_url": "str",
        "env_app_version": "str",
        "env_build_time": "str",
        "env_app_commit": "str",
        "env_app_base_url": "str",
        "env_data_key": "str",
        "env_smtp_host": "str",
        "env_smtp_port": "str",
        "env_smtp_user": "str",
        "env_smtp_password": "str",
        "env_email_from": "str",
        "env_bootstrap_admin_email": "str",
        "env_starting_budget": "str",
        "env_max_companies": "str",
        "env_alpha_vantage_key": "str",
        "env_agent_interval_minutes": "str",
        "env_mcp_base_url": "str",
        "env_mcp_token": "str",
        "default_app_base_url": "str",
        "default_mcp_base_url": "str",
        "default_starting_budget": "str",
        "default_max_companies": "int",
        "default_agent_interval_minutes": "int",
        "max_agent_interval_minutes": "int",
        "max_starting_budget": "int",
        "max_max_companies": "int",
        "mcp_token_bytes": "int",
        "smtp_default_port": "int",
        "environment_production": "str",
        "environment_development": "str",
        "placeholder_markers": "tuple[str, ...]",
        "version_unstamped": "str",
        "database_connect_timeout_seconds": "int",
        "database_statement_timeout_ms": "int",
        "migration_lock_timeout": "str",
        "migration_lock_key": "int",
        "routine_lock_key": "int",
        "static_directory": "str",
        "static_mount": "str",
        "page_file": "str",
        "page_paths": "tuple[str, ...]",
        "service_worker_path": "str",
        "service_worker_file": "str",
        "marker_build": "str",
        "marker_version": "str",
        "header_cache_control": "str",
        "page_cache_control": "str",
        "content_security_policy": "str",
        "frame_options": "str",
        "permissions_policy": "str",
        "content_type_options": "str",
        "referrer_policy": "str",
        "health_path": "str",
        "job_poll_seconds": "float",
        "job_shutdown_seconds": "float",
        "alert_interval_seconds": "int",
        "alert_subject": "str",
        "smtp_timeout_seconds": "float",
    }
    assert is_dataclass(tested, fields)


def test_values() -> None:
    tested = Constants
    result = dataclasses.asdict(tested)
    expected = {
        "app_name": "mcp_stock_markets",
        "logger_name": "mcp_stock_markets",
        "text_encoding": "utf-8",
        "env_environment": "APP_ENV",
        "env_database_url": "DATABASE_URL",
        "env_app_version": "APP_VERSION",
        "env_build_time": "BUILD_TIME",
        "env_app_commit": "APP_COMMIT",
        "env_app_base_url": "APP_BASE_URL",
        "env_data_key": "DATA_ENCRYPTION_KEY",
        "env_smtp_host": "SMTP_HOST",
        "env_smtp_port": "SMTP_PORT",
        "env_smtp_user": "SMTP_USER",
        "env_smtp_password": "SMTP_PASSWORD",
        "env_email_from": "EMAIL_FROM",
        "env_bootstrap_admin_email": "BOOTSTRAP_ADMIN_EMAIL",
        "env_starting_budget": "STARTING_BUDGET",
        "env_max_companies": "MAX_COMPANIES",
        "env_alpha_vantage_key": "ALPHA_VANTAGE_API_KEY",
        "env_agent_interval_minutes": "AGENT_INTERVAL_MINUTES",
        "env_mcp_base_url": "MCP_BASE_URL",
        "env_mcp_token": "MCP_TOKEN",
        "default_app_base_url": "http://localhost:8150",
        "default_mcp_base_url": "http://127.0.0.1:8150",
        "default_starting_budget": "500",
        "default_max_companies": 5,
        "default_agent_interval_minutes": 30,
        "max_agent_interval_minutes": 1440,
        "max_starting_budget": 1_000_000,
        "max_max_companies": 25,
        "mcp_token_bytes": 32,
        "smtp_default_port": 587,
        "environment_production": "production",
        "environment_development": "dev",
        "placeholder_markers": ("change_me", "change-me", "placeholder"),
        "version_unstamped": "dev",
        "database_connect_timeout_seconds": 5,
        "database_statement_timeout_ms": 15000,
        "migration_lock_timeout": "5s",
        "migration_lock_key": 7_310_401,
        "routine_lock_key": 7_310_404,
        "static_directory": "static",
        "static_mount": "/static",
        "page_file": "index.html",
        "page_paths": ("/", "/auth/link"),
        "service_worker_path": "/sw.js",
        "service_worker_file": "sw.js",
        "marker_build": "__BUILD__",
        "marker_version": "__VERSION__",
        "header_cache_control": "Cache-Control",
        "page_cache_control": "no-cache",
        "content_security_policy": (
            "default-src 'self'; "
            "script-src 'self'; "
            "connect-src 'self'; "
            "img-src 'self' data:; "
            "style-src 'self'; "
            "font-src 'self'; "
            "manifest-src 'self'; "
            "worker-src 'self'; "
            "object-src 'none'; "
            "base-uri 'none'; "
            "form-action 'self'; "
            "frame-ancestors 'none'"
        ),
        "frame_options": "DENY",
        "permissions_policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        "content_type_options": "nosniff",
        "referrer_policy": "strict-origin-when-cross-origin",
        "health_path": "/healthz",
        "job_poll_seconds": 1.0,
        "job_shutdown_seconds": 25.0,
        "alert_interval_seconds": 3600,
        "alert_subject": "[MCP Stock Markets] a background job failed",
        "smtp_timeout_seconds": 15.0,
    }
    assert result == expected
