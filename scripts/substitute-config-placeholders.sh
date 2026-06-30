#!/usr/bin/env bash
# substitute-config-placeholders.sh — Substitute bootstrap-time templated values
# in framework files.
#
# Reads `.gembaflow-config.json` from the current working directory, then runs
# in-place sed substitution for the four canonical placeholders in every Markdown
# file under `.claude/commands/`. Idempotent: re-running after substitution
# completes is a no-op.
#
# Placeholders (substituted in this file, by `bootstrap-workflow.md` after a
# fresh bootstrap, or by hand after editing `.gembaflow-config.json`):
#   {{org}}            — GitHub org login that hosts the framework + this fork
#   {{board.id}}       — Project board number on the GitHub Project the team uses
#   {{bot.worker}}     — GitHub login of the worker bot (opens PRs, makes commits)
#   {{bot.reviewer}}   — GitHub login of the reviewer bot (posts /review-pr verdicts)
#
# Usage:
#   bash scripts/substitute-config-placeholders.sh           # substitute in place
#   bash scripts/substitute-config-placeholders.sh --check   # report unsubstituted placeholders without modifying anything
#   bash scripts/substitute-config-placeholders.sh --help
#
# Exit codes:
#   0  — substitution complete (or --check found zero unsubstituted placeholders)
#   1  — error (missing config, bad JSON, unreadable files, or --check found placeholders)

set -euo pipefail

CONFIG_FILE=".gembaflow-config.json"
TARGET_DIR=".claude/commands"
CHECK_ONLY=false

show_help() {
  cat <<'HELP'
substitute-config-placeholders.sh — Substitute bootstrap-time templated values.

Reads .gembaflow-config.json and substitutes {{org}}, {{board.id}},
{{bot.worker}}, {{bot.reviewer}} placeholders in .claude/commands/*.md files.

Usage:
  bash scripts/substitute-config-placeholders.sh           # substitute in place
  bash scripts/substitute-config-placeholders.sh --check   # report only
  bash scripts/substitute-config-placeholders.sh --help

Exit codes:
  0  — substitution complete (or --check found zero unsubstituted)
  1  — error or --check found placeholders

See `docs/PLATFORM-GUIDE.md` for the templating convention.
HELP
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check) CHECK_ONLY=true; shift ;;
    --help|-h) show_help; exit 0 ;;
    *) echo "ERROR: Unknown flag: $1" >&2; exit 1 ;;
  esac
done

# ── Locate config ────────────────────────────────────────────────────────────

if [ ! -f "$CONFIG_FILE" ] && ! $CHECK_ONLY; then
  echo "ERROR: $CONFIG_FILE not found." >&2
  echo "Run /bootstrap-workflow to set up the templated values, or copy" >&2
  echo ".gembaflow-config.example.json to $CONFIG_FILE and edit by hand." >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "ERROR: jq is required to parse $CONFIG_FILE but is not installed." >&2
  exit 1
fi

# ── Check-only mode: report unsubstituted placeholders, exit accordingly ─────

if $CHECK_ONLY; then
  count=0
  while IFS= read -r -d '' file; do
    # `grep -c` exits 1 when there are zero matches AND prints "0"; the
    # `|| echo 0` ran in addition, producing "0\n0" and tripping `[ -gt ]`.
    # Split: capture stdout, then fall back to 0 only on grep error.
    file_hits=$(grep -c -E "\{\{(org|board\.id|bot\.worker|bot\.reviewer)\}\}" "$file" 2>/dev/null) || file_hits=0
    if [ "$file_hits" -gt 0 ]; then
      echo "$file: $file_hits unsubstituted placeholder(s)"
      count=$((count + file_hits))
    fi
  done < <(find "$TARGET_DIR" -type f -name "*.md" -print0 2>/dev/null)
  if [ "$count" -eq 0 ]; then
    echo "OK: no unsubstituted placeholders in $TARGET_DIR/"
    exit 0
  fi
  echo "FOUND: $count unsubstituted placeholder(s) — run substitute-config-placeholders.sh (no --check) to apply."
  exit 1
fi

# ── Extract values ────────────────────────────────────────────────────────────

ORG=$(jq -r '.org // ""' "$CONFIG_FILE")
BOARD_ID=$(jq -r '.board.id // ""' "$CONFIG_FILE")
BOT_WORKER=$(jq -r '.bot.worker // ""' "$CONFIG_FILE")
BOT_REVIEWER=$(jq -r '.bot.reviewer // ""' "$CONFIG_FILE")

# Reject empty / null values up front — a missing field means the operator hasn't
# finished filling in the example file; refuse to substitute "" into the spec.
for pair in "org:$ORG" "board.id:$BOARD_ID" "bot.worker:$BOT_WORKER" "bot.reviewer:$BOT_REVIEWER"; do
  k="${pair%%:*}"
  v="${pair#*:}"
  if [ -z "$v" ] || [ "$v" = "null" ]; then
    echo "ERROR: $CONFIG_FILE field '$k' is empty or missing." >&2
    echo "Fill in all four fields (org, board.id, bot.worker, bot.reviewer) before substituting." >&2
    exit 1
  fi
done

# Validate values don't contain sed-delimiter chars or newlines.
for pair in "org:$ORG" "board.id:$BOARD_ID" "bot.worker:$BOT_WORKER" "bot.reviewer:$BOT_REVIEWER"; do
  k="${pair%%:*}"
  v="${pair#*:}"
  if [[ "$v" == *"|"* ]] || [[ "$v" == *$'\n'* ]] || [[ "$v" == *"/"* ]]; then
    echo "ERROR: $CONFIG_FILE field '$k' contains an unsupported character (pipe, slash, or newline)." >&2
    echo "Got: '$v'" >&2
    exit 1
  fi
done

# ── Substitute in place ──────────────────────────────────────────────────────

if [ ! -d "$TARGET_DIR" ]; then
  echo "ERROR: $TARGET_DIR/ does not exist — is this a Gemba Flow repo?" >&2
  exit 1
fi

changed_files=0
while IFS= read -r -d '' file; do
  before=$(cat "$file")
  # Use | as sed delimiter (we already rejected | in the values above).
  # macOS BSD sed requires `-i ''`; GNU sed accepts `-i` alone. Use a tempfile
  # to stay portable.
  tmp=$(mktemp)
  sed \
    -e "s|{{org}}|$ORG|g" \
    -e "s|{{board\.id}}|$BOARD_ID|g" \
    -e "s|{{bot\.worker}}|$BOT_WORKER|g" \
    -e "s|{{bot\.reviewer}}|$BOT_REVIEWER|g" \
    "$file" > "$tmp"
  if ! cmp -s "$file" "$tmp"; then
    mv "$tmp" "$file"
    echo "  substituted: $file"
    changed_files=$((changed_files + 1))
  else
    rm -f "$tmp"
  fi
done < <(find "$TARGET_DIR" -type f -name "*.md" -print0)

if [ "$changed_files" -eq 0 ]; then
  echo "OK: no placeholders found in $TARGET_DIR/ (already substituted or never present)."
else
  echo "OK: substituted placeholders in $changed_files file(s)."
fi
