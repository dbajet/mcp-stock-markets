from __future__ import annotations

from datetime import datetime
from typing import Any

from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.structures.company import Company


class CompanyStore:
    """The S&P 500 as last read, and the companies of it the agent may buy
    (its market, the `universe`)."""

    _COLUMNS = "symbol, name, sector, sub_industry, headquarters, exchange"

    def __init__(self, database: Database) -> None:
        self._database = database

    def replaced(self, companies: list[Company]) -> int:
        """The list replaces the stored one in one transaction: members
        updated or added, former members removed. How many it holds."""
        with self._database.transaction() as connection:
            for company in companies:
                connection.execute(
                    f"""INSERT INTO companies ({self._COLUMNS}, refreshed_at) VALUES (%s, %s, %s, %s, %s, %s, now())
                        ON CONFLICT (symbol) DO UPDATE SET name = EXCLUDED.name, sector = EXCLUDED.sector,
                            sub_industry = EXCLUDED.sub_industry, headquarters = EXCLUDED.headquarters,
                            exchange = EXCLUDED.exchange, refreshed_at = now()""",
                    (
                        company.symbol,
                        company.name,
                        company.sector,
                        company.sub_industry,
                        company.headquarters,
                        company.exchange,
                    ),
                )
            connection.execute(
                "DELETE FROM companies WHERE NOT (symbol = ANY(%s))",
                ([company.symbol for company in companies],),
            )
        return len(companies)

    def refreshed_at(self) -> datetime | None:
        row = self._database.row("SELECT max(refreshed_at) AS refreshed_at FROM companies", ())
        return None if row is None else row["refreshed_at"]

    def company(self, symbol: str) -> Company | None:
        row = self._database.row(f"SELECT {self._COLUMNS} FROM companies WHERE symbol = %s", (symbol,))
        return None if row is None else Company.from_dict(row)

    def searched(self, query: str, sector: str, limit: int) -> list[Company]:
        """By symbol or name, a symbol that starts with the query first;
        within one sector when one is named."""
        pattern = f"%{self.escaped(query)}%"
        rows = self._database.rows(
            f"""SELECT {self._COLUMNS} FROM companies
                WHERE (symbol ILIKE %s OR name ILIKE %s) AND (%s = '' OR sector = %s)
                ORDER BY (symbol ILIKE %s) DESC, symbol
                LIMIT %s""",
            (pattern, pattern, sector, sector, f"{self.escaped(query)}%", limit),
        )
        return [Company.from_dict(row) for row in rows]

    def listed(self) -> list[Company]:
        """The whole index, by symbol: the market page filters it itself."""
        rows = self._database.rows(f"SELECT {self._COLUMNS} FROM companies ORDER BY symbol", ())
        return [Company.from_dict(row) for row in rows]

    def sectors(self) -> list[dict[str, Any]]:
        rows = self._database.rows(
            "SELECT sector, count(*) AS companies FROM companies GROUP BY sector ORDER BY sector", ()
        )
        return [{"sector": str(row["sector"]), "companies": int(row["companies"])} for row in rows]

    def count(self) -> int:
        row = self._database.row("SELECT count(*) AS companies FROM companies", ())
        return 0 if row is None else int(row["companies"])

    def universe(self) -> list[str]:
        rows = self._database.rows("SELECT symbol FROM universe ORDER BY added_at, symbol", ())
        return [str(row["symbol"]) for row in rows]

    def universe_companies(self) -> list[Company]:
        """The agent's market with what the list says of each; a company that
        left the index since it was chosen stays, known by its symbol only."""
        rows = self._database.rows(
            """SELECT u.symbol, coalesce(c.name, u.symbol) AS name, coalesce(c.sector, '') AS sector,
                       coalesce(c.sub_industry, '') AS sub_industry, coalesce(c.headquarters, '') AS headquarters,
                       coalesce(c.exchange, '') AS exchange
                FROM universe u LEFT JOIN companies c ON c.symbol = u.symbol
                ORDER BY u.added_at, u.symbol""",
            (),
        )
        return [Company.from_dict(row) for row in rows]

    def added(self, symbol: str, limit: int) -> bool:
        """Added when the market has room, in one statement so two requests
        cannot both take the last place; whether it was."""
        return (
            self._database.executed(
                """INSERT INTO universe (symbol)
                   SELECT %s WHERE (SELECT count(*) FROM universe) < %s
                   ON CONFLICT (symbol) DO NOTHING""",
                (symbol, limit),
            )
            == 1
        )

    def removed(self, symbol: str) -> bool:
        return self._database.executed("DELETE FROM universe WHERE symbol = %s", (symbol,)) == 1

    @classmethod
    def escaped(cls, text: str) -> str:
        """LIKE's wildcards in the query are searched as themselves."""
        return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
