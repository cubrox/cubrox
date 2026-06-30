# Refactor Backlog: `cubrox` → `masterkey`

**Author:** Backlog Prioritizer persona (Product Owner)
**Date:** 2026-06-29
**Status:** DRAFT — pending product-owner approval before loading into a live GitHub Project board
**Source artifacts:**
- `reports/refactor/01-architecture-plan.md` (v2) — phased plan, risk register
- `reports/refactor/02b-devops-signoff.md` — DevOps verdict ALIGNED
- `reports/refactor/03-verification.sh` + `03-verification-runbook.md` — 41-check verification harness
- `docs/TICKET-FORMAT.md` — Agentic PRD Lite ticket format (canonical)

This document is a draft. It does **not** create live GitHub issues. Once approved, the proposed labels + epics + tickets can be loaded into a fresh GitHub Project board under `github.com/users/cubrox/projects/<new>` (note: `cubrox` is a user account, not an org — see §Pre-loading findings below).

---

## Pre-loading findings (read before approving)

These are facts about the *current* state that bear on how the backlog must be loaded:

1. **`cubrox` is a GitHub user account, not an organization.** `gh api graphql user(login:"cubrox")` resolves; `organization(login:"cubrox")` returns NOT_FOUND. The new project board URL will be `github.com/users/cubrox/projects/<n>`, NOT `github.com/orgs/cubrox/projects/<n>`. Tickets that refer to "the new cubrox-org board" in the plan need to be re-read as "the new cubrox-user board" — functionally identical, only the URL pattern differs.
2. **Legacy `vibeacademy/projects/29` has 67 items** (open + closed, per `gh api graphql organization(login:"vibeacademy") projectV2(number:29)`). The migration ticket (E4-T2) must verify item count parity post-migration.
3. **Labels already in `cubrox/cubrox`** — full list inventoried via `gh label list`. Reuses: `epic`, `documentation`, `P0`, `P1`, `P2`, `area/ops`, `area/auth`, `area/ingestion`, `area/comprehension`, `area/reading`, `area/a11y`, `area/metric`, `audit`, `safety`, `security`, `synthetic-monitor`, `incident`, `epic/supabase-migration` (existing convention `epic/<name>`).

---

## Label scheme

Minimal label set designed to (a) fit conventions already in the repo, (b) avoid label proliferation, and (c) support filtering by phase + by type + by risk for an operator running `gh issue list --label phase/3 --label type:infra`.

### Reused labels (already in repo)

| Label | Where it applies |
|-------|------------------|
| `epic` | All six epics (E1-E6) |
| `P0` | Highest-blast-radius tickets (repo rename, var flip, WIF dual-write) |
| `P1` | Current-sprint refactor work |
| `P2` | Phase 5 cleanup (30-day-delayed) |
| `documentation` | Doc-only tickets (E2 doc-pass, E6 doc consolidation) |
| `area/ops` | Tickets touching infra/CI-CD/scripts |
| `audit` | Pre/post snapshot, verification harness runs |
| `safety` | Tickets that gate destructive ops (WIF verify, pre-flight checklist) |
| `synthetic-monitor` | Tickets touching `synthetic-monitor.yml` schedule disable/restore |

### New labels (proposed — minimum set)

| New label | Purpose | Rationale for new (vs. reusing) |
|-----------|---------|----------------------------------|
| `epic/masterkey-rename` | The umbrella epic family — every refactor ticket carries this | Follows existing `epic/supabase-migration` naming convention. Single tag for filtering ALL refactor work. |
| `phase/0` … `phase/5` | One label per architect-defined phase | Plan §3 is phased; phase labels let the operator gate sprint planning ("show me phase 3 work only"). No existing phase vocabulary in repo. |
| `type:infra` | Tickets that touch Cloud Run, AR, WIF, GCP IAM | `area/ops` is too broad — it includes CI/CD AND infra AND scripts AND observability. Splitting `type:infra` lets reviewers route to DevOps reviewer agent specifically. |
| `type:code` | Tickets touching `app/`, `tests/` | Distinguishes Phase 1 codebase changes from infra. |
| `type:ci-cd` | Tickets editing `.github/workflows/*` | Distinguishes CI changes from runtime infra (different failure modes, different reviewer). |
| `type:docs` | Tickets editing only `docs/*` or `CLAUDE.md` | Lower-risk subset of `documentation`; lets us batch doc tickets across phases. |
| `type:framework` | Tickets touching `.claude/`, `.gembaflow-overrides`, `scripts/template-sync.sh` | Risk of fighting `template-sync.sh`; reviewer must confirm `.gembaflow-overrides` is updated in lockstep. |
| `type:migration` | Tickets that perform a destructive or sticky state migration (repo rename, board migration, var flip, secret rotation) | Highest-blast-radius subset; flagged for pre-flight checklist enforcement. |
| `risk:destructive` | Tickets whose action is non-idempotent and partial-failure-prone (Cloud Run service delete, AR repo delete, repo rename) | Gates merge — requires explicit human approval, not bot review. |
| `verifies:G` | Tickets whose acceptance includes running verification section G (preview-deploy) | Per task brief: explicit linkage to verification harness section IDs. |

### "Blocked-by" convention

We use **issue body convention**, not a label, to express ticket dependencies. Each ticket's body includes:

```
## Dependencies
- Blocks: #<id>
- Blocked by: #<id>
```

Rationale: GitHub renders these as cross-links in the issue UI and they show up in the project board's relationship graph. A `blocked` label would be redundant and would require manual upkeep as upstream tickets close — the body links auto-update.

### Why this set is "reasonable"

Three principles:

1. **Reuse first.** Eight of the existing labels carry forward verbatim. The repo already has `epic`, priority labels, area labels, and ad-hoc tags (`audit`, `safety`, `synthetic-monitor`) that map directly to refactor needs.
2. **Three orthogonal axes only.** `phase/N` (when), `type:X` (what surface), `risk:destructive` + `verifies:G` (operational gates). No combinatorial proliferation — the operator filters along one axis at a time.
3. **One new naming convention extended, not invented.** `epic/masterkey-rename` mirrors the existing `epic/supabase-migration`. `phase/N` is the only entirely new prefix; six labels in that family is acceptable.

Total new labels: 11. Total label scheme size: 20. This is well below the threshold where label noise starts to overwhelm the picker UI (~30+).

---

## Epics

Six epics, one per phase of the architect's plan (`01-architecture-plan.md` §3). Numbering follows the plan phases (Phase 0 = Epic 1, Phase 1 = Epic 2, etc.) so a reader can cross-reference. Each epic ends at a specific rollback point (RB-N) — closing the epic is the implicit "RB-N rollback no longer reachable" gate.

---

### Epic 1 — Phase 0: Discovery & Pre-flight (read-only)

**Title:** `epic: Phase 0 — Pre-flight discovery & state snapshots`

**Description:**
Read-only inventory and snapshot work that must precede any code or infra change. Captures the pre-rename state of the Cloud Run service, the deployer SA's IAM policy, the secrets list, the WIF binding shape, Cloud Logging assets, open PRs, and external forks. Produces the snapshot artifacts that are the sole rollback path past Phase 5 (RB-5).

This is the lowest-risk epic but the most foundational — no ticket from later epics can start until the snapshots are captured and the open-PR check is green. The architect's Phase 0 explicitly notes "RB-0: Trivial — nothing changed."

**Acceptance criteria:**
- All four snapshot YAML files exist under `snapshots/` and are committed to the repo (per plan §3 Phase 0 step 2 / S2).
- WIF binding verified to match `provision-gcp-project.sh:437-474` shape (both `workloadIdentityUser` AND `serviceAccountTokenCreator` on `cubrox/cubrox` principalSet).
- Cloud Logging metric / alert / dashboard inventory captured (expected empty per ADR-004).
- Zero open PRs confirmed via `gh pr list --state open`.
- External forks enumerated; if any, owners notified.
- Verification harness section A passes (A1-A5).

**Labels:** `epic`, `epic/masterkey-rename`, `phase/0`, `type:infra`, `audit`, `safety`, `P1`

**Tickets:** E1-T1, E1-T2, E1-T3, E1-T4, E1-T5

**Rollback point that closes the epic:** RB-0 (nothing changed; rollback is no-op)

---

### Epic 2 — Phase 1: Code-level rename PR

**Title:** `epic: Phase 1 — Codebase rename PR (cubrox → masterkey identifiers)`

**Description:**
The single feature-branch PR that lands every in-repo identifier change: `app/main.py` title, `CUBROX_TEST_SEED_ENABLED` env-var rename across code/tests/ci.yml, `window.cubroxLineCount` browser global, `supabase/config.toml` local project_id, the two `.gembaflow-overrides`-listed scripts (`provision-gcp-project.sh`, `diagnose-cloudrun.sh`), agent persona files in `.gembaflow-overrides`, `.claude/PROJECT.md` Supabase stale-context fix, doc updates, synthetic-monitor schedule disable.

Critical property: the PR's preview deploy goes to the OLD `agile-flow-app` Cloud Run service (because `vars.CLOUD_RUN_SERVICE` is unflipped). A green preview here is the live no-op proof that the code rename does not change runtime behavior. This makes Phase 1's PR-merge in Phase 4 step 27 the second checkpoint where the rename is observed to be functionally inert — first against `agile-flow-app`, then re-deployed against `masterkey` after var flip.

**Acceptance criteria:**
- All §2.2 code/test/template renames applied (one PR, single commit-set OK).
- `ci.yml` lines 218/307/315 edited (B1 fix — `CUBROX_TEST_SEED_ENABLED` → `MASTERKEY_TEST_SEED_ENABLED`).
- `scripts/provision-gcp-project.sh:800,1011` + `scripts/diagnose-cloudrun.sh:35` + line 23 comment edited (B4).
- `.claude/PROJECT.md` Supabase fix folded in (S5).
- `synthetic-monitor.yml` schedule disabled with PR-body TODO for restore (per Q9).
- Local test suite green: `uv run pytest`, `ruff check`, `ruff format --check`, `mypy app/`, `tests/a11y` against local `supabase start`.
- PR opened; preview deploy lands on `agile-flow-app` and `/api/health` returns 200.
- Verification harness sections B, J, H pass (B1-B7, J1-J4, H1-H2).

**Labels:** `epic`, `epic/masterkey-rename`, `phase/1`, `type:code`, `type:ci-cd`, `type:docs`, `type:framework`, `P1`

**Tickets:** E2-T1, E2-T2, E2-T3, E2-T4, E2-T5, E2-T6, E2-T7, E2-T8

**Rollback point that closes the epic:** RB-1 (close PR; no production impact)

---

### Epic 3 — Phase 2: GitHub repo rename, board migration, WIF dual-write

**Title:** `epic: Phase 2 — Repo rename, project board migration, WIF dual-write`

**Description:**
The four highest-blast-radius operations in the whole refactor, ordered so WIF authentication never breaks. The WIF binding for `cubrox/masterkey` is dual-written on the deployer SA's IAM policy BEFORE the `gh repo rename` fires, so no GCP-touching workflow ever sees an unauthorized request. The repo rename itself triggers cascade-updates to local remotes on every developer machine, branch-protection ruleset re-validation, and Supabase GitHub App allowlist re-verification.

The project-board migration is full-history: ALL items (open + closed) from `vibeacademy/projects/29` (67 items per pre-flight inventory) move to the new cubrox-user board.

**Acceptance criteria:**
- New WIF binding present on deployer SA for `cubrox/masterkey` with BOTH `workloadIdentityUser` AND `serviceAccountTokenCreator` (E1, E2 PASS in verification harness).
- Old binding still present (E3 informational PASS — kept for grace window).
- `gh repo rename masterkey` executed; `gh repo view cubrox/masterkey` returns 200.
- Local `git remote -v` on operator's machine shows `cubrox/masterkey` (C2 PASS).
- Branch protection ruleset id 15886599 still applies post-rename (C4 PASS, per S3).
- Supabase GitHub App allowlist confirmed to still include `cubrox/masterkey` (R10 mitigation).
- New project board exists at `github.com/users/cubrox/projects/<n>` (note: `users/`, not `orgs/` per pre-loading finding).
- All 67 items migrated; legacy `vibeacademy/projects/29` closed (NOT deleted) with a description pointing to the new board.

**Labels:** `epic`, `epic/masterkey-rename`, `phase/2`, `type:infra`, `type:migration`, `risk:destructive`, `safety`, `P0`

**Tickets:** E3-T1, E3-T2, E3-T3, E3-T4

**Rollback point that closes the epic:** RB-2 (repo rename reversible via `gh repo rename cubrox`; WIF dual-write removable via `remove-iam-policy-binding`; legacy board still in place as fallback)

---

### Epic 4 — Phase 3: Cloud Run + Artifact Registry preparation (no traffic yet)

**Title:** `epic: Phase 3 — Pre-create masterkey infra and dry-run preview deploys`

