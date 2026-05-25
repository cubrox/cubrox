# Technical Architecture

## Overview

Cubrox is a server-rendered web application that delivers a configurable
reading surface for neurodivergent readers, with Baha'i writings as its
primary corpus. A single FastAPI process on Cloud Run serves Jinja2-rendered
HTML; HTMX drives in-page interactivity (preference toggles, fragment swaps,
deferred comprehension-question loading) without a JavaScript build step.
State persists to Supabase Postgres via SQLModel; per-PR Supabase
branches (Supabase GitHub App) give every preview deploy an isolated
database. Comprehension questions are generated on demand by
Anthropic's Claude API and cached by passage hash. Authentication is
passwordless via Supabase Auth (GoTrue) magic links; the access token
lives in an HttpOnly cookie.

The design optimises for two product invariants: **WCAG conformance is a
defining requirement, not a checkbox**, and **readability needs vary
significantly between individuals** (PRD §Constraints). Every reading
transformation is therefore a per-user preference, every UI surface ships
with semantic markup and keyboard support, and the rendering pipeline
applies user CSS variables server-side so the first paint already reflects
the reader's profile.

## Technology Stack

### Frontend

- Templates: **Jinja2** (server-rendered, no build step)
- Interactivity: **HTMX 2.x** loaded from CDN (`unpkg.com/htmx.org@2`)
- Styling: **Pico.css 2.x** (class-less baseline) layered with project CSS
  variables for the per-user reading surface
- Reading-support transforms: server-side text rewriters (e.g., bionic
  emphasis = wrap first N chars of each token in `<b>`); no client-side
  transformation libraries
- Accessibility tooling: **axe-core via Playwright** (test only); manual
  audit gates the WCAG success criterion (Roadmap §Phase 1)
- No bundler, no Node runtime — the CI `node` job is intentionally absent

### Backend

- Runtime: **Python 3.12**
- Framework: **FastAPI** + **Uvicorn** (single-process, async)
- ORM: **SQLModel** (Pydantic + SQLAlchemy)
- Migrations: **Alembic**
- Driver: **psycopg 3** with binary + connection pool
- Settings: **pydantic-settings** (env-driven; values surfaced from Secret
  Manager via Cloud Run env vars)
- HTTP client (LLM, email): **httpx** (already a dev dep; promote to runtime)
- Background work: **`fastapi.BackgroundTasks`** for fire-and-forget email
  sends and comprehension-question warmups. No queue infrastructure in MVP.

### LLM (comprehension questions)

- Provider: **Anthropic Claude API**, model **`claude-haiku-4-5`** (fast,
  cheap, strong on nuanced/sacred text)
- SDK: **`anthropic` Python SDK** with **prompt caching** on the system
  prompt (the per-passage user message is the only thing that changes)
- Secret: `ANTHROPIC_API_KEY` in Secret Manager → injected as Cloud Run env
- Budgeting: cap input passage at 4,000 tokens; refuse longer with a UX
  hint to split. Generated questions cached in Postgres by SHA-256 of
  `(passage_text, question_type, model_id, prompt_version)` so re-reads
  cost zero LLM calls.

### Authentication

