#!/bin/bash
#
# test-upgrade-cycle.sh — Automated upgrade cycle testing
#
# Tests the /upgrade flow against various dirty fork states.
# Creates isolated temp directories, applies scenarios, runs upgrade,
# and validates outcomes.
#
# Usage:
#   bash scripts/test-upgrade-cycle.sh                    # Run all scenarios
#   bash scripts/test-upgrade-cycle.sh <scenario>         # Run specific scenario
#   bash scripts/test-upgrade-cycle.sh --list             # List scenarios
#
# Exit codes:
#   0 — All tests passed
#   1 — One or more tests failed

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
TEST_WORKDIR="${TEST_WORKDIR:-/tmp/agile-flow-upgrade-tests}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
log_fail() { echo -e "${RED}[FAIL]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

# Test results tracking
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0
declare -a FAILED_TESTS=()

# Initialize a fresh test fork
init_test_fork() {
  local test_name="$1"
  local test_dir="$TEST_WORKDIR/$test_name"
  
  rm -rf "$test_dir"
  mkdir -p "$test_dir"
  
  # Copy repo (excluding .git to simulate fresh clone, then re-init)
  rsync -a --exclude='.git' --exclude='node_modules' --exclude='.venv' \
    "$REPO_ROOT/" "$test_dir/"
  
  cd "$test_dir" || exit
  git init -q
  git add -A
  git commit -q -m "Initial fork state"
  
  # Set up as downstream fork
  mkdir -p .agile-flow-meta
  echo "vibeacademy/agile-flow" > .agile-flow-meta/upstream
  echo "v1.0.8" > .agile-flow-meta/version  # Start one version behind
  
  git add .agile-flow-meta
  git commit -q -m "Configure as downstream fork"
  
  echo "$test_dir"
}

# Apply a dirty scenario (inline, not calling external script)
apply_scenario() {
  local scenario="$1"
  
  case "$scenario" in
    post-bootstrap-product)
      mkdir -p docs
      cat > docs/PRODUCT-DEFINITION.md << 'PDEOF'
# Product Definition
## Vision
Test product for upgrade testing.
## Target Users
- Developers testing upgrade flows
PDEOF
      cat > docs/PRODUCT-ROADMAP.md << 'PREOF'
# Product Roadmap
## Phase 1
- [ ] Test upgrade flow
PREOF
      git add docs/PRODUCT-*.md
      git commit -q -m "Complete bootstrap-product"
      ;;
      
    modified-agents)
      if [ -f ".claude/agents/github-ticket-worker.md" ]; then
        {
          echo ""
          echo "## Custom Team Guidelines"
          echo "- Use TypeScript strict mode"
          echo "- Prefer functional components"
        } >> .claude/agents/github-ticket-worker.md
        git add .claude/agents/github-ticket-worker.md
        git commit -q -m "Add custom agent guidelines"
      fi
      ;;
      
    has-overrides)
      cat > .agile-flow-overrides << 'OVEOF'
# Protected files
.claude/agents/github-ticket-worker.md
.claude/commands/work-ticket.md
OVEOF
      git add .agile-flow-overrides
      git commit -q -m "Configure overrides"
      ;;
      
    uncommitted-framework)
      if [ -f "scripts/doctor.sh" ]; then
        echo "# DEBUG: test modification" >> scripts/doctor.sh
      fi
      # Don't commit - leave dirty
      ;;
      
    uncommitted-userland)
      mkdir -p app/components
      echo "// WIP component" > app/components/Button.tsx
      # Don't commit - leave dirty
      ;;
      
    stale-version)
      echo "v0.9.0" > .agile-flow-meta/version
      git add .agile-flow-meta/version
      git commit -q -m "Set stale version"
      ;;
      
    clean)
      # Already clean from init
      ;;
      
    *)
      log_warn "Unknown scenario: $scenario"
      return 1
      ;;
  esac
}

# Run upgrade and capture results
run_upgrade() {
  local test_dir="$1"
  local output_file="$test_dir/.upgrade-output.txt"
  local exit_code
  
  cd "$test_dir" || exit
  
  # Run template-sync.sh and capture output
  if [ -f "scripts/template-sync.sh" ]; then
    bash scripts/template-sync.sh > "$output_file" 2>&1 || true
    exit_code=$?
  else
    echo "ERROR: template-sync.sh not found" > "$output_file"
    exit_code=127
  fi
  
  echo "$exit_code"
}

# Validation functions
check_no_conflict_markers() {
  local test_dir="$1"
  if grep -rq "<<<<<<< " "$test_dir" --include="*.md" --include="*.sh" 2>/dev/null; then
    return 1
  fi
  return 0
}

check_version_updated() {
  local test_dir="$1"
  local expected_version="${2:-v1.0.9}"
  local actual_version
  
  if [ -f "$test_dir/.agile-flow-meta/version" ]; then
    actual_version=$(cat "$test_dir/.agile-flow-meta/version")
    [ "$actual_version" = "$expected_version" ]
  else
    return 1
  fi
}

