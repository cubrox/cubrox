<!-- FRAMEWORK:START -->
# Gemba Flow - Claude Code Project Template

## >>> CRITICAL RULES — Read These First <<<

1. **Never commit directly to `main`.** All work on feature branches (`feature/issue-{number}-short-description`). All changes through pull requests.
2. **All tests must pass before pushing.** Never use `git push --no-verify`. Fix the failing checks instead.
3. **Conventional commits required.** Format: `<type>(<scope>): <subject>`. See `.claude/skills/commit.md` for types and scopes.
4. **Only humans merge PRs.** Agents create PRs and review them. Humans approve and merge.
5. **Solo mode is the default.** A fork's gh + git operations use the user's personal account. Set `GEMBAFLOW_WORKER_ACCOUNT` and `GEMBAFLOW_REVIEWER_ACCOUNT` env vars to opt into multi-bot mode (separation of duties, appropriate for production teams with provisioned bot accounts). `AGILE_FLOW_*` is still accepted as a deprecated fallback. The `.claude/hooks/ensure-github-account.sh` hook handles account switching for multi-bot mode automatically.
6. **No emojis in ASCII tables.** They break column alignment. Emojis OK in prose and headings.
7. **One canonical location per fact.** Don't duplicate content across CLAUDE.md, agent files, and skills.
8. **Never hardcode application URLs.** Use `window.location.origin` (client-side) or request headers (server-side) so code works in both production and PR preview environments.

---

## Critical Requirements

> **TL;DR:** Trunk-based dev, quality-driven workflow, pre-push verification.

### Trunk-Based Development (REQUIRED)

- `main` branch is protected — no direct commits
- All work on short-lived feature branches
- Branch naming: `feature/issue-{number}-short-description`
- PRs require review before merge, keep branches short-lived (< 1 day)

The agent workflow depends on this:

1. `github-ticket-worker` creates feature branches and PRs
1. `pr-reviewer` reviews PRs (cannot merge — human does)
1. Human performs final review and merge

### Pre-push Hook (REQUIRED)

```bash
git config core.hooksPath scripts/hooks
```

The hook auto-detects the language stack and runs lint + tests before push.
**`--no-verify` is forbidden.**

### Quick Fix Protocol

For changes under 20 lines that don't alter behavior (broken imports, lint
errors, typos): skip ticket ceremony but still use branch + PR.

---

## Agent Configuration

> **TL;DR:** 6 agents with non-overlapping authority. Worker and reviewer
> have NON-NEGOTIABLE PROTOCOL blocks. Only humans merge.

| Agent | Role | Owns | Cannot Do |
|-------|------|------|-----------|
| Product Manager | Strategy | Vision, go/no-go, feature eval | Backlog management |
| Product Owner | Tactics | Backlog, tickets, priorities | Strategic decisions |
| Ticket Worker | Implementation | Code, tests, PRs | Merge PRs |
| PR Reviewer | Quality Gate | Code review, recommendations | Merge PRs |
| Quality Engineer | Validation | Test plans, reports | Implementation |
| System Architect | Design | Architecture, patterns | Implementation |

### Account model

This template supports two modes. **Solo mode is the default** for new
forks; multi-bot mode is the production opt-in.

**Solo mode (default)** — one personal account plays all roles
(worker, reviewer, human merger). Recommended for workshops, tutorials,
individual learners, and framework evaluation. Bootstrap with
`bash scripts/setup-solo-mode.sh` (see `docs/GETTING-STARTED.md`).
Activated by `GEMBAFLOW_SOLO_MODE=true` (set automatically in
Codespaces via `.devcontainer/devcontainer.json`).

**Multi-bot mode (production)** — separate worker + reviewer bot
accounts plus a human merger. Provides separation of duties and an
audit trail. Requires bot account provisioning
(`scripts/setup-accounts.sh`). Activated by setting
`GEMBAFLOW_WORKER_ACCOUNT` (default: `va-worker`) and
`GEMBAFLOW_REVIEWER_ACCOUNT` (default: `va-reviewer`) env vars.
The `.claude/hooks/ensure-github-account.sh` hook auto-switches to
the right account before `gh pr create` and `gh pr review`.

Choose based on use case, not phase. Workshop attendees stay in solo
mode for the entire workshop. Production teams adopt multi-bot once
they have provisioned bot accounts and a documented PAT-rotation
schedule.

### GitHub CLI (`gh`)

Agents use the `gh` CLI for all GitHub operations (issues, PRs, reviews,
board ops). In solo mode, `gh` operates as the user's personal account
throughout. In multi-bot mode, each bot account authenticates via
`gh auth login` and the `.claude/hooks/ensure-github-account.sh` hook
switches to the correct account automatically before PR creation and
review operations.

### MCP Servers

MCP servers are defined in `.mcp.json` (project root). The bootstrap
wizard creates this file automatically. Configure allowed tools in
`.claude/settings.local.json` (see `.claude/settings.template.json`).

| Server | Required | Token |
|--------|----------|-------|
| `memory` | Yes | none |
| `sequential-thinking` | No | none |

---

## Formatting Standards

> **TL;DR:** No emojis in tables, GitHub-flavored markdown, code blocks
> with language specifiers.

- No emojis inside ASCII tables (they break alignment)
- Use GitHub-flavored markdown with clear heading hierarchy
- Code blocks with language specifiers
- Tables for structured data

### Agent Output Format

Every agent output MUST follow these patterns. Full spec: `docs/AGENT-OUTPUT-STANDARD.md`

**Result Block** — every completed action ends with:

