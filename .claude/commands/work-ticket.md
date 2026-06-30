---
description: Pick up and work on the next ticket from the Ready column
---

Launch the github-ticket-worker agent to implement the next prioritized ticket.

> **Reference**: See `docs/TICKET-FORMAT.md` for the expected ticket format.

## Pre-Flight Verification (REQUIRED)

Before starting work on any ticket, verify the following. STOP and report to
the user if any check fails — do not continue with partial tooling.

1. **`gh` CLI is authenticated and the repository is accessible** — Run
   `gh auth status` and `gh repo view --json nameWithOwner`. If either fails,
   STOP and instruct the user to fix the issue.
2. **GitHub account is correct** — Run `gh auth status` and confirm the active
   account matches the expected worker/bot account. If only a personal account
   is active, STOP and instruct the user to run `scripts/ensure-github-account.sh`.
3. **Claude hooks are registered** — Check that hook files referenced in
   `.claude/settings.local.json` exist and are executable. WARN if any hook is
   missing or not executable.
4. **Project board is accessible** — Attempt to read the project board. If
   access is denied or the board does not exist, STOP and report.

## Drain Mode Pre-Flight (REQUIRED when `DRAIN_CONTEXT` is set)

If `DRAIN_CONTEXT=true` is set in the environment (the signal that
`/work-ticket` was invoked from `/drain` — the drain orchestrator),
additionally verify:

1. **Safety class is present** — Run `gh issue view <N> --json labels`
   and confirm exactly **one** `safety:*` label is set. If zero or more
   than one, STOP with `safety:unclassified — abort`, leave the ticket
   in place, and signal the drain orchestrator to continue with the
   next ticket (greedy failure semantics — a missing classification is
   the operator's call to make, not the worker's).
2. **Safety class is drain-eligible** — The single label must be one of
   `safety:flagged`, `safety:internal`, or `safety:reversible`. If the
   label is `safety:hot`, STOP with `safety:hot — refused by drain`,
   leave the ticket in Ready, and signal continue. Hot tickets are a
   feature, not a failure; they wait for the operator.

Standalone `/work-ticket` (when `DRAIN_CONTEXT` is unset, e.g. a human
runs the skill directly) does NOT require a safety label — this preserves
backward compatibility for human-driven work. The two drain-mode checks
above are gated on the env var exactly so this guarantee holds.

See [`docs/safety-classes.md`](../../docs/safety-classes.md) for the
taxonomy decision tree and worked examples.

**Pre-substitution placeholder check.** If you see any of the four
bootstrap-time templated values (documented in
[`docs/PLATFORM-GUIDE.md`](../../docs/PLATFORM-GUIDE.md) §
"Bootstrap-time templated values") still in their raw `{{ ... }}` form
anywhere in this file or other `.claude/commands/*.md` files when you
read them, STOP with a message pointing the operator at
`bootstrap-workflow.md` — the substitution step hasn't run yet. Re-run
`bash scripts/substitute-config-placeholders.sh` (or re-bootstrap)
before proceeding. This avoids the failure mode where unsubstituted
template strings leak into runtime instructions.

## Critical Rules

1. **Branch from main**: `feature/issue-{number}-short-description`
2. **Move ticket to In Progress** on the project board before starting work
3. **All tests must pass before pushing** — never use `--no-verify`
4. **Monitor CI after PR creation**: `gh pr checks <PR_NUMBER> --watch` — fix failures up to 3 times
5. **Move ticket to In Review** only when CI passes
6. **Auto-handoff to `pr-reviewer` on green CI** — once CI is green and the ticket is in In Review, launch the `pr-reviewer` agent via the Task tool immediately. Do not pause for human approval; green CI means the human is out of the loop until the GO/NO-GO is posted. (Solo mode only — swarm mode skips this; the orchestrator handles review timing.)
7. **Never merge PRs** — human reviewer does this
8. **Never commit directly to main** — always use feature branches and PRs

## Workflow Steps

1. **Select Ticket** — Find top priority in Ready column, verify Definition of Ready, confirm no blockers
2. **Validate Ticket Format** — Check the ticket body for the 4 Power Sections:
   - **A. Environment Context**, **B. Guardrails**, **C. Happy Path**, **D. Definition of Done**
   - If any section is missing or empty:
     1. **STOP** and report to the user exactly which sections are missing —
        make the upstream formatting failure visible as a process problem
     2. Read `docs/TICKET-FORMAT.md`, `docs/TECHNICAL-ARCHITECTURE.md`,
        `docs/AGENTIC-CONTROLS.md`, and the parent epic
     3. Draft the missing sections following `docs/TICKET-FORMAT.md` exactly
     4. Present the draft to the user with a clear diff showing what was added —
        **do not proceed until the user explicitly approves**
     5. Update the GitHub issue with the user-approved version
   - If all 4 sections are present → proceed normally (no delay)
