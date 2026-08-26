from typing import Any

from litestar import Request
from litestar.connection import ASGIConnection
from litestar.exceptions import NotAuthorizedException
from litestar.handlers.base import BaseRouteHandler

from server.config import Config
from server.llm.client import LlmClient
from server.llm.client import ProviderStatusCache
from server.runs import RunManager
from server.store import Store


class AppServices:
    """Everything the route handlers need, built once at startup and stashed on ``app.state``."""

    def __init__(self, config: Config, store: Store, client: LlmClient, runs: RunManager) -> None:
        self.config = config
        self.store = store
        self.client = client
        self.runs = runs
        self.provider_status = ProviderStatusCache(client)


def services_of(request: Request[Any, Any, Any]) -> AppServices:
    services = request.app.state.services
    assert isinstance(services, AppServices)
    return services


def require_owner(connection: ASGIConnection[Any, Any, Any, Any], _: BaseRouteHandler) -> None:
    """Defence in depth.

    The router already refuses non-owner requests to any path outside ``public_paths``, and it
    strips client-supplied ``X-OpenHost-*`` headers, so this header is only ever set by the
    router.  Checking it means a manifest mistake that made ``/api`` public fails closed.
    """
    if connection.headers.get("x-openhost-is-owner") != "true":
        raise NotAuthorizedException(detail="owner only")
