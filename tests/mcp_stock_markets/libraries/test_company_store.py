from __future__ import annotations

from datetime import UTC, datetime

import pytest

from mcp_stock_markets.libraries.company_store import CompanyStore
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.structures.company import Company
from tests.conftest import helper_database


def helper_companies() -> list[Company]:
    return [
        Company(
            "AAPL", "Apple Inc.", "Information Technology", "Technology Hardware", "Cupertino, California", "NASDAQ"
        ),
        Company("MMM", "3M", "Industrials", "Industrial Conglomerates", "Saint Paul, Minnesota", "NYSE"),
        Company("AOS", "A. O. Smith", "Industrials", "Building Products", "Milwaukee, Wisconsin", "NYSE"),
        Company("BRK.B", "Berkshire Hathaway", "Financials", "Multi-Sector Holdings", "Omaha, Nebraska", "NYSE"),
        Company("MAA", "Mid-America Apartment Communities", "Real Estate", "REITs", "Germantown, Tennessee", "NYSE"),
    ]


def helper_store(database: Database) -> CompanyStore:
    result = CompanyStore(database)
    result.replaced(helper_companies())
    return result


def helper_universe(database: Database, symbols: list[str]) -> None:
    """The universe with these symbols, each added a minute after the one before."""
    for minute, symbol in enumerate(symbols):
        database.executed(
            "INSERT INTO universe (symbol, added_at) VALUES (%s, %s)",
            (symbol, datetime(2026, 10, 21, 14, minute, tzinfo=UTC)),
        )


def test___init__() -> None:
    database = Database("postgresql://u:p@h/d")
    tested = CompanyStore(database)
    result = tested._database is database
    assert result is True


@pytest.mark.database
def test_replaced() -> None:
    """Members updated or added, former members removed, in one transaction."""
    database = helper_database()
    tested = CompanyStore(database)
    first = tested.replaced(helper_companies())
    renamed = Company("MMM", "3M Company", "Industrials", "Industrial Conglomerates", "Maplewood, Minnesota", "NYSE")
    newcomer = Company("ADBE", "Adobe Inc.", "Information Technology", "Application Software", "San Jose", "NASDAQ")
    result = (first, tested.replaced([renamed, newcomer]))
    expected = (5, 2)
    assert result == expected
    exp_rows = [
        {
            "symbol": "ADBE",
            "name": "Adobe Inc.",
            "sector": "Information Technology",
            "sub_industry": "Application Software",
            "headquarters": "San Jose",
            "exchange": "NASDAQ",
        },
        {
            "symbol": "MMM",
            "name": "3M Company",
            "sector": "Industrials",
            "sub_industry": "Industrial Conglomerates",
            "headquarters": "Maplewood, Minnesota",
            "exchange": "NYSE",
        },
    ]
    rows = database.rows(
        "SELECT symbol, name, sector, sub_industry, headquarters, exchange FROM companies ORDER BY symbol", ()
    )
    assert rows == exp_rows


@pytest.mark.database
def test_replaced__an_empty_list_empties_the_table() -> None:
    database = helper_database()
    tested = helper_store(database)
    result = tested.replaced([])
    expected = 0
    assert result == expected
    exp_count = {"companies": 0}
    assert database.row("SELECT count(*) AS companies FROM companies", ()) == exp_count


@pytest.mark.database
def test_refreshed_at() -> None:
    database = helper_database()
    tested = CompanyStore(database)
    empty = tested.refreshed_at()
    tested.replaced(helper_companies())
    database.executed("UPDATE companies SET refreshed_at = %s", (datetime(2026, 10, 20, 6, 0, tzinfo=UTC),))
    database.executed(
        "UPDATE companies SET refreshed_at = %s WHERE symbol = %s", (datetime(2026, 10, 21, 6, 0, tzinfo=UTC), "MMM")
    )
    result = (empty, tested.refreshed_at())
    expected = (None, datetime(2026, 10, 21, 6, 0, tzinfo=UTC))
    assert result == expected


@pytest.mark.database
def test_company() -> None:
    database = helper_database()
    tested = helper_store(database)
    result = (tested.company("BRK.B"), tested.company("brk.b"), tested.company("ZZZ"))
    expected = (
        Company("BRK.B", "Berkshire Hathaway", "Financials", "Multi-Sector Holdings", "Omaha, Nebraska", "NYSE"),
        None,
        None,
    )
    assert result == expected


