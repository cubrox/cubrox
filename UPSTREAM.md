# Upstream Sync Notes

This repository is a GCP + FastAPI fork of
[vibeacademy/gembaflow](https://github.com/vibeacademy/gembaflow).

## Source Commit

Forked from: **`b9bd5e3`** (2026-04-09)

> `docs(readme): add YouTube video embed to README (#167)`

## Divergence Summary

Two major swaps from upstream:

1. **Platform:** Render/Supabase → GCP Cloud Run + Neon
2. **Stack:** Next.js/TypeScript → FastAPI + Jinja2 + HTMX + SQLModel + Alembic (Python 3.12)

The agent layer, ticket format, CI workflow structure, and docs
organization are mostly unchanged from upstream — only the stack- and
platform-specific content differs.

## Changed Files vs Upstream

### Application code (stack swap)

**Deleted** (Next.js):

- `app/` (Next.js App Router, TSX components, API routes)
- `__tests__/` (Vitest tests)
- `package.json`, `package-lock.json`
- `next.config.ts`
- `tsconfig.json`
- `eslint.config.mjs`
- `vitest.config.ts`, `vitest.setup.ts`
- `instrumentation.ts` (Sentry init)

**Created** (FastAPI):

- `pyproject.toml`, `uv.lock`, `.python-version`
- `app/__init__.py`, `app/main.py`, `app/config.py`, `app/db.py`, `app/templates.py`
- `app/api/__init__.py`, `app/api/health.py`, `app/api/todos.py`
- `app/models/__init__.py`, `app/models/todo.py`
- `templates/base.html`, `templates/home.html`
- `templates/_fragments/todo_item.html`, `templates/_fragments/todo_list.html`
- `static/style.css`
- `tests/conftest.py`, `tests/test_health.py`, `tests/test_todos.py`
- `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`
- `alembic/versions/001_create_todo_table.py`

### Infrastructure (GCP-specific)

- `Dockerfile` — single-stage Python 3.12 + uv, `~20` lines. Replaces
  the multi-stage Next.js standalone Dockerfile.
- `.dockerignore` — Python-centric exclusions
- `render.yaml` — **deleted**, not applicable to GCP
- `.github/workflows/deploy.yml` — Cloud Run + Artifact Registry + WIF.
  Runs `alembic upgrade head` against the production Neon URL before
  building and deploying the container.
- `.github/workflows/preview-deploy.yml` — Cloud Run revision tagging
  + Neon branch creation via `neondatabase/create-branch-action@v5`.
  Runs Alembic against the branch database before deploying the preview.
- `.github/workflows/preview-cleanup.yml` — deletes Neon branch + Cloud
  Run revision tag on PR close.
- `.github/workflows/rollback-production.yml` — traffic split to a
  previous Cloud Run revision; replaces Render's rollback API.

### Agent prompts (stack-aware guardrails)

- `.claude/agents/github-ticket-worker.md` — Stack Guardrails section
  rewritten for FastAPI/SQLModel/Neon/Cloud Run gotchas
- `.claude/agents/devops-engineer.md` — rewritten for GCP only,
  removing the multi-platform enumeration
- `.claude/agents/system-architect.md` — Platform Ecosystems rewritten
  for GCP services, database recommendation switched to Neon
- `.claude/commands/doctor.md` — secret checks updated for GCP/Neon;
  local checks use `uv` and `pyproject.toml` instead of `npm` and
  `package.json`
- `.claude/commands/bootstrap-architecture.md` — hardcoded to GCP
  Cloud Run, self-DSN env var references use `APP_URL`

### Documentation

- `docs/PLATFORM-GUIDE.md` — rewritten as a GCP-only setup walkthrough
- `docs/PATTERN-LIBRARY.md` — full rewrite; Cloud Run, Neon, FastAPI,
  SQLModel, HTMX patterns replace Render, Supabase, and Next.js patterns
- `docs/EPHEMERAL-PR-ENVIRONMENTS.md` — rewritten for the Cloud Run
  revision tagging + Neon branching architecture. Note: the
  `NEXT_PUBLIC_*` limitation section is gone because FastAPI has no
  build-time env var baking.
- `docs/CI-CD-GUIDE.md` — workflow table rewritten for GCP/Neon secrets,
  Python build commands, stack-specific troubleshooting

### Project metadata

- `CLAUDE.md` — tech stack, database, platform, build commands
- `README.md` — repositioned as "Gemba Flow (GCP + FastAPI Edition)",
  pointer to upstream for non-GCP or non-Python users

### New files

- `UPSTREAM.md` — this file
- `scripts/provision-gcp-project.sh` — idempotent GCP project bootstrap

## Unchanged Files (Should Track Upstream)

These files are platform- and stack-agnostic and should be synced from
upstream when the framework updates:

- `.claude/agents/agile-backlog-prioritizer.md`
- `.claude/agents/agile-product-manager.md`
- `.claude/agents/pr-reviewer.md`
- `.claude/agents/quality-engineer.md`
- `.claude/commands/*` (except `doctor.md` and `bootstrap-architecture.md`)
- `.claude/hooks/*`
- `.claude/skills/*`
- `.claude/settings.template.json`
- `.github/workflows/ci.yml` (language-agnostic, auto-detects stack)
- `.github/workflows/auto-fix.yml`
- `.github/workflows/auto-review.yml`
- `.github/workflows/auto-triage.yml`
- `.github/workflows/agent-audit-report.yml`
- `.github/workflows/release.yml`
- `.github/workflows/verify-agent-restrictions.yml`
- `.github/workflows/template-sync.yml`
- `docs/AGENT-*.md`
- `docs/AGENTIC-CONTROLS.md`
- `docs/ARTIFACT-FLOW.md`
- `docs/BRANCHING-STRATEGY.md`
- `docs/CONTEXT-OPTIMIZATIONS.md`
- `docs/DISTRIBUTION.md`
- `docs/FAQ.md`
- `docs/GETTING-STARTED.md`
- `docs/MAINTENANCE.md`
- `docs/MEMORY-ARCHITECTURE.md`
- `docs/TICKET-FORMAT.md`
- `docs/SENTRY-SETUP.md` — agent/self-receiver pattern is stack-agnostic
- `scripts/doctor.sh`
- `scripts/hooks/*`
- `scripts/setup-accounts.sh`
- `scripts/template-sync.sh`
- `scripts/validation/*`
- `scripts/verify-*`
- `scripts/lint-agent-policies.sh`
- `scripts/analyze-agent-actions.sh`
- `bootstrap.sh`
- `LICENSE`
- `VERSIONING.md`
- `CHANGELOG.md` — ours diverges quickly; stop tracking after the first sync

## Sync Procedure

When upstream Gemba Flow releases a new version:

1. Add the upstream as a remote (one-time):
   ```bash
   git remote add upstream https://github.com/vibeacademy/gembaflow.git
   ```

2. Fetch and review the diff:
   ```bash
   git fetch upstream main
   git log --oneline b9bd5e3..upstream/main
   ```

3. For each commit, decide:
   - **Framework fix** (agent prompt, command, utility) → cherry-pick or merge
   - **Render/Supabase-specific** → skip
   - **Next.js/TypeScript-specific** → skip
   - **Ambiguous** → read the diff and decide

4. Cherry-pick the safe ones:
   ```bash
   git cherry-pick COMMIT_SHA
   ```

5. For commits that touch files in the "Changed Files" list above, do a
   manual merge — the upstream changes may conflict with our rewrites.

6. Run the local smoke test after each sync:
   ```bash
   uv sync --extra dev
   uv run ruff check .
   uv run mypy app/
   uv run pytest
   docker build -t agile-flow-gcp-test .
   ```

7. Update the "Source Commit" line at the top of this file to the new
   upstream commit you synced to.

## License

Inherits the upstream BSL 1.1 license. See `LICENSE` for full terms.
