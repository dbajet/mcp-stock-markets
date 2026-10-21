from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from mcp_stock_markets.commands.session_command import SessionCommand
from mcp_stock_markets.constants.auth_constants import AuthConstants
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.settings import Settings
from mcp_stock_markets.structures.user_account import UserAccount


class SessionGuard:
    """What every route asks first: who is asking, and whether a
    state-changing request came from this site at all (`Origin`
    checked against APP_BASE_URL, on top of the SameSite cookie)."""

    def __init__(self, settings: Settings, sessions: SessionCommand) -> None:
        self._settings = settings
        self._sessions = sessions

    def same_origin(self, request: Request) -> None:
        if request.method in AuthConstants.unsafe_methods and request.headers.get("origin") != self._settings.origin():
            raise AppException(403, AuthConstants.origin_refused)

    def user(self, request: Request) -> UserAccount:
        self.same_origin(request)
        result = self._sessions.current(self.token_of(request))
        if result is None:
            raise AppException(401, AuthConstants.not_signed_in)
        return result

    def signed_in(self, token: str, body: dict[str, Any]) -> JSONResponse:
        """The answer that sets the session cookie: HttpOnly so no script reads
        it, Secure in production, SameSite=Lax so the link in an email still
        lands signed in."""
        result = JSONResponse(body)
        result.set_cookie(
            AuthConstants.cookie_name,
            token,
            max_age=AuthConstants.session_days * 24 * 3600,
            httponly=True,
            secure=self._settings.is_production(),
            samesite="lax",
            path="/",
        )
        return result

    @classmethod
    def signed_out(cls) -> JSONResponse:
        result = JSONResponse({"ok": True})
        result.delete_cookie(AuthConstants.cookie_name, path="/")
        return result

    @classmethod
    def token_of(cls, request: Request) -> str:
        return request.cookies.get(AuthConstants.cookie_name, "")
