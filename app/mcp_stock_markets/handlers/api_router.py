from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse, Response

from mcp_stock_markets.commands.health_command import HealthCommand
from mcp_stock_markets.constants.constants import Constants
from mcp_stock_markets.libraries.page_renderer import PageRenderer


class ApiRouter:
    """The health probe, the service worker, and the single page at every
    address it answers."""

    def __init__(self, health_command: HealthCommand, page_renderer: PageRenderer) -> None:
        self._health_command = health_command
        self._page_renderer = page_renderer

    def router(self) -> APIRouter:
        result = APIRouter()
        result.add_api_route(Constants.health_path, self.healthz, methods=["GET", "HEAD"])
        result.add_api_route(Constants.service_worker_path, self.service_worker, methods=["GET"])
        for path in Constants.page_paths:
            result.add_api_route(path, self.page, methods=["GET", "HEAD"], response_class=HTMLResponse)
        return result

    def healthz(self) -> JSONResponse:
        health = self._health_command.health()
        return JSONResponse(health.to_dict(), status_code=200 if health.ok else 503)

    def page(self) -> HTMLResponse:
        return self._page_renderer.page()

    def service_worker(self) -> Response:
        return self._page_renderer.service_worker()
