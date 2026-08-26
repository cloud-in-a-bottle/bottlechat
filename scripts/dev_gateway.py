#!/usr/bin/env python3
"""A stand-in for the OpenHost router + an openai-compat provider, for local development.

`just dev` points the app's OPENHOST_ROUTER_URL at this so the whole UI — including streaming and
reasoning — works without podman or real API keys.  Set DEV_GATEWAY_STATE to exercise the setup
screens: ready (default), no_provider, permission_required, no_models, error.  Set DEV_GATEWAY_DELAY
to slow the stream down.
"""

import json
import os
import random
import time
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer

PORT = int(os.environ.get("DEV_GATEWAY_PORT", "8099"))
STATE = os.environ.get("DEV_GATEWAY_STATE", "ready")
# Seconds between streamed words; raise it to watch the streaming UI in slow motion.
DELAY = float(os.environ.get("DEV_GATEWAY_DELAY", "0"))
MODELS = ["mock/echo-mini", "mock/thinker-pro", "other-vendor/fast-1"]

_REASONING = (
    "Let me work through this. The user is asking something I should answer directly and "
    "concretely. I'll structure the reply around a short explanation, a code sample, and a "
    "closing note so it's easy to skim. No need to over-hedge here."
)

_ANSWER = """Here's a **mock response** from the local dev gateway.

It streams token by token, so you can see how the UI behaves:

```python
def greet(name: str) -> str:
    return f"hello, {name}"
```

A few things worth checking:

1. Markdown renders, including `inline code`.
2. Long responses keep the view pinned to the bottom.
3. Stopping mid-stream keeps whatever arrived.

> The real gateway is Bifrost; this one just makes noises.
"""


def _chunks(text: str) -> list[str]:
    words = text.split(" ")
    out: list[str] = []
    for index, word in enumerate(words):
        out.append(word if index == 0 else " " + word)
    return out


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[dev-gateway] {fmt % args}", flush=True)

    def _send(self, status: int, payload: object) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.startswith("/api/services/v2/providers"):
            if STATE == "no_provider":
                self._send(200, {"providers": []})
            else:
                self._send(
                    200,
                    {
                        "providers": [
                            {
                                "app_id": "devgateway01",
                                "app_name": "bifrost-llm-gateway",
                                "service_version": "0.1.0",
                                "endpoint": "/service/",
                                "status": "running",
                                "is_default": True,
                            }
                        ]
                    },
                )
            return
        if self.path.endswith("/openai/v1/models"):
            if (refusal := self._refuse()) is not None:
                self._send(*refusal)
                return
            models = [] if STATE == "no_models" else MODELS
            self._send(200, {"object": "list", "data": [{"id": m, "object": "model"} for m in models]})
            return
        self._send(404, {"error": "not_found", "path": self.path})

    def do_POST(self) -> None:
        if not self.path.endswith("/openai/v1/chat/completions"):
            self._send(404, {"error": "not_found", "path": self.path})
            return
        if (refusal := self._refuse()) is not None:
            self._send(*refusal)
            return
        length = int(self.headers.get("content-length", "0"))
        request = json.loads(self.rfile.read(length) or b"{}")
        if request.get("stream"):
            self._stream(request)
        else:
            self._send(
                200,
                {
                    "choices": [{"message": {"role": "assistant", "content": "Mock title"}}],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 3},
                },
            )

    def _refuse(self) -> tuple[int, object] | None:
        if STATE == "no_provider":
            return 503, {"status_code": 503, "detail": "no provider", "extra": {"code": "service_not_available"}}
        if STATE == "permission_required":
            return 403, {
                "error": "permission_required",
                "required_grant": {
                    "grant": "full_access",
                    "scope": "global",
                    "grant_url": "http://localhost:8099/approve",
                },
            }
        if STATE == "error":
            return 502, {"error": {"message": "upstream provider refused the connection"}}
        return None

    def _stream(self, request: dict[str, object]) -> None:
        # SSE has no Content-Length, so HTTP/1.1 needs chunked framing — without it the client
        # can't tell where the response ends and just hangs.
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("cache-control", "no-cache")
        self.send_header("transfer-encoding", "chunked")
        self.end_headers()

        def write_chunk(data: bytes) -> None:
            self.wfile.write(f"{len(data):X}\r\n".encode() + data + b"\r\n")

        def emit(payload: dict[str, object]) -> None:
            write_chunk(f"data: {json.dumps(payload)}\n\n".encode())

        def delta(field: str, text: str) -> None:
            emit({"choices": [{"index": 0, "delta": {field: text}}]})

        thinks = request.get("reasoning_effort") is not None or "thinker" in str(request.get("model", ""))
        try:
            if thinks:
                for piece in _chunks(_REASONING):
                    delta("reasoning_content", piece)
                    time.sleep(DELAY or random.uniform(0.01, 0.03))
            for piece in _chunks(_ANSWER):
                delta("content", piece)
                time.sleep(DELAY or random.uniform(0.01, 0.04))
            emit(
                {
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                    "usage": {
                        "prompt_tokens": 42,
                        "completion_tokens": 210,
                        "completion_tokens_details": {"reasoning_tokens": 60 if thinks else 0},
                    },
                }
            )
            write_chunk(b"data: [DONE]\n\n")
            self.wfile.write(b"0\r\n\r\n")
        except (BrokenPipeError, ConnectionResetError):
            print("[dev-gateway] client disconnected mid-stream", flush=True)
            self.close_connection = True


def main() -> None:
    print(f"[dev-gateway] listening on http://127.0.0.1:{PORT} (state={STATE})", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
