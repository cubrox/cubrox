# DevOps Review: `cubrox` -> `masterkey` Rename Plan

**Reviewer:** DevOps Engineer persona
**Date:** 2026-06-29
**Plan under review:** `reports/refactor/01-architecture-plan.md`
**Repo state at review time:** `cubrox/cubrox`, 0 open PRs, default-branch ruleset id 15886599 active

---

## Verdict

**NEEDS_REVISION**

The plan is structurally sound and the staged cutover (pre-create new service, flip vars, delete old) is the right shape for Cloud Run. But there are seven blocking issues that would break things mid-rename, plus three claims that are factually wrong about how our infra is wired and need to be corrected before the architect's Phase 4 will execute cleanly. None of these require a major rewrite — they're tightening, not redoing.

The biggest single miss is **`ci.yml` references `CUBROX_TEST_SEED_ENABLED` at line 315 and the architect's inventory does not list it.** That guarantees Phase 1's PR turns the CI red the moment the env var is renamed in the app. Five other concrete issues follow.

---

## 1. Answers to the architect's open questions (Section 5)

### Q1 — Blue/green via Cloud Load Balancer + custom domain before rename?

**Don't do it.** The architect's instinct ("widens the blast radius") is correct. A Cloud Load Balancer in front of Cloud Run requires a serverless NEG, URL map, target HTTPS proxy, global forwarding rule, managed SSL cert provisioning (which takes 15-30 min to validate), and a domain you control. That's a week of work and at least one new IAM role for the deployer SA (`compute.networkAdmin`). The destructive create-new-then-delete-old approach the plan describes is the right call for a single-service Cloud Run app with no external DNS dependency. Pre-creating `masterkey` at Phase 3 step 18 already gives us 99% of the blue/green benefit — both services exist, both are reachable, we cut over GitHub vars in a single commit.

### Q2 — WIF condition: what is actually set today?

The architect mischaracterizes the WIF binding. Per `scripts/provision-gcp-project.sh` lines 437-439 and 465-474, the **attribute-condition is trivially true** (`assertion.repository != ''`) — it does NOT pin to repo. The repo pin lives on the **SA's IAM policy binding** as the `principalSet` member:

```
principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github/attribute.repository/${WIF_OWNER}/${WIF_REPO_NAME}
```

So R3 mitigation step "(a) change attribute condition" is impossible — there's nothing to change at the provider level. The actual fix is: **before Phase 2 step 12 (repo rename), add a second IAM binding** on the deployer SA for `principalSet://.../cubrox/masterkey` alongside the existing `principalSet://.../cubrox/cubrox`, for both `roles/iam.workloadIdentityUser` AND `roles/iam.serviceAccountTokenCreator` (the script's lines 466 confirm BOTH roles are required, not just `workloadIdentityUser`). Then rename. Then remove the old binding in Phase 5. This is the only way to do the rename without a window where WIF auth is broken.

Concrete commands (run before Phase 2 step 12):

```bash
SA_EMAIL=$(gcloud secrets versions access latest --secret=gcp-deployer-sa-email --project=$GCP_PROJECT_ID 2>/dev/null) \
  || SA_EMAIL="<read from GCP_SERVICE_ACCOUNT secret>"
PROJECT_NUMBER=$(gcloud projects describe $GCP_PROJECT_ID --format='value(projectNumber)')
NEW_MEMBER="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github/attribute.repository/cubrox/masterkey"
for role in roles/iam.workloadIdentityUser roles/iam.serviceAccountTokenCreator; do
  gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
    --role="$role" --member="$NEW_MEMBER" --project=$GCP_PROJECT_ID
done
```

### Q3 — Secret Manager secret renames?

**Leave them.** Architect is right. `supabase-url`, `supabase-anon-key`, `supabase-service-key` are project-scoped, generic, and the runtime SA already has `secretAccessor` bindings on them by name. Renaming costs: create new secret, replicate value, grant SA access, update `--set-secrets` on every deploy workflow, redeploy, delete old. Zero functional benefit. **DO NOT** prefix with project name; the secret namespace is already keyed by the GCP project ID which is the project boundary.

