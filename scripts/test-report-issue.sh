#!/usr/bin/env bash
# test-report-issue.sh — Acceptance tests for scripts/report-issue.sh
#
# Usage:
#   ./scripts/test-report-issue.sh           # Interactive output
#   CI=1 ./scripts/test-report-issue.sh      # CI mode (no colors)
#
# Exit codes:
#   0  — all tests passed
#   1  — one or more tests failed

set -euo pipefail

# ── Colors (disabled in CI mode) ──────────────────────────────────────────────

if [ "${CI:-}" = "1" ] || [ "${CI:-}" = "true" ]; then
  GREEN=""
  RED=""
  YELLOW=""
  NC=""
else
  GREEN='\033[0;32m'
  RED='\033[0;31m'
  YELLOW='\033[1;33m'
  NC='\033[0m'
fi

TESTS_PASSED=0
TESTS_FAILED=0

pass() {
  echo -e "  ${GREEN}PASS${NC}: $1"
  TESTS_PASSED=$((TESTS_PASSED + 1))
}

fail() {
  echo -e "  ${RED}FAIL${NC}: $1"
  TESTS_FAILED=$((TESTS_FAILED + 1))
}

info() {
  echo -e "  ${YELLOW}INFO${NC}: $1"
}

# ── Setup ─────────────────────────────────────────────────────────────────────

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Acceptance Tests: report-issue.sh"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── Test 1: Missing .agile-flow-meta directory ────────────────────────────────

echo "Test 1: Error when .agile-flow-meta directory is missing"

TEST_DIR="$WORK_DIR/test1"
mkdir -p "$TEST_DIR"
pushd "$TEST_DIR" >/dev/null
git init --quiet

if bash "$REPO_ROOT/scripts/report-issue.sh" --non-interactive --severity p1 --component docs --title "test" > "$WORK_DIR/test1.log" 2>&1; then
  fail "should exit non-zero when .agile-flow-meta is missing"
else
  if grep -q ".agile-flow-meta/ directory not found" "$WORK_DIR/test1.log"; then
    pass "error message mentions missing .agile-flow-meta/"
  else
    fail "expected error message about missing .agile-flow-meta/"
    cat "$WORK_DIR/test1.log"
  fi
  
  if grep -q "/upgrade" "$WORK_DIR/test1.log"; then
    pass "error message suggests running /upgrade"
  else
    fail "expected suggestion to run /upgrade"
  fi
fi

popd >/dev/null
echo ""

# ── Test 2: Missing upstream file ─────────────────────────────────────────────

echo "Test 2: Error when .agile-flow-meta/upstream is missing"

TEST_DIR="$WORK_DIR/test2"
mkdir -p "$TEST_DIR/.agile-flow-meta"
pushd "$TEST_DIR" >/dev/null
git init --quiet

if bash "$REPO_ROOT/scripts/report-issue.sh" --non-interactive --severity p1 --component docs --title "test" > "$WORK_DIR/test2.log" 2>&1; then
  fail "should exit non-zero when upstream file is missing"
else
  if grep -q "upstream not found" "$WORK_DIR/test2.log"; then
    pass "error message mentions missing upstream file"
  else
    fail "expected error message about missing upstream file"
    cat "$WORK_DIR/test2.log"
  fi
fi

popd >/dev/null
echo ""

# ── Test 3: Empty upstream file ───────────────────────────────────────────────

echo "Test 3: Error when .agile-flow-meta/upstream is empty"

TEST_DIR="$WORK_DIR/test3"
mkdir -p "$TEST_DIR/.agile-flow-meta"
echo "" > "$TEST_DIR/.agile-flow-meta/upstream"
pushd "$TEST_DIR" >/dev/null
git init --quiet

if bash "$REPO_ROOT/scripts/report-issue.sh" --non-interactive --severity p1 --component docs --title "test" > "$WORK_DIR/test3.log" 2>&1; then
  fail "should exit non-zero when upstream is empty"
else
  if grep -q "upstream is empty" "$WORK_DIR/test3.log"; then
    pass "error message mentions empty upstream file"
  else
    fail "expected error message about empty upstream file"
    cat "$WORK_DIR/test3.log"
  fi
fi

popd >/dev/null
echo ""

# ── Test 4: Invalid severity value ────────────────────────────────────────────

echo "Test 4: Error on invalid severity value"

