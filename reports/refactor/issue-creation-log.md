# Refactor Backlog → Issue Creation Log

**Date:** 2026-06-29
**Source:** `reports/refactor/04-backlog.md`
**Repo:** `cubrox/cubrox`
**Project:** `https://github.com/users/cubrox/projects/2`
**Account:** `tck517` (verified `gh auth status --active`)

## Epics (pre-existing)

| Epic | Issue # |
|------|---------|
| E1 (Phase 0) | #181 |
| E2 (Phase 1) | #182 |
| E3 (Phase 2) | #183 |
| E4 (Phase 3) | #184 |
| E5 (Phase 4) | #185 |
| E6 (Phase 5) | #186 |

## Ticket creation

All 37 tickets created via `gh issue create --repo cubrox/cubrox --body-file <tmp>`.
All 37 added to project board #2 via `gh project item-add 2 --owner cubrox --url ...`.

| Doc ID | Title                                                                                       | Issue # | Project add |
|--------|---------------------------------------------------------------------------------------------|---------|-------------|
| E1-T1  | chore: Inventory legacy vibeacademy/projects/29 board items                                  | #187    | OK          |
| E1-T2  | chore: Snapshot Cloud Run service + revisions + SA IAM + secrets                             | #188    | OK          |
| E1-T3  | chore: Verify WIF binding shape against provisioning script                                  | #189    | OK          |
| E1-T4  | chore: Enumerate Cloud Logging metrics, alerts, dashboards                                   | #190    | OK          |
| E1-T5  | chore: Confirm zero open PRs + enumerate forks, then bundle Phase 0 snapshots into PR        | #191    | OK          |
| E2-T1  | refactor: Rename CUBROX_TEST_SEED_ENABLED env var across code, tests, ci.yml                 | #192    | OK          |
| E2-T2  | refactor: Rename window.cubroxLineCount -> window.masterkeyLineCount                         | #193    | OK          |
| E2-T3  | refactor: Rename app metadata strings (FastAPI title, metric prog name, docstrings)          | #194    | OK          |
| E2-T4  | refactor: Rename tests/a11y package and update fixture URLs                                  | #195    | OK          |
| E2-T5  | refactor: Rename scripts/provision-gcp-project.sh and scripts/diagnose-cloudrun.sh defaults  | #196    | OK          |
| E2-T6  | docs: Update supabase/config.toml project_id and CLAUDE.md project information block         | #197    | OK          |
| E2-T7  | refactor: Apply .agile-flow-overrides agent persona renames and PROJECT.md Supabase fix      | #198    | OK          |
| E2-T8  | chore: Disable synthetic monitor schedule for cutover window                                 | #199    | OK          |
| E3-T1  | infra: Dual-write WIF binding for cubrox/masterkey on deployer SA                            | #200    | OK          |
| E3-T2  | infra: Rename GitHub repo cubrox/cubrox -> cubrox/masterkey                                  | #201    | OK          |
| E3-T3  | infra: Create new project board at github.com/users/cubrox/projects/<n>                      | #202    | OK          |
| E3-T4  | chore: Migrate all 67 items (open + closed) from vibeacademy/projects/29 to new board        | #203    | OK          |
| E4-T1  | infra: Create masterkey Artifact Registry repo + grant runtime SA reader                     | #204    | OK          |
| E4-T2  | infra: Pre-create Cloud Run masterkey service with correct env-var types (R13)               | #205    | OK          |
| E4-T3  | docs: Capture new service URL and pin into LAUNCH-CHECKLIST + CLAUDE.md                      | #206    | OK          |
| E4-T4  | chore: Add new production + preview Supabase Auth redirect URLs to allowlist                 | #207    | OK          |
| E4-T5  | test: Dry-run preview-deploy + preview-cleanup + Supabase branching against masterkey        | #208    | OK          |
| E4-T6  | chore: Verify Supabase GitHub App allowlist still contains cubrox/masterkey                  | #209    | OK          |
| E5-T1  | release: Merge Phase 1 PR with vars STILL pointing at agile-flow-app                         | #210    | OK          |
| E5-T2  | verify: Confirm agile-flow-app health post-merge before var flip                             | #211    | OK          |
| E5-T3  | infra: Flip GitHub vars (CLOUD_RUN_SERVICE + ARTIFACT_REPO) to masterkey                     | #212    | OK          |
| E5-T4  | release: Push trivial CHANGELOG commit to trigger deploy to masterkey                        | #213    | OK          |
| E5-T5  | verify: Confirm masterkey service health after first real deploy                             | #214    | OK          |
| E5-T6  | chore: Re-enable synthetic monitor schedule (follow-up PR)                                   | #215    | OK          |
| E5-T7  | docs: Announce new production URL and update external references                             | #216    | OK          |
| E6-T1  | infra: Delete old Cloud Run service agile-flow-app                                           | #217    | OK          |
| E6-T2  | infra: Archive image manifests + delete old Artifact Registry repo agile-flow                | #218    | OK          |
| E6-T3  | chore: Remove old Supabase Auth allowlist entries (production + preview)                     | #219    | OK          |
| E6-T4  | infra: Remove old WIF binding for cubrox/cubrox on deployer SA                               | #220    | OK          |
| E6-T5  | chore: Update Cloud Logging saved queries / dashboards / alerts (likely no-op)               | #221    | OK          |
| E6-T6  | chore: Memory MCP audit - rename or alias cubrox entities                                    | #222    | OK          |
| E6-T7  | docs: Write ADR-007 "Rename to Master Key / masterkey" and resolve PLATFORM-GUIDE drift      | #223    | OK          |

