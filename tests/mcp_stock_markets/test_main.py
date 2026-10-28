from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import socket
import threading
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import call, patch
from urllib.parse import urlsplit

import httpx2
import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from mcp_stock_markets.commands import agent_command, routine_command
from mcp_stock_markets.commands.agent_command import AgentCommand
from mcp_stock_markets.commands.broker_command import BrokerCommand
from mcp_stock_markets.commands.owner_command import OwnerCommand
from mcp_stock_markets.handlers import broker_mcp_server, market_router, portfolio_router, quotes_mcp_server
from mcp_stock_markets.handlers.mcp_server_handler import McpServerHandler
from mcp_stock_markets.handlers.sp500_mcp_server import Sp500McpServer
from mcp_stock_markets.libraries import web_box
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.libraries.job_queue import JobQueue
from mcp_stock_markets.libraries.settings_loader import SettingsLoader
from mcp_stock_markets.libraries.ticker import Ticker
from mcp_stock_markets.main import AppFactory, app
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.portfolio import Portfolio
from mcp_stock_markets.structures.settings import Settings
from mcp_stock_markets.structures.user_account import UserAccount
from tests.conftest import helper_database
from tests.support.fake_google_finance import FakeGoogleFinance
from tests.support.fake_openai_chat import FakeOpenAiChat
from tests.support.fake_smtp import FakeSMTP
from tests.support.fake_wikipedia import FakeWikipedia
from tests.support.frozen_datetime import FrozenDatetime

# A Wednesday, 11:00 in New York: the market is open.
MARKET_OPEN = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
# A Saturday: the market is closed.
MARKET_CLOSED = datetime(2026, 10, 24, 15, 0, tzinfo=UTC)
# Every module that asks the time of the market.
CLOCKED = [agent_command, routine_command, broker_mcp_server, quotes_mcp_server, market_router, portfolio_router]


def helper_settings(mcp_base_url: str) -> Settings:
    return Settings(
        environment="dev",
        database_url=os.environ["TEST_DATABASE_URL"],
        app_version="2026-10-21.1",
        build_time="20261021-120000Z",
        app_commit="5ca1ab1e",
        app_base_url="http://testserver",
        data_key="Zm9yLXRlc3RzLW9ubHktZm9yLXRlc3RzLW9ubHktMzI=",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="relay-user",
        smtp_password="relay-secret",
        email_from="trader@example.com",
        bootstrap_admin_email="boss@example.com",
        starting_budget=Decimal("500.00"),
        max_companies=5,
        alpaca_key_id="",
        alpaca_secret_key="",
        agent_interval_minutes=30,
        mcp_base_url=mcp_base_url,
        mcp_token="mcp-token",
    )


@contextmanager
def helper_internet(hosts: dict[str, Any]) -> Iterator[None]:
    """The vendors' fakes behind one urlopen, each answering its own host:
    Google, Wikipedia and the language model are reached through the same
    function, so one of them alone cannot stand in for it."""

    def opened(request: urllib.request.Request, timeout: float) -> Any:
        return hosts[urlsplit(request.full_url).hostname or ""](request, timeout=timeout)

    with patch.object(web_box.urllib.request, "urlopen", new=opened):
        yield


