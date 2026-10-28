from __future__ import annotations

import logging
import os
from decimal import Decimal
from unittest.mock import call, patch

import pytest

from mcp_stock_markets.libraries import settings_loader as settings_loader_module
from mcp_stock_markets.libraries.settings_loader import SettingsLoader
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.settings import Settings


def test___init__() -> None:
    environment = {"APP_ENV": "dev"}
    tested = SettingsLoader(environment)
    assert tested._environment is environment


def test_of_process() -> None:
    tested = SettingsLoader
    with patch.dict(os.environ, {"APP_ENV": "from-the-process"}):
        result = tested.of_process()
        assert result._read("APP_ENV") == "from-the-process"


def test_loaded() -> None:
    tested = SettingsLoader(
        {
            "APP_ENV": "production",
            "DATABASE_URL": " postgresql://u:secret@mcp_stock_markets-db:5432/mcp_stock_markets ",
            "APP_VERSION": "2026-10-11.2",
            "BUILD_TIME": "20261011-120000Z",
            "APP_COMMIT": "0123abcd",
            "APP_BASE_URL": "https://docs.example.com/",
            "DATA_ENCRYPTION_KEY": "a-real-data-key",
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "2587",
            "SMTP_USER": "smtp-user",
            "SMTP_PASSWORD": "smtp-password",
            "EMAIL_FROM": "MCP Stock Markets <noreply@example.com>",
            "BOOTSTRAP_ADMIN_EMAIL": " Ada@Example.COM ",
            "STARTING_BUDGET": " 1250.5 ",
            "MAX_COMPANIES": "8",
            "ALPACA_KEY_ID": " alpaca-key-id ",
            "ALPACA_SECRET_KEY": " alpaca-secret ",
            "AGENT_INTERVAL_MINUTES": "15",
            "MCP_BASE_URL": "http://127.0.0.1:8000/",
            "MCP_TOKEN": " mcp-token ",
        }
    )
    result = tested.loaded()
    expected = Settings(
        environment="production",
        database_url="postgresql://u:secret@mcp_stock_markets-db:5432/mcp_stock_markets",
        app_version="2026-10-11.2",
        build_time="20261011-120000Z",
        app_commit="0123abcd",
        app_base_url="https://docs.example.com",
        data_key="a-real-data-key",
        smtp_host="smtp.example.com",
        smtp_port=2587,
        smtp_user="smtp-user",
        smtp_password="smtp-password",
        email_from="MCP Stock Markets <noreply@example.com>",
        bootstrap_admin_email="ada@example.com",
        starting_budget=Decimal("1250.50"),
        max_companies=8,
        alpaca_key_id="alpaca-key-id",
        alpaca_secret_key="alpaca-secret",
        agent_interval_minutes=15,
        mcp_base_url="http://127.0.0.1:8000",
        mcp_token="mcp-token",
    )
    assert result == expected


def test_loaded__defaults_for_a_laptop(caplog: pytest.LogCaptureFixture) -> None:
    tested = SettingsLoader({"DATABASE_URL": "postgresql://u:p@127.0.0.1:5540/mcp_stock_markets"})
    with (
        patch.object(settings_loader_module.secrets, "token_bytes", side_effect=[bytes(32)]) as mock_token_bytes,
        patch.object(settings_loader_module.secrets, "token_urlsafe", side_effect=["fresh-token"]) as mock_urlsafe,
        caplog.at_level(logging.WARNING, logger="mcp_stock_markets"),
    ):
        result = tested.loaded()
    expected = Settings(
        environment="dev",
        database_url="postgresql://u:p@127.0.0.1:5540/mcp_stock_markets",
        app_version="dev",
        build_time="dev",
        app_commit="dev",
        app_base_url="http://localhost:8150",
        data_key="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        smtp_host="",
        smtp_port=587,
        smtp_user="",
        smtp_password="",
        email_from="",
        bootstrap_admin_email="",
        starting_budget=Decimal("5000.00"),
        max_companies=10,
        alpaca_key_id="",
        alpaca_secret_key="",
        agent_interval_minutes=30,
        mcp_base_url="http://127.0.0.1:8150",
        mcp_token="fresh-token",
    )
    assert result == expected
    exp_messages = [
        "[SETTINGS] DATA_ENCRYPTION_KEY is not set: generated for this process",
        "[SETTINGS] ALPACA_KEY_ID is not set: no daily history, no fallback quote",
        "[SETTINGS] ALPACA_SECRET_KEY is not set: no daily history, no fallback quote",
    ]
    assert [record.getMessage() for record in caplog.records] == exp_messages
    exp_calls = [call(32)]
    assert mock_token_bytes.mock_calls == exp_calls
    exp_calls = [call(32)]
    assert mock_urlsafe.mock_calls == exp_calls


