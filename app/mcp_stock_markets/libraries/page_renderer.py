from __future__ import annotations

from pathlib import Path

from starlette.responses import HTMLResponse, Response

from mcp_stock_markets.constants.constants import Constants
from mcp_stock_markets.structures.settings import Settings


class PageRenderer:
    """The single page, with its `__BUILD__` and `__VERSION__` markers
    replaced: the build busts the asset cache on each
    deploy, and the version reaches the header without a request of its own."""

    def __init__(self, directory: Path, settings: Settings) -> None:
        self._directory = directory
        self._settings = settings

    def page(self) -> HTMLResponse:
        source = (self._directory / Constants.page_file).read_text(encoding=Constants.text_encoding)
        content = source.replace(Constants.marker_build, self._settings.build_time).replace(
            Constants.marker_version, self._settings.app_version
        )
        return HTMLResponse(content, headers={Constants.header_cache_control: Constants.page_cache_control})

    def service_worker(self) -> Response:
        """The worker, from the root so its scope is the whole site, stamped
        with the build so each deploy installs a fresh one."""
        source = (self._directory / Constants.service_worker_file).read_text(encoding=Constants.text_encoding)
        return Response(
            source.replace(Constants.marker_build, self._settings.build_time),
            media_type="text/javascript",
            headers={Constants.header_cache_control: Constants.page_cache_control},
        )
