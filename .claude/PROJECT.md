# Project Configuration

## Platform

- **Hosting**: gcp
- **Compute**: Cloud Run
- **Database**: Neon
- **Selected**: 2026-05-02

## Stack

- **Backend**: FastAPI + Uvicorn (Python 3.12)
- **Templates**: Jinja2
- **Interactivity**: HTMX 2.x (CDN, no build step)
- **Styling**: Pico.css 2.x + project CSS variables
- **ORM**: SQLModel + Alembic
- **DB driver**: psycopg 3 (binary + pool)
- **Package manager**: uv

## External services

- **LLM**: Anthropic Claude API (model: `claude-haiku-4-5`)
- **Email**: Resend
- **PDF parsing**: pdfplumber (in-process)
- **Observability**: Google Cloud Logging + Error Reporting

## Required secrets (Google Secret Manager → Cloud Run env)

- `database-url` — Neon pooled connection string
- `anthropic-api-key` — Claude API key
- `resend-api-key` — transactional email
- `session-secret` — `itsdangerous` signing key (32 random bytes)

## Required GitHub Actions secrets

- `GCP_PROJECT_ID`, `GCP_SERVICE_ACCOUNT`, `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `NEON_PROJECT_ID`, `NEON_API_KEY`, `PRODUCTION_DATABASE_URL`
- `NEON_PARENT_BRANCH` (optional, defaults to `main`)