@pytest.mark.parametrize(
    "environment, expected",
    [
        pytest.param({}, "DATABASE_URL is not set", id="missing"),
        pytest.param({"DATABASE_URL": "   "}, "DATABASE_URL is not set", id="blank"),
    ],
)
def test__database_url__missing(environment: dict[str, str], expected: str) -> None:
    tested = SettingsLoader(environment)
    with pytest.raises(AppException) as exc_info:
        tested._database_url(False)
    assert exc_info.value.status_code == 500
    assert exc_info.value.message == expected


def test__database_url__placeholder_refused_in_production() -> None:
    tested = SettingsLoader({"DATABASE_URL": "postgresql://u:CHANGE_ME_token@h:5432/d"})
    with pytest.raises(AppException) as exc_info:
        tested._database_url(True)
    assert exc_info.value.status_code == 500
    assert exc_info.value.message == "DATABASE_URL still holds a placeholder"


def test__database_url__placeholder_warned_in_development(caplog: pytest.LogCaptureFixture) -> None:
    tested = SettingsLoader({"DATABASE_URL": "postgresql://u:CHANGE_ME_token@h:5432/d"})
    with caplog.at_level(logging.WARNING, logger="mcp_stock_markets"):
        result = tested._database_url(False)
    expected = "postgresql://u:CHANGE_ME_token@h:5432/d"
    assert result == expected
    exp_messages = ["[SETTINGS] DATABASE_URL still holds a placeholder"]
    assert [record.getMessage() for record in caplog.records] == exp_messages


@pytest.mark.parametrize(
    "environment, is_production, expected",
    [
        pytest.param({"APP_BASE_URL": "https://docs.example.com"}, True, "https://docs.example.com", id="said"),
        pytest.param(
            {"APP_BASE_URL": " https://docs.example.com// "}, True, "https://docs.example.com", id="trailing-slash"
        ),
        pytest.param({}, False, "http://localhost:8150", id="laptop-default"),
        pytest.param({"APP_BASE_URL": "/"}, False, "http://localhost:8150", id="only-a-slash"),
        pytest.param({"APP_BASE_URL": "http://127.0.0.1:8150"}, False, "http://127.0.0.1:8150", id="laptop-http"),
    ],
)
def test__app_base_url(environment: dict[str, str], is_production: bool, expected: str) -> None:
    tested = SettingsLoader(environment)
    result = tested._app_base_url(is_production)
    assert result == expected


def test__app_base_url__refused_in_production() -> None:
    tested = SettingsLoader({})
    with pytest.raises(AppException) as exc_info:
        tested._app_base_url(True)
    assert exc_info.value.status_code == 500
    assert exc_info.value.message == "APP_BASE_URL is not set"


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("http://docs.example.com", id="plain-http"),
        pytest.param("https://", id="no-host"),
        pytest.param("docs.example.com", id="no-scheme"),
    ],
)
def test__app_base_url__production_wants_https_with_a_host(value: str) -> None:
    tested = SettingsLoader({"APP_BASE_URL": value})
    with pytest.raises(AppException) as exc_info:
        tested._app_base_url(True)
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (500, "APP_BASE_URL must be an https:// address with a host")
    assert result == expected


@pytest.mark.parametrize(
    "is_production",
    [
        pytest.param(True, id="production"),
        pytest.param(False, id="dev"),
    ],
)
def test__data_key(is_production: bool) -> None:
    tested = SettingsLoader({"DATA_ENCRYPTION_KEY": " a-real-data-key "})
    result = tested._data_key(is_production)
    expected = "a-real-data-key"
    assert result == expected


@pytest.mark.parametrize(
    "environment",
    [
        pytest.param({}, id="missing"),
        pytest.param({"DATA_ENCRYPTION_KEY": "CHANGE_ME_fernet_key"}, id="placeholder"),
    ],
)
def test__data_key__refused_in_production(environment: dict[str, str]) -> None:
    tested = SettingsLoader(environment)
    with pytest.raises(AppException) as exc_info:
        tested._data_key(True)
    assert exc_info.value.status_code == 500
    assert exc_info.value.message == "DATA_ENCRYPTION_KEY is not set, or is still a placeholder"


@pytest.mark.parametrize(
    "environment",
    [
        pytest.param({}, id="missing"),
        pytest.param({"DATA_ENCRYPTION_KEY": "CHANGE_ME_fernet_key"}, id="placeholder"),
    ],
)
def test__data_key__generated_in_development(environment: dict[str, str], caplog: pytest.LogCaptureFixture) -> None:
    tested = SettingsLoader(environment)
    with (
        patch.object(settings_loader_module.secrets, "token_bytes", side_effect=[bytes(range(32))]) as mock_token_bytes,
        caplog.at_level(logging.WARNING, logger="mcp_stock_markets"),
    ):
        result = tested._data_key(False)
    expected = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
    assert result == expected
    exp_messages = ["[SETTINGS] DATA_ENCRYPTION_KEY is not set: generated for this process"]
    assert [record.getMessage() for record in caplog.records] == exp_messages
    exp_calls = [call(32)]
    assert mock_token_bytes.mock_calls == exp_calls


