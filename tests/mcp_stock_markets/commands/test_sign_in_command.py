from __future__ import annotations

from decimal import Decimal
from unittest.mock import call, patch

import pytest

from mcp_stock_markets.commands.session_command import SessionCommand
from mcp_stock_markets.commands.sign_in_command import SignInCommand
from mcp_stock_markets.constants.link_purpose import LinkPurpose
from mcp_stock_markets.libraries.alerter import Alerter
from mcp_stock_markets.libraries.blind_index import BlindIndex
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.libraries.email_box import EmailBox
from mcp_stock_markets.libraries.email_composer import EmailComposer
from mcp_stock_markets.libraries.job_queue import JobQueue
from mcp_stock_markets.libraries.magic_link_store import MagicLinkStore
from mcp_stock_markets.libraries.secret_sealer import SecretSealer
from mcp_stock_markets.libraries.session_store import SessionStore
from mcp_stock_markets.libraries.token_maker import TokenMaker
from mcp_stock_markets.libraries.user_store import UserStore
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.settings import Settings
from mcp_stock_markets.structures.user_account import UserAccount


def helper_settings() -> Settings:
    return Settings(
        environment="production",
        database_url="postgresql://u:p@h/d",
        app_version="v",
        build_time="b",
        app_commit="c",
        app_base_url="https://docs.example.com",
        data_key="Zm9yLXRlc3RzLW9ubHktZm9yLXRlc3RzLW9ubHktMzI=",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="user",
        smtp_password="secret",
        email_from="noreply@example.com",
        bootstrap_admin_email="",
        starting_budget=Decimal("500.00"),
        max_companies=5,
        alpaca_key_id="",
        alpaca_secret_key="",
        agent_interval_minutes=30,
        mcp_base_url="http://127.0.0.1:8000",
        mcp_token="mcp-token",
    )


def helper_users() -> UserStore:
    key = "Zm9yLXRlc3RzLW9ubHktZm9yLXRlc3RzLW9ubHktMzI="
    return UserStore(Database("postgresql://u:p@h/d"), SecretSealer(key), BlindIndex(key))


def helper_instance() -> SignInCommand:
    settings = helper_settings()
    database = Database("postgresql://u:p@h/d")
    users = helper_users()
    email_box = EmailBox(settings)
    return SignInCommand(
        settings,
        users,
        MagicLinkStore(database),
        SessionCommand(users, SessionStore(database)),
        EmailComposer(),
        email_box,
        JobQueue("mail", Alerter(email_box, "")),
    )


def helper_user(is_disabled: bool) -> UserAccount:
    return UserAccount(
        user_id=7,
        email="ada@example.com",
        display_name="Ada",
        is_disabled=is_disabled,
    )


def helper_admin() -> UserAccount:
    return UserAccount(
        user_id=1,
        email="boss@example.com",
        display_name="Boss",
        is_disabled=False,
    )


def test___init__() -> None:
    settings = helper_settings()
    database = Database("postgresql://u:p@h/d")
    users = helper_users()
    links = MagicLinkStore(database)
    sessions = SessionCommand(users, SessionStore(database))
    composer = EmailComposer()
    email_box = EmailBox(settings)
    jobs = JobQueue("mail", Alerter(email_box, ""))
    tested = SignInCommand(settings, users, links, sessions, composer, email_box, jobs)
    result = (
        tested._settings,
        tested._users,
        tested._links,
        tested._sessions,
        tested._composer,
        tested._email_box,
        tested._jobs,
    )
    expected = (settings, users, links, sessions, composer, email_box, jobs)
    assert result == expected


def test_requested() -> None:
    tested = helper_instance()
    with patch.object(JobQueue, "queued", side_effect=[None]) as mock_queued:
        result = tested.requested("ada@example.com")
    expected = "If this address has access, a sign-in link is on its way."
    assert result == expected
    exp_calls = [call(tested.delivered, ("ada@example.com",))]
    assert mock_queued.mock_calls == exp_calls


