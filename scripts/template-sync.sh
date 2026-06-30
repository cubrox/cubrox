#!/usr/bin/env bash
# template-sync.sh -- Sync framework files from vibeacademy/gembaflow releases.
# Called by .github/workflows/template-sync.yml (workflow_dispatch only).
# Guardrails:
#   - Only syncs directories/files listed in syncDirectories (.gembaflow-version)
#   - Respects .gembaflow-overrides — fork-local paths/globs are never touched
#   - Does NOT auto-merge; PR requires human review
#   - Uses unauthenticated GitHub API to fetch release metadata
#   - Phase 4 rebrand (#335): legacy .agile-flow-* dotfiles are auto-migrated to
#     .gembaflow-* on first run, with dual-read fallback for one release cycle.

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

UPSTREAM_REPO="vibeacademy/gembaflow"
# FALLBACK_REPO is only consulted when the primary returns 404. Post-Phase 2a
# (#332) the primary is now gembaflow natively; the fallback points at the
# legacy name and would only fire via GitHub's redirect if the gembaflow name
# is ever changed again. Belt-and-suspenders — see #331 / #332.
FALLBACK_REPO="vibeacademy/agile-flow"

# Phase 4 rebrand (#335): one-time migration of legacy .agile-flow-* dotfiles
# to .gembaflow-*. Runs early so the rename appears as a normal diff in the
# next sync PR. Idempotent: only renames when the new name does not yet exist.
if git rev-parse --git-dir >/dev/null 2>&1; then
  if [ -f .agile-flow-version ] && [ ! -f .gembaflow-version ]; then
    echo "INFO: migrating .agile-flow-version -> .gembaflow-version (one-time, Phase 4 rebrand)" >&2
    git mv .agile-flow-version .gembaflow-version
  fi
  if [ -d .agile-flow-meta ] && [ ! -d .gembaflow-meta ]; then
    echo "INFO: migrating .agile-flow-meta/ -> .gembaflow-meta/ (one-time, Phase 4 rebrand)" >&2
    git mv .agile-flow-meta .gembaflow-meta
  fi
  if [ -f .agile-flow-overrides ] && [ ! -f .gembaflow-overrides ]; then
    echo "INFO: migrating .agile-flow-overrides -> .gembaflow-overrides (one-time, Phase 4 rebrand)" >&2
    git mv .agile-flow-overrides .gembaflow-overrides
  fi
fi

VERSION_FILE=".gembaflow-version"
OVERRIDES_FILE=".gembaflow-overrides"
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

