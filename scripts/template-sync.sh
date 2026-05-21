#!/usr/bin/env bash
# template-sync.sh -- Sync framework files from vibeacademy/agile-flow releases.
# Called by .github/workflows/template-sync.yml (workflow_dispatch only).
# Guardrails:
#   - Only syncs directories/files listed in syncDirectories (.agile-flow-version)
#   - Respects .agile-flow-overrides — fork-local paths/globs are never touched
#   - Does NOT auto-merge; PR requires human review
#   - Uses unauthenticated GitHub API to fetch release metadata

# If invoked via `sh scripts/template-sync.sh`, re-exec with bash so bash-only
# features below (arrays/process substitution) do not crash at runtime.
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi

main() {
set -euo pipefail

# Check if gh CLI is installed
if ! command -v gh >/dev/null 2>&1; then
  echo "ERROR: GitHub CLI (gh) is not installed."
  echo "Install it from: https://cli.github.com/"
  exit 1
fi

# Check if gh is authenticated
if ! gh auth token >/dev/null 2>&1; then
  echo "ERROR: GitHub CLI is not authenticated."
  echo "Please run: gh auth login"
  echo "Then retry the upgrade command."
  exit 1
fi

UPSTREAM_REPO="vibeacademy/agile-flow"
VERSION_FILE=".agile-flow-version"
OVERRIDES_FILE=".agile-flow-overrides"
RUNNING_SCRIPT_REL=$(python3 -c "import os,sys; print(os.path.relpath(os.path.realpath(sys.argv[1]), os.getcwd()))" "$0")

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/overrides.sh
source "$SCRIPT_DIR/lib/overrides.sh"

# Runtime-critical files must never be overwritten while this script is running.
# The overrides file is user-configurable, so we enforce these guards in code.
RUNTIME_PROTECTED_PATHS=(
  "scripts/template-sync.sh"
  "scripts/lib/overrides.sh"
)

normalize_rel_path() {
  local path="$1"
  while [[ "$path" == ./* ]]; do
    path="${path#./}"
  done
  while [[ "$path" == *"//"* ]]; do
    path="${path//\/\//\/}"
  done
  path="${path%/}"
  printf '%s\n' "$path"
}

is_runtime_protected() {
  local path="$1"
  local normalized_path
  normalized_path="$(normalize_rel_path "$path")"
  local protected
  for protected in "${RUNTIME_PROTECTED_PATHS[@]}"; do
    if [ "$normalized_path" = "$(normalize_rel_path "$protected")" ]; then
      return 0
    fi
  done
  return 1
}

path_allowed_for_bootstrap_reentry() {
  local path="$1"
  local normalized_path
  local protected
  local sync_path

  normalized_path="$(normalize_rel_path "$path")"

  if [ "$normalized_path" = "$(normalize_rel_path "$VERSION_FILE")" ]; then
    return 0
  fi

  for protected in "${RUNTIME_PROTECTED_PATHS[@]}"; do
    if [ "$normalized_path" = "$(normalize_rel_path "$protected")" ] || [[ "$normalized_path" == "$(normalize_rel_path "$protected")/"* ]]; then
      return 0
    fi
  done

  while IFS= read -r sync_path; do
    [ -z "$sync_path" ] && continue
    sync_path="$(normalize_rel_path "$sync_path")"
    if [ "$normalized_path" = "$sync_path" ] || [[ "$normalized_path" == "$sync_path/"* ]]; then
      return 0
    fi
  done <<< "$SYNC_DIRS"

  return 1
}

is_user_content_path() {
  local path="$1"
  local normalized_path
  normalized_path="$(normalize_rel_path "$path")"
  
  # Paths that are explicitly user-content per docs/DISTRIBUTION.md
  # Check exact paths first
  case "$normalized_path" in
    "CHANGELOG.md"|"package-lock.json"|"render.yaml"|"eslint.config.mjs"|"tsconfig.json"|"tsconfig.tsbuildinfo"|"next.config.ts"|"next-env.d.ts"|"vitest.config.ts"|"vitest.setup.ts"|".claude/settings.local.json")
      return 0
      ;;
    "docs/PRODUCT-REQUIREMENTS.md"|"docs/PRODUCT-ROADMAP.md")
      return 0
      ;;
  esac
  
  # Check directory prefixes for user-content areas
  case "$normalized_path" in
    app/*|__tests__/*|reports/*)
      return 0
      ;;
  esac
  
  return 1
}

bootstrap_reentry_dirty_tree_is_safe() {
  local status_line
  local changed_path

  while IFS= read -r status_line; do
    [ -z "$status_line" ] && continue
    changed_path="${status_line:3}"
    if [[ "$changed_path" == *" -> "* ]]; then
      changed_path="${changed_path##* -> }"
    fi
    
    # Allow framework-controlled files (original logic)
    if path_allowed_for_bootstrap_reentry "$changed_path"; then
      continue
    fi
    
    # Allow user-content files (new logic) - they don't block framework operations
    if is_user_content_path "$changed_path"; then
      continue
    fi
    
    # All other changes (hybrid files without proper framework markers, etc.) still block
    return 1
  done < <(git status --porcelain)

  return 0
}

###############################################################################
# 1. Read local version and syncDirectories
###############################################################################
if [ ! -f "$VERSION_FILE" ]; then
  echo "ERROR: $VERSION_FILE not found."
  exit 1
fi

LOCAL_VERSION=$(python3 -c "import json,sys; print(json.load(open('$VERSION_FILE'))['version'])")
SYNC_DIRS=$(python3 -c "
import json, sys
dirs = json.load(open('$VERSION_FILE')).get('syncDirectories', [])
print('\n'.join(dirs))
")

echo "Local version : $LOCAL_VERSION"
echo "Sync targets  : $SYNC_DIRS"

load_override_patterns "$OVERRIDES_FILE"
echo "Protected overrides: ${#OVERRIDE_PATTERNS[@]} pattern(s)"

###############################################################################
# 2. Fetch latest release from GitHub (unauthenticated)
###############################################################################
RELEASE_JSON=$(curl -sf "https://api.github.com/repos/${UPSTREAM_REPO}/releases/latest") || {
  echo "ERROR: Could not fetch latest release from ${UPSTREAM_REPO}."
  exit 1
}

LATEST_VERSION=$(echo "$RELEASE_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['tag_name'].lstrip('v'))")
RELEASE_URL=$(echo "$RELEASE_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['html_url'])")
TARBALL_URL=$(echo "$RELEASE_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['tarball_url'])")

echo "Latest version: $LATEST_VERSION"

###############################################################################
# 3. Compare versions
###############################################################################
if [ "$LOCAL_VERSION" = "$LATEST_VERSION" ]; then
  echo "No updates available. Local version ($LOCAL_VERSION) matches latest release."
  exit 0
fi

echo "Update available: $LOCAL_VERSION -> $LATEST_VERSION"

###############################################################################
# 3a. Skip cleanly if the sync branch is already pushed (idempotent re-run)
###############################################################################
SYNC_BRANCH="agile-flow-sync/v${LATEST_VERSION}"

if git ls-remote --exit-code --heads origin "$SYNC_BRANCH" >/dev/null 2>&1; then
  echo "Sync branch '$SYNC_BRANCH' already exists on remote — nothing to do."
  if command -v gh >/dev/null 2>&1; then
    EXISTING_PR_URL=$(gh pr list --head "$SYNC_BRANCH" --state open --json url --jq '.[0].url // empty' 2>/dev/null || true)
    if [ -n "${EXISTING_PR_URL:-}" ]; then
      echo "Existing PR: $EXISTING_PR_URL"
    fi
  fi
  exit 0
fi

###############################################################################
# 4. Detect bootstrap re-entry state
###############################################################################
if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "ERROR: not inside a git repository — cannot create rollback tag."
  exit 1
fi

BOOTSTRAP_REENTRY_MODE=0
if ! git diff-index --quiet HEAD -- 2>/dev/null; then
  if bootstrap_reentry_dirty_tree_is_safe; then
    BOOTSTRAP_REENTRY_MODE=1
    echo "WARNING: detected bootstrap re-entry with staged sync-target files; reusing staged payload."
  else
    echo "ERROR: working tree has uncommitted changes in framework-controlled or hybrid files — refusing to upgrade without a clean rollback point."
    echo "User-content files (docs/PRODUCT-*.md, app/, etc.) don't block upgrades, but framework files do."
    echo "Commit or stash your framework file changes, then retry."
    exit 1
  fi
fi

###############################################################################
# 5. Download and extract release tarball (normal path only)
###############################################################################
WORK_DIR=""
EXTRACTED_DIR=""
if [ "$BOOTSTRAP_REENTRY_MODE" -eq 0 ]; then
  WORK_DIR=$(mktemp -d)
  TARBALL="$WORK_DIR/release.tar.gz"

  echo "Downloading release tarball..."
  curl -sfL "$TARBALL_URL" -o "$TARBALL"
  tar -xzf "$TARBALL" -C "$WORK_DIR"

  # GitHub tarballs extract into a directory like owner-repo-hash/
  EXTRACTED_DIR=$(find "$WORK_DIR" -mindepth 1 -maxdepth 1 -type d | head -1)

  if [ -z "$EXTRACTED_DIR" ]; then
    echo "ERROR: Could not find extracted release directory."
    rm -rf "$WORK_DIR"
    exit 1
  fi
fi

###############################################################################
# 6. Create pre-upgrade rollback tag (local-only safety net)
###############################################################################
if ! git symbolic-ref -q HEAD >/dev/null; then
  echo "ERROR: HEAD is detached — refusing to upgrade without a branch to roll back to."
  [ -n "$WORK_DIR" ] && rm -rf "$WORK_DIR"
  exit 1
fi

ROLLBACK_TAG="pre-upgrade-$(date +%Y%m%d-%H%M%S)"
if ! git tag "$ROLLBACK_TAG" 2>/dev/null; then
  echo "ERROR: failed to create rollback tag '$ROLLBACK_TAG'. Aborting."
  [ -n "$WORK_DIR" ] && rm -rf "$WORK_DIR"
  exit 1
fi
echo "Created rollback tag: $ROLLBACK_TAG (local-only)"

###############################################################################
# 7. Build change payload
###############################################################################
FILES_CHANGED=()
FILES_SKIPPED_OVERRIDE=()
FILES_SKIPPED_RUNTIME=()

if [ "$BOOTSTRAP_REENTRY_MODE" -eq 1 ]; then
  while IFS= read -r changed_path; do
    [ -z "$changed_path" ] && continue
    FILES_CHANGED+=("$changed_path")
  done < <(git diff --cached --name-only)
else
  while IFS= read -r sync_path; do
    [ -z "$sync_path" ] && continue

    upstream_path="$EXTRACTED_DIR/$sync_path"

    if [ ! -e "$upstream_path" ]; then
      echo "SKIP: $sync_path not found in upstream release."
      continue
    fi

    if [ -d "$upstream_path" ]; then
      # Directory sync: iterate over each file in the upstream directory
      while IFS= read -r file; do
        rel_file="${file#"$upstream_path"/}"
        local_file="$sync_path/$rel_file"
        normalized_local_file="$(normalize_rel_path "$local_file")"
        upstream_file="$file"

        if is_runtime_protected "$normalized_local_file"; then
          echo "SKIP (runtime-protected): $normalized_local_file"
          FILES_SKIPPED_RUNTIME+=("$normalized_local_file")
          continue
        fi

        if is_override "$local_file"; then
          echo "SKIP (override): $local_file"
          FILES_SKIPPED_OVERRIDE+=("$local_file")
          continue
        fi
        if [ "$local_file" = "$RUNNING_SCRIPT_REL" ]; then
          echo "SKIP: $local_file is the currently running script."
          continue
        fi

        # Create parent directory if needed
        mkdir -p "$(dirname "$local_file")"

        if [ -f "$local_file" ]; then
          if ! diff -q "$upstream_file" "$local_file" >/dev/null 2>&1; then
            cp "$upstream_file" "$local_file"
            git add "$local_file"
            FILES_CHANGED+=("$local_file")
            echo "UPDATED: $local_file"
          fi
        else
          cp "$upstream_file" "$local_file"
          git add "$local_file"
          FILES_CHANGED+=("$local_file")
          echo "ADDED: $local_file"
        fi
      done < <(find "$upstream_path" -type f)
    else
      # Single file sync
      normalized_sync_path="$(normalize_rel_path "$sync_path")"
      if is_runtime_protected "$normalized_sync_path"; then
        echo "SKIP (runtime-protected): $normalized_sync_path"
        FILES_SKIPPED_RUNTIME+=("$normalized_sync_path")
        continue
      fi

      if is_override "$sync_path"; then
        echo "SKIP (override): $sync_path"
        FILES_SKIPPED_OVERRIDE+=("$sync_path")
        continue
      fi
      if [ "$sync_path" = "$RUNNING_SCRIPT_REL" ]; then
        echo "SKIP: $sync_path is the currently running script."
        continue
      fi

      if [ -f "$sync_path" ]; then
        if ! diff -q "$upstream_path" "$sync_path" >/dev/null 2>&1; then
          cp "$upstream_path" "$sync_path"
          git add "$sync_path"
          FILES_CHANGED+=("$sync_path")
          echo "UPDATED: $sync_path"
        fi
      else
        mkdir -p "$(dirname "$sync_path")"
        cp "$upstream_path" "$sync_path"
        git add "$sync_path"
        FILES_CHANGED+=("$sync_path")
        echo "ADDED: $sync_path"
      fi
    fi
  done <<< "$SYNC_DIRS"
fi

if [ "${#FILES_SKIPPED_OVERRIDE[@]}" -gt 0 ]; then
  echo "Skipped ${#FILES_SKIPPED_OVERRIDE[@]} override(s) — kept local versions."
fi

if [ "${#FILES_SKIPPED_RUNTIME[@]}" -gt 0 ]; then
  echo "Skipped ${#FILES_SKIPPED_RUNTIME[@]} runtime-protected file(s)."
fi

###############################################################################
# 8. Clean up
###############################################################################
[ -n "$WORK_DIR" ] && rm -rf "$WORK_DIR"

###############################################################################
# 9. If no files changed, exit
###############################################################################
if [ ${#FILES_CHANGED[@]} -eq 0 ]; then
  echo "Already up to date. All synced files match the latest release."
  exit 0
fi

###############################################################################
# 10. Create branch, commit, and open PR
###############################################################################
# SYNC_BRANCH was computed and verified absent on remote in step 3a above.

git checkout -b "$SYNC_BRANCH"

# Update .agile-flow-version with the new version
python3 -c "
import json
with open('$VERSION_FILE', 'r') as f:
    data = json.load(f)
data['version'] = '$LATEST_VERSION'
with open('$VERSION_FILE', 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\\n')
"
git add "$VERSION_FILE"

# Create .agile-flow-meta directory and write version file
mkdir -p .agile-flow-meta
echo "$LATEST_VERSION" > .agile-flow-meta/version
git add .agile-flow-meta/version

COMMIT_MSG="chore(sync): update Agile Flow framework to v${LATEST_VERSION}"
# Scope the bot identity to this single commit using -c so running locally
# does NOT overwrite the user's per-repo git author config.
git -c user.name="github-actions[bot]" \
    -c user.email="github-actions[bot]@users.noreply.github.com" \
    commit -m "$COMMIT_MSG"
git push origin "$SYNC_BRANCH"

# Build file list for PR body
FILE_LIST=""
for f in "${FILES_CHANGED[@]}"; do
  FILE_LIST="${FILE_LIST}- \`${f}\`
"
done

PR_BODY="## Agile Flow Framework Update

Updates framework files from \`v${LOCAL_VERSION}\` to \`v${LATEST_VERSION}\`.

### Updated files

${FILE_LIST}
### Release notes

See the full release notes: ${RELEASE_URL}

---
> This PR was created automatically by the template-sync workflow.
> **Please review the changes before merging.**"

gh pr create \
  --title "chore(sync): update Agile Flow framework to v${LATEST_VERSION}" \
  --body "$PR_BODY" \
  --base main \
  --head "$SYNC_BRANCH"

echo ""
echo "===================== Summary ====================="
echo "PR created successfully for v${LATEST_VERSION}."
echo "Rollback: git reset --hard $ROLLBACK_TAG"
echo "==================================================="
}

main "$@"