@pytest.mark.parametrize(
    "environment, is_production, expected",
    [
        pytest.param({"SMTP_HOST": " smtp.example.com "}, True, "smtp.example.com", id="production-relay"),
        pytest.param({"SMTP_HOST": "smtp.example.com"}, False, "smtp.example.com", id="dev-relay"),
        pytest.param({}, False, "", id="dev-no-relay"),
    ],
)
def test__smtp_host(environment: dict[str, str], is_production: bool, expected: str) -> None:
    tested = SettingsLoader(environment)
    result = tested._smtp_host(is_production)
    assert result == expected


def test__smtp_host__refused_in_production() -> None:
    tested = SettingsLoader({})
    with pytest.raises(AppException) as exc_info:
        tested._smtp_host(True)
    assert exc_info.value.status_code == 500
    assert exc_info.value.message == "SMTP_HOST is not set: in production a link must reach an inbox"


@pytest.mark.parametrize(
    "environment, expected",
    [
        pytest.param({}, 587, id="default"),
        pytest.param({"SMTP_PORT": " "}, 587, id="blank"),
        pytest.param({"SMTP_PORT": "2465"}, 2465, id="said"),
    ],
)
def test__smtp_port(environment: dict[str, str], expected: int) -> None:
    tested = SettingsLoader(environment)
    result = tested._smtp_port()
    assert result == expected


def test__smtp_port__not_a_number() -> None:
    tested = SettingsLoader({"SMTP_PORT": "five-eight-seven"})
    with pytest.raises(AppException) as exc_info:
        tested._smtp_port()
    assert exc_info.value.status_code == 500
    assert exc_info.value.message == "SMTP_PORT is not a port: 'five-eight-seven'"


@pytest.mark.parametrize(
    "environment, expected",
    [
        pytest.param({}, Decimal("5000.00"), id="default"),
        pytest.param({"STARTING_BUDGET": "  "}, Decimal("5000.00"), id="blank"),
        pytest.param({"STARTING_BUDGET": "750"}, Decimal("750.00"), id="whole-dollars"),
        pytest.param({"STARTING_BUDGET": "123.456"}, Decimal("123.46"), id="to-the-cent"),
        pytest.param({"STARTING_BUDGET": "0.01"}, Decimal("0.01"), id="one-cent"),
        pytest.param({"STARTING_BUDGET": "1000000"}, Decimal("1000000.00"), id="the-maximum"),
    ],
)
def test__starting_budget(environment: dict[str, str], expected: Decimal) -> None:
    tested = SettingsLoader(environment)
    result = tested._starting_budget()
    assert result == expected
    # Equal Decimals can differ in places: the cents are part of the value.
    exp_exponent = -2
    assert result.as_tuple().exponent == exp_exponent


def test__starting_budget__not_an_amount() -> None:
    tested = SettingsLoader({"STARTING_BUDGET": "five hundred"})
    with pytest.raises(AppException) as exc_info:
        tested._starting_budget()
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (500, "STARTING_BUDGET is not an amount: 'five hundred'")
    assert result == expected


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("0", id="zero"),
        pytest.param("-10", id="negative"),
        pytest.param("1000000.01", id="over-the-maximum"),
        pytest.param("NaN", id="not-a-number"),
        pytest.param("Infinity", id="infinite"),
    ],
)
def test__starting_budget__out_of_bounds(value: str) -> None:
    tested = SettingsLoader({"STARTING_BUDGET": value})
    with pytest.raises(AppException) as exc_info:
        tested._starting_budget()
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (500, "STARTING_BUDGET must be more than 0 and at most 1000000")
    assert result == expected


@pytest.mark.parametrize(
    "environment, expected",
    [
        pytest.param({}, 5, id="default"),
        pytest.param({"SOME_COUNT": "1"}, 1, id="the-minimum"),
        pytest.param({"SOME_COUNT": " 25 "}, 25, id="the-maximum"),
    ],
)
def test__bounded(environment: dict[str, str], expected: int) -> None:
    tested = SettingsLoader(environment)
    result = tested._bounded("SOME_COUNT", 5, 25)
    assert result == expected


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("0", id="zero"),
        pytest.param("-1", id="negative"),
        pytest.param("26", id="over-the-maximum"),
    ],
)
def test__bounded__out_of_bounds(value: str) -> None:
    tested = SettingsLoader({"SOME_COUNT": value})
    with pytest.raises(AppException) as exc_info:
        tested._bounded("SOME_COUNT", 5, 25)
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (500, "SOME_COUNT must be from 1 to 25")
    assert result == expected