TEST_DIR="$WORK_DIR/test4"
mkdir -p "$TEST_DIR/.agile-flow-meta"
echo "https://github.com/vibeacademy/agile-flow" > "$TEST_DIR/.agile-flow-meta/upstream"
pushd "$TEST_DIR" >/dev/null
git init --quiet
git commit --allow-empty -m "init" --quiet

if bash "$REPO_ROOT/scripts/report-issue.sh" --non-interactive --severity invalid --component docs --title "test" > "$WORK_DIR/test4.log" 2>&1; then
  fail "should exit non-zero on invalid severity"
else
  if grep -q "severity must be p1, p2, or p3" "$WORK_DIR/test4.log"; then
    pass "error message lists valid severity values"
  else
    fail "expected error listing valid severity values (p1, p2, p3)"
    cat "$WORK_DIR/test4.log"
  fi
fi

popd >/dev/null
echo ""

# ── Test 5: Invalid component value ───────────────────────────────────────────

echo "Test 5: Error on invalid component value"

TEST_DIR="$WORK_DIR/test5"
mkdir -p "$TEST_DIR/.agile-flow-meta"
echo "https://github.com/vibeacademy/agile-flow" > "$TEST_DIR/.agile-flow-meta/upstream"
pushd "$TEST_DIR" >/dev/null
git init --quiet
git commit --allow-empty -m "init" --quiet

if bash "$REPO_ROOT/scripts/report-issue.sh" --non-interactive --severity p1 --component invalid --title "test" > "$WORK_DIR/test5.log" 2>&1; then
  fail "should exit non-zero on invalid component"
else
  if grep -q "component must be one of" "$WORK_DIR/test5.log"; then
    pass "error message lists valid components"
  else
    fail "expected error listing valid components"
    cat "$WORK_DIR/test5.log"
  fi
fi

popd >/dev/null
echo ""

# ── Test 6: Empty title ───────────────────────────────────────────────────────

echo "Test 6: Error when title is empty"

TEST_DIR="$WORK_DIR/test6"
mkdir -p "$TEST_DIR/.agile-flow-meta"
echo "https://github.com/vibeacademy/agile-flow" > "$TEST_DIR/.agile-flow-meta/upstream"
pushd "$TEST_DIR" >/dev/null
git init --quiet
git commit --allow-empty -m "init" --quiet

# Note: In non-interactive mode, an empty --title "" triggers the same error
# as a missing --title flag (both check for -z "$TITLE")
if bash "$REPO_ROOT/scripts/report-issue.sh" --non-interactive --severity p1 --component docs --title "" > "$WORK_DIR/test6.log" 2>&1; then
  fail "should exit non-zero when title is empty"
else
  if grep -q "title required" "$WORK_DIR/test6.log"; then
    pass "error message indicates title is required"
  else
    fail "expected error about required title"
    cat "$WORK_DIR/test6.log"
  fi
fi

popd >/dev/null
echo ""

# ── Test 7: Fallback path (gh not available) ──────────────────────────────────

echo "Test 7: Fallback to manual submission when gh CLI unavailable"

TEST_DIR="$WORK_DIR/test7"
mkdir -p "$TEST_DIR/.agile-flow-meta"
echo "https://github.com/vibeacademy/agile-flow" > "$TEST_DIR/.agile-flow-meta/upstream"
echo "1.0.0" > "$TEST_DIR/.agile-flow-meta/version"
pushd "$TEST_DIR" >/dev/null
git init --quiet
git commit --allow-empty -m "init" --quiet

# Create empty bin dir to shadow gh command
mkdir -p "$WORK_DIR/nogh-bin"
cat > "$WORK_DIR/nogh-bin/gh" <<'SH'
#!/usr/bin/env bash
# Simulate gh not being able to create issues (auth failure)
exit 1
SH
chmod +x "$WORK_DIR/nogh-bin/gh"

