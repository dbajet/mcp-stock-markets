from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import call, patch

import pytest

from mcp_stock_markets.commands.company_command import CompanyCommand
from mcp_stock_markets.libraries.company_store import CompanyStore
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.libraries.web_box import WebBox
from mcp_stock_markets.libraries.wikipedia_box import WikipediaBox
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.company import Company
from mcp_stock_markets.structures.settings import Settings


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


def helper_parts() -> tuple[CompanyStore, WikipediaBox]:
    return CompanyStore(Database("postgresql://u:p@h/d")), WikipediaBox(WebBox())


def helper_instance() -> CompanyCommand:
    return CompanyCommand(helper_settings(), *helper_parts())


def helper_apple() -> Company:
    return Company(
        symbol="AAPL",
        name="Apple Inc.",
        sector="Information Technology",
        sub_industry="Technology Hardware, Storage & Peripherals",
        headquarters="Cupertino, California",
        exchange="NASDAQ",
    )


def helper_jpmorgan() -> Company:
    return Company(
        symbol="JPM",
        name="JPMorgan Chase",
        sector="Financials",
        sub_industry="Diversified Banks",
        headquarters="New York City, New York",
        exchange="NYSE",
    )


def test___init__() -> None:
    store, wikipedia = helper_parts()
    tested = CompanyCommand(helper_settings(), store, wikipedia)
    result = (tested._limit, tested._store, tested._wikipedia)
    expected = (5, store, wikipedia)
    assert result == expected


def test_refreshed() -> None:
    tested = helper_instance()
    with (
        patch.object(
            WikipediaBox, "constituents", side_effect=[[helper_apple(), helper_jpmorgan()]]
        ) as mock_constituents,
        patch.object(CompanyStore, "replaced", side_effect=[2]) as mock_replaced,
    ):
        result = tested.refreshed()
    expected = 2
    assert result == expected
    exp_calls = [call()]
    assert mock_constituents.mock_calls == exp_calls
    exp_calls = [call([helper_apple(), helper_jpmorgan()])]
    assert mock_replaced.mock_calls == exp_calls


@pytest.mark.parametrize(
    "refreshed_at, expected",
    [
        pytest.param(None, True, id="never-read"),
        pytest.param(datetime(2026, 10, 20, 14, 0, 1, tzinfo=UTC), False, id="under-a-day"),
        pytest.param(datetime(2026, 10, 20, 14, 0, 0, tzinfo=UTC), False, id="exactly-a-day"),
        pytest.param(datetime(2026, 10, 20, 13, 59, 59, tzinfo=UTC), True, id="over-a-day"),
    ],
)
def test_is_stale(refreshed_at: datetime | None, expected: bool) -> None:
    tested = helper_instance()
    with patch.object(CompanyStore, "refreshed_at", side_effect=[refreshed_at]) as mock_refreshed_at:
        result = tested.is_stale(datetime(2026, 10, 21, 14, 0, 0, tzinfo=UTC))
    assert result is expected
    exp_calls = [call()]
    assert mock_refreshed_at.mock_calls == exp_calls


@pytest.mark.parametrize(
    "is_stale, outcomes, exp_refreshed, exp_messages",
    [
        pytest.param(False, [], [], [], id="fresh-nothing-read"),
        pytest.param(True, [503], [call()], ["[SP500] 503 companies"], id="stale-read"),
        pytest.param(
            True,
            [AppException(502, "The S&P 500 list could not be read.")],
            [call()],
            ["[SP500] not refreshed: The S&P 500 list could not be read."],
            id="stale-read-failed",
        ),
    ],
)
def test_refreshed_if_stale(
    caplog: pytest.LogCaptureFixture,
    is_stale: bool,
    outcomes: list[object],
    exp_refreshed: list[object],
    exp_messages: list[str],
) -> None:
    tested = helper_instance()
    now = datetime(2026, 10, 21, 14, 0, tzinfo=UTC)
    with (
        caplog.at_level(logging.INFO, logger="mcp_stock_markets"),
        patch.object(CompanyCommand, "is_stale", side_effect=[is_stale]) as mock_is_stale,
        patch.object(CompanyCommand, "refreshed", side_effect=outcomes) as mock_refreshed,
    ):
        result = tested.refreshed_if_stale(now)
    assert result is None
    assert caplog.messages == exp_messages
    exp_calls = [call(datetime(2026, 10, 21, 14, 0, tzinfo=UTC))]
    assert mock_is_stale.mock_calls == exp_calls
    assert mock_refreshed.mock_calls == exp_refreshed


def test_company() -> None:
    tested = helper_instance()
    with patch.object(CompanyStore, "company", side_effect=[helper_apple()]) as mock_company:
        result = tested.company("  aapl ")
    expected = helper_apple()
    assert result == expected
    exp_calls = [call("AAPL")]
    assert mock_company.mock_calls == exp_calls


def test_company__not_a_member() -> None:
    tested = helper_instance()
    with (
        patch.object(CompanyStore, "company", side_effect=[None]) as mock_company,
        pytest.raises(AppException) as exc_info,
    ):
        tested.company(" zzzz ")
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (404, "ZZZZ is not in the S&P 500.")
    assert result == expected
    exp_calls = [call("ZZZZ")]
    assert mock_company.mock_calls == exp_calls


