---
description: Post a plain-language explanation comment on a ticket or PR so a non-engineer reader can follow what's happening
---

<!-- FRAMEWORK:START -->

# /eli5 — Explain Like I'm Five

Read a GitHub issue or PR and post a comment that translates the dense
Agentic-PRD-Lite content into plain language for a **non-engineer reader**.
Every technical term that shows up in the source is a teaching opportunity:
explain it inline, briefly, in words a founder, workshop attendee, or
non-technical stakeholder will understand.

The original body is **never modified** — agents keep reading the canonical
spec; humans read the comment.

> **Original prototype:** `vibeacademy/cubrox` commit `3ba35cb`. This
> upstream version rewrites the audience model (cubrox assumed a
> tech-adjacent reader; gembaflow assumes a non-engineer) and raises the
> word ceiling to give inline definitions room to breathe.

## Audience

**The operator reading this comment is NOT an engineer.** They are a founder
watching the board, a workshop attendee following along, an investor scanning
shipped work, or any stakeholder who does not already know what an API, JWT,
RLS policy, feature flag, or CI gate is.

That means:

- Every technical term encountered in the source body is a **teaching
  opportunity**, not a shortcut. Define it inline on first use.
- Err toward over-explaining. The cost of seeming condescending is small;
  the cost of leaving the reader behind is the whole point of the command.
- `ELI5` here means *educate*, not just *translate*.

This is the deliberate counter to commands like `/review-pr` and
`/work-ticket`, which assume an engineer audience.

## Critical Rules

1. **Never edit the issue or PR body.** Post a comment only. The canonical
   body is the source of truth for agents.
2. **One ELI5 comment per target.** Re-running detects the prior comment via
   the marker `<!-- eli5-generated -->` on line 1, deletes it, and posts a
   fresh one. **Re-runs delete-and-replace; they never append.**
3. **Soft word ceiling: 600 words.** This is a *guideline*, not a hard
   limit. If your ELI5 exceeds the ceiling, you are not translating — you
   are rewriting. Cut harder OR split the educational asides into a
   separate `## Glossary` section the reader can skip. Do not silently
   blow past 600 words with no glossary.
4. **Self-contained.** Never assume the reader has seen prior tickets,
   parent epics, or linked PRs. If parent-epic context is necessary,
   summarize it inline in one or two sentences — do not link out and
   expect the reader to follow.
5. **No new information.** Every claim must trace back to the body, parent
   epic, or linked artifacts. No speculation about timelines, business
   impact, or user reach unless the source explicitly says so.
6. **Render-check every Mermaid diagram before posting.** Broken Mermaid
   renders as garbled syntax in GitHub's UI — worse than no diagram. See
   the render-check protocol below.

## Inline-Definition Convention

When a technical term appears in the source body, define it inline on its
first use using the pattern:

```
<term> (<brief plain-language definition>)
```

Keep the definition under ~15 words. Worked examples:

- **JWT** — "JWT (a signed, tamper-proof token the server hands the
  browser to prove who's logged in)"
- **RLS** — "row-level security (a database rule that controls which
  rows a given user is allowed to see or edit, enforced inside the
  database itself rather than in app code)"
- **feature flag** — "feature flag (a toggle that turns code on or off
  for specific users without re-deploying)"
- **CI gate** — "CI gate (an automated check that has to pass before
  code can be merged — like a spell-check, but for tests)"
- **webhook** — "webhook (a way for one service to ping another the
  moment something happens, instead of asking 'is it done yet?'
  repeatedly)"

The goal is that a reader who has never written code can follow the
sentence on the first pass without needing to look anything up.

If the same term appears multiple times in the comment, define it only
on first use.

## Workflow

1. **Resolve target** — `/eli5 #91` (issue) or `/eli5 #94` (PR — `gh`
   auto-detects which). With no argument, scan the In Review column for
   the most-recently-updated item.
2. **Read the target** — Body + parent epic (for issues) or linked-issue
   body (for PRs) + recent comments for context (merge events, prior
   reviews, operator confirmations).
3. **Detect prior ELI5 comment** — Search comments for the marker
   `<!-- eli5-generated -->`. If found, delete it via
   `gh api -X DELETE /repos/{owner}/{repo}/issues/comments/<id>` (this
   endpoint covers PR comments too — they are issue comments under the hood).
4. **Generate the sections** below. Skip the diagram if it would have
   fewer than 3 nodes or wouldn't clarify anything.
5. **Render-check** any Mermaid block — see the protocol below. If it
   fails twice in a row, drop the diagram and proceed without it.
6. **Post the comment** with the marker on line 1 so re-runs can detect it.
7. **Print a one-line confirmation** with the comment URL.

## Usage

```
/eli5 #91        # issue
/eli5 #94        # PR (same syntax; gh auto-detects)
/eli5            # most-recently-updated In Review item
```

## Comment Template — Issue

````markdown
<!-- eli5-generated -->

## What's this ticket about?

<2-3 sentences. The problem the ticket is trying to solve, in plain
language. Lead with the user-visible or operator-visible impact —
"people who signed up before the change can't log in" beats "the
migration fails." Define any technical term on its first use using the
inline-definition convention above. Assume the reader has not seen any
prior ticket or PR — summarize parent-epic context inline if needed.>

## Why does it matter?

<What goes wrong if this isn't done, in concrete terms the reader can
picture. Not "the auth layer breaks" — instead "anyone trying to log in
after Tuesday will get an error page." If the ticket fixes a known
incident, name it.>

## What's the plan?

<The proposed approach in plain words. Stay at the strategy level. Cite
specific files only if the reader needs them to track progress; otherwise
describe what the change does, not where it lives in the code.>

## What should you watch for?

