import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated
from typing import Any

import attr
from litestar import Request
from litestar import Router
from litestar import delete
from litestar import get
from litestar import patch
from litestar import post
from litestar.exceptions import ClientException
from litestar.exceptions import NotFoundException
from litestar.params import Parameter
from litestar.response import ServerSentEvent
from litestar.response import ServerSentEventMessage

from server.config import PROVIDER_REPO_URL
from server.links import request_scheme
from server.models import Chat
from server.models import Message
from server.models import MessageStatus
from server.models import Role
from server.models import Usage
from server.routes.dependencies import AppServices
from server.routes.dependencies import require_owner
from server.routes.dependencies import services_of
from server.routes.schemas import ChatDetail
from server.routes.schemas import ChatListResponse
from server.routes.schemas import CreateChatRequest
from server.routes.schemas import Defaults
from server.routes.schemas import OkResponse
from server.routes.schemas import ProviderRef
from server.routes.schemas import RetryRequest
from server.routes.schemas import SendMessageRequest
from server.routes.schemas import ShareRef
from server.routes.schemas import StatusResponse
from server.routes.schemas import TurnResponse
from server.routes.schemas import UpdateChatRequest
from server.runs import Run

_MAX_MESSAGE_CHARS = 500_000


def _share_ref(services: AppServices, request: Request[Any, Any, Any], chat_id: str) -> ShareRef | None:
    share = services.store.get_share_for_chat(chat_id)
    if share is None:
        return None
    base = services.config.app_url_for(services.config.app_name, request_scheme(request))
    return ShareRef(token=share.token, url=f"{base}/share/{share.token}")


def _require_chat(services: AppServices, chat_id: str) -> Chat:
    chat = services.store.get_chat(chat_id)
    if chat is None:
        raise NotFoundException(detail="no such chat")
    return chat


@get("/status")
async def status(request: Request[Any, Any, Any], refresh: bool = False) -> StatusResponse:
    services = services_of(request)
    provider = await services.provider_status.get(refresh)
    settings = services.store.get_settings()
    scheme = request_scheme(request)
    provider_ref = (
        ProviderRef(
            app_name=provider.provider_app_name,
            url=services.config.app_url_for(provider.provider_app_name, scheme),
        )
        if provider.provider_app_name
        else None
    )
    # A default model that has since disappeared from the provider would silently 404 on send.
    model_ids = {m.id for m in provider.models}
    fallback_model = provider.models[0].id if provider.models else None
    default_model = settings.model if settings.model in model_ids else fallback_model
    return StatusResponse(
        state=provider.state,
        models=provider.models,
        defaults=Defaults(model=default_model, effort=settings.effort),
        dashboard_url=services.config.dashboard_url(scheme),
        provider_repo_url=PROVIDER_REPO_URL,
        detail=provider.detail,
        grant_url=provider.grant_url,
        provider=provider_ref,
    )


@get("/chats")
async def list_chats(
    request: Request[Any, Any, Any],
    q: Annotated[str | None, Parameter(query="q")] = None,
    limit: int = 100,
    offset: int = 0,
) -> ChatListResponse:
    services = services_of(request)
    limit = max(1, min(limit, 500))
    if q and q.strip():
        return ChatListResponse(chats=services.store.search_chats(q.strip(), limit))
    return ChatListResponse(chats=services.store.list_chats(limit, max(0, offset)))


@post("/chats")
async def create_chat(request: Request[Any, Any, Any], data: CreateChatRequest) -> Chat:
    services = services_of(request)
    settings = services.store.get_settings()
    return services.store.create_chat(
        model=data.model or settings.model,
        effort=data.effort or settings.effort,
    )


@get("/chats/{chat_id:str}")
async def get_chat(request: Request[Any, Any, Any], chat_id: str) -> ChatDetail:
    services = services_of(request)
    chat = _require_chat(services, chat_id)
    return ChatDetail(
        chat=chat,
        messages=services.store.get_messages(chat_id),
        share=_share_ref(services, request, chat_id),
    )


