from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from mcp_stock_markets.constants.quote_source import QuoteSource
from mcp_stock_markets.constants.trade_side import TradeSide
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.libraries.portfolio_store import PortfolioStore
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.holding import Holding
from mcp_stock_markets.structures.portfolio import Portfolio
from mcp_stock_markets.structures.quote import Quote
from mcp_stock_markets.structures.trade import Trade
from mcp_stock_markets.structures.valuation import Valuation
from tests.conftest import helper_database

CREATED = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
AS_OF = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)


def helper_users(database: Database, names: list[str]) -> None:
    for name in names:
        database.executed(
            "INSERT INTO users (email_sealed, email_hash, display_name) VALUES (%s, %s, %s)",
            (b"sealed", f"hash-{name}", name),
        )


def helper_portfolio(database: Database, user_id: int, cash: str) -> Portfolio:
    """A portfolio made the way the store makes it, dated for the test."""
    database.executed(
        "INSERT INTO portfolios (user_id, starting_budget, cash, created_at) VALUES (%s, %s, %s, %s)",
        (user_id, Decimal("500.0000"), Decimal(cash), CREATED),
    )
    return Portfolio.from_dict(
        database.returned(
            "SELECT id AS portfolio_id, user_id, starting_budget, cash, created_at FROM portfolios WHERE user_id = %s",
            (user_id,),
        )
    )


def helper_run(database: Database) -> int:
    row = database.returned(
        "INSERT INTO agent_runs (trigger, status, connection_name, model) VALUES (%s, %s, %s, %s) RETURNING id",
        ("manual", "running", "Local", "good"),
    )
    return int(row["id"])


def helper_quote(symbol: str, price: str) -> Quote:
    return Quote(
        symbol=symbol,
        price=Decimal(price),
        currency="USD",
        as_of=AS_OF,
        source=QuoteSource.GOOGLE_FINANCE,
        fetched_at=datetime(2026, 10, 21, 15, 1, tzinfo=UTC),
    )


def helper_state(database: Database) -> dict[str, Any]:
    """The cash, the holdings and the trades, as stored."""
    return {
        "cash": database.rows("SELECT id, cash FROM portfolios ORDER BY id", ()),
        "holdings": database.rows(
            "SELECT portfolio_id, symbol, quantity, cost FROM holdings ORDER BY portfolio_id, symbol", ()
        ),
        "trades": database.rows(
            "SELECT id, symbol, side, quantity, price, amount, cash_after, agent_run_id FROM trades ORDER BY id", ()
        ),
    }


def helper_is_recent(moment: datetime) -> bool:
    return abs(datetime.now(UTC) - moment) < timedelta(minutes=5)


def test___init__() -> None:
    database = Database("postgresql://u:p@h/d")
    tested = PortfolioStore(database)
    result = tested._database is database
    assert result is True


@pytest.mark.database
def test_opened() -> None:
    """Made with the budget as its cash the first time; found as it is later."""
    database = helper_database()
    helper_users(database, ["ada"])
    tested = PortfolioStore(database)
    first = tested.opened(1, Decimal("500.00"))
    database.executed("UPDATE portfolios SET cash = %s, created_at = %s", (Decimal("12.5"), CREATED))
    result = (first._replace(created_at=CREATED), tested.opened(1, Decimal("900.00")))
    expected = (
        Portfolio(1, 1, Decimal("500.0000"), Decimal("500.0000"), CREATED),
        Portfolio(1, 1, Decimal("500.0000"), Decimal("12.5000"), CREATED),
    )
    assert result == expected
    exp_recent = True
    assert helper_is_recent(first.created_at) is exp_recent


@pytest.mark.database
def test_for_user() -> None:
    database = helper_database()
    helper_users(database, ["ada", "bob"])
    helper_portfolio(database, 2, "420.00")
    tested = PortfolioStore(database)
    result = (tested.for_user(2), tested.for_user(1))
    expected = (Portfolio(1, 2, Decimal("500.0000"), Decimal("420.0000"), CREATED), None)
    assert result == expected


@pytest.mark.database
def test_of_owner() -> None:
    """The portfolio of the enabled account; none when every account is disabled."""
    database = helper_database()
    helper_users(database, ["ada", "bob"])
    helper_portfolio(database, 1, "100.00")
    helper_portfolio(database, 2, "200.00")
    tested = PortfolioStore(database)
    database.executed("UPDATE users SET disabled_at = now() WHERE id = %s", (1,))
    owner = tested.of_owner()
    database.executed("UPDATE users SET disabled_at = now() WHERE id = %s", (2,))
    result = (owner, tested.of_owner())
    expected = (Portfolio(2, 2, Decimal("500.0000"), Decimal("200.0000"), CREATED), None)
    assert result == expected


