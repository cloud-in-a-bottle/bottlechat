- read README.md and style_guide.md at the beginning of every session.
- on first init, run `just setup` — python deps, node deps, pre-commit hooks, and the playwright chromium browser. pre-commit runs ruff and mypy on commit.
- use uv for all python work (`uv run ...`, `uv add ...`, `uv sync`). use npm inside `frontend/` for the frontend.
- this is a Cloud in a Bottle app. `cloudinabottle.toml` is the app manifest.
- litestar/hypercorn backend on port 8080 serving `/health`, the owner API under `/api`, the public share surface under `/share`, and the built solidjs frontend.
- `just dev` runs the backend plus vite with hot reload, backed by `scripts/dev_gateway.py` (a fake router + openai-compat provider). `DEV_GATEWAY_STATE` exercises the setup screens. no podman or API keys needed.
- tests use the Cloud in a Bottle test harness (`openhost[test-harness]`, imported as `openhost_test_harness`): each run builds the Dockerfile, deploys the app and `tests/mock_gateway/` under podman, and fronts them with the real router. so `just test` requires podman running. `stack.url` goes through the router and requires owner auth (`stack.owner_session`, or `stack.playwright_login(page)` for browser tests); `stack.app_url` hits the container directly.
- the `stack` fixture is session-scoped and shared, so tests see each other's chats. scope browser assertions to something unique (e.g. the active sidebar row) rather than a title several tests happen to produce.
- pytest-playwright keeps an event loop running for the whole session, so async unit tests can't use pytest-asyncio. `tests/test_llm_client.py` has a `run()` helper that executes coroutines on their own thread.

## things that are easy to get wrong here

- SSE responses need chunked framing under HTTP/1.1. the mock gateways set `Transfer-Encoding: chunked` explicitly; without it a client just hangs waiting for the body to end.
- `messages_fts` / `chats_fts` are plain (not external-content) FTS5 tables, so their triggers use `DELETE FROM ... WHERE rowid = ?`. the `INSERT INTO t(t, rowid, …) VALUES('delete', …)` form is only valid for contentless/external-content tables and fails with "SQL logic error".
- a generation run outlives the request that started it (see `runs.py`). don't tie its lifetime to an SSE subscriber; closing a tab must not cancel a response.
- anything added to `public_paths` is reachable by the whole internet. today that's the share surface and static assets only; keep every route that can reach chat data under `/api`.

## deploying & debugging on openhost

- openhost is a cloud platform for self-hosting apps. there's context on openhost at `~/work/openhost`; read `docs/src/creating_an_app.md` there for how apps are built and run.
- instances are managed via the `oh` cli. `oh instance list` shows the configured instances and the URL each is available at. the user will tell you which instance to use; do not touch the others. most commands take `--instance <name>`.
- these instances have web servers facing the public internet. be careful with anything that could open unsecured public access — eg adding `public_paths` in `cloudinabottle.toml`.
- prefer `oh` commands for debugging since they handle auth: `oh instance ssh` and `oh curl`. `oh instance token --instance <name>` gives a raw API token (Bearer auth) only if absolutely necessary — better not to see it, and never put it anywhere that might get committed.
- typical deploy loop: commit + push, then `oh app reload bottlechat --update --wait --instance <name>` to pull the changes and reload, then `oh app logs bottlechat --instance <name>` to check the logs.
- to test pages in a browser as the user would see them, use playwright and inject the API token as a Bearer header — this matches a request made with the owner's login cookies.
- bottlechat needs a provider of the `openai-compat` service on the same instance to do anything useful. install `github.com/cloud-in-a-bottle/bottled-bifrost` and configure a model in it first.

## specific to this repo

- if you run into any cases where the app test harness doesn't match the expected/real behavior of openhost, stop and mention this so that we can fix the test harness - don't just make some workaround to the issue.
- if you run into cases where openhost itself doesn't behave as expected, also stop and mention this so we can open a PR there to fix upstream.