3. **Load Context from Past Sessions** — Query Memory MCP for relevant
   institutional knowledge (silently skip if Memory MCP is not configured
   or returns no results):
   - Extract domain keywords from the ticket title and labels
   - `search_nodes` for `Pattern-` matching those keywords (cap: 3 results)
   - `search_nodes` for `Lesson-` matching those keywords (cap: 3 results)
   - If the ticket has a parent epic, `search_nodes` for `CompletedTicket-`
     in that epic (cap: 4 results, most recent first)
   - Total cap: 10 entities. Summarize findings in a brief
     "Context from past sessions" note before proceeding.
   - If no relevant entities found, produce no output — proceed silently.
4. **Setup** — Create branch, move to In Progress
5. **Implement** — Follow CLAUDE.md standards, write clean code, follow existing patterns
6. **Test Locally** — Run lint and tests. Do NOT push if any fail.
7. **Push** — If pre-push hook fails, fix and retry (see Reference below)
8. **Create PR** — Detailed description, link to issue
9. **Monitor CI** — Watch checks, auto-fix failures (max 3 attempts), move to In Review when green
10. **Hand off to reviewer** — On green CI, launch the `pr-reviewer` agent via the Task tool with the PR number. Wait for the GO/NO-GO verdict to be posted before returning. If CI never reaches green within 3 fix attempts, do NOT hand off — leave the escalation comment per the protocol below and stop.

## Quick Fix Protocol

For small bug fixes, content updates, or changes that don't warrant full ticket
ceremony, use this lightweight workflow instead of the standard ticket flow.

**When to use Quick Fix Protocol:**
- Bug fixes found during development (not from a ticket)
- Content or copy updates (data files, presets, text changes)
- Config tweaks (linter rules, CI fixes, dependency bumps)
- Any change the user explicitly requests without a ticket

**Quick Fix Workflow:**
1. Create a branch: `fix/short-description` or `content/short-description`
2. Implement the change
3. Test locally — all tests must pass
4. Push and create PR with "Quick fix — no linked ticket" in the description
5. **Do NOT move any board items** — there is no linked ticket to move
6. **Do NOT guess which ticket this corresponds to** — if unsure, ask the user

**What Quick Fix does NOT skip:**
- Branch requirement (never commit to main)
- PR requirement (never merge without review)
- Test requirement (never push with failing tests)
- Account verification (still use worker bot account)

## Usage

```
/work-ticket
/work-ticket #123
```

---

## Reference Material

### Pre-Push Hook Failure Protocol

```bash
# 1. Read the error output
# 2. Fix the issue (often auto-fixable):
uv run ruff check . --fix
# 3. Stage and amend:
git add -A && git commit --amend --no-edit
# 4. Push again:
git push origin <branch> --force-with-lease
```

| Error | Fix |
|-------|-----|
| `W293 Blank line contains whitespace` | `uv run ruff check --fix` |
| `F401 imported but unused` | Remove the unused import |
| `I001 Import block is un-sorted` | `uv run ruff check --fix` |
| `pytest` failures | Fix the failing test or the code it tests |

### CI Monitoring Protocol

```bash
gh pr checks <PR_NUMBER> --watch
# If checks fail:
gh run list --branch <BRANCH> --status failure --limit 1 --json databaseId,name
gh run view <RUN_ID> --log-failed
# Fix, commit, push, repeat (max 3 attempts)
```

| Failure Type | Response |
|--------------|----------|
| Lint errors (ruff) | Fix the specific lint violations |
| Test failures | Fix the failing test or the code it tests |
| Import errors | Fix import paths or add missing dependencies |
| Build failures | Fix build configuration or dependencies |

### When to Stop Retrying

Stop after 3 fix attempts OR when encountering:

- Flaky tests that pass/fail randomly (note in PR comment)
- Infrastructure issues (GitHub Actions outage)
- Failures requiring architectural changes beyond ticket scope
- Missing secrets or environment configuration

**Escalation**: Leave a detailed PR comment explaining what was tried,
what's failing, and recommended next steps.

### Workflow Rules

- Only work on tickets from the Ready column
- One ticket at a time (no parallel work)
- Agent is responsible for delivering a clean, CI-passing PR

### Output Format

Report each step with a Progress Line, then end your output with a Result Block:

```
→ Moved #21 to In Progress
→ Created branch: feature/issue-21-health-check
→ Implemented health check endpoint
→ Tests passing (3/3)
→ Pushed to origin
→ Created PR #108
→ CI green (1 fix attempt: ruff)
→ Moved #21 to In Review
→ Handed off to pr-reviewer (GO posted)

---

**Result:** PR created and reviewed
PR: #108 — feat: add health check endpoint
Branch: feature/issue-21-health-check
Ticket: #21 — moved to In Review
CI: green
Review: GO posted by pr-reviewer
```

If CI does not reach green within 3 fix attempts, the handoff is skipped and the Result Block reflects the escalation instead:

```
→ Created PR #108
→ CI failed (3 fix attempts exhausted)
→ Posted escalation comment on PR
→ Ticket #21 left in In Progress

---

**Result:** PR created — escalated, no handoff
PR: #108 — feat: add health check endpoint
CI: red after 3 attempts (test failure: <summary>)
Review: not started — awaiting human
```
