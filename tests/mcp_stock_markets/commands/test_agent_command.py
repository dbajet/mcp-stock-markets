from __future__ import annotations

import contextlib
import logging
import time
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import Mock, call, patch

import pytest

from mcp_stock_markets.commands.agent_command import AgentCommand
from mcp_stock_markets.commands.broker_command import BrokerCommand
from mcp_stock_markets.commands.quote_command import QuoteCommand
from mcp_stock_markets.constants.llm_kind import LlmKind
from mcp_stock_markets.constants.mcp_server_name import McpServerName
from mcp_stock_markets.constants.run_status import RunStatus
from mcp_stock_markets.constants.run_trigger import RunTrigger
from mcp_stock_markets.constants.step_kind import StepKind
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
from mcp_stock_markets.structures.agent_exchange import AgentExchange
from mcp_stock_markets.structures.agent_reply import AgentReply
from mcp_stock_markets.structures.agent_run import AgentRun
from mcp_stock_markets.structures.agent_step import AgentStep
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.llm_connection import LlmConnection
from mcp_stock_markets.structures.market_status import MarketStatus
from mcp_stock_markets.structures.settings import Settings
from mcp_stock_markets.structures.tool_call import ToolCall
from mcp_stock_markets.structures.tool_result import ToolResult
from mcp_stock_markets.structures.tool_spec import ToolSpec
from mcp_stock_markets.structures.valuation import Valuation

KEY = "Zm9yLXRlc3RzLW9ubHktZm9yLXRlc3RzLW9ubHktMzI="
NOW = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
NEW_YORK = timezone(timedelta(hours=-4))
MODULE = "mcp_stock_markets.commands.agent_command"


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


def helper_parts() -> tuple[Database, AgentRunStore, LlmGateway, McpClientBox, QuoteCommand, BrokerCommand, JobQueue]:
    settings = helper_settings()
    database = Database("postgresql://u:p@h/d")
    companies = CompanyStore(database)
    quotes = QuoteCommand(
        QuoteStore(database),
        companies,
        GoogleFinanceBox(WebBox()),
        AlphaVantageBox(WebBox(), ""),
        MarketClock(),
    )
    return (
        database,
        AgentRunStore(database),
        LlmGateway(LlmConnectionStore(database, SecretSealer(KEY)), OpenAiChatBox(), ClaudeBox()),
        McpClientBox(settings),
        quotes,
        BrokerCommand(settings, database, PortfolioStore(database), companies, quotes),
        JobQueue("agent", Alerter(EmailBox(settings), "owner@example.com")),
    )


def helper_instance() -> AgentCommand:
    return AgentCommand(helper_settings(), *helper_parts())


def helper_connection() -> LlmConnection:
    return LlmConnection(
        connection_id=1,
        name="Claude",
        kind=LlmKind.CLAUDE,
        base_url="",
        api_key="sk-test",
        model="claude-opus-5-5",
        disable_thinking=False,
    )


def helper_run(status: RunStatus, summary: str, error: str) -> AgentRun:
    return AgentRun(
        run_id=4,
        trigger=RunTrigger.MANUAL,
        status=status,
        started_at=NOW,
        finished_at=None if status is RunStatus.RUNNING else datetime(2026, 10, 21, 15, 2, tzinfo=UTC),
        connection_name="Claude",
        model="claude-opus-5-5",
        turns=0 if status is RunStatus.RUNNING else 2,
        summary=summary,
        error=error,
    )


def helper_step(kind: StepKind, content: str) -> AgentStep:
    return AgentStep(
        step_id=9,
        run_id=4,
        position=1,
        kind=kind,
        server="",
        tool="",
        arguments=None,
        content=content,
        is_error=False,
        elapsed_ms=0.0,
        created_at=NOW,
    )


def helper_tool(server: McpServerName, name: str) -> ToolSpec:
    return ToolSpec(
        server=server,
        name=name,
        description=f"The {name} tool.",
        input_schema={"type": "object", "properties": {}},
    )


def helper_system() -> str:
    return "\n".join(
        [
            "You manage a virtual stock portfolio. No real money is involved: this is a demonstration.",
            "Your goal is to make the portfolio's total value (cash plus the shares at their latest price) grow.",
            "",
            "You act only through the tools of three MCP servers:",
            "- sp500: the companies of the S&P 500 index, their sector and industry;",
            "- quotes: whether the US market is open, the latest price of a stock, and its daily history;",
            "- broker: the portfolio, its past transactions, and buying or selling shares.",
            "",
            "The rules, which the broker enforces:",
            "- you may buy only the companies of the market the owner chose (the broker's portfolio lists them);",
            "  you may always sell what the portfolio holds;",
            "- whole shares only, no short selling, no borrowing: cash never goes below zero;",
            "- orders are taken only while the US market is open, at the latest price, without fees.",
            "",
            "Each run, look at the portfolio and the market, decide, and place the orders you think are right.",
            "Doing nothing is a valid decision. Give every order a short reason.",
            "Finish with a summary of a few sentences: what you looked at, what you did, and why.",
        ]
    )


