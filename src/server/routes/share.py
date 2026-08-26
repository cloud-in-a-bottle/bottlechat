from typing import Any

from litestar import MediaType
from litestar import Request
from litestar import Router
from litestar import get
from litestar.exceptions import NotFoundException
from litestar.response import File

from server.routes.dependencies import services_of
from server.routes.schemas import SharedChat
from server.routes.schemas import SharedMessage


@get("/api/{token:str}", media_type=MediaType.JSON)
async def shared_chat(request: Request[Any, Any, Any], token: str) -> SharedChat:
    """The transcript behind a share link.

    Public: anyone with the token can read it.  Deliberately no chat id, model settings, token
    usage, or sibling-chat information — only what's needed to render the conversation.
    """
    services = services_of(request)
    chat = services.store.chat_for_share_token(token)
    if chat is None:
        raise NotFoundException(detail="this share link is not valid")
    messages = [
        SharedMessage(
            role=m.role.value,
            content=m.content,
            reasoning=m.reasoning,
            model=m.model,
            created_at=m.created_at,
        )
        for m in services.store.get_messages(chat.id)
        if m.content.strip() or m.reasoning.strip()
    ]
    return SharedChat(
        title=chat.title,
        created_at=chat.created_at,
        updated_at=chat.updated_at,
        messages=messages,
    )


@get("/{token:str}", media_type=MediaType.HTML)
async def shared_page(request: Request[Any, Any, Any]) -> File:
    """The SPA shell.  The token is read from the URL by the client, which then calls
    ``/share/api/<token>``; serving the shell unconditionally keeps a bad token from being
    distinguishable by response code before the page even loads."""
    services = services_of(request)
    index = services.config.frontend_dir / "index.html"
    if not index.is_file():
        raise NotFoundException(detail="frontend is not built")
    return File(path=index, media_type=MediaType.HTML, content_disposition_type="inline")


share_router = Router(path="/share", route_handlers=[shared_chat, shared_page])