def test_searched() -> None:
    tested = helper_instance()
    with patch.object(CompanyStore, "searched", side_effect=[[helper_apple()]]) as mock_searched:
        result = tested.searched("  apple ", " Information Technology  ")
    expected = [helper_apple()]
    assert result == expected
    exp_calls = [call("apple", "Information Technology", 25)]
    assert mock_searched.mock_calls == exp_calls


def test_sectors() -> None:
    tested = helper_instance()
    with patch.object(
        CompanyStore, "sectors", side_effect=[[{"sector": "Financials", "companies": 67}]]
    ) as mock_sectors:
        result = tested.sectors()
    expected = [{"sector": "Financials", "companies": 67}]
    assert result == expected
    exp_calls = [call()]
    assert mock_sectors.mock_calls == exp_calls


def test_count() -> None:
    tested = helper_instance()
    with patch.object(CompanyStore, "count", side_effect=[503]) as mock_count:
        result = tested.count()
    expected = 503
    assert result == expected
    exp_calls = [call()]
    assert mock_count.mock_calls == exp_calls


def test_universe() -> None:
    tested = helper_instance()
    with patch.object(
        CompanyStore, "universe_companies", side_effect=[[helper_apple(), helper_jpmorgan()]]
    ) as mock_universe_companies:
        result = tested.universe()
    expected = [helper_apple(), helper_jpmorgan()]
    assert result == expected
    exp_calls = [call()]
    assert mock_universe_companies.mock_calls == exp_calls


def test_symbols() -> None:
    tested = helper_instance()
    with patch.object(CompanyStore, "universe", side_effect=[["AAPL", "JPM"]]) as mock_universe:
        result = tested.symbols()
    expected = ["AAPL", "JPM"]
    assert result == expected
    exp_calls = [call()]
    assert mock_universe.mock_calls == exp_calls


def test_limit() -> None:
    tested = helper_instance()
    result = tested.limit()
    expected = 5
    assert result == expected


def test_added() -> None:
    tested = helper_instance()
    with (
        patch.object(CompanyCommand, "company", side_effect=[helper_apple()]) as mock_company,
        patch.object(CompanyStore, "universe", side_effect=[["JPM"]]) as mock_universe,
        patch.object(CompanyStore, "added", side_effect=[True]) as mock_added,
    ):
        result = tested.added(" aapl ")
    expected = helper_apple()
    assert result == expected
    exp_calls = [call(" aapl ")]
    assert mock_company.mock_calls == exp_calls
    exp_calls = [call()]
    assert mock_universe.mock_calls == exp_calls
    exp_calls = [call("AAPL", 5)]
    assert mock_added.mock_calls == exp_calls


def test_added__already_a_member() -> None:
    tested = helper_instance()
    with (
        patch.object(CompanyCommand, "company", side_effect=[helper_apple()]) as mock_company,
        patch.object(CompanyStore, "universe", side_effect=[["AAPL", "JPM"]]) as mock_universe,
        patch.object(CompanyStore, "added", side_effect=[]) as mock_added,
        pytest.raises(AppException) as exc_info,
    ):
        tested.added("AAPL")
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (409, "AAPL is already in the agent's market.")
    assert result == expected
    exp_calls = [call("AAPL")]
    assert mock_company.mock_calls == exp_calls
    exp_calls = [call()]
    assert mock_universe.mock_calls == exp_calls
    exp_calls = []
    assert mock_added.mock_calls == exp_calls


def test_added__the_market_is_full() -> None:
    tested = helper_instance()
    with (
        patch.object(CompanyCommand, "company", side_effect=[helper_apple()]) as mock_company,
        patch.object(CompanyStore, "universe", side_effect=[["A", "B", "C", "D", "E"]]) as mock_universe,
        patch.object(CompanyStore, "added", side_effect=[False]) as mock_added,
        pytest.raises(AppException) as exc_info,
    ):
        tested.added("AAPL")
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (409, "The agent's market holds at most 5 companies: remove one first.")
    assert result == expected
    exp_calls = [call("AAPL")]
    assert mock_company.mock_calls == exp_calls
    exp_calls = [call()]
    assert mock_universe.mock_calls == exp_calls
    exp_calls = [call("AAPL", 5)]
    assert mock_added.mock_calls == exp_calls


def test_removed() -> None:
    tested = helper_instance()
    with patch.object(CompanyStore, "removed", side_effect=[True]) as mock_removed:
        result = tested.removed(" aapl ")
    assert result is None
    exp_calls = [call("AAPL")]
    assert mock_removed.mock_calls == exp_calls


def test_removed__not_in_the_market() -> None:
    tested = helper_instance()
    with (
        patch.object(CompanyStore, "removed", side_effect=[False]) as mock_removed,
        pytest.raises(AppException) as exc_info,
    ):
        tested.removed(" jpm")
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (404, "JPM is not in the agent's market.")
    assert result == expected
    exp_calls = [call("JPM")]
    assert mock_removed.mock_calls == exp_calls


@pytest.mark.parametrize(
    "symbol, expected",
    [
        pytest.param("AAPL", "AAPL", id="already"),
        pytest.param("  brk.b \n", "BRK.B", id="trimmed-uppercased"),
    ],
)
def test_normalized(symbol: str, expected: str) -> None:
    tested = helper_instance()
    result = tested.normalized(symbol)
    assert result == expected
