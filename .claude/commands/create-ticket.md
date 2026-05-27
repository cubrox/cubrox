---
description: Create a well-structured ticket that meets Definition of Ready
---

Create a new ticket on the project board with guided workflow.

## Pre-Flight Verification (REQUIRED)

Before creating any ticket, verify the following. STOP and report to the user
if any check fails — do not continue with partial tooling.

1. **`gh` CLI is authenticated and the repository is accessible** — Run
   `gh auth status` and `gh repo view --json nameWithOwner`. If either fails,
   STOP and instruct the user to fix the issue.
2. **GitHub account is correct** — Run `gh auth status` and confirm the active
   account matches the expected worker/bot account. If only a personal account
   is active, STOP and instruct the user to run `scripts/ensure-github-account.sh`.
3. **Project board is accessible** — Attempt to read the project board. If
   access is denied or the board does not exist, STOP and report.

## Critical Rules

1. **Every ticket must meet Definition of Ready** before being added to the board
2. **Use the board configuration** from the project's GitHub Project settings
3. **Never create duplicate tickets** — search existing issues first
4. **Assign appropriate priority** (P0 = critical, P1 = important, P2 = nice to have)

## Workflow

1. **Understand** — Ask clarifying questions about the feature/fix/task
2. **Gather Context** — Read `docs/TECHNICAL-ARCHITECTURE.md` and `docs/PRODUCT-REQUIREMENTS.md` to pre-populate Environment Context and Guardrails
3. **Research** — Search existing issues to avoid duplicates, check related code
4. **Draft** — Write the ticket following the template below
5. **Scope Check** — If effort estimate is XL or the happy path has multiple branch points, suggest decomposition before creating
6. **Review** — Present the draft to the user for approval
7. **Create** — Create the GitHub issue and add it to the project board
8. **Categorize** — Set priority, size estimate, and move to Backlog

## Ticket Format

**Do not use an inline template.** Read `docs/TICKET-FORMAT.md` before drafting
any ticket — it is the single source of truth and contains the full specification
with examples.

Every ticket MUST include these 5 components:

1. **Standard Fields** — Problem Statement, Parent Epic, Effort Estimate, Priority
2. **A. Environment Context** — Populate from `docs/TECHNICAL-ARCHITECTURE.md`
   and the existing codebase (stack, integration points, files to modify)
3. **B. Guardrails** — Populate from `docs/AGENTIC-CONTROLS.md` and PRD
   non-functional requirements (security rules, performance targets, prohibitions)
4. **C. Happy Path** — Numbered steps: Input → Logic → Output. One flow per ticket.
5. **D. Definition of Done** — Specific test assertions, lint/type commands,
   reviewer-verifiable outcomes. Not vague.

### Self-Check Before Presenting Draft

Before showing the draft to the user, verify:
- [ ] Problem Statement is 2-3 sentences, not a paragraph
- [ ] Sections A-D are all present and non-empty
- [ ] Environment Context references specific files, not generic descriptions
- [ ] Guardrails include at least one explicit prohibition
- [ ] Happy Path has numbered steps with data shapes
- [ ] Definition of Done has concrete assertions (not "tests pass")
- [ ] Effort estimate is provided; if XL, suggest decomposition

## Usage

```
/create-ticket
/create-ticket Add health check endpoint to the API
```

### Output Format

End your output with a Result Block:

```
---

**Result:** Ticket created
Issue: #45 — feat: add health check endpoint
Priority: P1
Size: S
Column: Backlog
```
