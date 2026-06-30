# Refactor Plan: `cubrox` -> `masterkey`

**Author:** System Architect persona
**Date:** 2026-06-29
**Status:** REVISED (v3) — added Phase -1 (framework alignment) per user request 2026-06-29
**Scope locked by:** product owner (see task brief)

---

## Changelog

### v3 — 2026-06-29 — added Phase -1 (framework alignment) per user request 2026-06-29

- **Phase -1 added** to §3 BEFORE the existing Phase 0. Aligns the local fork with upstream's rebrand (`vibeacademy/agile-flow` → `vibeacademy/gembaflow`) and upgrades v1.3.0 → v1.5.0. Covers metadata-file renames (`.agile-flow-*` → `.gembaflow-*`), local `template-sync.sh` path edits, doc-string updates ("Agile Flow" → "Gemba Flow"), the v1.5.0 release notes' mandated **manual `curl` refresh of runtime-protected scripts**, the actual `/upgrade` run, and reconciliation of the overrides list against any upstream agent-file renames.
- **Reason this lands first:** upstream v1.5.0's `template-sync.sh` contains an early-exit one-time migration block that does `git mv .agile-flow-version .gembaflow-version` (and same for `.agile-flow-meta/`, `.agile-flow-overrides`) before doing the sync. The masterkey rename touches the SAME files (e.g., `E2-T5` edits paths governed by `.agile-flow-overrides`; `E2-T7` edits files listed in `.agile-flow-overrides`). If masterkey Phase 0 lands first, the next `/upgrade` would mid-rename our overrides file or fight the auto-migration, producing dual-state (`.agile-flow-overrides` AND `.gembaflow-overrides` both present until manual cleanup).
- **New rollback point RB-(-1)** documented.
- **Three Phase -1-specific risks added** to §4: R16 (upstream agent-file renames colliding with our overrides), R17 (`.gembaflow-config.example.json` is a new file expecting fork-specific values), R18 (the manual-curl refresh of `template-sync.sh` is itself a bootstrap-of-the-bootstrapper — if the curl fails or the wrong tag is fetched, the sync runs the old logic and leaves dual-state).
- Step renumbering: v2 used steps 1-40. v3 inserts steps numbered **(-1).1 through (-1).7** in the new Phase -1 (single hyphenated namespace, deliberately separate from the 1-40 numbering so no downstream cross-references break). Phase 0 onward unchanged.

### v2 — 2026-06-29 — incorporated DevOps review (`reports/refactor/02-devops-review.md`)

- **B1:** Added `.github/workflows/ci.yml:218,307,315` to §2.4 inventory and Phase 1 step 8. It inlines `CUBROX_TEST_SEED_ENABLED` literally — not a `vars.*` indirection — so a `vars` flip cannot cover it. Edit the file in the Phase 1 PR.
- **B2:** Rewrote R3 mitigation and added a dedicated Phase 2 step 16 (WIF dual-write). WIF is wired with a trivially-true attribute condition at the provider; the per-repo pin lives on the deployer SA's IAM policy as a `principalSet` member with BOTH `roles/iam.workloadIdentityUser` AND `roles/iam.serviceAccountTokenCreator`. The actual fix is to add a second SA IAM binding for `cubrox/masterkey` BEFORE the repo rename (step 17) and remove the old one in Phase 5 step 38. The "edit attribute condition" path I originally proposed is impossible.
- **B3:** Added explicit guard rail to Phase 3 step 23: do NOT use `--set-secrets` for `DATABASE_URL` or `ANTHROPIC_API_KEY` on the new `masterkey` service. Cloud Run's literal-vs-secret env-var type is sticky; switching mid-cutover would brick `deploy.yml`. Added as new risk R13.
- **B4:** `scripts/provision-gcp-project.sh` lines 800 + 1011 and `scripts/diagnose-cloudrun.sh` line 35 are now in scope. Both files are listed in `.agile-flow-overrides` (verified), so editing them does not fight `template-sync.sh`. Updated §2.5; folded into Phase 1 step 9.
- **B5:** Phase 3 step 24 now ends with capturing the new service URL via `gcloud run services describe ... --format='value(status.url)'` and pinning it into `docs/LAUNCH-CHECKLIST.md` line 10 (amend the still-open Phase 1 PR; or follow-up doc PR if Phase 1 has already merged).
- **B6:** R6 reworded to mention the real consequence — `pyproject.toml:name` is referenced by `[tool.*]` config blocks and `uv build` wheel filenames — so a future renamer must audit those. We still are not renaming today.
- **B7:** Re-sequenced Phase 4 to eliminate the var-flip-before-merge race. New order (steps 27-34): (1) merge Phase 1 PR with vars still pointing at the OLD service, which deploys the rename code to `agile-flow-app` and proves the rename is a live no-op; (2) verify health on the old service; (3) flip `vars.CLOUD_RUN_SERVICE` and `vars.ARTIFACT_REPO`; (4) push a trivial commit to `main` to trigger `deploy.yml` against the new service.
- **R10 added:** Supabase GitHub App may track the repo by `owner/name` vs `repository.id`. Verify the App allowlist still contains `cubrox/masterkey` post-rename (Phase 2 step 17).
- **R12 added:** Supabase Auth allowlist almost certainly has a preview-PR pattern (`https://pr-*---agile-flow-app-*.run.app/auth/callback`). Add the new `pr-*---masterkey-*.run.app` pattern in Phase 3 step 26.
- **R13 added:** Cloud Run env-var type stickiness (from B3).
- **R14 added:** Cloud Run services-per-region quota during the dual-service window (FYI; not a real risk, default quota is ~1000/region).
- **R15 added:** Fork-redirect breakage for any external `cubrox/cubrox` forks (probably none; verify via `gh api repos/cubrox/cubrox/forks` in Phase 0 step 6).
- **Q1, Q2, Q3, Q4, Q5, Q6, Q7, Q8, Q9, Q10:** All ten open questions resolved per DevOps's answers; moved from "Open questions" to "Resolved decisions" in §5.
- **S1 deferred** as a separate follow-up; **S5** (`.claude/PROJECT.md` Supabase fix) folded into the Phase 1 PR as a 5-line cosmetic; **S6** folded into the §2.6 `CLAUDE.md` row.
- **S2 applied:** Phase 0 step 2 now captures revisions, SA IAM policy, and secrets list in addition to the service spec.
- **S3, S4 applied:** S3 verification command added under §2.1 and Phase 2 step 17; S4 dry-run PR is now explicit Phase 3 step 25.
- **C11, C12, C13, C14, C15 etc.:** confirmations folded silently — claims I made correctly are kept as-is.

**Step renumbering note:** v1 used steps 1-31 across 5 phases. v2 inserts (a) Phase 0 step 4 (Cloud Logging enumeration), (b) Phase 0 step 6 (forks check), (c) Phase 1 step 11 (.claude/PROJECT.md fix), (d) Phase 1 step 13 (synthetic-monitor disable), (e) Phase 2 step 16 (WIF dual-write), (f) Phase 3 step 25 (dry-run PR), (g) Phase 4 split into steps 27-34, (h) Phase 5 step 38 (WIF prune). v2 uses steps 1-40 sequentially. All §2/§4/§5 cross-references in this revision use the new numbering.

---

## 1. Executive summary

- **The rename is a codebase / infra identifier change, not a brand change.** The user-facing product is already "Master Key" in `templates/home.html`, `passages_new.html`, `reading.html`, and `tests/test_home.py`. The string "Cubrox" only appears in technical artifacts: repo slug, package metadata, env-var prefixes, browser globals, Supabase project-id (local), test-seed package name, and developer docs. No marketing copy or sign-in flow needs to change.
- **Two distinct namespaces collapse into one after this work.** Today the repo is `cubrox/cubrox` on GitHub (confirmed via `git remote`), but the project board is still on the legacy `vibeacademy` org (`orgs/vibeacademy/projects/29`). After the rename, both will live under `cubrox/*` — repo at `cubrox/masterkey`, new board at `orgs/cubrox/projects/<new-id>` with all tickets migrated.
- **The Cloud Run service is currently named `agile-flow-app`, not `cubrox`.** This is a holdover from the upstream framework defaults (`vars.CLOUD_RUN_SERVICE` was never overridden — `docs/LAUNCH-CHECKLIST.md` line 10 shows the live URL `agile-flow-app-heo5ry7rua-uc.a.run.app`). The rename is therefore *also* the moment we finally give this service a project-specific name. **This is a destructive Cloud Run service rename and the highest-risk part of the plan** (see Risk Register §4).
- **Ephemeral preview deploys are the most fragile surface.** They depend on a per-service revision tag (`pr-N`) and a comment on the PR. The rename must hit Cloud Run service name + Artifact Registry repo + GitHub Actions `vars` atomically with the repo rename, or in-flight PRs will start failing.
- **Framework artifacts (Agile Flow) stay named as-is.** `pyproject.toml`'s `name = "agile-flow-gcp"` is the framework template name, not the product. `template-sync.sh` and the upstream URL in `.agile-flow-version` (`vibeacademy/agile-flow`) point at the *upstream framework*, which is unrelated to this product rename. Touching them would break upstream sync. **However**, two `.agile-flow-overrides`-listed scripts (`provision-gcp-project.sh`, `diagnose-cloudrun.sh`) DO need edits — they hardcode `agile-flow-app` as the default service name (B4).
- **WIF authentication is the highest-leverage "stuck in the middle" failure mode** (B2). The repo pin lives on the deployer SA's IAM policy as a `principalSet` member, not on the WIF provider's attribute condition. Phase 2 step 16 dual-writes the binding for the new repo name BEFORE the rename so no GCP-touching workflow ever sees an unauthorized request.

---

## 2. Inventory

### 2.1 GitHub repo + org

