from __future__ import annotations

import contextlib
import threading
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import call, patch

import pytest

from mcp_stock_markets.commands.broker_command import BrokerCommand
from mcp_stock_markets.commands.quote_command import QuoteCommand
from mcp_stock_markets.constants.quote_source import QuoteSource
from mcp_stock_markets.constants.trade_side import TradeSide
from mcp_stock_markets.libraries.alpha_vantage_box import AlphaVantageBox
from mcp_stock_markets.libraries.company_store import CompanyStore
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.libraries.google_finance_box import GoogleFinanceBox
from mcp_stock_markets.libraries.market_clock import MarketClock
from mcp_stock_markets.libraries.portfolio_store import PortfolioStore
from mcp_stock_markets.libraries.quote_store import QuoteStore
from mcp_stock_markets.libraries.web_box import WebBox
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.holding import Holding
from mcp_stock_markets.structures.market_status import MarketStatus
from mcp_stock_markets.structures.portfolio import Portfolio
from mcp_stock_markets.structures.portfolio_view import PortfolioView
from mcp_stock_markets.structures.position import Position
from mcp_stock_markets.structures.quote import Quote
from mcp_stock_markets.structures.settings import Settings
from mcp_stock_markets.structures.trade import Trade
from mcp_stock_markets.structures.user_account import UserAccount
from mcp_stock_markets.structures.valuation import Valuation

NOW = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
NEW_YORK = timezone(timedelta(hours=-4))