@pytest.mark.parametrize(
    "query, sector, limit, expected",
    [
        pytest.param(
            "a",
            "",
            10,
            [
                # A symbol that starts with the query first, then by symbol; names case-insensitive.
                Company(
                    "AAPL",
                    "Apple Inc.",
                    "Information Technology",
                    "Technology Hardware",
                    "Cupertino, California",
                    "NASDAQ",
                ),
                Company("AOS", "A. O. Smith", "Industrials", "Building Products", "Milwaukee, Wisconsin", "NYSE"),
                Company(
                    "BRK.B", "Berkshire Hathaway", "Financials", "Multi-Sector Holdings", "Omaha, Nebraska", "NYSE"
                ),
                Company(
                    "MAA", "Mid-America Apartment Communities", "Real Estate", "REITs", "Germantown, Tennessee", "NYSE"
                ),
            ],
            id="symbol-prefix-first-names-case-insensitive",
        ),
        pytest.param(
            "a",
            "Industrials",
            10,
            [Company("AOS", "A. O. Smith", "Industrials", "Building Products", "Milwaukee, Wisconsin", "NYSE")],
            id="within-one-sector",
        ),
        pytest.param(
            "",
            "",
            2,
            [
                Company(
                    "AAPL",
                    "Apple Inc.",
                    "Information Technology",
                    "Technology Hardware",
                    "Cupertino, California",
                    "NASDAQ",
                ),
                Company("AOS", "A. O. Smith", "Industrials", "Building Products", "Milwaukee, Wisconsin", "NYSE"),
            ],
            id="everything-up-to-the-limit",
        ),
        pytest.param("%", "", 10, [], id="a-wildcard-searched-as-itself"),
        pytest.param(
            ".",
            "",
            10,
            [
                Company(
                    "AAPL",
                    "Apple Inc.",
                    "Information Technology",
                    "Technology Hardware",
                    "Cupertino, California",
                    "NASDAQ",
                ),
                Company("AOS", "A. O. Smith", "Industrials", "Building Products", "Milwaukee, Wisconsin", "NYSE"),
                Company(
                    "BRK.B", "Berkshire Hathaway", "Financials", "Multi-Sector Holdings", "Omaha, Nebraska", "NYSE"
                ),
            ],
            id="a-dot",
        ),
    ],
)
@pytest.mark.database
def test_searched(query: str, sector: str, limit: int, expected: list[Company]) -> None:
    database = helper_database()
    tested = helper_store(database)
    result = tested.searched(query, sector, limit)
    assert result == expected


@pytest.mark.database
def test_sectors() -> None:
    database = helper_database()
    tested = CompanyStore(database)
    empty = tested.sectors()
    tested.replaced(helper_companies())
    result = (empty, tested.sectors())
    expected = (
        [],
        [
            {"sector": "Financials", "companies": 1},
            {"sector": "Industrials", "companies": 2},
            {"sector": "Information Technology", "companies": 1},
            {"sector": "Real Estate", "companies": 1},
        ],
    )
    assert result == expected


@pytest.mark.database
def test_count() -> None:
    database = helper_database()
    tested = CompanyStore(database)
    empty = tested.count()
    tested.replaced(helper_companies())
    result = (empty, tested.count())
    expected = (0, 5)
    assert result == expected


@pytest.mark.database
def test_universe() -> None:
    database = helper_database()
    tested = helper_store(database)
    empty = tested.universe()
    helper_universe(database, ["MMM", "AAPL", "AOS"])
    result = (empty, tested.universe())
    # In the order they were added, not by symbol.
    expected = ([], ["MMM", "AAPL", "AOS"])
    assert result == expected


@pytest.mark.database
def test_universe_companies() -> None:
    """A company that left the index stays, known by its symbol only."""
    database = helper_database()
    tested = helper_store(database)
    helper_universe(database, ["MMM", "GONE", "AAPL"])
    result = tested.universe_companies()
    expected = [
        Company("MMM", "3M", "Industrials", "Industrial Conglomerates", "Saint Paul, Minnesota", "NYSE"),
        Company("GONE", "GONE", "", "", "", ""),
        Company(
            "AAPL", "Apple Inc.", "Information Technology", "Technology Hardware", "Cupertino, California", "NASDAQ"
        ),
    ]
    assert result == expected


@pytest.mark.database
def test_added() -> None:
    """Added while the market has room; a symbol already in it is not added twice."""
    database = helper_database()
    tested = helper_store(database)
    result = (
        tested.added("MMM", 2),
        tested.added("MMM", 2),
        tested.added("AAPL", 2),
        tested.added("AOS", 2),
    )
    expected = (True, False, True, False)
    assert result == expected
    exp_rows = [{"symbol": "AAPL"}, {"symbol": "MMM"}]
    assert database.rows("SELECT symbol FROM universe ORDER BY symbol", ()) == exp_rows


@pytest.mark.database
def test_removed() -> None:
    database = helper_database()
    tested = helper_store(database)
    helper_universe(database, ["MMM", "AAPL"])
    result = (tested.removed("MMM"), tested.removed("MMM"))
    expected = (True, False)
    assert result == expected
    exp_rows = [{"symbol": "AAPL"}]
    assert database.rows("SELECT symbol FROM universe ORDER BY symbol", ()) == exp_rows


@pytest.mark.parametrize(
    "text, expected",
    [
        pytest.param("Apple", "Apple", id="plain"),
        pytest.param("50%_off", "50\\%\\_off", id="wildcards"),
        pytest.param("a\\b", "a\\\\b", id="the-escape-itself"),
    ],
)
def test_escaped(text: str, expected: str) -> None:
    tested = CompanyStore
    result = tested.escaped(text)
    assert result == expected
