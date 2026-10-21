from __future__ import annotations

from datetime import timedelta

import pytest

from mcp_stock_markets.constants.link_purpose import LinkPurpose
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.libraries.magic_link_store import MagicLinkStore
from tests.conftest import helper_database


def helper_user(database: Database, name: str) -> None:
    database.executed(
        "INSERT INTO users (email_sealed, email_hash, display_name) VALUES (%s, %s, %s)",
        (b"sealed", f"hash-{name}", name),
    )


def test___init__() -> None:
    database = Database("postgresql://u:p@h/d")
    tested = MagicLinkStore(database)
    result = tested._database is database
    assert result is True


@pytest.mark.database
def test_created() -> None:
    database = helper_database()
    helper_user(database, "ada")
    tested = MagicLinkStore(database)
    tested.created(1, "link-old", LinkPurpose.SIGN_IN, 15)
    database.executed(
        "UPDATE magic_links SET expires_at = now() - interval '1 second' WHERE token_hash = %s", ("link-old",)
    )
    result = (
        tested.created(1, "link-a", LinkPurpose.SIGN_IN, 15),
        tested.created(1, "link-b", LinkPurpose.SIGN_IN, 30),
    )
    stored = database.rows(
        """SELECT user_id, token_hash, purpose, expires_at - created_at AS lifetime, used_at
           FROM magic_links ORDER BY id""",
        (),
    )
    expected = (None, None)
    assert result == expected
    # The expired link went as the next one came.
    exp_stored = [
        {
            "user_id": 1,
            "token_hash": "link-a",
            "purpose": "sign_in",
            "lifetime": timedelta(minutes=15),
            "used_at": None,
        },
        {
            "user_id": 1,
            "token_hash": "link-b",
            "purpose": "sign_in",
            "lifetime": timedelta(minutes=30),
            "used_at": None,
        },
    ]
    assert stored == exp_stored


@pytest.mark.database
def test_redeemed() -> None:
    database = helper_database()
    helper_user(database, "ada")
    helper_user(database, "bob")
    tested = MagicLinkStore(database)
    tested.created(2, "link-b", LinkPurpose.SIGN_IN, 15)
    result = (tested.redeemed("link-b"), tested.redeemed("link-b"), tested.redeemed("unknown"))
    expected = (2, None, None)
    assert result == expected


@pytest.mark.database
def test_redeemed__expired() -> None:
    database = helper_database()
    helper_user(database, "ada")
    tested = MagicLinkStore(database)
    tested.created(1, "link-a", LinkPurpose.SIGN_IN, 15)
    database.executed(
        "UPDATE magic_links SET expires_at = now() - interval '1 second' WHERE token_hash = %s", ("link-a",)
    )
    result = tested.redeemed("link-a")
    used = database.row("SELECT used_at FROM magic_links WHERE token_hash = %s", ("link-a",))
    assert result is None
    exp_used = {"used_at": None}
    assert used == exp_used
