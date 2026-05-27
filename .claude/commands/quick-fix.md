---
description: Apply a small fix or content change without full ticket ceremony
---

Make a quick, targeted change (bug fix, content update, config tweak) using a
lightweight workflow that skips ticket creation and board management.

## Pre-Flight Verification (REQUIRED)

Before any work, verify the following. STOP and report if any check fails.

1. **GitHub account is correct** — Run `gh auth status` and confirm the active
   account matches the expected worker/bot account. If only a personal account
   is active, STOP and instruct the user to run `scripts/ensure-github-account.sh`.
2. **`gh` CLI is authenticated and the repository is accessible** — Run
   `gh auth status` and `gh repo view --json nameWithOwner`. If either fails,
   STOP and instruct the user to fix the issue.

## When to Use This Command

- Bug fixes found during development (not from a ticket)
- Content or copy updates (data files, presets, text changes)
- Config tweaks (linter rules, CI fixes, dependency bumps)
- Any change the user explicitly requests without a ticket

**Do NOT use this for feature work.** If the change introduces new behavior,
touches more than 3 files, or takes longer than ~1 hour, create a ticket with
`/create-ticket` and use `/work-ticket` instead.

## Workflow

1. **Confirm scope** — Describe the change to the user in 1-2 sentences. If
   the user hasn't specified what to fix, ask before proceeding.
2. **Create branch** — `fix/short-description` or `content/short-description`
3. **Implement** — Follow CLAUDE.md standards, write clean code
4. **Test locally** — Run lint and tests. Do NOT push if any fail.
5. **Push and create PR** — Include "Quick fix — no linked ticket" in the PR
   description body
6. **Skip board updates** — Do NOT move any board items. There is no linked
   ticket. Do NOT guess which ticket this corresponds to.

## What This Command Does NOT Skip

- Branch requirement (never commit to main)
- PR requirement (never merge without review)
- Test requirement (never push with failing tests)
- Account verification (still use worker bot account)
- Human merge (agent never merges)

## Usage

```
/quick-fix
/quick-fix Fix typo in footer component
/quick-fix Update API base URL in config
```
