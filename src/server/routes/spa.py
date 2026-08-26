from pathlib import Path
from typing import Any

from litestar import MediaType
from litestar import Request
from litestar import Response
from litestar import Router
from litestar import get
from litestar.datastructures import CacheControlHeader
from litestar.exceptions import NotFoundException
from litestar.response import File
from litestar.static_files import create_static_files_router

from server.config import Config
from server.routes.dependencies import services_of

# Cache-busted by Vite's content hashes, so they can be cached hard.
_IMMUTABLE = "public, max-age=31536000, immutable"
_IMMUTABLE_HEADER = CacheControlHeader(public=True, max_age=31536000, immutable=True)
# The shell and the service worker must never go stale, or a deploy won't reach open tabs.
_NO_CACHE = "no-cache"

_ROOT_FILES = {
    "manifest.webmanifest": "application/manifest+json",
    "sw.js": "text/javascript",
    "favicon.svg": "image/svg+xml",
}


def _frontend_dir(request: Request[Any, Any, Any]) -> Path:
    return services_of(request).config.frontend_dir


def _index(frontend_dir: Path) -> File:
    index = frontend_dir / "index.html"
    if not index.is_file():
        raise NotFoundException(detail="frontend is not built")
    return File(
        path=index,
        media_type=MediaType.HTML,
        content_disposition_type="inline",
        headers={"Cache-Control": _NO_CACHE},
    )


@get(["/", "/c/{chat_id:str}"], media_type=MediaType.HTML)
async def app_shell(request: Request[Any, Any, Any]) -> File:
    return _index(_frontend_dir(request))


@get("/{filename:str}", media_type=MediaType.TEXT, include_in_schema=False)
async def root_file(request: Request[Any, Any, Any], filename: str) -> File:
    media_type = _ROOT_FILES.get(filename)
    if media_type is None:
        raise NotFoundException()
    path = _frontend_dir(request) / filename
    if not path.is_file():
        raise NotFoundException()
    return File(
        path=path,
        media_type=media_type,
        content_disposition_type="inline",
        headers={"Cache-Control": _NO_CACHE},
    )


@get("/icons/{filename:str}", include_in_schema=False)
async def icon_file(request: Request[Any, Any, Any], filename: str) -> Response[bytes]:
    path = (_frontend_dir(request) / "icons" / filename).resolve()
    icons_dir = (_frontend_dir(request) / "icons").resolve()
    if icons_dir not in path.parents or not path.is_file():
        raise NotFoundException()
    return Response(
        content=path.read_bytes(),
        media_type="image/png" if path.suffix == ".png" else "image/svg+xml",
        headers={"Cache-Control": _IMMUTABLE},
    )


def assets_router(config: Config) -> Router:
    return create_static_files_router(
        path="/assets",
        directories=[config.frontend_dir / "assets"],
        name="assets",
        cache_control=_IMMUTABLE_HEADER,
    )
