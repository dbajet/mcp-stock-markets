from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from mcp_stock_markets.constants.trade_side import TradeSide
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.structures.holding import Holding
from mcp_stock_markets.structures.portfolio import Portfolio
from mcp_stock_markets.structures.quote import Quote
from mcp_stock_markets.structures.trade import Trade
from mcp_stock_markets.structures.valuation import Valuation


class PortfolioStore:
    """The portfolio, its holdings, its trades and its valuations. The
    writes of one order are separate statements made atomic by the
    caller's transaction (`Database.transaction`), which also locks the
    portfolio's row so two orders never read the same cash."""

    _PORTFOLIO = "id AS portfolio_id, user_id, starting_budget, cash, created_at"
    _TRADE = """id AS trade_id, executed_at, symbol, side, quantity, price, amount, cash_after,
                quote_source, quote_as_of, agent_run_id, reason"""

    def __init__(self, database: Database) -> None:
        self._database = database

    def opened(self, user_id: int, starting_budget: Decimal) -> Portfolio:
        """The user's portfolio, made with the starting budget as its cash
        the first time; later starts find it as it is."""
        self._database.executed(
            """INSERT INTO portfolios (user_id, starting_budget, cash) VALUES (%s, %s, %s)
               ON CONFLICT (user_id) DO NOTHING""",
            (user_id, starting_budget, starting_budget),
        )
        return Portfolio.from_dict(
            self._database.returned(f"SELECT {self._PORTFOLIO} FROM portfolios WHERE user_id = %s", (user_id,))
        )

    def for_user(self, user_id: int) -> Portfolio | None:
        row = self._database.row(f"SELECT {self._PORTFOLIO} FROM portfolios WHERE user_id = %s", (user_id,))
        return None if row is None else Portfolio.from_dict(row)

    def of_owner(self) -> Portfolio | None:
        """The portfolio of the one enabled account: whom the broker serves."""
        row = self._database.row(
            """SELECT p.id AS portfolio_id, p.user_id, p.starting_budget, p.cash, p.created_at
               FROM portfolios p JOIN users u ON u.id = p.user_id
               WHERE u.disabled_at IS NULL ORDER BY p.id LIMIT 1""",
            (),
        )
        return None if row is None else Portfolio.from_dict(row)

    def locked(self, portfolio_id: int) -> Portfolio:
        """Read for an order, inside its transaction: the row stays locked until it commits."""
        return Portfolio.from_dict(
            self._database.returned(
                f"SELECT {self._PORTFOLIO} FROM portfolios WHERE id = %s FOR UPDATE", (portfolio_id,)
            )
        )

    def holdings(self, portfolio_id: int) -> list[Holding]:
        rows = self._database.rows(
            "SELECT symbol, quantity, cost FROM holdings WHERE portfolio_id = %s ORDER BY symbol", (portfolio_id,)
        )
        return [Holding.from_dict(row) for row in rows]

    def holding(self, portfolio_id: int, symbol: str) -> Holding | None:
        row = self._database.row(
            "SELECT symbol, quantity, cost FROM holdings WHERE portfolio_id = %s AND symbol = %s",
            (portfolio_id, symbol),
        )
        return None if row is None else Holding.from_dict(row)

    def recorded(
        self,
        portfolio: Portfolio,
        side: TradeSide,
        quantity: int,
        quote: Quote,
        amount: Decimal,
        holding: Holding | None,
        run_id: int | None,
        reason: str,
    ) -> Trade:
        """One order's writes: the cash, the holding (deleted when sold to
        nothing), and the trade itself. The cash is the caller's sum; the
        database refuses it below zero whatever the sum says."""
        cash_after = portfolio.cash - amount if side is TradeSide.BUY else portfolio.cash + amount
        with self._database.transaction():
            self._database.executed(
                "UPDATE portfolios SET cash = %s WHERE id = %s", (cash_after, portfolio.portfolio_id)
            )
            if holding is None:
                self._database.executed(
                    "DELETE FROM holdings WHERE portfolio_id = %s AND symbol = %s",
                    (portfolio.portfolio_id, quote.symbol),
                )
            else:
                self._database.executed(
                    """INSERT INTO holdings (portfolio_id, symbol, quantity, cost) VALUES (%s, %s, %s, %s)
                       ON CONFLICT (portfolio_id, symbol) DO UPDATE SET quantity = EXCLUDED.quantity, cost = EXCLUDED.cost""",
                    (portfolio.portfolio_id, holding.symbol, holding.quantity, holding.cost),
                )
            row = self._database.returned(
                f"""INSERT INTO trades (portfolio_id, symbol, side, quantity, price, amount, cash_after,
                                        quote_source, quote_as_of, agent_run_id, reason)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING {self._TRADE}""",
                (
                    portfolio.portfolio_id,
                    quote.symbol,
                    side.value,
                    quantity,
                    quote.price,
                    amount,
                    cash_after,
                    quote.source.value,
                    quote.as_of,
                    run_id,
                    reason,
                ),
            )
        return Trade.from_dict(row)

    def trades(self, portfolio_id: int, limit: int) -> list[Trade]:
        rows = self._database.rows(
            f"SELECT {self._TRADE} FROM trades WHERE portfolio_id = %s ORDER BY executed_at DESC, id DESC LIMIT %s",
            (portfolio_id, limit),
        )
        return [Trade.from_dict(row) for row in rows]

    def valued(self, portfolio_id: int, valuation: Valuation) -> None:
        self._database.executed(
            "INSERT INTO valuations (portfolio_id, taken_at, cash, holdings_value, total_value) VALUES (%s, %s, %s, %s, %s)",
            (portfolio_id, valuation.taken_at, valuation.cash, valuation.holdings_value, valuation.total_value),
        )

    def valuations(self, portfolio_id: int, limit: int) -> list[Valuation]:
        """The latest points, oldest first, for the chart."""
        rows = self._database.rows(
            """SELECT taken_at, cash, holdings_value, total_value FROM
                   (SELECT id, taken_at, cash, holdings_value, total_value FROM valuations
                    WHERE portfolio_id = %s ORDER BY taken_at DESC, id DESC LIMIT %s) latest
               ORDER BY taken_at, id""",
            (portfolio_id, limit),
        )
        return [Valuation.from_dict(row) for row in rows]

    def last_valued_at(self, portfolio_id: int) -> datetime | None:
        row = self._database.row(
            "SELECT max(taken_at) AS taken_at FROM valuations WHERE portfolio_id = %s", (portfolio_id,)
        )
        return None if row is None else row["taken_at"]
