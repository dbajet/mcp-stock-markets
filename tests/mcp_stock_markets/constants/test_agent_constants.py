from __future__ import annotations

import dataclasses

from mcp_stock_markets.constants.agent_constants import AgentConstants
from tests.conftest import is_dataclass


def test_class() -> None:
    tested = AgentConstants
    fields = {
        "max_turns": "int",
        "max_tool_result_chars": "int",
        "run_lock_key": "int",
        "scheduler_tick_seconds": "float",
        "runs_page": "int",
        "turn_timeout_seconds": "float",
        "claude_max_tokens": "int",
        "claude_effort": "str",
        "openai_max_tokens": "int",
        "instructions": "tuple[str, ...]",
        "market_open": "str",
        "market_closed": "str",
        "no_model": "str",
        "busy": "str",
        "queued": "str",
        "run_not_found": "str",
        "runs_range_naive": "str",
        "runs_range_backwards": "str",
        "malformed_arguments": "str",
    }
    assert is_dataclass(tested, fields)


def test_values() -> None:
    tested = AgentConstants
    result = dataclasses.asdict(tested)
    expected = {
        "max_turns": 16,
        "max_tool_result_chars": 12000,
        "run_lock_key": 7310403,
        "scheduler_tick_seconds": 60.0,
        "runs_page": 1000,
        "turn_timeout_seconds": 180.0,
        "claude_max_tokens": 16000,
        "claude_effort": "medium",
        "openai_max_tokens": 4000,
        "instructions": (
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
        ),
        "market_open": "open",
        "market_closed": "closed (orders will be refused)",
        "no_model": "The agent needs a language model: choose one in Settings › Language models.",
        "busy": "The agent is already running.",
        "queued": "The agent will start in a moment.",
        "run_not_found": "This run does not exist.",
        "runs_range_naive": "A date range needs a time zone, such as 2026-10-28T07:00:00Z.",
        "runs_range_backwards": "The range ends before it starts.",
        "malformed_arguments": "The arguments of this call are not a JSON object.",
    }
    assert result == expected