## Second-pass: ETBD-E?-T? -> #NNN substitution

Built map `{E1-T1 -> 187, ..., E6-T7 -> 223}` and ran `python3 /tmp/refactor-issues/patch.py`.
Special-case handled: `ALL ETBD-E2-Tx` (in E3-T2 / #201) expanded to all eight E2 issue numbers.

| Doc ID | Issue # | Result            | Substitutions |
|--------|---------|-------------------|---------------|
| E1-T1  | #187    | no-patches-needed | 0             |
| E1-T2  | #188    | no-patches-needed | 0             |
| E1-T3  | #189    | no-patches-needed | 0             |
| E1-T4  | #190    | no-patches-needed | 0             |
| E1-T5  | #191    | PATCHED           | 4             |
| E2-T1  | #192    | no-patches-needed | 0             |
| E2-T2  | #193    | no-patches-needed | 0             |
| E2-T3  | #194    | no-patches-needed | 0             |
| E2-T4  | #195    | no-patches-needed | 0             |
| E2-T5  | #196    | no-patches-needed | 0             |
| E2-T6  | #197    | PATCHED           | 1             |
| E2-T7  | #198    | no-patches-needed | 0             |
| E2-T8  | #199    | PATCHED           | 1             |
| E3-T1  | #200    | PATCHED           | 2             |
| E3-T2  | #201    | PATCHED           | 5             |
| E3-T3  | #202    | PATCHED           | 2             |
| E3-T4  | #203    | PATCHED           | 2             |
| E4-T1  | #204    | PATCHED           | 1             |
| E4-T2  | #205    | PATCHED           | 1             |
| E4-T3  | #206    | PATCHED           | 1             |
| E4-T4  | #207    | PATCHED           | 1             |
| E4-T5  | #208    | PATCHED           | 3             |
| E4-T6  | #209    | PATCHED           | 2             |
| E5-T1  | #210    | PATCHED           | 2             |
| E5-T2  | #211    | PATCHED           | 2             |
| E5-T3  | #212    | PATCHED           | 2             |
| E5-T4  | #213    | PATCHED           | 2             |
| E5-T5  | #214    | PATCHED           | 2             |
| E5-T6  | #215    | PATCHED           | 2             |
| E5-T7  | #216    | PATCHED           | 1             |
| E6-T1  | #217    | PATCHED           | 3             |
| E6-T2  | #218    | PATCHED           | 1             |
| E6-T3  | #219    | PATCHED           | 1             |
| E6-T4  | #220    | PATCHED           | 2             |
| E6-T5  | #221    | PATCHED           | 2             |
| E6-T6  | #222    | PATCHED           | 1             |
| E6-T7  | #223    | PATCHED           | 1             |

Verification: scanned all 37 created issues with `gh issue view <n> --json body -q .body | grep ETBD` -> zero hits remain.

## Final summary

| Metric                                                                  | Count |
|-------------------------------------------------------------------------|-------|
| Tickets created                                                         | 37    |
| Tickets added to project board #2                                       | 37    |
| Tickets edited in second pass (ETBD-X -> #NNN)                          | 27    |
| Tickets with no placeholders to patch                                   | 10    |
| Total ETBD substitutions applied                                        | 50    |
| Failures                                                                | 0     |

## Label notes

The backlog doc only specifies labels at the epic level; per-ticket label sets were inferred from the parent epic plus the surface each ticket touches (e.g., `type:code` for `app/` edits, `type:ci-cd` for `.github/workflows/*`, `type:framework` for `.agile-flow-overrides`/`.claude/` edits, `type:infra` for `gcloud`/Cloud Run actions, `type:docs`/`documentation` for doc-only tickets, `area/auth` for Supabase Auth allowlist work, `area/ops` for shell-scripts, `synthetic-monitor` for monitor-touching tickets, `verifies:G` for tickets that exercise harness section G). Every ticket carries `epic/masterkey-rename` + appropriate `phase/N` + appropriate priority label (`P0`/`P1`/`P2`) as required. All labels confirmed present in the repo via `gh label list --repo cubrox/cubrox --limit 100`; no new labels invented.

## Artifacts

- Body files: `/tmp/refactor-issues/E?-T?.md` (37 files, one per ticket)
- Patched bodies (post-substitution): `/tmp/refactor-issues/patched-E?-T?.md` (27 files)
- Patcher script: `/tmp/refactor-issues/patch.py`
