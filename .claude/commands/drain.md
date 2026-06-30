---
description: Drain the Ready column autonomously by looping work-ticket → review-pr → agent-merge → validate for each safely-classified ticket, using Claude Code's /goal primitive as the loop driver
---

Drain the Ready column autonomously. Use Claude Code's built-in `/goal` primitive
as the loop driver; this skill supplies the project-specific structure
(pre-flight production-baseline check, Ready snapshot + safety filter,
per-iteration work-ticket + review-pr + agent-merge gate + production
validation, audit emit, rate limits, hard-stop conditions).

> **Reference**: ADR-006 in [`docs/TECHNICAL-ARCHITECTURE.md`](../../docs/TECHNICAL-ARCHITECTURE.md) — the architectural decision that v1 wraps `/goal` in this project-local skill, deferring "true unattended overnight" to a future API-bridge ticket.

## Audience and pre-conditions

You are the operator (`tck517`). Before invoking this skill:

- **The Ready column has been groomed** — every ticket has a `safety:*` label
  (per `docs/safety-classes.md`) and the 4 Power Sections (per `docs/TICKET-FORMAT.md`).
- **You accept the v1 trade-off** that your machine + Claude Code session must
  stay active while the drain runs (laptop awake, session open). Remote
  unattended operation is a future ticket.
- **You will make the release decision in the morning** — drain only merges
  code to `main`, where it ships dark on production behind feature flags. The
  flag flip (visibility = on for real users) stays a human decision.

## Pre-Flight Verification (REQUIRED — fail closed)

Verify ALL of the following BEFORE setting the `/goal` condition. STOP and
report to the user if any check fails — do not begin the loop with partial
or unhealthy state.

1. **`gh` CLI is authenticated as `cubrox`** — `gh auth status` shows
   `cubrox` as the active account. If not, run `gh auth switch -u cubrox`.
2. **Repository accessible** — `gh repo view --json nameWithOwner` succeeds.
3. **Project board accessible** — `gh project view 2 --owner cubrox`
   succeeds. Board operations during the drain require this scope.
4. **`agent-merge.yml` exists on `main`** — the merge gate from `#129` must be
   discoverable on the default branch (otherwise `gh workflow run agent-merge.yml`
   returns HTTP 404 — see `Lesson-workflow-dispatch-default-branch`).
5. **Production baseline is healthy** — run `node scripts/sentry-baseline.mjs`
   and compare the returned `baseline_errors_per_min` against the 24-hour
   median. If the current baseline is >2× the 24h median, **abort with a
   production-degraded notice** and post a comment on the originating
   invocation explaining why. Do not begin a drain on top of an already-soft
   production.
6. **At least one `safety:*` label is set on every Ready ticket** — if any
   Ready ticket lacks a safety class, STOP with the unclassified ticket
   number named, and instruct the operator to classify before re-invoking.

## Snapshot, sort, filter, plan

After pre-flight clears:

1. **Snapshot the Ready column** — `gh project item-list 2 --owner cubrox --limit 100 --format json`, filter for `status == "Ready"`.
2. **Topo-sort by `Depends on:` lines** in each ticket's body. Any ticket whose
   declared dependency is not in `Done` state goes to the back of the order
   (or is skipped if the dependency is itself still in Ready and the drain
   would process it first).
3. **Filter by safety class.** Default filter: `safety:flagged` and
   `safety:internal` only. Include `safety:reversible` ONLY if the operator
   explicitly passed `--include-reversible` in the invocation. `safety:hot`
   is ALWAYS filtered out (per the taxonomy — drain refuses). **For each
   `safety:hot` ticket filtered out, post an audit comment on the ticket
   itself** explaining drain skipped it and pointing to the morning manual
   queue — so the ticket carries its own breadcrumb, not just the wake-up
   summary's aggregate listing (per `#132` hardening sub-item 3).