<Concrete observables the reader can actually see: a PR will appear at
URL X, CI (the automated checks) will go green or red, the staging site
at Y will look different, a workshop attendee will notice Z. Bullet list.>

- [ ] <observable thing> — <where the reader sees it>

[Optional: ## How it fits — Mermaid diagram if ≥3 nodes and it actually
clarifies the flow. Skip otherwise. If render-check fails twice, drop
this section entirely.]

[Optional: ## Glossary — only if the inline definitions made the body
exceed 600 words. Move the longer definitions here so the body stays
readable, and let curious readers scroll down for the deeper explanation.]

---
*Generated from #<N>. Re-run `/eli5 #<N>` to refresh after the ticket changes.*
````

## Comment Template — PR

````markdown
<!-- eli5-generated -->

## What changed?

<2-3 sentences. What user-visible or operator-visible behavior is
different after this merges. Define technical terms inline. Tie back to
the linked issue if it explains the "why" — but summarize the issue's
"why" here, do not assume the reader will click through.>

## Why this change?

<The motivation in plain words. Why now? What problem does this fix or
what capability does it add? If this is a follow-up to an incident or a
previous PR, summarize that context inline in one or two sentences.>

## What should you verify before merging?

<Reviewer-facing checks a non-engineer can actually perform — clicking
through a staging URL, confirming a workshop scenario, eyeballing a
screenshot. Pulled from the PR's "Test plan" but translated out of
engineer-speak.>

- [ ] <thing to check> — <how to check it>

## What should you watch for after merging?

<Operator-facing — a setting that may need flipping, a smoke test to
run, a dashboard to glance at. Skip if "nothing".>

- [ ] <action> — <where to do it>

[Optional: ## How it works — Mermaid diagram of the new flow if it
clarifies things. Skip if trivial. If render-check fails twice, drop
this section.]

[Optional: ## Glossary — only if needed to keep the body under 600 words.]

---
*Generated from PR #<N>. Re-run `/eli5 #<N>` to refresh after pushes.*
````

## Mermaid Render-Check Protocol

Broken Mermaid renders as a code block of garbled syntax in GitHub's UI,
which is worse than having no diagram at all. Always validate before posting:

```bash
# 1. Generate the mermaid block as $MERMAID.
# 2. Pipe to mmdc to validate. Use npx so no global install is needed.
echo "$MERMAID" | npx -y @mermaid-js/mermaid-cli -i - -o /tmp/eli5-check.svg 2>/tmp/eli5-err

# 3. If exit code != 0:
#    - Retry generation ONCE, feeding the stderr error back to the model.
#    - If the second attempt also fails, drop the diagram entirely and
#      post the comment WITHOUT the "How it fits" / "How it works" section.
# 4. If mmdc is unavailable (no npx, no network), proceed without the
#    render check but add an HTML comment noting it:
#      <!-- mermaid render-check skipped: mmdc unavailable -->
```

The render check catches the common LLM failure modes:

- Unbalanced quotes inside node labels
- Reserved keywords used as node ids
- Mixed diagram types in one block (e.g. `sequenceDiagram` opening
  paired with `graph LR` syntax)
- Mismatched edge syntax

## Reference Material

### What to translate vs. what to define inline

The audience is a non-engineer. There is no "keep as-is" column — every
technical term gets a brief inline definition on first use. The table
below shows the *style* of translation, not which terms to skip.

| In the source body | In the ELI5 comment |
|---|---|
| `app/api/auth.py:42` | "the login route (the bit of server code that handles sign-in requests)" |
| `JWT` | "JWT (a signed token the server hands the browser to prove who's logged in)" |
| `RLS policy` | "row-level security (a database rule that controls which rows a given user can see)" |
| `feature flag` | "feature flag (a toggle that turns code on/off for specific users without re-deploying)" |
| `CI gate` | "CI gate (an automated check that has to pass before code can merge)" |
| `--proxy-headers flag` | "a configuration that tells the server to trust the headers coming from Cloud Run (Google's hosting service)" |
| `webhook` | "webhook (a way for one service to ping another the moment something happens)" |

Product names (Cloud Run, GitHub Actions, Supabase, Vercel) can stay,
but the first time one appears, add a 3-5 word gloss: "Supabase (the
database-and-auth service we use)".

### When to include a diagram

- Auth/login flows → sequence diagram
- Schema or data-shape changes → entity diagram or table
- CI/deploy changes → flowchart of the pipeline before/after
- Architecture decisions → component graph
- Pure deletion / cleanup tickets → **skip**
- Tickets/PRs with fewer than 3 distinct steps or nodes → **skip**

Note that the worked-example *comment templates* above do not contain
Mermaid diagrams — that is intentional. The render-check protocol is the
implementation of the diagram feature; the templates illustrate *language*,
not diagrams. Add a diagram to an actual ELI5 comment when the rules
above warrant it.

### When to flag escalation in the action sections

- The target has a P0 label
- Definition of Done requires a billing decision (paid plan, secret rotation cost)
- DoD references "two weeks of clean production logs" or similar dwell-time gates
- A blocker is itself a multi-ticket chain (mention the chain length,
  e.g. "blocked by #91, which is blocked by #84")

### Output Format

End your output with a Result Block:

```
---

**Result:** ELI5 comment posted
Target: <issue|PR> #<N> — <title>
Comment URL: https://github.com/.../issues/<N>#issuecomment-<...>
Word count: <N> (ceiling 600)
Diagram included: <yes|no|dropped-after-render-failure>
Inline definitions: <count>
```

<!-- Source: Gemba Flow (https://github.com/vibeacademy/gembaflow) -->
<!-- SPDX-License-Identifier: BUSL-1.1 -->

<!-- FRAMEWORK:END -->
