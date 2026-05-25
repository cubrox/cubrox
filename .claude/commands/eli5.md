---
description: Add a plain-language explanation comment to a ticket or PR so tech-adjacent operators can act
---

Read a GitHub issue or PR and post a comment that translates the technical
content into a tech-adjacent summary, a verified Mermaid diagram (when
warranted), and a focused "what this means for you" action list. The
original body is **not modified** — agents keep reading the canonical
spec; humans read the comment.

## Critical Rules

1. **Never edit the issue or PR body.** Post a comment only. The canonical body is the source of truth for agents.
2. **One ELI5 comment per target.** Re-running detects the prior comment (via a hidden HTML marker), deletes it, and posts a fresh one. No comment pollution from repeated invocations.
3. **400-word ceiling on the comment.** If you can't fit it, you're not summarizing — you're translating word-for-word. Cut harder.
4. **No new information.** Everything in the ELI5 must be supported by the body, related epic, or linked PRs/issues. No speculation about timelines, user impact, or business value beyond what's written.
5. **Render-check every Mermaid diagram before posting.** Broken Mermaid renders as a code block of garbled syntax in GitHub's UI — worse than no diagram.
6. **Audience: tech-adjacent operator of reasonable intelligence.** They know what an API, JWT, database schema, CI gate, and feature flag are. They don't know what `app/services/identity/session.py` is unless you tell them.

## Workflow

1. **Resolve target** — `/eli5 #91` (issue) or `/eli5 #94` (PR — `gh` auto-detects which). With no argument, scan the In Review column for the most-recently-updated item.
2. **Read the target** — Body + parent epic (issue) or linked-issue body (PR) + recent comments for context (merge events, prior reviews, operator confirmations).
3. **Detect prior ELI5 comment** — Search comments for the hidden marker `<!-- eli5-generated -->`. If found, delete it via `gh api -X DELETE /repos/.../issues/comments/<id>` (works for both issues and PRs — PR comments are issue comments under the hood).
4. **Generate the four sections** below. Skip the diagram if it would have <3 nodes.
5. **Render-check** any Mermaid block — see the protocol below. If it fails twice in a row, drop the diagram and proceed.
6. **Post the comment** with the marker on line 1 so re-runs can detect it.
7. **Print a one-line confirmation** with the comment URL.

## Usage

```
/eli5 #91        # issue
/eli5 #94        # PR (same syntax; gh auto-detects)
/eli5            # most-recent In Review item
```

## Comment Template — Issue

````markdown
<!-- eli5-generated -->
## What this ticket is about

<One paragraph. Lead with the product / UX impact. If the ticket fixes a
known incident, name it. Use technical terms the audience already knows
(API, JWT, schema, rate limit, RLS). Translate internal terms (file
paths, library names, function names).>

## How it fits

```mermaid
<flowchart, sequence, or graph showing where this ticket sits in the
larger flow. Skip this section entirely if <3 nodes.>
```

## What this means for you

<Operator-side action items pulled from Definition of Done — only the
ones a human has to do. Bullet checklist. Each item names the action
AND where to do it.>

- [ ] <action> — <where to do it>

## What's blocking it (if anything)

<One sentence per blocker, in plain language. "Waiting on #X to merge
because Y." Skip if no blockers.>

---
*Generated from #<N>. Re-run `/eli5 #<N>` to refresh after the ticket changes.*
````

## Comment Template — PR

````markdown
<!-- eli5-generated -->
## What this PR does

<One paragraph. What user-visible or operator-visible behavior changes
after this merges. Tie back to the linked issue if it explains the "why".>

## How it works

```mermaid
<diagram of the new flow or before/after architecture. Skip if trivial.>
```

## What to verify before merging

<Reviewer-facing — what should the human reviewer click through or
confirm? Pulled from the PR's "Test plan" + any operator items the PR
itself surfaces.>

- [ ] <thing to check>

## What to do after merging

<Operator-facing — Cloud Run env var to update, dashboard config to
flip, smoke test to run, etc. Skip if "nothing".>

- [ ] <action> — <where to do it>

---
*Generated from PR #<N>. Re-run `/eli5 #<N>` to refresh after pushes.*
````

## Mermaid Render-Check Protocol

```bash
# 1. Generate the mermaid block.
# 2. Pipe to mmdc to validate. Use npx so no global install needed.
echo "$MERMAID" | npx -y @mermaid-js/mermaid-cli -i - -o /tmp/eli5-check.svg 2>/tmp/eli5-err

# 3. If exit code != 0:
#    - Retry generation ONCE, feeding the stderr error back to the model
#    - If second attempt also fails, drop the diagram entirely
#      (post the comment without the "How it fits" / "How it works" section)
# 4. If mmdc is unavailable (no npx, no network), proceed without the
#    render check but add an HTML comment noting it:
#      <!-- mermaid render-check skipped: mmdc unavailable -->
```

The render check catches the common LLM failure modes:

- Unbalanced quotes inside node labels
- Reserved keywords used as node ids
- Mixed diagram types in one block (e.g. `sequenceDiagram` opening but `graph LR` syntax)
- Mismatched edge syntax

## Reference Material

### What to translate vs. keep technical

Audience is tech-adjacent: knows what an API, JWT, schema, RLS, JOIN, env var, CI gate, OAuth, secret manager, and webhook are. Does NOT know your file structure, internal function names, or specific library APIs.

| Translate | Keep as-is |
|---|---|
| `app/api/auth.py:42` → "the login route" | `JWT`, `RLS`, `CORS`, `OAuth` |
| `sign_in_with_otp()` → "Supabase's magic-link send" | "API endpoint", "database schema" |
| `itsdangerous.URLSafeTimedSerializer` → "the legacy cookie signer" | "rate limit", "feature flag" |
| `--proxy-headers` flag → "telling uvicorn to trust Cloud Run's forwarded headers" | Cloud Run, GitHub Actions, Supabase (product names) |
| Workflow YAML keys → "the auto-deploy pipeline step that..." | URLs (clickable) |

### When to include a diagram

- Auth/login flows → sequence diagram
- Schema or data-shape changes → entity diagram or table
- CI/deploy changes → flowchart of the pipeline before/after
- Architecture decisions → component graph
- Pure deletion / cleanup tickets → skip
- Tickets/PRs with <3 distinct steps or nodes → skip

### When to flag escalation in the action sections

- The target has a P0 label
- Definition of Done requires a billing decision (paid plan, secret rotation cost)
- DoD references "two weeks of clean production logs" or similar dwell-time gates
- A blocker is itself a multi-ticket chain (mention the chain length, e.g. "blocked by #91 which is blocked by #84")

### Output Format

End your output with a Result Block:

```
---

**Result:** ELI5 comment posted
Target: <issue|PR> #<N> — <title>
Comment URL: https://github.com/.../issues/<N>#issuecomment-<...>
Diagram included: <yes|no|dropped-after-render-failure>
Action items: <count> (reviewer: <N>, operator: <N>)
```