### Q4 — Artifact Registry cleanup window?

**30 days, not 7.** Storage is cheap (~$0.10/GB-month) and the *only* way to roll back to a specific commit-SHA revision after Phase 4 is to re-pull that image. If we delete the old `agile-flow` AR repo on day 7 and discover on day 10 that revision `agile-flow-app-00042-xyz` had a property the new `masterkey-*` revisions don't, we're stuck. Set a 30-day calendar reminder; let Cloud Run's own revision GC run on the new service.

### Q5 — Widen WIF to `repository_owner == 'cubrox'`?

**No, keep the per-repo binding.** Each binding is a single line in the SA's IAM policy; rename is a one-time event. Widening to org-level means any new repo created under `cubrox` (a public test fork, a workshop attendee mistake, anything someone with org-create permission spawns) inherits production-deploy capability. The blast radius of "I accidentally typed the wrong thing" goes from "this repo's workflows" to "every repo in the org". Audit-trail clarity is the secondary benefit; defense-in-depth is the primary one.

### Q6 — Custom domain timing?

**Defer entirely.** Architect's lean is right. Custom domain requires (a) a registered domain, (b) DNS records the team controls, (c) GCP-managed cert provisioning (15-30 min), (d) updating Supabase Auth redirect allowlist with the new domain, (e) a new round of magic-link testing. None of that is in the locked scope. Bundling it would also delay Phase 5 cleanup (you can't delete the old service while DNS still resolves to it for some users). File as a separate epic post-launch.

### Q7 — Enumerate Cloud Logging / Monitoring assets?

You can do this from the workstation now, no plan changes needed:

```bash
gcloud logging metrics list --project=$GCP_PROJECT_ID
gcloud alpha monitoring policies list --project=$GCP_PROJECT_ID --format='value(displayName,combiner)'
gcloud monitoring dashboards list --project=$GCP_PROJECT_ID --format='value(displayName)'
```

Based on the current setup (Cloud Logging + Error Reporting only, per `docs/LAUNCH-CHECKLIST.md` §E line 63, "Sentry deliberately deferred"), I expect zero custom alert policies and zero custom dashboards. The audit will most likely return empty, and Phase 5 step 30 becomes a no-op. **Run the enumeration before Phase 4 and confirm; if it returns anything, update those before Phase 5.** Note: Error Reporting is unaffected — it auto-groups by stack trace, not by service name.

### Q8 — `SUPABASE_DB_URL` secret survives rename?

Yes, repo secrets are repo-scoped not name-scoped. Rename preserves them. Confirmed by GitHub's docs and by the fact that the same is true for `GCP_PROJECT_ID`, `PRODUCTION_DATABASE_URL`, etc. The risk is non-existent. The architect correctly listed this in §2.1; Q8 is over-cautious — strike it.

### Q9 — Synthetic monitor cron during cutover?

**Disable the schedule cleanly, do NOT rely on luck.** Cron jobs in GitHub Actions can fire up to ~15 min late under load — the architect's "before the next :17" gambit is not reliable. Two options:

1. Comment out the `schedule:` block in `synthetic-monitor.yml` on the Phase 1 branch, restore in Phase 4 post-cutover small follow-up PR. (Adds a file edit, but is auditable.)
2. Set a GitHub repo variable `SYNTHETIC_MONITOR_DISABLED=true` and add `if: vars.SYNTHETIC_MONITOR_DISABLED != 'true'` to the monitor job. This avoids touching the workflow file.

Either way: don't rely on timing. Also: the alert issue dedup uses an HTML-comment marker in the body (line 153), so even if it does fire, it'll just comment on the existing issue rather than spam — but a false `[ALERT]` issue still wakes up the on-call.

### Q10 — `--min-instances=1` cost during dual-service window?