@pytest.mark.database
def test_locked() -> None:
    database = helper_database()
    helper_users(database, ["ada"])
    helper_portfolio(database, 1, "321.00")
    tested = PortfolioStore(database)
    with database.transaction() as connection:
        result = tested.locked(1)
        # The row is locked by this transaction until it ends.
        locks = connection.execute(
            "SELECT count(*) AS locks FROM pg_locks WHERE locktype = 'transactionid' AND pid = pg_backend_pid()"
        ).fetchone()
    expected = Portfolio(1, 1, Decimal("500.0000"), Decimal("321.0000"), CREATED)
    assert result == expected
    exp_locks = {"locks": 1}
    assert locks == exp_locks


@pytest.mark.database
def test_locked__an_unknown_portfolio() -> None:
    database = helper_database()
    tested = PortfolioStore(database)
    with pytest.raises(AppException) as exc_info:
        tested.locked(7)
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (500, "The database returned nothing.")
    assert result == expected


@pytest.mark.database
def test_holdings() -> None:
    database = helper_database()
    helper_users(database, ["ada", "bob"])
    helper_portfolio(database, 1, "100.00")
    helper_portfolio(database, 2, "100.00")
    for portfolio_id, symbol, quantity, cost in ((1, "MMM", 2, "300.00"), (1, "AAPL", 1, "343.99"), (2, "AOS", 3, "9")):
        database.executed(
            "INSERT INTO holdings (portfolio_id, symbol, quantity, cost) VALUES (%s, %s, %s, %s)",
            (portfolio_id, symbol, quantity, Decimal(cost)),
        )
    tested = PortfolioStore(database)
    result = (tested.holdings(1), tested.holdings(3))
    expected = (
        [Holding("AAPL", 1, Decimal("343.9900")), Holding("MMM", 2, Decimal("300.0000"))],
        [],
    )
    assert result == expected


@pytest.mark.database
def test_holding() -> None:
    database = helper_database()
    helper_users(database, ["ada"])
    helper_portfolio(database, 1, "100.00")
    database.executed(
        "INSERT INTO holdings (portfolio_id, symbol, quantity, cost) VALUES (%s, %s, %s, %s)",
        (1, "MMM", 2, Decimal("300.00")),
    )
    tested = PortfolioStore(database)
    result = (tested.holding(1, "MMM"), tested.holding(1, "AAPL"), tested.holding(2, "MMM"))
    expected = (Holding("MMM", 2, Decimal("300.0000")), None, None)
    assert result == expected


@pytest.mark.database
def test_recorded() -> None:
    """A buy, then a sale of everything: the cash, the holding and the trade each time."""
    database = helper_database()
    helper_users(database, ["ada"])
    portfolio = helper_portfolio(database, 1, "500.00")
    run_id = helper_run(database)
    tested = PortfolioStore(database)
    bought = tested.recorded(
        portfolio,
        TradeSide.BUY,
        2,
        helper_quote("AAPL", "150.0000"),
        Decimal("300.00"),
        Holding("AAPL", 2, Decimal("300.00")),
        run_id,
        "Momentum.",
    )
    after_buy = helper_state(database)
    sold = tested.recorded(
        portfolio._replace(cash=Decimal("200.0000")),
        TradeSide.SELL,
        2,
        helper_quote("AAPL", "160.0000"),
        Decimal("320.00"),
        None,
        None,
        "Taking the profit.",
    )
    result = (bought._replace(executed_at=AS_OF), sold._replace(executed_at=AS_OF))
    expected = (
        Trade(
            trade_id=1,
            executed_at=AS_OF,
            symbol="AAPL",
            side=TradeSide.BUY,
            quantity=2,
            price=Decimal("150.0000"),
            amount=Decimal("300.0000"),
            cash_after=Decimal("200.0000"),
            quote_source=QuoteSource.GOOGLE_FINANCE,
            quote_as_of=AS_OF,
            agent_run_id=1,
            reason="Momentum.",
        ),
        Trade(
            trade_id=2,
            executed_at=AS_OF,
            symbol="AAPL",
            side=TradeSide.SELL,
            quantity=2,
            price=Decimal("160.0000"),
            amount=Decimal("320.0000"),
            cash_after=Decimal("520.0000"),
            quote_source=QuoteSource.GOOGLE_FINANCE,
            quote_as_of=AS_OF,
            agent_run_id=None,
            reason="Taking the profit.",
        ),
    )
    assert result == expected
    exp_recent = (True, True)
    assert (helper_is_recent(bought.executed_at), helper_is_recent(sold.executed_at)) == exp_recent
    exp_after_buy = {
        "cash": [{"id": 1, "cash": Decimal("200.0000")}],
        "holdings": [{"portfolio_id": 1, "symbol": "AAPL", "quantity": 2, "cost": Decimal("300.0000")}],
        "trades": [
            {
                "id": 1,
                "symbol": "AAPL",
                "side": "buy",
                "quantity": 2,
                "price": Decimal("150.0000"),
                "amount": Decimal("300.0000"),
                "cash_after": Decimal("200.0000"),
                "agent_run_id": 1,
            }
        ],
    }
    assert after_buy == exp_after_buy
    # Sold to nothing: the holding is deleted.
    exp_after_sale = {
        "cash": [{"id": 1, "cash": Decimal("520.0000")}],
        "holdings": [],
        "trades": [
            *exp_after_buy["trades"],
            {
                "id": 2,
                "symbol": "AAPL",
                "side": "sell",
                "quantity": 2,
                "price": Decimal("160.0000"),
                "amount": Decimal("320.0000"),
                "cash_after": Decimal("520.0000"),
                "agent_run_id": None,
            },
        ],
    }
    assert helper_state(database) == exp_after_sale


