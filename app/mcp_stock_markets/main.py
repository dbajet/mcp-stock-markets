from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from mcp_stock_markets.commands.agent_command import AgentCommand
from mcp_stock_markets.commands.broker_command import BrokerCommand
from mcp_stock_markets.commands.company_command import CompanyCommand
from mcp_stock_markets.commands.health_command import HealthCommand
from mcp_stock_markets.commands.llm_connection_command import LlmConnectionCommand
from mcp_stock_markets.commands.owner_command import OwnerCommand
from mcp_stock_markets.commands.quote_command import QuoteCommand
from mcp_stock_markets.commands.routine_command import RoutineCommand
from mcp_stock_markets.commands.session_command import SessionCommand
from mcp_stock_markets.commands.sign_in_command import SignInCommand
from mcp_stock_markets.constants.agent_constants import AgentConstants
from mcp_stock_markets.constants.constants import Constants
from mcp_stock_markets.constants.mcp_constants import McpConstants
from mcp_stock_markets.handlers.account_router import AccountRouter
from mcp_stock_markets.handlers.agent_router import AgentRouter
from mcp_stock_markets.handlers.api_router import ApiRouter
from mcp_stock_markets.handlers.auth_router import AuthRouter
from mcp_stock_markets.handlers.broker_mcp_server import BrokerMcpServer
from mcp_stock_markets.handlers.llm_connection_router import LlmConnectionRouter
from mcp_stock_markets.handlers.market_router import MarketRouter
from mcp_stock_markets.handlers.mcp_server_handler import McpServerHandler
from mcp_stock_markets.handlers.portfolio_router import PortfolioRouter
from mcp_stock_markets.handlers.quotes_mcp_server import QuotesMcpServer
from mcp_stock_markets.handlers.session_guard import SessionGuard
from mcp_stock_markets.handlers.sp500_mcp_server import Sp500McpServer
from mcp_stock_markets.libraries.agent_run_store import AgentRunStore
from mcp_stock_markets.libraries.alerter import Alerter
from mcp_stock_markets.libraries.alpaca_box import AlpacaBox
from mcp_stock_markets.libraries.blind_index import BlindIndex
from mcp_stock_markets.libraries.claude_box import ClaudeBox
from mcp_stock_markets.libraries.company_store import CompanyStore
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.libraries.email_box import EmailBox
from mcp_stock_markets.libraries.email_composer import EmailComposer
from mcp_stock_markets.libraries.google_finance_box import GoogleFinanceBox
from mcp_stock_markets.libraries.job_queue import JobQueue
from mcp_stock_markets.libraries.llm_connection_store import LlmConnectionStore
from mcp_stock_markets.libraries.llm_gateway import LlmGateway
from mcp_stock_markets.libraries.magic_link_store import MagicLinkStore
from mcp_stock_markets.libraries.market_clock import MarketClock
from mcp_stock_markets.libraries.mcp_client_box import McpClientBox
from mcp_stock_markets.libraries.openai_chat_box import OpenAiChatBox
from mcp_stock_markets.libraries.page_renderer import PageRenderer
from mcp_stock_markets.libraries.portfolio_store import PortfolioStore
from mcp_stock_markets.libraries.quote_store import QuoteStore
from mcp_stock_markets.libraries.secret_sealer import SecretSealer
from mcp_stock_markets.libraries.security_headers import SecurityHeaders
from mcp_stock_markets.libraries.session_store import SessionStore
from mcp_stock_markets.libraries.settings_loader import SettingsLoader
from mcp_stock_markets.libraries.ticker import Ticker
from mcp_stock_markets.libraries.user_store import UserStore
from mcp_stock_markets.libraries.web_box import WebBox
from mcp_stock_markets.libraries.wikipedia_box import WikipediaBox
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.settings import Settings


