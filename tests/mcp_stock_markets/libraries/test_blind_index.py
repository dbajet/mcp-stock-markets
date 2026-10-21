from __future__ import annotations

import pytest

from mcp_stock_markets.libraries.blind_index import BlindIndex


def test___init__() -> None:
    """The index key is derived from the data key, never the data key itself."""
    tested = BlindIndex("the-data-key")
    result = tested._key.hex()
    expected = "28f804a54fce1607c1c97698e10901de958988cff0cb3a659be5b54bd5acb995"
    assert result == expected


@pytest.mark.parametrize(
    "data_key, email, expected",
    [
        pytest.param(
            "the-data-key",
            "ada@example.com",
            "46c723b89db532a8da1c37157ae04bc1fffa2ded6274f15d859a68b0d9e4ef4c",
            id="plain",
        ),
        pytest.param(
            "the-data-key",
            "  Ada@Example.COM \n",
            "46c723b89db532a8da1c37157ae04bc1fffa2ded6274f15d859a68b0d9e4ef4c",
            id="case-and-spaces",
        ),
        pytest.param(
            "another-key",
            "ada@example.com",
            "12f92172eb21567d2d8b7f633360725daafb49dc47935af1384ecd7375dcd1e0",
            id="another-key",
        ),
    ],
)
def test_digest(data_key: str, email: str, expected: str) -> None:
    tested = BlindIndex(data_key)
    result = tested.digest(email)
    assert result == expected
