from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from mcp_stock_markets.commands.llm_connection_command import LlmConnectionCommand
from mcp_stock_markets.handlers.llm_connection_request import LlmConnectionRequest
from mcp_stock_markets.handlers.llm_models_request import LlmModelsRequest
from mcp_stock_markets.handlers.llm_routing_request import LlmRoutingRequest
from mcp_stock_markets.handlers.session_guard import SessionGuard
from mcp_stock_markets.structures.llm_connection import LlmConnection
from mcp_stock_markets.structures.llm_routing import LlmRouting


class LlmConnectionRouter:
    """Settings › Language models. Keys go in, never out: every answer
    carries `has_key` instead."""

    def __init__(self, guard: SessionGuard, connections: LlmConnectionCommand) -> None:
        self._guard = guard
        self._connections = connections

    def router(self) -> APIRouter:
        result = APIRouter(prefix="/api/llm")
        result.add_api_route("/connections", self.listed, methods=["GET"])
        result.add_api_route("/connections", self.created, methods=["POST"])
        result.add_api_route("/connections/{connection_id}", self.updated, methods=["PUT"])
        result.add_api_route("/connections/{connection_id}", self.deleted, methods=["DELETE"])
        result.add_api_route("/connections/{connection_id}/health", self.health, methods=["GET"])
        result.add_api_route("/models", self.models, methods=["POST"])
        result.add_api_route("/routing", self.routed, methods=["PUT"])
        return result

    def listed(self, request: Request) -> dict[str, Any]:
        self._guard.user(request)
        return {
            "connections": [connection.public_dict() for connection in self._connections.connections()],
            "routing": self._connections.routing().to_dict(),
        }

    def created(self, request: Request, body: LlmConnectionRequest) -> dict[str, Any]:
        self._guard.user(request)
        return self._connections.created(self.connection_of(0, body)).public_dict()

    def updated(self, request: Request, connection_id: int, body: LlmConnectionRequest) -> dict[str, Any]:
        self._guard.user(request)
        return self._connections.updated(self.connection_of(connection_id, body)).public_dict()

    def deleted(self, request: Request, connection_id: int) -> dict[str, Any]:
        self._guard.user(request)
        self._connections.deleted(connection_id)
        return {"ok": True}

    def health(self, request: Request, connection_id: int) -> dict[str, Any]:
        self._guard.user(request)
        return self._connections.health(connection_id).to_dict()

    def models(self, request: Request, body: LlmModelsRequest) -> dict[str, Any]:
        """POST, not GET: the key travels in the body, never in a URL or a log."""
        self._guard.user(request)
        return {"models": self._connections.models(body.connection_id, body.kind, body.base_url, body.api_key)}

    def routed(self, request: Request, body: LlmRoutingRequest) -> dict[str, Any]:
        self._guard.user(request)
        self._connections.routed(LlmRouting.from_dict(body.model_dump()))
        return {"ok": True}

    @classmethod
    def connection_of(cls, connection_id: int, body: LlmConnectionRequest) -> LlmConnection:
        return LlmConnection.from_dict(body.model_dump(mode="json") | {"connection_id": connection_id})
