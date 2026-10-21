from __future__ import annotations

from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.structures.health import Health
from mcp_stock_markets.structures.settings import Settings


class HealthCommand:
    """Whether this process can serve: the database answers, and which
    commit it runs, so the deploy can tell the new color from the old."""

    def __init__(self, settings: Settings, database: Database) -> None:
        self._settings = settings
        self._database = database

    def health(self) -> Health:
        return Health(
            ok=self._database.is_reachable(),
            version=self._settings.app_version,
            commit=self._settings.app_commit,
        )