@pytest.mark.database
def test_recorded__a_holding_updated() -> None:
    database = helper_database()
    helper_users(database, ["ada"])
    portfolio = helper_portfolio(database, 1, "500.00")
    database.executed(
        "INSERT INTO holdings (portfolio_id, symbol, quantity, cost) VALUES (%s, %s, %s, %s)",
        (1, "AAPL", 3, Decimal("450.00")),
    )
    tested = PortfolioStore(database)
    result = tested.recorded(
        portfolio,
        TradeSide.SELL,
        1,
        helper_quote("AAPL", "160.0000"),
        Decimal("160.00"),
        Holding("AAPL", 2, Decimal("300.00")),
        None,
        "Trimming.",
    ).cash_after
    expected = Decimal("660.0000")
    assert result == expected
    exp_holdings = [{"portfolio_id": 1, "symbol": "AAPL", "quantity": 2, "cost": Decimal("300.0000")}]
    assert helper_state(database)["holdings"] == exp_holdings


@pytest.mark.database
def test_recorded__cash_below_zero_is_refused() -> None:
    """Whatever the caller's sum says, the database never lets the cash go
    below $0: the order's writes are rolled back together."""
    database = helper_database()
    helper_users(database, ["ada"])
    portfolio = helper_portfolio(database, 1, "500.00")
    tested = PortfolioStore(database)
    with pytest.raises(AppException) as exc_info:
        tested.recorded(
            portfolio,
            TradeSide.BUY,
            4,
            helper_quote("AAPL", "150.0000"),
            Decimal("600.00"),
            Holding("AAPL", 4, Decimal("600.00")),
            None,
            "Too much.",
        )
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (503, "The database is unavailable.")
    assert result == expected
    exp_state = {"cash": [{"id": 1, "cash": Decimal("500.0000")}], "holdings": [], "trades": []}
    assert helper_state(database) == exp_state


@pytest.mark.database
def test_recorded__an_update_making_cash_negative_is_refused() -> None:
    """The CHECK itself, whatever writes the cash."""
    database = helper_database()
    helper_users(database, ["ada"])
    helper_portfolio(database, 1, "500.00")
    with pytest.raises(AppException) as exc_info:
        database.executed("UPDATE portfolios SET cash = cash - %s WHERE id = %s", (Decimal("500.01"), 1))
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (503, "The database is unavailable.")
    assert result == expected
    exp_cash = [{"id": 1, "cash": Decimal("500.0000")}]
    assert helper_state(database)["cash"] == exp_cash


