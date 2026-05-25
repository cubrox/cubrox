# syntax=docker/dockerfile:1.7
#
# FastAPI on Google Cloud Run.
#
# Single-stage build using uv for fast dependency installation. No
# build-time env vars needed — FastAPI reads env vars at runtime, so
# `gcloud run deploy --set-env-vars` and Secret Manager mounts just work.
#
# Compare to the Next.js version this replaces (42 lines, multi-stage,
# HOSTNAME=0.0.0.0 hack, NEXT_PUBLIC_* build args): this is 20 lines.

FROM python:3.12-slim

# uv: fast Python package manager. Copied from the official image so we
# don't need to install it via pip at build time.
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /bin/

WORKDIR /app

# Install dependencies first (cached layer). --frozen ensures CI builds
# match the lockfile exactly.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Copy application code and install the project itself.
COPY . .
RUN uv sync --frozen --no-dev

# Cloud Run sends traffic to $PORT (default 8080). uvicorn honors the
# --host and --port flags, no env var fiddling needed.
ENV PORT=8080

EXPOSE 8080

# Run uvicorn directly — no shell, signals propagate cleanly for graceful
# shutdown. `--host 0.0.0.0` is explicit so we bind on all interfaces.
#
# --proxy-headers + --forwarded-allow-ips=* make uvicorn trust the
# X-Forwarded-* headers Cloud Run's proxy sets. Without this, code that
# builds URLs from `request.url` (Supabase magic-link callback redirect
# URL is the canonical case) gets the internal Cloud Run origin instead
# of the public host, and emails arrive with unclickable links. Safe
# on Cloud Run because the only thing in front of the container is
# Google's trusted proxy. Pattern #4 in docs/PATTERN-LIBRARY.md.
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8080", \
     "--proxy-headers", "--forwarded-allow-ips=*"]