check_overrides_preserved() {
  local test_dir="$1"
  local override_file="$2"
  
  # If override was configured and file exists, check it wasn't overwritten
  if [ -f "$test_dir/.agile-flow-overrides" ] && [ -f "$test_dir/$override_file" ]; then
    # Check if custom content still exists
    grep -q "Custom Team Guidelines" "$test_dir/$override_file" 2>/dev/null
  else
    return 0  # No override to check
  fi
}

check_userland_untouched() {
  local test_dir="$1"
  
  # If user content exists, verify it wasn't deleted
  if [ -d "$test_dir/app/components" ]; then
    [ -f "$test_dir/app/components/Button.tsx" ]
  else
    return 0
  fi
}

check_upgrade_blocked() {
  local output_file="$1"
  grep -q "uncommitted changes" "$output_file" 2>/dev/null || \
  grep -q "refusing to upgrade" "$output_file" 2>/dev/null
}

# Test case definitions
# Format: test_<name> { scenario, expected_outcome, validations }

run_test_case() {
  local test_name="$1"
  local scenario="$2"
  local expect_success="$3"  # true/false
  shift 3
  local validations=("$@")
  
  TESTS_RUN=$((TESTS_RUN + 1))
  log_info "Running test: $test_name"
  
  # Initialize fresh fork
  local test_dir
  test_dir=$(init_test_fork "$test_name")
  
  # Apply scenario
  cd "$test_dir" || exit
  apply_scenario "$scenario"
  
  # Run upgrade
  local exit_code
  exit_code=$(run_upgrade "$test_dir")
  local output_file="$test_dir/.upgrade-output.txt"
  
  # Check basic outcome
  local test_passed=true
  
  if [ "$expect_success" = "true" ]; then
    if [ "$exit_code" != "0" ]; then
      log_fail "$test_name: Expected success but got exit code $exit_code"
      cat "$output_file" | head -20
      test_passed=false
    fi
  else
    if [ "$exit_code" = "0" ]; then
      log_fail "$test_name: Expected failure but upgrade succeeded"
      test_passed=false
    fi
  fi
  
  # Run validations
  for validation in "${validations[@]}"; do
    case "$validation" in
      no-conflicts)
        if ! check_no_conflict_markers "$test_dir"; then
          log_fail "$test_name: Found conflict markers"
          test_passed=false
        fi
        ;;
      version-updated)
        if ! check_version_updated "$test_dir"; then
          log_fail "$test_name: Version not updated"
          test_passed=false
        fi
        ;;
      overrides-preserved)
        if ! check_overrides_preserved "$test_dir" ".claude/agents/github-ticket-worker.md"; then
          log_fail "$test_name: Overrides not preserved"
          test_passed=false
        fi
        ;;
      userland-untouched)
        if ! check_userland_untouched "$test_dir"; then
          log_fail "$test_name: Userland content was modified/deleted"
          test_passed=false
        fi
        ;;
      upgrade-blocked)
        if ! check_upgrade_blocked "$output_file"; then
          log_fail "$test_name: Upgrade should have been blocked"
          test_passed=false
        fi
        ;;
    esac
  done
  
  if [ "$test_passed" = "true" ]; then
    log_pass "$test_name"
    TESTS_PASSED=$((TESTS_PASSED + 1))
  else
    TESTS_FAILED=$((TESTS_FAILED + 1))
    FAILED_TESTS+=("$test_name")
  fi
  
  # Cleanup
  rm -rf "$test_dir"
}

