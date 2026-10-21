from __future__ import annotations

from decimal import Decimal
from typing import Any, NamedTuple
from urllib.parse import urlsplit

from mcp_stock_markets.constants.constants import Constants
from mcp_stock_markets.structures.wire import Wire


class Settings(NamedTuple):
    """Everything this process was told by its environment, read once by
    `SettingsLoader` and injected everywhere else."""

    environment: str
    database_url: str
    # What is running, stamped by the deploy script because only it knows.
    app_version: str
    build_time: str
    app_commit: str
    # Links come from this, never from a request's Host.
    app_base_url: str
    # Seals the owner's email and the language models' keys, and keys the blind index.
    # Changing it makes every sealed value unreadable, so a deployment keeps the
    # one it started with.
    data_key: str
    # Without a host, a sign-in link is written to the log: a laptop's choice, refused in production.
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    email_from: str
    # The one person who may sign in; the portfolio is theirs.
    bootstrap_admin_email: str
    # The cash the portfolio starts with, when it is made (the first start).
    starting_budget: Decimal
    # How many companies the owner may put in the agent's market.
    max_companies: int
    # Alpha Vantage: daily history and the fallback quote; empty disables both.
    alpha_vantage_key: str
    # How often the agent runs while the market is open.
    agent_interval_minutes: int
    # Where the agent reaches the MCP servers: this process's own port.
    mcp_base_url: str
    # The bearer token every MCP request carries; a fresh one per process
    # unless set, when an outside MCP client (a laptop's) must know it.
    mcp_token: str

    def is_production(self) -> bool:
        return self.environment == Constants.environment_production

    def origin(self) -> str:
        """The scheme, host and port the browser shows: what a request's
        `Origin` must equal."""
        parts = urlsplit(self.app_base_url)
        return f"{parts.scheme}://{parts.netloc}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "environment": self.environment,
            "database_url": self.database_url,
            "app_version": self.app_version,
            "build_time": self.build_time,
            "app_commit": self.app_commit,
            "app_base_url": self.app_base_url,
            "data_key": self.data_key,
            "smtp_host": self.smtp_host,
            "smtp_port": self.smtp_port,
            "smtp_user": self.smtp_user,
            "smtp_password": self.smtp_password,
            "email_from": self.email_from,
            "bootstrap_admin_email": self.bootstrap_admin_email,
            "starting_budget": str(self.starting_budget),
            "max_companies": self.max_companies,
            "alpha_vantage_key": self.alpha_vantage_key,
            "agent_interval_minutes": self.agent_interval_minutes,
            "mcp_base_url": self.mcp_base_url,
            "mcp_token": self.mcp_token,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Settings:
        return cls(
            environment=str(data["environment"]),
            database_url=str(data["database_url"]),
            app_version=str(data["app_version"]),
            build_time=str(data["build_time"]),
            app_commit=str(data["app_commit"]),
            app_base_url=str(data["app_base_url"]),
            data_key=str(data["data_key"]),
            smtp_host=str(data["smtp_host"]),
            smtp_port=int(data["smtp_port"]),
            smtp_user=str(data["smtp_user"]),
            smtp_password=str(data["smtp_password"]),
            email_from=str(data["email_from"]),
            bootstrap_admin_email=str(data["bootstrap_admin_email"]),
            starting_budget=Wire.money(data["starting_budget"]),
            max_companies=int(data["max_companies"]),
            alpha_vantage_key=str(data["alpha_vantage_key"]),
            agent_interval_minutes=int(data["agent_interval_minutes"]),
            mcp_base_url=str(data["mcp_base_url"]),
            mcp_token=str(data["mcp_token"]),
        )