4. **Emit the plan summary** as a comment on the originating drain invocation
   (a long-lived issue or PR designated for the run; if none, create a
   transient issue titled `drain run YYYY-MM-DDTHH:MMZ`). The summary uses
   this structured shape (per `#132` hardening sub-item 2 — replaces the
   prior prose-only form):

   ```markdown
   ## Drain plan

   **Run identifier:** drain-<UTC timestamp>
   **Started:** <ISO timestamp>
   **Production baseline (pre-drain):** <baseline_errors_per_min> errors/min
   **Completion condition:** /goal evaluates (a)-(d) after each turn (see below)

   | Order | Ticket | Class | Effort | Est wall-clock | Cumulative |
   |---|---|---|---|---|---|
   | 1 | #X | safety:internal | S | 45min | 45min |
   | 2 | #Y | safety:reversible | M | 120min + 30min rate-limit pause | 195min |

   **Total estimate:** <N> hours
   **Rate-limit pauses:** <K>×<window>min for reversibles
   **Skipped at filter time:** <list of safety:hot tickets with audit comment links>
   ```

   Wall-clock heuristic by effort class (averages from past tickets,
   refine over time): XS≈15min, S≈45min, M≈120min, L≈240min. Rate-limit
   pause adds `DRAIN_REVERSIBLES_WINDOW_MIN` (default 30) between
   consecutive `:reversible` tickets.

## Set the `/goal` condition

The loop driver. Set the condition as a single `/goal` invocation:

```text
/goal "Ready column drained. The condition is met when one of these holds:
  (a) the Ready-column snapshot taken at run start has been fully processed
      (every snapshot ticket is now either Done, In Review, or Blocked); OR
  (b) three consecutive tickets have failed (any combination of red CI,
      NO-GO review, agent-merge gate denial, or post-merge validation
      failure); OR
  (c) the production baseline has degraded mid-run (Sentry rate > 2× the
      pre-drain baseline) and a single post-rollback re-baseline failed to
      restore health; OR
  (d) the operator passed `--until <ISO time>` and that time has passed.

After each turn, the Haiku evaluator confirms whether one of (a)–(d) holds.
If not, another turn fires automatically to advance one more ticket
through the cycle below."
```

## The per-iteration cycle (one ticket per turn)

Within each `/goal` turn, advance exactly ONE ticket through these steps.
Stop the turn after the validation step (whether pass or fail); the next
turn picks up the next ticket.

1. **Pick the top ticket** from the topo-sorted snapshot that hasn't been
   touched yet.
2. **Rate-limit check for `safety:reversible`** — if the picked ticket is
   `:reversible` and a previous `:reversible` ticket merged less than the
   configured window ago in this drain run, skip it for now (it'll be
   picked again on a later turn). Move to the next ticket. **Window is
   configurable** via `DRAIN_REVERSIBLES_WINDOW_MIN` env var; default 30
   minutes (per `#132` hardening sub-item 1). All configuration knobs are
   listed in the "Configuration knobs" section below.
3. **Move the ticket to In Progress** on the project board.
4. **Invoke `/work-ticket <N>` with `DRAIN_CONTEXT=true` set.** The drain-
   mode pre-flight in `work-ticket.md` will verify the safety class is
   present and drain-eligible before proceeding. The `/work-ticket` flow
   handles its own work + push + CI watch + chained `/review-pr`.
5. **If `/work-ticket` reports CI red after 3 fix attempts** — mark the
   ticket Blocked with an audit comment, increment the consecutive-failure
   counter, and end the turn.
6. **If `/review-pr` returned NO-GO** — same as above.
7. **If both green:** signal the drain-merge bridge via
   `repository_dispatch`. The bridge
   (`.github/workflows/drain-merge-bridge.yml`) calls `agent-merge.yml`
   via `workflow_call` — the only path through which the gate permits
   real merges per its safety contract (see ADR-007).

   ```bash
   gh api -X POST /repos/$(gh repo view --json nameWithOwner -q .nameWithOwner)/dispatches \
     -f event_type=drain-merge \
     -F client_payload[pr_number]=<PR>
   ```

   Then wait for the bridge workflow run to complete (poll
   `gh run list --workflow=drain-merge-bridge.yml --limit 1 --json status`
   until `completed`); capture the bridge run ID AND the called gate run
   ID for the audit.
8. **If the gate denied the merge** — mark the ticket Blocked with an audit
   comment naming the gate's denial reason, increment the consecutive-
   failure counter, end the turn.