| Item | What changes | Notes |
|------|--------------|-------|
| Repo slug | `cubrox/cubrox` -> `cubrox/masterkey` | `gh repo rename masterkey` from a clone on the default branch. Org stays `cubrox`. |
| Local git remote | `git@github.com:cubrox/cubrox.git` -> `git@github.com:cubrox/masterkey.git` | `git remote set-url origin` after the rename. GitHub serves a 30-day HTTP redirect, but git's SSH transport doesn't honor it — relying on the redirect silently breaks `git push` on every developer machine. |
| Working-tree directory | Optional: `/Users/teddykim/projects/cubrox/cubrox` -> `/Users/teddykim/projects/cubrox/masterkey` | Cosmetic only; does NOT affect git. `cd` paths in CLAUDE/agent context will need to be re-read if the dir is moved. |
| GitHub Actions secrets | No rename needed | `GCP_PROJECT_ID`, `GCP_SERVICE_ACCOUNT`, `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SA_KEY`, `PRODUCTION_DATABASE_URL`, `ANTHROPIC_API_KEY`, `SUPABASE_ACCESS_TOKEN`, `SUPABASE_DB_URL` are repo-scoped, not name-scoped. They follow the repo through the rename. |
| Workload Identity Federation binding | **Dual-write before rename, prune after** | The WIF provider's attribute condition is trivially true (`assertion.repository != ''`, per `provision-gcp-project.sh:439`). The repo pin lives on the deployer SA's IAM policy as `principalSet://.../attribute.repository/cubrox/cubrox` with BOTH `roles/iam.workloadIdentityUser` AND `roles/iam.serviceAccountTokenCreator` (per `provision-gcp-project.sh:465-474`). Phase 2 step 16 adds a parallel binding for `cubrox/masterkey` BEFORE the rename. The old binding is removed in Phase 5 step 38. |
| GitHub Pages / repo description / topics | Cosmetic | None configured; nothing to change. |
| Branch protection ruleset (id `15886599`) | Auto-preserved by GitHub rename | Uses `~DEFAULT_BRANCH` sentinel (verified). After Phase 2 step 17, re-run `gh api repos/cubrox/masterkey/rulesets` to confirm the ruleset still applies. |
| GitHub Webhook / App installations | Auto-preserved by GitHub rename | The Supabase GitHub App (for per-PR branching) is installed at the org level and watches selected repos — verify `cubrox/masterkey` is still in the repo allowlist after the rename (see R10). |
| Project board (legacy) | `https://github.com/orgs/vibeacademy/projects/29` -> closed after migration | Source-of-truth ticket data. Read all items (open + closed) before tearing down. |
| Project board (new) | Create `https://github.com/orgs/cubrox/projects/<n>` | Mirror columns: Backlog / Ready / In Progress / In Review / Done. Re-add automation for status moves. |
| Ticket migration | All issues + PRs cross-linked to board | Use `gh api graphql` with `addProjectV2ItemById`. Closed tickets count toward the history; do not omit them. |
| External forks (FYI) | Confirm none exist | `gh api repos/cubrox/cubrox/forks --jq '.[].full_name'`. If any, warn the fork owners that their `origin` URL will redirect for 30 days then break. See R15. |

### 2.2 Code / application

| File | Identifier | Change | Justification |
|------|------------|--------|---------------|
| `pyproject.toml` | `name = "agile-flow-gcp"` | **NO change** | This is the framework starter name from the upstream template. Renaming it would diverge from `vibeacademy/agile-flow-gcp` and break `template-sync.sh` (which diffs files against upstream releases). The Python package on disk is `app/`, not `cubrox/`, so the project name string only appears in distribution metadata — and we don't publish to PyPI. **Leave it.** See R6 for the audit-debt note about `[tool.*]` config blocks if a future maintainer ever does rename it. |
| `app/main.py:19` | `FastAPI(title="Agile Flow GCP")` | -> `FastAPI(title="Master Key")` | This title surfaces in `/docs` (OpenAPI) and in error pages. "Master Key" matches the public brand already used in templates. |
| `app/main.py:59-64` | `CUBROX_TEST_SEED_ENABLED` env var | -> `MASTERKEY_TEST_SEED_ENABLED` | Codebase identifier. Coordinated change with `app/api/test_seed.py`, `tests/test_test_seed_guard.py`, `tests/a11y/playwright.config.ts`, **`.github/workflows/ci.yml:218,307,315`** (see §2.4 — B1), and the CI workflow. |
| `app/api/test_seed.py:32,41,66,71` | Same env var | Same | Module-level guard. |
| `app/api/home.py:5` | Docstring "Cubrox landing page" | -> "Master Key landing page" | Doc comment only. |
| `app/services/ingestion/pdf.py:5` | Docstring "...onto Cubrox" | -> "...onto Master Key" | Doc comment only. |
| `app/scripts/metric.py:30` | `prog="cubrox-metric"` | -> `prog="masterkey-metric"` | CLI program name shown in `--help`. |
| `templates/pages/reading.html:49,60,73,79` | `window.cubroxLineCount` | -> `window.masterkeyLineCount` | Browser global. Must be changed in lock-step with `tests/test_passage_close.py:221,228,234`. |
| `tests/test_passage_close.py:221,228,234` | `window.cubroxLineCount` assertions | Same | Test pins the global name. |
| `tests/test_test_seed_guard.py:25,42,53,56` | `CUBROX_TEST_SEED_ENABLED` | -> `MASTERKEY_TEST_SEED_ENABLED` | Test of the env-var guard. |
| `tests/test_seed_route.py:5` | Docstring | Update env-var name | Doc-only. |
| `tests/test_home.py:97` | "'Cubrox' remains the internal codebase identifier" | -> "'Master Key' is both internal and public; 'masterkey' is the codebase identifier" | Doc comment in test (intent has flipped post-rename). |
| `tests/a11y/package.json:2` | `"name": "cubrox-a11y-tests"` | -> `"name": "masterkey-a11y-tests"` | npm package name (local-only; not published). |
| `tests/a11y/package-lock.json:2,7` | Same | Same | Regenerated by `npm install`. |
| `tests/a11y/README.md:1,16,38,40,74` | "Cubrox accessibility tests" + env var | Update doc + env var | Doc + env-var name in run instructions. |
| `tests/a11y/playwright.config.ts:65` | `CUBROX_TEST_SEED_ENABLED: "true"` | -> `MASTERKEY_TEST_SEED_ENABLED: "true"` | Sets the env on the FastAPI subprocess. |
| `tests/a11y/fixtures/seed.ts:16` | Doc comment | Update env-var name | Doc-only. |
| `tests/test_auth_login.py:73,78` | `pr-42---agile-flow-app-xyz.run.app` | -> `pr-42---masterkey-xyz.run.app` | Test fixture; the test asserts that `_external_origin` returns the exact `X-Forwarded-Host` it received — the string itself has no semantic dependency on the service name (per R11). Rename for **coherence** only; it is not a test of the new naming. |

### 2.3 Infrastructure (GCP)

| Resource | Today | After | Strategy |
|----------|-------|-------|----------|
| Cloud Run service | `agile-flow-app` | `masterkey` | **Destructive recreate** — Cloud Run doesn't support in-place rename. See Order of Operations §3.4. |
| Artifact Registry repo | `agile-flow` | `masterkey` | New AR repo (cheap, no data to migrate). Old repo stays for **30 days** post-cutover (per resolved Q4) before cleanup. |
| Container image tags | `us-central1-docker.pkg.dev/$PROJECT/agile-flow/agile-flow-app:<sha>` | `us-central1-docker.pkg.dev/$PROJECT/masterkey/masterkey:<sha>` | First post-rename `deploy.yml` push creates the new tag. |
| GCP project ID | (kept) | (unchanged) | Per locked scope. |
| Supabase project ref | `gnswmcgaztcxslirulwm` | (unchanged) | Per locked scope. No data migration. |
| Service Account | (kept) | (unchanged) | Same SA continues to run the new Cloud Run service. |
| WIF binding on deployer SA | `principalSet://.../cubrox/cubrox` with `workloadIdentityUser` + `serviceAccountTokenCreator` | **Add** `principalSet://.../cubrox/masterkey` with both roles BEFORE rename; **remove** the old binding in Phase 5 | Per-repo binding kept narrow (resolved Q5 — no org-wide widening). |
| Secret Manager secrets | `supabase-url`, `supabase-anon-key`, `supabase-service-key` | (unchanged names) | These names don't contain "cubrox"; they're already generic. Renaming costs a coordinated 4-step dance for zero functional benefit (resolved Q3). **Leave as-is.** |
| Cloud Logging filter / Error Reporting | Filters on `resource.labels.service_name="agile-flow-app"` | Update saved queries to `="masterkey"` | Enumerate via `gcloud logging metrics list`, `gcloud alpha monitoring policies list`, `gcloud monitoring dashboards list` before Phase 4 (resolved Q7). Most likely returns empty per ADR-004 (Sentry deferred, no custom dashboards) — but verify; alerts that don't fire after the rename look like silence. Error Reporting auto-groups by stack trace, unaffected. |
| Cloud Monitoring alerts | (enumerate per Q7) | (update if any exist) | Same source as above. |
| Synthetic monitor URL | Resolves dynamically via `gcloud run services describe` (see `synthetic-monitor.yml:104-107`) | Auto-follows the new service name once `vars.CLOUD_RUN_SERVICE` is updated | No code change needed; the indirection saves us. |

### 2.4 CI/CD (GitHub Actions)

Most workflows read `vars.CLOUD_RUN_SERVICE` and `vars.ARTIFACT_REPO` with framework defaults — for those, **the fix is to set the repo variables, not to edit the workflow files** (avoids `template-sync.sh` conflict). The exception is `ci.yml`, which inlines `CUBROX_TEST_SEED_ENABLED` literally (B1) and must be edited.

| Workflow file | Today | Change |
|---------------|-------|--------|
| `.github/workflows/ci.yml:218,307,315` | Comments + `env: CUBROX_TEST_SEED_ENABLED: 'true'` inline literal | **Edit file directly in Phase 1 PR.** Rename to `MASTERKEY_TEST_SEED_ENABLED`. This is NOT a `vars.*` reference — a `vars` flip cannot reach it. If left unchanged, the a11y job's uvicorn subprocess receives the old env name, the test-seed router never mounts, every Playwright test 404s on `/test/seed`, and Phase 1 CI goes red. (B1) |
| `.github/workflows/deploy.yml:25-26` | `ARTIFACT_REPO: ${{ vars.ARTIFACT_REPO OR 'agile-flow' }}` / `SERVICE_NAME: ${{ vars.CLOUD_RUN_SERVICE OR 'agile-flow-app' }}` (OR = literal `&#124;&#124;`) | **No file edit.** Set GitHub repo `vars.CLOUD_RUN_SERVICE = masterkey` and `vars.ARTIFACT_REPO = masterkey` so the default is bypassed. |
| `.github/workflows/preview-deploy.yml:27-28` | Same pattern | Same — repo `vars` only. |
| `.github/workflows/preview-cleanup.yml:20` | `SERVICE_NAME: ${{ vars.CLOUD_RUN_SERVICE \|\| 'agile-flow-app' }}` | Same — repo `vars` only. |
| `.github/workflows/synthetic-monitor.yml:46` | Same | Same. **Plus** disable schedule for the cutover window per resolved Q9 (comment out `schedule:` block in Phase 1 step 13; restore in Phase 4 step 32 via a small follow-up PR). |
| `.github/workflows/rollback-production.yml:27` | Same | Same. |
| `.github/workflows/*.yml` `if: github.repository != 'vibeacademy/agile-flow-gcp'` guards | Six workflows have this guard | **No change.** The guard prevents deploys on the upstream framework template; our repo is neither `vibeacademy/agile-flow-gcp` nor will it be `cubrox/masterkey`. The guard keeps doing its job. |
| `.github/workflows/baseline-migrations.yml` | One-time workflow | Same upstream-guard pattern; no change needed. |
| `.github/workflows/template-sync.yml` (if present) | Pulls from upstream framework | No change. |