def helper_task() -> str:
    return "It is 2026-10-21T11:00-04:00 in New York. The market is open. Review the portfolio and act."


def test___init__() -> None:
    database, store, gateway, mcp, quotes, broker, jobs = helper_parts()
    tested = AgentCommand(helper_settings(), database, store, gateway, mcp, quotes, broker, jobs)
    result = (
        tested._interval,
        tested._database,
        tested._store,
        tested._gateway,
        tested._mcp,
        tested._quotes,
        tested._broker,
        tested._jobs,
    )
    expected = (timedelta(minutes=30), database, store, gateway, mcp, quotes, broker, jobs)
    assert result == expected


def test_queued() -> None:
    tested = helper_instance()
    with (
        patch.object(LlmGateway, "agent_connection", side_effect=[helper_connection()]) as mock_agent_connection,
        patch.object(JobQueue, "queued", side_effect=[None]) as mock_queued,
    ):
        result = tested.queued(RunTrigger.MANUAL)
    assert result is None
    exp_calls = [call()]
    assert mock_agent_connection.mock_calls == exp_calls
    exp_calls = [call(tested.performed, (RunTrigger.MANUAL,))]
    assert mock_queued.mock_calls == exp_calls


def test_queued__without_a_model() -> None:
    """Refused at once: nothing is queued, so no run is recorded as failed."""
    tested = helper_instance()
    with (
        patch.object(
            LlmGateway,
            "agent_connection",
            side_effect=[
                AppException(503, "The agent needs a language model: choose one in Settings › Language models.")
            ],
        ) as mock_agent_connection,
        patch.object(JobQueue, "queued", side_effect=[]) as mock_queued,
        pytest.raises(AppException) as exc_info,
    ):
        tested.queued(RunTrigger.SCHEDULE)
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (503, "The agent needs a language model: choose one in Settings › Language models.")
    assert result == expected
    exp_calls = [call()]
    assert mock_agent_connection.mock_calls == exp_calls
    exp_calls = []
    assert mock_queued.mock_calls == exp_calls


def test_performed() -> None:
    tested = helper_instance()
    with patch.object(
        AgentCommand, "ran", side_effect=[helper_run(RunStatus.COMPLETED, "Bought AAPL.", "")]
    ) as mock_ran:
        result = tested.performed(RunTrigger.SCHEDULE)
    assert result is None
    exp_calls = [call(RunTrigger.SCHEDULE)]
    assert mock_ran.mock_calls == exp_calls


@pytest.mark.parametrize(
    "last, expected",
    [
        pytest.param(None, True, id="never-ran"),
        pytest.param(datetime(2026, 10, 21, 14, 30, tzinfo=UTC), True, id="exactly-the-interval"),
        pytest.param(datetime(2026, 10, 21, 14, 0, tzinfo=UTC), True, id="longer"),
        pytest.param(datetime(2026, 10, 21, 14, 30, 0, 1, tzinfo=UTC), False, id="not-yet"),
    ],
)
def test_is_due(last: datetime | None, expected: bool) -> None:
    tested = helper_instance()
    with patch.object(AgentRunStore, "last_started", side_effect=[last]) as mock_last_started:
        result = tested.is_due(NOW)
    assert result is expected
    exp_calls = [call(RunTrigger.SCHEDULE)]
    assert mock_last_started.mock_calls == exp_calls