9. **Wait for the merge's deploy to land on production.** Poll Render's API
   for the deploy of the merge commit; require status `live` before
   proceeding. Time budget: 10 minutes; on timeout, treat as a failed
   validation and proceed to step 11.

   ```bash
   # Poll every 30s for up to 10 minutes; --slack and --post-issue not used here.
   # Per #194: after 5 consecutive pending results AND no deploy ever
   # started for our merge SHA, fall back to manually triggering the
   # deploy via Render API (Render's GH integration is empirically
   # unreliable; auto-deploy intermittently doesn't fire). Opt-out via
   # DRAIN_RENDER_AUTO_TRIGGER=false.
   PENDING_COUNT=0
   AUTO_TRIGGERED=false
   for i in $(seq 1 20); do
     RESULT=$(node scripts/render-deploy-status.mjs "$MERGE_SHA")
     LIVE=$(echo "$RESULT" | jq -r '.live')
     SOURCE=$(echo "$RESULT" | jq -r '.source')
     STATUS=$(echo "$RESULT" | jq -r '.status')
     if [ "$LIVE" = "true" ]; then break; fi
     if [ "$SOURCE" = "unavailable" ]; then
       # Token unconfigured OR Render API unreachable — fall back to the v1
       # curl liveness probe (per docs/testing/render-gating.md §Fallback)
       break
     fi
     if [ "$STATUS" = "pending" ]; then
       PENDING_COUNT=$((PENDING_COUNT + 1))
     else
       PENDING_COUNT=0
     fi
     if [ "$PENDING_COUNT" -ge 5 ] && [ "$AUTO_TRIGGERED" = "false" ] && [ "${DRAIN_RENDER_AUTO_TRIGGER:-true}" != "false" ]; then
       # 5 consecutive pending (~2.5 minutes) with no deploy ever found
       # for this SHA — auto-deploy webhook didn't fire. Trigger manually.
       echo "[drain] step 9: auto-deploy didn't fire for ${MERGE_SHA:0:7}; triggering manually (per #194)"
       curl -s -X POST -H "Authorization: Bearer $RENDER_API_TOKEN" \
         -H "Content-Type: application/json" -d '{}' \
         "${RENDER_API_BASE:-https://api.render.com/v1}/services/$RENDER_SERVICE_ID/deploys" > /dev/null
       AUTO_TRIGGERED=true
       # Reset pending counter — the new deploy starts from scratch
       PENDING_COUNT=0
     fi
     sleep 30
   done
   ```

   When `RENDER_API_TOKEN` + `RENDER_SERVICE_ID` are configured (see
   "Configuration knobs" below + `docs/testing/render-gating.md`), this
   polls until the _specific_ merge's deploy is `live` — meaning subsequent
   validation hits the new code, not the old one. When the env vars are
   unset (the v1 default before `#180` shipped, and the safe fallback for
   when Render's API is unreachable), the loop exits immediately on
   `source: "unavailable"` and the curl probe in step 10 alone gates
   liveness (the same v1 substitution used during the first real drain
   run on 2026-06-08).

   **Auto-trigger fallback (per `#194`):** if 5 consecutive `pending`
   results indicate no deploy was ever found for the merge SHA (Render's
   GH integration didn't fire), the loop triggers a manual deploy via
   `POST /v1/services/{id}/deploys` with empty body — Render then builds
   the latest commit on `main` (which IS our merge). Opt-out via
   `DRAIN_RENDER_AUTO_TRIGGER=false` env var. The fallback fires at most
   once per ticket cycle (`AUTO_TRIGGERED` flag) so a failed manual deploy
   doesn't trigger an endless retry loop.

   ### Verification methods to AVOID (per `#217`)

   Two channels look like deploy-progress signals but lie:

   - **`gh api commits/<sha>/status`** — Render IS receiving GitHub
     webhooks, IS building, and IS deploying, but does not always
     post status back to GitHub. Empirically silent on healthy
     deploys; treating `state: pending, statuses: []` as "deploy
     didn't fire" reads the wrong channel. Do not use as a deploy-
     progress signal under any circumstance. See `docs/drain-verification.md`
     for the postmortem on two false-positive Merged-NotDeployed
     verdicts (#152 and #210) that traced to this channel.
   - **Raw-character content-marker greps against rendered HTML** —
     markdown's `&` renders as `&amp;` in HTML; `<` as `&lt;`; `"` as
     `&quot;`. A grep for a marker containing any of those characters
     misses content that's actually there.

   ### Approved verification methods

   - **`node scripts/render-deploy-status.mjs <SHA>`** is the
     authoritative deploy-state reader. If it returns `source:
     "unavailable"` with `hint: "env vars not visible..."`, the
     credentials are likely fish-universal-only and not inherited by
     Bash — retry via `fish -c "node scripts/render-deploy-status.mjs <SHA>"`
     to confirm before treating the deploy as failed. See saved lesson
     `claude-code-bash-does-not-inherit-fish-universal-vars`.
   - **Entity-encoding-aware content markers** when the curl fallback
     is the only verification path: prefer path segments
     (`/bootstrap-product`), heading slugs (`workshop-printing`), or
     alphanumeric prose. Avoid markers containing `&`, `<`, `>`, `"`,
     or `'`.

10. **Run post-merge validation** — the deploy URL is fork-specific; export it as
    `PUBLIC_BASE_URL` before invoking, e.g. `export PUBLIC_BASE_URL=https://<your-deploy>.<provider>.example`.
    `PLAYWRIGHT_BASE_URL="$PUBLIC_BASE_URL" npx playwright test --grep @smoke-production`.
    For `safety:internal` tickets, the lightweight alternative is
    `curl -fsS "$PUBLIC_BASE_URL/api/health" && curl -fsS "$PUBLIC_BASE_URL/"`
    returning 200 from both (per the architecture report's lightweight-internal-validation rule).
    For `safety:internal` tickets that ship content rather than infra,
    the curl probe SHOULD additionally grep for at least one entity-
    encoding-safe marker (path segment, heading slug, or alphanumeric
    prose) — NOT a marker containing `&`, `<`, `>`, `"`, or `'` (per
    `#217`; markdown's `&` renders as `&amp;` in HTML and raw-character
    greps silently miss it).
11. **If validation passes:** mark the ticket Done. Reset the consecutive-
    failure counter to 0. Post an audit comment on the originating ticket
    naming the merge commit, the deploy ID, and the validation result.
12. **If step 9 reported a terminal deploy failure** (`build_failed`, `update_failed`, `canceled`)
    **AND no rollback target is available** (the merge's deploy never landed —
    Render kept the previous successful deploy live; nothing to revert to at
    Render's level): mark the ticket **Merged-NotDeployed** (per `#189`).
    Apply the `drain-stuck-on-deploy` label. Increment the consecutive-failure
    counter. Skip step 13 (rollback) entirely — there's no deploy to roll back
    from. Post an audit comment explaining the merge-but-no-deploy state.
    This outcome is **distinct from Blocked-Rolled-Back**: the rollback path
    fires only when a deploy successfully landed AND post-deploy validation
    failed; the Merged-NotDeployed path fires when the deploy itself never
    landed. Conflating them would mislead the morning operator (no rollback
    actually happened; nothing to investigate at the rollback layer).
13. **If validation fails after a successful deploy:** trigger `gh workflow run rollback-production.yml`
    with the previous good deploy ID. Wait for the rollback to complete.
    Mark the ticket Blocked-Rolled-Back. Increment the consecutive-failure
    counter. Re-baseline production (steps in pre-flight #5); if the
    re-baseline FAILS, hard-stop the drain.
14. **End the turn.** `/goal`'s evaluator checks the completion condition;
    if not met, fires another turn.

## Audit emit (per ticket)

After each turn, the drain MUST leave a comment on the originating ticket
naming:

- The drain run identifier (the originating invocation reference).
- The outcome: Done / Blocked / Blocked-Rolled-Back / Skipped.
- The PR number created (if any) and the merge commit (if merged).
- The workflow run IDs for `agent-merge.yml` and validation.
- The Sentry baseline before vs after (for Done outcomes).
- The reason (for Blocked / Rolled-back / Skipped).

The audit comment is the load-bearing artifact for the morning review —
the operator should be able to reconstruct what happened to every ticket
from these comments alone.

## Wake-up summary (end of run)

When `/goal` reports the condition met (or when the drain hard-stops),
collect the per-ticket outcomes into a state JSON and pipe it through
`scripts/emit-drain-summary.mjs` to render the canonical Markdown
summary, then post it as a comment on the originating drain invocation.
The script also fires an optional Slack ping when
`DRAIN_SLACK_WEBHOOK_URL` is set in the environment.

```bash
# State JSON shape lives in scripts/emit-drain-summary.mjs (the
# top-of-file comment). The skill writes it incrementally during the
# per-iteration cycle and finalizes at run end.
node scripts/emit-drain-summary.mjs /tmp/drain-state.json --slack --post-issue "$DRAIN_ISSUE"
```

(`--post-issue` shells to `gh issue comment <N> --body-file -` per `#178`.
Replaces the prior two-line pipe-to-tmp-file-then-gh pattern. The Markdown
still prints to stdout as well, so the operator can also pipe or save it
locally if needed.)

The summary covers six sections (per `__tests__/emit-drain-summary.test.ts`):

| Section | Content |
|---|---|
| Tickets shipped (Done) | Numbers + titles, with safety class, PR link, merge SHA, and audit-comment links |
| Tickets blocked | Numbers + titles + reason summary + PR link |
| Tickets rolled back | Numbers + titles + the rollback workflow run ID |
| Tickets merged but not deployed (per `#189`) | Numbers + titles + safety class + PR link + merge SHA + reason (e.g., Render `build_failed`) + audit-comment link |
| Tickets skipped (`safety:hot` or rate-limited) | Numbers + titles + reason |
| Production status at end of run | Sentry baseline before vs after + last health-check result + healthy/DEGRADED verdict |
| Recommended morning actions | Auto-synthesized: release flip for shipped `safety:flagged` tickets; triage for blocked; investigation for rolled-back; manual-queue promotion for skipped `:hot`; abort-cause investigation if aborted |

The summary is emitted even when the drain aborts early (per
`#131` guardrail) — partial info beats silent failure. Runs that
ship >20 tickets get a "large drain — flagged for daytime human
review" warning prepended.

## Critical Rules

1. **Never bypass the agent-merge gate.** Always dispatch via `gh workflow run agent-merge.yml`; never invoke `gh pr merge` directly. The gate's 7-condition re-verification is the load-bearing safety boundary.
2. **Never demote a `safety:hot` ticket during the run.** Hot tickets are explicitly out of scope for autonomous processing. If the operator wants a hot ticket merged, they do it themselves.
3. **Never advance past production-baseline degradation OR mid-run Merged-NotDeployed accumulation.** Re-baseline after every rolled-back ticket; if the re-baseline fails, hard-stop. If two or more tickets accumulate the Merged-NotDeployed outcome in the same run, hard-stop — the deploy pipeline is unhealthy and continuing would stack more stuck merges on top of broken infrastructure (per `#189`).
4. **Never run more than one `safety:reversible` ticket per `DRAIN_REVERSIBLES_WINDOW_MIN`-minute window** (default 30, configurable). The architecture report's rate-limit isn't optional — it exists because two reversibles back-to-back failing makes the rollback ambiguous. See the "Configuration knobs" section below for the env var.
5. **Never modify board state for a ticket the drain didn't touch.** The snapshot is taken at run start; tickets added to Ready mid-run are processed in the NEXT drain, not this one.
6. **`safety:flagged` tickets ship dark; the flag flip is a human decision.** The drain never lifts a flag; it only merges code behind one. The morning release decision belongs to the operator.

## Invocation shape

```text
/drain                           # default: process flagged + internal; no end time
/drain --until 06:00             # stop at 6am if Ready isn't empty by then
/drain --include-reversible      # opt-in to processing reversibles (rate-limited)
/drain --max-tickets 5           # cap the number of tickets processed
/drain --dry-run                 # emit the plan summary; do not execute
/drain --resume <drainId>        # resume an interrupted drain run (per #204)
/drain --resume                  # auto-detect most recent interrupted drain
```

`--dry-run` invokes everything through the snapshot + topo-sort + filter +
plan-summary emit, then stops without setting the `/goal` condition. Useful
for verifying the plan before bed.

`--resume` re-enters a drain that was interrupted (typically by an
Anthropic API error or operator session close). It reads the on-disk
state file from `/tmp/drain-state-<drainId>.json`, reconciles against
real-world state (PR/bridge/Render/board), and continues from the
appropriate cycle step. See [`docs/drain-resumption.md`](../../docs/drain-resumption.md)
for the mechanism, edge cases, and cleanup discipline.

## Configuration knobs

All drain tunables are env vars, listed here so they're reviewable in a
single block (per `#132` hardening guardrail):

| Env var | Default | Purpose |
|---|---|---|
| `DRAIN_REVERSIBLES_WINDOW_MIN` | `30` | Minimum minutes between consecutive `safety:reversible` merges in a single drain run (per-iteration cycle step 2 + Critical Rule #4). Lower values make drains run faster but make rollback ambiguity more likely when multiple reversibles fail back-to-back. |
| `DRAIN_SLACK_WEBHOOK_URL` | _(unset)_ | Optional Slack webhook for the wake-up summary's short-form ping. Wake-up summary still posts to the originating drain issue regardless; this just adds an external channel. Unset → no Slack call (per `scripts/emit-drain-summary.mjs` env-gating contract). |
| `DRAIN_CONTEXT` | _(unset)_ | Set to `true` by this skill before invoking `/work-ticket <N>` so the work-ticket pre-flight applies drain-mode safety-class checks (per `work-ticket.md` "Drain Mode Pre-Flight"). |
| `DRAIN_RENDER_AUTO_TRIGGER` | `true` | When `true` (default), step 9 falls back to manually triggering a Render deploy via API after 5 consecutive `pending` polls indicate the auto-deploy webhook didn't fire (per `#194` — Render's GH integration is empirically unreliable). Set to `false` to opt out and let step 9 simply time out instead. Opt-out makes sense when the operator wants to investigate provider-side reliability issues rather than work around them. |

The Sentry-baseline pre-flight (#5) reads its own env vars
(`SENTRY_API_URL`, `SENTRY_AUTH_TOKEN`, `SENTRY_ORG`, `SENTRY_PROJECT`)
per `docs/testing/sentry-gating.md` — those are independent of drain
configuration and live in the operator's shell config, not in this
table.

Similarly, the Render-deploy-status step (#9 in the per-iteration cycle)
reads its own env vars (`RENDER_API_TOKEN`, `RENDER_SERVICE_ID`,
optional `RENDER_API_BASE`) per `docs/testing/render-gating.md`. When
those env vars are unset, step 9's `scripts/render-deploy-status.mjs`
call returns `source: "unavailable"` and the loop exits immediately;
step 10's curl probe alone gates liveness (the v1 fallback). Setting
the env vars upgrades step 9 from "some version is alive" to "this
merge's deploy is live."

## State persistence & resumption (per `#204`)

Drain runs are operator-active per ADR-006 — the operator's machine
must stay on and the Claude Code session must stay open. Empirically
the Anthropic API errors mid-run from time to time (rate limit, 5xx,
transient outage), halting the session and forcing manual re-engagement.
Per `#204`, the skill writes its in-flight state to disk at 9 trigger
points so a `/drain --resume` can re-enter cleanly without re-doing
work the original run already shipped.

### State file location

`/tmp/drain-state-<drainId>.json` — one file per drain run. Written
atomically (`<file>.tmp` → `mv` to final path) so a partial write
can't corrupt the resume payload.

### State JSON shape

The canonical shape lives in the top-of-file comment of
[`scripts/emit-drain-summary.mjs`](../../scripts/emit-drain-summary.mjs).
Mid-run fields (`currentCycle`, `currentCycleStep`, `currentTicket`,
`snapshotOrder`, `lastWriteTime`) are written by this skill and read
by the `--resume` reconciliation logic. End-of-run fields (the bucket
arrays + `productionStatus`) are read by the renderer for the wake-up
summary.

### The 9 state-write trigger points

State is written immediately after each:

1. Pre-flight verification clears
2. Snapshot + topo-sort + filter + plan-summary emit completes
3. A ticket is moved to In Progress (per-cycle step 3)
4. A PR is created and pushed (per-cycle step 4)
5. The drain-merge bridge dispatch fires (per-cycle step 7)
6. Render reports the merge's deploy is `live` (per-cycle step 9 exits success)
7. Post-deploy validation passes (per-cycle step 11)
8. A ticket lands in Blocked / Rolled-Back / Merged-NotDeployed
   (per-cycle step 12 or 13)
9. The drain hard-stops (any of the four termination conditions)

State writes are **best-effort**. A disk-write failure logs a warning
to stderr but does not halt the drain — the worst case is "runs
without resumability," not "runs are corrupted."

### `--resume` invocation contract

When invoked, `--resume` does the following in order:

1. **Locate the state file.** If `<drainId>` was passed, read
   `/tmp/drain-state-<drainId>.json`. If no arg was passed, find the
   most recent `/tmp/drain-state-*.json` whose drain-anchor issue is
   still Open; refuse with a diagnostic if zero or more than one
   candidate matches.
2. **Verify the drain is in-flight.** Confirm the drain-anchor issue
   (`state.drainIssue`) is still Open. If it's Closed, refuse with a
   diagnostic — the previous run was wrapped up, the saved state is
   stale, and resuming would mutate already-final state.
3. **Reconcile `currentTicket` with real-world state.** Between
   interruption and resume, the world may have moved:
   - **(a) PR not yet created** — re-enter at per-cycle step 4
     (`/work-ticket <N>`)
   - **(b) PR open, CI red/pending** — re-enter at the CI-watch loop
     in `/work-ticket`'s step 9
   - **(c) PR open, CI green, no review yet** — re-enter at
     `/work-ticket`'s step 10 (chained `/review-pr`)
   - **(d) PR approved, bridge not yet dispatched** — re-enter at
     per-cycle step 7 (bridge dispatch)
   - **(e) Bridge dispatched, run not yet complete** — re-enter at the
     bridge-completion poll in step 7
   - **(f) Bridge succeeded, Render not yet polled** — re-enter at
     per-cycle step 9 (Render poll)
   - **(g) Render reports live, validation not run** — re-enter at
     per-cycle step 10 (validation)
   - **(h) Validation already ran, audit comment not posted** —
     re-enter at step 11/12/13 (mark outcome + audit comment)
4. **Mark the run as resumed.** Set `state.resumedFromInterruption = true`,
   `state.originalStartTime = state.startTime` (preserved),
   `state.resumedAt = <now>`, `state.startTime = state.resumedAt`. The
   wake-up summary's renderer reads these to prepend the resumption
   banner.
5. **Process the remaining tickets** in `state.snapshotOrder` (the
   topo-sorted initial array) starting from the position after
   `currentTicket`, applying the standard per-iteration cycle.

### When NOT to use `--resume`

- The operator already manually completed the in-flight cycle outside
  the skill (e.g., merged the PR, ran validation by hand). The saved
  state is stale; delete it (`rm /tmp/drain-state-<drainId>.json`) and
  start a fresh drain on the remaining tickets.
- The interruption was longer than a few hours and the production
  baseline has shifted significantly. Re-baseline manually before
  deciding whether `--resume` is safer than a fresh run.
- The drain-anchor issue has been Closed (the previous wake-up summary
  was already posted). `--resume` refuses; this is intentional.

### State file cleanup

Files older than 24 hours can be safely removed:

```bash
find /tmp -maxdepth 1 -name 'drain-state-*.json' -mtime +1 -delete
```

The skill does not auto-cleanup — the operator's discipline. A stale
file on disk doesn't cause harm; it just consumes space. `--resume`
without an arg auto-filters to drains whose anchor issue is Open, so
old state files don't accidentally route a resume to the wrong drain.

## Output format

End the drain with a single result line on the originating invocation:

```text
**Result:** Drain complete
Tickets processed: <N>
Shipped: <S>  Blocked: <B>  Rolled back: <R>  Skipped: <K>
Production status: healthy | degraded
Wake-up summary: <comment URL>
```

If the drain hard-stopped, the result line names the reason:

```text
**Result:** Drain halted
Reason: <consecutive-failure threshold | re-baseline failure | rollback failure | operator cancelled>
Last action: <ticket # and outcome>
Wake-up summary (partial): <comment URL>
```

## Related commands

- [`/work-ticket`](work-ticket.md) — the per-ticket workhorse. Drain invokes it with `DRAIN_CONTEXT=true`.
- [`/review-pr`](review-pr.md) — auto-chained from `/work-ticket` on green CI per project policy.
- [`agent-merge.yml`](../../.github/workflows/agent-merge.yml) — the conditional merge gate. Drain dispatches it per ticket.
- [`/groom-backlog`](groom-backlog.md) — the daytime work that fills Ready before invoking `/drain`.

## Reference reading

- ADR-006 in `docs/TECHNICAL-ARCHITECTURE.md` — the architectural decision behind this skill.
- `docs/safety-classes.md` — the taxonomy `/drain` filters on.
- `docs/agent-merge-gate.md` — the gate `/drain` dispatches per ticket.
- `docs/feature-flags.md` — the convention behind `safety:flagged` (dark deploy, morning flip).
- `reports/autonomous-drain-2026-06-03.md` — the architecture report that motivated this work (§5 taxonomy, §6 workflow shape, §11 bot model, §13 devops review items).