def helper_settings() -> Settings:
    return Settings(
        environment="dev",
        database_url="postgresql://u:p@h/d",
        app_version="2026-10-21.1",
        build_time="20261021-120000Z",
        app_commit="abc",
        app_base_url="https://stocks.example.com",
        data_key="Zm9yLXRlc3RzLW9ubHktZm9yLXRlc3RzLW9ubHktMzI=",
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


def helper_parts() -> tuple[Database, PortfolioStore, CompanyStore, QuoteCommand]:
    database = Database("postgresql://u:p@h/d")
    companies = CompanyStore(database)
    quotes = QuoteCommand(
        QuoteStore(database),
        companies,
        GoogleFinanceBox(WebBox()),
        AlphaVantageBox(WebBox(), ""),
        MarketClock(),
    )
    return database, PortfolioStore(database), companies, quotes


def helper_instance() -> BrokerCommand:
    return BrokerCommand(helper_settings(), *helper_parts())


def helper_portfolio(cash: Decimal) -> Portfolio:
    return Portfolio(
        portfolio_id=7,
        user_id=1,
        starting_budget=Decimal("500.00"),
        cash=cash,
        created_at=datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
    )


def helper_quote(symbol: str, price: Decimal, as_of: datetime) -> Quote:
    return Quote(
        symbol=symbol,
        price=price,
        currency="USD",
        as_of=as_of,
        source=QuoteSource.GOOGLE_FINANCE,
        fetched_at=NOW,
    )


def helper_open() -> MarketStatus:
    return MarketStatus(
        is_open=True,
        now=datetime(2026, 10, 21, 11, 0, tzinfo=NEW_YORK),
        closes_at=datetime(2026, 10, 21, 16, 0, tzinfo=NEW_YORK),
        next_open=datetime(2026, 10, 22, 9, 30, tzinfo=NEW_YORK),
    )


def helper_closed() -> MarketStatus:
    return MarketStatus(
        is_open=False,
        now=datetime(2026, 10, 21, 18, 0, tzinfo=NEW_YORK),
        closes_at=None,
        next_open=datetime(2026, 10, 22, 9, 30, tzinfo=NEW_YORK),
    )


def helper_trade(side: TradeSide, quantity: int, amount: Decimal, cash_after: Decimal) -> Trade:
    return Trade(
        trade_id=11,
        executed_at=NOW,
        symbol="AAPL",
        side=side,
        quantity=quantity,
        price=Decimal("100.1234"),
        amount=amount,
        cash_after=cash_after,
        quote_source=QuoteSource.GOOGLE_FINANCE,
        quote_as_of=datetime(2026, 10, 21, 14, 58, tzinfo=UTC),
        agent_run_id=3,
        reason="Strong quarter.",
    )


def helper_transaction() -> contextlib.nullcontext[None]:
    return contextlib.nullcontext()


def test___init__() -> None:
    database, store, companies, quotes = helper_parts()
    tested = BrokerCommand(helper_settings(), database, store, companies, quotes)
    result = (tested._starting_budget, tested._database, tested._store, tested._companies, tested._quotes)
    expected = (Decimal("500.00"), database, store, companies, quotes)
    assert result == expected


def test_opened() -> None:
    tested = helper_instance()
    owner = UserAccount(user_id=1, email="owner@example.com", display_name="owner", is_disabled=False)
    with patch.object(PortfolioStore, "opened", side_effect=[helper_portfolio(Decimal("500.00"))]) as mock_opened:
        result = tested.opened(owner)
    expected = helper_portfolio(Decimal("500.00"))
    assert result == expected
    exp_calls = [call(1, Decimal("500.00"))]
    assert mock_opened.mock_calls == exp_calls


def test_portfolio_for() -> None:
    tested = helper_instance()
    with patch.object(PortfolioStore, "for_user", side_effect=[helper_portfolio(Decimal("500.00"))]) as mock_for_user:
        result = tested.portfolio_for(1)
    expected = helper_portfolio(Decimal("500.00"))
    assert result == expected
    exp_calls = [call(1)]
    assert mock_for_user.mock_calls == exp_calls


def test_portfolio_for__none() -> None:
    tested = helper_instance()
    with (
        patch.object(PortfolioStore, "for_user", side_effect=[None]) as mock_for_user,
        pytest.raises(AppException) as exc_info,
    ):
        tested.portfolio_for(2)
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (404, "There is no portfolio: set BOOTSTRAP_ADMIN_EMAIL and restart.")
    assert result == expected
    exp_calls = [call(2)]
    assert mock_for_user.mock_calls == exp_calls


def test_owner_portfolio() -> None:
    tested = helper_instance()
    with patch.object(PortfolioStore, "of_owner", side_effect=[helper_portfolio(Decimal("500.00"))]) as mock_of_owner:
        result = tested.owner_portfolio()
    expected = helper_portfolio(Decimal("500.00"))
    assert result == expected
    exp_calls = [call()]
    assert mock_of_owner.mock_calls == exp_calls


def test_owner_portfolio__none() -> None:
    tested = helper_instance()
    with (
        patch.object(PortfolioStore, "of_owner", side_effect=[None]) as mock_of_owner,
        pytest.raises(AppException) as exc_info,
    ):
        tested.owner_portfolio()
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (404, "There is no portfolio: set BOOTSTRAP_ADMIN_EMAIL and restart.")
    assert result == expected
    exp_calls = [call()]
    assert mock_of_owner.mock_calls == exp_calls


def test_view() -> None:
    tested = helper_instance()
    apple = Holding(symbol="AAPL", quantity=2, cost=Decimal("400.0000"))
    jpmorgan = Holding(symbol="JPM", quantity=1, cost=Decimal("250.5000"))
    apple_quote = helper_quote("AAPL", Decimal("210.12345"), datetime(2026, 10, 21, 14, 58, tzinfo=UTC))
    positions = [
        Position(holding=apple, quote=apple_quote, value=Decimal("420.24690")),
        Position(holding=jpmorgan, quote=None, value=Decimal("250.5000")),
    ]
    with (
        patch.object(PortfolioStore, "holdings", side_effect=[[apple, jpmorgan]]) as mock_holdings,
        patch.object(BrokerCommand, "positions", side_effect=[tuple(positions)]) as mock_positions,
        patch.object(CompanyStore, "universe", side_effect=[["AAPL", "MSFT"]]) as mock_universe,
    ):
        result = tested.view(helper_portfolio(Decimal("10.00")), NOW)
    expected = PortfolioView(
        portfolio=helper_portfolio(Decimal("10.00")),
        positions=(
            Position(
                holding=Holding(symbol="AAPL", quantity=2, cost=Decimal("400.0000")),
                quote=helper_quote("AAPL", Decimal("210.12345"), datetime(2026, 10, 21, 14, 58, tzinfo=UTC)),
                value=Decimal("420.24690"),
            ),
            Position(
                holding=Holding(symbol="JPM", quantity=1, cost=Decimal("250.5000")),
                quote=None,
                value=Decimal("250.5000"),
            ),
        ),
        holdings_value=Decimal("670.7469"),
        total_value=Decimal("680.7469"),
        universe=("AAPL", "MSFT"),
    )
    assert result == expected
    exp_calls = [call(7)]
    assert mock_holdings.mock_calls == exp_calls
    exp_calls = [
        call(
            [
                Holding(symbol="AAPL", quantity=2, cost=Decimal("400.0000")),
                Holding(symbol="JPM", quantity=1, cost=Decimal("250.5000")),
            ],
            datetime(2026, 10, 21, 15, 0, tzinfo=UTC),
        )
    ]
    assert mock_positions.mock_calls == exp_calls
    exp_calls = [call()]
    assert mock_universe.mock_calls == exp_calls


def test_view__nothing_held() -> None:
    tested = helper_instance()
    with (
        patch.object(PortfolioStore, "holdings", side_effect=[[]]) as mock_holdings,
        patch.object(BrokerCommand, "positions", side_effect=[()]) as mock_positions,
        patch.object(CompanyStore, "universe", side_effect=[[]]) as mock_universe,
    ):
        result = tested.view(helper_portfolio(Decimal("500.00")), NOW)
    expected = PortfolioView(
        portfolio=helper_portfolio(Decimal("500.00")),
        positions=(),
        holdings_value=Decimal("0.0000"),
        total_value=Decimal("500.0000"),
        universe=(),
    )
    assert result == expected
    exp_calls = [call(7)]
    assert mock_holdings.mock_calls == exp_calls
    exp_calls = [call([], datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_positions.mock_calls == exp_calls
    exp_calls = [call()]
    assert mock_universe.mock_calls == exp_calls


def test_positions() -> None:
    tested = helper_instance()
    apple = Holding(symbol="AAPL", quantity=2, cost=Decimal("400.0000"))
    jpmorgan = Holding(symbol="JPM", quantity=1, cost=Decimal("250.5000"))
    # Both lookups wait for each other: priced one after another, the first
    # would wait alone and break the barrier.
    both = threading.Barrier(2, timeout=5)
    priced = {
        "AAPL": Position(holding=apple, quote=None, value=Decimal("400.0000")),
        "JPM": Position(holding=jpmorgan, quote=None, value=Decimal("250.5000")),
    }

    def helper_priced(holding: Holding, now: datetime) -> Position:
        both.wait()
        return priced[holding.symbol]

    with patch.object(BrokerCommand, "position", side_effect=helper_priced) as mock_position:
        result = tested.positions([apple, jpmorgan], NOW)
    expected = (
        Position(
            holding=Holding(symbol="AAPL", quantity=2, cost=Decimal("400.0000")), quote=None, value=Decimal("400.0000")
        ),
        Position(
            holding=Holding(symbol="JPM", quantity=1, cost=Decimal("250.5000")), quote=None, value=Decimal("250.5000")
        ),
    )
    assert result == expected
    # The two threads call in either order.
    exp_calls = [
        call(Holding(symbol="AAPL", quantity=2, cost=Decimal("400.0000")), datetime(2026, 10, 21, 15, 0, tzinfo=UTC)),
        call(Holding(symbol="JPM", quantity=1, cost=Decimal("250.5000")), datetime(2026, 10, 21, 15, 0, tzinfo=UTC)),
    ]
    assert sorted(mock_position.mock_calls, key=lambda made: made.args[0].symbol) == exp_calls


def test_positions__nothing_held() -> None:
    tested = helper_instance()
    with patch.object(BrokerCommand, "position", side_effect=[]) as mock_position:
        result = tested.positions([], NOW)
    assert result == ()
    exp_calls = []
    assert mock_position.mock_calls == exp_calls


def test_position() -> None:
    tested = helper_instance()
    quote = helper_quote("AAPL", Decimal("210.5000"), datetime(2026, 10, 21, 14, 58, tzinfo=UTC))
    with (
        patch.object(QuoteCommand, "quote", side_effect=[quote]) as mock_quote,
        patch.object(QuoteCommand, "latest", side_effect=[]) as mock_latest,
    ):
        result = tested.position(Holding(symbol="AAPL", quantity=3, cost=Decimal("600.0000")), NOW)
    expected = Position(
        holding=Holding(symbol="AAPL", quantity=3, cost=Decimal("600.0000")),
        quote=helper_quote("AAPL", Decimal("210.5000"), datetime(2026, 10, 21, 14, 58, tzinfo=UTC)),
        value=Decimal("631.5000"),
    )
    assert result == expected
    exp_calls = [call("AAPL", datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_quote.mock_calls == exp_calls
    exp_calls = []
    assert mock_latest.mock_calls == exp_calls


def test_position__the_latest_quote_when_reading_fails() -> None:
    tested = helper_instance()
    latest = helper_quote("AAPL", Decimal("205.0000"), datetime(2026, 10, 20, 19, 59, tzinfo=UTC))
    with (
        patch.object(
            QuoteCommand, "quote", side_effect=[AppException(502, "No price could be fetched for AAPL right now.")]
        ) as mock_quote,
        patch.object(QuoteCommand, "latest", side_effect=[latest]) as mock_latest,
    ):
        result = tested.position(Holding(symbol="AAPL", quantity=3, cost=Decimal("600.0000")), NOW)
    expected = Position(
        holding=Holding(symbol="AAPL", quantity=3, cost=Decimal("600.0000")),
        quote=helper_quote("AAPL", Decimal("205.0000"), datetime(2026, 10, 20, 19, 59, tzinfo=UTC)),
        value=Decimal("615.0000"),
    )
    assert result == expected
    exp_calls = [call("AAPL", datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_quote.mock_calls == exp_calls
    exp_calls = [call("AAPL")]
    assert mock_latest.mock_calls == exp_calls


def test_position__at_cost_without_any_quote() -> None:
    tested = helper_instance()
    with (
        patch.object(
            QuoteCommand, "quote", side_effect=[AppException(502, "No price could be fetched for AAPL right now.")]
        ) as mock_quote,
        patch.object(QuoteCommand, "latest", side_effect=[None]) as mock_latest,
    ):
        result = tested.position(Holding(symbol="AAPL", quantity=3, cost=Decimal("600.0000")), NOW)
    expected = Position(
        holding=Holding(symbol="AAPL", quantity=3, cost=Decimal("600.0000")),
        quote=None,
        value=Decimal("600.0000"),
    )
    assert result == expected
    exp_calls = [call("AAPL", datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_quote.mock_calls == exp_calls
    exp_calls = [call("AAPL")]
    assert mock_latest.mock_calls == exp_calls


def test_bought() -> None:
    tested = helper_instance()
    trade = helper_trade(TradeSide.BUY, 2, Decimal("200.2468"), Decimal("299.7532"))
    with patch.object(BrokerCommand, "ordered", side_effect=[trade]) as mock_ordered:
        result = tested.bought("AAPL", 2, "Strong quarter.", 3, NOW)
    expected = helper_trade(TradeSide.BUY, 2, Decimal("200.2468"), Decimal("299.7532"))
    assert result == expected
    exp_calls = [call(TradeSide.BUY, "AAPL", 2, "Strong quarter.", 3, datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_ordered.mock_calls == exp_calls


def test_sold() -> None:
    tested = helper_instance()
    trade = helper_trade(TradeSide.SELL, 1, Decimal("100.1234"), Decimal("600.1234"))
    with patch.object(BrokerCommand, "ordered", side_effect=[trade]) as mock_ordered:
        result = tested.sold("AAPL", 1, "Taking profits.", None, NOW)
    expected = helper_trade(TradeSide.SELL, 1, Decimal("100.1234"), Decimal("600.1234"))
    assert result == expected
    exp_calls = [call(TradeSide.SELL, "AAPL", 1, "Taking profits.", None, datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_ordered.mock_calls == exp_calls


@pytest.mark.parametrize(
    "held, exp_after",
    [
        pytest.param(None, Holding(symbol="AAPL", quantity=3, cost=Decimal("300.3702")), id="first-shares"),
        pytest.param(
            Holding(symbol="AAPL", quantity=2, cost=Decimal("190.0000")),
            Holding(symbol="AAPL", quantity=5, cost=Decimal("490.3702")),
            id="more-shares",
        ),
    ],
)
def test_ordered(held: Holding | None, exp_after: Holding) -> None:
    """The cash is the locked row's; an amount equal to it is spent; the price
    is rounded to four places; a trade exactly 15 minutes old prices it."""
    tested = helper_instance()
    quote = helper_quote("AAPL", Decimal("100.12340"), datetime(2026, 10, 21, 14, 45, tzinfo=UTC))
    trade = helper_trade(TradeSide.BUY, 3, Decimal("300.3702"), Decimal("0.0000"))
    with (
        patch.object(QuoteCommand, "market", side_effect=[helper_open()]) as mock_market,
        patch.object(PortfolioStore, "of_owner", side_effect=[helper_portfolio(Decimal("1.00"))]) as mock_of_owner,
        patch.object(CompanyStore, "universe", side_effect=[["AAPL", "JPM"]]) as mock_universe,
        patch.object(PortfolioStore, "holding", side_effect=[held]) as mock_holding,
        patch.object(QuoteCommand, "quote", side_effect=[quote]) as mock_quote,
        patch.object(Database, "transaction", side_effect=[helper_transaction()]) as mock_transaction,
        patch.object(PortfolioStore, "locked", side_effect=[helper_portfolio(Decimal("300.3702"))]) as mock_locked,
        patch.object(PortfolioStore, "recorded", side_effect=[trade]) as mock_recorded,
    ):
        result = tested.ordered(TradeSide.BUY, " aapl ", 3, "  Strong quarter. ", 3, NOW)
    expected = helper_trade(TradeSide.BUY, 3, Decimal("300.3702"), Decimal("0.0000"))
    assert result == expected
    exp_calls = [call(datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_market.mock_calls == exp_calls
    exp_calls = [call()]
    assert mock_of_owner.mock_calls == exp_calls
    assert mock_universe.mock_calls == exp_calls
    assert mock_transaction.mock_calls == exp_calls
    exp_calls = [call(7, "AAPL")]
    assert mock_holding.mock_calls == exp_calls
    exp_calls = [call("AAPL", datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_quote.mock_calls == exp_calls
    exp_calls = [call(7)]
    assert mock_locked.mock_calls == exp_calls
    exp_calls = [
        call(
            helper_portfolio(Decimal("300.3702")),
            TradeSide.BUY,
            3,
            helper_quote("AAPL", Decimal("100.12340"), datetime(2026, 10, 21, 14, 45, tzinfo=UTC)),
            Decimal("300.3702"),
            exp_after,
            3,
            "Strong quarter.",
        )
    ]
    assert mock_recorded.mock_calls == exp_calls


@pytest.mark.parametrize(
    "quantity, exp_amount, exp_after",
    [
        pytest.param(1, Decimal("110.0000"), Holding(symbol="AAPL", quantity=2, cost=Decimal("200.0000")), id="part"),
        pytest.param(3, Decimal("330.0000"), None, id="all"),
    ],
)
def test_ordered__sell(quantity: int, exp_amount: Decimal, exp_after: Holding | None) -> None:
    """A sale needs no room in the market: a company out of it is still sold."""
    tested = helper_instance()
    held = Holding(symbol="AAPL", quantity=3, cost=Decimal("300.0000"))
    quote = helper_quote("AAPL", Decimal("110.0000"), datetime(2026, 10, 21, 14, 58, tzinfo=UTC))
    trade = helper_trade(TradeSide.SELL, quantity, Decimal("110.0000"), Decimal("110.0000"))
    with (
        patch.object(QuoteCommand, "market", side_effect=[helper_open()]) as mock_market,
        patch.object(PortfolioStore, "of_owner", side_effect=[helper_portfolio(Decimal("0.00"))]) as mock_of_owner,
        patch.object(CompanyStore, "universe", side_effect=[]) as mock_universe,
        patch.object(PortfolioStore, "holding", side_effect=[held, held]) as mock_holding,
        patch.object(QuoteCommand, "quote", side_effect=[quote]) as mock_quote,
        patch.object(Database, "transaction", side_effect=[helper_transaction()]) as mock_transaction,
        patch.object(PortfolioStore, "locked", side_effect=[helper_portfolio(Decimal("0.00"))]) as mock_locked,
        patch.object(PortfolioStore, "recorded", side_effect=[trade]) as mock_recorded,
    ):
        result = tested.ordered(TradeSide.SELL, "AAPL", quantity, "Taking profits.", None, NOW)
    expected = helper_trade(TradeSide.SELL, quantity, Decimal("110.0000"), Decimal("110.0000"))
    assert result == expected
    exp_calls = [call(datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_market.mock_calls == exp_calls
    exp_calls = [call()]
    assert mock_of_owner.mock_calls == exp_calls
    assert mock_transaction.mock_calls == exp_calls
    exp_calls = []
    assert mock_universe.mock_calls == exp_calls
    exp_calls = [call(7, "AAPL"), call(7, "AAPL")]
    assert mock_holding.mock_calls == exp_calls
    exp_calls = [call("AAPL", datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_quote.mock_calls == exp_calls
    exp_calls = [call(7)]
    assert mock_locked.mock_calls == exp_calls
    exp_calls = [
        call(
            helper_portfolio(Decimal("0.00")),
            TradeSide.SELL,
            quantity,
            helper_quote("AAPL", Decimal("110.0000"), datetime(2026, 10, 21, 14, 58, tzinfo=UTC)),
            exp_amount,
            exp_after,
            None,
            "Taking profits.",
        )
    ]
    assert mock_recorded.mock_calls == exp_calls


def test_ordered__refused_before_anything_is_read() -> None:
    """The order's own checks come first: no portfolio, no price is read."""
    tested = helper_instance()
    with (
        patch.object(QuoteCommand, "market", side_effect=[helper_closed()]) as mock_market,
        patch.object(PortfolioStore, "of_owner", side_effect=[]) as mock_of_owner,
        patch.object(QuoteCommand, "quote", side_effect=[]) as mock_quote,
        pytest.raises(AppException) as exc_info,
    ):
        tested.ordered(TradeSide.BUY, "AAPL", 1, "Strong quarter.", 3, NOW)
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (409, "The US market is closed: orders are taken again from 2026-10-22T09:30:00-04:00.")
    assert result == expected
    exp_calls = [call(datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_market.mock_calls == exp_calls
    exp_calls = []
    assert mock_of_owner.mock_calls == exp_calls
    assert mock_quote.mock_calls == exp_calls


@pytest.mark.parametrize(
    "universe, exp_message",
    [
        pytest.param(
            ["JPM", "MSFT"], "AAPL is not in the agent's market: only JPM, MSFT may be bought.", id="other-companies"
        ),
        pytest.param([], "AAPL is not in the agent's market: only none may be bought.", id="empty-market"),
    ],
)
def test_ordered__buy_only_in_the_market(universe: list[str], exp_message: str) -> None:
    tested = helper_instance()
    with (
        patch.object(QuoteCommand, "market", side_effect=[helper_open()]) as mock_market,
        patch.object(PortfolioStore, "of_owner", side_effect=[helper_portfolio(Decimal("500.00"))]) as mock_of_owner,
        patch.object(CompanyStore, "universe", side_effect=[universe]) as mock_universe,
        patch.object(QuoteCommand, "quote", side_effect=[]) as mock_quote,
        pytest.raises(AppException) as exc_info,
    ):
        tested.ordered(TradeSide.BUY, "aapl", 1, "Strong quarter.", 3, NOW)
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (403, exp_message)
    assert result == expected
    exp_calls = [call(datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_market.mock_calls == exp_calls
    exp_calls = [call()]
    assert mock_of_owner.mock_calls == exp_calls
    assert mock_universe.mock_calls == exp_calls
    exp_calls = []
    assert mock_quote.mock_calls == exp_calls


@pytest.mark.parametrize(
    "held, exp_message",
    [
        pytest.param(None, "The portfolio holds no AAPL.", id="not-held"),
        pytest.param(
            Holding(symbol="AAPL", quantity=2, cost=Decimal("200.0000")),
            "The portfolio holds 2 AAPL, fewer than the 3 to sell.",
            id="fewer-held",
        ),
    ],
)
def test_ordered__sell_only_what_is_held(held: Holding | None, exp_message: str) -> None:
    tested = helper_instance()
    with (
        patch.object(QuoteCommand, "market", side_effect=[helper_open()]) as mock_market,
        patch.object(PortfolioStore, "of_owner", side_effect=[helper_portfolio(Decimal("500.00"))]) as mock_of_owner,
        patch.object(PortfolioStore, "holding", side_effect=[held]) as mock_holding,
        patch.object(QuoteCommand, "quote", side_effect=[]) as mock_quote,
        pytest.raises(AppException) as exc_info,
    ):
        tested.ordered(TradeSide.SELL, "AAPL", 3, "Taking profits.", 3, NOW)
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (409, exp_message)
    assert result == expected
    exp_calls = [call(datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_market.mock_calls == exp_calls
    exp_calls = [call()]
    assert mock_of_owner.mock_calls == exp_calls
    exp_calls = [call(7, "AAPL")]
    assert mock_holding.mock_calls == exp_calls
    exp_calls = []
    assert mock_quote.mock_calls == exp_calls


def test_ordered__sold_meanwhile() -> None:
    """Held when the order came, gone when the row is locked: refused under the lock."""
    tested = helper_instance()
    held = Holding(symbol="AAPL", quantity=3, cost=Decimal("300.0000"))
    quote = helper_quote("AAPL", Decimal("110.0000"), datetime(2026, 10, 21, 14, 58, tzinfo=UTC))
    with (
        patch.object(QuoteCommand, "market", side_effect=[helper_open()]) as mock_market,
        patch.object(PortfolioStore, "of_owner", side_effect=[helper_portfolio(Decimal("0.00"))]) as mock_of_owner,
        patch.object(PortfolioStore, "holding", side_effect=[held, None]) as mock_holding,
        patch.object(QuoteCommand, "quote", side_effect=[quote]) as mock_quote,
        patch.object(Database, "transaction", side_effect=[helper_transaction()]) as mock_transaction,
        patch.object(PortfolioStore, "locked", side_effect=[helper_portfolio(Decimal("0.00"))]) as mock_locked,
        patch.object(PortfolioStore, "recorded", side_effect=[]) as mock_recorded,
        pytest.raises(AppException) as exc_info,
    ):
        tested.ordered(TradeSide.SELL, "AAPL", 3, "Taking profits.", 3, NOW)
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (409, "The portfolio holds no AAPL.")
    assert result == expected
    exp_calls = [call(datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_market.mock_calls == exp_calls
    exp_calls = [call()]
    assert mock_of_owner.mock_calls == exp_calls
    assert mock_transaction.mock_calls == exp_calls
    exp_calls = [call(7, "AAPL"), call(7, "AAPL")]
    assert mock_holding.mock_calls == exp_calls
    exp_calls = [call("AAPL", datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_quote.mock_calls == exp_calls
    exp_calls = [call(7)]
    assert mock_locked.mock_calls == exp_calls
    exp_calls = []
    assert mock_recorded.mock_calls == exp_calls


def test_ordered__stale_quote() -> None:
    tested = helper_instance()
    quote = helper_quote("AAPL", Decimal("100.0000"), datetime(2026, 10, 21, 14, 44, 59, 999999, tzinfo=UTC))
    with (
        patch.object(QuoteCommand, "market", side_effect=[helper_open()]) as mock_market,
        patch.object(PortfolioStore, "of_owner", side_effect=[helper_portfolio(Decimal("500.00"))]) as mock_of_owner,
        patch.object(CompanyStore, "universe", side_effect=[["AAPL"]]) as mock_universe,
        patch.object(QuoteCommand, "quote", side_effect=[quote]) as mock_quote,
        patch.object(Database, "transaction", side_effect=[]) as mock_transaction,
        pytest.raises(AppException) as exc_info,
    ):
        tested.ordered(TradeSide.BUY, "AAPL", 1, "Strong quarter.", 3, NOW)
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (
        409,
        "The latest trade of AAPL is from 2026-10-21T14:44:59.999999+00:00: too old to price an order.",
    )
    assert result == expected
    exp_calls = [call(datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_market.mock_calls == exp_calls
    exp_calls = [call()]
    assert mock_of_owner.mock_calls == exp_calls
    assert mock_universe.mock_calls == exp_calls
    exp_calls = [call("AAPL", datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_quote.mock_calls == exp_calls
    exp_calls = []
    assert mock_transaction.mock_calls == exp_calls


def test_ordered__not_enough_cash() -> None:
    """The cash checked is the locked row's, not the one read before the lock."""
    tested = helper_instance()
    quote = helper_quote("AAPL", Decimal("231.4567"), datetime(2026, 10, 21, 14, 58, tzinfo=UTC))
    with (
        patch.object(QuoteCommand, "market", side_effect=[helper_open()]) as mock_market,
        patch.object(PortfolioStore, "of_owner", side_effect=[helper_portfolio(Decimal("5000.00"))]) as mock_of_owner,
        patch.object(CompanyStore, "universe", side_effect=[["AAPL"]]) as mock_universe,
        patch.object(PortfolioStore, "holding", side_effect=[None]) as mock_holding,
        patch.object(QuoteCommand, "quote", side_effect=[quote]) as mock_quote,
        patch.object(Database, "transaction", side_effect=[helper_transaction()]) as mock_transaction,
        patch.object(PortfolioStore, "locked", side_effect=[helper_portfolio(Decimal("694.3700"))]) as mock_locked,
        patch.object(PortfolioStore, "recorded", side_effect=[]) as mock_recorded,
        pytest.raises(AppException) as exc_info,
    ):
        tested.ordered(TradeSide.BUY, "AAPL", 3, "Strong quarter.", 3, NOW)
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (409, "3 AAPL at 231.4567 costs 694.3701, more than the 694.3700 of cash.")
    assert result == expected
    exp_calls = [call(datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_market.mock_calls == exp_calls
    exp_calls = [call()]
    assert mock_of_owner.mock_calls == exp_calls
    assert mock_universe.mock_calls == exp_calls
    assert mock_transaction.mock_calls == exp_calls
    exp_calls = [call(7, "AAPL")]
    assert mock_holding.mock_calls == exp_calls
    exp_calls = [call("AAPL", datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_quote.mock_calls == exp_calls
    exp_calls = [call(7)]
    assert mock_locked.mock_calls == exp_calls
    exp_calls = []
    assert mock_recorded.mock_calls == exp_calls


@pytest.mark.parametrize(
    "quantity, reason",
    [
        pytest.param(1, "", id="one-share-no-reason"),
        pytest.param(10_000, "r" * 500, id="the-most-shares-longest-reason"),
        pytest.param(5, "  " + "r" * 500 + "  ", id="reason-trimmed-before-measured"),
    ],
)
def test_checked_order(quantity: int, reason: str) -> None:
    tested = helper_instance()
    with patch.object(QuoteCommand, "market", side_effect=[helper_open()]) as mock_market:
        result = tested.checked_order(quantity, reason, NOW)
    assert result is None
    exp_calls = [call(datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_market.mock_calls == exp_calls


@pytest.mark.parametrize(
    "quantity, reason, exp_message",
    [
        pytest.param(0, "", "Order a whole number of shares, from 1 to 10000.", id="no-shares"),
        pytest.param(-1, "", "Order a whole number of shares, from 1 to 10000.", id="negative"),
        pytest.param(10_001, "", "Order a whole number of shares, from 1 to 10000.", id="too-many"),
        pytest.param(1, "r" * 501, "Give a reason of at most 500 characters.", id="reason-too-long"),
    ],
)
def test_checked_order__invalid(quantity: int, reason: str, exp_message: str) -> None:
    tested = helper_instance()
    with (
        patch.object(QuoteCommand, "market", side_effect=[]) as mock_market,
        pytest.raises(AppException) as exc_info,
    ):
        tested.checked_order(quantity, reason, NOW)
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (400, exp_message)
    assert result == expected
    exp_calls = []
    assert mock_market.mock_calls == exp_calls


def test_checked_order__market_closed() -> None:
    tested = helper_instance()
    with (
        patch.object(QuoteCommand, "market", side_effect=[helper_closed()]) as mock_market,
        pytest.raises(AppException) as exc_info,
    ):
        tested.checked_order(1, "Strong quarter.", NOW)
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (409, "The US market is closed: orders are taken again from 2026-10-22T09:30:00-04:00.")
    assert result == expected
    exp_calls = [call(datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_market.mock_calls == exp_calls


@pytest.mark.parametrize(
    "quantity",
    [
        pytest.param(1, id="fewer"),
        pytest.param(3, id="all"),
    ],
)
def test_held(quantity: int) -> None:
    tested = helper_instance()
    result = tested.held(Holding(symbol="AAPL", quantity=3, cost=Decimal("300.0000")), "AAPL", quantity)
    expected = Holding(symbol="AAPL", quantity=3, cost=Decimal("300.0000"))
    assert result == expected


@pytest.mark.parametrize(
    "holding, exp_message",
    [
        pytest.param(None, "The portfolio holds no AAPL.", id="not-held"),
        pytest.param(
            Holding(symbol="AAPL", quantity=3, cost=Decimal("300.0000")),
            "The portfolio holds 3 AAPL, fewer than the 4 to sell.",
            id="fewer-held",
        ),
    ],
)
def test_held__refused(holding: Holding | None, exp_message: str) -> None:
    tested = helper_instance()
    with pytest.raises(AppException) as exc_info:
        tested.held(holding, "AAPL", 4)
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (409, exp_message)
    assert result == expected


@pytest.mark.parametrize(
    "holding, expected",
    [
        pytest.param(None, Holding(symbol="AAPL", quantity=2, cost=Decimal("200.2468")), id="first-shares"),
        pytest.param(
            Holding(symbol="AAPL", quantity=3, cost=Decimal("290.0001")),
            Holding(symbol="AAPL", quantity=5, cost=Decimal("490.2469")),
            id="more-shares",
        ),
    ],
)
def test_bought_holding(holding: Holding | None, expected: Holding) -> None:
    tested = helper_instance()
    result = tested.bought_holding(holding, "AAPL", 2, Decimal("200.2468"))
    assert result == expected


@pytest.mark.parametrize(
    "holding, quantity, expected",
    [
        pytest.param(
            Holding(symbol="AAPL", quantity=3, cost=Decimal("10.0000")),
            1,
            Holding(symbol="AAPL", quantity=2, cost=Decimal("6.6667")),
            id="proportional-cost-rounded",
        ),
        pytest.param(
            Holding(symbol="AAPL", quantity=2, cost=Decimal("0.0001")),
            1,
            Holding(symbol="AAPL", quantity=1, cost=Decimal("0.0000")),
            id="half-to-even-down",
        ),
        pytest.param(
            Holding(symbol="AAPL", quantity=2, cost=Decimal("0.0003")),
            1,
            Holding(symbol="AAPL", quantity=1, cost=Decimal("0.0002")),
            id="half-to-even-up",
        ),
        pytest.param(Holding(symbol="AAPL", quantity=3, cost=Decimal("10.0000")), 3, None, id="sold-out"),
    ],
)
def test_sold_holding(holding: Holding, quantity: int, expected: Holding | None) -> None:
    tested = helper_instance()
    result = tested.sold_holding(holding, quantity)
    assert result == expected


@pytest.mark.parametrize(
    "limit, exp_limit",
    [
        pytest.param(50, 50, id="as-asked"),
        pytest.param(0, 1, id="at-least-one"),
        pytest.param(500, 500, id="the-most"),
        pytest.param(501, 500, id="at-most-500"),
    ],
)
def test_trades(limit: int, exp_limit: int) -> None:
    tested = helper_instance()
    trade = helper_trade(TradeSide.BUY, 2, Decimal("200.2468"), Decimal("299.7532"))
    with patch.object(PortfolioStore, "trades", side_effect=[[trade]]) as mock_trades:
        result = tested.trades(helper_portfolio(Decimal("299.7532")), limit)
    expected = [helper_trade(TradeSide.BUY, 2, Decimal("200.2468"), Decimal("299.7532"))]
    assert result == expected
    exp_calls = [call(7, exp_limit)]
    assert mock_trades.mock_calls == exp_calls


def test_valuations() -> None:
    tested = helper_instance()
    valuation = Valuation(
        taken_at=NOW, cash=Decimal("100.00"), holdings_value=Decimal("400.0000"), total_value=Decimal("500.0000")
    )
    with patch.object(PortfolioStore, "valuations", side_effect=[[valuation]]) as mock_valuations:
        result = tested.valuations(helper_portfolio(Decimal("100.00")))
    expected = [
        Valuation(
            taken_at=datetime(2026, 10, 21, 15, 0, tzinfo=UTC),
            cash=Decimal("100.00"),
            holdings_value=Decimal("400.0000"),
            total_value=Decimal("500.0000"),
        )
    ]
    assert result == expected
    exp_calls = [call(7, 2000)]
    assert mock_valuations.mock_calls == exp_calls


def test_valued() -> None:
    tested = helper_instance()
    view = PortfolioView(
        portfolio=helper_portfolio(Decimal("100.00")),
        positions=(),
        holdings_value=Decimal("412.5000"),
        total_value=Decimal("512.5000"),
        universe=("AAPL",),
    )
    with (
        patch.object(PortfolioStore, "of_owner", side_effect=[helper_portfolio(Decimal("100.00"))]) as mock_of_owner,
        patch.object(BrokerCommand, "view", side_effect=[view]) as mock_view,
        patch.object(PortfolioStore, "valued", side_effect=[None]) as mock_valued,
    ):
        result = tested.valued(NOW)
    expected = Valuation(
        taken_at=datetime(2026, 10, 21, 15, 0, tzinfo=UTC),
        cash=Decimal("100.00"),
        holdings_value=Decimal("412.5000"),
        total_value=Decimal("512.5000"),
    )
    assert result == expected
    exp_calls = [call()]
    assert mock_of_owner.mock_calls == exp_calls
    exp_calls = [call(helper_portfolio(Decimal("100.00")), datetime(2026, 10, 21, 15, 0, tzinfo=UTC))]
    assert mock_view.mock_calls == exp_calls
    exp_calls = [
        call(
            7,
            Valuation(
                taken_at=datetime(2026, 10, 21, 15, 0, tzinfo=UTC),
                cash=Decimal("100.00"),
                holdings_value=Decimal("412.5000"),
                total_value=Decimal("512.5000"),
            ),
        )
    ]
    assert mock_valued.mock_calls == exp_calls


@pytest.mark.parametrize(
    "last",
    [
        pytest.param(datetime(2026, 10, 21, 14, 30, tzinfo=UTC), id="valued"),
        pytest.param(None, id="never-valued"),
    ],
)
def test_last_valued_at(last: datetime | None) -> None:
    tested = helper_instance()
    with (
        patch.object(PortfolioStore, "of_owner", side_effect=[helper_portfolio(Decimal("100.00"))]) as mock_of_owner,
        patch.object(PortfolioStore, "last_valued_at", side_effect=[last]) as mock_last_valued_at,
    ):
        result = tested.last_valued_at()
    expected = last
    assert result == expected
    exp_calls = [call()]
    assert mock_of_owner.mock_calls == exp_calls
    exp_calls = [call(7)]
    assert mock_last_valued_at.mock_calls == exp_calls
