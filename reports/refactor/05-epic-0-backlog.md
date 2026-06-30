# Epic 0 Backlog: Framework Alignment (gembaflow v1.5.0)

**Author:** System Architect persona
**Date:** 2026-06-29
**Status:** DRAFT — pending product-owner approval before loading into GitHub
**Source artifacts:**
- `reports/refactor/01-architecture-plan.md` (v3) — §3 Phase -1 "Framework alignment (gembaflow v1.5.0)"
- Upstream v1.5.0 release notes — `gh release view v1.5.0 --repo vibeacademy/gembaflow`
- Upstream v1.5.0 file shapes — verified via `gh api repos/vibeacademy/gembaflow/contents/<path>?ref=v1.5.0`

This document is a draft. It does **not** create live GitHub issues. Once approved, the seven tickets below load as Epic 0 (E0) — landing BEFORE the existing Epic 1 / Phase 0 work (issues #181-#191).

---

## Epic-level summary

**Title:** `epic: Phase -1 — Framework alignment (vibeacademy/agile-flow v1.3.0 → vibeacademy/gembaflow v1.5.0)`

**Why this is Epic 0 rather than appended to Epic 1:** the masterkey-rename Phases 0-5 (Epics 1-6) touch the same `.agile-flow-overrides` file and the same `.claude/agents/*.md` files that v1.5.0's `template-sync.sh` auto-migrates. Sequencing matters — see plan §3 Phase -1 "Why this lands before masterkey Phase 0".

**Acceptance criteria for the epic:**
- Local metadata renamed: `.agile-flow-version` → `.gembaflow-version`, `.agile-flow-meta/` → `.gembaflow-meta/`, `.agile-flow-overrides` → `.gembaflow-overrides`. No `.agile-flow-*` files remain in the working tree.
- `.gembaflow-version` `version` field is `1.5.0`.
- `.gembaflow-config.json` exists (gitignored or committed per E0-T6 decision), populated with `org=cubrox`, `board.id=29`, solo-mode bot fields.
- `scripts/template-sync.sh` contains the `Self-healing post-sync refresh` block (`grep -c` returns `1`).
- `.claude/commands/work-ticket.md` and `drain.md` placeholders substituted (no literal `{{` in the rendered specs).
- Doc files `CLAUDE.md`, `UPSTREAM.md`, `VERSIONING.md` use "Gemba Flow" / `vibeacademy/gembaflow`.
- Branch-protection ruleset 15886599 requires both `version-parity` AND `json-validate`.
- `scripts/doctor.sh` exits 0; `uv run pytest` green; `/work-ticket` and `/sprint-status` invocations resolve.
- A `feature/framework-align-gembaflow-v1.5.0` PR is merged to `main`.

**Labels for the epic issue:** `epic`, `epic/masterkey-rename`, `phase/0`, `type:framework`, `type:infra`, `safety`, `P0`

(Reuse `phase/0` label per the user's note that overload is OK since this is "pre-phase-0".)

**Rollback point:** RB-(-1) (revert sync PR + restore `.agile-flow-*` filenames via `git mv` reversal).

---

## Tickets

Seven tickets. Sequence is load-bearing: E0-T1 (snapshot) blocks E0-T2 (bridge edits) blocks E0-T3 (curl refresh) blocks E0-T4 (sync) blocks E0-T5 (overrides reconcile) blocks E0-T6 (doc strings + branch-protection) blocks E0-T7 (verification).

E0-T2 and E0-T3 could in theory parallelize but in practice they're 30 minutes of work total and the operator should do them sequentially to keep the mental model clean.

---

### E0-T1 — `chore: Snapshot pre-rebrand state and capture v1.3.0 baseline`

**Problem Statement:** Phase -1 rollback (RB-(-1)) requires the pre-Phase-(-1) git SHA AND a copy of the v1.3.0 `template-sync.sh` (because that script is itself replaced by the upgrade — there's no on-disk "old version" after step (-1).5 runs). Without these, recovery from a botched sync requires fetching `template-sync.sh` from the now-redirected `vibeacademy/agile-flow` v1.3.0 tag, which works today via GitHub's repo-rename redirect but is one redirect-lapse away from breaking.

**Parent Epic:** E0
**Effort Estimate:** XS
**Priority:** P0

**A. Environment Context**
- Working tree must be clean (`git status` returns no modified files). If not clean: commit pending work to a wip branch first.
- Outputs go to `/tmp/`: `template-sync.v1.3.0.sh`, `agile-flow-version.pre-rebrand.json`, `agile-flow-overrides.pre-rebrand.txt`, `agile-flow-meta-version.pre-rebrand.txt`
- Capture `git rev-parse HEAD` as the pre-Phase-(-1) SHA — record in ticket comment.
- Run the existing `reports/refactor/03-verification.sh` harness to capture pre-rebrand PASS/FAIL state. Some checks may already PASS (e.g., the `CUBROX_TEST_SEED_ENABLED` checks shouldn't be affected by Phase -1 either way) — that's the baseline for "Phase -1 didn't regress anything".

**B. Guardrails**
- Read-only with respect to git and the file tree (snapshots go to `/tmp/`, not the repo).
- Do NOT commit snapshots to the repo — they go to `/tmp/` because (a) they contain framework-template content already on GitHub and (b) we don't want repo history bloat.
- Do NOT run `template-sync.sh` in this ticket — that's E0-T4.

**C. Happy Path**
1. `git status` — confirm clean working tree.
2. `git rev-parse HEAD > /tmp/pre-phase-minus-1.sha`; capture the SHA in ticket comment.
3. `cp scripts/template-sync.sh /tmp/template-sync.v1.3.0.sh`
4. `cp .agile-flow-version /tmp/agile-flow-version.pre-rebrand.json`
5. `cp .agile-flow-overrides /tmp/agile-flow-overrides.pre-rebrand.txt`
6. `cp .agile-flow-meta/version /tmp/agile-flow-meta-version.pre-rebrand.txt`
7. `bash reports/refactor/03-verification.sh > /tmp/verification.pre-rebrand.txt 2>&1` (or whichever invocation runs the full pre-rename harness — confirm via runbook). Record PASS/FAIL counts in ticket comment.
8. Create branch: `git checkout -b feature/framework-align-gembaflow-v1.5.0`.

**D. Definition of Done**
- All 4 snapshot files exist at the `/tmp/` paths above.
- Pre-Phase-(-1) SHA recorded in ticket comment.
- Pre-rebrand verification harness output saved; PASS/FAIL counts recorded in ticket comment.
- Branch `feature/framework-align-gembaflow-v1.5.0` checked out from `main`.

**Dependencies:** None (epic starter)
**Plan reference:** §3 Phase -1 step (-1).1
**Verification check:** Indirect — establishes the baseline that E0-T7 compares against.
**Labels:** `epic/masterkey-rename`, `phase/0`, `type:framework`, `safety`, `P1`

---

### E0-T2 — `chore: Bridge-edit local scripts/template-sync.sh paths (.agile-flow-* → .gembaflow-*)`

**Problem Statement:** Our v1.3.0 `scripts/template-sync.sh` has hardcoded references to `.agile-flow-version` (line 35), `.agile-flow-overrides` (line 36), and `.agile-flow-meta` (line 422-424). When we run the actual sync in E0-T4, the script we're running THEN is the v1.5.0 version (curl'd in E0-T3) which uses `.gembaflow-*` paths natively. But the v1.3.0 script may need to be sane for any read-only diagnostics between now and E0-T3 — and the line 34 `UPSTREAM_REPO="vibeacademy/gembaflow"` is already correct, so the rest of the file is consistently labelled. Bridge edit is technically optional but improves the mental model and is a 6-line change that takes 2 minutes.

**Parent Epic:** E0
**Effort Estimate:** XS
**Priority:** P1

**A. Environment Context**
- File: `scripts/template-sync.sh`
- Lines to edit (verify line numbers haven't drifted since the task brief):
  - Line 2: comment `Sync framework files from vibeacademy/agile-flow releases.` → `vibeacademy/gembaflow`
  - Line 5: comment `(.agile-flow-version)` → `(.gembaflow-version)`
  - Line 6: comment `.agile-flow-overrides` → `.gembaflow-overrides`
  - Line 34: already correct (`UPSTREAM_REPO="vibeacademy/gembaflow"`) — verify, don't edit
  - Line 35: `VERSION_FILE=".agile-flow-version"` → `".gembaflow-version"`
  - Line 36: `OVERRIDES_FILE=".agile-flow-overrides"` → `".gembaflow-overrides"`
  - Lines 422-424: `.agile-flow-meta` → `.gembaflow-meta` (3 occurrences in the mkdir + echo + git-add sequence)
- Other line numbers in plan §3 Phase -1 "What changes" item 3 — re-verify in case our local copy has drifted.

**B. Guardrails**
- Do NOT rename the actual metadata files in this ticket — that's done automatically by the v1.5.0 sync script's migration block in E0-T4.
- Do NOT change line 34 `UPSTREAM_REPO`; it's already `vibeacademy/gembaflow`.
- Do NOT commit yet — let E0-T3 fold its curl-refresh changes into the same commit. The expected `git diff` after this ticket is just the path string edits.

**C. Happy Path**
1. Confirm line numbers: `grep -n -E "agile-flow|gembaflow|VERSION_FILE|OVERRIDES_FILE|\.agile-flow-meta" scripts/template-sync.sh | head -20`
2. Apply the 6 edits above via `Edit` tool or sed.
3. `bash scripts/template-sync.sh --dry-run` (if `--dry-run` flag exists in v1.3.0; if not, skip — v1.3.0's `template-sync.sh` may not have `--dry-run`). The expected behavior: script reads `.agile-flow-version` (still exists, not yet renamed) but the path is now `.gembaflow-version` — so this WILL ERROR with "VERSION_FILE not found". That's expected and confirms the script wiring works.
4. Stage the edits but do NOT commit yet (let E0-T3 batch).

**D. Definition of Done**
- `grep -c "\.agile-flow-" scripts/template-sync.sh` returns 0 (no remaining `.agile-flow-` paths in the file).
- `grep -c "\.gembaflow-" scripts/template-sync.sh` returns ≥ 5 (the 5 edited path constants).
- Line 34 still reads `UPSTREAM_REPO="vibeacademy/gembaflow"` (untouched).

**Dependencies:** Blocked by: E0-T1. Blocks: E0-T3.
**Plan reference:** §3 Phase -1 step (-1).3
**Verification check:** Verified indirectly via E0-T4 (the sync run reads these paths)
**Labels:** `epic/masterkey-rename`, `phase/0`, `type:framework`, `risk:destructive` (edits a runtime-protected script), `P1`

---

### E0-T3 — `chore: Manual curl-refresh of runtime-protected scripts (v1.5.0 release-notes mandate)`

**Problem Statement:** Per upstream v1.5.0 release notes "Propagation note" section: existing forks at v1.4.0 or earlier require a one-time manual `curl` refresh of `scripts/template-sync.sh` and `scripts/lib/overrides.sh` on first `/upgrade` to v1.5.0. Our fork is on v1.3.0 (even older). The reason: v1.3.0's sync script lacks the post-loop self-heal mechanism (#371 / #486), so the upgrade pipeline cannot deliver itself — it would pull every other v1.5.0 file but leave the two runtime-protected scripts at their pre-v1.5.0 versions.

This is the keystone Phase -1 step. If it silently fails (R18), step E0-T4's sync runs the OLD code and produces dual-state.

**Parent Epic:** E0
**Effort Estimate:** XS
**Priority:** P0

**A. Environment Context**
- Network access to `raw.githubusercontent.com` required.
- Files refreshed: `scripts/template-sync.sh`, `scripts/lib/overrides.sh`
- Verification gate: `grep -c "Self-healing post-sync refresh" scripts/template-sync.sh` MUST return exactly `1`

**B. Guardrails**
- Use `curl -fsSL`: `-f` fails on HTTP error (404 returns exit 22), `-s` silent, `-S` show errors, `-L` follow redirects.
- Do NOT use a different tag than `v1.5.0`. Do NOT use `main` (which may have post-v1.5.0 changes that aren't in the synced tarball).
- If the grep gate fails, ABORT this ticket and re-curl. Do NOT proceed to E0-T4 with a half-refreshed script.

**C. Happy Path**
1. Run the release-notes-specified commands exactly:
   ```bash
   curl -fsSL "https://raw.githubusercontent.com/vibeacademy/gembaflow/v1.5.0/scripts/template-sync.sh" -o scripts/template-sync.sh
   curl -fsSL "https://raw.githubusercontent.com/vibeacademy/gembaflow/v1.5.0/scripts/lib/overrides.sh" -o scripts/lib/overrides.sh
   chmod +x scripts/template-sync.sh
   ```
2. **Verification gate:**
   ```bash
   grep -c "Self-healing post-sync refresh" scripts/template-sync.sh
   ```
   MUST return `1`. If `0`: re-curl; if still `0` after re-curl: investigate (release tag may have moved or upstream file structure changed).
3. Verify upstream URL line is correct: `grep -n "UPSTREAM_REPO" scripts/template-sync.sh` → expect `vibeacademy/gembaflow`.
4. Inspect first 60 lines of the new script: confirm the auto-migration block (`migrate_legacy_dotfiles`) is present.
5. Commit: `git add scripts/template-sync.sh scripts/lib/overrides.sh && git commit -m "chore(sync): manual refresh of runtime-protected scripts for v1.5.0 (per release notes)"`. Per release notes' verbatim commit message — `template-sync.yml` or other scripts may pattern-match it.
6. The bridge edits from E0-T2 are now moot (overwritten by the curl); that's expected.

**D. Definition of Done**
- Both files refreshed; `scripts/template-sync.sh` has `chmod +x`.
- `grep -c "Self-healing post-sync refresh" scripts/template-sync.sh` returns `1`.
- Commit landed on `feature/framework-align-gembaflow-v1.5.0` with exact message from release notes.
- `scripts/template-sync.sh` line 36 (or wherever `UPSTREAM_REPO` lives in v1.5.0) reads `vibeacademy/gembaflow`.

**Dependencies:** Blocked by: E0-T1, E0-T2. Blocks: E0-T4.
**Plan reference:** §3 Phase -1 step (-1).4
**Verification check:** The grep gate above is the canonical verification per release notes.
**Labels:** `epic/masterkey-rename`, `phase/0`, `type:framework`, `risk:destructive` (replaces runtime-protected scripts wholesale), `P0`

---

### E0-T4 — `chore: Run template-sync.sh — actual v1.3.0 → v1.5.0 upgrade`

**Problem Statement:** With the v1.5.0 sync script now in place (post-E0-T3), execute the actual upgrade. The new script's early one-time migration block does the `git mv .agile-flow-version .gembaflow-version` (and same for `.agile-flow-meta/`, `.agile-flow-overrides`), then proceeds with the normal sync of `syncDirectories` from the v1.5.0 tarball. Review the resulting branch's diff carefully before merge — the diff will be large (28 PRs of upstream changes between v1.3.0 and v1.5.0).

**Parent Epic:** E0
**Effort Estimate:** M (review-heavy)
**Priority:** P0

**A. Environment Context**
- Current branch: `feature/framework-align-gembaflow-v1.5.0` with the bridge edits + curl refresh committed.
- Network access required (tarball download).
- The sync may create a sub-branch `gembaflow-sync/v1.5.0` (per `template-sync.sh` line 388 in v1.5.0) or may apply directly to the current branch — depends on script behavior. Read terminal output carefully.
- Expected new syncDirectories per upstream `.gembaflow-version`: `.claude/modes/` and `features/` (added in v1.4+). Local fork doesn't have these yet — new directories will appear.

**B. Guardrails**
- Do NOT review the diff casually — there are 28 upstream PRs worth of change. Use a structured walkthrough: agents first (look for renames), commands second (look for new placeholders), scripts third (look for new files we may need to wire up in our deploy workflows), docs last (lowest stakes for this fork).
- Do NOT merge yet — E0-T5 reconciles overrides; E0-T6 lands doc string updates; E0-T7 is the verification gate. Merge happens only after E0-T7 passes.
- Do NOT delete the `gembaflow-sync/v1.5.0` sub-branch (if created) until the work is merged — recovery may need to reset onto it.

**C. Happy Path**
1. `bash scripts/template-sync.sh` (no `--dry-run`; this is the real run).
2. Watch terminal output for:
   - "migrating .agile-flow-version -> .gembaflow-version (one-time, Phase 4 rebrand)" (and 2 similar lines for meta + overrides)
   - "Self-healing post-sync refresh" block firing (or marking no changes)
   - Tarball download success
   - File copy count
   - Branch name created (capture)
3. Verify auto-migration: `ls -la .gembaflow-version .gembaflow-overrides .gembaflow-meta/ 2>&1` — all 3 exist. `ls -la .agile-flow-* 2>&1` — all return "No such file or directory".
4. Verify version bump: `grep '"version"' .gembaflow-version` shows `1.5.0`.
5. `git status` — review file list. Categorize:
   - Renames (R: `.agile-flow-*` → `.gembaflow-*`)
   - New files (e.g., `.gembaflow-config.example.json`, `.claude/modes/*`, `features/*`, new ADRs, new docs)
   - Modified files (every file under `.claude/` and `scripts/` that's not in overrides)
   - Removed files (per release notes: `scripts/test-report-issue.sh`, `docs/reports/report-issue-acceptance-template.html`)
6. `git diff --stat` — summary metrics; record in ticket comment.
7. Spot-check 3 agent files (e.g., `github-ticket-worker.md`): they should be UNCHANGED locally because they're in `.gembaflow-overrides` (auto-migrated from `.agile-flow-overrides`).

**D. Definition of Done**
- `.agile-flow-version`, `.agile-flow-overrides`, `.agile-flow-meta/` all GONE (renamed to `.gembaflow-*`).
- `.gembaflow-version` `version` field is `1.5.0`.
- `.gembaflow-config.example.json` present in working tree.
- Files in `.gembaflow-overrides` (carrying forward from old `.agile-flow-overrides`) are unchanged locally.
- Working tree shows the sync changes staged or in a sub-branch; no fatal errors in terminal output.
- Ticket comment captures: branch name (if sub-branch created), `git diff --stat` summary, list of removed files, list of new directories.

**Dependencies:** Blocked by: E0-T3. Blocks: E0-T5.
**Plan reference:** §3 Phase -1 step (-1).5
**Verification check:** Direct — script self-reports migration; manual ls confirms; E0-T7 is the final gate.
**Labels:** `epic/masterkey-rename`, `phase/0`, `type:framework`, `type:infra`, `risk:destructive` (runs `git mv` and overwrites ~hundreds of files), `P0`

---

### E0-T5 — `chore: Reconcile .gembaflow-overrides against post-sync file list; create .gembaflow-config.json`

**Problem Statement:** Two things go wrong if this ticket is skipped:
1. **R16:** `.gembaflow-overrides` was `git mv`'d from `.agile-flow-overrides` byte-for-byte. Every path listed must still exist post-sync; if upstream renamed `.claude/agents/devops-engineer.md` to `.claude/agents/platform-engineer.md` between v1.3.0 and v1.5.0, the overrides line silently no-ops and the upstream file lands without protection.
2. **R17:** v1.5.0's `.claude/commands/work-ticket.md` and `drain.md` contain `{{org}}`, `{{board.id}}`, `{{bot.worker}}`, `{{bot.reviewer}}` placeholders that `scripts/substitute-config-placeholders.sh` (new in v1.5.0) substitutes at bootstrap. Without `.gembaflow-config.json` populated, the substitution can't run — every `/work-ticket` invocation reads literal `{{org}}` placeholder text.

**Parent Epic:** E0
**Effort Estimate:** S
**Priority:** P0

**A. Environment Context**
- File to audit: `.gembaflow-overrides` (auto-migrated from `.agile-flow-overrides` in E0-T4)
- New file to create: `.gembaflow-config.json` (copied from `.gembaflow-config.example.json`, fields populated)
- New script to run: `scripts/substitute-config-placeholders.sh` (shipped in v1.5.0 by #478)
- Reference for placeholder values: `docs/PLATFORM-GUIDE.md` "Bootstrap-time templated values" section (synced in by E0-T4)
- Upstream's own `.gembaflow-overrides` (verified via `gh api repos/vibeacademy/gembaflow/contents/.gembaflow-overrides?ref=v1.5.0`) lists `.gembaflow-meta/` and `.claude/commands/work-ticket.md` — consider adding to our local file.

**B. Guardrails**
- Do NOT remove the existing 17 paths from `.gembaflow-overrides` without checking each one against the current file tree.
- Do NOT add a path to overrides unless the file (a) exists and (b) is fork-customized (otherwise we just freeze our local copy on a moving target).
- Do NOT commit `.gembaflow-config.json` to the repo if it contains bot-account credentials (it shouldn't — those are bot HANDLES not tokens, but be deliberate). Two options: (a) commit checked-in default + `.gitignore` a `.local.json` override, OR (b) `.gitignore` `.gembaflow-config.json` itself and document the per-operator setup. **Recommend (a)** for solo-mode simplicity — solo-mode means `org=cubrox`, `bot.worker=cubrox`, `bot.reviewer=cubrox`, all public information.
- For solo-mode: `bot.worker` and `bot.reviewer` both equal the operator's GitHub handle (per `CLAUDE.md` "Account model" section).

**C. Happy Path**
1. **Audit each line in `.gembaflow-overrides`:**
   ```bash
   while IFS= read -r line; do
     [[ "$line" =~ ^#.*$ || -z "$line" ]] && continue
     if [ ! -e "$line" ]; then
       echo "MISSING: $line"
     fi
   done < .gembaflow-overrides
   ```
   For each MISSING line: `git log --diff-filter=R --follow -- <path>` upstream to find the rename target (use `gh api` against `vibeacademy/gembaflow` if local clone of upstream isn't available). Update the overrides line. Re-apply our customizations to the new path. Commit.
2. **Add upstream-recommended overrides** if not already present:
   - `.gembaflow-meta/` — already implicit via the legacy line, but make explicit.
   - `.claude/commands/work-ticket.md` — protects substituted placeholders from being reverted to `{{org}}` etc. on next sync.
3. **Create `.gembaflow-config.json`:**
   ```bash
   cp .gembaflow-config.example.json .gembaflow-config.json
   ```
   Edit the 4 fields:
   - `org`: `cubrox` (for now — Phase 2 of masterkey rename keeps it as `cubrox`, this is the GitHub owner)
   - `board.id`: `29` (current legacy `vibeacademy/projects/29` — to be updated to the new cubrox-user board in masterkey Phase 2 step 18)
   - `bot.worker`: operator's GitHub handle (solo-mode)
   - `bot.reviewer`: operator's GitHub handle (solo-mode)
4. **Run substitution:**
   ```bash
   bash scripts/substitute-config-placeholders.sh
   bash scripts/substitute-config-placeholders.sh --check
   ```
   The `--check` mode (per release notes #478) returns non-zero if placeholders remain.
5. **Verify:**
   ```bash
   grep -nE '\{\{(org|board\.id|bot\.worker|bot\.reviewer)\}\}' .claude/commands/work-ticket.md .claude/commands/drain.md
   ```
   Expect 0 hits.
6. Commit: `chore(sync): reconcile .gembaflow-overrides post-rebrand; create .gembaflow-config.json`.

**D. Definition of Done**
- Every path listed in `.gembaflow-overrides` exists on disk.
- `.gembaflow-config.json` exists with all 4 fields populated.
- `bash scripts/substitute-config-placeholders.sh --check` exits 0.
- `grep -E '\{\{.*\}\}' .claude/commands/work-ticket.md` returns 0 hits.
- Decision recorded in ticket comment re: gitignore of `.gembaflow-config.json` (vs. checked-in).

**Dependencies:** Blocked by: E0-T4. Blocks: E0-T6.
**Plan reference:** §3 Phase -1 step (-1).6
**Verification check:** `substitute-config-placeholders.sh --check` is the canonical gate.
**Labels:** `epic/masterkey-rename`, `phase/0`, `type:framework`, `P1`

---

### E0-T6 — `docs: Update Agile Flow → Gemba Flow strings in CLAUDE.md, UPSTREAM.md, VERSIONING.md; add json-validate to branch-protection`

**Problem Statement:** Three local doc files reference the old framework name "Agile Flow" and the old upstream URL `vibeacademy/agile-flow`. These are local docs (NOT in `syncDirectories` for the most part — `CLAUDE.md` is in the upstream tree but our local copy is heavily customized, and `UPSTREAM.md` / `VERSIONING.md` are local-only) so the edits stick. Additionally, the v1.5.0 release notes mandate that branch-protected forks add `json-validate` to the required-status-checks list on the main ruleset.

**CAREFUL:** `CLAUDE.md` is in upstream's tree as a template/example, but our local `CLAUDE.md` has been heavily customized with project-specific content. Verify it's listed in `.gembaflow-overrides` (it likely is — if not, edits revert on next sync).

**Parent Epic:** E0
**Effort Estimate:** S
**Priority:** P1

**A. Environment Context**
- Files to edit (local, all 3):
  - `CLAUDE.md` — multiple "Agile Flow" mentions (line 2 header, lines 10/73/80/81 env-var prose), plus `agile-flow-app` example on line 195 (LEAVE — that's the Cloud Run service name, separate concern, handled by masterkey rename Epic 2)
  - `UPSTREAM.md` — every "Agile Flow" → "Gemba Flow"; every `vibeacademy/agile-flow` URL → `vibeacademy/gembaflow`
  - `VERSIONING.md` — same
- **Cross-check:** verify these files are in `.gembaflow-overrides` before editing. If not, edits will be reverted on next `/upgrade`.
- **AGILE_FLOW_* env var names:** the prose in `CLAUDE.md` lines 10/73/80/81 references `AGILE_FLOW_WORKER_ACCOUNT`, `AGILE_FLOW_REVIEWER_ACCOUNT`, `AGILE_FLOW_SOLO_MODE` as the environment variable names. Before flipping to `GEMBAFLOW_*`, check the v1.5.0 `bootstrap-workflow.md` and `.claude/hooks/ensure-github-account.sh` — if upstream still READS the `AGILE_FLOW_*` env names, our prose must continue to document them under those names even though the project is now "Gemba Flow". The rebrand may have been doc-and-metadata only (not env-var-name-touching) — verify before flipping.
- Branch-protection ruleset: id `15886599` (per plan §2.1 row 7); manage via `gh api repos/<owner>/<repo>/rulesets/15886599 --method PUT` or via GitHub UI.

**B. Guardrails**
- Do NOT change `AGILE_FLOW_*` env var NAMES in CLAUDE.md without verifying upstream code still reads them. If upstream code reads the new names, queue a separate ticket to update the env var actually exported in `.devcontainer/devcontainer.json` etc. — out of scope for this ticket.
- Do NOT remove the existing `version-parity` required check when adding `json-validate` — both must be present (per release notes "Fork-maintained files you must update").
- Do NOT touch `docs/PRODUCT-ROADMAP.md` "former internal codename: cubrox" line — that's historical attribution (and covered by masterkey rename §2.6 anyway).
- Do NOT edit any `.claude/agents/*.md` or `.claude/commands/*.md` files in this ticket — that's framework template territory; if those mention "Agile Flow" they'll get updated by the next upstream sync if upstream chose to rename them, otherwise leave alone (the prose in the agent personas is upstream's concern).

**C. Happy Path**
1. **Verify overrides protection** for the 3 local docs:
   ```bash
   for f in CLAUDE.md UPSTREAM.md VERSIONING.md; do grep -F "$f" .gembaflow-overrides && echo "OK: $f" || echo "MISSING: $f"; done
   ```
   If any are MISSING and the file exists in the v1.5.0 upstream tree (`gh api repos/vibeacademy/gembaflow/contents/<file>?ref=v1.5.0`), add them to `.gembaflow-overrides` first.
2. **Check upstream env-var naming:**
   ```bash
   gh api 'repos/vibeacademy/gembaflow/contents/.claude/hooks/ensure-github-account.sh?ref=v1.5.0' --jq '.content' | base64 -d | grep -E "AGILE_FLOW|GEMBAFLOW" | head -10
   ```
   Record finding in ticket comment.
3. **Edit `CLAUDE.md`:**
   - Line 2: `# Agile Flow - Claude Code Project Template` → `# Gemba Flow - Claude Code Project Template`
   - Lines 10/73/80/81: rewrite if upstream env vars are renamed; else leave the env var names but rewrite surrounding "Agile Flow" prose to "Gemba Flow"
4. **Edit `UPSTREAM.md`:** sed-replace `Agile Flow` → `Gemba Flow` (case-preserving — manual review), `vibeacademy/agile-flow` → `vibeacademy/gembaflow`. Keep historical references in CHANGELOG entries as written.
5. **Edit `VERSIONING.md`:** same approach as `UPSTREAM.md`.
6. **Update branch-protection ruleset:**
   ```bash
   gh api 'repos/cubrox/cubrox/rulesets/15886599' --jq '.rules' > /tmp/ruleset-before.json
   # Use jq to add json-validate to required_status_checks, write to /tmp/ruleset-patched.json
   gh api -X PUT 'repos/cubrox/cubrox/rulesets/15886599' --input /tmp/ruleset-patched.json
   gh api 'repos/cubrox/cubrox/rulesets/15886599' --jq '.rules' > /tmp/ruleset-after.json
   diff /tmp/ruleset-before.json /tmp/ruleset-after.json   # confirm json-validate appears
   ```
7. Commit: `docs: rebrand Agile Flow → Gemba Flow in local docs; add json-validate to branch protection`.

**D. Definition of Done**
- `grep -i "agile flow" CLAUDE.md UPSTREAM.md VERSIONING.md` returns 0 hits (except in historical attribution lines, if any are explicit "former name" notes).
- `grep "vibeacademy/agile-flow" UPSTREAM.md VERSIONING.md` returns 0 hits.
- `gh api repos/cubrox/cubrox/rulesets/15886599 --jq '..|.required_status_checks?'` includes both `version-parity` AND `json-validate`.
- All 3 doc files confirmed in `.gembaflow-overrides`.

**Dependencies:** Blocked by: E0-T5. Blocks: E0-T7.
**Plan reference:** §3 Phase -1 step (-1).7 (doc string subset) + v1.5.0 release notes "Fork-maintained files you must update"
**Verification check:** Direct grep; gh api inspection of ruleset.
**Labels:** `epic/masterkey-rename`, `phase/0`, `type:docs`, `type:infra` (branch protection), `P1`

---

### E0-T7 — `chore: Verification, smoke tests, and open PR for framework alignment`

**Problem Statement:** Final gate. Confirm the sync didn't break anything, smoke-test the slash commands that now run under v1.5.0 templated specs, and open the PR for review.

**Parent Epic:** E0
**Effort Estimate:** S
**Priority:** P0

**A. Environment Context**
- All E0-T1 through E0-T6 work committed on `feature/framework-align-gembaflow-v1.5.0`.
- Pre-rebrand verification output saved at `/tmp/verification.pre-rebrand.txt` (from E0-T1).
- Target: `bash scripts/doctor.sh`, `uv run pytest`, `uv run ruff check .`, `uv run mypy app/`, manual smoke of `/work-ticket` and `/sprint-status`.

**B. Guardrails**
- Do NOT merge this PR yourself — humans merge per CLAUDE.md "Critical Rules" #4. PR creation is the deliverable.
- Do NOT bypass `--no-verify` on the push — fix any pre-push hook failures (lint, test).
- If `uv run pytest` finds new failures vs. the pre-rebrand baseline, INVESTIGATE before opening PR. Likely candidates: v1.5.0 introduces a new test that depends on `.gembaflow-config.json` having specific values; or a renamed `.claude/agents/*.md` file is referenced by tests we don't yet know about.

**C. Happy Path**
1. **Doctor:** `bash scripts/doctor.sh` — must exit 0. Note: v1.5.0 added clone-freshness check (#472/#484); expect a new PASS line about being current with origin.
2. **Lint + format + types:** `uv run ruff check . && uv run ruff format --check . && uv run mypy app/` — all green.
3. **Tests:** `uv run pytest` — all green. Compare PASS count against `/tmp/verification.pre-rebrand.txt`; new tests are OK, fewer passes (new failures) is not.
4. **Verification harness:** `bash reports/refactor/03-verification.sh > /tmp/verification.post-phase-minus-1.txt 2>&1`. Diff against pre-rebrand. Expected delta: zero net regressions; any "agile-flow → gembaflow" rename should be neutral with respect to the masterkey-rename harness.
5. **Slash command smoke:**
   - `/work-ticket --help` (or invocation that loads spec without firing) — confirm the spec text has no literal `{{org}}` etc.
   - `/sprint-status` — confirm it resolves and queries the board.
   - `/doctor` — confirm it runs (this is the slash-command equivalent of step 1).
6. **Audit residual `.agile-flow-*` references:**
   ```bash
   grep -rE "\.agile-flow-(version|overrides|meta)" . \
     --include="*.sh" --include="*.md" --include="*.json" --include="*.yml" --include="*.yaml" \
     --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=reports
   ```
   Expect 0 hits. References in `reports/refactor/*.md` and session journals are historical — acceptable.
7. **Open PR:**
   ```bash
   git push -u origin feature/framework-align-gembaflow-v1.5.0
   gh pr create --title "feat(sync): framework alignment — gembaflow v1.5.0 + rebrand" --body "<see template below>"
   ```
   PR body template:
   ```
   ## Summary
   - Rebrand `.agile-flow-*` metadata → `.gembaflow-*` (auto-migrated by v1.5.0 sync script)
   - Upgrade framework v1.3.0 → v1.5.0
   - Create `.gembaflow-config.json` and run placeholder substitution
   - Update Agile Flow → Gemba Flow in local docs (CLAUDE.md, UPSTREAM.md, VERSIONING.md)
   - Add `json-validate` to branch-protection ruleset 15886599

   ## Why this lands before the masterkey-rename Epic 1
   See `reports/refactor/01-architecture-plan.md` §3 Phase -1 "Why this lands before masterkey Phase 0".

   ## Verification
   - [x] `scripts/doctor.sh` exits 0
   - [x] `uv run pytest` green
   - [x] `bash scripts/substitute-config-placeholders.sh --check` exits 0
   - [x] No `.agile-flow-*` metadata file references remain (`grep -r` clean)
   - [x] Branch-protection ruleset 15886599 contains both `version-parity` and `json-validate`
   - [x] `/work-ticket` / `/sprint-status` slash commands smoke-tested

   ## Follow-up
   Closes Epic 0 (Phase -1 framework alignment). Next: enumerate stale `.agile-flow-*` references in existing Epic 1-6 issues (per `reports/refactor/05-epic-0-backlog.md` § "Stale references in existing backlog issues") and patch them so the masterkey-rename Epic 1 work reads cleanly.
   ```

**D. Definition of Done**
- All verification checks above PASS.
- PR opened against `main` with the structured body above.
- Pre-push hook (lint + test) passes without `--no-verify`.
- Ticket comment links to the PR.

**Dependencies:** Blocked by: E0-T6. Blocks: Epic 1 (masterkey Phase 0; issues #181-#191).
**Plan reference:** §3 Phase -1 step (-1).7
**Verification check:** All harness sections + doctor.sh + pytest are the gates.
**Labels:** `epic/masterkey-rename`, `phase/0`, `type:framework`, `safety`, `P0`

---

## Stale references in existing backlog issues

The following existing GitHub issues (#181-#223) contain references to `.agile-flow-overrides`, `.agile-flow-version`, or `.agile-flow-meta` that become stale after Epic 0 lands. **This list is enumeration only — a follow-up agent will do the search-and-replace cleanly. Do NOT edit issue bodies in this ticket.**

**Important distinction:** `agile-flow-app` (Cloud Run service name) and `agile-flow` (Artifact Registry repo name) are NOT stale references — those are the live infrastructure names which continue to be correct through Phase 4 cutover. Only `.agile-flow-overrides` / `.agile-flow-version` / `.agile-flow-meta` METADATA file references become stale.

### Epics (#181-#186)

Counts from `gh issue view <num> --repo cubrox/cubrox --json body --jq .body | grep -c "agile-flow"`:

| Issue | Title | Total `agile-flow` refs | Of which `.agile-flow-*` metadata (stale post-Epic-0) | Of which `agile-flow-app` / `agile-flow` infra (still correct) |
|-------|-------|------------------------:|-------------------------------------------------------:|----------------------------------------------------------------:|
| #181 | epic: Phase 0 — Pre-flight | 0 | 0 | 0 |
| #182 | epic: Phase 1 — Codebase rename PR | 3 | 2 (`.agile-flow-overrides` twice in summary) | 1 (`agile-flow-app` Cloud Run service) |
| #183 | epic: Phase 2 — Repo rename, board migration, WIF | 0 | 0 | 0 |
| #184 | epic: Phase 3 — Pre-create masterkey infra | 2 | 0 | 2 (`agile-flow-app` Cloud Run service) |
| #185 | epic: Phase 4 — Cutover | 2 | 0 | 2 (`agile-flow-app` Cloud Run service) |
| #186 | epic: Phase 5 — Cleanup | 5 | 2 (`.agile-flow-overrides` in deferred-followup + acceptance) | 3 (`agile-flow-app` service + `agile-flow` AR repo + URL) |

**Epics needing body patches:** #182, #186. (4 total stale `.agile-flow-overrides` references across both.)

### Tickets (#187-#223 — scanned from `reports/refactor/04-backlog.md` per source-of-truth)

Pattern: `awk '/^#### E[1-6]-T[0-9]+/{cur=$2} /\.agile-flow-(overrides|version|meta)/{print cur}' reports/refactor/04-backlog.md | sort -u`

| Ticket | Issue # | Title (abbrev) | Stale-ref count | Where |
|--------|--------:|----------------|----------------:|-------|
| E2-T5 | #196 | Rename provision-gcp-project.sh and diagnose-cloudrun.sh defaults | 4 | Problem Statement + Env Context + Guardrails + Definition of Done all reference `.agile-flow-overrides` |
| E2-T7 | #198 | Apply .agile-flow-overrides agent persona renames + PROJECT.md Supabase fix | 5 | **Including the TITLE** — `refactor: Apply .agile-flow-overrides agent persona renames…` — plus Problem Statement, Env Context (2 mentions), Happy Path |
| E5-T7 | #216 | Announce new production URL and update external references | 1 | Guardrails: "Do NOT update upstream-synced framework docs unless added to `.agile-flow-overrides`" |
| E6-T7 | #223 | Write ADR-007 + resolve PLATFORM-GUIDE drift | 3 | Problem Statement + Happy Path + Definition of Done all reference `.agile-flow-overrides` |

**Tickets needing body patches:** #196, #198, #216, #223. (13 total stale `.agile-flow-overrides` references.)

**E2-T7 (#198) title needs patching** — this is the only ticket where the title itself contains a stale reference. The follow-up agent will need to rename the issue title via `gh issue edit 198 --title "refactor: Apply .gembaflow-overrides agent persona renames and PROJECT.md Supabase fix"`.

### Search-and-replace pattern for the follow-up agent

```bash
# For each affected issue, fetch body, sed-replace, re-post:
for num in 182 186 196 198 216 223; do
  gh issue view $num --repo cubrox/cubrox --json body --jq .body \
    | sed \
        -e 's|\.agile-flow-overrides|.gembaflow-overrides|g' \
        -e 's|\.agile-flow-version|.gembaflow-version|g' \
        -e 's|\.agile-flow-meta|.gembaflow-meta|g' \
    > /tmp/issue-$num-body.patched.md
  # Then: gh issue edit $num --repo cubrox/cubrox --body-file /tmp/issue-$num-body.patched.md
done
# Title patch (E2-T7 / #198 only):
gh issue edit 198 --repo cubrox/cubrox \
  --title "refactor: Apply .gembaflow-overrides agent persona renames and PROJECT.md Supabase fix"
```

**Do NOT** also sed-replace `agile-flow-app` or bare `agile-flow` — those are infrastructure names handled separately by Epics 5 and 6.

### Source-of-truth doc patching

`reports/refactor/04-backlog.md` itself has 17 `.agile-flow-overrides` references (per `grep -nE "\.agile-flow-(overrides|version|meta)" reports/refactor/04-backlog.md | wc -l`). After Epic 0 lands, the same sed-replace pattern should be applied to that file in a separate doc-only commit on the Epic-0 PR or a follow-up. This keeps the backlog doc consistent with the patched issue bodies.

---

**Result:** Epic 0 backlog drafted (7 tickets E0-T1 through E0-T7).
Recommendation: load tickets in dependency order; do not start Epic 1 (#181-#191) until E0-T7's PR has merged.
Stale references to clean up: 6 GitHub issues + the backlog source-of-truth doc.
