from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from mcp_stock_markets.libraries.security_headers import SecurityHeaders


def helper_app() -> FastAPI:
    result = FastAPI()
    result.add_middleware(SecurityHeaders)
    result.add_api_route("/", lambda: PlainTextResponse("ok"))
    return result


def test_inheritance() -> None:
    assert issubclass(SecurityHeaders, BaseHTTPMiddleware)


def test_dispatch() -> None:
    tested = helper_app()
    with TestClient(tested) as client:
        response = client.get("/")
    result = {
        name: response.headers[name]
        for name in (
            "Content-Security-Policy",
            "X-Frame-Options",
            "Permissions-Policy",
            "X-Content-Type-Options",
            "Referrer-Policy",
        )
    }
    expected = {
        "Content-Security-Policy": (
            "default-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self'; "
            "font-src 'self'; manifest-src 'self'; worker-src 'self'; object-src 'none'; base-uri 'none'; "
            "form-action 'self'; frame-ancestors 'none'"
        ),
        "X-Frame-Options": "DENY",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "strict-origin-when-cross-origin",
    }
    assert result == expected
    exp_hsts = "strict-transport-security"
    # nginx owns HSTS: never duplicated here.
    assert exp_hsts not in response.headers