###############################################################################
# Hybrid agent file handling (#363)
#
# `.claude/agents/*.md` is classified as hybrid in docs/DISTRIBUTION.md:
# framework persona + restrictions live between `<!-- FRAMEWORK:START -->` and
# `<!-- FRAMEWORK:END -->` markers; project-specific specialization written by
# `/bootstrap-agents` lives outside those markers. The sync must only update
# content between the markers and must preserve user content outside them.
#
# Behavior matrix:
#   - upstream has markers, local has markers      -> swap framework section
#   - upstream has markers, local lacks markers    -> WARN, preserve local file
#     (treat legacy file as fully user-owned; user runs /bootstrap-agents to
#     re-establish markers, OR they can pull the framework section from the
#     diff manually)
#   - upstream lacks markers (shouldn't happen)    -> WARN, fall through to
#     regular overwrite (treats as pure framework)
###############################################################################
is_hybrid_agent_path() {
  local path="$1"
  local normalized_path
  normalized_path="$(normalize_rel_path "$path")"
  case "$normalized_path" in
    .claude/agents/*.md)
      return 0
      ;;
  esac
  return 1
}

file_has_framework_markers() {
  # Returns 0 if file contains BOTH start and end markers, in that order.
  local path="$1"
  [ -f "$path" ] || return 1
  grep -q '<!-- FRAMEWORK:START -->' "$path" || return 1
  grep -q '<!-- FRAMEWORK:END -->' "$path" || return 1
  # Ensure START appears before END (line numbers).
  local start_line end_line
  start_line=$(grep -n '<!-- FRAMEWORK:START -->' "$path" | head -1 | cut -d: -f1)
  end_line=$(grep -n '<!-- FRAMEWORK:END -->' "$path" | head -1 | cut -d: -f1)
  [ -n "$start_line" ] && [ -n "$end_line" ] && [ "$start_line" -lt "$end_line" ]
}

# Replace the framework section in $local_file with the framework section
# from $upstream_file. Content outside the markers in $local_file is preserved
# byte-for-byte. Both files MUST contain the markers; callers must check first.
merge_hybrid_agent_file() {
  local upstream_file="$1"
  local local_file="$2"
  python3 - "$upstream_file" "$local_file" <<'PY'
import sys, re

upstream_path, local_path = sys.argv[1], sys.argv[2]
START = "<!-- FRAMEWORK:START -->"
END = "<!-- FRAMEWORK:END -->"

with open(upstream_path, "r") as f:
    upstream = f.read()
with open(local_path, "r") as f:
    local = f.read()

# Extract upstream framework section (including markers).
def extract(text, path):
    s = text.find(START)
    e = text.find(END)
    if s == -1 or e == -1 or e < s:
        sys.stderr.write(f"ERROR: missing FRAMEWORK markers in {path}\n")
        sys.exit(2)
    return text[s : e + len(END)]

up_section = extract(upstream, upstream_path)
loc_s = local.find(START)
loc_e = local.find(END)
if loc_s == -1 or loc_e == -1 or loc_e < loc_s:
    sys.stderr.write(f"ERROR: missing FRAMEWORK markers in {local_path}\n")
    sys.exit(2)

merged = local[:loc_s] + up_section + local[loc_e + len(END):]
with open(local_path, "w") as f:
    f.write(merged)
PY
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

# Read optional `upstream` field from .gembaflow-version. Accepts either a
# bare "owner/repo" string or a full GitHub URL; falls back to the hardcoded
# UPSTREAM_REPO if the field is absent or empty. This lets downstream variant
# forks point /upgrade at their own upstream without editing this script.
# See #331.
VERSION_UPSTREAM=$(python3 -c "
import json, sys
data = json.load(open('$VERSION_FILE'))
val = data.get('upstream') or ''
val = val.strip()
# Normalize URL form -> owner/repo. Accept https://github.com/<owner>/<repo>
# (with optional trailing .git or slash).
for prefix in ('https://github.com/', 'http://github.com/', 'git@github.com:'):
    if val.startswith(prefix):
        val = val[len(prefix):]
        break
if val.endswith('.git'):
    val = val[:-4]
val = val.strip('/')
print(val)
")
if [ -n "$VERSION_UPSTREAM" ]; then
  UPSTREAM_REPO="$VERSION_UPSTREAM"
fi

echo "Local version : $LOCAL_VERSION"
echo "Upstream repo : $UPSTREAM_REPO"
echo "Sync targets  : $SYNC_DIRS"

load_override_patterns "$OVERRIDES_FILE"
echo "Protected overrides: ${#OVERRIDE_PATTERNS[@]} pattern(s)"

###############################################################################
# 2. Fetch latest release from GitHub (unauthenticated)
###############################################################################
# Use -L so curl follows GitHub's 301 redirects in case an upstream repo is
# renamed in the future. Without -L, curl returns empty on a redirect and the
# next JSON parse fails silently.
RELEASE_JSON=$(curl -fsSL "https://api.github.com/repos/${UPSTREAM_REPO}/releases/latest" 2>/dev/null || true)

# If the primary returned 404 (or curl produced no output), retry against the
# fallback repo. This only fires when the primary truly doesn't exist; a 200
# response keeps behavior byte-for-byte identical to today.
if [ -z "$RELEASE_JSON" ] && [ -n "${FALLBACK_REPO:-}" ] && [ "$FALLBACK_REPO" != "$UPSTREAM_REPO" ]; then
  echo "INFO: ${UPSTREAM_REPO} not reachable; retrying against fallback ${FALLBACK_REPO}." >&2
  RELEASE_JSON=$(curl -fsSL "https://api.github.com/repos/${FALLBACK_REPO}/releases/latest" 2>/dev/null || true)
fi

if [ -z "$RELEASE_JSON" ]; then
  echo "ERROR: Could not fetch latest release from ${UPSTREAM_REPO} (or fallback ${FALLBACK_REPO})."
  exit 1
fi

LATEST_VERSION=$(echo "$RELEASE_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['tag_name'].lstrip('v'))")
RELEASE_URL=$(echo "$RELEASE_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['html_url'])")
TARBALL_URL=$(echo "$RELEASE_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['tarball_url'])")

echo "Latest version: $LATEST_VERSION"

###############################################################################
# 2a. Fresh-fork placeholder short-circuit (#381)
#
# Every fresh fork starts at ".gembaflow-version" version "0.1.0" — the template
# placeholder. If bootstrap.sh ran but couldn't set the version (e.g. network
# failure on `gh release view`), installedAt is stamped but version stays at
# "0.1.0". Without this short-circuit, every such fork's first /upgrade syncs
# from "0.1.0" to the actual latest release tag, generating a no-op PR.
#
# Detect this case (placeholder version + installedAt stamped) and just bump
# the version field locally — no PR, no churn. Legitimately-behind forks
# (version like "1.2.0" with a real installedAt) fall through to normal sync.
###############################################################################
INSTALLED_AT=$(python3 -c "import json; print(json.load(open('$VERSION_FILE')).get('installedAt') or '')")
if [ "$LOCAL_VERSION" = "0.1.0" ] && [ -n "$INSTALLED_AT" ]; then
  echo "INFO: detected fresh-fork placeholder version; setting LOCAL_VERSION to latest without sync." >&2
  if command -v jq >/dev/null 2>&1; then
    jq --arg ver "$LATEST_VERSION" '.version = $ver' "$VERSION_FILE" > "$VERSION_FILE.tmp" \
      && mv "$VERSION_FILE.tmp" "$VERSION_FILE"
  else
    python3 - <<PY
import json
with open("$VERSION_FILE") as f:
    data = json.load(f)
data["version"] = "$LATEST_VERSION"
with open("$VERSION_FILE", "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PY
  fi
  echo "Already up to date (fresh-fork initialized to v${LATEST_VERSION})."
  exit 0
fi

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
SYNC_BRANCH="gembaflow-sync/v${LATEST_VERSION}"

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
HYBRID_AGENTS_UPDATED=()       # .claude/agents/*.md with markers, framework section merged
HYBRID_AGENTS_LEGACY_SKIPPED=() # .claude/agents/*.md without markers, preserved local

# Mode-registry summary (#406). `.claude/modes/` is a fork-extensible registry —
# upstream files are synced like any other directory, but fork-local files are
# never touched (the find loop only iterates upstream files, so anything fork-
# local is implicitly preserved). We surface the split explicitly in the sync
# log so the maintainer can see at a glance which fork-local modes survived.
modes_summary_log() {
  local upstream_modes_dir="$1"
  [ -d "$upstream_modes_dir" ] || return 0

  local upstream_count
  upstream_count=$(find "$upstream_modes_dir" -maxdepth 1 -type f -name '*.md' | wc -l | tr -d ' ')

  local fork_local=()
  if [ -d ".claude/modes" ]; then
    while IFS= read -r local_file; do
      [ -z "$local_file" ] && continue
      local rel
      rel="${local_file##*/}"
      if [ ! -f "$upstream_modes_dir/$rel" ]; then
        fork_local+=("${rel%.md}")
      fi
    done < <(find ".claude/modes" -maxdepth 1 -type f -name '*.md')
  fi

  if [ "${#fork_local[@]}" -eq 0 ]; then
    echo "[modes] Syncing ${upstream_count} framework modes; 0 fork-local modes preserved."
  else
    local joined
    joined=$(IFS=,; echo "${fork_local[*]}")
    joined="${joined//,/, }"
    echo "[modes] Syncing ${upstream_count} framework modes; ${#fork_local[@]} fork-local modes preserved: ${joined}."
  fi
}

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
      # Friendly log line for the mode registry (#406).
      if [ "$(normalize_rel_path "$sync_path")" = ".claude/modes" ]; then
        modes_summary_log "$upstream_path"
      fi
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
            if is_hybrid_agent_path "$local_file"; then
              # Hybrid agent file (#363): only update the FRAMEWORK section.
              if file_has_framework_markers "$local_file" && file_has_framework_markers "$upstream_file"; then
                if merge_hybrid_agent_file "$upstream_file" "$local_file"; then
                  # If the merge produced no diff vs. the prior local file,
                  # there's nothing to commit. Otherwise stage.
                  if ! git diff --quiet -- "$local_file" 2>/dev/null; then
                    git add "$local_file"
                    FILES_CHANGED+=("$local_file")
                    HYBRID_AGENTS_UPDATED+=("$local_file")
                    echo "UPDATED (hybrid framework section): $local_file"
                  else
                    echo "UNCHANGED (hybrid framework section identical): $local_file"
                  fi
                else
                  echo "WARNING: hybrid merge failed for $local_file; preserving local file untouched." >&2
                fi
              else
                # Legacy or malformed: preserve local entirely; warn loudly.
                echo "WARNING: $local_file lacks <!-- FRAMEWORK:START/END --> markers; preserving local file. Run /bootstrap-agents to migrate." >&2
                HYBRID_AGENTS_LEGACY_SKIPPED+=("$local_file")
              fi
            else
              cp "$upstream_file" "$local_file"
              git add "$local_file"
              FILES_CHANGED+=("$local_file")
              echo "UPDATED: $local_file"
            fi
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
          if is_hybrid_agent_path "$sync_path"; then
            if file_has_framework_markers "$sync_path" && file_has_framework_markers "$upstream_path"; then
              if merge_hybrid_agent_file "$upstream_path" "$sync_path"; then
                if ! git diff --quiet -- "$sync_path" 2>/dev/null; then
                  git add "$sync_path"
                  FILES_CHANGED+=("$sync_path")
                  HYBRID_AGENTS_UPDATED+=("$sync_path")
                  echo "UPDATED (hybrid framework section): $sync_path"
                else
                  echo "UNCHANGED (hybrid framework section identical): $sync_path"
                fi
              else
                echo "WARNING: hybrid merge failed for $sync_path; preserving local file untouched." >&2
              fi
            else
              echo "WARNING: $sync_path lacks <!-- FRAMEWORK:START/END --> markers; preserving local file. Run /bootstrap-agents to migrate." >&2
              HYBRID_AGENTS_LEGACY_SKIPPED+=("$sync_path")
            fi
          else
            cp "$upstream_path" "$sync_path"
            git add "$sync_path"
            FILES_CHANGED+=("$sync_path")
            echo "UPDATED: $sync_path"
          fi
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
# 7.5. Self-healing post-sync refresh of runtime-protected files (#371)
###############################################################################
# The main sync loop above skips runtime-protected files (template-sync.sh and
# scripts/lib/overrides.sh) — correctly, because the running script cannot
# safely overwrite itself mid-execution. But that means bug fixes to those
# files never reach forks via the normal sync path.
#
# This post-loop block closes the gap. By the time we get here:
#   - The sync loop is finished — the currently-running script's main work is
#     done. The script process is still in memory; the next /upgrade
#     invocation is what reads the on-disk file.
#   - $EXTRACTED_DIR still holds the release tarball's contents (cleanup
#     happens after this block).
#
# For each path in RUNTIME_PROTECTED_PATHS, compare the local file's content
# to the tarball version. If different AND the path is not in
# .gembaflow-overrides, copy the tarball version over the local file and stage
# it. The change rides the same sync PR; the operator reviews and merges
# normally. The next /upgrade reads the refreshed file.

