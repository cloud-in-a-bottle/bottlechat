from enum import StrEnum

import attr


class Role(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class MessageStatus(StrEnum):
    COMPLETE = "complete"
    STREAMING = "streaming"
    ERROR = "error"
    CANCELLED = "cancelled"
    # A stream that was in flight when the server stopped.  Recovered at startup.
    INTERRUPTED = "interrupted"


class Effort(StrEnum):
    """Reasoning effort.  ``OFF`` omits ``reasoning_effort`` from the request entirely, which is
    what non-reasoning models need — some providers reject the field outright."""

    OFF = "off"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@attr.s(auto_attribs=True, frozen=True)
class Usage:
    prompt_tokens: int | None
    completion_tokens: int | None
    reasoning_tokens: int | None


@attr.s(auto_attribs=True, frozen=True)
class Message:
    id: str
    chat_id: str
    seq: int
    role: Role
    content: str
    reasoning: str
    status: MessageStatus
    model: str | None
    effort: Effort | None
    error: str | None
    usage: Usage | None
    created_at: str


@attr.s(auto_attribs=True, frozen=True)
class Chat:
    id: str
    title: str
    model: str | None
    effort: Effort
    created_at: str
    updated_at: str


@attr.s(auto_attribs=True, frozen=True)
class ChatSummary:
    id: str
    title: str
    updated_at: str
    # Populated by search; the matching text with <mark> around the hit.
    snippet: str | None = None


@attr.s(auto_attribs=True, frozen=True)
class ShareLink:
    token: str
    chat_id: str
    created_at: str


@attr.s(auto_attribs=True, frozen=True)
class ModelInfo:
    id: str
    provider: str
    label: str


@attr.s(auto_attribs=True, frozen=True)
class Settings:
    """Owner defaults for a new chat."""

    model: str | None
    effort: Effort
