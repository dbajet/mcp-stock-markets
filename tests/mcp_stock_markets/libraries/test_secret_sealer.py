from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from mcp_stock_markets.libraries.secret_sealer import SecretSealer
from mcp_stock_markets.structures.app_exception import AppException

KEY = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
OTHER_KEY = "Hx4dHBsaGRgXFhUUExIREA8ODQwLCgkIBwYFBAMCAQA="


def helper_instance() -> SecretSealer:
    return SecretSealer(KEY)


def helper_tampered() -> bytes:
    token = bytearray(Fernet(KEY).encrypt(b"ada@example.com"))
    token[-5] = ord("A") if token[-5] != ord("A") else ord("B")
    return bytes(token)


def test___init__() -> None:
    tested = helper_instance()
    result = Fernet(KEY).decrypt(tested._fernet.encrypt(b"probe"))
    expected = b"probe"
    assert result == expected


@pytest.mark.parametrize(
    "key",
    [
        pytest.param("not-a-key", id="not-base64-of-32-bytes"),
        pytest.param("", id="empty"),
        pytest.param("AAECAwQFBgcICQoLDA0ODxAREhMUFRYX", id="too-short"),
    ],
)
def test___init____a_bad_key_is_refused(key: str) -> None:
    with pytest.raises(AppException) as exc_info:
        SecretSealer(key)
    assert exc_info.value.status_code == 500
    assert exc_info.value.message == "DATA_ENCRYPTION_KEY is not a Fernet key"


def test_sealed() -> None:
    tested = helper_instance()
    sealed = tested.sealed("Zoë's notes.pdf")
    result = Fernet(KEY).decrypt(sealed).decode("utf-8")
    expected = "Zoë's notes.pdf"
    assert result == expected


def test_opened() -> None:
    tested = helper_instance()
    result = tested.opened(Fernet(KEY).encrypt("Zoë Lovelace".encode()))
    expected = "Zoë Lovelace"
    assert result == expected


def test_sealed_bytes() -> None:
    tested = helper_instance()
    content = b"%PDF-1.7\x00\xff\xfe binary"
    sealed = tested.sealed_bytes(content)
    result = Fernet(KEY).decrypt(sealed)
    expected = b"%PDF-1.7\x00\xff\xfe binary"
    assert result == expected


def test_opened_bytes() -> None:
    tested = helper_instance()
    result = tested.opened_bytes(Fernet(KEY).encrypt(b"\x89PNG\r\n\x1a\n"))
    expected = b"\x89PNG\r\n\x1a\n"
    assert result == expected


@pytest.mark.parametrize(
    "sealed",
    [
        pytest.param(Fernet(OTHER_KEY).encrypt(b"ada@example.com"), id="foreign-key"),
        pytest.param(helper_tampered(), id="tampered"),
        pytest.param(b"not a token at all", id="garbage"),
    ],
)
def test_opened_bytes__unreadable(sealed: bytes) -> None:
    tested = helper_instance()
    with pytest.raises(AppException) as exc_info:
        tested.opened_bytes(sealed)
    assert exc_info.value.status_code == 500
    assert exc_info.value.message == "A stored value could not be opened: the data key has changed since it was stored."