RUNTIME_REFRESHED=()

for protected in "${RUNTIME_PROTECTED_PATHS[@]}"; do
  normalized_protected="$(normalize_rel_path "$protected")"

  # Respect operator's explicit override choice: if the fork has added this
  # path to .gembaflow-overrides, the operator wants their local divergence
  # preserved across sync. Don't refresh.
  if is_override "$normalized_protected"; then
    echo "SKIP refresh (override): $normalized_protected"
    continue
  fi

  tarball_file="$EXTRACTED_DIR/$normalized_protected"
  if [ ! -f "$tarball_file" ]; then
    # Upstream tarball doesn't contain the file — unusual but bail safely.
    continue
  fi

  if [ ! -f "$normalized_protected" ]; then
    # Local file is missing; refresh = add.
    mkdir -p "$(dirname "$normalized_protected")"
    cp "$tarball_file" "$normalized_protected"
    git add "$normalized_protected" 2>/dev/null || true
    RUNTIME_REFRESHED+=("$normalized_protected")
    FILES_CHANGED+=("$normalized_protected")
    echo "REFRESHED (post-run, added): $normalized_protected"
    continue
  fi

  if ! diff -q "$tarball_file" "$normalized_protected" >/dev/null 2>&1; then
    cp "$tarball_file" "$normalized_protected"
    git add "$normalized_protected" 2>/dev/null || true
    RUNTIME_REFRESHED+=("$normalized_protected")
    FILES_CHANGED+=("$normalized_protected")
    echo "REFRESHED (post-run): $normalized_protected"
  fi