@patch("/chats/{chat_id:str}")
async def update_chat(request: Request[Any, Any, Any], chat_id: str, data: UpdateChatRequest) -> Chat:
    services = services_of(request)
    _require_chat(services, chat_id)
    title = data.title.strip() if data.title is not None else None
    if title is not None and not title:
        raise ClientException(detail="title cannot be empty")
    # Renaming a chat shouldn't jump it to the top of the sidebar.
    services.store.update_chat(chat_id, title=title, model=data.model, effort=data.effort, touch=False)
    if data.model is not None or data.effort is not None:
        settings = services.store.get_settings()
        services.store.save_settings(model=data.model or settings.model, effort=data.effort or settings.effort)
    return _require_chat(services, chat_id)


@delete("/chats/{chat_id:str}", status_code=200)
async def delete_chat(request: Request[Any, Any, Any], chat_id: str) -> OkResponse:
    services = services_of(request)
    for message in services.store.get_messages(chat_id):
        services.runs.cancel(message.id)
    if not services.store.delete_chat(chat_id):
        raise NotFoundException(detail="no such chat")
    return OkResponse(ok=True)


async def _resolve_model(services: AppServices, chat: Chat, requested: str | None) -> str:
    model = requested or chat.model
    if model:
        return model
    provider = await services.provider_status.get()
    if not provider.models:
        raise ClientException(detail="no models are configured in the provider")
    return provider.models[0].id


@post("/chats/{chat_id:str}/messages")
async def send_message(request: Request[Any, Any, Any], chat_id: str, data: SendMessageRequest) -> TurnResponse:
    services = services_of(request)
    chat = _require_chat(services, chat_id)
    content = data.content.strip()
    if not content:
        raise ClientException(detail="message cannot be empty")
    if len(content) > _MAX_MESSAGE_CHARS:
        raise ClientException(detail="message is too long")

    # A second send while one is in flight would interleave two runs into the same transcript.
    # The UI shows Stop instead of Send, but a double-submit or a second tab can still get here.
    if any(m.status is MessageStatus.STREAMING for m in services.store.get_messages(chat_id)):
        raise ClientException(detail="wait for the current response to finish")

    model = await _resolve_model(services, chat, data.model)
    effort = data.effort or chat.effort
    services.store.update_chat(chat_id, model=model, effort=effort, touch=False)
    services.store.save_settings(model=model, effort=effort)

    user_message = services.store.append_message(chat_id, Role.USER, content=content)
    assistant_message = services.store.append_message(
        chat_id, Role.ASSISTANT, status=MessageStatus.STREAMING, model=model, effort=effort
    )
    services.runs.start(chat_id, assistant_message, model, effort)
    return TurnResponse(user_message=user_message, assistant_message=assistant_message)


@post("/chats/{chat_id:str}/messages/{message_id:str}/retry")
async def retry_message(request: Request[Any, Any, Any], chat_id: str, message_id: str, data: RetryRequest) -> Message:
    services = services_of(request)
    chat = _require_chat(services, chat_id)
    message = services.store.get_message(message_id)
    if message is None or message.chat_id != chat_id or message.role is not Role.ASSISTANT:
        raise NotFoundException(detail="no such assistant message")
    if message.status is MessageStatus.STREAMING and services.runs.get(message_id) is not None:
        raise ClientException(detail="that response is still streaming")

    model = await _resolve_model(services, chat, data.model)
    effort = data.effort or chat.effort
    services.store.reset_message_for_retry(message_id, model, effort)
    services.store.update_chat(chat_id, model=model, effort=effort, touch=False)
    reset = services.store.get_message(message_id)
    assert reset is not None
    services.runs.start(chat_id, reset, model, effort)
    return reset


@post("/chats/{chat_id:str}/messages/{message_id:str}/stop", status_code=200)
async def stop_message(request: Request[Any, Any, Any], chat_id: str, message_id: str) -> OkResponse:
    services = services_of(request)
    _require_chat(services, chat_id)
    return OkResponse(ok=services.runs.cancel(message_id))


def _delta_event(index: int, kind: str, text: str) -> ServerSentEventMessage:
    return ServerSentEventMessage(event="delta", id=str(index), data=json.dumps({"kind": kind, "text": text}))


