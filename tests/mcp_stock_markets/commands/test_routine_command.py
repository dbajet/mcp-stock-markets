from __future__ import annotations

import contextlib
import logging
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import call, patch

import pytest

from mcp_stock_markets.commands.agent_command import AgentCommand
from mcp_stock_markets.commands.broker_command import BrokerCommand
from mcp_stock_markets.commands.company_command import CompanyCommand
from mcp_stock_markets.commands.quote_command import QuoteCommand
from mcp_stock_markets.commands.routine_command import RoutineCommand
from mcp_stock_markets.constants.run_trigger import RunTrigger
from mcp_stock_markets.libraries.agent_run_store import AgentRunStore
from mcp_stock_markets.libraries.alerter import Alerter
from mcp_stock_markets.libraries.alpha_vantage_box import AlphaVantageBox
from mcp_stock_markets.libraries.claude_box import ClaudeBox
from mcp_stock_markets.libraries.company_store import CompanyStore
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.libraries.email_box import EmailBox
from mcp_stock_markets.libraries.google_finance_box import GoogleFinanceBox
from mcp_stock_markets.libraries.job_queue import JobQueue
from mcp_stock_markets.libraries.llm_connection_store import LlmConnectionStore
from mcp_stock_markets.libraries.llm_gateway import LlmGateway
from mcp_stock_markets.libraries.market_clock import MarketClock
from mcp_stock_markets.libraries.mcp_client_box import McpClientBox
from mcp_stock_markets.libraries.openai_chat_box import OpenAiChatBox
from mcp_stock_markets.libraries.portfolio_store import PortfolioStore
from mcp_stock_markets.libraries.quote_store import QuoteStore
from mcp_stock_markets.libraries.secret_sealer import SecretSealer
from mcp_stock_markets.libraries.web_box import WebBox
from mcp_stock_markets.libraries.wikipedia_box import WikipediaBox
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.market_status import MarketStatus
from mcp_stock_markets.structures.settings import Settings
from mcp_stock_markets.structures.valuation import Valuation

KEY = "Zm9yLXRlc3RzLW9ubHktZm9yLXRlc3RzLW9ubHktMzI="
NOW = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
NEW_YORK = timezone(timedelta(hours=-4))
MODULE = "mcp_stock_markets.commands.routine_command"


def helper_settings() -> Settings:
    return Settings(
        environment="dev",
        database_url="postgresql://u:p@h/d",
        app_version="2026-10-21.1",
        build_time="20261021-120000Z",
        app_commit="abc",
        app_base_url="https://stocks.example.com",
        data_key=KEY,
        smtp_host="",
        smtp_port=587,
        smtp_user="",
        smtp_password="",
        email_from="",
        bootstrap_admin_email="owner@example.com",
        starting_budget=Decimal("500.00"),
        max_companies=5,
        alpha_vantage_key="",
        agent_interval_minutes=30,
        mcp_base_url="http://127.0.0.1:8000",
        mcp_token="mcp-token",
    )


def helper_parts() -> tuple[Database, CompanyCommand, QuoteCommand, BrokerCommand, AgentCommand]:
    settings = helper_settings()
    database = Database("postgresql://u:p@h/d")
    company_store = CompanyStore(database)
    quotes = QuoteCommand(
        QuoteStore(database),
        company_store,
        GoogleFinanceBox(WebBox()),
        AlphaVantageBox(WebBox(), ""),
        MarketClock(),
    )
    broker = BrokerCommand(settings, database, PortfolioStore(database), company_store, quotes)
    agent = AgentCommand(
        settings,
        database,
        AgentRunStore(database),
        LlmGateway(LlmConnectionStore(database, SecretSealer(KEY)), OpenAiChatBox(), ClaudeBox()),
        McpClientBox(settings),
        quotes,
        broker,
        JobQueue("agent", Alerter(EmailBox(settings), "owner@example.com")),
    )
    companies = CompanyCommand(settings, company_store, WikipediaBox(WebBox()))
    return database, companies, quotes, broker, agent


