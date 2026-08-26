import json
import time
from collections.abc import Callable
from collections.abc import Iterator

import httpx
import pytest
import requests
from conftest import LLM_SERVICE_URL
from openhost_test_harness import OpenhostStack


def _sse_events(response: requests.Response) -> Iterator[tuple[str, dict[str, object]]]:
    """Yield (event, data) pairs from a streaming SSE response."""
    event = "message"
    for raw in response.iter_lines(decode_unicode=True):
        line = raw or ""
        if line.startswith("event:"):
            event = line[len("event:") :].strip()
        elif line.startswith("data:"):
            payload = line[len("data:") :].strip()
            yield event, json.loads(payload) if payload else {}
            event = "message"


def _start_chat(stack: OpenhostStack, effort: str = "off", model: str = "mock/fast-1") -> str:
    response = stack.owner_session.post(f"{stack.url}/api/chats", json={"model": model, "effort": effort})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _send(stack: OpenhostStack, chat_id: str, content: str) -> str:
    response = stack.owner_session.post(f"{stack.url}/api/chats/{chat_id}/messages", json={"content": content})
    assert response.status_code == 201, response.text
    return str(response.json()["assistant_message"]["id"])


def _drain(stack: OpenhostStack, chat_id: str, message_id: str) -> dict[str, object]:
    """Consume a response stream to its end, returning the accumulated result."""
    content, reasoning, title = "", "", None
    status: dict[str, object] = {}
    with stack.owner_session.get(
        f"{stack.url}/api/chats/{chat_id}/messages/{message_id}/stream", stream=True, timeout=90
    ) as response:
        assert response.status_code == 200, response.text
        for event, data in _sse_events(response):
            if event == "delta":
                if data["kind"] == "content":
                    content += str(data["text"])
                else:
                    reasoning += str(data["text"])
            elif event == "status":
                status = data
            elif event == "title":
                title = data["title"]
            elif event == "end":
                break
    return {"content": content, "reasoning": reasoning, "title": title, **status}