class AppFactory:
    """The composition root: the one place that builds the boxes and
    the commands and hands them to each other."""

    def create(self) -> FastAPI:
        return self.created(SettingsLoader.of_process().loaded())

    def created(self, settings: Settings) -> FastAPI:
        database = Database(settings.database_url)
        email_box = EmailBox(settings)
        alerter = Alerter(email_box, settings.bootstrap_admin_email)
        mail_jobs = JobQueue("mail", alerter)
        # Its own thread: a run of several minutes must not hold back a sign-in email.
        agent_jobs = JobQueue("agent", alerter)
        sealer = SecretSealer(settings.data_key)
        users = UserStore(database, sealer, BlindIndex(settings.data_key))
        sessions = SessionCommand(users, SessionStore(database))
        sign_in = SignInCommand(
            settings, users, MagicLinkStore(database), sessions, EmailComposer(), email_box, mail_jobs
        )
        web = WebBox()
        company_store = CompanyStore(database)
        companies = CompanyCommand(settings, company_store, WikipediaBox(web))
        quotes = QuoteCommand(
            QuoteStore(database),
            company_store,
            GoogleFinanceBox(web),
            AlpacaBox(web, settings.alpaca_key_id, settings.alpaca_secret_key),
            MarketClock(),
        )
        broker = BrokerCommand(settings, database, PortfolioStore(database), company_store, quotes)
        connection_store = LlmConnectionStore(database, sealer)
        gateway = LlmGateway(connection_store, OpenAiChatBox(), ClaudeBox())
        agent = AgentCommand(
            settings, database, AgentRunStore(database), gateway, McpClientBox(settings), quotes, broker, agent_jobs
        )
        routine = RoutineCommand(database, companies, quotes, broker, agent)
        ticker = Ticker("routine", AgentConstants.scheduler_tick_seconds, routine.ticked, alerter)
        mcp_servers: list[McpServerHandler] = [
            Sp500McpServer(settings.mcp_token, companies),
            QuotesMcpServer(settings.mcp_token, quotes),
            BrokerMcpServer(settings.mcp_token, broker, companies),
        ]
        guard = SessionGuard(settings, sessions)
        static_directory = Path(__file__).parent / Constants.static_directory
        routers = [
            AuthRouter(guard, sign_in, sessions).router(),
            AccountRouter(guard).router(),
            PortfolioRouter(guard, broker).router(),
            MarketRouter(guard, companies, quotes).router(),
            AgentRouter(guard, agent).router(),
            LlmConnectionRouter(guard, LlmConnectionCommand(connection_store, gateway)).router(),
            ApiRouter(HealthCommand(settings, database), PageRenderer(static_directory, settings)).router(),
        ]
        result = FastAPI(
            lifespan=self.lifespan(
                settings,
                database,
                OwnerCommand(users),
                broker,
                agent,
                mcp_servers,
                [mail_jobs, agent_jobs],
                ticker,
            ),
            docs_url=None,
            redoc_url=None,
            openapi_url=None,
        )
        result.add_middleware(SecurityHeaders)
        result.add_exception_handler(AppException, self.app_exception_handler)
        for router in routers:
            result.include_router(router)
        for mcp_server in mcp_servers:
            result.mount(f"{McpConstants.mount_prefix}/{mcp_server.name.value}", mcp_server.app())
        result.mount(Constants.static_mount, StaticFiles(directory=static_directory), name="static")
        return result

    @classmethod
    def lifespan(
        cls,
        settings: Settings,
        database: Database,
        owners: OwnerCommand,
        broker: BrokerCommand,
        agent: AgentCommand,
        mcp_servers: list[McpServerHandler],
        job_queues: list[JobQueue],
        ticker: Ticker,
    ) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
        """What a color does when it starts and when it stops."""

        @asynccontextmanager
        async def result(_: FastAPI) -> AsyncIterator[None]:
            # The schema is brought up to date before the first request.
            applied = database.migrated()
            if applied:
                logging.getLogger(Constants.logger_name).info("[DATABASE] migrations applied: %s", applied)
            if (owner := owners.owner(settings.bootstrap_admin_email)) is not None:
                broker.opened(owner)
            agent.abandoned()
            # A mounted app's lifespan is not run by FastAPI: each MCP server's
            # session manager is started here, and stopped after the jobs.
            async with AsyncExitStack() as stack:
                for mcp_server in mcp_servers:
                    await stack.enter_async_context(mcp_server.server.session_manager.run())
                for queue in job_queues:
                    queue.started()
                ticker.started()
                yield
                # The tick in progress and the queued jobs (a sign-in email, a run)
                # finish before the color stops; the MCP servers stop after them.
                ticker.stopped()
                for queue in job_queues:
                    queue.stopped()
            database.closed()

        return result

    @classmethod
    async def app_exception_handler(cls, _: Request, exception: Exception) -> JSONResponse:
        # Starlette's handler signature takes any Exception; only AppException is registered here.
        if not isinstance(exception, AppException):
            raise exception
        return JSONResponse({"detail": exception.message}, status_code=exception.status_code)


# FastAPI needs a module-level ASGI callable for uvicorn discovery.
app = AppFactory().create()
