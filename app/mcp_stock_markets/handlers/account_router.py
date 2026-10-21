from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from mcp_stock_markets.handlers.session_guard import SessionGuard


class AccountRouter:
    """Who is signed in."""

    def __init__(self, guard: SessionGuard) -> None:
        self._guard = guard

    def router(self) -> APIRouter:
        result = APIRouter(prefix="/api/account")
        result.add_api_route("", self.account, methods=["GET"])
        return result

    def account(self, request: Request) -> dict[str, Any]:
        """The signed-in person, or 401: the page asks this first to know whom
        it shows. Outside /api/auth/, whose nginx rate limit is for sign-ins,
        not for every page load."""
        return self._guard.user(request).to_dict()
