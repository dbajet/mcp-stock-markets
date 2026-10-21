from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class _AgentConstants:
    # --- a run ------------------------------------------------------------------------
    # Rounds of "the model answers, its tool calls run": enough to read the
    # market, check a few prices and place a few orders; a model that has not
    # finished by then is stopped rather than left to spend.
    max_turns: int = 16
    # A tool's answer is cut to this many characters before the model reads it.
    max_tool_result_chars: int = 12_000
    # pg_try_advisory_lock key: one run at a time, across both colors.
    run_lock_key: int = 7_310_403
    # How often the scheduler wakes to see whether a run is due.
    scheduler_tick_seconds: float = 60.0
    runs_page: int = 50

    # --- the language model ----------------------------------------------------------
    # One model call; a run is many. Thinking counts against Claude's limit.
    turn_timeout_seconds: float = 180.0
    claude_max_tokens: int = 16000
    # Deciding what to trade is judgment, not a lookup: medium effort, the
    # default of Claude Opus 5.5, stated rather than left implicit.
    claude_effort: str = "medium"
    openai_max_tokens: int = 4000

    # --- what the model is told --------------------------------------------------------
    instructions: tuple[str, ...] = (
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
    )
    market_open: str = "open"
    market_closed: str = "closed (orders will be refused)"

    # --- messages ---------------------------------------------------------------------
    no_model: str = "The agent needs a language model: choose one in Settings › Language models."
    busy: str = "The agent is already running."
    queued: str = "The agent will start in a moment."
    run_not_found: str = "This run does not exist."
    malformed_arguments: str = "The arguments of this call are not a JSON object."


AgentConstants = _AgentConstants()