@pytest.mark.database
def test_trades() -> None:
    """Newest first, up to the limit; one portfolio's only."""
    database = helper_database()
    helper_users(database, ["ada", "bob"])
    portfolio = helper_portfolio(database, 1, "500.00")
    other = helper_portfolio(database, 2, "500.00")
    tested = PortfolioStore(database)
    for owner, symbol in ((portfolio, "MMM"), (portfolio, "AAPL"), (other, "AOS"), (portfolio, "ABT")):
        tested.recorded(
            owner, TradeSide.BUY, 1, helper_quote(symbol, "10.0000"), Decimal("10.00"), None, None, f"Buy {symbol}."
        )
    for trade_id, minute in ((1, 10), (2, 30), (3, 40), (4, 30)):
        database.executed(
            "UPDATE trades SET executed_at = %s WHERE id = %s",
            (datetime(2026, 10, 21, 15, minute, tzinfo=UTC), trade_id),
        )
    result = [(trade.trade_id, trade.symbol, trade.executed_at) for trade in tested.trades(1, 2)]
    # Two trades at the same moment: the later one first.
    expected = [
        (4, "ABT", datetime(2026, 10, 21, 15, 30, tzinfo=UTC)),
        (2, "AAPL", datetime(2026, 10, 21, 15, 30, tzinfo=UTC)),
    ]
    assert result == expected
    exp_all = [
        Trade(
            trade_id=4,
            executed_at=datetime(2026, 10, 21, 15, 30, tzinfo=UTC),
            symbol="ABT",
            side=TradeSide.BUY,
            quantity=1,
            price=Decimal("10.0000"),
            amount=Decimal("10.0000"),
            cash_after=Decimal("490.0000"),
            quote_source=QuoteSource.GOOGLE_FINANCE,
            quote_as_of=AS_OF,
            agent_run_id=None,
            reason="Buy ABT.",
        ),
        Trade(
            trade_id=2,
            executed_at=datetime(2026, 10, 21, 15, 30, tzinfo=UTC),
            symbol="AAPL",
            side=TradeSide.BUY,
            quantity=1,
            price=Decimal("10.0000"),
            amount=Decimal("10.0000"),
            cash_after=Decimal("490.0000"),
            quote_source=QuoteSource.GOOGLE_FINANCE,
            quote_as_of=AS_OF,
            agent_run_id=None,
            reason="Buy AAPL.",
        ),
        Trade(
            trade_id=1,
            executed_at=datetime(2026, 10, 21, 15, 10, tzinfo=UTC),
            symbol="MMM",
            side=TradeSide.BUY,
            quantity=1,
            price=Decimal("10.0000"),
            amount=Decimal("10.0000"),
            cash_after=Decimal("490.0000"),
            quote_source=QuoteSource.GOOGLE_FINANCE,
            quote_as_of=AS_OF,
            agent_run_id=None,
            reason="Buy MMM.",
        ),
    ]
    assert tested.trades(1, 10) == exp_all


@pytest.mark.database
def test_valued() -> None:
    database = helper_database()
    helper_users(database, ["ada"])
    helper_portfolio(database, 1, "500.00")
    tested = PortfolioStore(database)
    result = tested.valued(1, Valuation(AS_OF, Decimal("200.00"), Decimal("310.5"), Decimal("510.5")))
    assert result is None
    expected = [
        {
            "portfolio_id": 1,
            "taken_at": AS_OF,
            "cash": Decimal("200.0000"),
            "holdings_value": Decimal("310.5000"),
            "total_value": Decimal("510.5000"),
        }
    ]
    assert (
        database.rows("SELECT portfolio_id, taken_at, cash, holdings_value, total_value FROM valuations", ())
        == expected
    )


@pytest.mark.database
def test_valuations() -> None:
    """The latest points, oldest first."""
    database = helper_database()
    helper_users(database, ["ada", "bob"])
    helper_portfolio(database, 1, "500.00")
    helper_portfolio(database, 2, "500.00")
    tested = PortfolioStore(database)
    for portfolio_id, minute, total in ((1, 30, "503"), (1, 10, "501"), (2, 50, "999"), (1, 20, "502")):
        tested.valued(
            portfolio_id,
            Valuation(datetime(2026, 10, 21, 15, minute, tzinfo=UTC), Decimal("500"), Decimal("0"), Decimal(total)),
        )
    result = (tested.valuations(1, 2), tested.valuations(3, 10))
    expected = (
        [
            Valuation(
                datetime(2026, 10, 21, 15, 20, tzinfo=UTC), Decimal("500.0000"), Decimal("0.0000"), Decimal("502.0000")
            ),
            Valuation(
                datetime(2026, 10, 21, 15, 30, tzinfo=UTC), Decimal("500.0000"), Decimal("0.0000"), Decimal("503.0000")
            ),
        ],
        [],
    )
    assert result == expected


@pytest.mark.database
def test_last_valued_at() -> None:
    database = helper_database()
    helper_users(database, ["ada"])
    helper_portfolio(database, 1, "500.00")
    tested = PortfolioStore(database)
    empty = tested.last_valued_at(1)
    for minute in (30, 10):
        tested.valued(
            1, Valuation(datetime(2026, 10, 21, 15, minute, tzinfo=UTC), Decimal("1"), Decimal("0"), Decimal("1"))
        )
    result = (empty, tested.last_valued_at(1))
    expected = (None, datetime(2026, 10, 21, 15, 30, tzinfo=UTC))
    assert result == expected