def test__bounded__not_a_whole_number() -> None:
    tested = SettingsLoader({"SOME_COUNT": "five"})
    with pytest.raises(AppException) as exc_info:
        tested._bounded("SOME_COUNT", 5, 25)
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (500, "SOME_COUNT is not a whole number: 'five'")
    assert result == expected


def test__optional(caplog: pytest.LogCaptureFixture) -> None:
    tested = SettingsLoader({"ALPACA_KEY_ID": " alpaca-key-id "})
    with caplog.at_level(logging.WARNING, logger="mcp_stock_markets"):
        result = tested._optional("ALPACA_KEY_ID", "no daily history, no fallback quote")
    expected = "alpaca-key-id"
    assert result == expected
    exp_messages: list[str] = []
    assert [record.getMessage() for record in caplog.records] == exp_messages


@pytest.mark.parametrize(
    "environment",
    [
        pytest.param({}, id="missing"),
        pytest.param({"ALPACA_KEY_ID": "CHANGE_ME_alpaca_key_id"}, id="placeholder"),
    ],
)
def test__optional__unset_is_empty_and_warned(environment: dict[str, str], caplog: pytest.LogCaptureFixture) -> None:
    tested = SettingsLoader(environment)
    with caplog.at_level(logging.WARNING, logger="mcp_stock_markets"):
        result = tested._optional("ALPACA_KEY_ID", "no daily history, no fallback quote")
    expected = ""
    assert result == expected
    exp_messages = ["[SETTINGS] ALPACA_KEY_ID is not set: no daily history, no fallback quote"]
    assert [record.getMessage() for record in caplog.records] == exp_messages


def test__mcp_token() -> None:
    tested = SettingsLoader({"MCP_TOKEN": " the-mcp-token "})
    with patch.object(settings_loader_module.secrets, "token_urlsafe", side_effect=[]) as mock_urlsafe:
        result = tested._mcp_token()
    expected = "the-mcp-token"
    assert result == expected
    exp_calls: list[object] = []
    assert mock_urlsafe.mock_calls == exp_calls


@pytest.mark.parametrize(
    "environment",
    [
        pytest.param({}, id="missing"),
        pytest.param({"MCP_TOKEN": "CHANGE_ME_token_urlsafe_32"}, id="placeholder"),
    ],
)
def test__mcp_token__generated_when_unset(environment: dict[str, str]) -> None:
    tested = SettingsLoader(environment)
    with patch.object(settings_loader_module.secrets, "token_urlsafe", side_effect=["fresh-token"]) as mock_urlsafe:
        result = tested._mcp_token()
    expected = "fresh-token"
    assert result == expected
    exp_calls = [call(32)]
    assert mock_urlsafe.mock_calls == exp_calls


@pytest.mark.parametrize(
    "environment, expected",
    [
        pytest.param({}, 42, id="default"),
        pytest.param({"SOME_NUMBER": "  "}, 42, id="blank"),
        pytest.param({"SOME_NUMBER": "7"}, 7, id="said"),
        pytest.param({"SOME_NUMBER": "-3"}, -3, id="negative"),
    ],
)
def test__number(environment: dict[str, str], expected: int) -> None:
    tested = SettingsLoader(environment)
    result = tested._number("SOME_NUMBER", 42)
    assert result == expected


def test__number__not_a_whole_number() -> None:
    tested = SettingsLoader({"MAX_COMPANIES": "3.5"})
    with pytest.raises(AppException) as exc_info:
        tested._number("MAX_COMPANIES", 5)
    assert exc_info.value.status_code == 500
    assert exc_info.value.message == "MAX_COMPANIES is not a whole number: '3.5'"


@pytest.mark.parametrize(
    "value, expected",
    [
        pytest.param("CHANGE_ME_token_urlsafe_24", True, id="placeholder-upper"),
        pytest.param("postgresql://u:change-me@h/d", True, id="dashed-inside"),
        pytest.param("placeholder", True, id="word"),
        pytest.param("postgresql://u:s3cret@h/d", False, id="real"),
        pytest.param("", False, id="empty"),
    ],
)
def test_has_placeholder(value: str, expected: bool) -> None:
    tested = SettingsLoader
    result = tested.has_placeholder(value)
    assert result is expected


def test__warned(caplog: pytest.LogCaptureFixture) -> None:
    tested = SettingsLoader
    with caplog.at_level(logging.WARNING, logger="mcp_stock_markets"):
        tested._warned("SOME_NAME", "is odd")
    exp_messages = ["[SETTINGS] SOME_NAME is odd"]
    assert [record.getMessage() for record in caplog.records] == exp_messages


def test__read() -> None:
    tested = SettingsLoader({"A": "  value \n"})
    result = (tested._read("A"), tested._read("B"))
    expected = ("value", "")
    assert result == expected
