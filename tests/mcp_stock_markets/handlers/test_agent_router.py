from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import call, patch

import pytest
from starlette.requests import Request

from mcp_stock_markets.commands.agent_command import AgentCommand
from mcp_stock_markets.commands.broker_command import BrokerCommand
from mcp_stock_markets.commands.quote_command import QuoteCommand
from mcp_stock_markets.commands.session_command import SessionCommand
from mcp_stock_markets.constants.run_status import RunStatus
from mcp_stock_markets.constants.run_trigger import RunTrigger
from mcp_stock_markets.constants.step_kind import StepKind
from mcp_stock_markets.handlers.agent_router import AgentRouter
from mcp_stock_markets.handlers.session_guard import SessionGuard
from mcp_stock_markets.libraries.agent_run_store import AgentRunStore
from mcp_stock_markets.libraries.alerter import Alerter
from mcp_stock_markets.libraries.alpha_vantage_box import AlphaVantageBox
from mcp_stock_markets.libraries.blind_index import BlindIndex
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
from mcp_stock_markets.libraries.session_store import SessionStore
from mcp_stock_markets.libraries.user_store import UserStore
from mcp_stock_markets.libraries.web_box import WebBox
from mcp_stock_markets.structures.agent_run import AgentRun
from mcp_stock_markets.structures.agent_step import AgentStep
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.settings import Settings
from mcp_stock_markets.structures.user_account import UserAccount

KEY = "Zm9yLXRlc3RzLW9ubHktZm9yLXRlc3RzLW9ubHktMzI="
START = datetime(2026, 10, 28, 7, 0, tzinfo=UTC)
END = datetime(2026, 10, 29, 7, 0, tzinfo=UTC)


def helper_parts() -> tuple[SessionGuard, AgentCommand]:
    settings = Settings(
        environment="dev",
        database_url="postgresql://u:p@h/d",
        app_version="v",
        build_time="b",
        app_commit="c",
        app_base_url="https://stocks.example.com",
        data_key=KEY,
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
    database = Database(settings.database_url)
    sealer = SecretSealer(KEY)
    users = UserStore(database, sealer, BlindIndex(KEY))
    guard = SessionGuard(settings, SessionCommand(users, SessionStore(database)))
    web = WebBox()
    company_store = CompanyStore(database)
    quotes = QuoteCommand(
        QuoteStore(database), company_store, GoogleFinanceBox(web), AlphaVantageBox(web, ""), MarketClock()
    )
    broker = BrokerCommand(settings, database, PortfolioStore(database), company_store, quotes)
    agent = AgentCommand(
        settings,
        database,
        AgentRunStore(database),
        LlmGateway(LlmConnectionStore(database, sealer), OpenAiChatBox(), ClaudeBox()),
        McpClientBox(settings),
        quotes,
        broker,
        JobQueue("agent", Alerter(EmailBox(settings), "")),
    )
    return guard, agent


def helper_tested() -> AgentRouter:
    return AgentRouter(*helper_parts())


def helper_user() -> UserAccount:
    return UserAccount(user_id=7, email="owner@example.com", display_name="Owner", is_disabled=False)


def helper_request(method: str, path: str) -> Request:
    return Request({"type": "http", "method": method, "path": path, "headers": []})


def helper_run(run_id: int) -> AgentRun:
    return AgentRun(
        run_id=run_id,
        trigger=RunTrigger.SCHEDULE,
        status=RunStatus.COMPLETED,
        started_at=datetime(2026, 10, 21, 14, 0, tzinfo=UTC),
        finished_at=datetime(2026, 10, 21, 14, 2, tzinfo=UTC),
        connection_name="Claude",
        model="claude-opus-5-5",
        turns=4,
        summary="Bought one share of MSFT.",
        error="",
    )


def helper_run_dict(run_id: int) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "trigger": "schedule",
        "status": "completed",
        "started_at": "2026-10-21T14:00:00+00:00",
        "finished_at": "2026-10-21T14:02:00+00:00",
        "connection_name": "Claude",
        "model": "claude-opus-5-5",
        "turns": 4,
        "summary": "Bought one share of MSFT.",
        "error": "",
    }


def helper_denied(work: Callable[[Request], object], request: Request) -> tuple[int, str, list[Any]]:
    """What a handler does for nobody signed in: the guard's refusal, before any command."""
    with (
        patch.object(SessionGuard, "user", side_effect=[AppException(401, "Please sign in.")]) as mock_user,
        pytest.raises(AppException) as exc_info,
    ):
        work(request)
    return exc_info.value.status_code, exc_info.value.message, mock_user.mock_calls


def test___init__() -> None:
    guard, agent = helper_parts()
    tested = AgentRouter(guard, agent)
    result = (tested._guard, tested._agent)
    expected = (guard, agent)
    assert result == expected


def test_router() -> None:
    tested = helper_tested()
    result = [(route.path, tuple(sorted(route.methods)), route.name) for route in tested.router().routes]  # type: ignore[attr-defined]
    expected = [
        ("/api/agent/runs", ("GET",), "runs"),
        ("/api/agent/runs", ("POST",), "started"),
        ("/api/agent/runs/{run_id}", ("GET",), "run"),
        ("/api/agent/servers", ("GET",), "servers"),
    ]
    assert result == expected


