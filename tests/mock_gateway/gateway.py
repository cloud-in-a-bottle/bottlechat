"""An openai-compat provider that returns canned responses, for testing consumers.

Mirrors the real gateway's contract: the service interface lives under /service/, requires a
`full_access` grant in X-OpenHost-Permissions, and speaks the OpenAI chat-completions schema
(including `reasoning_content` deltas).  Tests drive its behaviour through /control, which is
owner-gated by OpenHost like any other non-public route.
"""

import json
import time
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer

SERVICE_PREFIX = "/service"

# Mutated by POST /control.
STATE: dict[str, object] = {
    "models": ["mock/fast-1", "mock/thinker-1"],
    "chat_status": 200,
    "chat_error": "the upstream provider rejected the request",
    # Seconds to sleep between streamed chunks — lets a test stop a response mid-flight.
    "chunk_delay": 0.0,
}

ANSWER = "Generators are lazy iterators.\n\n```python\ndef counter():\n    yield 1\n```\n\nThat is all."
REASONING = "The user wants a short explanation. Keep it to a definition plus one example."


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[mock-gateway] {fmt % args}", flush=True)

    def _json(self, status: int, payload: object) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _has_grant(self) -> bool:
        raw = self.headers.get("X-OpenHost-Permissions", "[]")
        try:
            grants = json.loads(raw)
        except json.JSONDecodeError:
            return False
        return any(isinstance(g, dict) and g.get("grant") == "full_access" for g in grants)

    def _deny(self) -> None:
        self._json(
            403,
            {
                "error": "permission_required",
                "required_grant": {"grant": "full_access", "scope": "global"},
            },
        )

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json(200, {"status": "ok"})
            return
        if self.path == f"{SERVICE_PREFIX}/openai/v1/models":
            if not self._has_grant():
                self._deny()
                return
            models = STATE["models"]
            assert isinstance(models, list)
            self._json(200, {"object": "list", "data": [{"id": m, "object": "model"} for m in models]})
            return
        self._json(404, {"error": "not_found", "path": self.path})

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(length) or b"{}"

        if self.path == "/control":
            STATE.update(json.loads(body))
            self._json(200, {"ok": True, "state": STATE})
            return

        if self.path != f"{SERVICE_PREFIX}/openai/v1/chat/completions":
            self._json(404, {"error": "not_found", "path": self.path})
            return
        if not self._has_grant():
            self._deny()
            return
        if STATE["chat_status"] != 200:
            status = STATE["chat_status"]
            assert isinstance(status, int)
            self._json(status, {"error": {"message": STATE["chat_error"]}})
            return

        request = json.loads(body)
        if request.get("stream"):
            self._stream(request)
        else:
            self._json(
                200,
                {
                    "choices": [{"message": {"role": "assistant", "content": "Python generators"}}],
                    "usage": {"prompt_tokens": 9, "completion_tokens": 2},
                },
            )

    def _stream(self, request: dict[str, object]) -> None:
        # SSE carries no Content-Length, so HTTP/1.1 requires chunked framing.
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("cache-control", "no-cache")
        self.send_header("transfer-encoding", "chunked")
        self.end_headers()

        def chunk(data: bytes) -> None:
            self.wfile.write(f"{len(data):X}\r\n".encode() + data + b"\r\n")

        def emit(payload: dict[str, object]) -> None:
            chunk(f"data: {json.dumps(payload)}\n\n".encode())

        delay = STATE["chunk_delay"]
        assert isinstance(delay, (int, float))
        thinks = request.get("reasoning_effort") is not None
        try:
            if thinks:
                for word in REASONING.split(" "):
                    emit({"choices": [{"index": 0, "delta": {"reasoning_content": word + " "}}]})
                    time.sleep(delay)
            for word in ANSWER.split(" "):
                emit({"choices": [{"index": 0, "delta": {"content": word + " "}}]})
                time.sleep(delay)
            emit(
                {
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                    "usage": {
                        "prompt_tokens": 11,
                        "completion_tokens": 23,
                        "completion_tokens_details": {"reasoning_tokens": 7 if thinks else 0},
                    },
                }
            )
            chunk(b"data: [DONE]\n\n")
            self.wfile.write(b"0\r\n\r\n")
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True


if __name__ == "__main__":
    print("[mock-gateway] listening on 0.0.0.0:8080", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