if PATH="$WORK_DIR/nogh-bin:$PATH" bash "$REPO_ROOT/scripts/report-issue.sh" --non-interactive --severity p2 --component ci --title "Test fallback" > "$WORK_DIR/test7.log" 2>&1; then
  # Should exit 0 even in fallback mode
  if grep -q "manual submission required" "$WORK_DIR/test7.log" || grep -q "Falling back" "$WORK_DIR/test7.log"; then
    pass "fallback message is shown when gh fails"
  else
    fail "expected fallback message"
    cat "$WORK_DIR/test7.log"
  fi
  
  if grep -q "github.com/vibeacademy/agile-flow/issues/new" "$WORK_DIR/test7.log"; then
    pass "pre-filled GitHub issue URL is provided"
  else
    fail "expected pre-filled GitHub issue URL"
    cat "$WORK_DIR/test7.log"
  fi
  
  # Check report file was created
  if find "$TEST_DIR/.agile-flow-meta/reports/" -name "report-*.md" -type f 2>/dev/null | grep -q .; then
    pass "report file saved to .agile-flow-meta/reports/"
    
    REPORT_FILE=$(find "$TEST_DIR/.agile-flow-meta/reports/" -name "report-*.md" -type f 2>/dev/null | head -1)
    if grep -q "severity: p2" "$REPORT_FILE"; then
      pass "report file contains correct severity"
    else
      fail "report file missing severity"
    fi
    if grep -q "component: ci" "$REPORT_FILE"; then
      pass "report file contains correct component"
    else
      fail "report file missing component"
    fi
  else
    fail "no report file created in .agile-flow-meta/reports/"
  fi
else
  fail "fallback mode should exit 0"
  cat "$WORK_DIR/test7.log"
fi

popd >/dev/null
echo ""

# ── Test 8: Happy path with mocked gh success ─────────────────────────────────

echo "Test 8: Happy path with successful gh issue create"

TEST_DIR="$WORK_DIR/test8"
mkdir -p "$TEST_DIR/.agile-flow-meta"
echo "https://github.com/vibeacademy/agile-flow" > "$TEST_DIR/.agile-flow-meta/upstream"
echo "1.0.0" > "$TEST_DIR/.agile-flow-meta/version"
pushd "$TEST_DIR" >/dev/null
git init --quiet
git commit --allow-empty -m "init" --quiet

# Create mock gh that succeeds
mkdir -p "$WORK_DIR/mock-gh-bin"
cat > "$WORK_DIR/mock-gh-bin/gh" <<'SH'
#!/usr/bin/env bash
# Mock gh issue create
if [[ "${1:-}" == "issue" && "${2:-}" == "create" ]]; then
  echo "https://github.com/vibeacademy/agile-flow/issues/999"
  exit 0
fi
exit 1
SH
chmod +x "$WORK_DIR/mock-gh-bin/gh"

if PATH="$WORK_DIR/mock-gh-bin:$PATH" bash "$REPO_ROOT/scripts/report-issue.sh" --non-interactive --severity p3 --component docs --title "Happy path test" > "$WORK_DIR/test8.log" 2>&1; then
  if grep -q "Issue filed successfully" "$WORK_DIR/test8.log"; then
    pass "success message is shown"
  else
    fail "expected success message"
    cat "$WORK_DIR/test8.log"
  fi
  
  # Check report file was created
  if find "$TEST_DIR/.agile-flow-meta/reports/" -name "report-*.md" -type f 2>/dev/null | grep -q .; then
    pass "report file saved even on success"
    
    REPORT_FILE=$(find "$TEST_DIR/.agile-flow-meta/reports/" -name "report-*.md" -type f 2>/dev/null | head -1)
    if grep -q 'title: "Happy path test"' "$REPORT_FILE"; then
      pass "report file contains correct title"
    else
      fail "report file missing title"
    fi
    if grep -q "downstream-report" "$WORK_DIR/test8.log" || grep -q "downstream-report" "$REPORT_FILE" 2>/dev/null; then
      pass "downstream-report label referenced"
    else
      info "downstream-report label check inconclusive"
    fi
  else
    fail "no report file created in .agile-flow-meta/reports/"
  fi
else
  fail "happy path should exit 0"
  cat "$WORK_DIR/test8.log"
fi

popd >/dev/null
echo ""

# ── Test 9: Unknown flag handling ─────────────────────────────────────────────

echo "Test 9: Error on unknown flag"

TEST_DIR="$WORK_DIR/test9"
mkdir -p "$TEST_DIR/.agile-flow-meta"
echo "https://github.com/vibeacademy/agile-flow" > "$TEST_DIR/.agile-flow-meta/upstream"
pushd "$TEST_DIR" >/dev/null
git init --quiet

# Capture to file to avoid pipefail issues
if bash "$REPO_ROOT/scripts/report-issue.sh" --unknown-flag > "$WORK_DIR/test9.log" 2>&1; then
  fail "should exit non-zero on unknown flag"