### 2.5 Scripts

| Script | Item | Change |
|--------|------|--------|
| `scripts/smoke_auth.py:52` | Docstring sample URL `cubrox-xxxxx-uc.a.run.app` | -> `masterkey-xxxxx-uc.a.run.app` (doc only) |
| `scripts/smoke_auth.py:86` | `SMOKE_EMAIL_DOMAIN = "smoke.cubrox.test"` | -> `"smoke.masterkey.test"` (used only as a leak-detection tag in Supabase user lists; cosmetic but coherent) |
| `scripts/diagnose-cloudrun.sh:35` (also doc-comment line 23) | `SERVICE="${CLOUD_RUN_SERVICE:-agile-flow-app}"` | -> `SERVICE="${CLOUD_RUN_SERVICE:-masterkey}"` (also update line 23 comment). **In scope per B4** — this script IS listed in `.agile-flow-overrides` (verified), so editing does not fight `template-sync.sh`. New workshop operators running `/diagnose-cloudrun` would otherwise hit the wrong default. |
| `scripts/provision-gcp-project.sh:800` | `SERVICE_NAME="${CLOUD_RUN_SERVICE:-agile-flow-app}"` | -> `SERVICE_NAME="${CLOUD_RUN_SERVICE:-masterkey}"`. **In scope per B4** — file IS in `.agile-flow-overrides` (verified). New GCP project provisioning would otherwise create a service named `agile-flow-app` that doesn't match `vars.CLOUD_RUN_SERVICE=masterkey`, orphaning the first deploy. |
| `scripts/provision-gcp-project.sh:1011` | `echo "   CLOUD_RUN_SERVICE      = agile-flow-app"` | -> `echo "   CLOUD_RUN_SERVICE      = masterkey"`. **In scope per B4.** This is the post-script "next steps" output; an operator following its instructions would otherwise set the wrong var name. |
| `scripts/doctor.sh` | No `cubrox` references found | No change |
| `scripts/template-sync.sh` | Sync from upstream `vibeacademy/gembaflow` | No change — upstream framework reference, not project-specific (R14). |

### 2.6 Docs