Architect's option B (`--min-instances=0` until cutover, flip to 1 in Phase 4) is the right one. ~$15-30/month is rounding error, BUT keeping the placeholder service warm with `--min-instances=1` means it's *actually running* the smoke-test image during the dual-service window. If anything goes wrong with the placeholder (bad image, missing env, OOM), it crashes loudly and falsely looks like the cutover broke. Keep the placeholder at `--min-instances=0` (cold-start risk on first probe is acceptable for a service no one is using), and let the actual production deploy in Phase 4 flip min-instances to 1 because `deploy.yml` line 168 hardcodes `--min-instances=1` on every deploy. (Side note: that hardcoding means Phase 3 step 18's `--min-instances=1` flag is overridden the moment Phase 4 step 23 runs anyway. The architect's pre-create command is functionally fine, but the flag is cosmetic.)

---

## 2. Blocking concerns

### B1 — `CUBROX_TEST_SEED_ENABLED` is set inside `.github/workflows/ci.yml`, missing from the inventory

`.github/workflows/ci.yml:315` sets `CUBROX_TEST_SEED_ENABLED: 'true'` in the a11y job's env. The architect's §2.4 inventory of CI/CD workflows lists only files that need changes via `vars.*` indirection — but ci.yml literally inlines the old env-var name. After Phase 1 renames the app's env-var to `MASTERKEY_TEST_SEED_ENABLED`, the a11y job will pass the OLD name to a uvicorn subprocess that no longer reads it. Result: the test-seed router never mounts, every Playwright test hits 404 on `/test/seed`, the a11y job goes red on Phase 1's PR, and merging Phase 1 blocks indefinitely.

**Fix:** Add `.github/workflows/ci.yml:218,307,315` to the §2.4 table with the rename. This is NOT an upstream-synced file — it's project-owned (workflows/ is in the syncDirectories list in `.agile-flow-version` for *some* templates but this `ci.yml` has project-specific job definitions like the a11y block). Just edit it in the Phase 1 PR alongside the app code.

### B2 — WIF rebinding step missing from Phase 2

Per Q2 answer above: the architect's R3 mitigation "change the attribute condition" doesn't match how WIF is wired in this project. The actual fix (add SA IAM binding for the new repo name BEFORE the rename, remove old one in Phase 5) is not in Phase 2's numbered steps. Without it, **every workflow that needs GCP — `deploy.yml`, `preview-deploy.yml`, `synthetic-monitor.yml`, `preview-cleanup.yml`, `rollback-production.yml` — will fail with `iam.serviceAccountTokenCreator denied` immediately after Phase 2 step 12.** Production keeps serving the last revision, but no new deploys can happen — including the cutover deploy itself in Phase 4. This is the single most likely "stuck in the middle" failure mode.

**Fix:** Insert a step 11.5 in Phase 2 (before step 12): "Add IAM binding for `principalSet://.../cubrox/masterkey` to the deployer SA for both `roles/iam.workloadIdentityUser` AND `roles/iam.serviceAccountTokenCreator`. Verify by triggering `workflow_dispatch` on `rollback-production.yml` (it auths to GCP but only acts on user-confirmed input — safe to dry-run with `revision=<currentRevision>`, `reason='WIF binding verification'`)." Then step 12 (repo rename) is safe. Then a Phase 5 step removes the old binding.

### B3 — DATABASE_URL env-var type collision risk at first post-cutover deploy

`.github/workflows/deploy.yml:171-184` warns explicitly about this trap: Cloud Run permits ONE env-var TYPE per name (plain literal vs Secret Manager mount), and switching types fails with `Cannot update environment variable [DATABASE_URL] to <type> because it has already been set with a different type`. The architect's Phase 3 step 18 pre-creates `masterkey` with `--set-env-vars="DATABASE_URL=$PROD_DB_URL"` (plain literal — matches production's current shape). That's correct. But Phase 4 step 23 will then deploy via `deploy.yml`, which ALSO sets `DATABASE_URL` as a plain literal (line 216). Consistent — should work. **However**, if anyone in the dual-service window manually runs a `gcloud run deploy masterkey --set-secrets="DATABASE_URL=..."` (for example, to test secret-mount migration), the masterkey service becomes permanently stuck on the secret type, and the next `deploy.yml` run fails. This is not in the risk register.