def test_health_is_reachable_without_auth(stack: OpenhostStack) -> None:
    response = httpx.get(f"{stack.app_url}/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_the_api_is_owner_only(stack: OpenhostStack) -> None:
    """Through the router an anonymous caller is bounced to /login; straight at the container,
    where the router isn't there to gate anything, the app's own header check refuses."""
    through_router = requests.get(f"{stack.url}/api/chats", allow_redirects=False, timeout=10)
    assert through_router.status_code in (302, 303, 307)
    assert "/login" in through_router.headers.get("location", "")

    direct = httpx.get(f"{stack.app_url}/api/chats")
    assert direct.status_code == 401


def test_status_reports_the_gateways_models(stack: OpenhostStack) -> None:
    response = stack.owner_session.get(f"{stack.url}/api/status?refresh=true")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "ready"
    assert [m["id"] for m in body["models"]] == ["mock/fast-1", "mock/thinker-1"]
    assert body["provider"]["app_name"] == "mock-gateway"


def test_a_full_turn_streams_and_is_persisted(stack: OpenhostStack) -> None:
    chat_id = _start_chat(stack)
    message_id = _send(stack, chat_id, "how do python generators work")
    result = _drain(stack, chat_id, message_id)

    assert result["status"] == "complete"
    assert "Generators are lazy iterators." in str(result["content"])
    assert result["title"] == "Python generators"

    detail = stack.owner_session.get(f"{stack.url}/api/chats/{chat_id}").json()
    assert detail["chat"]["title"] == "Python generators"
    assistant = detail["messages"][1]
    assert assistant["status"] == "complete"
    assert assistant["content"] == result["content"]
    assert assistant["usage"]["completion_tokens"] == 23


def test_reasoning_is_streamed_and_stored_separately(stack: OpenhostStack) -> None:
    chat_id = _start_chat(stack, effort="high", model="mock/thinker-1")
    result = _drain(stack, chat_id, _send(stack, chat_id, "think about this"))

    assert "The user wants a short explanation." in str(result["reasoning"])
    assert "Generators are lazy iterators." in str(result["content"])

    assistant = stack.owner_session.get(f"{stack.url}/api/chats/{chat_id}").json()["messages"][1]
    assert assistant["reasoning"].startswith("The user wants")
    assert assistant["reasoning"] not in assistant["content"]
    assert assistant["usage"]["reasoning_tokens"] == 7


def test_a_finished_response_can_be_replayed_by_a_second_tab(stack: OpenhostStack) -> None:
    chat_id = _start_chat(stack)
    message_id = _send(stack, chat_id, "replay me")
    first = _drain(stack, chat_id, message_id)
    # Long enough after the fact that the in-memory run may be gone; the DB copy must still
    # produce an identical stream for a tab that opens the chat later.
    second = _drain(stack, chat_id, message_id)
    assert second["content"] == first["content"]
    assert second["status"] == "complete"


def test_stopping_mid_stream_keeps_the_partial_text(
    stack: OpenhostStack, gateway_control: Callable[..., None]
) -> None:
    gateway_control(chunk_delay=0.35)
    chat_id = _start_chat(stack)
    message_id = _send(stack, chat_id, "stop me")

    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        message = stack.owner_session.get(f"{stack.url}/api/chats/{chat_id}").json()["messages"][1]
        if message["content"]:
            break
        time.sleep(0.2)

    stopped = stack.owner_session.post(f"{stack.url}/api/chats/{chat_id}/messages/{message_id}/stop")
    assert stopped.status_code == 200 and stopped.json()["ok"] is True

    result = _drain(stack, chat_id, message_id)
    assert result["status"] == "cancelled"
    assert 0 < len(str(result["content"])) < 60

    stored = stack.owner_session.get(f"{stack.url}/api/chats/{chat_id}").json()["messages"][1]
    assert stored["status"] == "cancelled"
    assert stored["content"] == result["content"]


def test_a_gateway_failure_is_recorded_on_the_message(
    stack: OpenhostStack, gateway_control: Callable[..., None]
) -> None:
    gateway_control(chat_status=503, chat_error="upstream model is unavailable")
    chat_id = _start_chat(stack)
    result = _drain(stack, chat_id, _send(stack, chat_id, "this will fail"))
    assert result["status"] == "error"
    assert "upstream model is unavailable" in str(result["error"])

    gateway_control(chat_status=200)
    message_id = stack.owner_session.get(f"{stack.url}/api/chats/{chat_id}").json()["messages"][1]["id"]
    retried = stack.owner_session.post(f"{stack.url}/api/chats/{chat_id}/messages/{message_id}/retry", json={})
    assert retried.status_code == 201, retried.text
    assert _drain(stack, chat_id, message_id)["status"] == "complete"


def test_no_models_configured_is_reported_as_its_own_state(
    stack: OpenhostStack, gateway_control: Callable[..., None]
) -> None:
    gateway_control(models=[])
    body = stack.owner_session.get(f"{stack.url}/api/status?refresh=true").json()
    assert body["state"] == "no_models"
    assert body["models"] == []
    assert body["provider"]["app_name"] == "mock-gateway"


def test_without_the_grant_the_app_asks_for_permission(stack: OpenhostStack) -> None:
    revoke = stack.owner_session.post(
        f"{stack.router_url}/api/permissions/v2/revoke",
        json={"app_id": stack.app_id, "service_url": LLM_SERVICE_URL, "grant": "full_access"},
    )
    assert revoke.status_code == 200, revoke.text
    try:
        body = stack.owner_session.get(f"{stack.url}/api/status?refresh=true").json()
        assert body["state"] == "permission_required"
        assert "/approve-permissions-v2" in body["grant_url"]
    finally:
        stack.grant(stack.app_id, LLM_SERVICE_URL, "full_access")
    assert stack.owner_session.get(f"{stack.url}/api/status?refresh=true").json()["state"] == "ready"


def test_chats_are_searchable_by_message_text(stack: OpenhostStack) -> None:
    chat_id = _start_chat(stack)
    _drain(stack, chat_id, _send(stack, chat_id, "a distinctive phrase about marmosets"))

    hits = stack.owner_session.get(f"{stack.url}/api/chats?q=marmosets").json()["chats"]
    assert [c["id"] for c in hits] == [chat_id]
    assert "<mark>marmosets</mark>" in hits[0]["snippet"]

    assert stack.owner_session.get(f"{stack.url}/api/chats?q=zzzznotathing").json()["chats"] == []


def test_share_links_are_public_and_revocable(stack: OpenhostStack) -> None:
    chat_id = _start_chat(stack)
    _drain(stack, chat_id, _send(stack, chat_id, "share me"))

    created = stack.owner_session.post(f"{stack.url}/api/chats/{chat_id}/share")
    assert created.status_code == 201, created.text
    token = created.json()["token"]
    assert len(token) >= 24
    assert created.json()["url"].endswith(f"/share/{token}")

    # A brand new session: no owner cookie, exactly what a recipient has.
    anonymous = requests.Session()
    shared = anonymous.get(f"{stack.url}/share/api/{token}", timeout=10)
    assert shared.status_code == 200, shared.text
    body = shared.json()
    assert body["messages"][0]["content"] == "share me"
    assert "Generators are lazy iterators." in body["messages"][1]["content"]

    page = anonymous.get(f"{stack.url}/share/{token}", timeout=10)
    assert page.status_code == 200
    assert '<div id="root">' in page.text

    assert anonymous.get(f"{stack.url}/share/api/not-a-real-token", timeout=10).status_code == 404

    revoked = stack.owner_session.delete(f"{stack.url}/api/chats/{chat_id}/share")
    assert revoked.status_code == 200 and revoked.json()["ok"] is True
    assert anonymous.get(f"{stack.url}/share/api/{token}", timeout=10).status_code == 404


def test_a_share_link_shows_messages_added_after_it_was_created(stack: OpenhostStack) -> None:
    chat_id = _start_chat(stack)
    _drain(stack, chat_id, _send(stack, chat_id, "first question"))
    token = stack.owner_session.post(f"{stack.url}/api/chats/{chat_id}/share").json()["token"]
    _drain(stack, chat_id, _send(stack, chat_id, "second question"))

    anonymous = requests.Session()
    messages = anonymous.get(f"{stack.url}/share/api/{token}", timeout=10).json()["messages"]
    assert [m["content"] for m in messages if m["role"] == "user"] == ["first question", "second question"]


def test_sharing_does_not_expose_other_chats(stack: OpenhostStack) -> None:
    shared_id = _start_chat(stack)
    _drain(stack, shared_id, _send(stack, shared_id, "public thing"))
    private_id = _start_chat(stack)
    _drain(stack, private_id, _send(stack, private_id, "private thing"))
    token = stack.owner_session.post(f"{stack.url}/api/chats/{shared_id}/share").json()["token"]

    anonymous = requests.Session()
    body = anonymous.get(f"{stack.url}/share/api/{token}", timeout=10).json()
    assert "private thing" not in json.dumps(body)
    assert anonymous.get(f"{stack.url}/api/chats/{private_id}", allow_redirects=False, timeout=10).status_code != 200


def test_deleting_a_chat_removes_it(stack: OpenhostStack) -> None:
    chat_id = _start_chat(stack)
    _drain(stack, chat_id, _send(stack, chat_id, "delete me"))
    assert stack.owner_session.delete(f"{stack.url}/api/chats/{chat_id}").status_code == 200
    assert stack.owner_session.get(f"{stack.url}/api/chats/{chat_id}").status_code == 404
    assert stack.owner_session.get(f"{stack.url}/api/chats?q=delete").json()["chats"] == []


def test_renaming_a_chat_sticks(stack: OpenhostStack) -> None:
    chat_id = _start_chat(stack)
    _drain(stack, chat_id, _send(stack, chat_id, "rename me"))
    renamed = stack.owner_session.patch(f"{stack.url}/api/chats/{chat_id}", json={"title": "  My title  "})
    assert renamed.status_code == 200 and renamed.json()["title"] == "My title"
    assert stack.owner_session.patch(f"{stack.url}/api/chats/{chat_id}", json={"title": "  "}).status_code == 400


def test_the_spa_shell_and_pwa_assets_are_served(stack: OpenhostStack) -> None:
    for path in ("/", "/c/some-chat-id"):
        page = stack.owner_session.get(f"{stack.url}{path}")
        assert page.status_code == 200, path
        assert '<div id="root">' in page.text

    manifest = stack.owner_session.get(f"{stack.url}/manifest.webmanifest")
    assert manifest.status_code == 200
    assert manifest.json()["display"] == "standalone"

    assert stack.owner_session.get(f"{stack.url}/sw.js").status_code == 200
    assert stack.owner_session.get(f"{stack.url}/icons/icon-192.png").status_code == 200


@pytest.mark.parametrize("payload", [{"content": ""}, {"content": "   "}])
def test_empty_messages_are_rejected(stack: OpenhostStack, payload: dict[str, str]) -> None:
    chat_id = _start_chat(stack)
    assert stack.owner_session.post(f"{stack.url}/api/chats/{chat_id}/messages", json=payload).status_code == 400


def test_a_second_send_while_streaming_is_refused(stack: OpenhostStack, gateway_control: Callable[..., None]) -> None:
    gateway_control(chunk_delay=0.3)
    chat_id = _start_chat(stack)
    message_id = _send(stack, chat_id, "first")

    second = stack.owner_session.post(f"{stack.url}/api/chats/{chat_id}/messages", json={"content": "second"})
    assert second.status_code == 400
    assert "finish" in second.json()["detail"]

    _drain(stack, chat_id, message_id)
    assert len(stack.owner_session.get(f"{stack.url}/api/chats/{chat_id}").json()["messages"]) == 2