**Description:**
Pre-creates the `masterkey` Artifact Registry repo and the `masterkey` Cloud Run service with a placeholder revision, mounting the same secrets as `agile-flow-app` but matching `deploy.yml`'s env-var TYPES exactly (`--set-env-vars` for `DATABASE_URL` + `ANTHROPIC_API_KEY`; `--set-secrets` for the three Supabase keys). This is where R13 (env-var type stickiness) is permanently locked in — getting it wrong here bricks the service for the rest of the refactor.

Captures the new service URL, pins it into `docs/LAUNCH-CHECKLIST.md` line 10 and `CLAUDE.md` (B5 + S6). Runs the explicit dry-run PR (with a smoke `supabase/migrations/*.sql` empty file per R10) to exercise preview-deploy + preview-cleanup + Supabase branching against the new service. Adds both production and preview Supabase Auth redirect patterns (R4 + R12).

**Acceptance criteria:**
- `masterkey` AR repo exists in `us-central1` (F4 PASS).
- `masterkey` Cloud Run service exists; `/api/health` returns 200; `/api/health/db` returns 200 (F1, F2, F3 PASS).
- `--set-env-vars` used for `DATABASE_URL` + `ANTHROPIC_API_KEY` (R13 guard — verified by inspecting `gcloud run services describe`).
- New service URL captured and committed into `docs/LAUNCH-CHECKLIST.md` line 10 (and §2.C/D lines 45-46, 51 updated) + `CLAUDE.md` Project Information block.
- Supabase Auth allowlist contains both `https://masterkey-<hash>-uc.a.run.app/auth/callback` AND `https://pr-*---masterkey-*-uc.a.run.app/auth/callback` (manual dashboard verify per runbook §5.4; I4 will SKIP).
- Dry-run PR labelled `phase3-dryrun` opens, preview deploys to `masterkey` service, preview-cleanup runs on PR-close, Supabase branch created from smoke migration file. Verification section G with `--exercise-preview-deploy` flag PASSes (G1-G6).
- `vars.CLOUD_RUN_SERVICE` returned to `agile-flow-app` after dry-run (Phase 4 step 27 requires old var still in effect at Phase 1 PR merge time).

**Labels:** `epic`, `epic/masterkey-rename`, `phase/3`, `type:infra`, `type:migration`, `verifies:G`, `P0`

**Tickets:** E4-T1, E4-T2, E4-T3, E4-T4, E4-T5, E4-T6

**Rollback point that closes the epic:** RB-3 (delete `masterkey` service + AR repo; revert dry-run var flip; no prod impact)

---

### Epic 5 — Phase 4: Cutover (re-sequenced per B7)

**Title:** `epic: Phase 4 — Cutover (merge code PR, flip vars, deploy to masterkey)`

**Description:**
The destructive cutover, re-sequenced per B7 to eliminate the var-flip-before-merge race window. The ordering ships exactly one risk per step: merge Phase 1 PR with old vars (deploys rename code to `agile-flow-app` as live no-op proof) → verify old service health → flip `vars.CLOUD_RUN_SERVICE` + `vars.ARTIFACT_REPO` → push trivial commit to trigger `deploy.yml` against `masterkey` → verify new service health → re-enable synthetic monitor.

This is the epic with the lowest tolerance for sequencing mistakes; every ticket below carries `risk:destructive` and requires the prior ticket to be PASS-verified before proceeding.

**Acceptance criteria:**
- Phase 1 PR merged with `vars.CLOUD_RUN_SERVICE` still `agile-flow-app`. `deploy.yml` runs green; `agile-flow-app` `/api/health` returns 200 post-merge.
- `gh variable set CLOUD_RUN_SERVICE --body masterkey` and `gh variable set ARTIFACT_REPO --body masterkey` executed; values verified via `gh variable list` (D1, D2 PASS).
- Trivial commit (`CHANGELOG.md` entry per §2.6) pushed to `main`; `deploy.yml` builds `masterkey/masterkey:<sha>` and deploys to `masterkey` service.
- `masterkey` service `/api/health`, `/api/health/db`, `/` all return 200 (F1-F3 PASS).
- `scripts/smoke_auth.py` against `$NEW_URL` round-trips a Supabase magic link end-to-end.
- Synthetic monitor `schedule:` block restored via follow-up PR; next :17-past-hour run hits `masterkey`-resolved URL (self-heals per Q9).
- Verification harness full run: all sections PASS except E3 + F5 informational, I4 SKIP.

**Labels:** `epic`, `epic/masterkey-rename`, `phase/4`, `type:infra`, `type:migration`, `risk:destructive`, `verifies:G`, `synthetic-monitor`, `P0`

**Tickets:** E5-T1, E5-T2, E5-T3, E5-T4, E5-T5, E5-T6, E5-T7

**Rollback point that closes the epic:** RB-4 (re-flip vars + trivial commit; old service was never deleted — clean revert)

---

### Epic 6 — Phase 5: Cleanup & follow-ups (30 days post-cutover)

**Title:** `epic: Phase 5 — Cleanup (delete old service, prune WIF, memory MCP audit)`

**Description:**
30-day-delayed cleanup of the dual-state artifacts: old Cloud Run service `agile-flow-app`, old Artifact Registry repo `agile-flow`, old Supabase Auth allowlist entries (production + preview pattern), old WIF binding on `cubrox/cubrox`, Cloud Logging assets enumerated in Phase 0. Plus the deferred follow-ups flagged in the plan: Memory MCP entity audit/rename (R7), doc-link rot cleanup (R8), upstream-doc decision (R5 — whether to add `docs/PLATFORM-GUIDE.md` to `.gembaflow-overrides`).

The 30-day window is intentional (per resolved Q4): storage is rounding-error cost and the only way to roll back to a specific commit-SHA revision is to re-pull that image. Do NOT start this epic until Phase 4 has been stable for ≥ 30 days AND the rollback decision has been declined.

**Acceptance criteria:**
- Old Cloud Run service `agile-flow-app` deleted (F5 PASS — old service is gone).
- Old AR repo `agile-flow` deleted; image manifests archived first (per R2 mitigation).
- Old Supabase Auth allowlist entries (`https://agile-flow-app-*` production URL AND `https://pr-*---agile-flow-app-*` preview pattern) removed (R12 mitigation completion).
- Old WIF binding on `cubrox/cubrox` removed from deployer SA IAM policy (E3 flips to PASS).
- Cloud Logging metrics / dashboards / alerts updated to `resource.labels.service_name="masterkey"` (likely no-op per ADR-004; Phase 0 inventory drives the action list).
- Memory MCP entities renamed or aliased from "cubrox" → "masterkey" / "Master Key" (R7).
- ADR-007 "Rename to Master Key / masterkey" written and committed (per §2.6 decision to leave ADR-006 immutable).
- Decision logged on `docs/PLATFORM-GUIDE.md` + `docs/CI-CD-GUIDE.md`: add to `.gembaflow-overrides` and edit, or accept drift (R5).

**Labels:** `epic`, `epic/masterkey-rename`, `phase/5`, `type:infra`, `type:docs`, `risk:destructive`, `P2`

**Tickets:** E6-T1, E6-T2, E6-T3, E6-T4, E6-T5, E6-T6, E6-T7

**Rollback point that closes the epic:** RB-5 (past this point, rollback requires re-creating from Phase 0 snapshots)

---

## Tickets

Each ticket below conforms to the Agentic PRD Lite format (`docs/TICKET-FORMAT.md`). Format compressed for backlog density — when loaded into GitHub, each ticket should expand its Power Sections inline per the canonical template.

---

### Epic 1 — Phase 0 tickets

#### E1-T1 — `chore: Inventory legacy vibeacademy/projects/29 board items`

**Problem Statement:** The legacy project board has 67 items (open + closed) that must migrate to the new cubrox-user board with full parity. No export exists today; without inventory, migration completeness cannot be verified.

**Parent Epic:** E1 — Phase 0 Pre-flight
**Effort Estimate:** S
**Priority:** P1

**A. Environment Context**
- `gh api graphql` with `organization(login: "vibeacademy") { projectV2(number: 29) { items(first: 100) { ... } } }`
- Output destination: `snapshots/vibeacademy-project-29-items.json` (new file)
- 67 items confirmed by pre-flight; query paginates if total > 100

**B. Guardrails**
- Read-only; do NOT use any GraphQL mutation in this ticket.
- Do NOT include item field values that may contain PII (assignee emails) — `gh api` shouldn't return them anyway, but verify.