def test_runs() -> None:
    tested = helper_tested()
    request = helper_request("GET", "/api/agent/runs")
    with (
        patch.object(SessionGuard, "user", side_effect=[helper_user()]) as mock_user,
        patch.object(AgentCommand, "runs", side_effect=[[helper_run(2), helper_run(1)]]) as mock_runs,
    ):
        result = tested.runs(request, START, END)
    expected = {"runs": [helper_run_dict(2), helper_run_dict(1)], "limit": 1000}
    assert result == expected
    exp_calls = [call(request)]
    assert mock_user.mock_calls == exp_calls
    exp_calls = [call(datetime(2026, 10, 28, 7, 0, tzinfo=UTC), datetime(2026, 10, 29, 7, 0, tzinfo=UTC))]
    assert mock_runs.mock_calls == exp_calls


def test_runs__denied_without_a_session() -> None:
    tested = helper_tested()
    request = helper_request("GET", "/api/agent/runs")
    result = helper_denied(lambda req: tested.runs(req, START, END), request)
    expected = (401, "Please sign in.", [call(request)])
    assert result == expected


def test_started() -> None:
    tested = helper_tested()
    request = helper_request("POST", "/api/agent/runs")
    with (
        patch.object(SessionGuard, "user", side_effect=[helper_user()]) as mock_user,
        patch.object(AgentCommand, "queued", side_effect=[None]) as mock_queued,
    ):
        result = tested.started(request)
    expected = {"ok": True, "detail": "The agent will start in a moment."}
    assert result == expected
    exp_calls = [call(request)]
    assert mock_user.mock_calls == exp_calls
    exp_calls = [call(RunTrigger.MANUAL)]
    assert mock_queued.mock_calls == exp_calls


def test_started__no_model_is_refused() -> None:
    tested = helper_tested()
    request = helper_request("POST", "/api/agent/runs")
    error = AppException(409, "The agent needs a language model: choose one in Settings › Language models.")
    with (
        patch.object(SessionGuard, "user", side_effect=[helper_user()]) as mock_user,
        patch.object(AgentCommand, "queued", side_effect=[error]) as mock_queued,
        pytest.raises(AppException) as exc_info,
    ):
        tested.started(request)
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (409, "The agent needs a language model: choose one in Settings › Language models.")
    assert result == expected
    exp_calls = [call(request)]
    assert mock_user.mock_calls == exp_calls
    exp_calls = [call(RunTrigger.MANUAL)]
    assert mock_queued.mock_calls == exp_calls


def test_started__denied_without_a_session() -> None:
    tested = helper_tested()
    request = helper_request("POST", "/api/agent/runs")
    result = helper_denied(lambda req: tested.started(req), request)
    expected = (401, "Please sign in.", [call(request)])
    assert result == expected


def test_run() -> None:
    tested = helper_tested()
    request = helper_request("GET", "/api/agent/runs/3")
    step = AgentStep(
        step_id=11,
        run_id=3,
        position=1,
        kind=StepKind.TOOL,
        server="quotes",
        tool="get_quote",
        arguments={"symbol": "MSFT"},
        content='{"price": "512.2500"}',
        is_error=False,
        elapsed_ms=42.5,
        created_at=datetime(2026, 10, 21, 14, 1, tzinfo=UTC),
    )
    with (
        patch.object(SessionGuard, "user", side_effect=[helper_user()]) as mock_user,
        patch.object(AgentCommand, "run", side_effect=[(helper_run(3), [step])]) as mock_run,
    ):
        result = tested.run(request, 3)
    expected = {
        "run": helper_run_dict(3),
        "steps": [
            {
                "step_id": 11,
                "run_id": 3,
                "position": 1,
                "kind": "tool",
                "server": "quotes",
                "tool": "get_quote",
                "arguments": {"symbol": "MSFT"},
                "content": '{"price": "512.2500"}',
                "is_error": False,
                "elapsed_ms": 42.5,
                "created_at": "2026-10-21T14:01:00+00:00",
            }
        ],
    }
    assert result == expected
    exp_calls = [call(request)]
    assert mock_user.mock_calls == exp_calls
    exp_calls = [call(3)]
    assert mock_run.mock_calls == exp_calls


def test_run__denied_without_a_session() -> None:
    tested = helper_tested()
    request = helper_request("GET", "/api/agent/runs/3")
    result = helper_denied(lambda req: tested.run(req, 3), request)
    expected = (401, "Please sign in.", [call(request)])
    assert result == expected


def test_servers() -> None:
    tested = helper_tested()
    request = helper_request("GET", "/api/agent/servers")
    catalog = [
        {"server": "sp500", "url": "http://127.0.0.1:8000/mcp/sp500/", "tools": []},
        {
            "server": "quotes",
            "url": "http://127.0.0.1:8000/mcp/quotes/",
            "error": "The MCP server quotes did not answer.",
        },
    ]
    with (
        patch.object(SessionGuard, "user", side_effect=[helper_user()]) as mock_user,
        patch.object(AgentCommand, "catalog", side_effect=[catalog]) as mock_catalog,
    ):
        result = tested.servers(request)
    expected = {
        "servers": [
            {"server": "sp500", "url": "http://127.0.0.1:8000/mcp/sp500/", "tools": []},
            {
                "server": "quotes",
                "url": "http://127.0.0.1:8000/mcp/quotes/",
                "error": "The MCP server quotes did not answer.",
            },
        ]
    }
    assert result == expected
    exp_calls = [call(request)]
    assert mock_user.mock_calls == exp_calls
    exp_calls = [call()]
    assert mock_catalog.mock_calls == exp_calls


def test_servers__denied_without_a_session() -> None:
    tested = helper_tested()
    request = helper_request("GET", "/api/agent/servers")
    result = helper_denied(lambda req: tested.servers(req), request)
    expected = (401, "Please sign in.", [call(request)])
    assert result == expected