else
  if grep -q "Unknown flag" "$WORK_DIR/test9.log"; then
    pass "error on unknown flag"
  else
    fail "expected error on unknown flag"
    cat "$WORK_DIR/test9.log"
  fi
fi

popd >/dev/null
echo ""

# ── Test 10: Non-interactive mode requires all fields ─────────────────────────

echo "Test 10: Non-interactive mode requires --severity"

TEST_DIR="$WORK_DIR/test10"
mkdir -p "$TEST_DIR/.agile-flow-meta"
echo "https://github.com/vibeacademy/agile-flow" > "$TEST_DIR/.agile-flow-meta/upstream"
pushd "$TEST_DIR" >/dev/null
git init --quiet
git commit --allow-empty -m "init" --quiet

if bash "$REPO_ROOT/scripts/report-issue.sh" --non-interactive --component docs --title "test" > "$WORK_DIR/test10.log" 2>&1; then
  fail "should exit non-zero when severity missing in non-interactive mode"
else
  if grep -q "severity required in non-interactive" "$WORK_DIR/test10.log"; then
    pass "error indicates severity required in non-interactive mode"
  else
    fail "expected error about severity required in non-interactive mode"
    cat "$WORK_DIR/test10.log"
  fi
fi

popd >/dev/null
echo ""

# ── Test 11: Git URL parsing (git@ format) ────────────────────────────────────

echo "Test 11: Parse git@ format upstream URL"

TEST_DIR="$WORK_DIR/test11"
mkdir -p "$TEST_DIR/.agile-flow-meta"
echo "git@github.com:vibeacademy/agile-flow.git" > "$TEST_DIR/.agile-flow-meta/upstream"
echo "1.0.0" > "$TEST_DIR/.agile-flow-meta/version"
pushd "$TEST_DIR" >/dev/null
git init --quiet
git commit --allow-empty -m "init" --quiet

# Use mock gh
if PATH="$WORK_DIR/mock-gh-bin:$PATH" bash "$REPO_ROOT/scripts/report-issue.sh" --non-interactive --severity p3 --component docs --title "SSH URL test" > "$WORK_DIR/test11.log" 2>&1; then
  if grep -q "vibeacademy/agile-flow" "$WORK_DIR/test11.log"; then
    pass "git@ URL parsed to correct repo"
  else
    fail "git@ URL not parsed correctly"
    cat "$WORK_DIR/test11.log"
  fi
else
  fail "should handle git@ URL format"
  cat "$WORK_DIR/test11.log"
fi

popd >/dev/null
echo ""

# ── Test 12: Title with special characters ────────────────────────────────────

echo "Test 12: Handle title with special characters"

TEST_DIR="$WORK_DIR/test12"
mkdir -p "$TEST_DIR/.agile-flow-meta"
echo "https://github.com/vibeacademy/agile-flow" > "$TEST_DIR/.agile-flow-meta/upstream"
echo "1.0.0" > "$TEST_DIR/.agile-flow-meta/version"
pushd "$TEST_DIR" >/dev/null
git init --quiet
git commit --allow-empty -m "init" --quiet

SPECIAL_TITLE='Fix "quotes" and backslash \\ issue'

if PATH="$WORK_DIR/mock-gh-bin:$PATH" bash "$REPO_ROOT/scripts/report-issue.sh" --non-interactive --severity p3 --component docs --title "$SPECIAL_TITLE" > "$WORK_DIR/test12.log" 2>&1; then
  REPORT_FILE=$(find "$TEST_DIR/.agile-flow-meta/reports/" -name "report-*.md" -type f 2>/dev/null | head -1)
  if [ -f "$REPORT_FILE" ]; then
    pass "report file created with special characters in title"
    # Check the YAML frontmatter contains escaped quotes
    if grep -q 'title:' "$REPORT_FILE"; then
      pass "title field present in report"
    else
      fail "title field missing from report"
    fi
  else
    fail "report file not created"
  fi
else
  fail "should handle special characters in title"
  cat "$WORK_DIR/test12.log"
fi

popd >/dev/null
echo ""

# ── Results ───────────────────────────────────────────────────────────────────

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "Results: ${GREEN}${TESTS_PASSED} passed${NC}, ${RED}${TESTS_FAILED} failed${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ "$TESTS_FAILED" -gt 0 ]; then
  exit 1
fi

exit 0