| File | Change |
|------|--------|
| `CLAUDE.md:164-166,175,195` | `Project Name: Cubrox` -> `Project Name: Master Key (codebase: masterkey)`. Repo URL -> `https://github.com/cubrox/masterkey`. Project Board URL -> new `cubrox` org board URL. `Organization: vibeacademy` -> `Organization: cubrox`. `docker build -t agile-flow-app .` -> `docker build -t masterkey .`. **Also add the new production Cloud Run URL** here once known (per S6), so `/doctor` and future agent sessions discover it without re-reading old runbooks. |
| `docs/PRODUCT-REQUIREMENTS.md:5` | `Name: Cubrox (working name — TBD)` -> `Name: Master Key (public) / masterkey (codebase)` |
| `docs/PRODUCT-ROADMAP.md:107` | Change-log row attributing initial roadmap to "cubrox" — doc only, leave as historical record OR replace with "masterkey". Historical attribution preferred; keep as `cubrox` (footnote: "former internal codename"). |
| `docs/TECHNICAL-ARCHITECTURE.md:5,518` | "Cubrox is a server-rendered..." -> "Master Key is...". ADR-006 line 518 "cubrox owned and had to maintain" -> "the project owned and had to maintain" (or leave as historical narrative — ADRs are immutable post-acceptance per the doc's own convention; choice: write a tiny **ADR-007 "Rename to Master Key / masterkey"** and leave ADR-006 untouched). |
| `docs/LAUNCH-CHECKLIST.md:10,12,45-46,51` | Production URL `agile-flow-app-heo5ry7rua-uc.a.run.app` -> new `masterkey-*.run.app` URL. **The new hash is unknowable until Phase 3 step 23 actually creates the service** (per B5). Phase 3 step 24 captures it and pins it here. Repo + board URLs updated. |
| `docs/PATTERN-LIBRARY.md:1368` | "Cubrox chose (1)" -> "We chose (1)" or "Master Key chose (1)" — purely narrative. |
| `docs/PATTERN-LIBRARY.md:1098,1105,1171,1187,1213` | Example `agile-flow-app` -> `masterkey` in code snippets. Cosmetic (these are illustrative). |
| `docs/PLATFORM-GUIDE.md:76,349,699,861,897,902,904` | Same — `agile-flow-app` -> `masterkey`. **But this is an upstream-synced doc** — likely fights `template-sync.sh`. Decision: leave the upstream version intact, append a project-specific overrides note OR add `docs/PLATFORM-GUIDE.md` to `.agile-flow-overrides` and edit freely. |
| `docs/CI-CD-GUIDE.md:99` | Same — same decision tree as above. |
| `docs/FAQ.md` | (verify) — likely no rename needed |
| `docs/GETTING-STARTED.md` | (verify) — upstream framework doc; likely no rename |
| `docs/MEMORY-ARCHITECTURE.md` | (verify) |
| `README.md` | (verify; mostly framework boilerplate from `vibeacademy/agile-flow-gcp`) |
| `CHANGELOG.md` | Add entry: "Renamed codebase identifier `cubrox` -> `masterkey`. No user-facing change; public product name remains `Master Key`." Used as the trivial commit that triggers the post-cutover `deploy.yml` run (Phase 4 step 30). |
| `reports/session-journals/2026-05-25..2026-06-05.md` | **No change** — session journals are historical record. |

### 2.7 Agent + framework artifacts (Agile Flow)

| Item | Change |
|------|--------|
| `.agile-flow-version` | `upstream: https://github.com/vibeacademy/agile-flow` — **no change** (correct upstream). |
| `.agile-flow-overrides` | Add `docs/PLATFORM-GUIDE.md`, `docs/CI-CD-GUIDE.md` if we choose to edit those (see §2.6). |
| `.agile-flow-meta/version` | No change. |
| `.claude/PROJECT.md` | This is project-specific (not synced). Lines 7-9 reference Neon, but the project is on Supabase — **already stale**. Per S5, fold the 5-line Supabase fix into the Phase 1 PR alongside the rename — it removes ongoing stale-context confusion for every agent that reads this file. |
| `.claude/agents/github-ticket-worker.md:33` | "Product: Cubrox" -> "Product: Master Key (codebase: masterkey)". Listed in `.agile-flow-overrides` — safe to edit. |
| `.claude/agents/system-architect.md` | Verify (system architect persona is overridden; safe to edit). The product-specific bounded-context section already says "Reading Surface", not "Cubrox" — likely no edit. |
| `.claude/agents/devops-engineer.md:72,307-324` | Examples reference `agile-flow-app`. Listed in `.agile-flow-overrides` — safe to edit to `masterkey`. |
| `.claude/commands/eli5.md:18-19` | `vibeacademy/cubrox` prototype reference — leave as historical attribution (the eli5 command IS from upstream `agile-flow` / `gembaflow`, this is its provenance). |
| Other `.claude/agents/*.md`, `.claude/commands/*.md`, `.claude/skills/*.md` | Spot-check; upstream-synced; do not edit unless project-specific. |

### 2.8 Supabase

| Item | Change |
|------|--------|
| Supabase project (remote, `gnswmcgaztcxslirulwm`) | **No change** to project ref, schema, or data. |
| `supabase/config.toml:9` | `project_id = "cubrox"` -> `project_id = "masterkey"`. This is the **local Supabase CLI workspace identifier** — affects only `supabase start` / local Docker container naming. No impact on the remote. |
| `supabase/config.toml:5` | Comment `Org: vibeacademy` -> `Org: cubrox` (or whatever the Supabase org actually is — verify in dashboard; not necessarily a GitHub-org match). |
| Supabase Auth redirect allowlist (production URL) | **Add** `https://masterkey-<hash>-uc.a.run.app/auth/callback` (Phase 3 step 26) alongside the existing `agile-flow-app-*` URL. Remove the old one in Phase 5 step 37 only after stability is confirmed. |
| Supabase Auth redirect allowlist (preview-PR URL pattern) | **R12.** Almost certainly contains a `https://pr-*---agile-flow-app-*.run.app/auth/callback` wildcard for preview-deploy callbacks. Add `https://pr-*---masterkey-*.run.app/auth/callback` in Phase 3 step 26 alongside the production URL. Verify against the Supabase dashboard before Phase 5 step 37 prunes the old pattern. |
| Supabase GitHub App config | **R10.** Verify the App is installed on `cubrox/masterkey` post-rename. GitHub usually preserves App installs, but the Supabase App's internal repo allowlist may track by `owner/name` (in which case the rename silently breaks per-PR branching) or by `repository.id` (in which case it auto-updates). Visit Supabase dashboard → Project Settings → Integrations → GitHub immediately after Phase 2 step 17 and confirm `cubrox/masterkey` appears. If it doesn't, re-install the App on the new repo name. Also exercise the path: include a `supabase/migrations/<timestamp>_rename_smoke.sql` empty file in the Phase 3 step 25 dry-run PR so branch-creation actually runs. |
| Supabase magic-link email template | No change — already content-neutral re. service name. |

### 2.9 Memory MCP

The Memory MCP graph for the current session was empty when queried (`mcp__memory__search_nodes("cubrox")` returned `{entities: [], relations: []}`). Other agent sessions may have entities keyed on "Cubrox", "Cubrox PRD", etc. **Not in immediate scope** — flag for post-rename audit:
- Run `mcp__memory__search_nodes("cubrox")` across active sessions.
- Rename entity names, or create alias relations from the old name to the new one.

---

## 3. Order of operations

Numbered, with explicit rollback points (RB-N) and "what's safe to interleave" annotations.

### Phase -1: Framework alignment (gembaflow v1.5.0)

This phase exists because upstream renamed `vibeacademy/agile-flow` → `vibeacademy/gembaflow` and shipped v1.5.0 while we sat on v1.3.0. The local fork still has `.agile-flow-*` metadata files and CLAUDE.md / UPSTREAM.md / VERSIONING.md still say "Agile Flow". **This phase lands before the existing Phase 0** because the masterkey rename (Phases 0-5 below) touches the same `.agile-flow-overrides` file and the same agent persona files that the v1.5.0 sync auto-migrates. Sequencing matters: do the framework alignment first, get a clean baseline at v1.5.0 with `.gembaflow-*` dotfiles, THEN start the masterkey rename. The reverse order produces dual-state and merge-conflict pain.

#### What changes

1. Metadata file renames (auto-migrated by upstream's `template-sync.sh` v1.5.0 lines 47-58):
   - `.agile-flow-version` → `.gembaflow-version` (JSON; `upstream` field still legitimately points at `vibeacademy/agile-flow` in upstream's own copy, so we leave that field alone — the actual sync URL is hard-coded in `template-sync.sh` line 36 as `vibeacademy/gembaflow` with `FALLBACK_REPO=vibeacademy/agile-flow` per line 41)
   - `.agile-flow-meta/` → `.gembaflow-meta/` (directory containing `version` file)
   - `.agile-flow-overrides` → `.gembaflow-overrides` (text file listing fork-customized paths)
2. New file shipped: `.gembaflow-config.example.json`. Per upstream contents (4 fields: `org`, `board.id`, `bot.worker`, `bot.reviewer`), this is the **example/template** consumed by `scripts/substitute-config-placeholders.sh` to populate `{{org}} / {{board.id}} / {{bot.worker}} / {{bot.reviewer}}` placeholders in `.claude/commands/work-ticket.md` and `.claude/commands/drain.md`. We **leave the `.example.json` in place as shipped** and additionally create `.gembaflow-config.json` with our actual values (`org=cubrox` for now — to be flipped to whatever the post-Phase-2 owner is, `board.id=29` for now, `bot.worker`/`bot.reviewer` per solo-mode = repo owner). The example file is not consumed at runtime; the unsuffixed one is. This avoids triggering the bootstrap-time substitution with placeholder values still in place (which would corrupt the slash-command specs).
3. Local `scripts/template-sync.sh` path edits — strictly pre-sync bridge, lines 35-36 and 422:
   - Line 35: `VERSION_FILE=".agile-flow-version"` → `".gembaflow-version"`
   - Line 36: `OVERRIDES_FILE=".agile-flow-overrides"` → `".gembaflow-overrides"`
   - Line 422: `mkdir -p .agile-flow-meta` → `mkdir -p .gembaflow-meta`
   - Line 423: same — `.agile-flow-meta/version` → `.gembaflow-meta/version`
   - Line 424: same — `git add .agile-flow-meta/version` → `git add .gembaflow-meta/version`
   - Line 2 / 5 / 6: comments — update for honesty
   - Note: line 34 already correctly says `vibeacademy/gembaflow` (the only line that was forward-fixed when somebody started this work earlier).
   - **`scripts/template-sync.sh` is in `syncDirectories` so the upstream v1.5.0 version will overwrite our local edits on the actual sync run.** That's fine — the local edits are bridge-only, intended to let our CURRENT run of the script (with dotfiles still named `.agile-flow-*`) read the correct paths long enough to download the v1.5.0 tarball, after which the post-loop self-heal block (#371 / #486 per release notes) overwrites `template-sync.sh` with the upstream v1.5.0 version. The local edits' lifetime is exactly one `/upgrade` invocation.
4. Doc string updates (these are NOT in `syncDirectories` for most files — local-only):
   - `CLAUDE.md` line 2 (template heading): "Agile Flow - Claude Code Project Template" → "Gemba Flow - Claude Code Project Template"
   - `CLAUDE.md` lines 10, 73, 80, 81 (`AGILE_FLOW_*` env-var names — these env vars MAY have been renamed by upstream v1.4 or v1.5; check the v1.5.0 `bootstrap-workflow.md` and `ensure-github-account.sh` before flipping. If upstream still reads `AGILE_FLOW_*` env names, our doc must continue to call them that even though the project is now "Gemba Flow". This is a deliberate cross-check during step (-1).5 review.)
   - `UPSTREAM.md`: every "Agile Flow" → "Gemba Flow"; every `vibeacademy/agile-flow` URL → `vibeacademy/gembaflow`
   - `VERSIONING.md`: same
5. Version bump: `.gembaflow-version` `version` field flips from `1.3.0` → `1.5.0` (the sync script's normal post-sync logic does this; we don't hand-edit).
6. New `syncDirectories` entries per upstream v1.5.0's own `.gembaflow-version`: `.claude/modes` and `features`. The first sync pulls these as new directories. Verify nothing in the fork would conflict.
7. Per v1.5.0 release notes' "Migration notes" section: branch-protection ruleset must add `json-validate` as a required status check (was split off from `version-parity` in #471). This is a Phase -1 deliverable: update GitHub branch-protection rule on `main` to require both `version-parity` AND `json-validate`. **Note:** this is mechanically the SAME ruleset (id 15886599) the masterkey Phase 2 step 17 verifies — touching it in Phase -1 is harmless; Phase 2's re-verify still succeeds.

#### Order of operations within Phase -1

Order matters because the v1.5.0 release notes describe a chicken-and-egg problem: the new `template-sync.sh` contains the auto-migration AND the post-sync self-heal, but our v1.3.0 fork has neither. The release notes' "Propagation note" is the canonical sequence:

(-1).1 **Snapshot current state.** `cp .agile-flow-version /tmp/.agile-flow-version.pre-rebrand`; same for `.agile-flow-overrides`, `.agile-flow-meta/version`. Capture `git rev-parse HEAD` as the pre-Phase-(-1) SHA for RB-(-1) rollback. Commit any pending working-tree changes to a wip branch.
(-1).2 **Branch:** `feature/framework-align-gembaflow-v1.5.0`.
(-1).3 **Bridge-edit local `scripts/template-sync.sh`** (per "What changes" item 3). This lets the OLD script (which has the OLD VERSION_FILE/OVERRIDES_FILE paths hardcoded as constants but ALSO has the line-34 upstream URL already correct) find the locally-still-`.agile-flow-*`-named files long enough to do the version comparison and download the v1.5.0 tarball. Test: `bash scripts/template-sync.sh --dry-run` (if `--dry-run` flag exists in our v1.3.0; if not, skip — the rename is verified at step (-1).5 after the actual sync runs).
(-1).4 **Manual curl-refresh of runtime-protected scripts** per the v1.5.0 release notes (this is the keystone — our v1.3.0 doesn't have the self-heal so the upgrade pipeline can't deliver itself):
```bash
curl -fsSL "https://raw.githubusercontent.com/vibeacademy/gembaflow/v1.5.0/scripts/template-sync.sh" -o scripts/template-sync.sh
curl -fsSL "https://raw.githubusercontent.com/vibeacademy/gembaflow/v1.5.0/scripts/lib/overrides.sh" -o scripts/lib/overrides.sh
chmod +x scripts/template-sync.sh
grep -c "Self-healing post-sync refresh" scripts/template-sync.sh   # MUST return 1
```
The grep is the v1.5.0 release-notes' own verification gate. If it returns 0, abort and re-curl.
(-1).5 **Run the sync.** Execute `bash scripts/template-sync.sh`. This now-v1.5.0 script:
- Runs the early one-time migration block (lines 47-58): `git mv .agile-flow-version .gembaflow-version`, same for `.agile-flow-meta/`, same for `.agile-flow-overrides`. Local edits done in (-1).3 are now irrelevant; the file paths in the new script point at `.gembaflow-*` natively.
- Reads `.gembaflow-version`, sees `version=1.3.0` and upstream latest is `v1.5.0`, creates branch `gembaflow-sync/v1.5.0`, downloads the tarball, copies syncDirectories.
- Post-sync loop: re-copies `scripts/template-sync.sh` and `scripts/lib/overrides.sh` from the tarball if they differ from upstream AND not in overrides. (Idempotent on this run because we already curl'd the latest in step (-1).4.)
- Updates `.gembaflow-version` `version` field to `1.5.0`.
- The script opens a PR (or stages a branch — depends on environment; check terminal output).
(-1).6 **Reconcile the overrides list.** The auto-migration moves `.agile-flow-overrides` to `.gembaflow-overrides` byte-for-byte (it's `git mv`, not a content-transform). Walk the file: every path still listed must exist post-sync. Specifically:
- The 5 agent/command paths (`.claude/agents/github-ticket-worker.md`, `.claude/agents/devops-engineer.md`, `.claude/agents/system-architect.md`, `.claude/commands/doctor.md`, `.claude/commands/bootstrap-architecture.md`) — verify none were renamed by upstream v1.4/v1.5 (R16). If `.claude/agents/devops-engineer.md` became `.claude/agents/platform-engineer.md` upstream (hypothetical), our overrides line silently no-ops and the new file gets stomped on next sync.
- The 10 GCP/workshop scripts in `scripts/*.sh` — confirm none are now shipped by upstream (which would mean we're overriding an actual upstream file rather than a fork-local addition).
- Append the two new upstream overrides if applicable: `.gembaflow-meta/` and `.claude/commands/work-ticket.md` per upstream v1.5.0's `.gembaflow-overrides` (verified via `gh api`). The first is structural; the second is so that bootstrap-time-substituted placeholders survive the next sync.
- **Create `.gembaflow-config.json`** by copying `.gembaflow-config.example.json` and filling in actual values. Run `bash scripts/substitute-config-placeholders.sh` (new in v1.5.0) to populate placeholders in `.claude/commands/work-ticket.md` and `.claude/commands/drain.md`.
(-1).7 **Doc string updates** (per "What changes" item 4) AND **verification gate:**
- Edit `CLAUDE.md`, `UPSTREAM.md`, `VERSIONING.md` per item 4.
- Add `json-validate` to branch-protection ruleset 15886599.
- `bash scripts/doctor.sh` — must complete without ERROR.
- `uv run pytest` — full suite must pass.
- Manual smoke: `/work-ticket` slash command resolves (loads the now-template-substituted spec), `/sprint-status` runs, `/doctor` runs.
- `grep -r "\.agile-flow-" . --include="*.sh" --include="*.md" --include="*.json"` — expect 0 hits in non-historical files (session journals + ADRs may keep their references as historical record).
- Open PR for `feature/framework-align-gembaflow-v1.5.0`.

#### Why this lands before masterkey Phase 0

Three reasons, in priority order:

1. **Same files, sequence-sensitive.** Existing E2-T5 (#196) edits `scripts/provision-gcp-project.sh` + `scripts/diagnose-cloudrun.sh` defaults; these are listed in `.agile-flow-overrides`. Existing E2-T7 (#198) edits files listed in `.agile-flow-overrides`. If masterkey lands first and the masterkey PR commits change `.agile-flow-overrides`, the v1.5.0 sync's auto-migration `git mv .agile-flow-overrides .gembaflow-overrides` produces a merge conflict against the not-yet-merged masterkey commits — or worse, lands two copies of the file in the working tree. Doing framework alignment first means by the time E2-T5 / E2-T7 run, the file is already `.gembaflow-overrides` and there's nothing to migrate.
2. **Clean baseline at v1.5.0.** v1.5.0 adds `audit-local-customizations.sh` (run by `/upgrade` per #468) which surfaces every framework-controlled file modified locally but NOT in `.gembaflow-overrides`. Running this BEFORE Phase 0 catches drift the masterkey rename would otherwise pile on top of.
3. **`agile-flow-app` Cloud Run service name disambiguation.** Once we say "Gemba Flow" in CLAUDE.md, the Cloud Run service name `agile-flow-app` is unambiguously a project-specific holdover (not a framework default). This makes the masterkey Phase 4 cutover narrative cleaner — we're renaming "the legacy Cubrox Cloud Run service", not "the Agile Flow framework default service".

#### Rollback point RB-(-1)

Pre-Phase-(-1) SHA captured in step (-1).1. Rollback is `git reset --hard <pre-Phase-(-1)-SHA>` on the feature branch BEFORE the sync PR merges. After merge: rollback requires reverting the sync PR (which is a multi-hundred-file revert touching `.claude/`, `scripts/`, etc.) AND `git mv`-reversing the metadata file renames (which the upstream `template-sync.sh` will re-do on the next `/upgrade`).

**Special concern: framework-rollback is itself a framework operation.** `template-sync.sh` is in `syncDirectories` AND in `RUNTIME_PROTECTED_PATHS`, which means the upstream v1.5.0 version replaces our local v1.3.0 version during the sync. The script that ran the sync is no longer the script that lives on disk. If the sync produces a broken state, the recovery script available to us is the NEW v1.5.0 one (or a curl of the old v1.3.0 from `github.com/vibeacademy/agile-flow/raw/v1.3.0/scripts/template-sync.sh` — note: from `vibeacademy/agile-flow` since at v1.3.0 the repo wasn't yet renamed). Capture the v1.3.0 script as `/tmp/template-sync.v1.3.0.sh` in step (-1).1 alongside the metadata snapshot.

#### Specific risks (see also §4 R16-R18)

- **R16:** v1.4.0 or v1.5.0 may have renamed agents whose old names appear in our `.agile-flow-overrides`. If `.claude/agents/devops-engineer.md` is renamed to `.claude/agents/platform-engineer.md` upstream, our override line silently no-ops, the upstream file lands, and our fork-customized contents are lost on next sync. Mitigation: (-1).6 walks the overrides list against the actual on-disk file list post-sync.
- **R17:** `.gembaflow-config.example.json` is a new file shipped in v1.5.0 with 4 placeholder fields (`org`, `board.id`, `bot.worker`, `bot.reviewer`). If we don't create `.gembaflow-config.json` from it and run `substitute-config-placeholders.sh`, the v1.5.0 `.claude/commands/work-ticket.md` and `drain.md` will load with `{{org}}` etc. literally in the spec text — every `/work-ticket` invocation will read placeholder syntax and fail. Mitigation: (-1).6 explicitly creates `.gembaflow-config.json` and runs the substitution script.
- **R18:** The manual curl-refresh of `template-sync.sh` in step (-1).4 is bootstrap-of-the-bootstrapper. If the curl returns HTTP 404 (e.g., tag `v1.5.0` typo'd, or the file moved upstream), the on-disk script stays at v1.3.0 logic, the auto-migration block is absent, and step (-1).5's sync produces dual-state: `.agile-flow-*` files remain AND `.gembaflow-*` may or may not appear depending on whether v1.3.0's logic happens to look for the new names anywhere (it doesn't — it'd just say "VERSION_FILE not found"). Mitigation: the `grep -c "Self-healing post-sync refresh" scripts/template-sync.sh` gate in step (-1).4 fails loud if the refresh didn't take.

**RB-(-1):** Revert to pre-Phase-(-1) SHA on the feature branch before merge; OR if merged, revert the sync PR + restore `.agile-flow-*` filenames via `git mv` reversal (the `/tmp/template-sync.v1.3.0.sh` snapshot can drive the recovery).

---

### Phase 0 — Pre-flight (read-only, no production impact)

1. Inventory all open + closed tickets on `orgs/vibeacademy/projects/29`. Export to a local JSON file. (`gh api graphql` with `node(id: $projectId) { items(...) }`.)
2. Snapshot the existing state into `snapshots/` (per S2):
   - `gcloud run services describe agile-flow-app --region=us-central1 --format=yaml > snapshots/agile-flow-app.pre-rename.yaml`
   - `gcloud run revisions list --service=agile-flow-app --region=us-central1 --format=yaml > snapshots/revisions.pre-rename.yaml`
   - `gcloud iam service-accounts get-iam-policy $SA_EMAIL --format=yaml > snapshots/sa-iam.pre-rename.yaml`
   - `gcloud secrets list --project=$GCP_PROJECT_ID --format=yaml > snapshots/secrets.pre-rename.yaml`
   These are the rollback artifacts if the new service goes sideways.
3. **Verify WIF wiring.** Confirm the binding shape matches what `provision-gcp-project.sh` provisioned:
   ```bash
   SA_EMAIL=$(gcloud secrets versions access latest --secret=gcp-deployer-sa-email --project=$GCP_PROJECT_ID 2>/dev/null) \
     || SA_EMAIL="<read from GCP_SERVICE_ACCOUNT secret>"
   gcloud iam service-accounts get-iam-policy "$SA_EMAIL" \
     --project=$GCP_PROJECT_ID --format=json \
     | jq '.bindings[] | select(.role | IN("roles/iam.workloadIdentityUser","roles/iam.serviceAccountTokenCreator"))'
   ```
   Expect to see `principalSet://.../attribute.repository/cubrox/cubrox` for BOTH roles. Provider's attribute condition is `assertion.repository != ''` (trivially true) — confirm with `gcloud iam workload-identity-pools providers describe ... --format=value(attributeCondition)`. **There is nothing to edit at the provider level**; the work is at the SA IAM binding (Phase 2 step 16).
4. Enumerate Cloud Logging / Monitoring assets (resolved Q7):
   ```bash
   gcloud logging metrics list --project=$GCP_PROJECT_ID
   gcloud alpha monitoring policies list --project=$GCP_PROJECT_ID --format='value(displayName,combiner)'
   gcloud monitoring dashboards list --project=$GCP_PROJECT_ID --format='value(displayName)'
   ```
   Most likely returns empty (per ADR-004); if non-empty, queue those entries for Phase 5 step 39.
5. Confirm zero open PRs (preview deploys in flight are a hazard for Phase 4). If any exist, ask their authors to rebase after the rename — don't try to migrate live revision tags. Verified at v1 review time: `gh pr list --state open` returns `[]`.
6. Enumerate external forks: `gh api repos/cubrox/cubrox/forks --jq '.[].full_name'` (per R15). If any exist, notify the fork owners.

**RB-0:** Trivial — nothing changed.

### Phase 1 — Code-only changes on a feature branch

7. Branch: `feature/refactor-cubrox-to-masterkey`.
8. Apply ALL §2.2 code/test/template renames AND `.github/workflows/ci.yml:218,307,315` rename (B1). Drive via:
   - `app/main.py` title
   - `CUBROX_TEST_SEED_ENABLED` -> `MASTERKEY_TEST_SEED_ENABLED` everywhere (one ripgrep + sed pass, then audit) — including `ci.yml`
   - `window.cubroxLineCount` -> `window.masterkeyLineCount`
   - `app/scripts/metric.py` prog name
   - test fixtures (`pr-42---agile-flow-app-...` -> `pr-42---masterkey-...`)
   - npm package.json + package-lock.json regenerate
9. Apply §2.5 script edits to `scripts/provision-gcp-project.sh` (lines 800, 1011) and `scripts/diagnose-cloudrun.sh` (line 35 + line 23 comment) (B4). Both are in `.agile-flow-overrides`, safe to edit.
10. Apply §2.6 doc renames (carefully; do not edit upstream-synced docs without adding to `.agile-flow-overrides`).
11. Apply §2.7 agent persona edits (only the files in `.agile-flow-overrides`). **Also** fold the `.claude/PROJECT.md` Supabase fix here (per S5).
12. Update `supabase/config.toml` `project_id`.
13. **Disable synthetic monitor schedule for the cutover window** (resolved Q9): comment out the `schedule:` block in `.github/workflows/synthetic-monitor.yml` on this branch. Add a TODO in the PR body to restore it in a small follow-up PR after Phase 4 step 32.
14. Run full local test suite: `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`, `uv run mypy app/`, and `tests/a11y` (locally against `supabase start`).
15. Open PR. **The preview deploy on this PR will still go to the old `agile-flow-app` service** because we haven't flipped `vars.CLOUD_RUN_SERVICE` yet. That's the validation: a green preview here proves the code rename is functionally a no-op.

**RB-1:** Close PR, no impact. Nothing has been deployed.

### Phase 2 — GitHub repo + board migration + WIF dual-write (independent of code)

Can run in parallel with Phase 1 (the code-only branch). Four operations; order matters within this phase — WIF binding MUST land before the repo rename.

16. **WIF dual-write (NEW step, was 11.5 in DevOps review — must happen BEFORE the repo rename).** Add a parallel `principalSet` IAM binding on the deployer SA for `cubrox/masterkey` with BOTH `roles/iam.workloadIdentityUser` AND `roles/iam.serviceAccountTokenCreator`:
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
    The old `cubrox/cubrox` binding remains intact in parallel — both names resolve during the grace window. **Verify:** trigger `workflow_dispatch` on `rollback-production.yml` with `revision=<currentRevision>` and `reason='WIF binding verification'`. This auths to GCP but only acts on user-confirmed input — safe to dry-run. If the auth step passes, the binding is plumbed.
17. **Repo rename:** `gh repo rename masterkey --repo cubrox/cubrox` (or via GH UI). GitHub auto-redirects git clone URLs for 30 days, but:
    - **Immediately** update local remotes on every developer machine: `git remote set-url origin git@github.com:cubrox/masterkey.git`.
    - Verify branch-protection ruleset (id 15886599) still applies: `gh api repos/cubrox/masterkey/rulesets` (per S3).
    - Verify Supabase GitHub App allowlist still contains the repo (per R10): Supabase dashboard → Project Settings → Integrations → GitHub.
18. **New project board:** create `https://github.com/orgs/cubrox/projects/<new>`. Mirror columns + automation. Migrate items from `orgs/vibeacademy/projects/29` via `gh api graphql` `addProjectV2ItemById` for every issue/PR ID (open AND closed). Verify item count parity.
19. Close the legacy `vibeacademy/projects/29` board (do NOT delete — keep as audit record). Add a README note in its description pointing to the new board.

**RB-2:** Repo rename is reversible via `gh repo rename cubrox`. Board migration is additive; the legacy board still exists as fallback until step 19. WIF dual-write is purely additive — removing the new binding is a one-line `remove-iam-policy-binding`.

### Phase 3 — Cloud Run + Artifact Registry preparation (no traffic yet)

20. Create new Artifact Registry repo `masterkey` in the same region: `gcloud artifacts repositories create masterkey --repository-format=docker --location=us-central1`.
21. Grant the runtime SA `roles/artifactregistry.reader` on the new repo (usually inherited from project-level, but verify).
22. **Build + push** an image to the new repo manually as a smoke test: `docker build -t us-central1-docker.pkg.dev/$PROJECT/masterkey/masterkey:smoke . && docker push ...`.
23. **Pre-create** the Cloud Run service `masterkey` with a placeholder revision pointing at the smoke image, mounting the same secrets as `agile-flow-app`. **CRITICAL (B3 / R13):** match `deploy.yml`'s env-var TYPES exactly — `DATABASE_URL` and `ANTHROPIC_API_KEY` MUST be plain literals via `--set-env-vars`, NEVER `--set-secrets`. Cloud Run's literal-vs-secret env-var type is sticky per name; switching requires a destructive service recreate. Production currently uses literals (per `deploy.yml:216-217`); the placeholder must do the same:
    ```
    gcloud run deploy masterkey \
      --image=us-central1-docker.pkg.dev/$PROJECT/masterkey/masterkey:smoke \
      --region=us-central1 \
      --service-account=$RUNTIME_SA \
      --port=8080 --memory=512Mi --cpu=1 \
      --min-instances=0 --max-instances=10 \
      --allow-unauthenticated \
      --set-env-vars="ENVIRONMENT=production,DATABASE_URL=$PROD_DB_URL,ANTHROPIC_API_KEY=$KEY" \
      --set-secrets="SUPABASE_URL=supabase-url:latest,SUPABASE_ANON_KEY=supabase-anon-key:latest,SUPABASE_SERVICE_KEY=supabase-service-key:latest" \
      --no-traffic
    ```
    (Per resolved Q10: `--min-instances=0` for the placeholder, not 1 — the placeholder shouldn't actually run the smoke image hot. `deploy.yml:168` will flip it to 1 on the real Phase 4 deploy.) Then `--to-latest` traffic shift, but **only on the new service in isolation** — `agile-flow-app` still serves prod.
24. Curl the new service's URL — `/api/health` (200), `/api/health/db` (200), then `/` (200, sees Master Key landing). **Capture the new URL** for `docs/LAUNCH-CHECKLIST.md` (B5):
    ```bash
    NEW_URL=$(gcloud run services describe masterkey --region=us-central1 --format='value(status.url)')
    echo "$NEW_URL"  # e.g. https://masterkey-aBcDeFgH-uc.a.run.app
    ```
    Amend the still-open Phase 1 PR (or open a small doc PR if Phase 1 has already merged) to pin `$NEW_URL` into `docs/LAUNCH-CHECKLIST.md` line 10, and `CLAUDE.md`'s Project Information block per S6. Update §2.C health-probe instructions (lines 45-46) and §2.D auth-test (line 51) of the launch checklist to reference `$NEW_URL`.
25. **Dry-run preview-deploy + preview-cleanup against the new service (was Phase 4 R1 mitigation; now an explicit numbered step per S4).** Open a throwaway PR with a trivial change AND a `supabase/migrations/<timestamp>_rename_smoke.sql` empty file (per R10 — exercises the Supabase branching path). Confirm:
    - First push (with `vars.CLOUD_RUN_SERVICE` still `agile-flow-app`): preview goes to the old service. ✓
    - Flip `vars.CLOUD_RUN_SERVICE=masterkey` temporarily, push a new commit: preview-deploy run pushes to `masterkey/masterkey:pr-N-<sha>`, tags `masterkey` service, smoke-test passes, PR comment updates in place (verified by R1's marker-string match in v1). ✓
    - Close the PR: preview-cleanup runs against `masterkey`, finds and removes the `pr-N` tag (handles missing-tag idempotently per workflow code). ✓
    - **Flip the var BACK to `agile-flow-app` immediately** after the dry-run completes — Phase 4 step 27 needs the old var still in effect when Phase 1 PR merges.
    - Label the dry-run PR `phase3-dryrun` so cleanup is easy to confirm.
26. **Add the new service URL + preview pattern to the Supabase Auth redirect allowlist** (per R4 + R12). Both production URLs allowed simultaneously; old ones stay until Phase 5 cleanup. Patterns to add: `https://masterkey-<hash>-uc.a.run.app/auth/callback` (production) AND `https://pr-*---masterkey-*-uc.a.run.app/auth/callback` (preview).

**RB-3:** Delete the `masterkey` service + Artifact Registry repo. Revert the temporary var flip done in step 25. No prod impact (the old `agile-flow-app` service was never touched).

### Phase 4 — Cutover (re-sequenced per B7 to eliminate the var-flip-before-merge race)

The v1 ordering had a race window where `vars.CLOUD_RUN_SERVICE=masterkey` could be live while the Phase 1 PR was still unmerged — meaning any preview-deploy fired between var flip and merge would try to push to the new AR/service with OLD code (which still references `CUBROX_TEST_SEED_ENABLED`). The new ordering ships exactly one risk per step.

27. **Merge the Phase 1 PR** (vars STILL point at `agile-flow-app`). The merge triggers `deploy.yml`, which builds the post-rename code and deploys to the **old** `agile-flow-app` service. This is the live verification that the code rename is a functional no-op (satisfies Phase 1 step 15's acceptance criterion against production rather than just preview).
28. **Verify production health on the old service URL** after the merge-triggered deploy. `curl https://agile-flow-app-heo5ry7rua-uc.a.run.app/api/health` and `/api/health/db`; run `scripts/smoke_auth.py` against the old URL. If any of these fail, **stop and roll back the merge** — do not flip vars while production is unhealthy.
29. **Flip GitHub vars** (instantaneous, atomic from the deploy pipeline's perspective):
    ```bash
    gh variable set CLOUD_RUN_SERVICE --body masterkey
    gh variable set ARTIFACT_REPO --body masterkey
    ```
30. **Push a trivial commit to `main`** (the `CHANGELOG.md` entry from §2.6 is a natural choice) to trigger `deploy.yml`. The workflow now reads `vars.CLOUD_RUN_SERVICE=masterkey`, builds an image into `masterkey/masterkey:<sha>`, and deploys to the `masterkey` Cloud Run service. Watch the run.
31. **Verify new service URL health.** `curl $NEW_URL/api/health`, `/api/health/db`, `/`. Run `scripts/smoke_auth.py` against `$NEW_URL`. Confirm Supabase magic-link round-trip succeeds (the synthetic monitor would normally catch this, but it's disabled per Phase 1 step 13).
32. **Re-enable synthetic monitor.** Open a small follow-up PR restoring the `schedule:` block in `.github/workflows/synthetic-monitor.yml`. On merge, the monitor's next :17-past-the-hour run hits `gcloud run services describe masterkey` → resolves to `$NEW_URL` → probes the new service URL automatically (self-heals per resolved Q9 + C3).
33. **Inform users / update external URL references.** If a custom domain is in play (currently isn't), no action. If we're on `*.run.app`, the user-facing URL has changed — announce the new URL. Update any docs that reference the production URL but were not touched in Phase 3 step 24.
34. **Keep both Supabase Auth allowlist entries** (old + new, production + preview patterns) for 24-48h post-cutover. Phase 5 step 37 prunes the old ones.

**RB-4 (critical rollback):**
- If step 30's `deploy.yml` run fails: the new service either has a bad revision (use `gcloud run services update-traffic masterkey --to-revisions=<prev>=100`) or never deployed (the old service is still serving prod via the deploy from step 27, the rename is just stalled — fix the workflow and re-run).
- If the deploy succeeds but real traffic shows breakage: `gh variable set CLOUD_RUN_SERVICE --body agile-flow-app` and `gh variable set ARTIFACT_REPO --body agile-flow`. Push another trivial commit to trigger `deploy.yml`. The old service was never deleted (Phase 5 hasn't run), so this is a clean revert.
- The new service can be deleted once safe: `gcloud run services delete masterkey`.
- If WIF auth fails despite the dual-write: confirm the new binding actually applied via `gcloud iam service-accounts get-iam-policy $SA_EMAIL`. The provider's attribute condition is trivially true, so the only possible cause is the binding not being present.

### Phase 5 — Cleanup (30 days after cutover per resolved Q4, no rollback expected)

35. Delete the old Cloud Run service: `gcloud run services delete agile-flow-app --region=us-central1`.
36. Delete the old Artifact Registry repo (after confirming no images are pulled from it): `gcloud artifacts repositories delete agile-flow --location=us-central1`. Note: this is destructive and loses image history; archive the latest few image manifests first if forensics matter. **30-day grace window** lets us re-pull any commit-SHA-tagged image for incident triage.
37. Remove the old `agile-flow-app-*.run.app` production URL AND the old `pr-*---agile-flow-app-*` preview pattern from the Supabase Auth redirect allowlist (per R12).
38. **Remove the old WIF binding:**
    ```bash
    OLD_MEMBER="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github/attribute.repository/cubrox/cubrox"
    for role in roles/iam.workloadIdentityUser roles/iam.serviceAccountTokenCreator; do
      gcloud iam service-accounts remove-iam-policy-binding "$SA_EMAIL" \
        --role="$role" --member="$OLD_MEMBER" --project=$GCP_PROJECT_ID
    done
    ```
39. Update Cloud Logging saved queries, dashboards, and any alert policies enumerated in Phase 0 step 4 to reference `resource.labels.service_name="masterkey"`. Likely a no-op per ADR-004 (no custom alerts/dashboards configured), but verify.
40. Close the `cubrox/cubrox` repo redirect note in CHANGELOG.

**RB-5:** Past this point, rollback means re-creating from snapshots (Phase 0 step 2). Don't run Phase 5 until Phase 4 has been stable for at least 30 days.

---

## 4. Risk register

### R1 — Ephemeral preview deploys break mid-rename

**Likelihood:** High if Phase 4 is staged poorly.
**Impact:** All open PRs lose preview deploys; reviewers can't validate visually.

**Mechanism:** `preview-deploy.yml` builds an image into `${ARTIFACT_REPO}/${SERVICE_NAME}:pr-N-<sha>` and tags a Cloud Run revision on `${SERVICE_NAME}`. If we flip `vars.CLOUD_RUN_SERVICE` while PRs are open, the next preview-deploy run will:
1. Try to push to a new Artifact Registry path (`masterkey/masterkey:pr-N-<sha>`) — succeeds IF Phase 3 step 20 ran (the new AR repo exists).
2. Try to tag a `pr-N` revision on the `masterkey` service — succeeds IF Phase 3 step 23 pre-created the service.
3. Smoke-test the preview URL pattern `https://pr-N---masterkey-<hash>-uc.a.run.app/api/health` — the URL changes shape (different `<hash>` segment), so the **PR comment with the stale `agile-flow-app` URL will be updated in place** by the `actions/github-script` step (line 307: `c.body?.startsWith('## Preview Deployment')`). Verified: the script overwrites by marker, doesn't append.
4. The cleanup workflow (`preview-cleanup.yml`) when the PR closes will run against the NEW `${SERVICE_NAME}` and look for `pr-N` tag — won't find it on `masterkey` if the tag was created against `agile-flow-app` pre-flip. **Result: orphaned `pr-N` tag on `agile-flow-app` until Phase 5 deletes the service.**

**Mitigation:**
- **Phase 3 step 25 dry-run PR** is now the explicit acceptance gate: open a throwaway PR, flip vars, push, verify, close, restore vars.
- Communicate to all PR authors before flip: "rebase your PR onto post-rename main; your preview URL is going to change."
- Plan Phase 4 for a quiet window (no PRs in flight). Phase 0 step 5 confirms zero open PRs.

### R2 — Cloud Run service rename loses traffic history / revision history

**Likelihood:** Certain (this is how Cloud Run works — services aren't renameable in-place; confirmed by `gcloud run services --help`).
**Impact:** Operational forensics. Cannot `gcloud run revisions list agile-flow-app-00042-xyz` after Phase 5 step 35.

**Mitigation:**
- Phase 0 step 2 captures full YAML snapshots (service + revisions + SA IAM + secrets list per S2).
- Phase 5 step 36: archive image manifests before deleting AR repo.
- Cloud Logging retains logs by project + resource label for 30 days minimum (configurable); old service logs are still query-able as long as the project lives.

### R3 — WIF auth fails after repo rename (REVISED per B2)

**Likelihood:** Certain if Phase 2 step 16 (dual-write) is skipped.
**Impact:** Every workflow that authenticates to GCP starts failing with `iam.serviceAccounts.getAccessToken denied`. `deploy.yml`, `preview-deploy.yml`, `synthetic-monitor.yml`, `rollback-production.yml`, `preview-cleanup.yml` are all affected. Production isn't down (last good revision still serves) but no new deploys can ship — including rollback. **This is the single most likely "stuck in the middle" failure mode.**

**Mechanism:** Per `provision-gcp-project.sh:437-439, 465-474`, the WIF provider's attribute-condition is trivially true (`assertion.repository != ''`). The repo pin lives on the **deployer SA's IAM policy** as `principalSet://.../attribute.repository/cubrox/cubrox`, with BOTH `roles/iam.workloadIdentityUser` AND `roles/iam.serviceAccountTokenCreator`. After the repo rename, GitHub's OIDC token presents `repository = cubrox/masterkey`, which doesn't match the bound principalSet, so token-exchange fails. **There is nothing to change at the provider level** — the v1 plan's "edit the attribute condition" path was wrong.

**Mitigation:**
- Phase 2 step 16 dual-writes the new binding BEFORE the rename. The old binding stays alongside until Phase 5 step 38 removes it. Both names resolve for the entire grace window.
- Verification: `workflow_dispatch` on `rollback-production.yml` with `revision=<current>` and `reason='WIF binding verification'` after step 16 but before step 17 (the repo rename).
- The per-repo binding kept narrow (not widened to org-level per resolved Q5) — accidental sibling repos created under `cubrox` never inherit deploy capability.

### R4 — Supabase magic-link sign-in breaks (redirect URL not in allowlist)

**Likelihood:** Certain if Phase 3 step 26 is skipped.
**Impact:** Users click their magic link, GoTrue refuses the redirect, sign-in fails. Production auth outage.

**Mitigation:**
- Phase 3 step 26 (allowlist the new production URL + new preview pattern pre-cutover).
- `synthetic-monitor.yml` (after re-enable in Phase 4 step 32) will catch any remaining gap within an hour of cutover (it drives a real sign-in against the live URL). `synthetic-monitor.yml:104-107` calls `gcloud run services describe ${SERVICE_NAME}` and `SERVICE_NAME` now reads `vars.CLOUD_RUN_SERVICE=masterkey` — self-healing as long as the var flip happens.

### R5 — `template-sync.sh` next run reverts hand-edited files

**Likelihood:** Medium (the next time someone runs `/upgrade` or `template-sync`).
**Impact:** Renames in `.claude/agents/*.md`, `docs/PLATFORM-GUIDE.md`, etc. get reverted to upstream.

**Mitigation:**
- For files in `.claude/agents` that are already in `.agile-flow-overrides`, the override mechanism protects them — no action needed.
- For `scripts/provision-gcp-project.sh` and `scripts/diagnose-cloudrun.sh`: both are already in `.agile-flow-overrides` (verified), so the B4-mandated edits are protected.
- For `docs/PLATFORM-GUIDE.md`, `docs/CI-CD-GUIDE.md`: either (a) add them to `.agile-flow-overrides` if we edited them, or (b) leave the upstream `agile-flow-app` references intact and accept that the docs say "agile-flow-app" while reality says "masterkey" (low-cost — these are framework reference docs, not operational runbooks).
- Strongly recommend (a): add to `.agile-flow-overrides` ONLY the files we actually edited.

### R6 — `pyproject.toml` rename desync (REVISED per B6)

**Likelihood:** Zero (we're not renaming it).
**Impact:** N/A today.

**Audit-debt note for future maintainers:** if any maintainer later renames `pyproject.toml:name` from `agile-flow-gcp`, they must also audit `[tool.*]` config blocks for the old name. The current value flows into:
- `uv build` wheel filenames (`agile_flow_gcp-X.Y.Z-py3-none-any.whl`)
- `uv pip list` display
- Any `[tool.X.agile-flow-gcp]` config block that scopes by project name (none today; verify before any future rename)
- `template-sync.sh`'s diff logic against upstream

None of our internal code imports the package by its `pyproject.toml` name (the code is in `app/`, not `agile_flow_gcp/`), so a future rename would be cosmetic + config-audit only.

### R7 — Memory MCP entities reference stale names

**Likelihood:** Medium.
**Impact:** Agents in long-lived sessions answer questions using "Cubrox" terminology after the rename, confusing operators.

**Mitigation:**
- Post-rename: run a `prune-memory` skill pass searching for `cubrox` / `Cubrox` entities and rename or add alias observations.
- Out of immediate scope per task brief — flagged as follow-up.

### R8 — Documentation links rot

**Likelihood:** Low-medium.
**Impact:** External references (blog posts, internal wiki, Slack messages) that link to `https://github.com/cubrox/cubrox` get a GitHub 30-day redirect, then break. References to `agile-flow-app-heo5ry7rua-uc.a.run.app` break the moment we delete the old service in Phase 5.

**Mitigation:**
- GitHub redirect window covers the urgent path.
- Communicate the URL change before Phase 5.
- If we have a custom domain (we don't; resolved Q6 defers it), this is moot.

### R9 — `tests/a11y` package-lock churn breaks CI cache key

**Likelihood:** Low.
**Impact:** First CI run after the npm rename rebuilds Playwright browsers (slow but not broken).

**Mitigation:** None needed; cache repopulates within one run.

### R10 — Supabase GitHub App allowlist may de-list the repo on rename (NEW per DevOps)

**Likelihood:** Unknown (depends on whether Supabase tracks by `repository.id` or `owner/name`).
**Impact:** Per-PR Supabase branching silently breaks for new PRs. The Phase 4 step 30 deploy could land with `DATABASE_URL` pointing at production even for migration PRs that should have been branched.

**Mitigation:**
- Immediately after Phase 2 step 17 (repo rename), visit Supabase dashboard → Project Settings → Integrations → GitHub. Confirm `cubrox/masterkey` appears in the allowlist. If it doesn't, re-install the App on the new repo name.
- The Phase 3 step 25 dry-run PR includes an empty `supabase/migrations/<timestamp>_rename_smoke.sql` to exercise the branch-creation path — if branching doesn't fire on that PR, the App allowlist hasn't updated.

### R11 — `tests/test_auth_login.py` fixture URL is coherence-only, not semantic (NEW per DevOps)

**Likelihood:** N/A (clarification, not a risk).
**Impact:** N/A.

**Note:** The test asserts that `_external_origin` returns the exact `X-Forwarded-Host` it received as the redirect URL — the string itself has no semantic dependency on the service name. The §2.2 rename of `pr-42---agile-flow-app-xyz.run.app` -> `pr-42---masterkey-xyz.run.app` is for coherence, NOT to verify the new naming. Captured in §2.2's Justification column so a reviewer doesn't misread the change.

### R12 — Supabase Auth allowlist preview-PR pattern (NEW per DevOps)

**Likelihood:** Certain (the preview-deploy redirect pattern almost certainly exists today).
**Impact:** Magic-link sign-in inside preview environments breaks the moment `vars.CLOUD_RUN_SERVICE=masterkey` is active and a PR triggers a preview build. Reviewers can't smoke-test auth changes in PRs.

**Mitigation:**
- Phase 3 step 26 adds `https://pr-*---masterkey-*-uc.a.run.app/auth/callback` alongside the existing `https://pr-*---agile-flow-app-*.run.app/auth/callback` pattern.
- Phase 5 step 37 prunes the old pattern after stability is confirmed.

### R13 — Cloud Run env-var type stickiness (`literal` vs `secret`) (NEW per B3)

**Likelihood:** Medium (a manual `gcloud run deploy` in the dual-service window could brick the new service).
**Impact:** `Cannot update environment variable [DATABASE_URL] to <type> because it has already been set with a different type` — the next `deploy.yml` run fails permanently; the only fix is destructive service recreate (which restarts the entire cutover).

**Mitigation:**
- Phase 3 step 23 sets `DATABASE_URL` and `ANTHROPIC_API_KEY` as plain literals via `--set-env-vars` only, matching `deploy.yml:216-217`'s shape.
- DO NOT use `--set-secrets` for `DATABASE_URL` or `ANTHROPIC_API_KEY` on `masterkey` during the dual-service window. Supabase credentials (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`) DO use `--set-secrets` and that matches production — leave them as-is.
- If anyone needs to test secret-mount migration during the dual-service window, do it on a fresh throwaway service, not on `masterkey`.

### R14 — Cloud Run services-per-region quota during dual-service window (NEW; FYI only per DevOps)

**Likelihood:** N/A — quota headroom is huge.
**Impact:** None expected.

**Note:** Pre-creating `masterkey` in Phase 3 while `agile-flow-app` still exists means 2 services in the project. Default Cloud Run quota is ~1000 services per region per project. Captured here for completeness; no mitigation needed.

### R15 — External forks of `cubrox/cubrox` may have stale upstream URLs (NEW per DevOps)

**Likelihood:** Probably zero.
**Impact:** Fork owners' `git remote -v` continues to show `cubrox/cubrox` until they manually update; GitHub redirect covers 30 days.

**Mitigation:**
- Phase 0 step 6 enumerates forks via `gh api repos/cubrox/cubrox/forks --jq '.[].full_name'`.
- If any exist, notify the owners with the `git remote set-url` command.

### R16 — Upstream agent-file renames silently no-op our overrides (NEW per Phase -1)

**Likelihood:** Medium. v1.4.0 / v1.5.0 cumulative changes are large (28 PRs across both); at least one agent or command file is plausibly renamed.
**Impact:** Our `.gembaflow-overrides` line points at a path that no longer exists. The upstream file (newly named) lands without override protection, and our fork-customized contents (which were keyed to the old name) are lost on the same sync.

**Mitigation:**
- Phase -1 step (-1).6 walks `.gembaflow-overrides` against the actual on-disk file list post-sync, line by line.
- For any line where the listed file no longer exists post-sync: `git log --diff-filter=R --follow` upstream to find the rename target, update the overrides line, manually re-apply our customizations to the new path, and commit.

### R17 — `.gembaflow-config.json` missing causes slash-command spec corruption (NEW per Phase -1)

**Likelihood:** Certain if step (-1).6 skips creating `.gembaflow-config.json`.
**Impact:** v1.5.0 `.claude/commands/work-ticket.md` and `.claude/commands/drain.md` contain `{{org}}`, `{{board.id}}`, `{{bot.worker}}`, `{{bot.reviewer}}` placeholders that `substitute-config-placeholders.sh` populates at bootstrap. Without `.gembaflow-config.json`, the substitution either errors or leaves the placeholders literal. Every `/work-ticket` invocation reads spec text containing literal `{{org}}` and either fails or misbehaves.

**Mitigation:**
- Phase -1 step (-1).6 explicitly creates `.gembaflow-config.json` (copied from `.gembaflow-config.example.json`, fields populated).
- For Phase -1 only, `org=cubrox` (will be overwritten in masterkey Phase 2; user-account is fine here since the repo lives at `cubrox/cubrox`), `board.id=29` (legacy `vibeacademy/projects/29` is still the active board through Phase 2). Solo-mode means `bot.worker` and `bot.reviewer` both equal the operator's GitHub handle.
- Run `bash scripts/substitute-config-placeholders.sh` and `bash scripts/substitute-config-placeholders.sh --check` to verify substitution completed.
- Add `.gembaflow-config.json` to `.gitignore` (it contains operator-specific bot account names — shouldn't be tracked) OR commit a checked-in default and `.gitignore` only a `.local.json` override. Decide in step (-1).6.

### R18 — Bootstrap-of-bootstrapper: manual curl-refresh of `template-sync.sh` may silently fail (NEW per Phase -1)

**Likelihood:** Low but consequential.
**Impact:** Step (-1).4's two `curl` commands fetch the v1.5.0 `template-sync.sh` and `lib/overrides.sh`. If either curl returns HTTP 404 (typo'd tag, file moved upstream) or returns a partial file (network blip during pipe to `-o`), the on-disk script stays at v1.3.0 logic. Step (-1).5's `bash scripts/template-sync.sh` then runs the OLD code, which has no auto-migration and no self-heal. The result is dual-state: the script tries to read `.agile-flow-version` (which exists, so it succeeds), syncs v1.5.0 syncDirectories on top of our v1.3.0 tree, but never migrates the dotfile names. Next `/upgrade` run finds the upgraded v1.5.0 syncDirectories AND a still-`.agile-flow-*`-named metadata set — confused.

**Mitigation:**
- Step (-1).4 ends with `grep -c "Self-healing post-sync refresh" scripts/template-sync.sh` which MUST return exactly `1`. Loud failure if curl didn't take.
- Step (-1).1 captures the pre-Phase-(-1) SHA AND a copy of v1.3.0 `template-sync.sh` to `/tmp/template-sync.v1.3.0.sh` as the bootstrap-of-bootstrapper rollback path.
- `curl -fsSL` is used (lowercase `f` exits non-zero on HTTP error; `S` shows errors; `L` follows redirects) — explicit choice to fail loud on 404.

---

## 5. Resolved decisions (was "open questions" in v1)

All ten v1 open questions have been resolved by DevOps. Folded into the plan as decisions:

| # | Question (v1) | Decision (v2) | Folded into |
|---|---------------|---------------|-------------|
| Q1 | Blue/green via Cloud Load Balancer + custom domain before rename? | **No.** Stick with destructive create-new-then-delete-old. Pre-creating `masterkey` in Phase 3 step 23 gives 99% of the blue/green benefit. CLB requires a week of work + new IAM role + DNS dependency — out of locked scope. | §3 Phase 3, Out of Scope |
| Q2 | What does the WIF condition look like today? | The provider's attribute-condition is `assertion.repository != ''` (trivially true). The repo pin lives on the deployer SA's IAM policy as a `principalSet` member with BOTH `roles/iam.workloadIdentityUser` AND `roles/iam.serviceAccountTokenCreator`. The actual fix is Phase 2 step 16 dual-write. | §2.1, §2.3, §3 Phase 2 step 16, R3 |
| Q3 | Secret Manager secret renames? | **No.** Leave `supabase-url`, `supabase-anon-key`, `supabase-service-key` unchanged. Generic names, no `cubrox` in them, runtime SA already bound. Renaming costs 4-step coordinated dance for zero benefit. | §2.3 |
| Q4 | Artifact Registry cleanup window? | **30 days, not 7.** Storage is $0.10/GB-month (rounding error). The only way to roll back to a specific commit-SHA revision is to re-pull that image. | §2.3, §3 Phase 5 |
| Q5 | Widen WIF to `repository_owner == 'cubrox'`? | **No, keep per-repo binding.** Each rename is a one-time event; widening means any new repo under `cubrox` (workshop fork, accidental create) inherits production-deploy capability. Defense-in-depth > audit convenience. | §3 Phase 2 step 16, R3 |
| Q6 | Custom domain timing? | **Defer entirely.** Requires registered domain, DNS, managed cert (15-30 min provisioning), new Supabase allowlist round, new magic-link testing. Bundle would also delay Phase 5 cleanup. File as separate post-launch epic. | Out of Scope |
| Q7 | Enumerate Cloud Logging / Monitoring assets? | **Phase 0 step 4 enumeration.** Expected to be empty per ADR-004 (Sentry deferred). Update if non-empty in Phase 5 step 39. | §3 Phase 0 step 4, §3 Phase 5 step 39 |
| Q8 | `SUPABASE_DB_URL` secret survives rename? | **Yes** (repo secrets are repo-scoped, not name-scoped). Question struck — over-cautious. | §2.1 |
| Q9 | Synthetic monitor cron during cutover? | **Disable cleanly, do not rely on luck.** Cron in GitHub Actions can fire up to ~15 min late. Comment out `schedule:` block in Phase 1 PR; restore in small follow-up PR in Phase 4 step 32. | §3 Phase 1 step 13, §3 Phase 4 step 32 |
| Q10 | `--min-instances=1` cost during dual-service window? | **Set `--min-instances=0` on the placeholder.** Keeping the smoke image warm risks loud false-alarms if the smoke image has any problem. `deploy.yml:168` hardcodes `--min-instances=1` on the real deploy, so the Phase 4 deploy flips it automatically. | §3 Phase 3 step 23 |

---

## 6. Out of scope

Explicitly NOT part of this refactor:

- **GCP project ID rename.** Per locked scope. Would require recreating IAM bindings, WIF pool, secrets, the whole project — orders of magnitude more work.
- **Supabase project ref change.** Per locked scope. Would require database migration, RLS re-deploy, JWT signing-key rotation, redirect-URL migration, magic-link template re-deploy, and a downtime window for the cutover. Out of scope.
- **Supabase org rename.** If the Supabase org happens to be named `vibeacademy` in the dashboard, that's a separate change managed in the Supabase UI and not coupled to this refactor.
- **Custom domain introduction.** Per resolved Q1 + Q6 — deferred as a separate post-launch epic.
- **Cloud Load Balancer / blue-green via traffic-splitting.** Per resolved Q1.
- **Widening WIF to org-level.** Per resolved Q5 — defense-in-depth precludes it.
- **Renaming Secret Manager secrets to add a project prefix.** Per resolved Q3.
- **Public brand change.** "Master Key" is already the public name. This refactor does NOT rename the brand to "masterkey-lowercase" or anything like that.
- **`pyproject.toml` rename.** The framework starter name `agile-flow-gcp` is intentionally preserved. See R6 for audit notes if a future maintainer ever does rename it.
- **Framework artifact renames** (`scripts/template-sync.sh`, `.agile-flow-version` upstream URL, `bootstrap.sh`, the bulk of `scripts/*.sh` that are NOT in `.agile-flow-overrides`). These point at the *Agile Flow framework template*, not the *Master Key product*. Editing them would break framework sync. **NOTE:** `scripts/provision-gcp-project.sh` and `scripts/diagnose-cloudrun.sh` ARE in scope (per B4) because they're in `.agile-flow-overrides`.
- **CHANGELOG link rewrites for historical entries.** The historical record stays as written. Only the post-rename entries reflect the new repo URL.
- **Memory MCP entity migration.** Out of immediate scope; flagged as follow-up under R7.
- **Session-journal historical rewrites.** `reports/session-journals/*.md` stay as written — they're a historical log, not a maintained reference.
- **Database table renames, ORM model renames, API path renames.** Nothing in the persistence layer or HTTP API surface contains "cubrox" — verified via `grep`. No data migration needed.
- **Code package rename** (`app/` -> `masterkey/`). The codebase uses `app` as the import root, which is project-neutral. Renaming it would touch every import line for no functional benefit.
- **Adding `workflow_dispatch:` to `deploy.yml`.** Per S1 — useful escape hatch independent of the rename, but defer to a separate follow-up so the rename PR stays single-purpose.

---

**Result:** Refactor plan revised (v2) for re-review.
Scope: `cubrox` codebase + infra identifier rename to `masterkey`
Recommendation: 5-phase staged cutover with pre-created Cloud Run service; WIF dual-write before repo rename; var-flip after PR merge to eliminate race
Required changes since v1: 7 blockers (B1-B7) all incorporated; R10/R12/R13/R14/R15 added; Q1-Q10 resolved
Risks: 15 identified; R3 (WIF auth — now mitigated by Phase 2 step 16 dual-write) and R1 (preview-deploy break — mitigated by Phase 3 step 25 dry-run) remain highest-leverage
Out of scope: GCP project, Supabase project ref, public brand, framework artifacts not in `.agile-flow-overrides`, `pyproject.toml`, custom domain, CLB