**Fix:** Add to Phase 3 step 18: "DO NOT use `--set-secrets` for `DATABASE_URL` on `masterkey`. The literal-vs-secret type is sticky on Cloud Run; switching requires service recreate. Use the same env-var shape `deploy.yml` uses (plain literal sourced from `PRODUCTION_DATABASE_URL`)." Same warning for `ANTHROPIC_API_KEY`.

### B4 — `provision-gcp-project.sh` hardcodes `agile-flow-app` at line 800, 1011 and is in `.agile-flow-overrides`

The architect's §2.5 says `provision-gcp-project.sh` is "framework provisioner — out of scope". That's wrong twice:
1. `.agile-flow-overrides` (verified content: this file IS listed, line "scripts/provision-gcp-project.sh") so editing it does NOT fight `template-sync.sh`.
2. New workshop attendees / new GCP project setups will run this script and get a service named `agile-flow-app` even after the rename, which then doesn't match `vars.CLOUD_RUN_SERVICE=masterkey` and creates a *second* orphan service on their project.

The script reads `SERVICE_NAME="${CLOUD_RUN_SERVICE:-agile-flow-app}"` — so the operator-passed env var works as a workaround, but the default and the post-script "next steps" output (line 1011) still print `agile-flow-app`. This is a footgun.

**Fix:** Update lines 800 and 1011 of `scripts/provision-gcp-project.sh` to default to `masterkey`. Add to the Phase 1 PR — it's in overrides, won't conflict with upstream sync. Also update `scripts/diagnose-cloudrun.sh` line 35 (`SERVICE="${CLOUD_RUN_SERVICE:-agile-flow-app}"`) — same reasoning, also in `.agile-flow-overrides` (verified line "scripts/diagnose-cloudrun.sh"). The architect's §2.5 explicitly said "no change" for both — that's incorrect.

### B5 — `docs/LAUNCH-CHECKLIST.md:10` hardcodes the live URL hash; rename invalidates it

The plan §3 Phase 4 step 25 says to update this line, but it's a SINGLE-LINE source-of-truth for "what URL do operators hit" and it's referenced from multiple checklist items (§2.C health-probe instructions on line 45-46, §2.D auth-test on line 51). After cutover, the new URL hash (the `heo5ry7rua` segment) WILL change — that's a Cloud Run service-creation-time value, not a service-name-derived value. The new hash is unknowable until Phase 3 step 18 actually runs `gcloud run deploy`.

**Fix:** Phase 3 step 19 (curl the new service) should END with: "capture the new URL via `gcloud run services describe masterkey --region=us-central1 --format='value(status.url)'` and pin it into `docs/LAUNCH-CHECKLIST.md` line 10 in the Phase 1 PR (which is still open at this point — amend the PR with the URL update before merging in Phase 4)." If the Phase 1 PR has already merged, this becomes a separate doc-only PR in Phase 4.

### B6 — `pyproject.toml` package name is `agile-flow-gcp` but the project is for Cubrox — and the architect leaves this for future maintainers without explaining the consequence

Architect says "leave it" (§2.2 first row, R6). I agree we shouldn't rename it. But the *reason* given ("the Python package on disk is `app/`, not `cubrox/`") understates one real consequence: `pyproject.toml`'s `name` is what `uv build` emits in the wheel filename and what shows up in `uv pip list`. It's also what `pyproject.toml`-aware tools (ruff config blocks, mypy config blocks, pytest config blocks) reference. If ANY of those config blocks scope to `[tool.X.agile-flow-gcp]`, they'll silently stop applying after a rename.

