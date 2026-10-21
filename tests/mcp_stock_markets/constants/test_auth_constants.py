from __future__ import annotations

import dataclasses

from mcp_stock_markets.constants.auth_constants import AuthConstants
from tests.conftest import is_dataclass


def test_class() -> None:
    tested = AuthConstants
    fields = {
        "cookie_name": "str",
        "session_days": "int",
        "magic_link_minutes": "int",
        "token_bytes": "int",
        "blind_index_label": "str",
        "link_path": "str",
        "link_requested": "str",
        "not_signed_in": "str",
        "link_refused": "str",
        "origin_refused": "str",
        "unsafe_methods": "tuple[str, ...]",
    }
    assert is_dataclass(tested, fields)


def test_values() -> None:
    tested = AuthConstants
    result = dataclasses.asdict(tested)
    expected = {
        "cookie_name": "mcp_stock_markets_session",
        "session_days": 30,
        "magic_link_minutes": 15,
        "token_bytes": 32,
        "blind_index_label": "mcp_stock_markets email blind index v1",
        "link_path": "/auth/link",
        "link_requested": "If this address has access, a sign-in link is on its way.",
        "not_signed_in": "Please sign in.",
        "link_refused": "This sign-in link has expired or was already used. Ask for a new one.",
        "origin_refused": "This request did not come from MCP Stock Markets.",
        "unsafe_methods": ("POST", "PUT", "PATCH", "DELETE"),
    }
    assert result == expected
