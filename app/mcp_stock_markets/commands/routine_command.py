from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from mcp_stock_markets.commands.agent_command import AgentCommand
from mcp_stock_markets.commands.broker_command import BrokerCommand
from mcp_stock_markets.commands.company_command import CompanyCommand
from mcp_stock_markets.commands.quote_command import QuoteCommand
from mcp_stock_markets.constants.broker_constants import BrokerConstants
from mcp_stock_markets.constants.constants import Constants
from mcp_stock_markets.constants.run_trigger import RunTrigger
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.structures.app_exception import AppException


class RoutineCommand:
    """What the scheduler does each minute: read the S&P 500 again when the
    stored list is a day old; while the market is open, value the portfolio
    every half hour and queue an agent run when one is due. Each job takes
    the advisory lock the two colors share, so only one does it."""

    def __init__(
        self,
        database: Database,
        companies: CompanyCommand,
        quotes: QuoteCommand,
        broker: BrokerCommand,
        agent: AgentCommand,
    ) -> None:
        self._database = database
        self._companies = companies
        self._quotes = quotes
        self._broker = broker
        self._agent = agent

    def ticked(self) -> None:
        now = datetime.now(UTC)
        with self._database.held(Constants.routine_lock_key) as is_free:
            if not is_free:
                return
            self._companies.refreshed_if_stale(now)
            if not self._quotes.market(now).is_open:
                return
            self.valued_if_due(now)
            if self._agent.is_due(now):
                self.agent_queued()

    def valued_if_due(self, now: datetime) -> None:
        last = self._broker.last_valued_at()
        if last is None or now - last >= timedelta(minutes=BrokerConstants.valuation_interval_minutes):
            self._broker.valued(now)

    def agent_queued(self) -> None:
        """A run without a model is skipped, and said so in the log: the owner
        has not chosen one yet."""
        try:
            self._agent.queued(RunTrigger.SCHEDULE)
        except AppException as error:
            logging.getLogger(Constants.logger_name).info("[ROUTINE] no scheduled run: %s", error.message)