@pytest.mark.parametrize(
    "trigger, is_due, exp_now, exp_is_due",
    [
        pytest.param(RunTrigger.MANUAL, [], [], [], id="manual-always"),
        pytest.param(
            RunTrigger.SCHEDULE,
            [True],
            [call.now(UTC)],
            [call(datetime(2026, 10, 21, 15, 0, tzinfo=UTC))],
            id="scheduled-still-due",
        ),
    ],
)
@pytest.mark.parametrize(
    "conversed, exp_finished",
    [
        pytest.param(
            (2, RunStatus.COMPLETED, "Bought AAPL."),
            [call(4, RunStatus.COMPLETED, 2, "Bought AAPL.", "")],
            id="completed",
        ),
        pytest.param(
            (16, RunStatus.EXHAUSTED, "Stopped after 16 rounds without a final summary."),
            [call(4, RunStatus.EXHAUSTED, 16, "Stopped after 16 rounds without a final summary.", "")],
            id="exhausted",
        ),
    ],
)
def test_ran(
    trigger: RunTrigger,
    is_due: list[bool],
    exp_now: list[object],
    exp_is_due: list[object],
    conversed: tuple[int, RunStatus, str],
    exp_finished: list[object],
) -> None:
    tested = helper_instance()
    finished = helper_run(conversed[1], conversed[2], "")
    with (
        patch(f"{MODULE}.datetime", wraps=datetime) as mock_datetime,
        patch.object(Database, "held", side_effect=[contextlib.nullcontext(True)]) as mock_held,
        patch.object(AgentCommand, "is_due", side_effect=is_due) as mock_is_due,
        patch.object(LlmGateway, "agent_connection", side_effect=[helper_connection()]) as mock_agent_connection,
        patch.object(AgentRunStore, "started", side_effect=[helper_run(RunStatus.RUNNING, "", "")]) as mock_started,
        patch.object(AgentCommand, "conversed", side_effect=[conversed]) as mock_conversed,
        patch.object(AgentRunStore, "finished", side_effect=[None]) as mock_finished,
        patch.object(AgentCommand, "valued", side_effect=[None]) as mock_valued,
        patch.object(AgentRunStore, "run", side_effect=[finished]) as mock_run,
    ):
        mock_datetime.now.side_effect = [NOW]
        result = tested.ran(trigger)
    expected = finished
    assert result == expected
    assert mock_datetime.mock_calls == exp_now
    exp_calls = [call(7_310_403)]
    assert mock_held.mock_calls == exp_calls
    assert mock_is_due.mock_calls == exp_is_due
    exp_calls = [call()]
    assert mock_agent_connection.mock_calls == exp_calls
    assert mock_valued.mock_calls == exp_calls
    exp_calls = [call(trigger, "Claude", "claude-opus-5-5")]
    assert mock_started.mock_calls == exp_calls
    exp_calls = [call(helper_run(RunStatus.RUNNING, "", ""), helper_connection())]
    assert mock_conversed.mock_calls == exp_calls
    assert mock_finished.mock_calls == exp_finished
    exp_calls = [call(4)]
    assert mock_run.mock_calls == exp_calls


def test_ran__lock_busy(caplog: pytest.LogCaptureFixture) -> None:
    tested = helper_instance()
    with (
        caplog.at_level(logging.INFO, logger="mcp_stock_markets"),
        patch(f"{MODULE}.datetime", wraps=datetime) as mock_datetime,
        patch.object(Database, "held", side_effect=[contextlib.nullcontext(False)]) as mock_held,
        patch.object(LlmGateway, "agent_connection", side_effect=[]) as mock_agent_connection,
        patch.object(AgentRunStore, "started", side_effect=[]) as mock_started,
    ):
        result = tested.ran(RunTrigger.MANUAL)
    assert result is None
    exp_messages = ["[AGENT] a run is in progress elsewhere"]
    assert caplog.messages == exp_messages
    exp_calls = []
    assert mock_datetime.mock_calls == exp_calls
    assert mock_agent_connection.mock_calls == exp_calls
    assert mock_started.mock_calls == exp_calls
    exp_calls = [call(7_310_403)]
    assert mock_held.mock_calls == exp_calls


