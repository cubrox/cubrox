# Upgrading Agile Flow

This guide explains how to update your project to a newer version of the
Agile Flow framework. Upgrades only touch framework-controlled files (agents,
commands, hooks, skills, scripts). Your application code, product docs, and
configuration customizations are never modified.

For the full list of what is and is not touched during an upgrade, see
[DISTRIBUTION.md](DISTRIBUTION.md).

---

## Check Your Current Version

```bash
jq .version .gembaflow-version
```

The `/doctor` command also checks for updates automatically and warns you if
a newer version is available.

To see all available releases, visit the
[Agile Flow releases page](https://github.com/vibeacademy/agile-flow/releases).

---

## Upgrade Methods

### Option 1: `/upgrade` Command (Recommended)

From Claude Code, run:

```
/upgrade
```

This checks for a newer release, syncs framework files, and opens a pull
request for you to review. You must commit or stash any uncommitted changes
before running the command.

### Option 2: GitHub Actions

1. Go to your repository on GitHub.
2. Click the **Actions** tab.
3. Select the **Template Sync** workflow in the left sidebar.
4. Click **Run workflow** and confirm.

The workflow runs the same sync script and opens a pull request.

---

## What Happens During an Upgrade

1. The sync script fetches the latest release from `vibeacademy/agile-flow`.
2. It compares your local version (from `.gembaflow-version`) to the latest.
3. If an update is available, it downloads the release and copies only the
   directories listed in `syncDirectories` (inside `.gembaflow-version`):
   - `.claude/agents`
   - `.claude/commands`
   - `.claude/hooks`
   - `.claude/skills`
   - `scripts`
   - `starters`
4. It creates a branch (`agile-flow-sync/v{VERSION}`), commits the changes,
   and opens a pull request.
5. Your `.gembaflow-version` file is updated with the new version number.

**Your code is safe.** Application code (`app/`, `__tests__/`), product docs
(`PRODUCT-REQUIREMENTS.md`, `PRODUCT-ROADMAP.md`), deployment config
(`render.yaml`), and other user-content files are never touched.

---

## Reviewing and Merging the Sync PR

1. Open the pull request on GitHub (or run `gh pr view --web`).
2. Review the changed files. The PR body lists every file that was added or
   updated.
3. If everything looks good, click **Squash and merge**.
4. After merging, your project is running the new version.

---

## Troubleshooting

### "Your working tree has uncommitted changes"

Commit or stash your changes before running `/upgrade`:

```bash
git stash
/upgrade
# After the upgrade PR is merged:
git stash pop
```

### "GitHub CLI is not authenticated"

Log in to the GitHub CLI:

```bash
gh auth login
```

### "Could not fetch latest release"

The sync script uses the public GitHub API. This can fail if:

- You have no internet connection.
- The GitHub API is temporarily unavailable.
- You have hit the unauthenticated API rate limit (60 requests/hour).

Wait a few minutes and try again.

### "Branch already exists on remote"

A sync PR for this version was already created. Check your open pull requests:

```bash
gh pr list
```

If the PR is still open, review and merge it. If it was closed without
merging and you want to retry, delete the remote branch first:

```bash
git push origin --delete agile-flow-sync/v{VERSION}
```

### Merge Conflicts

If the sync PR has merge conflicts, it usually means a framework file was
edited locally. To resolve:

1. Check out the sync branch locally:

   ```bash
   gh pr checkout <PR_NUMBER>
   ```

2. Merge main into it and resolve conflicts:

   ```bash
   git merge main
   # Resolve conflicts, keeping the upstream version for framework files
   git add .
   git commit -m "fix: resolve sync merge conflicts"
   git push
   ```

3. Review the PR again and merge.

---

## Manual Upgrade

If the automated sync does not work for your setup, you can upgrade manually:

1. Download the latest release from the
   [releases page](https://github.com/vibeacademy/agile-flow/releases).
2. Extract the archive.
3. Copy the framework directories (`.claude/agents`, `.claude/commands`,
   `.claude/hooks`, `.claude/skills`, `scripts`, `starters`) into your
   project, overwriting existing files.
4. Update the `version` field in `.gembaflow-version` to match the release
   tag.
5. Commit the changes and open a pull request for review.