**Fix:** No action needed today (we're not renaming), but add a NOTE to R6: "if any maintainer later renames `pyproject.toml:name`, they must also audit `[tool.*]` config blocks for the old name." Architect can either accept this clarification or strike R6 entirely as out-of-scope speculation.

### B7 — Phase 4 step 22 ("Merge the Phase 1 PR") races the var flip in step 21

Phase 4 sequencing:
- Step 21: `gh variable set CLOUD_RUN_SERVICE --body masterkey` and `gh variable set ARTIFACT_REPO --body masterkey`
- Step 22: Merge the Phase 1 PR
- Step 23: deploy.yml runs and uses new vars

Problem: if step 21 runs first and ANY workflow fires between step 21 and step 22 (e.g. someone pushes a commit, opens a PR, the synthetic monitor hits :17), that workflow runs with NEW vars but OLD code (Phase 1 PR not yet merged). For `deploy.yml` that's fine (only triggers on main push). For `preview-deploy.yml` it's a real problem — it'll try to push to AR repo `masterkey/masterkey:pr-N-<sha>` and tag `masterkey` service, but the in-flight PR's code still references `CUBROX_TEST_SEED_ENABLED` in tests. For `synthetic-monitor.yml` (which doesn't deploy, just probes) it's actually fine because it resolves the URL dynamically.

**Fix:** Reorder Phase 4:
- 21a. Merge the Phase 1 PR (CI is green from when it was opened; merging doesn't trigger a deploy yet because `deploy.yml` only fires on push-to-main, which is what the merge does — but the deploy step's `vars.CLOUD_RUN_SERVICE` is still `agile-flow-app`, so it would deploy to the OLD service. NO — this is wrong too).
- 21b. Set the GitHub vars (instantaneous).
- 21c. Trigger `deploy.yml` via `workflow_dispatch` (requires adding `workflow_dispatch:` to deploy.yml, which it currently does NOT have — verified at line 3-5: only `on.push.branches: [main]`).

OR — simpler — use the existing trigger: **merge Phase 1 PR FIRST while vars still point at `agile-flow-app`** (deploys post-rename code to old service — works because code rename is functionally a no-op per §3 Phase 1 step 11 acceptance criterion). Then set the vars. Then push a tiny no-op commit to main to trigger `deploy.yml` against the new service. This way each phase ships only one risk, not two.

Recommend: revise Phase 4 to:
- 21. Merge the Phase 1 PR (post-rename code deploys to old service via existing vars — verifies code rename is a no-op live, satisfies §3.11 acceptance gate).
- 22. Verify production health on the old service URL after the merge-triggered deploy.
- 23. Set vars: `CLOUD_RUN_SERVICE=masterkey`, `ARTIFACT_REPO=masterkey`.
- 24. Push a trivial commit to main (e.g. CHANGELOG entry for the rename) to trigger `deploy.yml`, which now builds + deploys to the new service.
- 25. Verify new service URL health.
- 26. Synthetic monitor next run hits the new URL automatically.

This ordering eliminates the race entirely.

---

## 3. Non-blocking suggestions

### S1 — Add a `workflow_dispatch:` trigger to `deploy.yml` permanently

Independent of the rename, `deploy.yml` only fires on push-to-main. There's no manual-deploy escape hatch except merging an empty PR. Adding `workflow_dispatch:` (with no inputs, runs on the default branch) costs nothing and would have helped in past incidents — and helps in Phase 4 step 23 if we choose the alternate ordering. One-line addition. File a follow-up after the rename.

### S2 — Snapshot more than the service spec in Phase 0 step 2

Plan says `gcloud run services describe agile-flow-app --format=yaml > snapshots/...`. Also capture:
- `gcloud run revisions list --service=agile-flow-app --region=us-central1 --format=yaml > snapshots/revisions.pre-rename.yaml`
- `gcloud iam service-accounts get-iam-policy $SA_EMAIL --format=yaml > snapshots/sa-iam.pre-rename.yaml`
- `gcloud secrets list --project=$GCP_PROJECT_ID --format=yaml > snapshots/secrets.pre-rename.yaml`

Costs nothing, gives a full forensic picture if anything goes sideways in Phase 4 or 5.

### S3 — Verify the `~DEFAULT_BRANCH` ruleset survives rename

Verified ruleset id `15886599` (active, applies to `~DEFAULT_BRANCH`, requires PR) — see `gh api repos/cubrox/cubrox/rulesets/15886599`. The `~DEFAULT_BRANCH` sentinel auto-follows GitHub's notion of the default branch, which the rename preserves. Should be unaffected. After Phase 2 step 12, re-run `gh api repos/cubrox/masterkey/rulesets` and confirm. (Architect's plan says "Auto-preserved by GitHub rename — verify after rename" in §2.1; this is fine, just calling out the specific verification command.)

### S4 — Smoke-test PR for Phase 4 dry-run

Architect's R1 mitigation suggests opening a throwaway PR after Phase 3 step 19 and flipping vars during it. Make this an explicit numbered step in Phase 3 (call it 19b). It's the only end-to-end verification of the preview-deploy + preview-cleanup paths against the new service and AR repo BEFORE any production traffic is involved. Mark the dry-run PR with a label so the cleanup step can be confirmed without auditing all open PRs.

### S5 — Update `.claude/PROJECT.md` to reflect Supabase, not Neon

Architect noted this as a "side-quest" (§2.7). Recommend folding into the Phase 1 PR — it's a 5-line edit, eliminates ongoing stale-context confusion for any agent that reads it, and it's already a small batch of doc-only edits.

### S6 — Document the new service URL in the Phase 1 PR body or a follow-up

After the cutover, anyone running `/doctor` or reading old reports/journals will see the old URL. The new URL needs to live in CLAUDE.md or a `docs/INFRA.md` so it's discoverable. Architect's plan covers `docs/LAUNCH-CHECKLIST.md` but doesn't pick a permanent home — recommend adding the production URL to CLAUDE.md's "Project Information" block.

---

## 4. Additional risks the architect missed

### R10 — Supabase GitHub App install scope can de-list the repo on rename

The Supabase GitHub App (configured for per-PR branching at `preview-deploy.yml:60-67, 130-159`) is installed at the GitHub-org level with a *selected-repos* allowlist (the typical install pattern). When `cubrox/cubrox` becomes `cubrox/masterkey`, GitHub usually preserves App installations across renames — but the App's internal repo allowlist may or may not auto-update depending on how Supabase tracks the repo (by `repository.id` vs by `owner/name`). If by ID, fine. If by name, the rename silently breaks Supabase branching for new PRs and the Phase 4 step 23 deploy could land with `DATABASE_URL` pointing at prod even for migration PRs.

**Mitigation:** Immediately after Phase 2 step 12, visit Supabase dashboard → Project Settings → Integrations → GitHub, confirm `cubrox/masterkey` appears in the allowlist. If it doesn't, re-install the App on the new repo name. Also: in the dry-run PR from S4, ensure a migration file is changed (e.g. add an empty `supabase/migrations/<timestamp>_rename_smoke.sql`) so the branch-creation path actually exercises.

### R11 — `tests/test_auth_login.py` lines 73,78 not a test of fixture data — it's a test of `_external_origin` behavior

Architect's §2.2 last row says to update the fixture URL from `pr-42---agile-flow-app-xyz.run.app` to `pr-42---masterkey-xyz.run.app`. That's correct cosmetic-wise. **But the test is asserting that the *exact* X-Forwarded-Host comes back as the redirect URL** — it has no semantic dependency on the service name; any string works. Renaming it is good for coherence but it's NOT a test of the new service name, and shouldn't be miscategorized. Mention this in §2.2's "Justification" column so a reviewer doesn't think the test is verifying the new naming.

### R12 — Old preview URL pattern in Supabase Auth redirect allowlist

Plan §3 Phase 5 step 29 removes the old production redirect URL from Supabase allowlist. But the allowlist *probably* also has `https://pr-*---agile-flow-app-*.run.app/auth/callback` (or equivalent) for preview-deploy callbacks. Verify against Supabase dashboard before Phase 5 step 29 and add the new `pr-*---masterkey-*.run.app` pattern in Phase 3 step 20 alongside the production URL. Otherwise preview PR auth breaks the moment the new service is in use.

### R13 — Cloud Run quota: services per region

Pre-creating `masterkey` in Phase 3 while `agile-flow-app` still exists means 2 services in the project. Default Cloud Run quota is ~1000 services per region per project, so this is fine — but worth mentioning that the dual-service window exists. NOT a real risk, just an "FYI for the next person reading the plan."

### R14 — `template-sync.sh` next run after rename — `.agile-flow-version`'s `upstream` URL

`.agile-flow-version` currently points at `https://github.com/vibeacademy/agile-flow` (the framework, not the GCP variant). Architect correctly says don't change this (§2.7). But `scripts/template-sync.sh:34` hardcodes `UPSTREAM_REPO="vibeacademy/gembaflow"` — and `scripts/doctor.sh:148` curls `vibeacademy/gembaflow/releases/latest`. These are upstream-synced scripts (NOT in `.agile-flow-overrides`), so don't edit. Just confirming the architect's "no change" claim is correct — the upstream framework is `vibeacademy/gembaflow` / `vibeacademy/agile-flow`, independent of `cubrox/*`. Bookkeeping note only.

### R15 — Workshop attendees who forked `cubrox/cubrox` (if any)

If anyone has forked the repo while it was named `cubrox/cubrox` and is doing independent work, their fork still references `cubrox/cubrox` as upstream. GitHub's auto-rename handles the redirect for 30 days, but a `git remote -v` on a forked clone will continue to read `cubrox/cubrox` until manually changed. Probably no one has forked, but worth checking via `gh api repos/cubrox/cubrox/forks --jq '.[].full_name'`. Not a blocker.

---

## 5. Confirmations (architect's claims I verified are correct)

- **C1.** `.github/workflows/deploy.yml:25-26`, `preview-deploy.yml:27-28`, `preview-cleanup.yml:20`, `synthetic-monitor.yml:46`, `rollback-production.yml:27` all read `vars.CLOUD_RUN_SERVICE` and `vars.ARTIFACT_REPO` with `||` fallback defaults. Setting repo vars IS sufficient; no workflow file edits needed for these five files. **Architect's §2.4 strategy is correct for these workflows.**
- **C2.** The upstream-template guard `if: github.repository != 'vibeacademy/agile-flow-gcp'` on six workflows (`deploy.yml:20`, `preview-deploy.yml:15,21`, `preview-cleanup.yml:14`, `synthetic-monitor.yml:41`, `baseline-migrations.yml:45`) does NOT need updating — `cubrox/masterkey` is correctly neither `vibeacademy/agile-flow-gcp` nor any other guarded slug.
- **C3.** Synthetic monitor resolves the URL dynamically via `gcloud run services describe ${SERVICE_NAME}` (verified at `synthetic-monitor.yml:104-107`) so it self-heals once `vars.CLOUD_RUN_SERVICE` is flipped. Architect's §2.3 row "Synthetic monitor URL" is correct.
- **C4.** Repo secrets (`GCP_*`, `PRODUCTION_DATABASE_URL`, `ANTHROPIC_API_KEY`, `SUPABASE_ACCESS_TOKEN`, `SUPABASE_DB_URL`) are repo-scoped and survive the rename. Architect's §2.1 secrets row is correct.
- **C5.** The branch protection ruleset (id 15886599, verified) uses `~DEFAULT_BRANCH` which auto-follows, so the rename preserves PR-required-merge protection. Architect's §2.1 ruleset row is correct.
- **C6.** Cloud Run does NOT support in-place service rename — verified by `gcloud run services --help` (no `rename` subcommand). Architect's §2.3 strategy ("destructive recreate") is the only available approach.
- **C7.** `--set-secrets=FOO=secret:latest` captures the secret value at deploy time and requires a redeploy to rotate. (`docs/devops-engineer.md:127-128`.) Architect's §2.3 "leave secret names alone" advice is correct — renaming would force a redeploy dance for zero benefit.
- **C8.** The Phase 0 step 2 service-spec snapshot is the right rollback artifact for the destructive recreate. Cloud Run revision history is per-service, so the new `masterkey` service starts with empty history — the snapshot lets you reconstruct the `agile-flow-app` revision config if needed.
- **C9.** Architect's R1 analysis (preview-deploy.yml comment update via marker-string match at line 307) is correct: `c.body?.startsWith('## Preview Deployment')` overwrites by marker. The preview URL change between cutover commits will be transparently reflected in the PR comment, not appended.
- **C10.** `pyproject.toml` name is `agile-flow-gcp` (verified line 2). Architect's "leave it" decision is correct — see B6 for the minor caveat.
- **C11.** `app/main.py` line 19 sets `FastAPI(title=...)`. Architect's rename target is correct.
- **C12.** Inventory of `CUBROX_TEST_SEED_ENABLED` usages in app source (`app/main.py:59,64`, `app/api/test_seed.py:32,41,66,71`) and tests (`tests/test_test_seed_guard.py:25,42,53,56`, `tests/a11y/playwright.config.ts:65`, `tests/a11y/fixtures/seed.ts:16`, `tests/a11y/README.md:16,38,40`) is exhaustive — verified via `rg`. **Plus the one missed in B1 above (`ci.yml:218,307,315`).**
- **C13.** Inventory of `window.cubroxLineCount` (`templates/pages/reading.html:49,60,73,79`, `tests/test_passage_close.py:221,228,234`) is exhaustive — verified.
- **C14.** Magic-link redirect URL is constructed dynamically from `X-Forwarded-Host` (`app/api/auth.py:51-63,94-95`), so the rename does NOT require code changes for redirect-URL handling. Only the Supabase Auth allowlist needs new URLs. Architect's §2.8 row is correct (and Phase 3 step 20 handles it).
- **C15.** No open PRs in the repo at review time (verified: `gh pr list --state open` returned `[]`). Architect's Phase 0 step 4 prerequisite is satisfied today.

---

## 6. Summary of required changes to the architect's plan

To move from `NEEDS_REVISION` to `ALIGNED`, the architect should:

1. **Add `ci.yml:218,307,315`** to the inventory in §2.4 and Phase 1 step 6 (B1).
2. **Rewrite R3 mitigation and add Phase 2 step 11.5** for the SA IAM-binding dual-write per Q2 + B2.
3. **Add B3's warning** to Phase 3 step 18 about not using `--set-secrets` for `DATABASE_URL`.
4. **Update §2.5 for `provision-gcp-project.sh` (lines 800, 1011) and `diagnose-cloudrun.sh` (line 35)** — both are in `.agile-flow-overrides`, safe to edit, and currently default to `agile-flow-app` (B4).
5. **Re-sequence Phase 4** per B7 to eliminate the var-flip-before-merge race.
6. **Capture the post-creation `masterkey` service URL** in Phase 3 step 19 and pin it in `docs/LAUNCH-CHECKLIST.md` per B5.
7. **Add R10 (Supabase GitHub App rename behavior) and R12 (preview-deploy redirect-URL pattern)** to the risk register.
8. **Adopt 30-day AR cleanup window** per Q4.
9. **Add explicit synthetic-monitor disable step** during cutover window per Q9.

After these changes, the plan is sound and ready to execute.

---

**Result:** Plan reviewed; verdict NEEDS_REVISION
Blocking concerns: 7 (B1-B7)
Non-blocking suggestions: 6 (S1-S6)
Additional risks identified: 6 (R10-R15)
Architect claims verified correct: 15 (C1-C15)