done

if [ "${#RUNTIME_REFRESHED[@]}" -gt 0 ]; then
  echo "Refreshed ${#RUNTIME_REFRESHED[@]} runtime-protected file(s) post-run. The on-disk versions are now current; the next /upgrade will read the refreshed code."
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

# Update the version manifest with the new version.
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

# Write the meta-dir version stamp.
META_DIR=".gembaflow-meta"
mkdir -p "$META_DIR"
echo "$LATEST_VERSION" > "$META_DIR/version"
git add "$META_DIR/version"

# Bump package.json "version" to match the new framework release. The downstream
# CI job (validate-version-parity.sh) requires .gembaflow-version and
# package.json to agree; without this, every sync PR lands with red CI. See
# vibeacademy/gembaflow#361. Idempotent: no-op when versions already match.
# Skipped on non-Node forks (no package.json at repo root).
if [ -f package.json ]; then
  CURRENT_PKG_VERSION=""
  if command -v jq >/dev/null 2>&1; then
    CURRENT_PKG_VERSION=$(jq -r '.version // empty' package.json)
  else
    CURRENT_PKG_VERSION=$(python3 -c "import json; print(json.load(open('package.json')).get('version', ''))")
  fi

  if [ "$CURRENT_PKG_VERSION" != "$LATEST_VERSION" ]; then
    if command -v jq >/dev/null 2>&1; then
      TMP_PKG=$(mktemp)
      jq --arg v "$LATEST_VERSION" '.version = $v' package.json > "$TMP_PKG"
      mv "$TMP_PKG" package.json
    else
      python3 -c "
