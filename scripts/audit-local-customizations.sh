#!/usr/bin/env bash
# Audits framework-controlled files (paths under `syncDirectories` in
# `.gembaflow-version`) that have been modified locally since the fork
# was bootstrapped — and that are NOT already listed in
# `.gembaflow-overrides`. These are the files at silent-clobber risk on
# the next `/upgrade`.
#
# Output is informational (exit 0 always). The script never modifies
# `.gembaflow-overrides` itself.
#
# Usage:
#   scripts/audit-local-customizations.sh

set -euo pipefail

MANIFEST=".gembaflow-version"
OVERRIDES=".gembaflow-overrides"

if [ ! -f "$MANIFEST" ]; then
  echo "SKIP: $MANIFEST not found — fork is not bootstrapped." >&2
  exit 0
fi

INSTALLED_AT=$(jq -r '.installedAt // empty' "$MANIFEST")
mapfile -t SYNC_DIRS < <(jq -r '.syncDirectories[]? // empty' "$MANIFEST")

if [ "${#SYNC_DIRS[@]}" -eq 0 ]; then
  echo "SKIP: $MANIFEST has no syncDirectories." >&2
  exit 0
fi

# Fall back to earliest commit if installedAt is missing/empty.
if [ -z "$INSTALLED_AT" ] || [ "$INSTALLED_AT" = "null" ]; then
  INSTALLED_AT=$(git log --reverse --format=%cI -- "${SYNC_DIRS[@]}" 2>/dev/null | head -1)
  if [ -z "$INSTALLED_AT" ]; then
    echo "SKIP: cannot determine installedAt — no commits found under syncDirectories." >&2
    exit 0
  fi
  echo "NOTE: $MANIFEST has no installedAt; falling back to earliest commit ($INSTALLED_AT) under syncDirectories." >&2
fi

# Load override patterns (skip blank + comment lines).
declare -a OVERRIDE_PATTERNS=()
if [ -f "$OVERRIDES" ]; then
  while IFS= read -r line; do
    # Strip leading/trailing whitespace.
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [ -z "$line" ] && continue
    [[ "$line" == \#* ]] && continue
    OVERRIDE_PATTERNS+=("$line")
  done < "$OVERRIDES"
fi

# Returns 0 if $1 is covered by an entry in OVERRIDE_PATTERNS.
is_overridden() {
  local path="$1"
  local pat
  for pat in "${OVERRIDE_PATTERNS[@]}"; do
    if [ "$pat" = "$path" ]; then
      return 0
    fi
    if [[ "$pat" == */ ]] && [[ "$path" == "$pat"* ]]; then
      return 0
    fi
  done
  return 1
}

# Collect changed files since INSTALLED_AT under any syncDir.
mapfile -t CHANGED < <(git log --since="$INSTALLED_AT" --name-only --pretty=format: -- "${SYNC_DIRS[@]}" 2>/dev/null \
  | grep -v '^$' \
  | sort -u)

if [ "${#CHANGED[@]}" -eq 0 ]; then
  echo "No framework-controlled files have been modified since $INSTALLED_AT — nothing to surface."
  exit 0
fi

# Filter out overridden paths.
declare -a UNPROTECTED=()
for f in "${CHANGED[@]}"; do
  if ! is_overridden "$f"; then
    UNPROTECTED+=("$f")
  fi
done

if [ "${#UNPROTECTED[@]}" -eq 0 ]; then
  echo "All ${#CHANGED[@]} locally-modified framework file(s) are already covered by $OVERRIDES — safe to upgrade."
  exit 0
fi

echo "The following file(s) under syncDirectories have been modified locally"
echo "since $INSTALLED_AT and are NOT in $OVERRIDES."
echo "Consider adding them to $OVERRIDES before proceeding with /upgrade."
echo ""
printf '%-60s  %-24s  %s\n' "PATH" "LAST MODIFIED" "LAST AUTHOR"
printf '%-60s  %-24s  %s\n' "----" "-------------" "-----------"
for f in "${UNPROTECTED[@]}"; do
  # Last commit touching this path.
  read -r LAST_DATE LAST_AUTHOR <<< "$(git log -1 --format='%cI %an' -- "$f" 2>/dev/null)"
  printf '%-60s  %-24s  %s\n' "$f" "${LAST_DATE:-?}" "${LAST_AUTHOR:-?}"
done

echo ""
echo "To add a path: append it to $OVERRIDES (one path per line; trailing /"
echo "marks a directory). Comments start with #."

exit 0