def test_ran__scheduled_no_longer_due() -> None:
    """A scheduled run queued behind a long Run now is dropped."""
    tested = helper_instance()
    with (
        patch(f"{MODULE}.datetime", wraps=datetime) as mock_datetime,
        patch.object(Database, "held", side_effect=[contextlib.nullcontext(True)]) as mock_held,
        patch.object(AgentCommand, "is_due", side_effect=[False]) as mock_is_due,
        patch.object(LlmGateway, "agent_connection", side_effect=[]) as mock_agent_connection,
        patch.object(AgentRunStore, "started", side_effect=[]) as mock_started,
    ):
        mock_datetime.now.side_effect = [NOW]
        result = tested.ran(RunTrigger.SCHEDULE)
    assert result is None
    exp_calls = [call.now(UTC)]
    assert mock_datetime.mock_calls == exp_calls
    exp_calls = [call(7_310_403)]
    assert mock_held.mock_calls == exp_calls
    exp_calls = [call(datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_is_due.mock_calls == exp_calls
    exp_calls = []
    assert mock_agent_connection.mock_calls == exp_calls
    assert mock_started.mock_calls == exp_calls


def test_ran__failed() -> None:
    """The model or a server failed: the run is finished as failed, with why."""
    tested = helper_instance()
    failed = helper_run(RunStatus.FAILED, "", "The language model did not answer.")
    with (
        patch.object(Database, "held", side_effect=[contextlib.nullcontext(True)]) as mock_held,
        patch.object(LlmGateway, "agent_connection", side_effect=[helper_connection()]) as mock_agent_connection,
        patch.object(AgentRunStore, "started", side_effect=[helper_run(RunStatus.RUNNING, "", "")]) as mock_started,
        patch.object(
            AgentCommand, "conversed", side_effect=[AppException(502, "The language model did not answer.")]
        ) as mock_conversed,
        patch.object(AgentRunStore, "finished", side_effect=[None]) as mock_finished,
        patch.object(AgentCommand, "valued", side_effect=[None]) as mock_valued,
        patch.object(AgentRunStore, "run", side_effect=[failed]) as mock_run,
    ):
        result = tested.ran(RunTrigger.MANUAL)
    expected = helper_run(RunStatus.FAILED, "", "The language model did not answer.")
    assert result == expected
    exp_calls = [call(7_310_403)]
    assert mock_held.mock_calls == exp_calls
    exp_calls = [call()]
    assert mock_agent_connection.mock_calls == exp_calls
    assert mock_valued.mock_calls == exp_calls
    exp_calls = [call(RunTrigger.MANUAL, "Claude", "claude-opus-5-5")]
    assert mock_started.mock_calls == exp_calls
    exp_calls = [call(helper_run(RunStatus.RUNNING, "", ""), helper_connection())]
    assert mock_conversed.mock_calls == exp_calls
    exp_calls = [call(4, RunStatus.FAILED, 0, "", "The language model did not answer.")]
    assert mock_finished.mock_calls == exp_calls
    exp_calls = [call(4)]
    assert mock_run.mock_calls == exp_calls


def test_ran__unexpected_error() -> None:
    """The run is still finished, as failed, and the error goes on to the job queue."""
    tested = helper_instance()
    with (
        patch.object(Database, "held", side_effect=[contextlib.nullcontext(True)]) as mock_held,
        patch.object(LlmGateway, "agent_connection", side_effect=[helper_connection()]) as mock_agent_connection,
        patch.object(AgentRunStore, "started", side_effect=[helper_run(RunStatus.RUNNING, "", "")]) as mock_started,
        patch.object(AgentCommand, "conversed", side_effect=[KeyError("content")]) as mock_conversed,
        patch.object(AgentRunStore, "finished", side_effect=[None]) as mock_finished,
        patch.object(AgentCommand, "valued", side_effect=[]) as mock_valued,
        patch.object(AgentRunStore, "run", side_effect=[]) as mock_run,
        pytest.raises(KeyError) as exc_info,
    ):
        tested.ran(RunTrigger.MANUAL)
    result = exc_info.value.args
    expected = ("content",)
    assert result == expected
    exp_calls = [call(7_310_403)]
    assert mock_held.mock_calls == exp_calls
    exp_calls = [call()]
    assert mock_agent_connection.mock_calls == exp_calls
    exp_calls = [call(RunTrigger.MANUAL, "Claude", "claude-opus-5-5")]
    assert mock_started.mock_calls == exp_calls
    exp_calls = [call(helper_run(RunStatus.RUNNING, "", ""), helper_connection())]
    assert mock_conversed.mock_calls == exp_calls
    exp_calls = [call(4, RunStatus.FAILED, 0, "", "The run stopped on an unexpected error.")]
    assert mock_finished.mock_calls == exp_calls
    exp_calls = []
    assert mock_valued.mock_calls == exp_calls
    assert mock_run.mock_calls == exp_calls


def helper_replied(replies: list[AgentReply], seen: list[list[AgentExchange]]) -> Any:
    """agent_reply's stand-in: the run's exchanges as each call saw them (the
    list itself goes on growing after the call), and the next reply."""

    def replied(
        connection: LlmConnection,
        system: str,
        task: str,
        exchanges: list[AgentExchange],
        tools: list[ToolSpec],
    ) -> AgentReply:
        seen.append(list(exchanges))
        return replies.pop(0)

    return replied


def test_conversed() -> None:
    """Thinking, words and tool calls are recorded in the order they came; the
    answers go back to the model in the next round."""
    tested = helper_instance()
    portfolio = helper_tool(McpServerName.BROKER, "portfolio")
    quote = helper_tool(McpServerName.QUOTES, "quote")
    first = AgentReply(
        text="Let me look at the portfolio.",
        reasoning="Check cash first.",
        tool_calls=(
            ToolCall(call_id="c1", name="broker__portfolio", arguments={}),
            ToolCall(call_id="c2", name="quotes__quote", arguments={"symbol": "AAPL"}),
        ),
        model="claude-opus-5-5",
        raw=({"type": "text"},),
    )
    last = AgentReply(text="Held everything.", reasoning="", tool_calls=(), model="claude-opus-5-5", raw=())
    results = [
        ToolResult(call_id="c1", content='{"cash": "500.00"}', is_error=False),
        ToolResult(call_id="c2", content='{"price": "231.45"}', is_error=False),
    ]
    seen: list[list[AgentExchange]] = []
    run = helper_run(RunStatus.RUNNING, "", "")
    steps = [helper_step(StepKind.THINKING, "a"), helper_step(StepKind.MODEL, "b"), helper_step(StepKind.MODEL, "c")]
    with (
        patch(f"{MODULE}.datetime", wraps=datetime) as mock_datetime,
        patch.object(AgentCommand, "tools", side_effect=[[portfolio, quote]]) as mock_tools,
        patch.object(AgentCommand, "task", side_effect=[helper_task()]) as mock_task,
        patch.object(LlmGateway, "agent_reply", side_effect=helper_replied([first, last], seen)) as mock_agent_reply,
        patch.object(AgentCommand, "stepped", side_effect=steps) as mock_stepped,
        patch.object(AgentCommand, "answered", side_effect=results) as mock_answered,
    ):
        mock_datetime.now.side_effect = [NOW]
        manager = Mock()
        manager.attach_mock(mock_stepped, "stepped")
        manager.attach_mock(mock_answered, "answered")
        result = tested.conversed(run, helper_connection())
    expected = (2, RunStatus.COMPLETED, "Held everything.")
    assert result == expected
    exp_calls = [call.now(UTC)]
    assert mock_datetime.mock_calls == exp_calls
    exp_calls = [call()]
    assert mock_tools.mock_calls == exp_calls
    exp_calls = [call(datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_task.mock_calls == exp_calls
    exp_exchange = AgentExchange(
        reply=AgentReply(
            text="Let me look at the portfolio.",
            reasoning="Check cash first.",
            tool_calls=(
                ToolCall(call_id="c1", name="broker__portfolio", arguments={}),
                ToolCall(call_id="c2", name="quotes__quote", arguments={"symbol": "AAPL"}),
            ),
            model="claude-opus-5-5",
            raw=({"type": "text"},),
        ),
        results=(
            ToolResult(call_id="c1", content='{"cash": "500.00"}', is_error=False),
            ToolResult(call_id="c2", content='{"price": "231.45"}', is_error=False),
        ),
    )
    exp_seen = [[], [exp_exchange]]
    assert seen == exp_seen
    exp_tools = [
        helper_tool(McpServerName.BROKER, "portfolio"),
        helper_tool(McpServerName.QUOTES, "quote"),
    ]
    # The mock keeps the exchanges list itself, as the run left it.
    exp_calls = [
        call(helper_connection(), helper_system(), helper_task(), [exp_exchange], exp_tools),
        call(helper_connection(), helper_system(), helper_task(), [exp_exchange], exp_tools),
    ]
    assert mock_agent_reply.mock_calls == exp_calls
    exp_by_name = {
        "broker__portfolio": helper_tool(McpServerName.BROKER, "portfolio"),
        "quotes__quote": helper_tool(McpServerName.QUOTES, "quote"),
    }
    exp_calls = [
        call.stepped(
            helper_run(RunStatus.RUNNING, "", ""), StepKind.THINKING, "", "", None, "Check cash first.", False, 0.0
        ),
        call.stepped(
            helper_run(RunStatus.RUNNING, "", ""),
            StepKind.MODEL,
            "",
            "",
            None,
            "Let me look at the portfolio.",
            False,
            0.0,
        ),
        call.answered(
            helper_run(RunStatus.RUNNING, "", ""),
            ToolCall(call_id="c1", name="broker__portfolio", arguments={}),
            exp_by_name,
        ),
        call.answered(
            helper_run(RunStatus.RUNNING, "", ""),
            ToolCall(call_id="c2", name="quotes__quote", arguments={"symbol": "AAPL"}),
            exp_by_name,
        ),
        call.stepped(
            helper_run(RunStatus.RUNNING, "", ""), StepKind.MODEL, "", "", None, "Held everything.", False, 0.0
        ),
    ]
    assert manager.mock_calls == exp_calls


def test_conversed__silent_end() -> None:
    """A reply with no words and no calls ends the run at once, recording nothing."""
    tested = helper_instance()
    silent = AgentReply(text="", reasoning="", tool_calls=(), model="claude-opus-5-5", raw=())
    with (
        patch(f"{MODULE}.datetime", wraps=datetime) as mock_datetime,
        patch.object(AgentCommand, "tools", side_effect=[[]]) as mock_tools,
        patch.object(AgentCommand, "task", side_effect=[helper_task()]) as mock_task,
        patch.object(LlmGateway, "agent_reply", side_effect=[silent]) as mock_agent_reply,
        patch.object(AgentCommand, "stepped", side_effect=[]) as mock_stepped,
        patch.object(AgentCommand, "answered", side_effect=[]) as mock_answered,
    ):
        mock_datetime.now.side_effect = [NOW]
        result = tested.conversed(helper_run(RunStatus.RUNNING, "", ""), helper_connection())
    expected = (1, RunStatus.COMPLETED, "")
    assert result == expected
    exp_calls = [call.now(UTC)]
    assert mock_datetime.mock_calls == exp_calls
    exp_calls = [call()]
    assert mock_tools.mock_calls == exp_calls
    exp_calls = [call(datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_task.mock_calls == exp_calls
    exp_calls = [call(helper_connection(), helper_system(), helper_task(), [], [])]
    assert mock_agent_reply.mock_calls == exp_calls
    exp_calls = []
    assert mock_stepped.mock_calls == exp_calls
    assert mock_answered.mock_calls == exp_calls


def test_conversed__exhausted() -> None:
    """A model that calls tools every round is stopped after 16 rounds."""
    tested = helper_instance()
    tool = helper_tool(McpServerName.BROKER, "portfolio")
    reply = AgentReply(
        text="",
        reasoning="",
        tool_calls=(ToolCall(call_id="c1", name="broker__portfolio", arguments={}),),
        model="claude-opus-5-5",
        raw=(),
    )
    answer = ToolResult(call_id="c1", content='{"cash": "500.00"}', is_error=False)
    seen: list[list[AgentExchange]] = []
    run = helper_run(RunStatus.RUNNING, "", "")
    with (
        patch(f"{MODULE}.datetime", wraps=datetime) as mock_datetime,
        patch.object(AgentCommand, "tools", side_effect=[[tool]]) as mock_tools,
        patch.object(AgentCommand, "task", side_effect=[helper_task()]) as mock_task,
        patch.object(LlmGateway, "agent_reply", side_effect=helper_replied([reply] * 17, seen)) as mock_agent_reply,
        patch.object(AgentCommand, "stepped", side_effect=[]) as mock_stepped,
        patch.object(AgentCommand, "answered", side_effect=[answer] * 17) as mock_answered,
    ):
        mock_datetime.now.side_effect = [NOW]
        result = tested.conversed(run, helper_connection())
    expected = (16, RunStatus.EXHAUSTED, "Stopped after 16 rounds without a final summary.")
    assert result == expected
    exp_calls = [call.now(UTC)]
    assert mock_datetime.mock_calls == exp_calls
    exp_calls = [call()]
    assert mock_tools.mock_calls == exp_calls
    exp_calls = [call(datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_task.mock_calls == exp_calls
    exp_exchange = AgentExchange(
        reply=AgentReply(
            text="",
            reasoning="",
            tool_calls=(ToolCall(call_id="c1", name="broker__portfolio", arguments={}),),
            model="claude-opus-5-5",
            raw=(),
        ),
        results=(ToolResult(call_id="c1", content='{"cash": "500.00"}', is_error=False),),
    )
    exp_seen = [[exp_exchange] * rounds for rounds in range(16)]
    assert seen == exp_seen
    exp_calls = [
        call(
            helper_connection(),
            helper_system(),
            helper_task(),
            [exp_exchange] * 16,
            [helper_tool(McpServerName.BROKER, "portfolio")],
        )
    ] * 16
    assert mock_agent_reply.mock_calls == exp_calls
    exp_calls = []
    assert mock_stepped.mock_calls == exp_calls
    exp_calls = [
        call(
            helper_run(RunStatus.RUNNING, "", ""),
            ToolCall(call_id="c1", name="broker__portfolio", arguments={}),
            {"broker__portfolio": helper_tool(McpServerName.BROKER, "portfolio")},
        )
    ] * 16
    assert mock_answered.mock_calls == exp_calls


def test_tools() -> None:
    tested = helper_instance()
    with patch.object(
        McpClientBox,
        "tools",
        side_effect=[
            [helper_tool(McpServerName.SP500, "search")],
            [helper_tool(McpServerName.QUOTES, "quote"), helper_tool(McpServerName.QUOTES, "market")],
            [helper_tool(McpServerName.BROKER, "buy")],
        ],
    ) as mock_tools:
        result = tested.tools()
    expected = [
        helper_tool(McpServerName.SP500, "search"),
        helper_tool(McpServerName.QUOTES, "quote"),
        helper_tool(McpServerName.QUOTES, "market"),
        helper_tool(McpServerName.BROKER, "buy"),
    ]
    assert result == expected
    exp_calls = [call(McpServerName.SP500), call(McpServerName.QUOTES), call(McpServerName.BROKER)]
    assert mock_tools.mock_calls == exp_calls


def test_answered() -> None:
    tested = helper_instance()
    run = helper_run(RunStatus.RUNNING, "", "")
    tools = {"broker__buy": helper_tool(McpServerName.BROKER, "buy")}
    answer = ToolResult(call_id="c1", content='{"trade_id": 11}', is_error=False)
    with (
        patch(f"{MODULE}.time", wraps=time) as mock_time,
        patch.object(McpClientBox, "called", side_effect=[answer]) as mock_called,
        patch.object(AgentCommand, "stepped", side_effect=[helper_step(StepKind.TOOL, "")]) as mock_stepped,
    ):
        mock_time.perf_counter.side_effect = [2.0, 2.0625]
        result = tested.answered(
            run, ToolCall(call_id="c1", name="broker__buy", arguments={"symbol": "AAPL", "quantity": 1}), tools
        )
    expected = ToolResult(call_id="c1", content='{"trade_id": 11}', is_error=False)
    assert result == expected
    exp_calls = [call.perf_counter(), call.perf_counter()]
    assert mock_time.mock_calls == exp_calls
    exp_calls = [call(McpServerName.BROKER, "buy", {"symbol": "AAPL", "quantity": 1}, "c1", 4)]
    assert mock_called.mock_calls == exp_calls
    exp_calls = [
        call(
            helper_run(RunStatus.RUNNING, "", ""),
            StepKind.TOOL,
            "broker",
            "buy",
            {"symbol": "AAPL", "quantity": 1},
            '{"trade_id": 11}',
            False,
            62.5,
        )
    ]
    assert mock_stepped.mock_calls == exp_calls


def test_answered__unknown_tool() -> None:
    tested = helper_instance()
    run = helper_run(RunStatus.RUNNING, "", "")
    tools = {"broker__buy": helper_tool(McpServerName.BROKER, "buy")}
    with (
        patch.object(McpClientBox, "called", side_effect=[]) as mock_called,
        patch.object(AgentCommand, "stepped", side_effect=[helper_step(StepKind.TOOL, "")]) as mock_stepped,
    ):
        result = tested.answered(run, ToolCall(call_id="c1", name="broker__short", arguments={"symbol": "AAPL"}), tools)
    expected = ToolResult(call_id="c1", content="There is no tool named broker__short.", is_error=True)
    assert result == expected
    exp_calls = []
    assert mock_called.mock_calls == exp_calls
    exp_calls = [
        call(
            helper_run(RunStatus.RUNNING, "", ""),
            StepKind.TOOL,
            "",
            "broker__short",
            {"symbol": "AAPL"},
            "There is no tool named broker__short.",
            True,
            0.0,
        )
    ]
    assert mock_stepped.mock_calls == exp_calls


def test_answered__malformed_arguments() -> None:
    tested = helper_instance()
    run = helper_run(RunStatus.RUNNING, "", "")
    tools = {"broker__buy": helper_tool(McpServerName.BROKER, "buy")}
    with (
        patch.object(McpClientBox, "called", side_effect=[]) as mock_called,
        patch.object(AgentCommand, "stepped", side_effect=[helper_step(StepKind.TOOL, "")]) as mock_stepped,
    ):
        result = tested.answered(run, ToolCall(call_id="c1", name="broker__buy", arguments=None), tools)
    expected = ToolResult(call_id="c1", content="The arguments of this call are not a JSON object.", is_error=True)
    assert result == expected
    exp_calls = []
    assert mock_called.mock_calls == exp_calls
    exp_calls = [
        call(
            helper_run(RunStatus.RUNNING, "", ""),
            StepKind.TOOL,
            "broker",
            "buy",
            None,
            "The arguments of this call are not a JSON object.",
            True,
            0.0,
        )
    ]
    assert mock_stepped.mock_calls == exp_calls


def test_stepped() -> None:
    tested = helper_instance()
    with patch.object(
        AgentRunStore, "stepped", side_effect=[helper_step(StepKind.MODEL, "Held everything.")]
    ) as mock_stepped:
        result = tested.stepped(
            helper_run(RunStatus.RUNNING, "", ""), StepKind.MODEL, "", "", None, "Held everything.", False, 0.0
        )
    expected = helper_step(StepKind.MODEL, "Held everything.")
    assert result == expected
    exp_calls = [call(4, StepKind.MODEL, "", "", None, "Held everything.", False, 0.0)]
    assert mock_stepped.mock_calls == exp_calls


@pytest.mark.parametrize(
    "status, expected",
    [
        pytest.param(
            MarketStatus(
                is_open=True,
                now=datetime(2026, 10, 21, 11, 0, 42, 123, tzinfo=NEW_YORK),
                closes_at=datetime(2026, 10, 21, 16, 0, tzinfo=NEW_YORK),
                next_open=datetime(2026, 10, 22, 9, 30, tzinfo=NEW_YORK),
            ),
            "It is 2026-10-21T11:00-04:00 in New York. The market is open. Review the portfolio and act.",
            id="open",
        ),
        pytest.param(
            MarketStatus(
                is_open=False,
                now=datetime(2026, 10, 21, 18, 5, tzinfo=NEW_YORK),
                closes_at=None,
                next_open=datetime(2026, 10, 22, 9, 30, tzinfo=NEW_YORK),
            ),
            "It is 2026-10-21T18:05-04:00 in New York. The market is closed (orders will be refused). "
            "Review the portfolio and act.",
            id="closed",
        ),
    ],
)
def test_task(status: MarketStatus, expected: str) -> None:
    tested = helper_instance()
    with patch.object(QuoteCommand, "market", side_effect=[status]) as mock_market:
        result = tested.task(NOW)
    assert result == expected
    exp_calls = [call(datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_market.mock_calls == exp_calls


@pytest.mark.parametrize(
    "outcome, exp_messages",
    [
        pytest.param(
            Valuation(
                taken_at=NOW,
                cash=Decimal("100.00"),
                holdings_value=Decimal("400.0000"),
                total_value=Decimal("500.0000"),
            ),
            [],
            id="valued",
        ),
        pytest.param(
            AppException(404, "There is no portfolio: set BOOTSTRAP_ADMIN_EMAIL and restart."),
            ["[AGENT] not valued: There is no portfolio: set BOOTSTRAP_ADMIN_EMAIL and restart."],
            id="not-valued",
        ),
    ],
)
def test_valued(caplog: pytest.LogCaptureFixture, outcome: object, exp_messages: list[str]) -> None:
    tested = helper_instance()
    with (
        caplog.at_level(logging.WARNING, logger="mcp_stock_markets"),
        patch(f"{MODULE}.datetime", wraps=datetime) as mock_datetime,
        patch.object(BrokerCommand, "valued", side_effect=[outcome]) as mock_valued,
    ):
        mock_datetime.now.side_effect = [NOW]
        result = tested.valued()
    assert result is None
    assert caplog.messages == exp_messages
    exp_calls = [call.now(UTC)]
    assert mock_datetime.mock_calls == exp_calls
    exp_calls = [call(datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_valued.mock_calls == exp_calls


@pytest.mark.parametrize(
    "is_free, abandoned, expected, exp_abandoned",
    [
        pytest.param(True, [2], 2, [call("Interrupted: the app stopped during the run.")], id="free"),
        pytest.param(False, [], 0, [], id="another-color-runs"),
    ],
)
def test_abandoned(is_free: bool, abandoned: list[int], expected: int, exp_abandoned: list[object]) -> None:
    tested = helper_instance()
    with (
        patch.object(Database, "held", side_effect=[contextlib.nullcontext(is_free)]) as mock_held,
        patch.object(AgentRunStore, "abandoned", side_effect=abandoned) as mock_abandoned,
    ):
        result = tested.abandoned()
    assert result == expected
    exp_calls = [call(7_310_403)]
    assert mock_held.mock_calls == exp_calls
    assert mock_abandoned.mock_calls == exp_abandoned


def test_runs() -> None:
    tested = helper_instance()
    with patch.object(AgentRunStore, "runs", side_effect=[[helper_run(RunStatus.COMPLETED, "Held.", "")]]) as mock_runs:
        result = tested.runs()
    expected = [helper_run(RunStatus.COMPLETED, "Held.", "")]
    assert result == expected
    exp_calls = [call(50)]
    assert mock_runs.mock_calls == exp_calls


def test_run() -> None:
    tested = helper_instance()
    with (
        patch.object(AgentRunStore, "run", side_effect=[helper_run(RunStatus.COMPLETED, "Held.", "")]) as mock_run,
        patch.object(AgentRunStore, "steps", side_effect=[[helper_step(StepKind.MODEL, "Held.")]]) as mock_steps,
    ):
        result = tested.run(4)
    expected = (helper_run(RunStatus.COMPLETED, "Held.", ""), [helper_step(StepKind.MODEL, "Held.")])
    assert result == expected
    exp_calls = [call(4)]
    assert mock_run.mock_calls == exp_calls
    assert mock_steps.mock_calls == exp_calls


def test_run__not_found() -> None:
    tested = helper_instance()
    with (
        patch.object(AgentRunStore, "run", side_effect=[None]) as mock_run,
        patch.object(AgentRunStore, "steps", side_effect=[]) as mock_steps,
        pytest.raises(AppException) as exc_info,
    ):
        tested.run(99)
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (404, "This run does not exist.")
    assert result == expected
    exp_calls = [call(99)]
    assert mock_run.mock_calls == exp_calls
    exp_calls = []
    assert mock_steps.mock_calls == exp_calls


def test_catalog() -> None:
    """A server that does not answer is listed with why."""
    tested = helper_instance()
    with patch.object(
        McpClientBox,
        "tools",
        side_effect=[
            [helper_tool(McpServerName.SP500, "search")],
            AppException(503, "The MCP server quotes did not answer."),
            [],
        ],
    ) as mock_tools:
        result = tested.catalog()
    expected = [
        {
            "server": "sp500",
            "url": "http://127.0.0.1:8000/mcp/sp500/",
            "tools": [
                {
                    "server": "sp500",
                    "name": "search",
                    "description": "The search tool.",
                    "input_schema": {"type": "object", "properties": {}},
                }
            ],
        },
        {
            "server": "quotes",
            "url": "http://127.0.0.1:8000/mcp/quotes/",
            "error": "The MCP server quotes did not answer.",
        },
        {"server": "broker", "url": "http://127.0.0.1:8000/mcp/broker/", "tools": []},
    ]
    assert result == expected
    exp_calls = [call(McpServerName.SP500), call(McpServerName.QUOTES), call(McpServerName.BROKER)]
    assert mock_tools.mock_calls == exp_calls