```
---

**Result:** <one-line outcome>
<key-value pairs, one per line>
```

**Progress Lines** — multi-step workflows report each step:

```
→ Step completed
✗ Step failed — see output above
```

**Standard Vocabulary** — use these terms only, no synonyms:

| Category | Terms |
|----------|-------|
| Decisions | GO / NO-GO / CONDITIONAL |
| Status | On Track / At Risk / Blocked |
| Findings | Required change (blocking) / Suggestion (non-blocking) |
| Effort | S (1-4h) / M (0.5-2d) / L (2-5d) / XL (5+d) |

**GitHub References** — first mention: `#N — title`. Subsequent: bare `#N`.

**Section Order** (multi-section reports): Context → Findings → Recommendations → Result Block

<!-- FRAMEWORK:END -->

---

## Project-Specific Configuration

### Project Information

- **License**: BSL 1.1 (converts to Apache 2.0 after 3 years per release)
- **Project Name**: Cubrox
- **Repository**: https://github.com/vibeacademy/cubrox
- **Project Board**: https://github.com/orgs/vibeacademy/projects/29
- **Tech Stack**: FastAPI + Jinja2 + HTMX on Python 3.12
- **Database layer**: SQLModel + Supabase CLI migrations (`supabase/migrations/*.sql`)
- **Platform**: Google Cloud Platform (Cloud Run)
- **Database**: Supabase Postgres (Pro plan, branching enabled; project ref `gnswmcgaztcxslirulwm`)
- **Auth**: Supabase Auth (GoTrue magic-link via `supabase-py`; JWT in HttpOnly cookie)
- **Container Registry**: Artifact Registry
- **Secrets**: Google Secret Manager
- **Package manager**: uv
- **Organization**: vibeacademy
- **LLM**: Anthropic Claude API (`claude-haiku-4-5` for comprehension questions, with prompt caching + Postgres result cache)
- **PDF**: pdfplumber, in-process, ≤25 MB
- **Observability**: Google Cloud Logging + Error Reporting
- **Architecture doc**: `docs/TECHNICAL-ARCHITECTURE.md`

### Build & Test Commands

```bash
uv sync --extra dev                              # Install dependencies
uv run uvicorn app.main:app --reload --port 8080 # Dev server
uv run ruff check .                              # Lint
uv run ruff format .                             # Format
uv run mypy app/                                 # Type check
uv run pytest                                    # Tests
uv run pytest --cov=app --cov-report=term-missing # Tests with coverage
supabase start                                   # Start local Supabase stack (needs Docker)
supabase stop                                    # Stop local Supabase stack
supabase status                                  # Show local stack URLs + keys
supabase db reset                                # Reset local DB and re-apply migrations
docker build -t agile-flow-app .                 # Local container build
```

### Definition of Ready

A ticket is ready when it has: clear title, description with context,
testable acceptance criteria, effort estimate, priority label, no blockers.

### Definition of Done

A ticket is done when: all acceptance criteria met, code reviewed and
approved, tests passing, no lint errors, PR merged to main.

---

<!-- FRAMEWORK:START -->
## Reference

> Detailed documentation lives in `docs/`. Consult as needed.

| Document | Contents |
|----------|----------|
| `docs/AGENTIC-CONTROLS.md` | 8-layer defense-in-depth controls |
| `docs/CONTEXT-OPTIMIZATIONS.md` | Context engineering principles |
| `docs/SENTRY-SETUP.md` | Sentry + GitHub integration setup |
| `docs/CI-CD-GUIDE.md` | Workflows, secrets, troubleshooting |
| `docs/PLATFORM-GUIDE.md` | Deployment platform options and setup |
| `docs/GETTING-STARTED.md` | First-time setup walkthrough |
| `docs/FAQ.md` | Common questions for non-engineers |
| `docs/TICKET-FORMAT.md` | Agentic PRD Lite ticket format (canonical) |
| `docs/PATTERN-LIBRARY.md` | Known solutions for Cloud Run/Supabase/GitHub silent failures |
| `docs/ARTIFACT-FLOW.md` | Artifact flow diagrams and authority matrix |
| `docs/AGENT-WORKFLOW-SUMMARY.md` | Complete workflow documentation |
| `docs/MAINTENANCE.md` | Weekly audit and maintenance guide |
| `docs/LAUNCH-CHECKLIST.md` | M1 go-live runbook: pre-flight gates, GO/NO-GO sign-off, incident/rollback |
| `docs/DISTRIBUTION.md` | Framework/user-content boundary classification |
| `docs/MEMORY-ARCHITECTURE.md` | Agent memory system: persistence types, data flow, known gaps |
| `scripts/doctor.sh` | Local diagnostic script (standalone) |

### Slash Commands

| Command | Description |
|---------|-------------|
| `/groom-backlog` | Prioritize tickets, populate Ready |
| `/work-ticket` | Pick up next ticket and implement |
| `/review-pr` | Review PRs in In Review column |
| `/check-milestone` | Check milestone progress |
| `/research` | Market research with web search |
| `/jtbd` | Jobs-to-be-Done user analysis |
| `/positioning` | Product positioning analysis |
| `/evaluate-feature` | Evaluate feature for strategic fit |
| `/release-decision` | Go/no-go decision |
| `/sprint-status` | Board health overview |
| `/test-feature` | Create test plan and validate |
| `/architect-review` | Architectural guidance |
| `/lock-scope` | Lock MVP scope |
| `/doctor` | Environment health check (local + remote) |
| `/upgrade` | Upgrade framework files to latest release |
<!-- FRAMEWORK:END -->
