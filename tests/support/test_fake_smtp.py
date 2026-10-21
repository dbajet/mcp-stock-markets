from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

import pytest

from mcp_stock_markets.libraries import email_box as email_box_module
from tests.support.fake_smtp import FakeSMTP


def helper_message() -> EmailMessage:
    result = EmailMessage()
    result["Subject"] = "Hi"
    result["From"] = "noreply@example.com"
    result["To"] = "ada@example.com"
    result.set_content("Hello")
    return result


def test___init__() -> None:
    tested = FakeSMTP(failing_step="login", unreachable=True)
    result = (tested.failing_step, tested.unreachable, tested.calls)
    expected = ("login", True, [])
    assert result == expected


def test___init____an_unknown_step_is_refused() -> None:
    with pytest.raises(ValueError) as exc_info:
        FakeSMTP(failing_step="helo")
    assert str(exc_info.value) == "unknown step: helo"


def test_installed() -> None:
    tested = FakeSMTP()
    original = email_box_module.smtplib.SMTP
    with tested.installed() as installed:
        result = (installed is tested, email_box_module.smtplib.SMTP is tested)
    expected = (True, True)
    assert result == expected
    exp_restored = original
    assert email_box_module.smtplib.SMTP is exp_restored


def test___call__() -> None:
    tested = FakeSMTP()
    result = tested("smtp.example.com", 587, timeout=15.0)
    assert result is tested
    expected = [("connect", "smtp.example.com", 587, 15.0)]
    assert tested.calls == expected


def test___call____unreachable() -> None:
    tested = FakeSMTP(unreachable=True)
    with pytest.raises(ConnectionRefusedError) as exc_info:
        tested("smtp.example.com", 587, timeout=15.0)
    assert str(exc_info.value) == "[Errno 111] Connection refused"
    expected = [("connect", "smtp.example.com", 587, 15.0)]
    assert tested.calls == expected


def test___call____connect_refused() -> None:
    tested = FakeSMTP(failing_step="connect")
    with pytest.raises(smtplib.SMTPConnectError) as exc_info:
        tested("smtp.example.com", 587, timeout=15.0)
    assert exc_info.value.smtp_code == 421
    assert exc_info.value.smtp_error == b"Service not available"
    expected = [("connect", "smtp.example.com", 587, 15.0)]
    assert tested.calls == expected


def test___enter__() -> None:
    tested = FakeSMTP()
    result = tested.__enter__()
    assert result is tested


def test___exit__() -> None:
    """QUIT is sent even when the body raised, as smtplib does."""
    tested = FakeSMTP()
    with pytest.raises(RuntimeError), tested:
        raise RuntimeError("body failed")
    expected = [("quit",)]
    assert tested.calls == expected


@pytest.mark.parametrize(
    "context, expected",
    [
        pytest.param(ssl.create_default_context(), [("starttls", "CERT_REQUIRED", True)], id="default-context"),
        pytest.param(None, [("starttls", None, None)], id="no-context"),
    ],
)
def test_starttls(context: ssl.SSLContext | None, expected: list[tuple[object, ...]]) -> None:
    tested = FakeSMTP()
    result = tested.starttls(context=context)
    exp_result = (220, b"Ready to start TLS")
    assert result == exp_result
    assert tested.calls == expected


def test_starttls__failing() -> None:
    tested = FakeSMTP(failing_step="starttls")
    with pytest.raises(smtplib.SMTPNotSupportedError) as exc_info:
        tested.starttls(context=None)
    assert str(exc_info.value) == "STARTTLS extension not supported by server."
    expected = [("starttls", None, None)]
    assert tested.calls == expected


def test_login() -> None:
    tested = FakeSMTP()
    result = tested.login("user", "password")
    exp_result = (235, b"Authentication successful")
    assert result == exp_result
    expected = [("login", "user", "password")]
    assert tested.calls == expected


def test_login__failing() -> None:
    tested = FakeSMTP(failing_step="login")
    with pytest.raises(smtplib.SMTPAuthenticationError) as exc_info:
        tested.login("user", "password")
    exp_error = (535, b"Authentication Credentials Invalid")
    assert (exc_info.value.smtp_code, exc_info.value.smtp_error) == exp_error
    expected = [("login", "user", "password")]
    assert tested.calls == expected


def test_send_message() -> None:
    tested = FakeSMTP()
    result = tested.send_message(helper_message())
    exp_result: dict[str, tuple[int, bytes]] = {}
    assert result == exp_result
    expected = [("send_message", "noreply@example.com", "ada@example.com", "Hi", "Hello\n")]
    assert tested.calls == expected


def test_send_message__failing() -> None:
    tested = FakeSMTP(failing_step="send_message")
    with pytest.raises(smtplib.SMTPDataError) as exc_info:
        tested.send_message(helper_message())
    assert exc_info.value.smtp_code == 554
    assert exc_info.value.smtp_error == b"Message rejected: Email address is not verified."
    expected = [("send_message", "noreply@example.com", "ada@example.com", "Hi", "Hello\n")]
    assert tested.calls == expected


def test_quit() -> None:
    tested = FakeSMTP()
    result = tested.quit()
    exp_result = (221, b"Bye")
    assert result == exp_result
    expected = [("quit",)]
    assert tested.calls == expected


def test__failed_at() -> None:
    tested = FakeSMTP(failing_step="login")
    result = tested._failed_at("starttls")
    assert result is None
    with pytest.raises(smtplib.SMTPAuthenticationError):
        tested._failed_at("login")
