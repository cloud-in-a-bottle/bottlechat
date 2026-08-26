from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import attr
import httpx
from litestar import Litestar
from litestar import get
from loguru import logger

from server.config import Config
from server.db import Database
from server.llm.client import LlmClient
from server.routes.api import api_router
from server.routes.dependencies import AppServices
from server.routes.share import share_router
from server.routes.spa import app_shell
from server.routes.spa import assets_router
from server.routes.spa import icon_file
from server.routes.spa import root_file
from server.runs import RunManager
from server.store import Store


@attr.s(auto_attribs=True, frozen=True)
class HealthStatus:
    status: str


@get("/health", sync_to_thread=False)
def health() -> HealthStatus:
    return HealthStatus(status="ok")


def create_app(config: Config | None = None) -> Litestar:
    resolved = config or Config.from_env()
    if not (resolved.frontend_dir / "assets").is_dir():
        raise RuntimeError(
            f"no built frontend at {resolved.frontend_dir} — run `just build-frontend` "
            f"(or set BOTTLECHAT_FRONTEND_DIR)"
        )

    @asynccontextmanager
    async def lifespan(app: Litestar) -> AsyncIterator[None]:
        database = Database(resolved.db_path)
        store = Store(database)
        interrupted = store.mark_streaming_as_interrupted()
        if interrupted:
            logger.info("marked {} in-flight response(s) as interrupted after restart", interrupted)
        http_client = httpx.AsyncClient(follow_redirects=False)
        llm_client = LlmClient(resolved, http_client)
        runs = RunManager(store, llm_client)
        app.state.services = AppServices(config=resolved, store=store, client=llm_client, runs=runs)
        try:
            yield
        finally:
            await runs.shutdown()
            await http_client.aclose()
            database.close()

    return Litestar(
        route_handlers=[
            health,
            api_router,
            share_router,
            assets_router(resolved),
            app_shell,
            icon_file,
            root_file,
        ],
        lifespan=[lifespan],
    )


app = create_app()
