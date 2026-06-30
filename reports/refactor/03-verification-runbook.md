# Verification Runbook: `cubrox` -> `masterkey` Rename

**Companion to:** `reports/refactor/03-verification.sh`
**Architecture plan:** `reports/refactor/01-architecture-plan.md` (v2)
**DevOps sign-off:** `reports/refactor/02b-devops-signoff.md`
**Author:** Quality Engineer persona
**Date:** 2026-06-29

---

## 1. What this gives you

`03-verification.sh` is a read-only health checker that proves the
five things the refactor must achieve without breaking:

1. The rename is complete (no stale `cubrox` / `agile-flow-app` references
   outside the allowlisted historical/framework paths).
2. CI/CD wiring is intact (workflows, vars, secrets, WIF bindings).
3. Ephemeral PR-preview deploys still work end-to-end (the explicit user
   requirement — Phase 3 step 25 and Phase 4 of the plan).
4. Nothing data-bearing migrated by accident (Supabase project ref
   `gnswmcgaztcxslirulwm` and the GCP project ID remain unchanged).
5. Local dev (`uv` + `supabase`) and remote (Cloud Run new service) come
   up clean.

The script is divided into ten sections (A-J), each independently
runnable via `--section`. Failures in one section do not abort the
others — every check executes on every run.

---

## 2. When to run

| Phase from the plan | What to run | Expected result |
|---------------------|-------------|-----------------|
| Pre-flight (Phase 0) | `bash reports/refactor/03-verification.sh --section A` | A1-A5 PASS — baseline snapshot captured under `reports/refactor/snapshots/<ts>/`. Everything else: failures are the **expected pre-rename state** and constitute the diff baseline. |
| End of Phase 1 (code PR open) | `bash reports/refactor/03-verification.sh --section B,J,H` | B1-B7 + J1-J4 + H1-H2 PASS. Sections C-G expected to still fail because GH/GCP haven't been touched yet. |
| End of Phase 2 (repo rename + WIF dual-write) | `bash reports/refactor/03-verification.sh --section C,E` | C1-C4 + E1-E2 PASS. E3 will be informational ("old binding still present" is fine until Phase 5). |
| End of Phase 3 (Cloud Run + AR pre-created) | `bash reports/refactor/03-verification.sh --section F,G` | F1-F4 PASS. F5 informational. G1-G3 PASS (G4-G6 only run with `--exercise-preview-deploy`). |
| Dry-run gate (Phase 3 step 25) | `bash reports/refactor/03-verification.sh --section G --exercise-preview-deploy` | G4-G6 PASS — see §5 for the manual variant. |
| After Phase 4 cutover | `bash reports/refactor/03-verification.sh` (full run) | All sections PASS except potentially E3+F5 informational, and I4 (SKIP — dashboard-only). |
| 30 days post-Phase-5 cleanup | `bash reports/refactor/03-verification.sh` | Everything PASS; E3 should flip to "old binding pruned" and F5 to "old service deleted". |

Run the script BEFORE making any change in a phase to capture state, and
again AFTER, so the diff is meaningful. Snapshots are written into
`reports/refactor/snapshots/<utc-timestamp>/` and never overwritten —
the script is idempotent in this sense.

---

## 3. Prerequisites

The script degrades to SKIP for any check whose tool isn't available,
so missing prerequisites only narrow coverage — they never break the
run.

| Tool / setting | Used by | Install / configure |
|----------------|---------|---------------------|
| `bash` 4+ | everything | preinstalled on macOS; `brew install bash` for newer features (not strictly required) |
| `gh` authed | A1-A3, C1, C4, D1-D4, G3-G6 | `gh auth login` (uses your personal account in solo mode per CLAUDE.md) |
| `gcloud` authed + project set | A4-A5, E1-E3, F1-F5, H3 | `gcloud auth login && gcloud config set project <id>` |
| `jq` | E1-E3 IAM parsing | `brew install jq` |
| `uv` | H2 (pytest) | `brew install uv` (per CLAUDE.md "Build & Test Commands") |
| `supabase` CLI | I3 | `brew install supabase/tap/supabase` |
| `curl` | C3, F2-F3, H3, G5 | preinstalled |
| `git` | C2, G4 | preinstalled |

### Environment variables read

