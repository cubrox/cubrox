#!/usr/bin/env bash
# report-issue.test.sh — Tests for --dry-run / --fixture-repo flags on report-issue.sh
#
# Run:
#   ./scripts/report-issue.test.sh           # interactive output
#   CI=1 ./scripts/report-issue.test.sh      # CI mode (no colors)
#
# Exit codes: 0 if all tests pass, 1 if any test fails.
#
# The tests use a stub `gh` on PATH to record the args the script tries to send,
# without making real network calls. The default-mode and fixture-mode tests
# assert which `--repo` the script targets; the dry-run test asserts that the
# stub `gh` is never invoked.

set -euo pipefail

if [ "${CI:-}" = "1" ] || [ "${CI:-}" = "true" ]; then
  GREEN=""; RED=""; NC=""
else
  GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
fi

TESTS_PASSED=0
TESTS_FAILED=0

pass() { echo -e "  ${GREEN}PASS${NC}: $1"; TESTS_PASSED=$((TESTS_PASSED + 1)); }
fail() { echo -e "  ${RED}FAIL${NC}: $1"; TESTS_FAILED=$((TESTS_FAILED + 1)); }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/report-issue.sh"
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

# Stub `gh`. Records every invocation to $GH_LOG (one line per call) and exits 0
# for `issue create`. `auth status` returns success without ghu_ tokens so the
# Codespaces fallback path is not triggered. `label list` returns the
# downstream-report label so the live-mode test follows the labeled branch.
SHIM_DIR="$WORK_DIR/shim"
mkdir -p "$SHIM_DIR"
cat > "$SHIM_DIR/gh" <<'SHIM'
#!/usr/bin/env bash
# Record each call so the test can assert what was attempted.
printf '%s\n' "$*" >> "$GH_LOG"
case "$1" in
  auth)
    if [ "${2:-}" = "status" ]; then echo "Logged in (test stub)"; exit 0; fi ;;
  label)
    if [ "${2:-}" = "list" ]; then echo "downstream-report"; exit 0; fi ;;
  issue)
    if [ "${2:-}" = "create" ]; then echo "https://github.com/test/stub/issues/1"; exit 0; fi ;;
esac
exit 0
SHIM
chmod +x "$SHIM_DIR/gh"

# Fresh workspace + fake .gembaflow-version pointing at the canonical upstream.
make_workspace() {
  local dir="$1"
  mkdir -p "$dir"
  ( cd "$dir" && git init --quiet && git commit --allow-empty -m init --quiet )
  cat > "$dir/.gembaflow-version" <<JSON
{"upstream": "https://github.com/vibeacademy/gembaflow", "version": "v1.4.0"}
JSON
}

# Run report-issue.sh with the gh stub on PATH. Sets $GH_LOG per call so each
# test's invocation log is isolated.
run_under_stub() {
  local workdir="$1"; shift
  local log="$workdir/gh.log"
  : > "$log"
  ( cd "$workdir" && GH_LOG="$log" PATH="$SHIM_DIR:$PATH" bash "$SCRIPT" "$@" )
  return $?
}

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Tests: report-issue.sh --dry-run / --fixture-repo"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Test (a): default mode files an issue against the upstream from .gembaflow-version.
TEST_DIR="$WORK_DIR/a-default"
make_workspace "$TEST_DIR"
set +e
run_under_stub "$TEST_DIR" \
  --non-interactive --severity p2 --component docs --title "default-mode test" \
  --body "Test body" > "$TEST_DIR/out.log" 2>&1
rc=$?
set -e
echo ""
echo "(a) Default mode targets upstream repo from .gembaflow-version"
if [ "$rc" -eq 0 ]; then
  pass "exit 0"
else
  fail "expected exit 0, got $rc"
  cat "$TEST_DIR/out.log"
fi
if grep -q "issue create --repo vibeacademy/gembaflow " "$TEST_DIR/gh.log"; then
  pass "gh issue create --repo vibeacademy/gembaflow was attempted"
else
  fail "did not see 'gh issue create --repo vibeacademy/gembaflow' in shim log"
  cat "$TEST_DIR/gh.log"
fi

