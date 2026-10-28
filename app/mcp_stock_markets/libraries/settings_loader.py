from __future__ import annotations

import base64
import logging
import os
import secrets
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from mcp_stock_markets.constants.constants import Constants
from mcp_stock_markets.constants.market_constants import MarketConstants
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.settings import Settings


class SettingsLoader:
    """The one place that reads the environment.

    It fails closed in production and warns in development, here rather than
    only in the deploy script: a `docker compose up` run by hand has no deploy
    script in front of it, and would otherwise boot on a placeholder.
    """

    def __init__(self, environment: Mapping[str, str]) -> None:
        self._environment = environment

    @classmethod
    def of_process(cls) -> SettingsLoader:
        """This process's own environment: the one mention of `os.environ`
        in the application."""
        return cls(os.environ)

    def loaded(self) -> Settings:
        environment = self._read(Constants.env_environment) or Constants.environment_development
        is_production = environment == Constants.environment_production
        result = Settings(
            environment=environment,
            database_url=self._database_url(is_production),
            app_version=self._read(Constants.env_app_version) or Constants.version_unstamped,
            build_time=self._read(Constants.env_build_time) or Constants.version_unstamped,
            app_commit=self._read(Constants.env_app_commit) or Constants.version_unstamped,
            app_base_url=self._app_base_url(is_production),
            data_key=self._data_key(is_production),
            smtp_host=self._smtp_host(is_production),
            smtp_port=self._smtp_port(),
            smtp_user=self._read(Constants.env_smtp_user),
            smtp_password=self._read(Constants.env_smtp_password),
            email_from=self._read(Constants.env_email_from),
            bootstrap_admin_email=self._read(Constants.env_bootstrap_admin_email).lower(),
            starting_budget=self._starting_budget(),
            max_companies=self._bounded(
                Constants.env_max_companies, Constants.default_max_companies, Constants.max_max_companies
            ),
            alpaca_key_id=self._optional(Constants.env_alpaca_key_id, "no daily history, no fallback quote"),
            alpaca_secret_key=self._optional(Constants.env_alpaca_secret_key, "no daily history, no fallback quote"),
            agent_interval_minutes=self._bounded(
                Constants.env_agent_interval_minutes,
                Constants.default_agent_interval_minutes,
                Constants.max_agent_interval_minutes,
            ),
            mcp_base_url=self._read(Constants.env_mcp_base_url).rstrip("/") or Constants.default_mcp_base_url,
            mcp_token=self._mcp_token(),
        )
        return result

    def _database_url(self, is_production: bool) -> str:
        """No default in any environment: a process with nowhere to keep its
        rows has nothing to offer. The URL carries the database password, so
        a placeholder in it is refused in production like any other secret."""
        result = self._read(Constants.env_database_url)
        if not result:
            raise AppException(500, f"{Constants.env_database_url} is not set")
        if self.has_placeholder(result):
            if is_production:
                raise AppException(500, f"{Constants.env_database_url} still holds a placeholder")
            self._warned(Constants.env_database_url, "still holds a placeholder")
        return result

    def _app_base_url(self, is_production: bool) -> str:
        """Every link is made from this: in production it must be said, never
        guessed from a request."""
        result = self._read(Constants.env_app_base_url).rstrip("/")
        if not result:
            if is_production:
                raise AppException(500, f"{Constants.env_app_base_url} is not set")
            return Constants.default_app_base_url
        # Links need a host, and cookies marked Secure need TLS.
        parts = urlsplit(result)
        if is_production and (parts.scheme != "https" or not parts.hostname):
            raise AppException(500, f"{Constants.env_app_base_url} must be an https:// address with a host")
        return result

    def _data_key(self, is_production: bool) -> str:
        """The sealing key, or a fresh one per process on a laptop: a restart
        then forgets what it sealed, which a laptop can afford. Production
        refuses: its sealed documents must open after every restart."""
        result = self._read(Constants.env_data_key)
        if result and not self.has_placeholder(result):
            return result
        if is_production:
            raise AppException(500, f"{Constants.env_data_key} is not set, or is still a placeholder")
        self._warned(Constants.env_data_key, "is not set: generated for this process")
        return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(Constants.text_encoding)

    def _smtp_host(self, is_production: bool) -> str:
        """The relay, or nothing, which writes sign-in links to the log. A
        link in a log is a login for whoever reads the log, so production
        refuses to start without a relay."""
        result = self._read(Constants.env_smtp_host)
        if not result and is_production:
            raise AppException(500, f"{Constants.env_smtp_host} is not set: in production a link must reach an inbox")
        return result

    def _smtp_port(self) -> int:
        """A port that is not a number is a mistake worth stopping on."""
        raw = self._read(Constants.env_smtp_port)
        if not raw:
            return Constants.smtp_default_port
        try:
            return int(raw)
        except ValueError as error:
            raise AppException(500, f"{Constants.env_smtp_port} is not a port: {raw!r}") from error

    def _starting_budget(self) -> Decimal:
        """Dollars and cents, more than nothing: the portfolio's first cash."""
        raw = self._read(Constants.env_starting_budget) or Constants.default_starting_budget
        try:
            result = Decimal(raw)
        except InvalidOperation as error:
            raise AppException(500, f"{Constants.env_starting_budget} is not an amount: {raw!r}") from error
        if not result.is_finite() or result <= 0 or result > Constants.max_starting_budget:
            raise AppException(
                500,
                f"{Constants.env_starting_budget} must be more than 0 and at most {Constants.max_starting_budget}",
            )
        return result.quantize(Decimal(MarketConstants.money_places))

    def _bounded(self, name: str, default: int, maximum: int) -> int:
        result = self._number(name, default)
        if not 1 <= result <= maximum:
            raise AppException(500, f"{name} must be from 1 to {maximum}")
        return result

    def _optional(self, name: str, without: str) -> str:
        """A value the app runs without, saying what is missing then: the
        Alpaca key pair, whose absence the tools tell the agent too."""
        result = self._read(name)
        if not result or self.has_placeholder(result):
            self._warned(name, f"is not set: {without}")
            return ""
        return result

    def _mcp_token(self) -> str:
        """The MCP servers' bearer token. Made fresh per process when unset:
        the agent is in this process and is handed it, so no one else needs it."""
        result = self._read(Constants.env_mcp_token)
        if result and not self.has_placeholder(result):
            return result
        return secrets.token_urlsafe(Constants.mcp_token_bytes)

    def _number(self, name: str, default: int) -> int:
        raw = self._read(name)
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError as error:
            raise AppException(500, f"{name} is not a whole number: {raw!r}") from error

    @classmethod
    def has_placeholder(cls, value: str) -> bool:
        lowered = value.lower()
        return any(marker in lowered for marker in Constants.placeholder_markers)

    @classmethod
    def _warned(cls, name: str, problem: str) -> None:
        logging.getLogger(Constants.logger_name).warning("[SETTINGS] %s %s", name, problem)

    def _read(self, name: str) -> str:
        return self._environment.get(name, "").strip()
