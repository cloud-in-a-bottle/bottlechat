import json
import time
from collections.abc import AsyncIterator
from collections.abc import Sequence
from enum import StrEnum
from typing import Any

import attr
import httpx
from loguru import logger

from server.config import LLM_SERVICE_URL
from server.config import LLM_SHORTNAME
from server.config import Config
from server.llm.events import Completed
from server.llm.events import Delta
from server.llm.events import DeltaKind
from server.llm.events import Failed
from server.llm.events import StreamEvent
from server.models import Effort
from server.models import ModelInfo
from server.models import Usage

_MODELS_TIMEOUT = httpx.Timeout(20.0)
# Generous: a reasoning model can think for minutes before the first token.  The read timeout
# applies per-chunk once streaming starts, so a healthy stream never trips it.
_CHAT_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=60.0, pool=10.0)


class ProviderState(StrEnum):
    READY = "ready"
    # Nothing on this compute space provides the openai-compat service.
    NO_PROVIDER = "no_provider"
    # A provider exists but hasn't been granted to this app.
    PERMISSION_REQUIRED = "permission_required"
    # The provider answered, but the owner hasn't configured any models in it.
    NO_MODELS = "no_models"
    # The provider is installed but broken/unreachable.
    ERROR = "error"


@attr.s(auto_attribs=True, frozen=True)
class ProviderStatus:
    state: ProviderState
    models: list[ModelInfo]
    detail: str | None = None
    grant_url: str | None = None
    provider_app_name: str | None = None


@attr.s(auto_attribs=True, frozen=True)
class ChatRequest:
    model: str
    effort: Effort
    messages: list["ChatTurn"]


@attr.s(auto_attribs=True, frozen=True)
class ChatTurn:
    role: str
    content: str


def _text_of(value: object) -> str:
    """Pull display text out of a delta field.

    Providers disagree on shape: a bare string, a list of content parts, or a dict with a
    ``text``/``content`` key.  Anything unrecognized contributes nothing rather than leaking
    ``repr`` output into the transcript.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("text", "thinking", "content"):
            inner = value.get(key)
            if isinstance(inner, str):
                return inner
        return ""
    if isinstance(value, list):
        return "".join(_text_of(part) for part in value)
    return ""


def _usage_from_payload(payload: dict[str, Any]) -> Usage | None:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return None
    details = usage.get("completion_tokens_details")
    reasoning = details.get("reasoning_tokens") if isinstance(details, dict) else None
    return Usage(
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        reasoning_tokens=reasoning,
    )


def _model_info(model_id: str) -> ModelInfo:
    provider, _, rest = model_id.partition("/")
    if not rest:
        return ModelInfo(id=model_id, provider="other", label=model_id)
    return ModelInfo(id=model_id, provider=provider, label=rest)


def _error_detail(response_body: str, status: int) -> str:
    try:
        body = json.loads(response_body)
    except json.JSONDecodeError:
        return f"HTTP {status}: {response_body[:300]}"
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return str(error["message"])
        if isinstance(error, str):
            return error
        if isinstance(body.get("detail"), str):
            return str(body["detail"])
    return f"HTTP {status}: {response_body[:300]}"


class LlmClient:
    """Talks to the openai-compat provider through the OpenHost service router.

    Every call goes to ``$OPENHOST_ROUTER_URL/api/services/v2/call/llm/...`` with this app's
    token; the router resolves the provider and injects the permission grants.
    """

    def __init__(self, config: Config, client: httpx.AsyncClient) -> None:
        self._config = config
        self._client = client

    def _service_url(self, path: str) -> str:
        return f"{self._config.router_url}/api/services/v2/call/{LLM_SHORTNAME}/{path.lstrip('/')}"

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._config.app_token}"}

    async def provider_app_name(self) -> str | None:
        """The app name of the provider the router would route us to, for building 'go configure
        it' links.  ``None`` when discovery fails or nothing provides the service."""
        try:
            response = await self._client.get(
                f"{self._config.router_url}/api/services/v2/providers",
                params={"service": LLM_SERVICE_URL},
                headers=self._headers,
                timeout=_MODELS_TIMEOUT,
            )
        except httpx.HTTPError as e:
            logger.warning("provider discovery failed: {}", e)
            return None
        if response.status_code != 200:
            return None
        providers = response.json().get("providers", [])
        if not providers:
            return None
        default = next((p for p in providers if p.get("is_default")), providers[0])
        name = default.get("app_name")
        return str(name) if name else None

    async def status(self) -> ProviderStatus:
        try:
            response = await self._client.get(
                self._service_url("openai/v1/models"), headers=self._headers, timeout=_MODELS_TIMEOUT
            )
        except httpx.HTTPError as e:
            return ProviderStatus(state=ProviderState.ERROR, models=[], detail=f"Could not reach the router: {e}")

        if response.status_code == 503:
            return ProviderStatus(state=ProviderState.NO_PROVIDER, models=[])
        if response.status_code == 404:
            # The shortname isn't declared — a manifest bug, not an owner-fixable state.
            return ProviderStatus(
                state=ProviderState.ERROR, models=[], detail=_error_detail(response.text, response.status_code)
            )
        if response.status_code == 403:
            return ProviderStatus(
                state=ProviderState.PERMISSION_REQUIRED,
                models=[],
                grant_url=_grant_url_from(response.text),
                provider_app_name=await self.provider_app_name(),
            )
        if response.status_code != 200:
            return ProviderStatus(
                state=ProviderState.ERROR,
                models=[],
                detail=_error_detail(response.text, response.status_code),
                provider_app_name=await self.provider_app_name(),
            )

        try:
            data = response.json().get("data")
        except json.JSONDecodeError:
            return ProviderStatus(
                state=ProviderState.ERROR, models=[], detail="The provider returned a non-JSON model list."
            )
        models = [_model_info(str(m["id"])) for m in data if isinstance(m, dict) and m.get("id")] if data else []
        models.sort(key=lambda m: (m.provider, m.label))
        provider_app_name = await self.provider_app_name()
        if not models:
            return ProviderStatus(state=ProviderState.NO_MODELS, models=[], provider_app_name=provider_app_name)
        return ProviderStatus(state=ProviderState.READY, models=models, provider_app_name=provider_app_name)

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        payload: dict[str, Any] = {
            "model": request.model,
            "stream": True,
            "stream_options": {"include_usage": True},
            "messages": [{"role": t.role, "content": t.content} for t in request.messages],
        }
        if request.effort is not Effort.OFF:
            payload["reasoning_effort"] = request.effort.value

        try:
            async with self._client.stream(
                "POST",
                self._service_url("openai/v1/chat/completions"),
                json=payload,
                headers=self._headers,
                timeout=_CHAT_TIMEOUT,
            ) as response:
                if response.status_code != 200:
                    body = (await response.aread()).decode("utf-8", "replace")
                    yield Failed(message=_error_detail(body, response.status_code))
                    return
                usage: Usage | None = None
                async for line in response.aiter_lines():
                    for event in _parse_sse_line(line):
                        if isinstance(event, Completed):
                            usage = event.usage or usage
                            continue
                        if isinstance(event, Failed):
                            yield event
                            return
                        yield event
        except httpx.HTTPError as e:
            yield Failed(message=f"Connection to the model provider failed: {e}")
            return
        yield Completed(usage=usage)

    async def generate_title(self, first_user_message: str, model: str) -> str | None:
        """A short title for the chat.  Best-effort: a failure just leaves the fallback title."""
        prompt = (
            "Summarize this chat opener as a title of at most 6 words. Reply with the title only — "
            "no quotes, no punctuation at the end.\n\n" + first_user_message[:2000]
        )
        try:
            response = await self._client.post(
                self._service_url("openai/v1/chat/completions"),
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 10000,
                    "stream": False,
                },
                headers=self._headers,
                timeout=httpx.Timeout(60.0),
            )
        except httpx.HTTPError as e:
            logger.warning("title generation failed: {}", e)
            return None
        if response.status_code != 200:
            logger.warning("title generation returned {}: {}", response.status_code, response.text[:200])
            return None
        choices = response.json().get("choices") or []
        if not choices:
            return None
        title = _text_of(choices[0].get("message", {}).get("content")).strip().strip('"').strip()
        first_line = title.splitlines()[0].strip() if title else ""
        return first_line[:80] or None


