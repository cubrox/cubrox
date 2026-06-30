#!/usr/bin/env bash
# overrides.sh -- Shared loader for .gembaflow-overrides.
#
# Sourced by template-sync.sh (and downstream pull-upstream.sh) so both flows
# agree on which framework files are intentionally fork-customised and must
# never be overwritten by an upstream sync.
#
# Usage:
#   source "$(dirname "${BASH_SOURCE[0]}")/lib/overrides.sh"
#   load_override_patterns ".gembaflow-overrides"   # populates OVERRIDE_PATTERNS
#   if is_override "scripts/doctor.sh"; then ... ; fi
#
# File format (.gembaflow-overrides):
#   - One path per line, relative to the repo root
#   - Lines starting with `#` are comments
#   - Blank lines are ignored
#   - Bash glob characters (`*`, `?`, `[...]`) match any portion of the path.
#     Note: bash pattern matching is greedy — `*` will cross `/`, so
#     `scripts/*.sh` also matches `scripts/lib/overrides.sh`. Use a more
#     specific path if you need a narrower match.

# Indexed array of patterns loaded from the overrides file.
OVERRIDE_PATTERNS=()

# load_override_patterns <overrides-file>
#
# Populates OVERRIDE_PATTERNS from the given file. If the file does not exist
# (the common case on a fresh fork), OVERRIDE_PATTERNS is left empty and
# is_override always returns 1. This preserves first-run behavior.
load_override_patterns() {
  local overrides_file="${1:-.gembaflow-overrides}"
  OVERRIDE_PATTERNS=()

  [ -f "$overrides_file" ] || return 0

  local line
  while IFS= read -r line || [ -n "$line" ]; do
    # Trim leading/trailing whitespace
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [ -z "$line" ] && continue
    [[ "$line" == \#* ]] && continue
    OVERRIDE_PATTERNS+=("$line")
  done < "$overrides_file"
}

# is_override <relative-path>
#
# Returns 0 if the given path matches any loaded override pattern, 1 otherwise.
# Patterns use bash glob semantics (e.g. `scripts/doctor.sh`, `scripts/*.sh`).
is_override() {
  local path="$1"
  local pattern
  for pattern in "${OVERRIDE_PATTERNS[@]}"; do
    # shellcheck disable=SC2053
    if [[ "$path" == $pattern ]]; then
      return 0
    fi
  done
  return 1
}