| Var | Required by | Purpose |
|-----|-------------|---------|
| `GCP_PROJECT_ID` | section A,E,F,H | falls back to `gcloud config get-value project` |
| `GCP_SERVICE_ACCOUNT` | section A5, E | deployer SA email (same value as `secrets.GCP_SERVICE_ACCOUNT`) |

The script never reads any other env var. It does not write any.

---

## 4. Interpreting output

### Status semantics

- **`[PASS] <id> — <desc>`** — check executed and met its expectation.
- **`[FAIL] <id> — <desc> — <reason>`** — check executed and the expected
  invariant was NOT met. The reason includes a pointer to the relevant
  plan step. The script's final exit code is non-zero if any FAIL occurred.
- **`[SKIP] <id> — <desc> — <reason>`** — check's prerequisites were not
  met (e.g., `gcloud` not authed, `jq` missing, `--exercise-preview-deploy`
  not passed). SKIPs do not contribute to the exit code.

### Exit codes

- `0` — every executed check passed (skips are OK).
- `1` — at least one check failed; see the **Failures** block in the
  summary for the list with reasons.
- `2` — invalid command-line flag.

### Re-running after a fix

The script is idempotent. Re-run the same `--section` subset; previously-
fixed checks should flip to PASS without any side effects.

---

## 5. The ephemeral preview deploy test (section G — highest-risk requirement)

This is the explicit user requirement. Section G has two modes.

### 5.1 Static mode (default) — read-only

Runs G1-G3. Confirms:

- `preview-deploy.yml` still wires `vars.CLOUD_RUN_SERVICE` and
  `vars.ARTIFACT_REPO` correctly.
- `preview-cleanup.yml` reads the same vars.
- The repository vars have been flipped to `masterkey`, so a preview
  would push to the new AR and tag the new service.

If any of these fail, do **not** open a PR — the preview build will
deploy to the wrong place or fail authentication.

### 5.2 Active mode — `--exercise-preview-deploy`

Runs G4-G6. This is the **only mutating path** in the script. It will:

