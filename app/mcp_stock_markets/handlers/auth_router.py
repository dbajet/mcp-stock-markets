from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from mcp_stock_markets.commands.session_command import SessionCommand
from mcp_stock_markets.commands.sign_in_command import SignInCommand
from mcp_stock_markets.handlers.session_guard import SessionGuard
from mcp_stock_markets.handlers.sign_in_request import SignInRequest
from mcp_stock_markets.handlers.token_request import TokenRequest


class AuthRouter:
    """Signing in, by an emailed link, and out. Everything under /api/auth/
    is rate-limited by nginx."""

    def __init__(
        self,
        guard: SessionGuard,
        sign_in: SignInCommand,
        sessions: SessionCommand,
    ) -> None:
        self._guard = guard
        self._sign_in = sign_in
        self._sessions = sessions

    def router(self) -> APIRouter:
        result = APIRouter(prefix="/api/auth")
        result.add_api_route("/link-request", self.link_requested, methods=["POST"])
        result.add_api_route("/link", self.link_redeemed, methods=["POST"])
        result.add_api_route("/sign-out", self.signed_out, methods=["POST"])
        return result

    def link_requested(self, request: Request, body: SignInRequest) -> dict[str, Any]:
        self._guard.same_origin(request)
        return {"message": self._sign_in.requested(body.email)}

    def link_redeemed(self, request: Request, body: TokenRequest) -> JSONResponse:
        self._guard.same_origin(request)
        return self._guard.signed_in(self._sign_in.redeemed(body.token), {"ok": True})

    def signed_out(self, request: Request) -> JSONResponse:
        self._guard.same_origin(request)
        self._sessions.ended(SessionGuard.token_of(request))
        return SessionGuard.signed_out()
