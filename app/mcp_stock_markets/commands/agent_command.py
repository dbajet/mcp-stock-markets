from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from mcp_stock_markets.commands.broker_command import BrokerCommand
from mcp_stock_markets.commands.quote_command import QuoteCommand
from mcp_stock_markets.constants.agent_constants import AgentConstants
from mcp_stock_markets.constants.constants import Constants
from mcp_stock_markets.constants.mcp_server_name import McpServerName
from mcp_stock_markets.constants.run_status import RunStatus
from mcp_stock_markets.constants.run_trigger import RunTrigger
from mcp_stock_markets.constants.step_kind import StepKind
from mcp_stock_markets.libraries.agent_run_store import AgentRunStore
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.libraries.job_queue import JobQueue
from mcp_stock_markets.libraries.llm_gateway import LlmGateway
from mcp_stock_markets.libraries.mcp_client_box import McpClientBox
from mcp_stock_markets.structures.agent_exchange import AgentExchange
from mcp_stock_markets.structures.agent_run import AgentRun
from mcp_stock_markets.structures.agent_step import AgentStep
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.llm_connection import LlmConnection
from mcp_stock_markets.structures.settings import Settings
from mcp_stock_markets.structures.tool_call import ToolCall
from mcp_stock_markets.structures.tool_result import ToolResult
from mcp_stock_markets.structures.tool_spec import ToolSpec


