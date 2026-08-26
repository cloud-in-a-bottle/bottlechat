import asyncio
import json
from collections.abc import Callable
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx

from server.config import Config
from server.llm.client import ChatRequest
from server.llm.client import ChatTurn
from server.llm.client import LlmClient
from server.llm.client import ProviderState
from server.llm.events import Completed
from server.llm.events import Delta
from server.llm.events import DeltaKind
from server.llm.events import Failed
from server.models import Effort

Route = Callable[[httpx.Request], httpx.Response]


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    """pytest-playwright keeps an event loop running for the whole session, so async work in
    these tests gets its own thread and its own loop."""
    with ThreadPoolExecutor(1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _config(tmp_path: Path) -> Config:
    return Config(
        db_path=tmp_path / "chats.sqlite",
        router_url="http://router.test",
        app_token="token",
        app_name="bottlechat",
        zone_domain="zone.test",
        frontend_dir=tmp_path / "dist",
    )


def _client(tmp_path: Path, handler: Route) -> LlmClient:
    return LlmClient(_config(tmp_path), httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def _providers_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={"providers": [{"app_id": "abc", "app_name": "bifrost-llm-gateway", "is_default": True}]},
    )


def _sse(lines: list[dict[str, object]]) -> str:
    return "".join(f"data: {json.dumps(line)}\n\n" for line in lines) + "data: [DONE]\n\n"


def test_models_are_grouped_and_sorted(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "providers" in request.url.path:
            return _providers_response()
        return httpx.Response(200, json={"data": [{"id": "openai/gpt-5"}, {"id": "anthropic/claude"}]})

    status = run(_client(tmp_path, handler).status())
    assert status.state is ProviderState.READY
    assert [m.id for m in status.models] == ["anthropic/claude", "openai/gpt-5"]
    assert status.models[0].provider == "anthropic"
    assert status.models[0].label == "claude"
    assert status.provider_app_name == "bifrost-llm-gateway"


def test_no_provider_when_the_router_cannot_resolve_one(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "no provider", "extra": {"code": "service_not_available"}})

    status = run(_client(tmp_path, handler).status())
    assert status.state is ProviderState.NO_PROVIDER
    assert status.models == []


def test_permission_required_surfaces_the_grant_url(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "providers" in request.url.path:
            return _providers_response()
        return httpx.Response(
            403,
            json={
                "error": "permission_required",
                "required_grant": {
                    "grant": "full_access",
                    "scope": "global",
                    "grant_url": "https://zone.test/approve-permissions-v2?app=abc",
                },
            },
        )

    status = run(_client(tmp_path, handler).status())
    assert status.state is ProviderState.PERMISSION_REQUIRED
    assert status.grant_url == "https://zone.test/approve-permissions-v2?app=abc"


def test_empty_model_list_is_its_own_state(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "providers" in request.url.path:
            return _providers_response()
        return httpx.Response(200, json={"object": "list", "data": []})

    status = run(_client(tmp_path, handler).status())
    assert status.state is ProviderState.NO_MODELS
    assert status.provider_app_name == "bifrost-llm-gateway"


def test_gateway_failure_reports_the_upstream_message(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "providers" in request.url.path:
            return _providers_response()
        return httpx.Response(502, json={"error": {"message": "bifrost is starting up"}})

    status = run(_client(tmp_path, handler).status())
    assert status.state is ProviderState.ERROR
    assert status.detail == "bifrost is starting up"


def test_unreachable_router_is_an_error_not_a_crash(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    status = run(_client(tmp_path, handler).status())
    assert status.state is ProviderState.ERROR
    assert "Could not reach the router" in (status.detail or "")


def _collect(client: LlmClient, effort: Effort = Effort.OFF) -> list[object]:
    request = ChatRequest(model="mock/fast-1", effort=effort, messages=[ChatTurn(role="user", content="hi")])

    async def collect() -> list[object]:
        return [event async for event in client.stream_chat(request)]

    return run(collect())


def test_streaming_separates_reasoning_from_content(tmp_path: Path) -> None:
    body = _sse(
        [
            {"choices": [{"delta": {"reasoning_content": "think "}}]},
            {"choices": [{"delta": {"content": "hello "}}]},
            {"choices": [{"delta": {"content": "world"}}]},
            {"choices": [{"delta": {}}], "usage": {"prompt_tokens": 4, "completion_tokens": 2}},
        ]
    )
    events = _collect(_client(tmp_path, lambda _: httpx.Response(200, text=body)))
    assert events[0] == Delta(kind=DeltaKind.REASONING, text="think ")
    assert [e.text for e in events if isinstance(e, Delta) and e.kind is DeltaKind.CONTENT] == ["hello ", "world"]
    final = events[-1]
    assert isinstance(final, Completed)
    assert final.usage is not None and final.usage.prompt_tokens == 4


def test_streaming_accepts_the_other_reasoning_field_names(tmp_path: Path) -> None:
    for field in ("reasoning", "thinking"):
        body = _sse([{"choices": [{"delta": {field: "pondering"}}]}])
        events = _collect(_client(tmp_path, lambda _, b=body: httpx.Response(200, text=b)))
        assert Delta(kind=DeltaKind.REASONING, text="pondering") in events


def test_streaming_accepts_content_as_a_list_of_parts(tmp_path: Path) -> None:
    body = _sse([{"choices": [{"delta": {"content": [{"type": "text", "text": "chunked"}]}}]}])
    events = _collect(_client(tmp_path, lambda _: httpx.Response(200, text=body)))
    assert Delta(kind=DeltaKind.CONTENT, text="chunked") in events


def test_a_mid_stream_error_chunk_fails_the_response(tmp_path: Path) -> None:
    body = _sse([{"choices": [{"delta": {"content": "partial"}}]}, {"error": {"message": "rate limited"}}])
    events = _collect(_client(tmp_path, lambda _: httpx.Response(200, text=body)))
    assert events[-1] == Failed(message="rate limited")


def test_a_non_200_response_fails_before_any_delta(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "slow down"}})

    events = _collect(_client(tmp_path, handler))
    assert events == [Failed(message="slow down")]


def test_reasoning_effort_is_sent_only_when_enabled(tmp_path: Path) -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, text=_sse([{"choices": [{"delta": {"content": "ok"}}]}]))

    _collect(_client(tmp_path, handler), effort=Effort.OFF)
    _collect(_client(tmp_path, handler), effort=Effort.HIGH)
    assert "reasoning_effort" not in seen[0]
    assert seen[1]["reasoning_effort"] == "high"


def test_service_calls_carry_the_app_token(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": []})

    run(_client(tmp_path, handler).status())
    assert seen[0].headers["authorization"] == "Bearer token"
    assert seen[0].url.path == "/api/services/v2/call/llm/openai/v1/models"