1. Create a throwaway branch `verify/preview-deploy-<UTC-ts>`.
2. Append a single timestamp comment to this runbook file
   (so there's a diff to commit; no semantic change).
3. Commit + push, then open a PR labelled `phase3-dryrun` with a body
   that says "Auto-created by 03-verification.sh — SAFE TO CLOSE".
4. Poll for up to 12 minutes for `preview-deploy.yml` to finish.
5. Extract the preview URL from the auto-generated PR comment and
   curl `/api/health`.
6. Close the PR + delete the branch, then check that
   `preview-cleanup.yml` ran.

**Do not run active mode if:**
- there are real PRs in flight (their preview-deploy runs may queue
  behind this one)
- `vars.CLOUD_RUN_SERVICE` is mid-flip (Phase 4 step 29) — wait until
  the var is settled
- the `masterkey` Cloud Run service does not yet exist (Phase 3 step 23
  unfinished — F1 will be FAIL; do not exercise)

### 5.3 Manual fallback if active mode times out

If G4 times out (workflow runs longer than 12 min) or G6's cleanup
conclusion is "pending", follow this manual checklist:

1. `gh pr list --label phase3-dryrun --state all` — find the PR number.
2. `gh run list --workflow=preview-deploy.yml --branch <branch> --limit 1`
   — verify the workflow ran and look at its conclusion.
3. Read the PR comment (the workflow injects it via `actions/github-script`,
   marker `## Preview Deployment`). The comment table shows the preview
   URL, the Cloud Run tag (`pr-N`), the DB source, and the smoke-test result.
4. `curl https://pr-N---masterkey-<hash>-uc.a.run.app/api/health` —
   expect HTTP 200.
5. After PR close: `gh run list --workflow=preview-cleanup.yml --limit 5`
   — find the corresponding cleanup run; conclusion should be `success`.
6. `gcloud run services describe masterkey --region=us-central1 --format='value(status.traffic[].tag)'`
   — confirm `pr-N` is no longer in the tag list.

### 5.4 Supabase Auth allowlist (linked to preview test)

The script CANNOT query the Supabase Auth redirect allowlist via API
without a service-role key embedded in the dashboard. Check I4 will
always SKIP. Manually verify in the Supabase dashboard:

- Navigate to **Authentication** → **URL Configuration** → **Redirect URLs**.
- Confirm both `https://pr-*---masterkey-*-uc.a.run.app/auth/callback`
  (preview) and `https://masterkey-<hash>-uc.a.run.app/auth/callback`
  (production) are present.
- Per R12: do NOT remove the old `agile-flow-app` patterns until
  Phase 5 step 37 (24-48h post-cutover stability confirmed).

---

## 6. Known false positives & how to suppress them

| ID | Symptom | Why it can false-positive | Mitigation built into the script |
|----|---------|---------------------------|----------------------------------|
| **B1** (most likely) | Reports a `cubrox` reference in a file that is "legitimately historical" but is not on the allowlist (e.g., a new session journal under a non-`reports/session-journals/` path). | Allowlist is path-regex-based. New session journals or ADRs that legitimately reference the old name need to be added. | Edit `ALLOWLIST=(...)` in `03-verification.sh` section_B; each entry has a comment explaining why. Add new lines with the same documentation convention. |
| B2 | Same pattern, for `agile-flow-app`. | Same. | Same allowlist edit in `ALLOWLIST_AFA=(...)`. The upstream-synced docs (`PLATFORM-GUIDE.md`, `CI-CD-GUIDE.md`) are intentionally allowed because the plan §2.6 left the per-doc decision (add to `.agile-flow-overrides` vs. accept the drift) up to the maintainer. |
| C3 | Old repo URL returns HTTP 200 instead of a 301/302 redirect. | If the rename has not happened yet, the URL still resolves normally. PASSes in that case. Only FAILs if it returns 404 (rename happened > 30 days ago and grace lapsed). | Three-way branch in the check distinguishes these cases. |
| E3 / F5 | Reports old WIF binding / old service "still present". | Plan keeps both for the 30-day grace window. | Marked as informational PASS with a `note` line. |
| H1 | `scripts/doctor.sh` exits non-zero due to a WARN-level finding unrelated to the rename. | doctor.sh's contract is non-zero on any WARN+FAIL; many warns are baseline-noisy. | Treated as informational — the script reports H1 PASS regardless and prints a note telling the operator to run `bash scripts/doctor.sh` directly. |
| I2 | Reports zero occurrences of the Supabase project ref. | Would only happen if someone accidentally migrated the project ref (out-of-scope per plan §6). The check FAILs intentionally — there is no false-positive scenario worth suppressing. | Do NOT suppress. If this fails, treat as P0. |
| I4 | Always SKIP. | Supabase Auth allowlist requires manual dashboard access. | See §5.4 above for the manual procedure. |

### The single check most likely to false-positive: **B1**

Path-regex allowlists are inherently fragile against new files added
to historical-record locations. To extend safely:

1. Run `bash reports/refactor/03-verification.sh --section B` and read
   the violation list.
2. For each genuinely-historical file, add a regex line to `ALLOWLIST=`
   with a one-line comment explaining WHY it's allowlisted (which plan
   section authorises it).
3. Re-run to confirm the violation count dropped to zero.
4. Commit the allowlist change in the same PR as whatever code change
   added the historical file — that way the allowlist is reviewed
   alongside the content.

**Do not** widen the allowlist via broad regexes (e.g., `.*\.md$`) —
that defeats the check's purpose.

---

## 7. Maintenance

This script intentionally encodes the architecture plan's constants
(`NEW_REPO`, `NEW_SERVICE`, `SUPABASE_PROJECT_REF`, etc.) at the top.
If any of those change in a future refactor, edit the constants block,
not the per-check logic.

The `--section` flag is the contract for partial runs. If you add a
new section (K, L, ...), update both the `main()` function and the
"When to run" table in §2 of this runbook.

Snapshots accumulate forever under `reports/refactor/snapshots/`. Prune
them periodically; they are diagnostic-only and not consumed by any
automation.

---

**Result:** Verification runbook ready — companion to `03-verification.sh`
Sections: 10 (A-J), each independently runnable via `--section`
Hard requirement covered: ephemeral preview deploy verification (§5, gated behind `--exercise-preview-deploy`)
Manual checks documented: I4 (Supabase Auth allowlist) + §5.3 (preview-deploy fallback)
False-positive guard: B1/B2 allowlists are explicit regex lists with per-entry rationale