**C. Happy Path**
1. Run paginated `gh api graphql` query against project 29.
2. Capture: item ID, type (Issue/PR/DraftIssue), title, status field, URL, closed flag.
3. Write to `snapshots/vibeacademy-project-29-items.json`.
4. Commit + push to feature branch (will land in E1-T5's PR).

**D. Definition of Done**
- `snapshots/vibeacademy-project-29-items.json` exists in repo.
- `jq '. | length' snapshots/vibeacademy-project-29-items.json` returns 67 (or current totalCount).
- File committed in a PR alongside E1-T2-T5 snapshots.

**Dependencies:** None (epic starter)
**Plan reference:** §3 Phase 0 step 1
**Verification check:** Feeds E3-T2 (board migration count-parity check)

---

#### E1-T2 — `chore: Snapshot Cloud Run service + revisions + SA IAM + secrets`

**Problem Statement:** Phase 0 step 2 (S2) requires four snapshot artifacts as the sole rollback path past Phase 5 (RB-5). Without these, any post-cutover incident has no clean way to recreate the pre-rename service shape.

**Parent Epic:** E1
**Effort Estimate:** S
**Priority:** P1

**A. Environment Context**
- `gcloud` authed against `$GCP_PROJECT_ID`
- Outputs go to `snapshots/`: `agile-flow-app.pre-rename.yaml`, `revisions.pre-rename.yaml`, `sa-iam.pre-rename.yaml`, `secrets.pre-rename.yaml`
- `$SA_EMAIL` read from `gcp-deployer-sa-email` secret or `GCP_SERVICE_ACCOUNT` env var

**B. Guardrails**
- Read-only `gcloud ... describe` / `... list` only. No `update`, `delete`, `apply`.
- Do NOT commit secret VALUES — `gcloud secrets list` returns names only; do NOT pipe through `gcloud secrets versions access`.

**C. Happy Path**
1. `gcloud run services describe agile-flow-app --region=us-central1 --format=yaml > snapshots/agile-flow-app.pre-rename.yaml`
2. `gcloud run revisions list --service=agile-flow-app --region=us-central1 --format=yaml > snapshots/revisions.pre-rename.yaml`
3. `gcloud iam service-accounts get-iam-policy $SA_EMAIL --format=yaml > snapshots/sa-iam.pre-rename.yaml`
4. `gcloud secrets list --project=$GCP_PROJECT_ID --format=yaml > snapshots/secrets.pre-rename.yaml`
5. Commit (via E1-T5's snapshot-bundle PR).

**D. Definition of Done**
- All four files exist under `snapshots/` and are non-empty.
- `grep -E "secretData|payload" snapshots/secrets.pre-rename.yaml` returns 0 matches (guard against accidental secret VALUE inclusion).
- Verification harness A4-A5 PASS when run with `--section A`.

**Dependencies:** None
**Plan reference:** §3 Phase 0 step 2 (B-class S2)
**Verification check:** Verified by A4, A5; also unlocks RB-2 through RB-5 (any rollback needs these)

---

#### E1-T3 — `chore: Verify WIF binding shape against provisioning script`

**Problem Statement:** R3 is the highest-likelihood "stuck in middle" failure mode. The plan's mitigation depends on the WIF binding actually matching the shape `provision-gcp-project.sh:437-474` provisioned (both roles, principalSet repository-pin). If reality differs from the assumption, Phase 2 step 16's dual-write would fail to actually grant the new repo authentication.

**Parent Epic:** E1
**Effort Estimate:** XS
**Priority:** P1

**A. Environment Context**
- `gcloud` authed; `jq` installed
- Deployer SA email: `gcloud secrets versions access latest --secret=gcp-deployer-sa-email --project=$GCP_PROJECT_ID` (fallback: read `GCP_SERVICE_ACCOUNT` secret)
- WIF provider: `gcloud iam workload-identity-pools providers describe github --location=global --workload-identity-pool=github --format=value(attributeCondition)`

**B. Guardrails**
- Read-only. Do NOT add or remove any IAM binding in this ticket.
- Do NOT proceed to E3-T1 if either role is missing from the existing principalSet — escalate (the rename cannot safely start).

**C. Happy Path**
1. Read SA email per A above.
2. `gcloud iam service-accounts get-iam-policy $SA_EMAIL --project=$GCP_PROJECT_ID --format=json | jq '.bindings[] | select(.role | IN("roles/iam.workloadIdentityUser","roles/iam.serviceAccountTokenCreator"))'`
3. Confirm output contains `principalSet://.../attribute.repository/cubrox/cubrox` for BOTH roles.
4. Confirm provider's `attributeCondition` is `assertion.repository != ''`.
5. Record findings in ticket comment.

**D. Definition of Done**
- Comment on ticket records the exact `principalSet` URI and confirms both roles bound.
- Provider attribute condition recorded.
- If either expectation fails: ticket blocks E3-T1; escalate via P0 issue.

**Dependencies:** None
**Plan reference:** §3 Phase 0 step 3 (B-class B2 verification)
**Verification check:** Pre-condition for E1, E2 to be meaningful in Phase 2

---

#### E1-T4 — `chore: Enumerate Cloud Logging metrics, alerts, dashboards`

**Problem Statement:** Resolved Q7 expects this enumeration to return empty (per ADR-004 — Sentry deferred, no custom dashboards), but alerts that don't fire after the rename look like silence. Without the inventory, Phase 5 step 39's "update saved queries" has no action list.

**Parent Epic:** E1
**Effort Estimate:** XS
**Priority:** P1

**A. Environment Context**
- `gcloud` authed against `$GCP_PROJECT_ID`
- Outputs: `snapshots/logging-assets.pre-rename.txt`

**B. Guardrails**
- Read-only. Do NOT delete/edit any logging asset in this ticket.

**C. Happy Path**
1. `gcloud logging metrics list --project=$GCP_PROJECT_ID`
2. `gcloud alpha monitoring policies list --project=$GCP_PROJECT_ID --format='value(displayName,combiner)'`
3. `gcloud monitoring dashboards list --project=$GCP_PROJECT_ID --format='value(displayName)'`
4. Concatenate outputs into `snapshots/logging-assets.pre-rename.txt` with section headers.
5. Commit.

**D. Definition of Done**
- `snapshots/logging-assets.pre-rename.txt` exists.
- If non-empty: each entry is queued as a sub-task on E6-T5.
- If empty: ticket comment records "no Cloud Logging assets reference service_name; Phase 5 step 39 is a no-op."

**Dependencies:** None
**Plan reference:** §3 Phase 0 step 4 (resolved Q7)
**Verification check:** Feeds E6-T5 action list

---

#### E1-T5 — `chore: Confirm zero open PRs + enumerate forks, then bundle Phase 0 snapshots into PR`

**Problem Statement:** Phase 4's preview-deploy hazard window requires zero in-flight PRs at cutover time. External forks (R15) need their owners notified before the 30-day GitHub redirect lapses. This ticket also bundles E1-T1 through E1-T4 outputs into a single PR for review.

**Parent Epic:** E1
**Effort Estimate:** S
**Priority:** P1

**A. Environment Context**
- `gh` authed
- Branch: `feature/refactor-phase0-snapshots`
- Files added: `snapshots/*.yaml`, `snapshots/*.json`, `snapshots/*.txt` from E1-T1-T4
- New file: `snapshots/forks.pre-rename.txt`

**B. Guardrails**
- Do NOT close any in-flight PR found — escalate to its author for rebase plan.
- Do NOT contact fork owners directly via GitHub mention in this ticket; only record their handles for human follow-up.

**C. Happy Path**
1. `gh pr list --state open --repo cubrox/cubrox` — expect `[]`.
2. `gh api repos/cubrox/cubrox/forks --jq '.[].full_name' > snapshots/forks.pre-rename.txt`
3. Commit all snapshot artifacts from E1-T1 through E1-T4 + the fork list.
4. Open PR titled "Phase 0 snapshots — pre-rename baseline".
5. PR body lists rollback-recovery procedures referencing each snapshot file.

**D. Definition of Done**
- PR opened with all snapshot artifacts.
- Snapshot files reviewed for accidental secret leakage (no `secretData`, no `payload`).
- If forks list is non-empty: ticket comment lists owner handles; human owner contacts them.
- PR merges to `main` (this is the only Phase 0 merge — pre-rename baseline).
- Verification harness section A PASSes with `--section A` after merge.

**Dependencies:** Blocked by: E1-T1, E1-T2, E1-T3, E1-T4
**Plan reference:** §3 Phase 0 steps 5, 6
**Verification check:** Verified by A1-A5

---

### Epic 2 — Phase 1 tickets

All Epic 2 tickets land on a single branch `feature/refactor-cubrox-to-masterkey` and merge as a single PR (per plan Phase 1 step 7). Tickets are decomposed for parallel sub-task tracking; commits may be grouped.

---

#### E2-T1 — `refactor: Rename CUBROX_TEST_SEED_ENABLED env var across code, tests, ci.yml`

**Problem Statement:** The env-var name appears in app code, test code, two test config files, and three lines of `ci.yml` (B1 — inlined literal, not a `vars.*` indirection). Renaming in lock-step is required; missing any one site causes the test-seed router to silently not mount.

**Parent Epic:** E2
**Effort Estimate:** S
**Priority:** P1

**A. Environment Context**
- Stack: FastAPI + Python 3.12 + Playwright (see `docs/TECHNICAL-ARCHITECTURE.md`)
- Files to modify:
  - `app/main.py:59-64`
  - `app/api/test_seed.py:32,41,66,71`
  - `tests/test_test_seed_guard.py:25,42,53,56`
  - `tests/test_seed_route.py:5` (docstring)
  - `tests/a11y/playwright.config.ts:65`
  - `tests/a11y/fixtures/seed.ts:16` (docstring)
  - `tests/a11y/README.md:1,16,38,40,74`
  - **`.github/workflows/ci.yml:218,307,315`** (B1 — critical)

**B. Guardrails**
- One-shot ripgrep + sed pass, then audit ALL hits.
- Do NOT touch `docs/AGENTIC-CONTROLS.md` (mentions env var as example).
- Do NOT skip `ci.yml` — `vars.*` flip cannot reach it.

**C. Happy Path**
1. `rg -l 'CUBROX_TEST_SEED_ENABLED' .` — list all hits.
2. For each hit: replace with `MASTERKEY_TEST_SEED_ENABLED`.
3. Re-run `rg 'CUBROX_TEST_SEED_ENABLED' .` — must return 0 matches.
4. Run `uv run pytest tests/test_test_seed_guard.py` — must pass.
5. Run a11y locally: `cd tests/a11y && npx playwright test` against `supabase start` + `uv run uvicorn`.

**D. Definition of Done**
- `rg 'CUBROX_TEST_SEED_ENABLED' .` returns 0 matches.
- `rg 'MASTERKEY_TEST_SEED_ENABLED' .` returns ≥ 8 matches (counts above).
- `uv run pytest tests/test_test_seed_guard.py` passes.
- Local a11y suite passes.
- Verification harness B3, B4 PASS.

**Dependencies:** None within E2 (E2 tickets all on same branch — sequencing is logical, not enforced)
**Plan reference:** §2.2 + §2.4 row 1 + Phase 1 step 8 (B1)
**Verification check:** Verified by B3, B4, D3

---

#### E2-T2 — `refactor: Rename window.cubroxLineCount → window.masterkeyLineCount`

**Problem Statement:** A browser global appears in templates and tests. Must move in lockstep — test pins the global name, so any mismatch fails the test immediately.

**Parent Epic:** E2
**Effort Estimate:** XS
**Priority:** P1

**A. Environment Context**
- Files to modify:
  - `templates/pages/reading.html:49,60,73,79`
  - `tests/test_passage_close.py:221,228,234`

**B. Guardrails**
- Both files must be edited in the same commit (or both staged before push) — bisecting halfway leaves test broken.
- Do NOT introduce a backwards-compat alias; the rename is hard.

**C. Happy Path**
1. Edit both files; replace `cubroxLineCount` → `masterkeyLineCount`.
2. `rg 'cubroxLineCount' .` — 0 matches.
3. `uv run pytest tests/test_passage_close.py` passes.

**D. Definition of Done**
- `rg 'cubroxLineCount' .` returns 0.
- `rg 'masterkeyLineCount' .` returns 7 matches (4 template + 3 test).
- `uv run pytest tests/test_passage_close.py` passes.
- Verification harness B7 PASS.

**Dependencies:** None
**Plan reference:** §2.2 rows for `reading.html` and `test_passage_close.py`
**Verification check:** Verified by B7

---

#### E2-T3 — `refactor: Rename app metadata strings (FastAPI title, metric prog name, docstrings)`

**Problem Statement:** Cosmetic-but-coherent string renames in `app/main.py`, `app/scripts/metric.py`, `app/api/home.py`, `app/services/ingestion/pdf.py`. These surface in `/docs` OpenAPI, CLI `--help`, and code comments.

**Parent Epic:** E2
**Effort Estimate:** XS
**Priority:** P1

**A. Environment Context**
- Files: `app/main.py:19`, `app/scripts/metric.py:30`, `app/api/home.py:5`, `app/services/ingestion/pdf.py:5`, `tests/test_home.py:97`

**B. Guardrails**
- Do NOT change the public brand "Master Key" anywhere — it's already correct in templates.
- `app/main.py:19` title becomes `"Master Key"` (matches public brand), not `"masterkey"`.

**C. Happy Path**
1. Apply edits per §2.2 table.
2. `uv run pytest tests/test_home.py` passes (test contains an assertion about the docstring intent).

**D. Definition of Done**
- `curl localhost:8080/docs` (after `uv run uvicorn`) shows title "Master Key".
- `uv run python -m app.scripts.metric --help` shows `prog="masterkey-metric"`.
- `uv run pytest tests/test_home.py` passes.

**Dependencies:** None
**Plan reference:** §2.2 rows for `app/main.py`, `app/api/home.py`, `app/services/ingestion/pdf.py`, `app/scripts/metric.py`, `tests/test_home.py`
**Verification check:** No direct harness check; covered by B1 generic scan

---

#### E2-T4 — `refactor: Rename tests/a11y package and update fixture URLs`

**Problem Statement:** Local-only npm package + a fixture URL. Package rename touches `package.json` + `package-lock.json` (regenerated by `npm install`). Fixture URLs in `tests/test_auth_login.py` are coherence-only (R11) — not testing the new name.

**Parent Epic:** E2
**Effort Estimate:** XS
**Priority:** P1

**A. Environment Context**
- Files: `tests/a11y/package.json:2`, `tests/a11y/package-lock.json:2,7` (regenerate), `tests/test_auth_login.py:73,78`

**B. Guardrails**
- Do NOT publish the renamed package anywhere — it's local-only.
- `tests/test_auth_login.py` rename is COSMETIC per R11; do NOT add a semantic assertion about the new name.

**C. Happy Path**
1. Edit `tests/a11y/package.json` `"name": "masterkey-a11y-tests"`.
2. `cd tests/a11y && rm package-lock.json && npm install` to regenerate lock file.
3. Edit `tests/test_auth_login.py:73,78` URL strings.
4. Run `uv run pytest tests/test_auth_login.py` — passes.

**D. Definition of Done**
- `tests/a11y/package.json` `"name"` is `"masterkey-a11y-tests"`.
- `tests/a11y/package-lock.json` regenerated.
- `uv run pytest tests/test_auth_login.py` passes.

**Dependencies:** None
**Plan reference:** §2.2 rows for `tests/a11y/package.json`, `tests/a11y/package-lock.json`, `tests/test_auth_login.py` + R11
**Verification check:** Covered by B1 generic scan

---

#### E2-T5 — `refactor: Rename scripts/provision-gcp-project.sh and scripts/diagnose-cloudrun.sh defaults`

**Problem Statement:** Both scripts hardcode `agile-flow-app` as a default `CLOUD_RUN_SERVICE`. New workshop operators following them would create a service named `agile-flow-app` that doesn't match `vars.CLOUD_RUN_SERVICE=masterkey`, orphaning the first deploy (B4). Both files are in `.gembaflow-overrides` so editing does not fight `template-sync.sh`.

**Parent Epic:** E2
**Effort Estimate:** XS
**Priority:** P1

**A. Environment Context**
- Files: `scripts/provision-gcp-project.sh:800,1011`, `scripts/diagnose-cloudrun.sh:35` + line 23 comment
- Both files listed in `.gembaflow-overrides` (verified)

**B. Guardrails**
- Do NOT remove either file from `.gembaflow-overrides` — that would re-expose them to `template-sync.sh` revert.
- Do NOT edit OTHER scripts in `scripts/*.sh` (those are upstream framework — out of scope per §6).

**C. Happy Path**
1. `provision-gcp-project.sh:800` — change `SERVICE_NAME="${CLOUD_RUN_SERVICE:-agile-flow-app}"` to `:-masterkey`.
2. `provision-gcp-project.sh:1011` — change echo "next-steps" string to `masterkey`.
3. `diagnose-cloudrun.sh:35` — change `SERVICE="${CLOUD_RUN_SERVICE:-agile-flow-app}"` to `:-masterkey`. Update comment at line 23.
4. `rg 'agile-flow-app' scripts/{provision-gcp-project,diagnose-cloudrun}.sh` returns 0 matches.

**D. Definition of Done**
- `rg 'agile-flow-app' scripts/provision-gcp-project.sh scripts/diagnose-cloudrun.sh` returns 0.
- Both files still appear in `.gembaflow-overrides`.
- Verification harness B2 PASS (generic agile-flow-app scan, with these two files no longer offenders).

**Dependencies:** None
**Plan reference:** §2.5 + Phase 1 step 9 (B4)
**Verification check:** Verified by B2

---

#### E2-T6 — `docs: Update supabase/config.toml project_id and CLAUDE.md project information block`

**Problem Statement:** `supabase/config.toml:9` `project_id = "cubrox"` is the local Supabase CLI workspace identifier; must align with new name (B6 in supabase/config rename — local-only). `CLAUDE.md` Project Information block holds the project name, repo URL, project board URL, and docker build command — all stale post-rename. **NOTE:** Production Cloud Run URL is captured later in E4-T3; CLAUDE.md gets the URL inserted then via that ticket.

**Parent Epic:** E2
**Effort Estimate:** XS
**Priority:** P1

**A. Environment Context**
- Files: `supabase/config.toml:5,9`, `CLAUDE.md:164-166,175,195`
- Project board URL — for now, leave a TODO placeholder; E3-T3 fills it in once the new board exists.

**B. Guardrails**
- Do NOT change Supabase remote `project_id` (`gnswmcgaztcxslirulwm` — that's a different field, locked-scope per §6).
- Do NOT change `Organization:` to `cubrox` blindly — `cubrox` is a USER account, not an org. Suggest the line read `Owner: cubrox (user account)` for accuracy.

**C. Happy Path**
1. Edit `supabase/config.toml:9` `project_id = "masterkey"`; edit line 5 comment from `Org: vibeacademy` to `Org: cubrox`.
2. Edit `CLAUDE.md` Project Name, Repository URL, Project Board URL (placeholder for now), `docker build -t agile-flow-app .` → `docker build -t masterkey .`, Owner line.
3. `supabase start` still works (smoke).
4. `uv run pytest tests/test_home.py` still passes.

**D. Definition of Done**
- `grep '^project_id' supabase/config.toml` shows `"masterkey"`.
- `grep -A2 'Project Information' CLAUDE.md | grep 'Project Name'` shows `Master Key`.
- Verification harness B6 PASS, J4 PASS.

**Dependencies:** Blocks: E3-T3 (board URL placeholder must be filled in by board-migration ticket)
**Plan reference:** §2.6 + §2.8 + S5 + S6
**Verification check:** Verified by B6, J4

---

#### E2-T7 — `refactor: Apply .gembaflow-overrides agent persona renames and PROJECT.md Supabase fix`

**Problem Statement:** Agent persona files in `.gembaflow-overrides` reference the old project name or example service. `.claude/PROJECT.md` lines 7-9 incorrectly reference Neon (S5 — project is actually on Supabase). Folding this 5-line cosmetic into the Phase 1 PR removes ongoing agent confusion.

**Parent Epic:** E2
**Effort Estimate:** S
**Priority:** P1

**A. Environment Context**
- Files (all listed in `.gembaflow-overrides`):
  - `.claude/agents/github-ticket-worker.md:33` ("Product: Cubrox" → "Product: Master Key (codebase: masterkey)")
  - `.claude/agents/devops-engineer.md:72,307-324` (`agile-flow-app` examples → `masterkey`)
  - `.claude/PROJECT.md` lines 7-9 (Neon → Supabase, 5-line fix per S5)

**B. Guardrails**
- Edit ONLY files already in `.gembaflow-overrides`. Do NOT add framework files to overrides as a side effect.
- Do NOT touch `.claude/commands/eli5.md:18-19` — that's a `vibeacademy/cubrox` historical attribution (eli5 is from upstream agile-flow).
- Do NOT touch `.claude/agents/system-architect.md` unless `rg 'cubrox|agile-flow-app' .claude/agents/system-architect.md` finds non-historical hits.

**C. Happy Path**
1. Verify each target file is in `.gembaflow-overrides`: `grep -E '(github-ticket-worker|devops-engineer|PROJECT\.md)' .gembaflow-overrides`.
2. Apply edits per A.
3. Run `bash scripts/template-sync.sh --dry-run` (if available) to confirm no conflicts.

**D. Definition of Done**
- `rg 'Product: Cubrox' .claude/agents/` returns 0.
- `rg 'agile-flow-app' .claude/agents/devops-engineer.md` returns 0 (or only inside an explicit "historical example" code block).
- `rg 'Neon' .claude/PROJECT.md` returns 0.
- Verification harness J2, J3 PASS.

**Dependencies:** None
**Plan reference:** §2.7 + S5 + Phase 1 step 11
**Verification check:** Verified by J2, J3

---

#### E2-T8 — `chore: Disable synthetic monitor schedule for cutover window`

**Problem Statement:** Per resolved Q9, the synthetic monitor's hourly cron must be disabled cleanly during the cutover window — cron can fire up to 15 min late, and a fire mid-flip would trip on resolved old-service URL. Comment out the `schedule:` block on the Phase 1 branch; restore via small follow-up PR in Phase 4 (E5-T6).

**Parent Epic:** E2
**Effort Estimate:** XS
**Priority:** P1

**A. Environment Context**
- File: `.github/workflows/synthetic-monitor.yml` (likely lines near top of file — find the `on: schedule:` block)
- The workflow's `workflow_dispatch` trigger should remain — manual fires must still work during cutover for diagnostic purposes.

**B. Guardrails**
- Do NOT delete the `schedule:` block — comment it out so the restore in E5-T6 is a trivial uncommenting.
- Do NOT remove `workflow_dispatch` or the workflow itself.
- Add a PR-body TODO referencing E5-T6 as the restore ticket.

**C. Happy Path**
1. Open `.github/workflows/synthetic-monitor.yml`.
2. Comment out the `schedule:` block with a `# DISABLED for masterkey rename — restore in <PR for E5-T6>` marker.
3. Add a clear TODO comment with E5-T6 ID.
4. PR body of Phase 1 PR also lists this restore as a follow-up.

**D. Definition of Done**
- `grep -E '^\s*schedule:' .github/workflows/synthetic-monitor.yml` returns 0 (uncommented).
- `grep -E '^\s*#.*schedule:' .github/workflows/synthetic-monitor.yml` returns 1 (commented).
- `workflow_dispatch` still uncommented in the file.
- PR body lists E5-T6 as follow-up.

**Dependencies:** Blocks: E5-T6 (restore ticket)
**Plan reference:** §3 Phase 1 step 13 (resolved Q9)
**Verification check:** No direct harness check; verified implicitly by absence of stray monitor fires during cutover

---

### Epic 3 — Phase 2 tickets

**ORDER WITHIN EPIC IS LOAD-BEARING.** E3-T1 (WIF dual-write) MUST complete before E3-T2 (repo rename). E3-T3 + E3-T4 (board migration) can run after E3-T2.

---

#### E3-T1 — `infra: Dual-write WIF binding for cubrox/masterkey on deployer SA`

**Problem Statement:** R3 (highest-leverage "stuck in middle" failure mode) materializes the instant `gh repo rename` fires if the deployer SA's IAM policy doesn't already have a binding for the new repo path. Phase 2 step 16 dual-writes the new principalSet BEFORE the rename; both bindings exist simultaneously during the grace window.

**Parent Epic:** E3
**Effort Estimate:** S
**Priority:** P0

**A. Environment Context**
- `gcloud` authed against `$GCP_PROJECT_ID`
- Deployer SA email: `gcloud secrets versions access latest --secret=gcp-deployer-sa-email --project=$GCP_PROJECT_ID` (fallback: `GCP_SERVICE_ACCOUNT` secret)
- Project number: `gcloud projects describe $GCP_PROJECT_ID --format='value(projectNumber)'`
- Roles to bind: `roles/iam.workloadIdentityUser` AND `roles/iam.serviceAccountTokenCreator`
- New member: `principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github/attribute.repository/cubrox/masterkey`

**B. Guardrails**
- Do NOT remove the existing `cubrox/cubrox` binding in this ticket — that's E6-T4's job.
- Do NOT widen to org-level (`repository_owner == 'cubrox'`) — resolved Q5 declined this.
- Do NOT proceed to E3-T2 (repo rename) until verification dry-run (step below) passes.

**C. Happy Path**
1. Read `$SA_EMAIL`, `$PROJECT_NUMBER`.
2. For each role in (`roles/iam.workloadIdentityUser`, `roles/iam.serviceAccountTokenCreator`):
   - `gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" --role="$role" --member="$NEW_MEMBER" --project=$GCP_PROJECT_ID`
3. Verify: `gh workflow run rollback-production.yml -f revision=<currentRevision> -f reason='WIF binding verification' --repo cubrox/cubrox`. The workflow auths to GCP but only acts on user-confirmed input — auth-step pass = binding plumbed.
4. Watch the workflow run via `gh run watch`; first auth step must succeed.

**D. Definition of Done**
- `gcloud iam service-accounts get-iam-policy $SA_EMAIL --format=json | jq '.bindings[] | select(.members[] | contains("cubrox/masterkey"))'` returns BOTH role entries.
- `rollback-production.yml` dispatch run reaches the auth-success step.
- Verification harness E1, E2 PASS.

**Dependencies:** Blocked by: E1-T3 (WIF shape verification); blocks: E3-T2
**Plan reference:** §3 Phase 2 step 16 (B-class B2)
**Verification check:** Verified by E1, E2

---

#### E3-T2 — `infra: Rename GitHub repo cubrox/cubrox → cubrox/masterkey`

**Problem Statement:** THE highest-blast-radius single operation in the entire refactor. Triggers cascade-updates to: local remotes on every dev machine, branch-protection ruleset re-validation, Supabase GitHub App allowlist (R10), 30-day GitHub redirect (after which old URL 404s). Must NOT happen until E3-T1's WIF dual-write is confirmed, every Phase 1 sub-ticket has merged its commits to the feature branch, and the pre-flight checklist below is green.

**Parent Epic:** E3
**Effort Estimate:** S (the action is one command; the pre-flight is the work)
**Priority:** P0

**A. Environment Context**
- `gh` authed; current user has admin on `cubrox/cubrox`
- Local clone: `/Users/teddykim/projects/cubrox/cubrox` (or wherever; remote URL update follows)
- Branch protection ruleset id: `15886599` (per plan §2.1 row 7)
- Supabase GitHub App: org-level install, repo allowlist may track by `owner/name` or `repository.id` (R10)

**B. Guardrails**
- Do NOT run `gh repo rename` until ALL items in pre-flight checklist below are checked off.
- Do NOT delete the redirect by recreating a `cubrox/cubrox` placeholder repo — the 30-day GitHub redirect is the safety net for external links (R8).
- Do NOT proceed if any open PR exists (re-verify `gh pr list --state open` immediately before rename).

**Pre-flight checklist (MUST be 100% green before running `gh repo rename`):**
- [ ] E3-T1 verification dispatch run succeeded (WIF binding plumbed).
- [ ] E1-T5 PR merged (snapshots present in `main`).
- [ ] `gh pr list --state open --repo cubrox/cubrox` returns `[]`.
- [ ] `git remote -v` notification ready to send to every dev with a local clone.
- [ ] Supabase dashboard tab open at Project Settings → Integrations → GitHub (for immediate post-rename verification).
- [ ] Branch protection ruleset captured via `gh api repos/cubrox/cubrox/rulesets > /tmp/rulesets.pre-rename.json`.
- [ ] Forks list (E1-T5 output) re-checked; if any new forks since: notify owners.
- [ ] `vars.CLOUD_RUN_SERVICE` confirmed STILL `agile-flow-app` (no premature flip).
- [ ] Operator has terminal ready to run `git remote set-url origin git@github.com:cubrox/masterkey.git` immediately after rename.

**C. Happy Path**
1. Complete pre-flight checklist (above).
2. `gh repo rename masterkey --repo cubrox/cubrox` (or via GitHub UI).
3. Immediately: `git remote set-url origin git@github.com:cubrox/masterkey.git` on operator's machine.
4. Verify: `gh repo view cubrox/masterkey --json nameWithOwner` returns `cubrox/masterkey`.
5. Verify: `gh api repos/cubrox/masterkey/rulesets` returns the ruleset (id 15886599) (per S3).
6. Verify: Supabase dashboard → Integrations → GitHub still shows `cubrox/masterkey` (R10). If not: re-install Supabase GitHub App on new repo name.
7. Notify all devs with local clones to run `git remote set-url`.

**D. Definition of Done**
- `gh repo view cubrox/masterkey` returns HTTP 200.
- `gh repo view cubrox/cubrox` returns a 30-day-redirect to `cubrox/masterkey` (verification C3).
- Operator's local `git remote -v` shows `cubrox/masterkey`.
- Branch protection ruleset id 15886599 still applies (C4).
- Supabase GitHub App allowlist still contains the repo (manual dashboard check, recorded in ticket comment).
- Verification harness C1, C2, C3, C4 PASS.

**Dependencies:** Blocked by: E3-T1, E1-T5, ALL E2-Tx (Phase 1 PR opened); blocks: E3-T3, E3-T4, E4-T1
**Plan reference:** §3 Phase 2 step 17
**Verification check:** Verified by C1, C2, C3, C4; R10 manually verified (no harness check)

---

#### E3-T3 — `infra: Create new project board at github.com/users/cubrox/projects/<n>`

**Problem Statement:** Per locked scope, the project board moves from `vibeacademy/projects/29` to a new cubrox-owned board. Pre-loading finding: `cubrox` is a USER, not an org, so the new board URL is `users/cubrox/projects/<n>`, not `orgs/cubrox/`. Board must mirror columns + automation BEFORE item migration.

**Parent Epic:** E3
**Effort Estimate:** S
**Priority:** P0

**A. Environment Context**
- `gh project create --owner cubrox` (or via GitHub UI under user-account projects)
- Columns to mirror: Backlog / Ready / In Progress / In Review / Done (per `.claude/agents/agile-backlog-prioritizer.md`)
- Automation: status-move workflows (read existing automation on vibeacademy/projects/29 via UI before re-creating)

**B. Guardrails**
- Board lives on USER account `cubrox`, NOT an org (verified via `gh api graphql user(login:"cubrox")`).
- Do NOT migrate items yet — that's E3-T4. Empty new board is the deliverable here.
- Do NOT close vibeacademy/projects/29 — that's E3-T4's final step.

**C. Happy Path**
1. `gh project create --owner cubrox --title "Master Key"` (or equivalent UI).
2. Capture new project number `N` and URL `https://github.com/users/cubrox/projects/N`.
3. Create columns: Backlog, Ready, In Progress, In Review, Done.
4. Configure status-move automation (mirror legacy board's workflows by inspection).
5. Update `CLAUDE.md` Project Board URL placeholder (set in E2-T6) to the new URL.

**D. Definition of Done**
- New project resolvable: `gh api graphql user(login:"cubrox") projectV2(number:N)` returns 200.
- Board has 5 columns matching legacy.
- `CLAUDE.md` Project Board URL line updated to new URL (PR alongside or hot-fix).
- Verification harness no direct check; J4 (CLAUDE.md update) covers indirectly.

**Dependencies:** Blocked by: E3-T2 (repo rename); blocks: E3-T4
**Plan reference:** §3 Phase 2 step 18 + pre-loading finding #1
**Verification check:** Indirectly via J4 (CLAUDE.md update)

---

#### E3-T4 — `chore: Migrate all 67 items (open + closed) from vibeacademy/projects/29 to new board`

**Problem Statement:** Per locked-scope decision: ALL items (open AND closed) must migrate so the new board carries the full history. 67 items per E1-T1 inventory. Closed tickets count toward the historical record; omitting them loses audit trail.

**Parent Epic:** E3
**Effort Estimate:** M
**Priority:** P1

**A. Environment Context**
- Input: `snapshots/vibeacademy-project-29-items.json` (from E1-T1)
- API: `gh api graphql` with `addProjectV2ItemById(input: {projectId, contentId})` for each issue/PR ID
- DraftIssue items: need `addProjectV2DraftIssue` instead
- Field values (status, priority, etc.): re-set after add via `updateProjectV2ItemFieldValue`

**B. Guardrails**
- Do NOT delete vibeacademy/projects/29 — only close it (`updateProjectV2 input:{closed:true}`).
- Do NOT lose status/field data — capture field values from source, re-apply to destination.
- Migrate in batches of ~10 with sleep to avoid rate-limit.

**C. Happy Path**
1. Parse `snapshots/vibeacademy-project-29-items.json` for items + their field values.
2. For each item: `gh api graphql -f query='mutation { addProjectV2ItemById(input: {projectId: $newId, contentId: $itemId}) { item { id } } }'`.
3. For each new item ID: re-apply field values via `updateProjectV2ItemFieldValue`.
4. Verify item count parity: `gh api graphql user(login:"cubrox") projectV2(number:N) { items { totalCount } }` returns 67 (or whatever the source totalCount is at migration time).
5. Close legacy board: edit description to "MIGRATED to https://github.com/users/cubrox/projects/N — archived for audit."; mark closed.

**D. Definition of Done**
- Item count on new board equals source `totalCount` (recorded in ticket comment).
- Spot-check: 3 open + 3 closed items from legacy appear on new board with correct status field.
- Legacy `vibeacademy/projects/29` `closed = true`; description updated.
- Verification: manual — no harness check (board state outside script's purview).

**Dependencies:** Blocked by: E3-T3, E1-T1
**Plan reference:** §3 Phase 2 steps 18, 19
**Verification check:** Manual count check; no harness ID

---

### Epic 4 — Phase 3 tickets

#### E4-T1 — `infra: Create masterkey Artifact Registry repo + grant runtime SA reader`

**Problem Statement:** New AR repo `masterkey` in `us-central1` needed before `masterkey` service can pull images. Plan §3 Phase 3 steps 20-21.

**Parent Epic:** E4
**Effort Estimate:** XS
**Priority:** P1

**A. Environment Context**
- `gcloud` authed; `$GCP_PROJECT_ID`, region `us-central1`
- Runtime SA: same as current (read from existing Cloud Run service spec)

**B. Guardrails**
- Do NOT delete or modify old `agile-flow` AR repo — both coexist through Phase 5.
- Verify `roles/artifactregistry.reader` granted (usually inherited from project-level — confirm, don't assume).

**C. Happy Path**
1. `gcloud artifacts repositories create masterkey --repository-format=docker --location=us-central1 --project=$GCP_PROJECT_ID`
2. Verify reader binding: `gcloud artifacts repositories get-iam-policy masterkey --location=us-central1`. If runtime SA not listed: `gcloud artifacts repositories add-iam-policy-binding masterkey --location=us-central1 --member=serviceAccount:$RUNTIME_SA --role=roles/artifactregistry.reader`.
3. Build + push smoke image: `docker build -t us-central1-docker.pkg.dev/$GCP_PROJECT_ID/masterkey/masterkey:smoke . && docker push ...`.

**D. Definition of Done**
- `gcloud artifacts repositories describe masterkey --location=us-central1` returns 200.
- Smoke image visible: `gcloud artifacts docker images list us-central1-docker.pkg.dev/$GCP_PROJECT_ID/masterkey`.
- Verification harness F4 PASS.

**Dependencies:** Blocked by: E3-T2 (WIF binding for new repo must auth — only needed if pushing via CI, but smoke-push is local OK)
**Plan reference:** §3 Phase 3 steps 20-22
**Verification check:** Verified by F4

---

#### E4-T2 — `infra: Pre-create Cloud Run masterkey service with correct env-var types (R13)`

**Problem Statement:** R13 (env-var type stickiness) is permanently locked in by this ticket — `DATABASE_URL` and `ANTHROPIC_API_KEY` MUST be plain literals via `--set-env-vars` to match `deploy.yml:216-217`'s shape. Getting it wrong here bricks the service for the rest of the refactor (`Cannot update environment variable to <type> because it has already been set with a different type`).

**Parent Epic:** E4
**Effort Estimate:** S
**Priority:** P0

**A. Environment Context**
- `gcloud` authed; region `us-central1`
- Smoke image: from E4-T1
- Runtime SA: same as `agile-flow-app`
- Secrets to mount (same as current production):
  - `--set-secrets=SUPABASE_URL=supabase-url:latest,SUPABASE_ANON_KEY=supabase-anon-key:latest,SUPABASE_SERVICE_KEY=supabase-service-key:latest`
- Literals to set (same as current production):
  - `--set-env-vars="ENVIRONMENT=production,DATABASE_URL=$PROD_DB_URL,ANTHROPIC_API_KEY=$KEY"`
- Per resolved Q10: `--min-instances=0` for placeholder (NOT 1)

**B. Guardrails**
- DO NOT use `--set-secrets` for `DATABASE_URL` or `ANTHROPIC_API_KEY` — R13. The literal-vs-secret type is sticky per name; switching requires destructive service recreate.
- DO NOT serve real traffic — use `--no-traffic` then `--to-latest` on the new service in isolation.
- DO NOT set `--min-instances=1` on the placeholder — the smoke image shouldn't run hot.
- `deploy.yml:168` hardcodes `--min-instances=1`; Phase 4's real deploy flips it automatically.

**C. Happy Path**
1. Read `$PROD_DB_URL` from `PRODUCTION_DATABASE_URL` secret; `$KEY` from `ANTHROPIC_API_KEY` secret; `$RUNTIME_SA` from `agile-flow-app` service spec.
2. `gcloud run deploy masterkey --image=us-central1-docker.pkg.dev/$GCP_PROJECT_ID/masterkey/masterkey:smoke --region=us-central1 --service-account=$RUNTIME_SA --port=8080 --memory=512Mi --cpu=1 --min-instances=0 --max-instances=10 --allow-unauthenticated --set-env-vars="ENVIRONMENT=production,DATABASE_URL=$PROD_DB_URL,ANTHROPIC_API_KEY=$KEY" --set-secrets="SUPABASE_URL=supabase-url:latest,SUPABASE_ANON_KEY=supabase-anon-key:latest,SUPABASE_SERVICE_KEY=supabase-service-key:latest" --no-traffic`
3. `gcloud run services update-traffic masterkey --to-latest --region=us-central1`.
4. Verify env-var types: `gcloud run services describe masterkey --format=yaml | grep -E 'name: (DATABASE_URL|ANTHROPIC_API_KEY)' -A 2` — value field is a literal, not a `valueFrom: secretKeyRef:` block.

**D. Definition of Done**
- `gcloud run services describe masterkey --region=us-central1 --format='value(status.url)'` returns a URL.
- `gcloud run services describe masterkey --format=yaml` shows `DATABASE_URL` and `ANTHROPIC_API_KEY` as direct values (no `valueFrom`).
- Supabase keys ARE mounted via `valueFrom: secretKeyRef:` (matches production shape).
- `--min-instances=0` confirmed.
- Verification harness F1, F2, F3 PASS.

**Dependencies:** Blocked by: E4-T1
**Plan reference:** §3 Phase 3 step 23 (B-class B3, R13)
**Verification check:** Verified by F1, F2, F3

---

#### E4-T3 — `docs: Capture new service URL and pin into LAUNCH-CHECKLIST + CLAUDE.md`

**Problem Statement:** New service URL `$NEW_URL` is unknowable until E4-T2 creates the service (B5). Pin it into `docs/LAUNCH-CHECKLIST.md` line 10 (plus health-probe and auth-test lines 45-46, 51) and `CLAUDE.md` Project Information block per S6 so `/doctor` and agent sessions discover it without re-reading old runbooks.

**Parent Epic:** E4
**Effort Estimate:** XS
**Priority:** P1

**A. Environment Context**
- Files: `docs/LAUNCH-CHECKLIST.md:10,12,45-46,51`, `CLAUDE.md` Project Information block
- New URL: `gcloud run services describe masterkey --region=us-central1 --format='value(status.url)'`
- If Phase 1 PR still open: amend that PR. If already merged: open small doc-only follow-up PR.

**B. Guardrails**
- Do NOT remove old URL references from session journals or ADRs — historical record stays.
- Do NOT change lines outside the four call-outs in launch checklist.

**C. Happy Path**
1. `NEW_URL=$(gcloud run services describe masterkey --region=us-central1 --format='value(status.url)')`.
2. Replace `agile-flow-app-heo5ry7rua-uc.a.run.app` with the new hostname in launch checklist lines 10, 12, 45-46, 51.
3. Add the new URL to `CLAUDE.md` Project Information block (new line or replace docker example URL).
4. Open or amend PR.

**D. Definition of Done**
- `grep 'masterkey-.*\.run\.app' docs/LAUNCH-CHECKLIST.md` returns ≥ 4 matches.
- `grep 'masterkey-.*\.run\.app' CLAUDE.md` returns ≥ 1 match.
- PR merged.

**Dependencies:** Blocked by: E4-T2
**Plan reference:** §3 Phase 3 step 24 (B-class B5 + S6)
**Verification check:** No direct harness ID; reviewer-verifiable

---

#### E4-T4 — `chore: Add new production + preview Supabase Auth redirect URLs to allowlist`

**Problem Statement:** R4 (production magic-link sign-in breaks) and R12 (preview magic-link sign-in breaks) both materialize the instant `vars.CLOUD_RUN_SERVICE=masterkey` is active if the allowlist hasn't been updated. Both production and preview-PR patterns must be added BEFORE Phase 4 step 29's var flip.

**Parent Epic:** E4
**Effort Estimate:** XS
**Priority:** P0

**A. Environment Context**
- Supabase dashboard (no public API for redirect allowlist) — manual addition
- URLs to add:
  - Production: `https://masterkey-<hash>-uc.a.run.app/auth/callback` (use exact `$NEW_URL` from E4-T3)
  - Preview pattern: `https://pr-*---masterkey-*-uc.a.run.app/auth/callback`
- Dashboard path: Authentication → URL Configuration → Redirect URLs

**B. Guardrails**
- ADD both new entries; do NOT remove the existing `agile-flow-app` entries. Both must coexist through Phase 5.
- Do NOT use a wildcard so broad it allows untrusted hostnames (e.g., `https://*-uc.a.run.app/*`).

**C. Happy Path**
1. Open Supabase dashboard → Authentication → URL Configuration.
2. Add production URL exactly matching `$NEW_URL` + `/auth/callback`.
3. Add preview pattern `https://pr-*---masterkey-*-uc.a.run.app/auth/callback`.
4. Save changes.
5. Record screenshot of allowlist in ticket comment (audit trail).

**D. Definition of Done**
- Ticket comment includes screenshot showing 4 entries in allowlist (old prod + old preview + new prod + new preview).
- Verification harness I4 SKIP (expected — manual check); runbook §5.4 manual check passes.

**Dependencies:** Blocked by: E4-T3 (need `$NEW_URL`)
**Plan reference:** §3 Phase 3 step 26 (R4 + R12)
**Verification check:** Manual (I4 always SKIP per runbook §5.4)

---

#### E4-T5 — `test: Dry-run preview-deploy + preview-cleanup + Supabase branching against masterkey`

**Problem Statement:** Phase 3 step 25's explicit dry-run gate (S4). Opens a throwaway PR labelled `phase3-dryrun` with a trivial change AND an empty `supabase/migrations/<timestamp>_rename_smoke.sql` (per R10) to exercise the Supabase branching path. Confirms preview-deploy pushes to `masterkey/masterkey:pr-N-<sha>`, tags `masterkey` service, smoke-test passes, PR comment updates in place. Then closes PR and confirms cleanup removes the `pr-N` tag. **This ticket runs the `--exercise-preview-deploy` mode of section G.**

**Parent Epic:** E4
**Effort Estimate:** M
**Priority:** P0

**A. Environment Context**
- Branch: `verify/preview-deploy-<UTC-ts>` (per runbook §5.2)
- Throwaway file change: append a timestamp comment to `03-verification-runbook.md` (per runbook §5.2)
- Smoke migration: `supabase/migrations/<timestamp>_rename_smoke.sql` (empty file with single `-- smoke` comment per R10)
- Tools: `gh`, `git`, `curl`
- Variable manipulation: must temporarily flip `vars.CLOUD_RUN_SERVICE` to `masterkey` for the dry-run, then flip back

**B. Guardrails**
- DO NOT run this ticket if any real PR is open (`gh pr list --state open` must return `[]`).
- DO NOT leave `vars.CLOUD_RUN_SERVICE=masterkey` set after the dry-run — Phase 4 step 27 (E5-T1) requires OLD var still in effect when Phase 1 PR merges.
- DO NOT skip the close-PR step — orphaned `pr-N` tag on `masterkey` blocks cleanup verification.
- Label the dry-run PR `phase3-dryrun` (new label may need to be created) so cleanup is easy to confirm.

**C. Happy Path (mirrors runbook §5.2)**
1. Verify F1 (masterkey service exists) PASSes.
2. Create throwaway branch.
3. Append timestamp comment + smoke migration file.
4. Commit + push; open PR.
5. **Phase A:** With `vars.CLOUD_RUN_SERVICE=agile-flow-app` (current), confirm first push routes preview to old service. PASS.
6. Flip vars: `gh variable set CLOUD_RUN_SERVICE --body masterkey && gh variable set ARTIFACT_REPO --body masterkey`.
7. Push empty commit; watch `preview-deploy.yml` for ≤ 12 min.
8. Confirm: image pushed to `masterkey/masterkey:pr-N-<sha>`, `pr-N` tag on `masterkey` service, smoke-test passed, PR comment updated in place.
9. Confirm Supabase branching: dashboard shows new branch from the smoke migration PR.
10. Close PR.
11. Confirm `preview-cleanup.yml` runs against `masterkey` and removes `pr-N` tag.
12. **Flip vars BACK:** `gh variable set CLOUD_RUN_SERVICE --body agile-flow-app && gh variable set ARTIFACT_REPO --body agile-flow`.
13. Delete branch; clean up.

**D. Definition of Done**
- Verification harness G with `--exercise-preview-deploy` flag: G1-G6 ALL PASS.
- Supabase dashboard shows the PR's migration branch was created.
- After cleanup: `gcloud run services describe masterkey --format='value(status.traffic[].tag)'` does NOT contain `pr-N`.
- `gh variable list` shows `CLOUD_RUN_SERVICE=agile-flow-app` and `ARTIFACT_REPO=agile-flow` (vars flipped BACK).

**Dependencies:** Blocked by: E4-T2, E4-T4 (allowlist must include preview pattern); blocks: E5-T1 (must succeed before Phase 4 cutover)
**Plan reference:** §3 Phase 3 step 25 (S4 + R10 + R12); runbook §5.2
**Verification check:** Verified by G1-G6 (active mode)
**NOTE:** This ticket touches ephemeral preview deploys. Verification harness section G must run green before the ticket can close.

---

#### E4-T6 — `chore: Verify Supabase GitHub App allowlist still contains cubrox/masterkey (R10 follow-through)`

**Problem Statement:** R10 — Supabase GitHub App may track repos by `owner/name` OR by `repository.id`. If by name, the rename silently breaks per-PR branching. Step 17 of the plan calls for verification IMMEDIATELY after the repo rename; this ticket is the explicit check.

**Parent Epic:** E4 (logically Phase 2; placed in E4 because verified via the dry-run PR's branching outcome from E4-T5)
**Effort Estimate:** XS
**Priority:** P0

**A. Environment Context**
- Manual check: Supabase dashboard → Project Settings → Integrations → GitHub
- Functional check: E4-T5's smoke migration PR should create a Supabase branch

**B. Guardrails**
- Do NOT re-install the App preemptively; only re-install if the allowlist does not show `cubrox/masterkey`.

**C. Happy Path**
1. Open Supabase dashboard → Project Settings → Integrations → GitHub.
2. Confirm `cubrox/masterkey` appears in the allowlist.
3. If absent: re-install the App on the new repo name and re-confirm.
4. Cross-check: confirm E4-T5's dry-run PR (with smoke migration file) created a Supabase branch.

**D. Definition of Done**
- Ticket comment includes screenshot showing `cubrox/masterkey` in allowlist.
- E4-T5's smoke migration PR has a corresponding Supabase branch visible in dashboard.

**Dependencies:** Blocked by: E3-T2 (repo rename done), E4-T5 (smoke migration PR exercises path)
**Plan reference:** §2.8 + §3 Phase 2 step 17 + R10
**Verification check:** Manual — no harness ID

---

### Epic 5 — Phase 4 tickets

**ORDER WITHIN EPIC IS LOAD-BEARING (per B7).** Each ticket below blocks the next; verification gate between every step.

---

#### E5-T1 — `release: Merge Phase 1 PR with vars STILL pointing at agile-flow-app`

**Problem Statement:** Per re-sequenced Phase 4 (B7), the Phase 1 PR merges FIRST while `vars.CLOUD_RUN_SERVICE` is still `agile-flow-app`. This deploys the rename code to the OLD service — a live no-op proof that the code rename is functionally inert against production traffic.

**Parent Epic:** E5
**Effort Estimate:** XS (merge is a click; the prep is Phase 1)
**Priority:** P0

**A. Environment Context**
- PR: the Phase 1 feature branch PR (contains E2-T1 through E2-T8 commits)
- Trigger: merge → `deploy.yml` → builds + deploys to `agile-flow-app` (because vars unflipped)
- E4-T5 must have run successfully (variables confirmed reset to old values)

**B. Guardrails**
- DO NOT flip `vars.CLOUD_RUN_SERVICE` before this merge — that would route the deploy to `masterkey` with no prior verification of old-service health.
- DO NOT merge until E4-T5 dry-run is verified GREEN and vars confirmed reset.
- DO NOT merge if `gh variable get CLOUD_RUN_SERVICE` does NOT return `agile-flow-app` (or empty — workflow default applies).

**C. Happy Path**
1. Verify `gh variable list` shows `CLOUD_RUN_SERVICE=agile-flow-app` (or absent → default).
2. Verify Phase 1 PR is green (all CI checks pass).
3. Merge PR via GitHub UI (human action, not bot — per CLAUDE.md rule 4).
4. Watch `deploy.yml` run on `main`; expect deploy to `agile-flow-app` with new image SHA.

**D. Definition of Done**
- PR merged to `main`.
- `deploy.yml` run for merge commit: conclusion = `success`.
- `gcloud run services describe agile-flow-app --format='value(status.latestReadyRevisionName)'` shows a new revision name with timestamp newer than the merge.

**Dependencies:** Blocked by: E4-T5 (dry-run gate); blocks: E5-T2
**Plan reference:** §3 Phase 4 step 27 (B-class B7)
**Verification check:** Reviewer-verifiable; no harness ID directly (D3 covers the file-level proof)

---

#### E5-T2 — `verify: Confirm agile-flow-app health post-merge before var flip`

**Problem Statement:** Phase 4 step 28 — verify the rename-code deploy to the OLD service didn't break anything. If health is bad here, we roll back the merge before flipping vars (preserves the clean rollback path).

**Parent Epic:** E5
**Effort Estimate:** XS
**Priority:** P0

**A. Environment Context**
- Old service URL: `https://agile-flow-app-heo5ry7rua-uc.a.run.app` (per `docs/LAUNCH-CHECKLIST.md:10` before E4-T3 update)
- Tools: `curl`, `scripts/smoke_auth.py`

**B. Guardrails**
- If ANY of the three health checks fails: STOP. Do NOT proceed to E5-T3. Roll back the merge via `git revert` PR and re-run `deploy.yml`.
- Do NOT run `scripts/smoke_auth.py` more than 3 times (creates Supabase users; uses `smoke.cubrox.test` domain for tag-cleanup later).

**C. Happy Path**
1. `curl -sf https://agile-flow-app-heo5ry7rua-uc.a.run.app/api/health` → HTTP 200.
2. `curl -sf https://agile-flow-app-heo5ry7rua-uc.a.run.app/api/health/db` → HTTP 200.
3. `uv run python scripts/smoke_auth.py --url https://agile-flow-app-heo5ry7rua-uc.a.run.app` → success.

**D. Definition of Done**
- All three checks return success.
- Ticket comment records each curl response status + smoke_auth output.

**Dependencies:** Blocked by: E5-T1; blocks: E5-T3
**Plan reference:** §3 Phase 4 step 28
**Verification check:** No direct harness ID (script doesn't probe old service post-rename); reviewer-verifiable

---

#### E5-T3 — `infra: Flip GitHub vars (CLOUD_RUN_SERVICE + ARTIFACT_REPO) to masterkey`

**Problem Statement:** The pivot moment. Two `gh variable set` commands flip the deploy target from `agile-flow-app` to `masterkey`. Atomic from `deploy.yml`'s perspective.

**Parent Epic:** E5
**Effort Estimate:** XS
**Priority:** P0

**A. Environment Context**
- `gh` authed
- Commands: `gh variable set CLOUD_RUN_SERVICE --body masterkey && gh variable set ARTIFACT_REPO --body masterkey`

**B. Guardrails**
- DO NOT push to `main` between this ticket and E5-T4 — the next push must be the controlled trivial commit from E5-T4, not an accidental commit.
- DO NOT flip only one of the two vars — both must change atomically.

**C. Happy Path**
1. Verify E5-T2 was green.
2. `gh variable set CLOUD_RUN_SERVICE --body masterkey --repo cubrox/masterkey`.
3. `gh variable set ARTIFACT_REPO --body masterkey --repo cubrox/masterkey`.
4. Verify: `gh variable list --repo cubrox/masterkey` shows both set to `masterkey`.

**D. Definition of Done**
- `gh variable get CLOUD_RUN_SERVICE` returns `masterkey`.
- `gh variable get ARTIFACT_REPO` returns `masterkey`.
- Verification harness D1, D2 PASS.

**Dependencies:** Blocked by: E5-T2; blocks: E5-T4
**Plan reference:** §3 Phase 4 step 29
**Verification check:** Verified by D1, D2

---

#### E5-T4 — `release: Push trivial CHANGELOG commit to trigger deploy to masterkey`

**Problem Statement:** Phase 4 step 30 — the trivial commit that triggers `deploy.yml` to build into `masterkey/masterkey:<sha>` and deploy to the `masterkey` Cloud Run service. CHANGELOG.md entry per §2.6 is the natural choice (also serves as the human-readable record of the rename).

**Parent Epic:** E5
**Effort Estimate:** XS
**Priority:** P0

**A. Environment Context**
- File: `CHANGELOG.md` (append entry)
- Content: per §2.6: "Renamed codebase identifier `cubrox` → `masterkey`. No user-facing change; public product name remains `Master Key`."
- Branch: short-lived `feature/refactor-changelog-trigger` → PR → merge (per CLAUDE.md rule 1: no direct commits to main)

**B. Guardrails**
- Commit MUST be trivial — single-line CHANGELOG addition. Do NOT bundle other changes.
- Do NOT push directly to `main` — use feature branch + PR (CLAUDE.md rule 1).

**C. Happy Path**
1. Create branch `feature/refactor-changelog-trigger`.
2. Append CHANGELOG entry.
3. Open PR; merge (human action).
4. Watch `deploy.yml` run; expect image build into `masterkey/masterkey:<sha>` and deploy to `masterkey` service.

**D. Definition of Done**
- PR merged.
- `deploy.yml` run conclusion = `success`.
- `gcloud artifacts docker images list us-central1-docker.pkg.dev/$GCP_PROJECT_ID/masterkey` shows the new image SHA.
- `gcloud run services describe masterkey --format='value(status.latestReadyRevisionName)'` shows new revision.

**Dependencies:** Blocked by: E5-T3; blocks: E5-T5
**Plan reference:** §3 Phase 4 step 30
**Verification check:** Reviewer-verifiable; harness F1 will reflect new revision

---

#### E5-T5 — `verify: Confirm masterkey service health after first real deploy`

**Problem Statement:** Phase 4 step 31 — verify the new service is healthy on real production traffic. If any check fails, roll back per RB-4.

**Parent Epic:** E5
**Effort Estimate:** XS
**Priority:** P0

**A. Environment Context**
- New service URL: `$NEW_URL` from E4-T3
- Tools: `curl`, `scripts/smoke_auth.py`
- Synthetic monitor still disabled per E2-T8 — manual smoke is the only signal

**B. Guardrails**
- If `/api/health` or `/api/health/db` fails: STOP and execute RB-4 (re-flip vars + trivial commit).
- If `/api/health/db` returns 5xx: Supabase connection broken — check `DATABASE_URL` env-var value on `masterkey` service.
- If `scripts/smoke_auth.py` fails on magic-link redirect: E4-T4's allowlist update didn't take effect — re-check Supabase dashboard.

**C. Happy Path**
1. `curl -sf $NEW_URL/api/health` → 200.
2. `curl -sf $NEW_URL/api/health/db` → 200.
3. `curl -sf $NEW_URL/` → 200 (Master Key landing).
4. `uv run python scripts/smoke_auth.py --url $NEW_URL` → success.

**D. Definition of Done**
- All four checks pass.
- Verification harness F1, F2, F3, H3 PASS.

**Dependencies:** Blocked by: E5-T4; blocks: E5-T6
**Plan reference:** §3 Phase 4 step 31
**Verification check:** Verified by F1, F2, F3, H3

---

#### E5-T6 — `chore: Re-enable synthetic monitor schedule (follow-up PR)`

**Problem Statement:** Reverses the E2-T8 disable. Re-enables hourly cron; the monitor's `gcloud run services describe ${SERVICE_NAME}` indirection auto-resolves to `masterkey`-derived URL via `vars.CLOUD_RUN_SERVICE` (self-heals per Q9 + C3).

**Parent Epic:** E5
**Effort Estimate:** XS
**Priority:** P1

**A. Environment Context**
- File: `.github/workflows/synthetic-monitor.yml`
- Branch: `feature/refactor-restore-monitor` → PR → merge

**B. Guardrails**
- Do NOT bundle other changes — single-purpose uncomment.
- Do NOT modify the `workflow_dispatch` trigger — must remain.

**C. Happy Path**
1. Create branch.
2. Uncomment `schedule:` block in `synthetic-monitor.yml`.
3. Remove the `# DISABLED for masterkey rename` marker.
4. Open PR; merge.
5. Wait for next :17-past-hour fire; confirm it hits `$NEW_URL` and passes.

**D. Definition of Done**
- PR merged.
- `grep -E '^\s*schedule:' .github/workflows/synthetic-monitor.yml` returns ≥ 1 (uncommented).
- Next scheduled run (verified via `gh run list --workflow=synthetic-monitor.yml --limit 1`) conclusion = `success`.

**Dependencies:** Blocked by: E2-T8 (matching disable), E5-T5 (must wait until new service healthy)
**Plan reference:** §3 Phase 4 step 32 (resolved Q9)
**Verification check:** No direct harness ID; observable via `gh run list`

---

#### E5-T7 — `docs: Announce new production URL and update external references`

**Problem Statement:** Phase 4 step 33 — the user-facing URL has changed (we're on `*.run.app`, no custom domain). Announce internally; update any operational docs that reference the production URL but were not touched in E4-T3.

**Parent Epic:** E5
**Effort Estimate:** S
**Priority:** P1

**A. Environment Context**
- New URL: `$NEW_URL` from E4-T3
- Audit search: `rg 'agile-flow-app-heo5ry7rua' .` (find any leftover hard-coded URLs)
- Announcement channels: ticket comment + CHANGELOG (already done in E5-T4) + any team-comms surface

**B. Guardrails**
- Do NOT update session journals (historical record).
- Do NOT update upstream-synced framework docs unless added to `.gembaflow-overrides`.

**C. Happy Path**
1. `rg 'agile-flow-app-heo5ry7rua' .` — list remaining hits.
2. For each non-historical hit: replace with `$NEW_URL`'s hostname.
3. Open PR with the doc updates.
4. Post a notification to team comms with old URL + new URL + deprecation date.

**D. Definition of Done**
- `rg 'agile-flow-app-heo5ry7rua' .` returns only allowlisted historical files (session journals, ADRs).
- Team comms post recorded (link in ticket comment).
- Verification harness B2 PASS.

**Dependencies:** Blocked by: E5-T5
**Plan reference:** §3 Phase 4 step 33
**Verification check:** Verified by B2

---

### Epic 6 — Phase 5 tickets (30 days post-cutover)

#### E6-T1 — `infra: Delete old Cloud Run service agile-flow-app`

**Problem Statement:** Phase 5 step 35 — destructive cleanup. Frees the dual-service window state. Do NOT execute until Phase 4 has been stable for ≥ 30 days AND the rollback option has been explicitly declined.

**Parent Epic:** E6
**Effort Estimate:** XS (the action is one command; the gate is the 30-day wait)
**Priority:** P2

**A. Environment Context**
- `gcloud` authed
- Command: `gcloud run services delete agile-flow-app --region=us-central1`

**B. Guardrails**
- DO NOT execute if `<30 days since E5-T5 verification PASS>`.
- DO NOT execute if any Cloud Logging alert still references `service_name="agile-flow-app"` (check E1-T4 inventory + E6-T5 status).
- DO NOT execute if `gh variable get CLOUD_RUN_SERVICE` still returns `agile-flow-app` (would indicate rollback in progress).

**C. Happy Path**
1. Verify 30-day window elapsed; verify F1 (masterkey health) PASSes; verify E6-T5 status (logging filter updates done).
2. `gcloud run services delete agile-flow-app --region=us-central1` (confirm prompt).
3. Verify: `gcloud run services list --region=us-central1 --format='value(metadata.name)' | grep agile-flow-app` returns nothing.

**D. Definition of Done**
- `gcloud run services describe agile-flow-app --region=us-central1` returns `NOT_FOUND`.
- Verification harness F5 flips to "old service deleted" PASS.

**Dependencies:** Blocked by: E5-T5 + 30-day timer + E6-T5 status; pairs with E6-T2 (AR cleanup)
**Plan reference:** §3 Phase 5 step 35
**Verification check:** F5 reflects deletion

---

#### E6-T2 — `infra: Archive image manifests + delete old Artifact Registry repo agile-flow`

**Problem Statement:** Phase 5 step 36 — destructive. Archive image manifests first (R2 mitigation — preserves forensics for past commit-SHA debugging) before deleting the repo.

**Parent Epic:** E6
**Effort Estimate:** S
**Priority:** P2

**A. Environment Context**
- `gcloud artifacts docker images list us-central1-docker.pkg.dev/$GCP_PROJECT_ID/agile-flow --format=json > snapshots/agile-flow-images.archive.json`
- Then: `gcloud artifacts repositories delete agile-flow --location=us-central1`

**B. Guardrails**
- Manifest archive MUST commit to `snapshots/` BEFORE the delete command runs.
- Do NOT delete if any image in the repo is still referenced by a Cloud Run revision (check `gcloud run revisions list --service=masterkey` — should NOT reference `agile-flow/` paths after Phase 4).

**C. Happy Path**
1. Archive: `gcloud artifacts docker images list ... > snapshots/agile-flow-images.archive.json`; commit.
2. Verify no revision references the repo.
3. `gcloud artifacts repositories delete agile-flow --location=us-central1` (confirm prompt).

**D. Definition of Done**
- `snapshots/agile-flow-images.archive.json` committed.
- `gcloud artifacts repositories describe agile-flow --location=us-central1` returns `NOT_FOUND`.

**Dependencies:** Blocked by: E6-T1 (no Cloud Run revision should reference it after old service deletion)
**Plan reference:** §3 Phase 5 step 36 (R2 mitigation)
**Verification check:** Reviewer-verifiable

---

#### E6-T3 — `chore: Remove old Supabase Auth allowlist entries (production + preview)`

**Problem Statement:** Phase 5 step 37 — prune the old `agile-flow-app-*` production URL AND old `pr-*---agile-flow-app-*` preview pattern from Supabase Auth allowlist after 24-48h post-cutover stability confirmed (per R12).

**Parent Epic:** E6
**Effort Estimate:** XS
**Priority:** P2

**A. Environment Context**
- Supabase dashboard → Authentication → URL Configuration → Redirect URLs

**B. Guardrails**
- Do NOT remove if E5-T5 is not at least 30 days old (or 24-48h minimum per R12 mitigation).
- Do NOT remove the new `masterkey` entries.

**C. Happy Path**
1. Open Supabase dashboard.
2. Delete old `agile-flow-app` production entry.
3. Delete old `pr-*---agile-flow-app-*` preview pattern.
4. Record screenshot of allowlist (now 2 entries: new prod + new preview).

**D. Definition of Done**
- Allowlist contains only `masterkey` patterns (screenshot in ticket comment).

**Dependencies:** Blocked by: E5-T5 + 24-48h minimum (or 30-day window)
**Plan reference:** §3 Phase 5 step 37 (R12)
**Verification check:** Manual

---

#### E6-T4 — `infra: Remove old WIF binding for cubrox/cubrox on deployer SA`

**Problem Statement:** Phase 5 step 38 — prune the dual-write binding from E3-T1. After this, only `cubrox/masterkey` has WIF auth (matches original posture, narrower than dual-state).

**Parent Epic:** E6
**Effort Estimate:** XS
**Priority:** P2

**A. Environment Context**
- `gcloud` authed; `$SA_EMAIL`, `$PROJECT_NUMBER`
- Old member: `principalSet://.../attribute.repository/cubrox/cubrox`
- Roles to remove: both `workloadIdentityUser` and `serviceAccountTokenCreator`

**B. Guardrails**
- DO NOT run until 30-day window elapsed AND E5-T5 PASSes AND E6-T1 succeeded (no chance of rollback to old service).
- DO NOT remove the `cubrox/masterkey` binding by accident — double-check member string.

**C. Happy Path**
1. For each role:
   - `gcloud iam service-accounts remove-iam-policy-binding "$SA_EMAIL" --role="$role" --member="$OLD_MEMBER" --project=$GCP_PROJECT_ID`
2. Verify: `gcloud iam service-accounts get-iam-policy $SA_EMAIL --format=json | jq '.bindings[] | select(.members[] | contains("cubrox/cubrox"))'` returns empty.

**D. Definition of Done**
- Verification harness E3 flips to "old binding pruned" PASS.
- E1, E2 still PASS (new binding intact).

**Dependencies:** Blocked by: E6-T1; E5-T5 + 30-day timer
**Plan reference:** §3 Phase 5 step 38
**Verification check:** E3 PASS

---

#### E6-T5 — `chore: Update Cloud Logging saved queries / dashboards / alerts (likely no-op)`

**Problem Statement:** Phase 5 step 39 — update any logging asset enumerated in E1-T4 to reference `service_name="masterkey"`. Expected no-op per ADR-004; ticket exists for accountability.

**Parent Epic:** E6
**Effort Estimate:** XS to S (depends on E1-T4 inventory)
**Priority:** P2

**A. Environment Context**
- Input: `snapshots/logging-assets.pre-rename.txt` from E1-T4
- If non-empty: update each entry via `gcloud logging metrics update`, `gcloud monitoring policies update`, etc.

**B. Guardrails**
- Do NOT delete any logging metric — only update its filter.
- Do NOT close this ticket without an explicit "verified empty" or "updated N items" note.

**C. Happy Path (empty inventory case)**
1. Re-read `snapshots/logging-assets.pre-rename.txt`.
2. Confirm empty → comment "No logging assets reference service_name; step 39 is a no-op."
3. Close ticket.

**C'. Happy Path (non-empty inventory case)**
1. For each entry: update filter `resource.labels.service_name="agile-flow-app"` → `="masterkey"`.
2. Verify via re-list.

**D. Definition of Done**
- Either: ticket comment says "no-op confirmed" + close.
- Or: each entry from E1-T4 inventory updated; re-list shows new service_name.

**Dependencies:** Blocked by: E1-T4 (inventory); soft-blocked by E6-T1 (deleting old service before updating filters is fine — empty filters just return no results)
**Plan reference:** §3 Phase 5 step 39 (resolved Q7)
**Verification check:** No harness ID

---

#### E6-T6 — `chore: Memory MCP audit — rename or alias cubrox entities`

**Problem Statement:** R7 follow-up. Memory MCP graph in active sessions may have entities keyed on "Cubrox", "Cubrox PRD", etc. After 30 days, run a `prune-memory` pass to rename or add alias observations so agents stop using stale terminology.

**Parent Epic:** E6
**Effort Estimate:** S
**Priority:** P2

**A. Environment Context**
- Tool: Memory MCP (`mcp__memory__search_nodes`, `mcp__memory__create_entities`, `mcp__memory__delete_entities`, `mcp__memory__add_observations`)
- Run via `/prune-memory` skill on each long-lived agent session
- This session: queried at plan-writing time and returned empty — re-check before action

**B. Guardrails**
- Do NOT delete entities — alias or rename to preserve graph relations.
- Do NOT auto-batch across sessions; run per-session manually so the operator can review.

**C. Happy Path**
1. In each long-lived session: `mcp__memory__search_nodes("cubrox")`.
2. For each entity found: either rename (delete + recreate with new name + same observations) or add an observation linking old name → new name.
3. Document the migration log in a ticket comment.

**D. Definition of Done**
- Ticket comment lists sessions audited + entities renamed/aliased.
- New search `mcp__memory__search_nodes("cubrox")` in audited sessions returns only intentionally-historical entries.

**Dependencies:** Soft-blocked by E5-T5 (no point migrating before cutover is real)
**Plan reference:** §2.9 + R7
**Verification check:** No harness ID

---

#### E6-T7 — `docs: Write ADR-007 "Rename to Master Key / masterkey" and resolve PLATFORM-GUIDE drift`

**Problem Statement:** Per §2.6, ADR-006 stays immutable; the rename's architectural rationale needs its own ADR-007. Also resolves the open question on `docs/PLATFORM-GUIDE.md` + `docs/CI-CD-GUIDE.md`: either add them to `.gembaflow-overrides` and edit, or accept the drift (per R5).

**Parent Epic:** E6
**Effort Estimate:** S
**Priority:** P2

**A. Environment Context**
- File to create: `docs/adr/007-rename-to-masterkey.md` (or wherever ADRs live; check ADR-006 location)
- Files in question: `docs/PLATFORM-GUIDE.md`, `docs/CI-CD-GUIDE.md`
- Reference: `01-architecture-plan.md` (the full rename context), `02b-devops-signoff.md`

**B. Guardrails**
- ADR-007 references but does NOT duplicate `01-architecture-plan.md` content — link only.
- For PLATFORM-GUIDE / CI-CD-GUIDE: decide ONE way and document the decision in ADR-007. Do NOT leave both options open.

**C. Happy Path**
1. Read existing ADR template/location.
2. Write ADR-007 with: context (link to plan + signoff), decision (rename happened), consequences (15 risks, dual-state for 30 days, etc.), and the PLATFORM-GUIDE decision.
3. If decision = "add to overrides": edit `.gembaflow-overrides` to include both files; edit them to say `masterkey`.
4. If decision = "accept drift": no file edits; ADR-007 records why (upstream framework drift is acceptable).
5. PR + merge.

**D. Definition of Done**
- `docs/adr/007-rename-to-masterkey.md` (or equivalent path) exists and is merged.
- PLATFORM-GUIDE decision recorded.
- If overrides path chosen: `rg 'agile-flow-app' docs/PLATFORM-GUIDE.md docs/CI-CD-GUIDE.md` returns 0; both files in `.gembaflow-overrides`.

**Dependencies:** Soft-blocked by E5-T5 (writing about a rename before it's real is premature)
**Plan reference:** §2.6 + R5
**Verification check:** No harness ID

---

## Dependency graph

ASCII rendering — read top-to-bottom is roughly chronological:

```
Phase 0 (Epic 1)
   E1-T1 ──┐
   E1-T2 ──┤
   E1-T3 ──┼──► E1-T5 ─────────────────────────────────────────────┐
   E1-T4 ──┘                                                       │
                                                                   │
Phase 1 (Epic 2) — all on one branch, merge together as one PR     │
   E2-T1 ────┐                                                     │
   E2-T2 ────┤                                                     │
   E2-T3 ────┤                                                     │
   E2-T4 ────┼──► (Phase 1 PR opens — preview goes to OLD svc)     │
   E2-T5 ────┤                                                     │
   E2-T6 ────┤                                                     │
   E2-T7 ────┤                                                     │
   E2-T8 ────┘                                                     │
                                                                   │
Phase 2 (Epic 3) — order LOAD-BEARING                              │
   E1-T3 ────────────────────────────────────► E3-T1 (WIF)         │
   E1-T5 ──────────────────────────────────────►──┐                │
   ALL E2-Tx (Phase 1 PR opened) ────────────────►┤                │
                                                  ▼                │
                                              E3-T2 (REPO RENAME) ◄┘
                                                  │
                                                  ▼
                                              E3-T3 (new board)
                                                  │
                                              E1-T1 ──► E3-T4 (migrate 67 items)
                                                  │
Phase 3 (Epic 4)                                  │
   E3-T2 ────► E4-T1 (AR repo)                    │
                  │                               │
                  ▼                               │
              E4-T2 (Cloud Run pre-create) ◄──────┤
                  │                               │
                  ▼                               │
              E4-T3 (capture URL → docs)          │
                  │                               │
                  ▼                               │
              E4-T4 (Supabase allowlist)          │
                  │                               │
              E3-T2 ─┐                            │
                     ▼                            │
                  E4-T5 (DRY-RUN — gates Phase 4) │
                     │                            │
                     ├──► E4-T6 (Supabase App     │
                     │           allowlist check) │
                     │                            │
Phase 4 (Epic 5) — order LOAD-BEARING             │
                     ▼                            │
                  E5-T1 (merge Phase 1 PR — old vars still)
                     │
                     ▼
                  E5-T2 (verify old svc health)
                     │
                     ▼
                  E5-T3 (FLIP VARS) ◄── highest-risk single ticket
                     │
                     ▼
                  E5-T4 (trivial commit → deploy to masterkey)
                     │
                     ▼
                  E5-T5 (verify new svc health)
                     │
                     ▼
                  E5-T6 (re-enable monitor) ◄── pairs with E2-T8
                     │
                     ▼
                  E5-T7 (announce new URL)
                     │
                     ▼                30-day timer
                     ╰─────────────────────────► Phase 5 (Epic 6)
                                                E6-T1 (delete old svc)
                                                E6-T2 (delete old AR)
                                                E6-T3 (prune Supabase allowlist)
                                                E6-T4 (prune old WIF)
                                                E6-T5 (Cloud Logging updates)
                                                E6-T6 (Memory MCP audit)
                                                E6-T7 (ADR-007 + PLATFORM-GUIDE)
```

### Critical chain (cannot parallelize)

`E1-T3 → E3-T1 → E3-T2 → E4-T2 → E4-T3 → E4-T4 → E4-T5 → E5-T1 → E5-T2 → E5-T3 → E5-T4 → E5-T5`

This is the 12-ticket critical path. Everything else is either Phase 0 prep (parallelizable into the same PR), Phase 1 code work (parallelizable into the same PR), or Phase 5 cleanup (no internal ordering within the 30-day window except E6-T1 → E6-T2).

### What blocks the most downstream work

**E3-T2 (repo rename)** unblocks: E3-T3, E3-T4, E4-T1, E4-T2, E4-T3, E4-T4, E4-T5, E4-T6, E5-T1-T7, E6-T1-T7. Twenty-three downstream tickets. This is why E3-T2's pre-flight checklist is the longest in the backlog.

---

## Recommended sprint shape

The whole refactor can ship as a focused "rename week" (one human-week of elapsed time, calendar — most tickets are short; the gating is sequential verification, not effort).

### Sprint structure: One focused "rename week" + 30-day cleanup

**Sprint 1 — "Rename Week" (5 working days)**

Day 1 (morning): Epic 1 (Phase 0) — all 5 tickets, snapshots merged.
Day 1 (afternoon) - Day 2: Epic 2 (Phase 1) — single PR, all 8 sub-tickets, code review.
Day 3 (morning): Epic 3 tickets E3-T1 (WIF) + E3-T2 (repo rename) + E3-T3 (board creation).
Day 3 (afternoon): Epic 3 ticket E3-T4 (board migration of 67 items).
Day 4: Epic 4 (Phase 3) — all 6 tickets including E4-T5 dry-run gate.
Day 5 (morning): Epic 5 (Phase 4) tickets E5-T1 through E5-T5 (the cutover).
Day 5 (afternoon): Epic 5 tickets E5-T6 + E5-T7 (re-enable monitor, announce).

**Sprint 2 — "Cleanup Sprint" (scheduled 30 days later, 1 day total)**

All 7 Epic 6 tickets — destructive cleanup. ≤ 1 day elapsed work.

### Smallest "ship now" subset if execution stops partway

If execution must stop after Sprint 1 day 5 (cutover succeeded), the system is in a fully-functional state with two valid postures:

1. **`agile-flow-app` deleted, only `masterkey` lives** (executed Phase 5 same-day): clean state. Recommended only if 30-day rollback window is explicitly declined by product owner.
2. **Both services live, `masterkey` serving traffic** (dual-state through Phase 5 gate): default — preserves rollback.

If execution stops mid-Phase 4 (between E5-T3 and E5-T5), the rollback is RB-4: flip vars back, trivial commit, old service serves again. The system is never left in a half-rename state for more than the duration of a single `gh workflow run`.

The minimum viable subset for "the rename happened" is:
- Epic 1 (snapshots) + Epic 2 (code PR merged) + Epic 3-T1 + Epic 3-T2 (WIF + repo rename) + Epic 4-T1 through T5 (new infra + dry-run) + Epic 5-T1 through T5 (cutover + verify).

Twenty-one tickets to cross the "rename complete" line. Epics 3-T3/T4 (board migration) and 5-T6/T7 (monitor + announce) can slip into a follow-up if needed; Epic 6 is always 30+ days later by design.

---

## Highest-risk ticket flag

**E5-T3 (Flip GitHub vars CLOUD_RUN_SERVICE + ARTIFACT_REPO to masterkey)** is the highest-risk single ticket.

Reasoning:
- It is the **moment of irreversible commitment** to the new service for all subsequent deploys. Once flipped, the next push to `main` (or any preview PR) routes to `masterkey`. If `masterkey` is misconfigured (e.g., E4-T2 set env-var types wrong per R13), the next deploy fails AND `agile-flow-app` is no longer the live target.
- It depends on the **largest stack of upstream invariants holding simultaneously**: E4-T2 env-var types correct, E4-T3 URL captured, E4-T4 Supabase allowlist updated, E4-T5 dry-run succeeded, E5-T1 Phase 1 PR merged, E5-T2 old-service health confirmed.
- It is **two `gh variable set` commands** — small action, no rich error feedback. A typo (`masterke` instead of `masterkey`) deploys to a non-existent service silently. The only safety is the verification harness D1, D2 PASS check, which the ticket explicitly requires before continuing.
- The rollback (RB-4) is well-defined and tested by E4-T5's dry-run, BUT the rollback path itself requires another two `gh variable set` calls and a trivial commit — a 5-10 minute reversal window during which preview deploys fire against the wrong target.

E3-T2 (repo rename) has more downstream blast radius, but its pre-flight checklist + 30-day GitHub redirect grace window make recovery comparatively straightforward. E5-T3 is the smallest-yet-most-irreversible ticket in the entire refactor.

---

**Result:** Refactor backlog drafted — ready for product-owner review before live load
Format: 6 epics + 37 tickets in Agentic PRD Lite per `docs/TICKET-FORMAT.md` (E1: 5, E2: 8, E3: 4, E4: 6, E5: 7, E6: 7)
Label scheme: 9 reused + 11 new (`epic/masterkey-rename`, `phase/0..5`, `type:*`, `risk:destructive`, `verifies:G`)
Verification linkage: every ticket cross-references plan §section + harness check IDs where applicable
Highest-risk ticket: E5-T3 (var flip) — small action, largest stack of preconditions, narrow rollback window
