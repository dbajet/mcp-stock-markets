from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class _Constants:
    # --- application ----------------------------------------------------------
    app_name: str = "mcp_stock_markets"
    logger_name: str = "mcp_stock_markets"
    text_encoding: str = "utf-8"

    # --- environment (read by SettingsLoader alone) ---------------------------
    env_environment: str = "APP_ENV"
    env_database_url: str = "DATABASE_URL"
    env_app_version: str = "APP_VERSION"
    env_build_time: str = "BUILD_TIME"
    env_app_commit: str = "APP_COMMIT"
    env_app_base_url: str = "APP_BASE_URL"
    env_data_key: str = "DATA_ENCRYPTION_KEY"
    env_smtp_host: str = "SMTP_HOST"
    env_smtp_port: str = "SMTP_PORT"
    env_smtp_user: str = "SMTP_USER"
    env_smtp_password: str = "SMTP_PASSWORD"
    env_email_from: str = "EMAIL_FROM"
    env_bootstrap_admin_email: str = "BOOTSTRAP_ADMIN_EMAIL"
    env_starting_budget: str = "STARTING_BUDGET"
    env_max_companies: str = "MAX_COMPANIES"
    env_alpha_vantage_key: str = "ALPHA_VANTAGE_API_KEY"
    env_agent_interval_minutes: str = "AGENT_INTERVAL_MINUTES"
    env_mcp_base_url: str = "MCP_BASE_URL"
    env_mcp_token: str = "MCP_TOKEN"
    default_app_base_url: str = "http://localhost:8150"
    # Where the agent reaches the MCP servers: this very process, on its own
    # port. Compose sets the container's (8000); uvicorn on a laptop, its --port.
    default_mcp_base_url: str = "http://127.0.0.1:8150"
    default_starting_budget: str = "500"
    default_max_companies: int = 5
    default_agent_interval_minutes: int = 30
    # A day: an interval longer than that is a typo.
    max_agent_interval_minutes: int = 1440
    # A budget large enough to be a typo rather than a demo.
    max_starting_budget: int = 1_000_000
    # More companies than the agent can look at in one run without drowning its context.
    max_max_companies: int = 25
    mcp_token_bytes: int = 32
    smtp_default_port: int = 587
    environment_production: str = "production"
    environment_development: str = "dev"
    # A value containing one of these was copied from .env.example and never filled.
    placeholder_markers: tuple[str, ...] = ("change_me", "change-me", "placeholder")
    version_unstamped: str = "dev"

    # --- database ---------------------------------------------------------------
    database_connect_timeout_seconds: int = 5
    # Long enough to store the S&P 500 list in one transaction, short enough that a stuck query frees its worker.
    database_statement_timeout_ms: int = 15000
    # A migration waiting on a busy table fails the start instead of queueing every query behind it.
    migration_lock_timeout: str = "5s"
    # pg_advisory_xact_lock key: the two colors starting together must not both migrate.
    migration_lock_key: int = 7_310_401
    # pg_try_advisory_lock key: the scheduler's routine runs in one color at a time.
    routine_lock_key: int = 7_310_404

    # --- pages ------------------------------------------------------------------
    static_directory: str = "static"
    static_mount: str = "/static"
    page_file: str = "index.html"
    # The addresses the single page answers: the app itself, and the page a
    # sign-in link opens (its button POSTs the token).
    page_paths: tuple[str, ...] = ("/", "/auth/link")
    # The service worker must be served from the root to control the whole site.
    service_worker_path: str = "/sw.js"
    service_worker_file: str = "sw.js"
    marker_build: str = "__BUILD__"
    marker_version: str = "__VERSION__"
    header_cache_control: str = "Cache-Control"
    page_cache_control: str = "no-cache"

    # --- security headers (nginx owns HSTS, deploy/nginx-mcp_stock_markets.conf) ------
    content_security_policy: str = (
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
    )
    frame_options: str = "DENY"
    # Nothing here needs a device: everything is denied.
    permissions_policy: str = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
    content_type_options: str = "nosniff"
    referrer_policy: str = "strict-origin-when-cross-origin"

    # --- health -----------------------------------------------------------------
    health_path: str = "/healthz"

    # --- background work ------------------------------------------------
    # How long the job loop waits for work before checking whether it must stop.
    job_poll_seconds: float = 1.0
    # How long a stopping color gives its queued jobs (a sign-in email, an agent
    # run in progress) to finish; under the container's 30 s stop_grace_period.
    job_shutdown_seconds: float = 25.0
    # A failing background job alerts a person at most this often.
    alert_interval_seconds: int = 3600
    alert_subject: str = "[MCP Stock Markets] a background job failed"

    # --- email ------------------------------------------------------------------
    smtp_timeout_seconds: float = 15.0


Constants = _Constants()
