import attr

from server.llm.client import ProviderState
from server.models import Chat
from server.models import ChatSummary
from server.models import Effort
from server.models import Message
from server.models import ModelInfo


@attr.s(auto_attribs=True, frozen=True)
class ProviderRef:
    app_name: str
    url: str


@attr.s(auto_attribs=True, frozen=True)
class Defaults:
    model: str | None
    effort: Effort


@attr.s(auto_attribs=True, frozen=True)
class StatusResponse:
    state: ProviderState
    models: list[ModelInfo]
    defaults: Defaults
    dashboard_url: str
    provider_repo_url: str
    detail: str | None = None
    grant_url: str | None = None
    provider: ProviderRef | None = None


@attr.s(auto_attribs=True, frozen=True)
class ShareRef:
    token: str
    url: str


@attr.s(auto_attribs=True, frozen=True)
class ChatDetail:
    chat: Chat
    messages: list[Message]
    share: ShareRef | None


@attr.s(auto_attribs=True, frozen=True)
class ChatListResponse:
    chats: list[ChatSummary]


@attr.s(auto_attribs=True, frozen=True)
class CreateChatRequest:
    model: str | None = None
    effort: Effort | None = None


@attr.s(auto_attribs=True, frozen=True)
class UpdateChatRequest:
    title: str | None = None
    model: str | None = None
    effort: Effort | None = None


@attr.s(auto_attribs=True, frozen=True)
class SendMessageRequest:
    content: str
    model: str | None = None
    effort: Effort | None = None


@attr.s(auto_attribs=True, frozen=True)
class RetryRequest:
    model: str | None = None
    effort: Effort | None = None


@attr.s(auto_attribs=True, frozen=True)
class TurnResponse:
    user_message: Message
    assistant_message: Message


@attr.s(auto_attribs=True, frozen=True)
class SharedMessage:
    role: str
    content: str
    reasoning: str
    model: str | None
    created_at: str


@attr.s(auto_attribs=True, frozen=True)
class SharedChat:
    title: str
    created_at: str
    updated_at: str
    messages: list[SharedMessage]


@attr.s(auto_attribs=True, frozen=True)
class OkResponse:
    ok: bool
