from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from mcp_stock_markets.constants.constants import Constants


class SecurityHeaders(BaseHTTPMiddleware):
    """The headers the application owns, set in exactly one place. nginx owns
    HSTS, because it owns TLS and this
    process speaks plain HTTP on the loopback, where a browser ignores it —
    see `deploy/nginx-mcp_stock_markets.conf`."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        result = await call_next(request)
        # Mutates in place: a Starlette Response cannot be copied without losing the body it streams.
        result.headers["Content-Security-Policy"] = Constants.content_security_policy
        result.headers["X-Frame-Options"] = Constants.frame_options
        result.headers["Permissions-Policy"] = Constants.permissions_policy
        result.headers["X-Content-Type-Options"] = Constants.content_type_options
        result.headers["Referrer-Policy"] = Constants.referrer_policy
        return result
