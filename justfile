default: test

# Install python deps, node deps, pre-commit hooks, and the playwright chromium browser.
setup:
    uv sync
    cd frontend && npm ci
    uv run pre-commit install
    uv run playwright install chromium

# Build the frontend into frontend/dist (what the container and `just run` serve).
build-frontend:
    cd frontend && npm run build

# Serve the built app on http://localhost:8000, backed by the mock gateway on :8099.
run: build-frontend
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p data
    uv run python scripts/dev_gateway.py & gateway=$!
    trap 'kill $gateway 2>/dev/null || true' EXIT
    OPENHOST_SQLITE_CHATS=data/chats.sqlite \
    OPENHOST_ROUTER_URL=http://127.0.0.1:8099 \
    OPENHOST_APP_TOKEN=dev-token \
    OPENHOST_APP_NAME=bottlechat \
    OPENHOST_ZONE_DOMAIN=localhost:8000 \
    uv run hypercorn server.app:app --bind 127.0.0.1:8000

# Backend on :8000 plus the vite dev server on :5173 with hot reload.
dev: build-frontend
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p data
    uv run python scripts/dev_gateway.py & gateway=$!
    OPENHOST_SQLITE_CHATS=data/chats.sqlite \
    OPENHOST_ROUTER_URL=http://127.0.0.1:8099 \
    OPENHOST_APP_TOKEN=dev-token \
    OPENHOST_APP_NAME=bottlechat \
    OPENHOST_ZONE_DOMAIN=localhost:5173 \
    uv run hypercorn server.app:app --bind 127.0.0.1:8000 --reload & backend=$!
    trap 'kill $gateway $backend 2>/dev/null || true' EXIT
    cd frontend && npm run dev

# Run the test suite (builds the Dockerfile and runs the app under podman).
test *args:
    uv run pytest -x {{args}}

# Lint, format, and typecheck everything.
check:
    uv run ruff check --fix .
    uv run ruff format .
    uv run mypy
    cd frontend && npx tsc --noEmit

# Regenerate the PWA icons from scripts/make_icons.py.
icons:
    uv run python scripts/make_icons.py

# Build the container image.
build:
    docker build -t bottlechat .
