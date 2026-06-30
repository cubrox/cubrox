# DevOps Sign-off: `cubrox` -> `masterkey` Rename Plan v2

**Reviewer:** DevOps Engineer persona
**Date:** 2026-06-29
**Plan under review:** `reports/refactor/01-architecture-plan.md` (v2)
**Prior review:** `reports/refactor/02-devops-review.md`

---

## Verdict

**ALIGNED**

v2 substantively addresses all seven B-class blockers from the prior review, folds R10/R12 (plus three additional FYI-grade risks R13/R14/R15) into the register with workable mitigations, and resolves all ten v1 open questions consistently with what I recommended. The Phase 4 re-sequencing is materially correct — the var-flip race window is gone. Restraint is warranted; no new blocking concerns.

---

## 1. Blocker resolution table

| ID | Resolved? | Where in v2 | Notes |
|----|-----------|-------------|-------|
| B1 | Y | §2.4 row 1 (`ci.yml:218,307,315`) + Phase 1 step 8 + Changelog bullet B1 | `CUBROX_TEST_SEED_ENABLED` literal in `ci.yml` is now explicitly in the Phase 1 PR's rename pass. Architect correctly identifies it cannot be handled by a `vars.*` flip. |
| B2 | Y | §2.1 WIF row + §2.3 WIF row + Phase 0 step 3 (verify) + Phase 2 step 16 (dual-write, BEFORE rename) + Phase 5 step 38 (prune) + R3 (rewritten) | The correct mechanism is now used: SA IAM policy `principalSet` dual-write with BOTH `workloadIdentityUser` AND `serviceAccountTokenCreator`, verified via `rollback-production.yml` workflow_dispatch dry-run. The wrong "edit attribute condition" path is removed from R3. |
| B3 | Y | Phase 3 step 23 explicit guard rail + R13 + Changelog bullet B3 | Plain literal `--set-env-vars` for `DATABASE_URL` and `ANTHROPIC_API_KEY`, matching `deploy.yml:216-217`. Explicit DO-NOT-USE-secrets warning for `masterkey` during dual-service window. Supabase keys correctly retained on `--set-secrets`. |
| B4 | Y | §2.5 (both scripts in scope) + Phase 1 step 9 + Changelog bullet B4 | `scripts/provision-gcp-project.sh:800,1011` and `scripts/diagnose-cloudrun.sh:35` (+ line 23 comment) all queued for edit in Phase 1 PR. Architect explicitly confirms both files in `.agile-flow-overrides` so `template-sync.sh` won't revert them. |
| B5 | Y | §2.6 LAUNCH-CHECKLIST row + Phase 3 step 24 (captures `$NEW_URL` and pins it) | URL capture command included; instruction to amend Phase 1 PR while still open (or open a doc-only follow-up) is correct. Lines 45-46 and 51 of launch checklist are explicitly called out for update. |
| B6 | Y | §2.2 first row note + R6 rewritten | Audit-debt language matches my suggestion: `pyproject.toml:name` flows into wheel filenames, `uv pip list`, and `[tool.*]` config blocks. No action required today. |
| B7 | Y | §3 Phase 4 (re-sequenced steps 27-34) + RB-4 + Changelog bullet B7 | New order: merge PR with old vars (deploys rename code to old service as a live no-op proof) → verify old-service health → flip vars → trivial commit to trigger deploy to new service → verify new-service health → re-enable synthetic monitor. This matches my recommended alternate ordering exactly. Race window eliminated. |

---

## 2. Risk register check

**R10 (Supabase GitHub App allowlist on rename):** Present in §2.8 row 5 and R10 entry. Mitigation routes through Supabase dashboard verification post-rename plus the Phase 3 step 25 dry-run PR exercising the branching path with an empty migration file. Workable.

**R12 (preview-PR redirect pattern in Supabase Auth allowlist):** Present in §2.8 row 4 and R12 entry. Both production AND preview URL patterns added in Phase 3 step 26; both old patterns pruned in Phase 5 step 37. Workable.

**Additional risks v2 adds:**
- **R13** (env-var type stickiness) — well-scoped from B3, mitigation matches.
- **R14** (services-per-region quota during dual-service) — FYI only as I flagged.
- **R15** (external forks) — FYI only as I flagged; Phase 0 step 6 enumeration is appropriate.

**New risks I would flag now:** None. I considered whether the Phase 3 step 25 dry-run requires the temporary `vars.CLOUD_RUN_SERVICE=masterkey` flip to happen WHILE the Phase 1 PR is still in flight — and noted the architect correctly warns "Flip the var BACK to `agile-flow-app` immediately" before Phase 4 step 27 (Phase 1 merge). That sequencing is safe because the dry-run PR itself is post-Phase-1-PR-open but pre-merge, and no other PRs are in flight per Phase 0 step 5. If a real PR opens during the dry-run window, the operator is responsible for not pushing to it — acceptable operational discipline, not a structural risk worth a new R entry.

---

## 3. Phase ordering sanity check

Phase 0 is read-only (inventory, snapshots, WIF verification, Cloud Logging enumeration, open-PR check, forks check) — no production impact. Phase 1 lands all code/script/doc edits on a feature branch and its preview deploy goes to the OLD `agile-flow-app` service (because vars are unflipped), which is the right validation that the rename is a functional no-op. Phase 2 dual-writes the WIF binding for `cubrox/masterkey` BEFORE renaming the repo, so no GCP-touching workflow ever sees an unauthorized request — then renames the repo and migrates the project board, with the Supabase GitHub App allowlist verified immediately after. Phase 3 pre-creates the new Artifact Registry repo and Cloud Run `masterkey` service with matching env-var types (per R13), captures the new URL into LAUNCH-CHECKLIST, runs the explicit dry-run PR to exercise preview-deploy + preview-cleanup against the new service (with a Supabase migration to exercise branching per R10), and adds both production and preview redirect URLs to Supabase Auth. Phase 4 ships exactly one risk per step: merge Phase 1 PR with old vars → verify old service health → flip vars → trivial commit triggers deploy to new service → verify new service health → re-enable synthetic monitor. Phase 5 (30-day delay) prunes the old service, old AR repo, old Supabase redirect entries, old WIF binding, and updates any Cloud Logging assets enumerated in Phase 0. No race windows, no broken dependencies, every destructive step has a rollback path documented.

---

## 4. New blocking concerns

None.

---

## 5. Sign-off

The plan is sound and ready for execution-design review. Handing off to Quality Engineering for verification-script design — specifically, pre/post checks for each phase's RB-N rollback point, the dry-run PR's acceptance gate at Phase 3 step 25, and the synthetic-monitor self-healing assertion in Phase 4 step 32.

---

**Result:** Plan sign-off granted; verdict ALIGNED
Blocking concerns resolved: 7 of 7 (B1-B7)
New risks accepted with mitigation: R10, R12, R13, R14, R15
Open questions resolved consistently: 10 of 10 (Q1-Q10)
New blockers raised: 0
