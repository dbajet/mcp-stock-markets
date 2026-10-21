from __future__ import annotations

import hmac
import json

from starlette.types import ASGIApp, Receive, Scope, Send

from mcp_stock_markets.constants.constants import Constants
from mcp_stock_markets.constants.mcp_constants import McpConstants


class McpGuard:
    """The second lock on the MCP servers (nginx's 404 is the first): every
    request must carry the app's bearer token, compared in constant time.
    An ASGI wrapper rather than the SDK's OAuth resource-server support:
    the only client is this app's own agent, which is handed the token, so
    there is no authorization server to point at."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        self._app = app
        self._expected = f"{McpConstants.bearer_prefix}{token}".encode(Constants.text_encoding)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and not self.is_allowed(scope):
            await self.refused(send)
            return
        await self._app(scope, receive, send)

    def is_allowed(self, scope: Scope) -> bool:
        presented = b""
        for name, value in scope.get("headers", []):
            if name.decode("latin-1").lower() == McpConstants.authorization_header:
                presented = value
        return hmac.compare_digest(presented, self._expected)

    @classmethod
    async def refused(cls, send: Send) -> None:
        body = json.dumps({"detail": McpConstants.refused}).encode(Constants.text_encoding)
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"www-authenticate", b"Bearer"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