def test_delivered() -> None:
    tested = helper_instance()
    with (
        patch.object(UserStore, "by_email", side_effect=[helper_user(False)]) as mock_by_email,
        patch.object(TokenMaker, "token", side_effect=["tok-link"]) as mock_token,
        patch.object(MagicLinkStore, "created", side_effect=[None]) as mock_created,
        patch.object(EmailBox, "send", side_effect=[None]) as mock_send,
    ):
        result = tested.delivered("Ada@Example.com")
    assert result is None
    exp_calls = [call("Ada@Example.com")]
    assert mock_by_email.mock_calls == exp_calls
    exp_calls = [call()]
    assert mock_token.mock_calls == exp_calls
    exp_calls = [call(7, "2c5e6263399f2bfaa09106484b3f9b62f96253f1af16176397f0abf77d1d1180", LinkPurpose.SIGN_IN, 15)]
    assert mock_created.mock_calls == exp_calls
    exp_calls = [
        call(
            "ada@example.com",
            "Your MCP Stock Markets sign-in link",
            [
                "Hello Ada,",
                "",
                "To sign in to MCP Stock Markets, open this link:",
                "https://docs.example.com/auth/link?token=tok-link",
                "",
                "It works once, for 15 minutes.",
                "If you did not ask for it, ignore this message.",
            ],
        )
    ]
    assert mock_send.mock_calls == exp_calls


@pytest.mark.parametrize(
    "user",
    [
        pytest.param(None, id="unknown"),
        pytest.param(helper_user(True), id="disabled"),
    ],
)
def test_delivered__nobody_to_send_to(user: UserAccount | None) -> None:
    tested = helper_instance()
    with (
        patch.object(UserStore, "by_email", side_effect=[user]) as mock_by_email,
        patch.object(TokenMaker, "token", side_effect=[]) as mock_token,
        patch.object(MagicLinkStore, "created", side_effect=[]) as mock_created,
        patch.object(EmailBox, "send", side_effect=[]) as mock_send,
    ):
        result = tested.delivered("ada@example.com")
    assert result is None
    exp_calls = [call("ada@example.com")]
    assert mock_by_email.mock_calls == exp_calls
    assert mock_token.mock_calls == []
    assert mock_created.mock_calls == []
    assert mock_send.mock_calls == []


def test_redeemed() -> None:
    tested = helper_instance()
    with (
        patch.object(MagicLinkStore, "redeemed", side_effect=[7]) as mock_redeemed,
        patch.object(UserStore, "by_id", side_effect=[helper_user(False)]) as mock_by_id,
        patch.object(SessionCommand, "started", side_effect=["session-tok"]) as mock_started,
    ):
        result = tested.redeemed("link-tok")
    expected = "session-tok"
    assert result == expected
    exp_calls = [call("532c6f97184af9c0d5ab90a17e43d837a6221f6c44d07ea652eec679a61dbe63")]
    assert mock_redeemed.mock_calls == exp_calls
    exp_calls = [call(7)]
    assert mock_by_id.mock_calls == exp_calls
    exp_calls = [call(7)]
    assert mock_started.mock_calls == exp_calls


@pytest.mark.parametrize(
    "user_ids, users, exp_by_id_calls",
    [
        pytest.param([None], [], [], id="unknown_expired_or_spent"),
        pytest.param([7], [None], [call(7)], id="vanished_user"),
        pytest.param([7], [helper_user(True)], [call(7)], id="disabled_user"),
    ],
)
def test_redeemed__refused(user_ids: list[int | None], users: list[UserAccount | None], exp_by_id_calls: list) -> None:
    tested = helper_instance()
    with (
        patch.object(MagicLinkStore, "redeemed", side_effect=user_ids) as mock_redeemed,
        patch.object(UserStore, "by_id", side_effect=users) as mock_by_id,
        patch.object(SessionCommand, "started", side_effect=[]) as mock_started,
    ):
        with pytest.raises(AppException) as exc_info:
            tested.redeemed("link-tok")
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (401, "This sign-in link has expired or was already used. Ask for a new one.")
    assert result == expected
    exp_calls = [call("532c6f97184af9c0d5ab90a17e43d837a6221f6c44d07ea652eec679a61dbe63")]
    assert mock_redeemed.mock_calls == exp_calls
    assert mock_by_id.mock_calls == exp_by_id_calls
    assert mock_started.mock_calls == []


def test__link() -> None:
    tested = helper_instance()
    with (
        patch.object(TokenMaker, "token", side_effect=["tok-link"]) as mock_token,
        patch.object(MagicLinkStore, "created", side_effect=[None]) as mock_created,
    ):
        result = tested._link(7, LinkPurpose.SIGN_IN, 15)
    expected = "https://docs.example.com/auth/link?token=tok-link"
    assert result == expected
    exp_calls = [call()]
    assert mock_token.mock_calls == exp_calls
    exp_calls = [call(7, "2c5e6263399f2bfaa09106484b3f9b62f96253f1af16176397f0abf77d1d1180", LinkPurpose.SIGN_IN, 15)]
    assert mock_created.mock_calls == exp_calls