# Test (b): --dry-run mode never invokes gh.
TEST_DIR="$WORK_DIR/b-dryrun"
make_workspace "$TEST_DIR"
set +e
run_under_stub "$TEST_DIR" \
  --dry-run --non-interactive --severity p2 --component docs \
  --title "dry-run test" --body "Test body" > "$TEST_DIR/out.log" 2>&1
rc=$?
set -e
echo ""
echo "(b) --dry-run makes zero gh calls"
if [ "$rc" -eq 0 ]; then
  pass "exit 0"
else
  fail "expected exit 0, got $rc"
  cat "$TEST_DIR/out.log"
fi
if [ ! -s "$TEST_DIR/gh.log" ]; then
  pass "gh shim log is empty (no network calls attempted)"
else
  fail "expected empty gh log, got:"
  cat "$TEST_DIR/gh.log"
fi
if grep -q "DRY RUN - No issue created" "$TEST_DIR/out.log"; then
  pass "preview output includes 'DRY RUN - No issue created'"
else
  fail "missing 'DRY RUN - No issue created' marker in stdout"
fi

# Test (c): --fixture-repo retargets gh issue create to the fixture slug.
TEST_DIR="$WORK_DIR/c-fixture"
make_workspace "$TEST_DIR"
set +e
run_under_stub "$TEST_DIR" \
  --fixture-repo va-worker/gembaflow-test-fixture \
  --non-interactive --severity p2 --component docs \
  --title "fixture test" --body "Test body" > "$TEST_DIR/out.log" 2>&1
rc=$?
set -e
echo ""
echo "(c) --fixture-repo retargets the gh issue create call"
if [ "$rc" -eq 0 ]; then
  pass "exit 0"
else
  fail "expected exit 0, got $rc"
  cat "$TEST_DIR/out.log"
fi
if grep -q "issue create --repo va-worker/gembaflow-test-fixture " "$TEST_DIR/gh.log"; then
  pass "gh issue create --repo va-worker/gembaflow-test-fixture was attempted"
else
  fail "did not see fixture-repo slug in shim log"
  cat "$TEST_DIR/gh.log"
fi
if grep -q "issue create --repo vibeacademy/gembaflow " "$TEST_DIR/gh.log"; then
  fail "upstream repo should NOT be targeted when --fixture-repo is set"
else
  pass "upstream repo was not targeted"
fi

# Test (d): invalid --fixture-repo slug rejected.
TEST_DIR="$WORK_DIR/d-bad-slug"
make_workspace "$TEST_DIR"
set +e
run_under_stub "$TEST_DIR" \
  --fixture-repo bad-slug \
  --non-interactive --severity p2 --component docs \
  --title "bad slug" --body "Test body" > "$TEST_DIR/out.log" 2>&1
rc=$?
set -e
echo ""
echo "(d) Invalid --fixture-repo slug is rejected"
if [ "$rc" -ne 0 ]; then
  pass "exit non-zero on bad slug"
else
  fail "expected non-zero exit, got $rc"
fi
if grep -q "must match 'org/name'" "$TEST_DIR/out.log"; then
  pass "error message mentions the 'org/name' format"
else
  fail "missing format hint in error message"
  cat "$TEST_DIR/out.log"
fi

# Test (e): --dry-run and --fixture-repo together is a hard error.
TEST_DIR="$WORK_DIR/e-mutex"
make_workspace "$TEST_DIR"
set +e
run_under_stub "$TEST_DIR" \
  --dry-run --fixture-repo va-worker/test-fixture \
  --non-interactive --severity p2 --component docs \
  --title "mutex" --body "Test body" > "$TEST_DIR/out.log" 2>&1
rc=$?
set -e
echo ""
echo "(e) --dry-run + --fixture-repo is mutually exclusive"
if [ "$rc" -ne 0 ]; then
  pass "exit non-zero"
else
  fail "expected non-zero exit, got $rc"
fi
if grep -q "mutually exclusive" "$TEST_DIR/out.log"; then
  pass "error message includes 'mutually exclusive'"
else
  fail "missing 'mutually exclusive' wording"
  cat "$TEST_DIR/out.log"
fi

# ── Summary ───────────────────────────────────────────────────────────────────

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Passed: $TESTS_PASSED   Failed: $TESTS_FAILED"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

[ "$TESTS_FAILED" -eq 0 ]
