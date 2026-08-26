FROM node:22-alpine AS frontend

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY src/ src/
RUN uv sync --frozen --no-dev

COPY --from=frontend /build/dist frontend/dist

EXPOSE 8080

CMD ["uv", "run", "--frozen", "--no-dev", "hypercorn", "server.app:app", "--bind", "0.0.0.0:8080"]