class AgentCommand:
    """The trading agent: a language model that acts only through the MCP
    servers' tools.

    A run lists the tools of every server (`tools/list`), hands them to
    the model with its instructions, then loops: the model answers, each
    tool it calls is sent to its server (`tools/call`), the answers go back
    to the model, until it ends with a summary or runs out of rounds. Every
    step is recorded as it happens — the run's transcript is the demo.

    Runs happen on the agent's own thread (a JobQueue), one at a time across
    both colors (an advisory lock): the scheduler's while the market is open,
    and the owner's Run now. A run that cannot take the lock is dropped, not
    queued: another is already looking at the same portfolio."""

    def __init__(
        self,
        settings: Settings,
        database: Database,
        store: AgentRunStore,
        gateway: LlmGateway,
        mcp: McpClientBox,
        quotes: QuoteCommand,
        broker: BrokerCommand,
        jobs: JobQueue,
    ) -> None:
        self._interval = timedelta(minutes=settings.agent_interval_minutes)
        self._database = database
        self._store = store
        self._gateway = gateway
        self._mcp = mcp
        self._quotes = quotes
        self._broker = broker
        self._jobs = jobs

    def queued(self, trigger: RunTrigger) -> None:
        """Refused at once without a model, rather than recorded as a failed run."""
        self._gateway.agent_connection()
        self._jobs.queued(self.performed, (trigger,))

    def performed(self, trigger: RunTrigger) -> None:
        """The run as a job: the queue wants no answer."""
        self.ran(trigger)

    def is_due(self, now: datetime) -> bool:
        last = self._store.last_started(RunTrigger.SCHEDULE)
        return last is None or now - last >= self._interval

    def ran(self, trigger: RunTrigger) -> AgentRun | None:
        """One run, or None when another holds the lock, or a scheduled run
        is no longer due (one queued behind a long Run now)."""
        with self._database.held(AgentConstants.run_lock_key) as is_free:
            if not is_free:
                logging.getLogger(Constants.logger_name).info("[AGENT] a run is in progress elsewhere")
                return None
            if trigger is RunTrigger.SCHEDULE and not self.is_due(datetime.now(UTC)):
                return None
            connection = self._gateway.agent_connection()
            run = self._store.started(trigger, connection.name, connection.model)
            # Finished whatever happens: an unexpected error (the job queue logs
            # and reports it) must not leave the run "running" on the page.
            turns, status, summary, error = 0, RunStatus.FAILED, "", "The run stopped on an unexpected error."
            try:
                turns, status, summary = self.conversed(run, connection)
                error = ""
            except AppException as failure:
                error = failure.message
            finally:
                self._store.finished(run.run_id, status, turns, summary, error)
            self.valued()
            return self._store.run(run.run_id)

    def conversed(self, run: AgentRun, connection: LlmConnection) -> tuple[int, RunStatus, str]:
        """The rounds of the run: how many, how it ended, and its summary."""
        tools = {tool.qualified_name(): tool for tool in self.tools()}
        system = "\n".join(AgentConstants.instructions)
        task = self.task(datetime.now(UTC))
        exchanges: list[AgentExchange] = []
        for turn in range(1, AgentConstants.max_turns + 1):
            reply = self._gateway.agent_reply(connection, system, task, exchanges, list(tools.values()))
            if reply.reasoning:
                self.stepped(run, StepKind.THINKING, "", "", None, reply.reasoning, False, 0.0)
            if reply.text:
                self.stepped(run, StepKind.MODEL, "", "", None, reply.text, False, 0.0)
            if not reply.tool_calls:
                return turn, RunStatus.COMPLETED, reply.text
            results = tuple(self.answered(run, call, tools) for call in reply.tool_calls)
            # The run's own conversation, rebuilt each round from these exchanges.
            exchanges.append(AgentExchange(reply=reply, results=results))
        return (
            AgentConstants.max_turns,
            RunStatus.EXHAUSTED,
            f"Stopped after {AgentConstants.max_turns} rounds without a final summary.",
        )

    def tools(self) -> list[ToolSpec]:
        return [tool for server in McpServerName for tool in self._mcp.tools(server)]

    def answered(self, run: AgentRun, call: ToolCall, tools: dict[str, ToolSpec]) -> ToolResult:
        """The server's answer to one call, recorded; a call the servers
        cannot take is answered with why, so the model can correct itself."""
        if (tool := tools.get(call.name)) is None:
            result = ToolResult(call_id=call.call_id, content=f"There is no tool named {call.name}.", is_error=True)
            self.stepped(run, StepKind.TOOL, "", call.name, call.arguments, result.content, True, 0.0)
            return result
        if call.arguments is None:
            result = ToolResult(call_id=call.call_id, content=AgentConstants.malformed_arguments, is_error=True)
            self.stepped(run, StepKind.TOOL, tool.server.value, tool.name, None, result.content, True, 0.0)
            return result
        started = time.perf_counter()
        result = self._mcp.called(tool.server, tool.name, call.arguments, call.call_id, run.run_id)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        self.stepped(
            run,
            StepKind.TOOL,
            tool.server.value,
            tool.name,
            call.arguments,
            result.content,
            result.is_error,
            elapsed_ms,
        )
        return result

    def stepped(
        self,
        run: AgentRun,
        kind: StepKind,
        server: str,
        tool: str,
        arguments: dict[str, Any] | None,
        content: str,
        is_error: bool,
        elapsed_ms: float,
    ) -> AgentStep:
        return self._store.stepped(run.run_id, kind, server, tool, arguments, content, is_error, elapsed_ms)

    def task(self, now: datetime) -> str:
        status = self._quotes.market(now)
        market = AgentConstants.market_open if status.is_open else AgentConstants.market_closed
        return f"It is {status.now.isoformat(timespec='minutes')} in New York. The market is {market}. Review the portfolio and act."

    def valued(self) -> None:
        """The portfolio's value after the run, a point of its chart; a
        failure to value it does not fail the run."""
        try:
            self._broker.valued(datetime.now(UTC))
        except AppException as error:
            logging.getLogger(Constants.logger_name).warning("[AGENT] not valued: %s", error.message)

    def abandoned(self) -> int:
        """At startup: runs a stopped process left `running`, marked failed —
        unless another color is running one now (it holds the lock)."""
        with self._database.held(AgentConstants.run_lock_key) as is_free:
            if not is_free:
                return 0
            return self._store.abandoned("Interrupted: the app stopped during the run.")

    def runs(self, start: datetime, end: datetime) -> list[AgentRun]:
        """The runs started in a range of moments: the page turns the owner's
        days, in their own time zone, into those moments."""
        if start.tzinfo is None or end.tzinfo is None:
            raise AppException(400, AgentConstants.runs_range_naive)
        if end < start:
            raise AppException(400, AgentConstants.runs_range_backwards)
        return self._store.runs(start, end, AgentConstants.runs_page)

    def run(self, run_id: int) -> tuple[AgentRun, list[AgentStep]]:
        if (result := self._store.run(run_id)) is None:
            raise AppException(404, AgentConstants.run_not_found)
        return result, self._store.steps(run_id)

    def catalog(self) -> list[dict[str, Any]]:
        """Each MCP server, its address and its tools as `tools/list` gives
        them — asked over MCP, as the agent asks — or why it did not answer."""
        result: list[dict[str, Any]] = []
        for server in McpServerName:
            entry: dict[str, Any] = {"server": server.value, "url": self._mcp.url(server)}
            try:
                entry["tools"] = [tool.to_dict() for tool in self._mcp.tools(server)]
            except AppException as error:
                entry["error"] = error.message
            result.append(entry)
        return result