# A reasoning model can go quiet for minutes before its first token.  An idle SSE connection is
# what intermediaries reap first, so send a comment line to keep it obviously alive.
_HEARTBEAT_SECONDS = 15.0


async def _stream_run(run: Run, services: AppServices, cursor: int) -> AsyncIterator[ServerSentEventMessage]:
    index = cursor
    while True:
        if index < len(run.chunks):
            chunk = run.chunks[index]
            yield _delta_event(index, chunk.kind.value, chunk.text)
            index += 1
            continue
        if run.is_finished:
            break
        try:
            async with asyncio.timeout(_HEARTBEAT_SECONDS):
                await run.wait_past(index)
        except TimeoutError:
            yield ServerSentEventMessage(comment="keep-alive")

    yield ServerSentEventMessage(
        event="status",
        data=json.dumps({"status": run.status.value, "error": run.error, "usage": _usage_dict(run.usage)}),
    )
    title = await _await_title(run, services)
    if title is not None:
        yield ServerSentEventMessage(event="title", data=json.dumps({"title": title}))
    yield ServerSentEventMessage(event="end", data="{}")


# A title is generated right after the response completes, so a client that just watched the
# stream is worth holding open briefly rather than making it poll for the new sidebar entry.
_TITLE_WAIT_SECONDS = 30.0


async def _await_title(run: Run, services: AppServices) -> str | None:
    if run.title is not None:
        return run.title
    if run.status is not MessageStatus.COMPLETE:
        return None
    chat = services.store.get_chat(run.chat_id)
    if chat is None or chat.title != "New chat":
        return None
    try:
        async with asyncio.timeout(_TITLE_WAIT_SECONDS):
            return await run.wait_for_title()
    except TimeoutError:
        return None


def _usage_dict(usage: Usage | None) -> dict[str, Any] | None:
    return attr.asdict(usage) if usage is not None else None


async def _replay_finished(message: Message) -> AsyncIterator[ServerSentEventMessage]:
    """No live run for this message — replay whatever the DB has and close."""
    index = 0
    if message.reasoning:
        yield _delta_event(index, "reasoning", message.reasoning)
        index += 1
    if message.content:
        yield _delta_event(index, "content", message.content)
    yield ServerSentEventMessage(
        event="status",
        data=json.dumps({"status": message.status.value, "error": message.error, "usage": _usage_dict(message.usage)}),
    )
    yield ServerSentEventMessage(event="end", data="{}")


@get("/chats/{chat_id:str}/messages/{message_id:str}/stream")
async def stream_message(
    request: Request[Any, Any, Any],
    chat_id: str,
    message_id: str,
    cursor: int = 0,
) -> ServerSentEvent:
    services = services_of(request)
    _require_chat(services, chat_id)
    message = services.store.get_message(message_id)
    if message is None or message.chat_id != chat_id:
        raise NotFoundException(detail="no such message")

    # EventSource resends its last id on reconnect; honour it over the query param.
    last_event_id = request.headers.get("last-event-id")
    if last_event_id and last_event_id.isdigit():
        cursor = int(last_event_id) + 1

    run = services.runs.get(message_id)
    if run is None:
        return ServerSentEvent(_replay_finished(message))
    return ServerSentEvent(_stream_run(run, services, max(0, cursor)))


@post("/chats/{chat_id:str}/share")
async def create_share(request: Request[Any, Any, Any], chat_id: str) -> ShareRef:
    services = services_of(request)
    _require_chat(services, chat_id)
    services.store.create_share(chat_id)
    ref = _share_ref(services, request, chat_id)
    assert ref is not None
    return ref


@delete("/chats/{chat_id:str}/share", status_code=200)
async def revoke_share(request: Request[Any, Any, Any], chat_id: str) -> OkResponse:
    services = services_of(request)
    _require_chat(services, chat_id)
    return OkResponse(ok=services.store.revoke_share(chat_id))


api_router = Router(
    path="/api",
    guards=[require_owner],
    route_handlers=[
        status,
        list_chats,
        create_chat,
        get_chat,
        update_chat,
        delete_chat,
        send_message,
        retry_message,
        stop_message,
        stream_message,
        create_share,
        revoke_share,
    ],
)
