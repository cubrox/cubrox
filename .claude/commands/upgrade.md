---
description: "Upgrade Gemba Flow framework files to the latest release"
---

# /upgrade — Gemba Flow Framework Upgrade

Check for a newer version of Gemba Flow and sync framework files from the
latest upstream release. User content is never modified.

## Flags

- `--skip-audit` — skip the local-customizations audit step (#3). Useful
  for automated re-runs in CI where operator confirmation is not
  available.

## Instructions

1. **Verify clean working tree** — run `git status --porcelain`. If there are
   uncommitted changes, STOP and report:

   ```
   Your working tree has uncommitted changes. Please commit or stash them
   before upgrading:
     git stash
     /upgrade
   ```

2. **Verify GitHub CLI authentication** — run `gh auth status`. If not
   authenticated, STOP and report:

   ```
   GitHub CLI is not authenticated. Run:
     gh auth login
   ```

3. **Audit local customizations** — unless `--skip-audit` was passed, run:

   ```bash
   bash scripts/audit-local-customizations.sh
   ```

   The script surfaces framework-controlled files (paths under
   `syncDirectories`) that have been modified locally since the fork was
   bootstrapped and are NOT in `.gembaflow-overrides`. These are the
   files at silent-clobber risk on the next sync.

   - If the audit prints "No framework-controlled files have been
     modified..." or "All ... locally-modified framework file(s) are
     already covered", proceed to step 4.
   - If the audit lists unprotected paths, PROMPT the operator:

     ```
     The audit surfaced N file(s) at clobber risk. Continue without
     adding them to .gembaflow-overrides? [y/N]:
     ```

     - Operator answers `y` (or `yes`): proceed to step 4.
     - Operator answers `N` / no / anything else: STOP. Suggest the
       operator add the relevant paths to `.gembaflow-overrides` first,
       commit, then re-run `/upgrade`.

   The audit step never modifies `.gembaflow-overrides` itself — that's
   an explicit operator choice, not automated.

4. **Run the sync script**:

   ```bash
   bash scripts/template-sync.sh
   ```

5. **Parse the output** and report what happened. The script will print one of:

   - **Already up to date** — no action needed.
   - **Update available: X -> Y** followed by file-level ADDED/UPDATED/SKIP
     lines and a PR URL.
   - **ERROR** — report the error message to the user.

6. **If a PR was created**, remind the user:

   ```
   A sync PR has been created. Review the changes, then merge when ready:
     gh pr view <PR_NUMBER> --web
   ```

## Rollback

Before any file mutation, `template-sync.sh` creates a local-only tag named
`pre-upgrade-YYYYMMDD-HHMMSS` pointing at HEAD. The script's final summary
prints the exact recovery command, for example:

```
Rollback: git reset --hard pre-upgrade-20260511-213045
```

If the sync PR contains a broken file, an unwanted upstream change, or a
lost customization, recover with:

```bash
git reset --hard pre-upgrade-YYYYMMDD-HHMMSS
```

Tags are **not pushed to the remote** — they stay local so upstream tag
namespaces remain clean. List your local rollback points anytime:

```bash
git tag --list 'pre-upgrade-*'
```

If the sync PR has already been merged to `main`, the rollback approach is
to `git revert` the merge commit on a new branch instead — the local tag
only restores your local working tree, not the published merge.

## Important

- This command calls `scripts/template-sync.sh` as-is. Do not modify the script.
- The sync only updates framework-controlled files. User content (app code,
  config customizations, product docs) is never touched. See
  [DISTRIBUTION.md](../../docs/DISTRIBUTION.md) for the full classification.
- The created PR requires human review and merge. Do not auto-merge.
- For details on what gets synced and troubleshooting, see
  [UPGRADING.md](../../docs/UPGRADING.md).

### Output Format

End your output with a Result Block:

```
---

**Result:** Upgrade complete
From: v0.9.0
To: v1.0.0
PR: #42 — chore(sync): update Gemba Flow framework to v1.0.0
Action: Review and merge the PR to finalize the upgrade
```

Or if already up to date:

```
---

**Result:** Already up to date
Version: v0.9.0
```