def _grant_url_from(body: str) -> str | None:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    required = parsed.get("required_grant")
    if isinstance(required, dict) and isinstance(required.get("grant_url"), str):
        return str(required["grant_url"])
    return None


def _parse_sse_line(line: str) -> Sequence[StreamEvent]:
    if not line.startswith("data:"):
        return ()
    data = line[len("data:") :].strip()
    if not data or data == "[DONE]":
        return ()
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        logger.warning("skipping unparseable SSE chunk: {}", data[:200])
        return ()
    if not isinstance(payload, dict):
        return ()

    if isinstance(payload.get("error"), (dict, str)):
        return (Failed(message=_error_detail(data, 200)),)

    events: list[StreamEvent] = []
    for choice in payload.get("choices") or []:
        delta = choice.get("delta")
        if not isinstance(delta, dict):
            continue
        for key in ("reasoning_content", "reasoning", "thinking"):
            if key in delta and (text := _text_of(delta[key])):
                events.append(Delta(kind=DeltaKind.REASONING, text=text))
                break
        if text := _text_of(delta.get("content")):
            events.append(Delta(kind=DeltaKind.CONTENT, text=text))

    # Usage arrives on its own trailing chunk when stream_options.include_usage is set.
    if (usage := _usage_from_payload(payload)) is not None:
        events.append(Completed(usage=usage))
    return events


class ProviderStatusCache:
    """The model list barely changes, and the frontend asks for it on every page load and
    reconnect — each miss costs two round trips through the router."""

    def __init__(self, client: LlmClient, ttl_seconds: float = 15.0) -> None:
        self._client = client
        self._ttl = ttl_seconds
        self._cached: tuple[float, ProviderStatus] | None = None

    async def get(self, refresh: bool = False) -> ProviderStatus:
        if not refresh and self._cached is not None and time.monotonic() - self._cached[0] < self._ttl:
            return self._cached[1]
        status = await self._client.status()
        self._cached = (time.monotonic(), status)
        return status
