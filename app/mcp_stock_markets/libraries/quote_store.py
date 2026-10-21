from __future__ import annotations

from datetime import date, datetime

from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.structures.daily_bar import DailyBar
from mcp_stock_markets.structures.quote import Quote


class QuoteStore:
    """Every price read, the daily bars, and the day each stock's bars were
    last fetched."""

    _QUOTE_COLUMNS = "symbol, price, currency, as_of, source, fetched_at"
    _BAR_COLUMNS = "symbol, day, open, high, low, close, volume"

    def __init__(self, database: Database) -> None:
        self._database = database

    def stored(self, quote: Quote) -> Quote:
        self._database.executed(
            f"INSERT INTO quotes ({self._QUOTE_COLUMNS}) VALUES (%s, %s, %s, %s, %s, %s)",
            (quote.symbol, quote.price, quote.currency, quote.as_of, quote.source.value, quote.fetched_at),
        )
        return quote

    def latest(self, symbol: str) -> Quote | None:
        row = self._database.row(
            f"SELECT {self._QUOTE_COLUMNS} FROM quotes WHERE symbol = %s ORDER BY fetched_at DESC, id DESC LIMIT 1",
            (symbol,),
        )
        return None if row is None else Quote.from_dict(row)

    def latest_before(self, symbol: str, moment: datetime) -> Quote | None:
        row = self._database.row(
            f"""SELECT {self._QUOTE_COLUMNS} FROM quotes WHERE symbol = %s AND fetched_at <= %s
                ORDER BY fetched_at DESC, id DESC LIMIT 1""",
            (symbol, moment),
        )
        return None if row is None else Quote.from_dict(row)

    def bars(self, symbol: str, days: int) -> list[DailyBar]:
        """The latest days, oldest first."""
        rows = self._database.rows(
            f"""SELECT {self._BAR_COLUMNS} FROM
                    (SELECT {self._BAR_COLUMNS} FROM daily_bars WHERE symbol = %s ORDER BY day DESC LIMIT %s) latest
                ORDER BY day""",
            (symbol, days),
        )
        return [DailyBar.from_dict(row) for row in rows]

    def bars_replaced(self, symbol: str, bars: list[DailyBar], fetched_on: date) -> None:
        """The bars and the day they were fetched, together: a crash between
        them would fetch again, never trust half a series."""
        with self._database.transaction() as connection:
            for bar in bars:
                connection.execute(
                    f"""INSERT INTO daily_bars ({self._BAR_COLUMNS}) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (symbol, day) DO UPDATE SET open = EXCLUDED.open, high = EXCLUDED.high,
                            low = EXCLUDED.low, close = EXCLUDED.close, volume = EXCLUDED.volume""",
                    (bar.symbol, bar.day, bar.open, bar.high, bar.low, bar.close, bar.volume),
                )
            connection.execute(
                """INSERT INTO history_fetches (symbol, fetched_on) VALUES (%s, %s)
                   ON CONFLICT (symbol) DO UPDATE SET fetched_on = EXCLUDED.fetched_on""",
                (symbol, fetched_on),
            )

    def fetched_on(self, symbol: str) -> date | None:
        row = self._database.row("SELECT fetched_on FROM history_fetches WHERE symbol = %s", (symbol,))
        return None if row is None else row["fetched_on"]