import json
with open('package.json', 'r') as f:
    data = json.load(f)
data['version'] = '$LATEST_VERSION'
with open('package.json', 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\\n')
"
    fi
    git add package.json
    echo "UPDATED: package.json version -> $LATEST_VERSION"
  else
    echo "OK: package.json version already $LATEST_VERSION (no-op)"
  fi
fi

COMMIT_MSG="chore(sync): update Gemba Flow framework to v${LATEST_VERSION}"
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

# Build hybrid-agent warning section for PR body (#363).
HYBRID_SECTION=""
if [ "${#HYBRID_AGENTS_UPDATED[@]}" -gt 0 ]; then
  HYBRID_LIST=""
  for f in "${HYBRID_AGENTS_UPDATED[@]}"; do
    HYBRID_LIST="${HYBRID_LIST}  - \`${f}\`
"
  done
  HYBRID_SECTION="${HYBRID_SECTION}
> [!IMPORTANT]
> Hybrid agent files updated (framework section only):
${HYBRID_LIST}> User content outside \`<!-- FRAMEWORK:START -->\` / \`<!-- FRAMEWORK:END -->\` markers was preserved. Review the diff to confirm your \`/bootstrap-agents\` specialization is intact.
"
fi
if [ "${#HYBRID_AGENTS_LEGACY_SKIPPED[@]}" -gt 0 ]; then
  LEGACY_LIST=""
  for f in "${HYBRID_AGENTS_LEGACY_SKIPPED[@]}"; do
    LEGACY_LIST="${LEGACY_LIST}  - \`${f}\`
"
  done
  HYBRID_SECTION="${HYBRID_SECTION}
> [!WARNING]
> Legacy agent files (no FRAMEWORK markers) were left untouched and may be out of date:
${LEGACY_LIST}> Run \`/bootstrap-agents\` to re-establish markers and re-apply your project specialization, then re-run \`/upgrade\` to pick up the latest framework persona.
"
fi

# Build runtime-protected refresh section for PR body (#371).
RUNTIME_REFRESH_SECTION=""
if [ "${#RUNTIME_REFRESHED[@]}" -gt 0 ]; then
  REFRESH_LIST=""
  for f in "${RUNTIME_REFRESHED[@]}"; do
    REFRESH_LIST="${REFRESH_LIST}  - \`${f}\`
"
  done
  RUNTIME_REFRESH_SECTION="
> [!IMPORTANT]
> Runtime-protected files refreshed (post-run):
${REFRESH_LIST}> These files are skipped during the main sync loop because the running script cannot overwrite itself mid-execution. The post-run refresh re-copies them after the loop completes, so the next \`/upgrade\` invocation reads the current code. The currently-running script process is unaffected — only the on-disk file is updated. Review the diff before merging.
"
fi

PR_BODY="## Gemba Flow Framework Update

Updates framework files from \`v${LOCAL_VERSION}\` to \`v${LATEST_VERSION}\`.

### Updated files

${FILE_LIST}${HYBRID_SECTION}${RUNTIME_REFRESH_SECTION}
### Release notes

See the full release notes: ${RELEASE_URL}

---
> This PR was created automatically by the template-sync workflow.
> **Please review the changes before merging.**"

gh pr create \
  --title "chore(sync): update Gemba Flow framework to v${LATEST_VERSION}" \
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
