# bottlechat

A chat UI for the models configured in your [Bifrost](https://github.com/cloud-in-a-bottle/bottled-bifrost)
gateway, running as a Cloud in a Bottle app. Streaming responses, reasoning support, searchable
history, stable links, and shareable transcripts — private to the compute space owner unless you
choose to share a chat.

bottlechat has no model access of its own. It consumes the `openai-compat` cross-app service, so
inference happens in whichever app provides that service (Bifrost is the reference provider) using
the API keys you configured there. bottlechat never sees those keys.

## What it does

- **Chat** with any model the gateway exposes, at a reasoning effort you pick per chat.
- **Streaming** responses over SSE, with thinking/reasoning shown in a collapsible block that
  folds itself away once the answer starts.
- **History** stored in SQLite in the app's persistent data dir, searchable full-text (message
  bodies, reasoning, and titles) and browsable in a date-grouped sidebar.
- **Stable links** — every chat lives at `/c/<id>`.
- **Share links** — one click produces `/share/<token>`, readable by anyone with the link and
  nobody else. Shared chats are live: messages you add later show up there too. Revoke at any time.
- **Multi-tab safe** — responses are generated and persisted server-side, so closing the tab that
  started one doesn't lose it, and reopening the chat (in that tab or another) picks the stream
  back up mid-flight. Tabs don't see each other's *new* chats until they reload.
- **Installable PWA** with a mobile layout (drawer sidebar, safe-area insets).

Text only for now — no attachments, no tools.

## Setup states

If inference isn't usable, the app says exactly what to do instead of failing at send time:

| State | What the owner sees |
|-------|---------------------|
| No app provides `openai-compat` | "No LLM gateway installed", with a link to install Bifrost |
| A provider exists but isn't granted | "Permission needed", with the router's approval link |
| Provider up, zero models configured | "No models configured", linking into the provider's UI |
| Provider unreachable or erroring | The upstream error, with a retry |

## How requests flow

```
browser ──► bottlechat backend ──► OpenHost router ──► provider app (Bifrost) ──► upstream model
         ◄── SSE ───────────────  (persists as it streams)
```

The browser never talks to the service interface directly. Everything goes through the backend so
responses are written to the database as they arrive, which is what makes reconnecting mid-stream
and closing the tab safe.

## Auth

The router gates the app to the logged-in owner; there is no other auth. `/api/*` additionally
re-checks the `X-OpenHost-Is-Owner` header the router injects (it strips any client-supplied
`X-OpenHost-*`), so a manifest mistake fails closed rather than open.

`public_paths` covers `/share` plus the static files a share page loads (`/assets`, `/icons`,
`/favicon.svg`, `/manifest.webmanifest`) — code and images only. Share tokens are 32 characters of
`secrets.token_urlsafe` entropy, and the share API returns just the transcript: no chat id, no
model settings, no token counts, no reference to your other chats.

## Data

One SQLite database at `$OPENHOST_SQLITE_CHATS` (`chats.sqlite` in the app data dir), so it's in
OpenHost's backups and readable with the `sqlite3` CLI:

```
chats     (id, title, model, effort, created_at, updated_at)
messages  (id, chat_id, seq, role, content, reasoning, status, model, effort, error, usage_json, …)
shares    (token, chat_id, created_at)
settings  (key, value)                 -- last-used model + effort
*_fts                                  -- FTS5 indexes over message text and chat titles
```

Message text is stored verbatim, one row per turn — `select role, content from messages order by
seq` is a readable transcript.

## Development

```bash
just setup            # python deps, node deps, pre-commit hooks, playwright chromium
just dev              # backend :8000 + vite :5173 with hot reload
just run              # the built app on :8000
just test             # full suite (builds the Dockerfile, runs under podman)
just check            # ruff + mypy + tsc
just icons            # regenerate the PWA icons
```

`just dev` and `just run` start `scripts/dev_gateway.py`, a stand-in for the router and an
openai-compat provider, so the whole UI works locally without podman or real API keys. Set
`DEV_GATEWAY_STATE` to `no_provider`, `permission_required`, `no_models`, or `error` to see the
setup screens.

Tests use the OpenHost test harness: each run builds the Dockerfile, deploys the app *and* a mock
gateway (`tests/mock_gateway/`) under podman, and fronts both with the real OpenHost router — so
service calls, permission grants, and public-path routing are exercised for real, not stubbed.
Podman must be running.

## Layout

```
src/server/          litestar backend
  llm/               the openai-compat client (provider status, streaming, title generation)
  routes/            owner api, public share routes, spa/static
  runs.py            in-flight responses: fan-out to tabs, incremental persistence
  store.py, db.py    sqlite schema and queries
frontend/src/        solidjs app
tests/mock_gateway/  a fake openai-compat provider, deployed alongside the app in tests
```