def helper_free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@contextmanager
def helper_served(built: FastAPI, port: int) -> Iterator[httpx2.Client]:
    """The app on a real port, lifespan on: the agent is an MCP client of its
    own servers over HTTP, which the in-process test client cannot carry."""
    server = uvicorn.Server(uvicorn.Config(built, host="127.0.0.1", port=port, log_level="warning", lifespan="on"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    waiter = threading.Event()
    while not server.started:
        waiter.wait(0.02)
    try:
        with httpx2.Client(base_url=f"http://127.0.0.1:{port}", headers=helper_origin(), timeout=10) as client:
            yield client
    finally:
        server.should_exit = True
        thread.join(10)


def helper_origin() -> dict[str, str]:
    """What the browser sends: the APP_BASE_URL's origin, whichever port serves."""
    return {"Origin": "http://testserver"}


def helper_sent(fake: FakeSMTP, count: int) -> list[tuple[Any, ...]]:
    """The messages the job thread handed to the relay, once `count` of them
    are there or after five seconds: the thread is real, so the test waits."""
    waiter = threading.Event()
    for _ in range(500):
        result = [entry for entry in fake.calls if entry[0] == "send_message"]
        if len(result) >= count:
            return result
        waiter.wait(0.01)
    return [entry for entry in fake.calls if entry[0] == "send_message"]


def helper_token(message: tuple[Any, ...]) -> str:
    found = re.search(r"/auth/link\?token=([A-Za-z0-9_-]+)", str(message[4]))
    return "" if found is None else found.group(1)


def helper_masked(message: tuple[Any, ...]) -> tuple[Any, ...]:
    """The message with its random token replaced, so the rest is asserted whole."""
    return (*message[:4], re.sub(r"token=[A-Za-z0-9_-]+", "token=<token>", str(message[4])))


def helper_unstamped(text: str) -> str:
    """The database's own times (rows stamped by `now()`, not the frozen
    clock) replaced, so the rest is asserted whole."""
    return re.sub(
        r'"(created_at|executed_at|started_at|finished_at)": "[^"]+"',
        r'"\1": "<time>"',
        text,
    )


def helper_until(probe: Any, is_done: Any) -> Any:
    """`probe()` again until `is_done(answer)`, for ten seconds at most: the
    agent runs on its own thread."""
    waiter = threading.Event()
    result = probe()
    for _ in range(500):
        if is_done(result):
            return result
        waiter.wait(0.02)
        result = probe()
    return result


def helper_routes(built: FastAPI) -> list[tuple[str, tuple[str, ...]]]:
    """Every route the application answers, with the routers it includes
    opened up: FastAPI keeps an included router as one entry of its own."""
    result: list[tuple[str, tuple[str, ...]]] = []
    for entry in built.routes:
        routes = entry.original_router.routes if hasattr(entry, "original_router") else [entry]
        result.extend(
            (route.path, tuple(sorted(getattr(route, "methods", None) or ())))  # type: ignore[attr-defined]
            for route in routes
        )
    return result


def helper_request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


def helper_owner() -> UserAccount:
    return UserAccount(user_id=1, email="boss@example.com", display_name="boss", is_disabled=False)


def helper_wikipedia() -> FakeWikipedia:
    return FakeWikipedia([FakeWikipedia.page(FakeWikipedia.members(460))])


def test_app() -> None:
    result = isinstance(app, FastAPI)
    assert result is True


def test_create() -> None:
    tested = AppFactory()
    settings = helper_settings("http://127.0.0.1:8000")
    built = FastAPI()
    with (
        patch.object(SettingsLoader, "loaded", side_effect=[settings]) as mock_loaded,
        patch.object(AppFactory, "created", side_effect=[built]) as mock_created,
    ):
        result = tested.create()
    assert result is built
    exp_calls = [call()]
    assert mock_loaded.mock_calls == exp_calls
    exp_calls = [call(settings)]
    assert mock_created.mock_calls == exp_calls


def test_created() -> None:
    tested = AppFactory()
    built = tested.created(helper_settings("http://127.0.0.1:8000"))
    result = sorted(helper_routes(built))
    expected = [
        ("/", ("GET", "HEAD")),
        ("/api/account", ("GET",)),
        ("/api/agent/runs", ("GET",)),
        ("/api/agent/runs", ("POST",)),
        ("/api/agent/runs/{run_id}", ("GET",)),
        ("/api/agent/servers", ("GET",)),
        ("/api/auth/link", ("POST",)),
        ("/api/auth/link-request", ("POST",)),
        ("/api/auth/sign-out", ("POST",)),
        ("/api/companies", ("GET",)),
        ("/api/companies/refresh", ("POST",)),
        ("/api/llm/connections", ("GET",)),
        ("/api/llm/connections", ("POST",)),
        ("/api/llm/connections/{connection_id}", ("DELETE",)),
        ("/api/llm/connections/{connection_id}", ("PUT",)),
        ("/api/llm/connections/{connection_id}/health", ("GET",)),
        ("/api/llm/models", ("POST",)),
        ("/api/llm/routing", ("PUT",)),
        ("/api/market", ("GET",)),
        ("/api/portfolio", ("GET",)),
        ("/api/trades", ("GET",)),
        ("/api/universe", ("POST",)),
        ("/api/universe/{symbol}", ("DELETE",)),
        ("/api/valuations", ("GET",)),
        ("/auth/link", ("GET", "HEAD")),
        ("/healthz", ("GET", "HEAD")),
        ("/mcp/broker", ()),
        ("/mcp/quotes", ()),
        ("/mcp/sp500", ()),
        ("/static", ()),
        ("/sw.js", ("GET",)),
    ]
    assert result == expected
    exp_flags = (None, None, None)
    assert (built.docs_url, built.redoc_url, built.openapi_url) == exp_flags


@pytest.mark.database
def test_created__the_shell_its_health_and_the_closed_mcp_door() -> None:
    """The wiring, unmocked: lifespan on, the schema, the owner's account and
    portfolio in place, the S&P 500 read by the scheduler's first tick; an
    MCP request without the token is refused."""
    database = helper_database()
    tested = AppFactory()
    wikipedia = helper_wikipedia()
    with (
        FrozenDatetime.installed(MARKET_CLOSED, CLOCKED),
        helper_internet({"en.wikipedia.org": wikipedia}),
        TestClient(tested.created(helper_settings("http://127.0.0.1:8000"))) as client,
    ):
        health = client.get("/healthz")
        home = client.get("/")
        mcp = client.post("/mcp/broker/", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        companies = helper_until(
            lambda: database.row("SELECT count(*) AS companies FROM companies", ()),
            lambda row: row is not None and row["companies"] > 0,
        )
    portfolio = database.row("SELECT user_id, starting_budget, cash FROM portfolios", ())
    result = [
        (health.status_code, health.json(), health.headers["x-frame-options"]),
        (home.status_code, home.headers["content-type"], home.headers["cache-control"]),
        (mcp.status_code, mcp.json(), mcp.headers["www-authenticate"]),
        companies,
        portfolio,
        len(wikipedia.requests),
    ]
    expected = [
        (200, {"ok": True, "version": "2026-10-21.1", "commit": "5ca1ab1e"}, "DENY"),
        (200, "text/html; charset=utf-8", "no-cache"),
        (401, {"detail": "This MCP server needs the app's bearer token."}, "Bearer"),
        {"companies": 460},
        {"user_id": 1, "starting_budget": Decimal("500.0000"), "cash": Decimal("500.0000")},
        1,
    ]
    assert result == expected


@pytest.mark.database
def test_created__sign_in_flow() -> None:
    """Sign in end to end: the owner asks for a link, the job thread mails
    it through the relay, the link opens a session once."""
    helper_database()
    tested = AppFactory()
    fake = FakeSMTP()
    with (
        fake.installed(),
        FrozenDatetime.installed(MARKET_CLOSED, CLOCKED),
        helper_internet({"en.wikipedia.org": helper_wikipedia()}),
        TestClient(tested.created(helper_settings("http://127.0.0.1:8000"))) as client,
    ):
        before = client.get("/api/account")
        requested = client.post("/api/auth/link-request", json={"email": "Boss@Example.com "}, headers=helper_origin())
        message = helper_sent(fake, 1)[0]
        redeemed = client.post("/api/auth/link", json={"token": helper_token(message)}, headers=helper_origin())
        me = client.get("/api/account")
        reused = client.post("/api/auth/link", json={"token": helper_token(message)}, headers=helper_origin())
        signed_out = client.post("/api/auth/sign-out", headers=helper_origin())
        after = client.get("/api/portfolio")
    result = [
        (before.status_code, before.json()),
        (requested.status_code, requested.json()),
        (redeemed.status_code, redeemed.json()),
        (me.status_code, me.json()),
        (reused.status_code, reused.json()),
        signed_out.status_code,
        (after.status_code, after.json()),
    ]
    expected = [
        (401, {"detail": "Please sign in."}),
        (200, {"message": "If this address has access, a sign-in link is on its way."}),
        (200, {"ok": True}),
        (200, {"user_id": 1, "email": "boss@example.com", "display_name": "boss", "is_disabled": False}),
        (401, {"detail": "This sign-in link has expired or was already used. Ask for a new one."}),
        200,
        (401, {"detail": "Please sign in."}),
    ]
    assert result == expected
    exp_message = (
        "send_message",
        "trader@example.com",
        "boss@example.com",
        "Your MCP Stock Markets sign-in link",
        "Hello boss,\n"
        "\n"
        "To sign in to MCP Stock Markets, open this link:\n"
        "http://testserver/auth/link?token=<token>\n"
        "\n"
        "It works once, for 15 minutes.\n"
        "If you did not ask for it, ignore this message.\n",
    )
    assert helper_masked(message) == exp_message


@pytest.mark.database
def test_created__a_request_from_another_site_is_refused() -> None:
    helper_database()
    tested = AppFactory()
    with (
        FrozenDatetime.installed(MARKET_CLOSED, CLOCKED),
        helper_internet({"en.wikipedia.org": helper_wikipedia()}),
        TestClient(tested.created(helper_settings("http://127.0.0.1:8000"))) as client,
    ):
        response = client.post(
            "/api/auth/link-request", json={"email": "boss@example.com"}, headers={"Origin": "https://evil.example.com"}
        )
    result = (response.status_code, response.json())
    expected = (403, {"detail": "This request did not come from MCP Stock Markets."})
    assert result == expected


def helper_trader() -> FakeOpenAiChat:
    """A model that reads the portfolio, prices ADBE, buys one share, then sums up."""
    return FakeOpenAiChat(
        [
            FakeOpenAiChat.completion(
                FakeOpenAiChat.assistant(
                    "Looking at the account first.",
                    [
                        FakeOpenAiChat.tool_call("call_1", "broker__get_portfolio", "{}"),
                        FakeOpenAiChat.tool_call("call_2", "quotes__get_quote", '{"symbol": "ADBE"}'),
                    ],
                ),
                "tool_calls",
                "trader-1",
            ),
            FakeOpenAiChat.completion(
                FakeOpenAiChat.assistant(
                    None,
                    [
                        FakeOpenAiChat.tool_call(
                            "call_3", "broker__buy", '{"symbol": "ADBE", "quantity": 1, "reason": "Cheap today."}'
                        )
                    ],
                ),
                "tool_calls",
                "trader-1",
            ),
            FakeOpenAiChat.completion(
                FakeOpenAiChat.assistant("Bought one ADBE share at $400.00; $100.00 of cash left.", []),
                "stop",
                "trader-1",
            ),
        ]
    )


@pytest.mark.database
def test_created__the_agent_trades_through_the_mcp_servers() -> None:
    """The demo end to end, with nothing mocked between our own classes: the
    owner signs in, chooses a company, sets up a model and presses Run now;
    the agent lists the three servers' tools over MCP, the model calls
    them, the broker buys at Google's price; the run, the trade, the
    portfolio and its valuation are all there to see."""
    database = helper_database()
    port = helper_free_port()
    tested = AppFactory()
    smtp = FakeSMTP()
    google = FakeGoogleFinance(
        [FakeGoogleFinance.quote_entry("ADBE", "NASDAQ", "Adobe Inc.", 400.0, int(MARKET_OPEN.timestamp()) - 60)]
    )
    trader = helper_trader()
    built = tested.created(helper_settings(f"http://127.0.0.1:{port}"))
    with (
        smtp.installed(),
        FrozenDatetime.installed(MARKET_OPEN, CLOCKED),
        helper_internet({"en.wikipedia.org": helper_wikipedia(), "www.google.com": google, "llm.example.com": trader}),
        helper_served(built, port) as client,
    ):
        helper_until(
            lambda: database.row("SELECT count(*) AS companies FROM companies", ()),
            lambda row: row is not None and row["companies"] > 0,
        )
        client.post("/api/auth/link-request", json={"email": "boss@example.com"})
        client.post("/api/auth/link", json={"token": helper_token(helper_sent(smtp, 1)[0])})
        chosen = client.post("/api/universe", json={"symbol": "adbe"})
        connection = client.post(
            "/api/llm/connections",
            json={"name": "Local", "kind": "openai", "base_url": "https://llm.example.com/v1", "model": "trader-1"},
        )
        client.put("/api/llm/routing", json={"agent": connection.json()["connection_id"]})
        started = client.post("/api/agent/runs")
        run = helper_until(
            # The run is stamped by the database's clock, not the frozen one.
            lambda: client.get(
                "/api/agent/runs", params={"start": "2000-01-01T00:00:00Z", "end": "2100-01-01T00:00:00Z"}
            ).json()["runs"],
            lambda runs: len(runs) == 1 and runs[0]["status"] != "running",
        )
        detail = client.get(f"/api/agent/runs/{run[0]['run_id']}").json()
        trades = client.get("/api/trades").json()
        portfolio = client.get("/api/portfolio").json()
        servers = client.get("/api/agent/servers").json()
    steps = [
        (step["kind"], step["server"], step["tool"], step["arguments"], step["is_error"], step["content"])
        for step in detail["steps"]
    ]
    result = [
        (chosen.status_code, chosen.json()),
        started.json(),
        (detail["run"]["status"], detail["run"]["turns"], detail["run"]["model"], detail["run"]["summary"]),
        [step[:5] for step in steps],
        helper_unstamped(steps[2][5]),
        steps[4][5],
    ]
    expected = [
        (
            200,
            {
                "symbol": "ADBE",
                "name": "Adobe Inc.",
                "sector": "Information Technology",
                "sub_industry": "Application Software",
                "headquarters": "San Jose, California",
                "exchange": "NASDAQ",
            },
        ),
        {"ok": True, "detail": "The agent will start in a moment."},
        ("completed", 3, "trader-1", "Bought one ADBE share at $400.00; $100.00 of cash left."),
        [
            ("model", "", "", None, False),
            ("tool", "broker", "get_portfolio", {}, False),
            ("tool", "quotes", "get_quote", {"symbol": "ADBE"}, False),
            ("tool", "broker", "buy", {"symbol": "ADBE", "quantity": 1, "reason": "Cheap today."}, False),
            ("model", "", "", None, False),
        ],
        '{"symbol": "ADBE", "price": "400.0000", "currency": "USD", "as_of": "2026-10-21T14:59:00+00:00", '
        '"source": "google_finance", "fetched_at": "2026-10-21T15:00:00+00:00", "age_seconds": 60}',
        "Bought one ADBE share at $400.00; $100.00 of cash left.",
    ]
    assert result == expected
    exp_trade = {
        "symbol": "ADBE",
        "side": "buy",
        "quantity": 1,
        "price": "400.0000",
        "amount": "400.0000",
        "cash_after": "100.0000",
        "quote_source": "google_finance",
        "quote_as_of": "2026-10-21T14:59:00+00:00",
        "agent_run_id": run[0]["run_id"],
        "reason": "Cheap today.",
    }
    assert [{key: trade[key] for key in exp_trade} for trade in trades["trades"]] == [exp_trade]
    exp_portfolio = (
        "100.0000",
        "400.0000",
        "500.0000",
        ["ADBE"],
        [{"symbol": "ADBE", "quantity": 1, "cost": "400.0000"}],
    )
    assert (
        portfolio["portfolio"]["cash"],
        portfolio["holdings_value"],
        portfolio["total_value"],
        portfolio["universe"],
        [position["holding"] for position in portfolio["positions"]],
    ) == exp_portfolio
    exp_tools = {
        "sp500": ["list_sectors", "search_companies", "get_company"],
        "quotes": ["get_market_status", "get_quote", "get_daily_history"],
        "broker": ["get_portfolio", "get_transactions", "buy", "sell"],
    }
    assert {server["server"]: [tool["name"] for tool in server["tools"]] for server in servers["servers"]} == exp_tools
    # The model saw every tool of the three servers, and each round its own answers and the servers'.
    exp_requests = [
        (10, ["system", "user"]),
        (10, ["system", "user", "assistant", "tool", "tool"]),
        (10, ["system", "user", "assistant", "tool", "tool", "assistant", "tool"]),
    ]
    assert [
        (len(request[3]["tools"]), [message["role"] for message in request[3]["messages"]])
        for request in trader.requests
    ] == exp_requests
    # One price read from Google: the broker priced the order on the minute-old quote it had just read.
    assert len(google.requests) == 1


def test_lifespan(caplog: pytest.LogCaptureFixture) -> None:
    """Start: migrate, set up the owner and their portfolio, close the runs a
    stopped process left open, start the MCP servers' session managers, the
    job threads and the scheduler. Stop: the scheduler and the jobs drain
    before the database closes."""
    tested = AppFactory
    settings = helper_settings("http://127.0.0.1:8000")
    database = Database("postgresql://u:p@h/d")
    order: list[str] = []
    portfolio = Portfolio(1, 1, Decimal("500"), Decimal("500"), MARKET_OPEN)
    mcp_server = Sp500McpServer("mcp-token", object())  # type: ignore[arg-type]
    mcp_server.app()
    with (
        patch.object(Database, "migrated", side_effect=[(1,)]) as mock_migrated,
        patch.object(OwnerCommand, "owner", side_effect=[helper_owner()]) as mock_owner,
        patch.object(BrokerCommand, "opened", side_effect=lambda owner: (order.append("opened"), portfolio)[1]),
        patch.object(AgentCommand, "abandoned", side_effect=lambda: (order.append("abandoned"), 0)[1]),
        patch.object(JobQueue, "started", side_effect=lambda: order.append("started")) as mock_started,
        patch.object(Ticker, "started", side_effect=lambda: order.append("ticking")) as mock_ticking,
        patch.object(Ticker, "stopped", side_effect=lambda: order.append("ticked")) as mock_ticked,
        patch.object(JobQueue, "stopped", side_effect=lambda: order.append("stopped")) as mock_stopped,
        patch.object(Database, "closed", side_effect=lambda: order.append("database")) as mock_closed,
        caplog.at_level(logging.INFO, logger="mcp_stock_markets"),
    ):
        lifespan = tested.lifespan(
            settings,
            database,
            OwnerCommand.__new__(OwnerCommand),
            BrokerCommand.__new__(BrokerCommand),
            AgentCommand.__new__(AgentCommand),
            [mcp_server],
            [JobQueue.__new__(JobQueue), JobQueue.__new__(JobQueue)],
            Ticker.__new__(Ticker),
        )

        async def scenario() -> None:
            async with lifespan(FastAPI()):
                order.append("serving")

        asyncio.run(scenario())
    result = order
    expected = [
        "opened",
        "abandoned",
        "started",
        "started",
        "ticking",
        "serving",
        "ticked",
        "stopped",
        "stopped",
        "database",
    ]
    assert result == expected
    exp_calls = [call()]
    assert mock_migrated.mock_calls == exp_calls
    assert mock_ticking.mock_calls == exp_calls
    assert mock_ticked.mock_calls == exp_calls
    assert mock_closed.mock_calls == exp_calls
    exp_calls = [call("boss@example.com")]
    assert mock_owner.mock_calls == exp_calls
    exp_calls = [call(), call()]
    assert mock_started.mock_calls == exp_calls
    assert mock_stopped.mock_calls == exp_calls
    exp_messages = ["[DATABASE] migrations applied: (1,)"]
    assert [record.getMessage() for record in caplog.records] == exp_messages


def test_lifespan__nothing_to_migrate_and_no_owner(caplog: pytest.LogCaptureFixture) -> None:
    """Silent when the schema is current; without an owner there is no portfolio to open."""
    tested = AppFactory
    database = Database("postgresql://u:p@h/d")
    servers: list[McpServerHandler] = []
    with (
        patch.object(Database, "migrated", side_effect=[()]),
        patch.object(OwnerCommand, "owner", side_effect=[None]),
        patch.object(BrokerCommand, "opened", side_effect=[]) as mock_opened,
        patch.object(AgentCommand, "abandoned", side_effect=[0]),
        patch.object(JobQueue, "started", side_effect=[None]),
        patch.object(Ticker, "started", side_effect=[None]),
        patch.object(Ticker, "stopped", side_effect=[None]),
        patch.object(JobQueue, "stopped", side_effect=[None]),
        patch.object(Database, "closed", side_effect=[None]),
        caplog.at_level(logging.INFO, logger="mcp_stock_markets"),
    ):
        lifespan = tested.lifespan(
            helper_settings("http://127.0.0.1:8000"),
            database,
            OwnerCommand.__new__(OwnerCommand),
            BrokerCommand.__new__(BrokerCommand),
            AgentCommand.__new__(AgentCommand),
            servers,
            [JobQueue.__new__(JobQueue)],
            Ticker.__new__(Ticker),
        )

        async def scenario() -> None:
            async with lifespan(FastAPI()):
                pass

        asyncio.run(scenario())
    result = ([record.getMessage() for record in caplog.records], mock_opened.mock_calls)
    expected: tuple[list[str], list[Any]] = ([], [])
    assert result == expected


def test_app_exception_handler() -> None:
    tested = AppFactory
    response = asyncio.run(tested.app_exception_handler(helper_request(), AppException(409, "Already there.")))
    result = (response.status_code, json.loads(response.body))
    expected = (409, {"detail": "Already there."})
    assert result == expected


def test_app_exception_handler__anything_else_is_raised_again() -> None:
    tested = AppFactory
    with pytest.raises(ValueError) as exc_info:
        asyncio.run(tested.app_exception_handler(helper_request(), ValueError("not ours")))
    result = str(exc_info.value)
    expected = "not ours"
    assert result == expected