- **Passwordless magic link via Supabase Auth (GoTrue)** (per ADR-006,
  superseding ADR-002's hand-rolled approach)
- Flow: POST `/login` → `supabase.auth.sign_in_with_otp(email, redirect_url)`
  → Supabase mints + emails the link → GET `/auth/callback` two-stage
  handler (JS bridge converts URL hash → query params per Pattern #35)
  → `supabase.auth.get_user(access_token)` validates → `sb-access-token`
  HttpOnly cookie set, 7-day max-age
- Email transport: **Supabase's built-in SMTP** (no Resend dependency).
  Custom SMTP configurable in Supabase Dashboard if rate limits bite.
- Session: Supabase-issued JWT in HttpOnly cookie. No server-side
  session table; no `itsdangerous` cookie signer.
- Identity source: **`auth.users` in Supabase** (managed by GoTrue). The
  local `User` SQLModel was deleted in SUPA-2c (#91). Routes that need
  user identity get it from the Supabase user object via the
  `current_user` dependency in `app/integrations/supabase/auth.py`.
- Rate limiting: per-IP + per-email token buckets on POST `/login`
  (existing `rate_bucket` table). Supabase's own rate limits sit
  upstream of this.
- Secrets: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`
  in GCP Secret Manager (mounted as Cloud Run env vars).

### PDF ingestion

- Parser: **`pdfplumber`** (MIT-licensed; license-clean for BSL 1.1 release)
- Path: multipart upload → FastAPI route → in-process parse → render in
  reading view. Cap at 25 MB to stay under Cloud Run's 32 MB request limit.
- Errors surfaced inline ("This PDF couldn't be parsed — try copy-pasting
  the text") per Risk #3 in the PRD.

### Database

- Primary: **Supabase Postgres** (Pro plan, per-PR branching enabled via
  the Supabase GitHub App). Project ref: `gnswmcgaztcxslirulwm`.
- Schema source of truth: **Supabase CLI migrations** in
  `supabase/migrations/*.sql` (replaces the deleted Alembic chain).
- Row-Level Security on every public-schema table:
  - Tenant-scoped tables (`passage`, `preference`, `reading_event`)
    use `owner_id = auth.uid()` policies — anon key safe to use from
    request handlers
  - System / cross-user tables (`comprehension_question_cache`,
    `rate_bucket`, `todo`) have RLS enabled with no
    authenticated/anon policies — reachable only via the service-key
    client in `app/integrations/supabase/client.py::service_client()`
- App-table FKs point at `auth.users(id)` in the SQL migrations; the
  SQLModel field declarations carry only the column type (no
  `foreign_key="user.id"` since `auth.users` is in a different schema
  and isn't a SQLModel-managed table).
- No cache layer in MVP; Postgres handles preference + passage reads.
- No search engine in MVP. Add when curated-library work in Phase 3 lands.

### Infrastructure

- Hosting: **GCP Cloud Run** (scale-to-zero, single region us-east1)
- Container registry: **Artifact Registry**
- Secrets: **Google Secret Manager** → mounted as Cloud Run env vars
- Auth to GCP: **Workload Identity Federation** from GitHub Actions (SA key
  fallback for workshops only)
- CI/CD: **GitHub Actions** — `ci.yml` (lint+test), `preview-deploy.yml`
  (per-PR ephemeral Cloud Run revision; Supabase GitHub App
  auto-creates per-PR Postgres branches), `deploy.yml` (main → production)
- Observability: **Google Cloud Logging + Error Reporting** (zero-setup,
  auto-grouping of FastAPI tracebacks). Sentry deferred to Phase 2 if
  Cloud Logging proves insufficient.

## System Design

### Component Diagram

```
                ┌──────────────────────────────────────────────┐
                │              Browser (HTMX 2.x)              │
                │  Renders server HTML; swaps fragments on     │
                │  preference toggle / question request.       │
                └──────────────────┬───────────────────────────┘
                                   │ HTTPS
                                   ▼
              ┌────────────────────────────────────────────────┐
              │              Cloud Run service                 │
              │   FastAPI + Uvicorn (single async process)     │
              │                                                │
              │  ┌────────┐  ┌──────────┐  ┌────────────────┐  │
              │  │ Auth   │  │ Reading  │  │ Comprehension  │  │
              │  │ routes │  │ surface  │  │ question route │  │
              │  │ /login │  │ /read    │  │ (HTMX lazy)    │  │
              │  │ /verify│  │ /upload  │  │                │  │
              │  └────────┘  └──────────┘  └────────────────┘  │
              │       │           │                │           │
              │       ▼           ▼                ▼           │
              │  ┌───────────────────────┐  ┌────────────────┐ │
              │  │  SQLModel session     │  │ Anthropic SDK  │ │
              │  │  (psycopg pool)       │  │ (httpx-backed) │ │
              │  │   supabase-py         │  │                │ │
              │  └───────────┬───────────┘  └────────┬───────┘ │
              └──────────────┼───────────────────────┼─────────┘
                             ▼                       ▼
                  ┌────────────────────────┐   ┌────────────────────┐
                  │  Supabase              │   │  Anthropic API     │
                  │  - auth.users (GoTrue) │   │  Claude Haiku 4.5  │
                  │  - passage / pref /    │   │  (prompt caching)  │
                  │    reading_event       │   └────────────────────┘
                  │  - RLS on every public │
                  │    table              │
                  │  - magic-link email    │
                  │    delivery            │
                  └────────────────────────┘
```

### Data Flow — typical reading session

1. User pastes text or uploads PDF → `POST /passages` → server parses
   (pdfplumber) → row in `passage` → redirect to `/read/{id}`.
2. `GET /read/{id}` renders the reading surface with the user's preferences
   inlined as CSS variables in the template head. First paint is already
   correctly styled — no reflow.
3. Comprehension panel is loaded via `hx-get="/passages/{id}/questions"
   hx-trigger="load delay:200ms"` so the page appears instantly.
4. The question route checks the cache (`comprehension_question_cache` keyed
   by passage hash). On miss, it calls Claude Haiku via the Anthropic SDK
   with prompt caching on the system prompt, persists the result, returns
   the HTML fragment.
5. Preference toggles `hx-post` to `/preferences/{key}`, swap the `<style>`
   variable block via `hx-target="#reading-surface-style"
   hx-swap="outerHTML"`. No full-page reload.
6. Reading-event writes (`reading_event` table) happen on passage close
   (`hx-trigger="unload"` beacon) and feed the 100k-line metric.

### API Design

REST + HTML fragments. Routes return either a full Jinja page (browser
navigation) or an HTMX fragment (when `HX-Request: true`). Same handler,
template selection driven by request header.

| Route                              | Method | Returns          | Notes                                  |
|------------------------------------|--------|------------------|----------------------------------------|
| `/`                                | GET    | Page             | Marketing / login CTA                  |
| `/login`                           | POST   | Fragment         | Email submitted → magic link sent      |
| `/auth/verify`                     | GET    | Redirect         | Token consumed → session cookie set    |
| `/passages`                        | POST   | Redirect         | Paste or PDF upload                    |
| `/read/{passage_id}`               | GET    | Page             | Reading surface (full chrome)          |
| `/passages/{id}/questions`        | GET    | Fragment         | Lazy-loaded comprehension panel        |
| `/preferences/{key}`               | POST   | Fragment         | Updates one preference, swaps `<style>` |
| `/healthz`                         | GET    | JSON             | Cloud Run liveness/readiness           |

JSON APIs are intentionally absent in MVP — there is no mobile client or
third-party integration. Adding JSON later is straightforward (FastAPI's
`response_class` already supports both).

### Reading-Surface Mechanics

The reading surface is a single Jinja template that injects per-user CSS
variables in a `<style id="reading-surface-style">` block:

```html
<style id="reading-surface-style">
  :root {
    --reader-font: {{ prefs.font }};
    --reader-size: {{ prefs.size }};
    --reader-line-height: {{ prefs.line_height }};
    --reader-bg: {{ prefs.bg }};
    --reader-fg: {{ prefs.fg }};
    --reader-max-width: {{ prefs.max_width }};
  }
</style>
```

Visual reformatting modes (font, size, contrast, spacing, max width) are
all CSS-variable swaps — no DOM rewrites. Bionic-style emphasis is the
exception: it requires server-side text transformation (wrap first N chars
of each token in `<b>`), produced when the passage is rendered, gated on
`prefs.bionic_enabled`.

This keeps the reading surface accessible by default: screen readers see
plain semantic HTML; visual transformations are CSS-only or
opt-in-and-explicit.

## Data Models

### Core Entities

- **User**: account holder. Identified by email. No password hash
  (passwordless).
- **MagicLinkToken**: short-lived, hashed; one active per user.
- **Preference**: per-user reading-support settings. JSONB-typed for
  schema flexibility as the support toolkit evolves.
- **Passage**: a piece of text the user is reading. Originates from paste
  or PDF upload.
- **ComprehensionQuestionCache**: keyed by passage hash; stores generated
  questions to avoid re-paying the LLM cost on re-reads.
- **ReadingEvent**: append-only log of read sessions, used for the 100k
  metric. Stores `lines_processed` as the rendered-line count at session
  close.

### Database Schema (sketch)

```sql
CREATE TABLE "user" (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email       CITEXT UNIQUE NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_login  TIMESTAMPTZ
);

CREATE TABLE magic_link_token (
  user_id     UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  token_hash  BYTEA PRIMARY KEY,
  expires_at  TIMESTAMPTZ NOT NULL,
  consumed_at TIMESTAMPTZ
);
CREATE INDEX ON magic_link_token (user_id);

CREATE TABLE preference (
  user_id    UUID PRIMARY KEY REFERENCES "user"(id) ON DELETE CASCADE,
  values     JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE passage (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  text            TEXT NOT NULL,
  text_hash       BYTEA NOT NULL,           -- SHA-256, used as cache key
  source_type     TEXT NOT NULL CHECK (source_type IN ('paste','pdf')),
  source_filename TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON passage (user_id, created_at DESC);
CREATE INDEX ON passage (text_hash);

CREATE TABLE comprehension_question_cache (
  passage_hash    BYTEA NOT NULL,
  question_type   TEXT NOT NULL,
  model_id        TEXT NOT NULL,
  prompt_version  INT  NOT NULL,
  questions       JSONB NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (passage_hash, question_type, model_id, prompt_version)
);

CREATE TABLE reading_event (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  passage_id       UUID NOT NULL REFERENCES passage(id) ON DELETE CASCADE,
  lines_processed  INT  NOT NULL,
  occurred_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON reading_event (occurred_at);
```

`gen_random_uuid()` is pre-installed on Supabase projects (pgcrypto
extension is enabled by default). `citext` is no longer used — emails
live in `auth.users` (Supabase-managed) rather than a local table.
Extensions are declared in the Supabase SQL migration files
(`supabase/migrations/*.sql`), not via Alembic.

## Development Standards

### Code Style

- Lint + format: **ruff** (`ruff check .` / `ruff format .`), line-length 100
- Selected rules: `E`, `F`, `I`, `W`, `B`, `UP` (already configured)
- Type-checking: **mypy** in strict-ish mode (`check_untyped_defs = true`)
- Naming: `snake_case` modules and functions, `PascalCase` for SQLModel
  classes, `UPPER_SNAKE` for constants. Module names singular
  (`app/models/passage.py`), not plural.
- Imports: stdlib → third-party → local, separated by blank lines (ruff
  isort handles automatically)
- Comments: only when *why* is non-obvious. No what-comments. No "added
  for ticket #123" — that belongs in the PR.

### Testing Requirements

- Unit + HTTP tests: **pytest** + **httpx.AsyncClient** with the in-memory
  SQLite session fixture documented in this file.
- HTMX endpoints: assert on HTML substrings; assert fragment responses do
  NOT include `<html` (catches accidental full-page returns).
- LLM call sites: mock the `anthropic.Anthropic` client; never hit the
  real API in CI. A separate `tests/integration/` directory may hit the
  real API behind an env-var gate, run only manually.
- Coverage target: **>80%** on `app/`. Enforced via `pytest-cov`.
- Accessibility: Playwright + `@axe-core/playwright` smoke test on the
  reading surface; runs on every PR via `ci.yml`. (Adds Node only for the
  test run, kept in `tests/a11y/`; production stays Node-free.)

### Documentation

- Public functions: one-line docstring when the name doesn't tell the
  whole story; otherwise none.
- Migrations: Alembic message must describe *why*, not *what* the SQL
  does. The SQL itself is in the file.
- Architecture decisions: ADRs appended to this document under
  "Architecture Decision Records" — short, dated, never edited after
  acceptance (supersede with a new ADR instead).

### Code Review

- All PRs reviewed by `pr-reviewer` agent before human merge.
- Required-change blockers: failing tests, missing migration for schema
  change, secret leak, accessibility regression on the reading surface,
  unbounded LLM cost (no cache lookup, no input cap).
- Suggestions are non-blocking — merge can proceed if author disagrees
  with rationale.

## Security

### Authentication

- Passwordless magic link delivered by Supabase Auth (GoTrue). Token
  lifetime + single-use semantics are Supabase-managed.
- Sessions: Supabase-issued JWT in an HttpOnly cookie
  (`sb-access-token`, `Secure`, `SameSite=Lax`, 7-day max-age).
- Rate-limit `POST /login` per IP and per email (10/hour each) using
  a Postgres-backed token bucket. Supabase's own rate limits sit
  upstream; ours is defense-in-depth against per-target abuse.

### Authorization

- Single role: authenticated user. Two enforcement layers:
  1. Route handlers filter by `WHERE owner_id = current_user.id`
  2. Supabase Row-Level Security on every public-schema table —
     `owner_id = auth.uid()` for tenant-scoped tables; RLS enabled
     with no anon/authenticated policies for service-role-only tables
     (`comprehension_question_cache`, `rate_bucket`, `todo`)
- No admin UI in MVP. Admin tasks happen via the Supabase Dashboard's
  SQL editor or via the service-key client.

### Data Protection

- TLS via Cloud Run's managed cert.
- Secrets in **Google Secret Manager**, never in source. The `database-url`,
  `ANTHROPIC_API_KEY`, `RESEND_API_KEY`, and `SESSION_SECRET` secrets are
  injected as Cloud Run env vars at deploy time.
- PII collected: email only. Passages may contain user-uploaded content;
  treat as private to the user (no cross-user reads, no LLM training opt-in).
- Anthropic data handling: passages are sent to the Claude API for
  question generation. Anthropic's default policy does not train on API
  inputs — verify in the privacy policy linked from the marketing page.
- No third-party analytics in MVP. (Cloud Logging is first-party.)

## Scalability

### Current Targets (Roadmap §M2)

- **100,000 lines processed within 3 months of launch.** Assuming a
  working session is ~200 lines, that's ~500 sessions, easily handled by
  a single Cloud Run instance.
- **Perceived latency < 100 ms for view changes** (PRD §NFR). This is the
  binding constraint, not throughput.

### Scaling Strategy

- Cloud Run scales horizontally on request concurrency (default 80
  concurrent requests per instance). Scale-to-zero when idle.
- Supabase's Supavisor pooler handles fan-out without exhausting the
  database.
- Comprehension-question cache keeps LLM calls bounded by *distinct
  passages* read, not *re-reads*. Even at 10x the metric target, expected
  monthly LLM spend is under $20.
- Reading-event writes are append-only and cheap; no concern through M3.

### When to revisit

- Add Redis if `reading_event` aggregation queries (the metric dashboard)
  become slow, or if rate-limit lookups exceed 10 ms p99.
- Move PDF parsing to a Cloud Tasks worker if files >25 MB become common
  (workshop-style large documents). Until then, in-process is simpler.

## Architecture Decision Records

### ADR-001: Anthropic Claude for comprehension question generation

- Status: Accepted (2026-05-02)
- Context: PRD lists the comprehension-question generator as TBD between
  LLM and rules-based. Sacred/poetic text quality is a Risk #2 explicitly
  called out. Neurodivergent reading benefits from questions that engage
  with *meaning*, not just recall.
- Decision: Use **Anthropic Claude Haiku 4.5** via the official Python
  SDK, with prompt caching on the system prompt and Postgres-backed
  result caching by passage hash.
- Consequences: Adds Anthropic as a third-party vendor and `ANTHROPIC_API_KEY`
  as a managed secret. Avoids vendor lock-in by isolating the call site
  behind an `app/services/questions.py` interface — swap to Vertex/Gemini
  is a one-file change. Cost remains negligible at MVP scale due to
  result caching.

### ADR-002: Passwordless magic-link authentication

- Status: **Superseded by ADR-006 (2026-05-25)**
- Context: Primary users are neurodivergent readers; password friction
  (remembering, typing, resetting) is exactly the kind of cognitive load
  the product is built to remove.
- Decision: Hand-rolled magic-link flow (~50 LOC), token hashed at rest,
  15-minute TTL, single-use. Email delivery via **Resend**. Sessions via
  signed cookie (`itsdangerous`).
- Consequences: Adds Resend as a vendor and `RESEND_API_KEY` as a managed
  secret. Removes the entire password-reset surface (no UI, no rate-limit
  story, no breach exposure for stored hashes). Magic links can be
  hijacked if the user's email is compromised — same exposure as
  password reset, so net-equivalent risk.

### ADR-003: pdfplumber over PyMuPDF for PDF parsing

- Status: Accepted (2026-05-02)
- Context: PRD lists PDF upload as P0. PyMuPDF has better text-extraction
  fidelity but is **AGPL-licensed**, which conflicts with this project's
  BSL 1.1 → Apache 2.0 release path.
- Decision: Use **pdfplumber** (MIT-licensed). If extraction quality is
  inadequate during Phase 1 testing on representative documents, revisit
  with options: (a) license PyMuPDF commercially, (b) move to a separate
  AGPL-clean parser like `pypdf` + Tesseract for OCR, (c) sandbox PyMuPDF
  in an isolated worker that the BSL conversion can exclude.
- Consequences: Some loss of fidelity on heavily-formatted PDFs.
  Mitigated by clear error UX (Risk #3 in PRD) — user can fall back to
  paste.

### ADR-004: Cloud Logging + Error Reporting over Sentry for MVP

- Status: Accepted (2026-05-02)
- Context: Three observability options exist (Cloud Logging, Sentry,
  both). MVP scope favours zero-setup over best-in-class.
- Decision: **Cloud Logging + Error Reporting**, both auto-wired by Cloud
  Run. Add Sentry in Phase 2 if grouping/triage proves insufficient.
- Consequences: Slightly worse stack-trace ergonomics than Sentry, no
  release tracking, no issue assignment. Acceptable for an MVP whose
  user base is a small first cohort. The instrumentation cost to add
  Sentry later is one `app/main.py` import + one secret.

### ADR-005: HTMX + server-side rendering, no SPA

- Status: Accepted (2026-05-02)
- Context: Reading surface needs to feel instant (<100 ms perceived
  latency) and be WCAG-conformant by default. SPA frameworks add a
  rendering layer between source HTML and what assistive tech sees, and
  shift accessibility burden onto the framework.
- Decision: Server-rendered Jinja templates + HTMX for in-page swaps. No
  React/Vue/Svelte. No bundler. Pico.css for baseline styling.
- Consequences: Smaller bundle, faster first paint, easier accessibility
  audit, no Node toolchain in production. The cost is that complex
  client-side interactions (e.g., drag-to-reorder) require either light
  custom JS or graceful server round-trips. Acceptable for the MVP
  surface, which is fundamentally a read-and-toggle experience.

### ADR-006: Supabase consolidation (Neon Postgres + Resend auth → Supabase)

- Status: Accepted (2026-05-25)
- Supersedes: ADR-002 (hand-rolled magic-link)
- Context: Production was running two vendors' worth of complexity —
  Neon for Postgres, Resend for the hand-rolled magic-link email — and
  the Resend account hit the test-mode "sender must be account owner"
  limit when a non-owner user tried to sign in (Cloud Run logs,
  2026-05-23). The hand-rolled ADR-002 implementation made every auth
  feature (rate limiting, token expiry, multi-device sessions) something
  cubrox owned and had to maintain.
- Decision: Consolidate persistence + auth on **Supabase** (Pro plan,
  branching enabled). Replace Neon Postgres → Supabase Postgres
  (`gnswmcgaztcxslirulwm`). Replace hand-rolled magic-link →
  Supabase Auth (GoTrue magic-link via `supabase.auth.sign_in_with_otp`).
  Replace `itsdangerous`-signed session cookie → Supabase JWT in
  HttpOnly cookie. Replace Alembic schema management → Supabase CLI
  migrations (`supabase/migrations/*.sql`).
- Consequences:
  - Drops two vendor dependencies (Neon, Resend) and three Python
    packages (`resend`, `itsdangerous`, `alembic`) for one (`supabase`)
  - Removes ~500 LOC of hand-rolled auth code, including the entire
    `app/services/identity/` directory, `app/models/user.py`, and
    `app/models/magic_link_token.py`
  - Adds RLS as a defensive layer — every user-scoped public-schema
    table enforces ownership at the database level, not just in route
    code
  - Single billing relationship (Supabase) instead of two (Neon +
    Resend)
  - Loses some control over the email template UX vs. the hand-rolled
    Resend version (Supabase Auth's dashboard template editor is the
    only knob); ADR-002's neurodivergent-UX argument still holds —
    Supabase Auth's magic-link experience is equivalent
  - Migration shipped across SUPA-1 through SUPA-6 (#80 through #85)
    over ~3 days of agent work. Two follow-ups remain in the backlog:
    a11y harness seed restoration (#97) and per-PR Supabase branch URL
    injection (#99)