# Test suite
run_all_tests() {
  log_info "Starting upgrade cycle tests..."
  log_info "Work directory: $TEST_WORKDIR"
  echo ""
  
  mkdir -p "$TEST_WORKDIR"
  
  # Test 1: Clean upgrade (baseline)
  run_test_case "clean-upgrade" "clean" "true" \
    "no-conflicts" "version-updated"
  
  # Test 2: Post-bootstrap-product upgrade
  run_test_case "post-bootstrap-product-upgrade" "post-bootstrap-product" "true" \
    "no-conflicts" "version-updated"
  
  # Test 3: Modified agents (without overrides - should get overwritten)
  run_test_case "modified-agents-no-override" "modified-agents" "true" \
    "no-conflicts" "version-updated"
  
  # Test 4: Modified agents WITH overrides (should preserve)
  # This needs a compound scenario
  run_test_case_compound "modified-agents-with-override" \
    "modified-agents" "has-overrides" \
    "true" \
    "no-conflicts" "version-updated" "overrides-preserved"
  
  # Test 5: Uncommitted framework files (should block)
  run_test_case "uncommitted-framework-blocked" "uncommitted-framework" "false" \
    "upgrade-blocked"
  
  # Test 6: Uncommitted userland files (should allow)
  run_test_case "uncommitted-userland-allowed" "uncommitted-userland" "true" \
    "no-conflicts" "userland-untouched"
  
  # Test 7: Stale version upgrade
  run_test_case "stale-version-upgrade" "stale-version" "true" \
    "no-conflicts" "version-updated"
  
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo -e "Tests run: $TESTS_RUN | ${GREEN}Passed: $TESTS_PASSED${NC} | ${RED}Failed: $TESTS_FAILED${NC}"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  
  if [ ${#FAILED_TESTS[@]} -gt 0 ]; then
    echo ""
    log_fail "Failed tests:"
    for t in "${FAILED_TESTS[@]}"; do
      echo "  - $t"
    done
    return 1
  fi
  
  return 0
}

# Compound scenario test (applies multiple scenarios)
run_test_case_compound() {
  local test_name="$1"
  local scenario1="$2"
  local scenario2="$3"
  local expect_success="$4"
  shift 4
  local validations=("$@")
  
  TESTS_RUN=$((TESTS_RUN + 1))
  log_info "Running test: $test_name (compound)"
  
  local test_dir
  test_dir=$(init_test_fork "$test_name")
  
  cd "$test_dir" || exit
  apply_scenario "$scenario1"
  apply_scenario "$scenario2"
  
  local exit_code
  exit_code=$(run_upgrade "$test_dir")
  local output_file="$test_dir/.upgrade-output.txt"
  
  local test_passed=true
  
  if [ "$expect_success" = "true" ]; then
    if [ "$exit_code" != "0" ]; then
      log_fail "$test_name: Expected success but got exit code $exit_code"
      cat "$output_file" | head -20
      test_passed=false
    fi
  else
    if [ "$exit_code" = "0" ]; then
      log_fail "$test_name: Expected failure but upgrade succeeded"
      test_passed=false
    fi
  fi
  
  for validation in "${validations[@]}"; do
    case "$validation" in
      no-conflicts)
        if ! check_no_conflict_markers "$test_dir"; then
          log_fail "$test_name: Found conflict markers"
          test_passed=false
        fi
        ;;
      version-updated)
        if ! check_version_updated "$test_dir"; then
          log_fail "$test_name: Version not updated"
          test_passed=false
        fi
        ;;
      overrides-preserved)
        if ! check_overrides_preserved "$test_dir" ".claude/agents/github-ticket-worker.md"; then
          log_fail "$test_name: Overrides not preserved"
          test_passed=false
        fi
        ;;
      userland-untouched)
        if ! check_userland_untouched "$test_dir"; then
          log_fail "$test_name: Userland content was modified/deleted"
          test_passed=false
        fi
        ;;
      upgrade-blocked)
        if ! check_upgrade_blocked "$output_file"; then
          log_fail "$test_name: Upgrade should have been blocked"
          test_passed=false
        fi
        ;;
    esac
  done
  
  if [ "$test_passed" = "true" ]; then
    log_pass "$test_name"
    TESTS_PASSED=$((TESTS_PASSED + 1))
  else
    TESTS_FAILED=$((TESTS_FAILED + 1))
    FAILED_TESTS+=("$test_name")
  fi
  
  rm -rf "$test_dir"
}

# Single scenario test
run_single_test() {
  local scenario="$1"
  
  log_info "Running single scenario test: $scenario"
  mkdir -p "$TEST_WORKDIR"
  
  local test_dir
  test_dir=$(init_test_fork "single-$scenario")
  
  cd "$test_dir" || exit
  apply_scenario "$scenario"
  
  log_info "Test fork ready at: $test_dir"
  log_info "Run upgrade manually: cd $test_dir && bash scripts/template-sync.sh"
  echo ""
  log_info "Current state:"
  git status --short
  echo ""
  log_info "Version: $(cat .agile-flow-meta/version 2>/dev/null || echo 'not set')"
}

# List available tests
list_tests() {
  echo ""
  echo "Available test scenarios:"
  echo ""
  echo "  clean                    — Fresh fork, no changes"
  echo "  post-bootstrap-product   — Has PRODUCT-*.md files"
  echo "  modified-agents          — Custom agent guidelines added"
  echo "  has-overrides            — .agile-flow-overrides configured"
  echo "  uncommitted-framework    — Dirty framework files (should block)"
  echo "  uncommitted-userland     — Dirty user content (should allow)"
  echo "  stale-version            — Old version marker"
  echo ""
  echo "Usage:"
  echo "  bash scripts/test-upgrade-cycle.sh           # Run full test suite"
  echo "  bash scripts/test-upgrade-cycle.sh <scenario> # Setup single scenario for manual testing"
  echo ""
}

# Main
main() {
  local arg="${1:-all}"
  
  case "$arg" in
    --list|-l|list)
      list_tests
      ;;
    --help|-h|help)
      list_tests
      ;;
    all)
      run_all_tests
      ;;
    *)
      run_single_test "$arg"
      ;;
  esac
}

main "$@"