def helper_instance() -> RoutineCommand:
    return RoutineCommand(*helper_parts())


def helper_status(is_open: bool) -> MarketStatus:
    return MarketStatus(
        is_open=is_open,
        now=datetime(2026, 10, 21, 11, 0, tzinfo=NEW_YORK),
        closes_at=datetime(2026, 10, 21, 16, 0, tzinfo=NEW_YORK) if is_open else None,
        next_open=datetime(2026, 10, 22, 9, 30, tzinfo=NEW_YORK),
    )


def test___init__() -> None:
    database, companies, quotes, broker, agent = helper_parts()
    tested = RoutineCommand(database, companies, quotes, broker, agent)
    result = (tested._database, tested._companies, tested._quotes, tested._broker, tested._agent)
    expected = (database, companies, quotes, broker, agent)
    assert result == expected


@pytest.mark.parametrize(
    "is_due, exp_agent_queued",
    [
        pytest.param(True, [call()], id="run-due"),
        pytest.param(False, [], id="run-not-due"),
    ],
)
def test_ticked(is_due: bool, exp_agent_queued: list[object]) -> None:
    """The market open: the list refreshed if stale, the portfolio valued if
    due, and a run queued when one is due."""
    tested = helper_instance()
    with (
        patch(f"{MODULE}.datetime", wraps=datetime) as mock_datetime,
        patch.object(Database, "held", side_effect=[contextlib.nullcontext(True)]) as mock_held,
        patch.object(CompanyCommand, "refreshed_if_stale", side_effect=[None]) as mock_refreshed_if_stale,
        patch.object(QuoteCommand, "market", side_effect=[helper_status(True)]) as mock_market,
        patch.object(RoutineCommand, "valued_if_due", side_effect=[None]) as mock_valued_if_due,
        patch.object(AgentCommand, "is_due", side_effect=[is_due]) as mock_is_due,
        patch.object(RoutineCommand, "agent_queued", side_effect=[None]) as mock_agent_queued,
    ):
        mock_datetime.now.side_effect = [NOW]
        result = tested.ticked()
    assert result is None
    exp_calls = [call.now(UTC)]
    assert mock_datetime.mock_calls == exp_calls
    exp_calls = [call(7_310_404)]
    assert mock_held.mock_calls == exp_calls
    exp_calls = [call(datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_refreshed_if_stale.mock_calls == exp_calls
    assert mock_market.mock_calls == exp_calls
    assert mock_valued_if_due.mock_calls == exp_calls
    assert mock_is_due.mock_calls == exp_calls
    assert mock_agent_queued.mock_calls == exp_agent_queued


def test_ticked__market_closed() -> None:
    """Only the S&P 500 refresh: nothing is valued, no run is queued."""
    tested = helper_instance()
    with (
        patch(f"{MODULE}.datetime", wraps=datetime) as mock_datetime,
        patch.object(Database, "held", side_effect=[contextlib.nullcontext(True)]) as mock_held,
        patch.object(CompanyCommand, "refreshed_if_stale", side_effect=[None]) as mock_refreshed_if_stale,
        patch.object(QuoteCommand, "market", side_effect=[helper_status(False)]) as mock_market,
        patch.object(RoutineCommand, "valued_if_due", side_effect=[]) as mock_valued_if_due,
        patch.object(AgentCommand, "is_due", side_effect=[]) as mock_is_due,
        patch.object(RoutineCommand, "agent_queued", side_effect=[]) as mock_agent_queued,
    ):
        mock_datetime.now.side_effect = [NOW]
        result = tested.ticked()
    assert result is None
    exp_calls = [call.now(UTC)]
    assert mock_datetime.mock_calls == exp_calls
    exp_calls = [call(7_310_404)]
    assert mock_held.mock_calls == exp_calls
    exp_calls = [call(datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_refreshed_if_stale.mock_calls == exp_calls
    assert mock_market.mock_calls == exp_calls
    exp_calls = []
    assert mock_valued_if_due.mock_calls == exp_calls
    assert mock_is_due.mock_calls == exp_calls
    assert mock_agent_queued.mock_calls == exp_calls


def test_ticked__lock_busy() -> None:
    """The other color does the routine: nothing is done here."""
    tested = helper_instance()
    with (
        patch(f"{MODULE}.datetime", wraps=datetime) as mock_datetime,
        patch.object(Database, "held", side_effect=[contextlib.nullcontext(False)]) as mock_held,
        patch.object(CompanyCommand, "refreshed_if_stale", side_effect=[]) as mock_refreshed_if_stale,
        patch.object(QuoteCommand, "market", side_effect=[]) as mock_market,
        patch.object(RoutineCommand, "valued_if_due", side_effect=[]) as mock_valued_if_due,
        patch.object(RoutineCommand, "agent_queued", side_effect=[]) as mock_agent_queued,
    ):
        mock_datetime.now.side_effect = [NOW]
        result = tested.ticked()
    assert result is None
    exp_calls = [call.now(UTC)]
    assert mock_datetime.mock_calls == exp_calls
    exp_calls = [call(7_310_404)]
    assert mock_held.mock_calls == exp_calls
    exp_calls = []
    assert mock_refreshed_if_stale.mock_calls == exp_calls
    assert mock_market.mock_calls == exp_calls
    assert mock_valued_if_due.mock_calls == exp_calls
    assert mock_agent_queued.mock_calls == exp_calls


@pytest.mark.parametrize(
    "last, valued, exp_valued",
    [
        pytest.param(
            None,
            [Valuation(taken_at=NOW, cash=Decimal("500.00"), holdings_value=Decimal("0"), total_value=Decimal("500"))],
            [call(datetime(2026, 10, 21, 15, 0, tzinfo=UTC))],
            id="never-valued",
        ),
        pytest.param(
            datetime(2026, 10, 21, 14, 30, tzinfo=UTC),
            [Valuation(taken_at=NOW, cash=Decimal("500.00"), holdings_value=Decimal("0"), total_value=Decimal("500"))],
            [call(datetime(2026, 10, 21, 15, 0, tzinfo=UTC))],
            id="half-an-hour-ago",
        ),
        pytest.param(datetime(2026, 10, 21, 14, 30, 0, 1, tzinfo=UTC), [], [], id="not-yet"),
    ],
)
def test_valued_if_due(last: datetime | None, valued: list[Valuation], exp_valued: list[object]) -> None:
    tested = helper_instance()
    with (
        patch.object(BrokerCommand, "last_valued_at", side_effect=[last]) as mock_last_valued_at,
        patch.object(BrokerCommand, "valued", side_effect=valued) as mock_valued,
    ):
        result = tested.valued_if_due(NOW)
    assert result is None
    exp_calls = [call()]
    assert mock_last_valued_at.mock_calls == exp_calls
    assert mock_valued.mock_calls == exp_valued


@pytest.mark.parametrize(
    "outcome, exp_messages",
    [
        pytest.param(None, [], id="queued"),
        pytest.param(
            AppException(503, "The agent needs a language model: choose one in Settings › Language models."),
            ["[ROUTINE] no scheduled run: The agent needs a language model: choose one in Settings › Language models."],
            id="no-model",
        ),
    ],
)
def test_agent_queued(caplog: pytest.LogCaptureFixture, outcome: object, exp_messages: list[str]) -> None:
    tested = helper_instance()
    with (
        caplog.at_level(logging.INFO, logger="mcp_stock_markets"),
        patch.object(AgentCommand, "queued", side_effect=[outcome]) as mock_queued,
    ):
        result = tested.agent_queued()
    assert result is None
    assert caplog.messages == exp_messages
    exp_calls = [call(RunTrigger.SCHEDULE)]
    assert mock_queued.mock_calls == exp_calls
