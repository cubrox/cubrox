#!/usr/bin/env bash
# Tests for scripts/lib/overrides.sh
# Usage: ./scripts/lib/overrides.test.sh

set -uo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

TESTS_PASSED=0
TESTS_FAILED=0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/overrides.sh
source "$SCRIPT_DIR/overrides.sh"

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

assert_eq() {
  local name="$1"
  local expected="$2"
  local actual="$3"
  if [ "$expected" = "$actual" ]; then
    echo -e "  ${GREEN}PASS${NC}: $name"
    TESTS_PASSED=$((TESTS_PASSED + 1))
  else
    echo -e "  ${RED}FAIL${NC}: $name"
    echo "    expected: $expected"
    echo "    actual:   $actual"
    TESTS_FAILED=$((TESTS_FAILED + 1))
  fi
}

assert_match() {
  local name="$1"
  local path="$2"
  if is_override "$path"; then
    echo -e "  ${GREEN}PASS${NC}: $name ('$path' matches)"
    TESTS_PASSED=$((TESTS_PASSED + 1))
  else
    echo -e "  ${RED}FAIL${NC}: $name ('$path' should match)"
    TESTS_FAILED=$((TESTS_FAILED + 1))
  fi
}

assert_no_match() {
  local name="$1"
  local path="$2"
  if is_override "$path"; then
    echo -e "  ${RED}FAIL${NC}: $name ('$path' should NOT match)"
    TESTS_FAILED=$((TESTS_FAILED + 1))
  else
    echo -e "  ${GREEN}PASS${NC}: $name ('$path' does not match)"
    TESTS_PASSED=$((TESTS_PASSED + 1))
  fi
}

echo "Running overrides.sh tests"
echo "=========================="

echo
echo "Test 1: Missing overrides file leaves OVERRIDE_PATTERNS empty"
load_override_patterns "$WORK_DIR/does-not-exist"
assert_eq "OVERRIDE_PATTERNS length is 0" "0" "${#OVERRIDE_PATTERNS[@]}"
assert_no_match "first-run behavior unchanged" "scripts/doctor.sh"

echo
echo "Test 2: Empty overrides file leaves OVERRIDE_PATTERNS empty"
: > "$WORK_DIR/empty"
load_override_patterns "$WORK_DIR/empty"
assert_eq "empty file -> 0 patterns" "0" "${#OVERRIDE_PATTERNS[@]}"

echo
echo "Test 3: Exact path match"
cat > "$WORK_DIR/exact" <<'EOF'
scripts/doctor.sh
.claude/agents/system-architect.md
EOF
load_override_patterns "$WORK_DIR/exact"
assert_eq "loaded 2 patterns" "2" "${#OVERRIDE_PATTERNS[@]}"
assert_match "doctor.sh listed -> match" "scripts/doctor.sh"
assert_match "agent file listed -> match" ".claude/agents/system-architect.md"
assert_no_match "unrelated file -> no match" "scripts/template-sync.sh"

echo
echo "Test 4: Comments and blank lines are ignored"
cat > "$WORK_DIR/comments" <<'EOF'
# This is a comment

   # Indented comment

scripts/doctor.sh

# Another comment
scripts/extra.sh
EOF
load_override_patterns "$WORK_DIR/comments"
assert_eq "loaded 2 patterns (comments stripped)" "2" "${#OVERRIDE_PATTERNS[@]}"
assert_match "doctor.sh still matches" "scripts/doctor.sh"
assert_match "extra.sh still matches" "scripts/extra.sh"

echo
echo "Test 5: Leading/trailing whitespace is trimmed"
cat > "$WORK_DIR/whitespace" <<'EOF'
   scripts/doctor.sh
scripts/extra.sh
EOF
load_override_patterns "$WORK_DIR/whitespace"
assert_match "leading whitespace trimmed" "scripts/doctor.sh"
assert_match "trailing whitespace trimmed" "scripts/extra.sh"

echo
echo "Test 6: Glob patterns"
cat > "$WORK_DIR/globs" <<'EOF'
scripts/*.sh
.claude/agents/worker-*.md
docs/**
EOF
load_override_patterns "$WORK_DIR/globs"
assert_match "scripts/*.sh matches scripts/doctor.sh" "scripts/doctor.sh"
assert_match "scripts/*.sh matches scripts/workshop-setup.sh" "scripts/workshop-setup.sh"
# Bash pattern matching: `*` is greedy and crosses `/`, so a glob anchored to
# a directory prefix matches nested files too. Documented in overrides.sh.
assert_match "scripts/*.sh also matches nested file (bash glob is greedy)" "scripts/lib/overrides.sh"
assert_match "worker-*.md matches worker-engineer" ".claude/agents/worker-engineer.md"
assert_no_match "worker-*.md does NOT match other agents" ".claude/agents/system-architect.md"

echo
echo "Test 7: Reloading replaces previous patterns"
cat > "$WORK_DIR/first" <<'EOF'
scripts/doctor.sh
EOF
cat > "$WORK_DIR/second" <<'EOF'
docs/PATTERN-LIBRARY.md
EOF
load_override_patterns "$WORK_DIR/first"
assert_match "first load: doctor.sh matches" "scripts/doctor.sh"
load_override_patterns "$WORK_DIR/second"
assert_no_match "after reload: doctor.sh no longer matches" "scripts/doctor.sh"
assert_match "after reload: PATTERN-LIBRARY matches" "docs/PATTERN-LIBRARY.md"

echo
echo "Test 8: File without trailing newline still reads last line"
printf 'scripts/doctor.sh' > "$WORK_DIR/no-newline"
load_override_patterns "$WORK_DIR/no-newline"
assert_eq "1 pattern loaded (no trailing newline)" "1" "${#OVERRIDE_PATTERNS[@]}"
assert_match "last line still matched" "scripts/doctor.sh"

echo
echo "=========================="
echo "Results: ${TESTS_PASSED} passed, ${TESTS_FAILED} failed"

if [ "$TESTS_FAILED" -gt 0 ]; then
  exit 1
fi
exit 0
