#!/bin/bash

# Bot Permissions Verification Script
#
# Verifies that worker and reviewer bot accounts have correct permissions
# and are properly restricted from destructive actions.
#
# Configuration: Set these variables for your project:
#   REPO - Your GitHub org/repo (e.g., "your-org/your-repo")
#   WORKER_BOT - Your worker bot account name (default: {org}-worker)
#   REVIEWER_BOT - Your reviewer bot account name (default: {org}-reviewer)
#
# See .claude/README.md for bot account setup instructions.

# Don't use set -e as we handle errors manually in tests

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration - CUSTOMIZE THESE FOR YOUR PROJECT
# If not set, try to detect from git remote
REPO="${REPO:-}"
if [ -z "$REPO" ]; then
  REPO=$(git remote get-url origin 2>/dev/null | sed -E 's|.*github.com[:/]||' | sed 's/.git$//')
fi
if [ -z "$REPO" ]; then
  echo "Error: Could not determine repository. Set REPO environment variable."
  exit 1
fi

MAIN_BRANCH="main"

# Bot account names - customize for your organization
# Default pattern: {org}-worker and {org}-reviewer
ORG=$(echo "$REPO" | cut -d'/' -f1)
WORKER_BOT="${WORKER_BOT:-${ORG}-worker}"
REVIEWER_BOT="${REVIEWER_BOT:-${ORG}-reviewer}"

# CI check name deprecation aliases
# ---------------------------------
# When this script's expected_checks list is renamed (e.g. v1.2.1 renamed
# `typecheck` → `version-parity`), forks need a release cycle to rename
# their own `.github/workflows/ci.yml` job to match. During that window,
# the script should accept EITHER the new name OR the old name so the
# fork's required-check verification keeps passing.
#
# Convention: when adding a new alias, add an entry below with the
# DEPRECATED_AT: marker so the cleanup-bot can grep for stale entries:
#
#   [old-name]=new-name  # DEPRECATED_AT: vX.Y.Z; remove in vX.Y+1
#
# The KEY is the old (deprecated) name; the VALUE is the new (canonical)
# name listed in expected_checks. To find all active aliases:
#
#   grep -n "DEPRECATED_AT:" scripts/verify-bot-permissions.sh
#
# After one release cycle, file a follow-up PR removing the entry. Forks
# that haven't renamed by then will start failing the verification (which
# is the intended behavior — the grace period has elapsed).
declare -A DEPRECATED_CHECK_ALIASES=(
    # No active aliases at the moment. The mechanism is in place for the
    # next rename. Illustrative example (NOT active):
    #   [typecheck]=version-parity  # DEPRECATED_AT: v1.2.1; remove in v1.3.0
)

# Counters
PASS=0
FAIL=0
SKIP=0

# Store original account
ORIGINAL_ACCOUNT=""

print_header() {
    echo ""
    echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${NC}         ${BLUE}Bot Permissions Verification Script${NC}              ${BLUE}║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

print_section() {
    echo ""
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}$1${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

pass() {
    echo -e "${GREEN}✓ PASS:${NC} $1"
    ((PASS++))
}

fail() {
    echo -e "${RED}✗ FAIL:${NC} $1"
    ((FAIL++))
}

skip() {
    echo -e "${YELLOW}○ SKIP:${NC} $1"
    ((SKIP++))
}

info() {
    echo -e "${BLUE}→${NC} $1"
}

cleanup() {
    # Restore original account if we changed it
    if [ -n "$ORIGINAL_ACCOUNT" ]; then
        gh auth switch --user "$ORIGINAL_ACCOUNT" 2>/dev/null || true
    fi
}

trap cleanup EXIT

get_active_account() {
    gh auth status 2>&1 | grep "Active account: true" -B3 | grep "account" | head -1 | sed 's/.*account //' | sed 's/ .*//'
}

switch_to_account() {
    local account=$1
    gh auth switch --user "$account" 2>/dev/null || return 1
    return 0
}

check_account_exists() {
    local account=$1
    gh auth status 2>&1 | grep -q "account $account" && return 0 || return 1
}

# =============================================================================
# Tests
# =============================================================================

test_worker_exists() {
    info "Checking if $WORKER_BOT account exists..."
    if check_account_exists "$WORKER_BOT"; then
        pass "$WORKER_BOT account exists in gh CLI"
    else
        fail "$WORKER_BOT account not found in gh CLI"
    fi
}

test_reviewer_exists() {
    info "Checking if $REVIEWER_BOT account exists..."
    if check_account_exists "$REVIEWER_BOT"; then
        pass "$REVIEWER_BOT account exists in gh CLI"
    else
        fail "$REVIEWER_BOT account not found in gh CLI"
    fi
}

test_worker_scopes() {
    info "Checking $WORKER_BOT PAT scopes..."

    local status=$(gh auth status 2>&1)
    local worker_section=$(echo "$status" | grep -A5 "account $WORKER_BOT")

    if echo "$worker_section" | grep -q "repo" && \
       echo "$worker_section" | grep -q "read:org" && \
       echo "$worker_section" | grep -q "project" && \
       echo "$worker_section" | grep -q "workflow"; then
        pass "$WORKER_BOT has required scopes (repo, read:org, project, workflow)"
    else
        fail "$WORKER_BOT missing required scopes"
        echo "  Current scopes: $(echo "$worker_section" | grep "Token scopes")"
    fi
}

test_reviewer_scopes() {
    info "Checking $REVIEWER_BOT PAT scopes..."

    local status=$(gh auth status 2>&1)
    local reviewer_section=$(echo "$status" | grep -A5 "account $REVIEWER_BOT")

    if echo "$reviewer_section" | grep -q "repo" && \
       echo "$reviewer_section" | grep -q "read:org" && \
       echo "$reviewer_section" | grep -q "project" && \
       echo "$reviewer_section" | grep -q "workflow"; then
        pass "$REVIEWER_BOT has required scopes (repo, read:org, project, workflow)"
    else
        fail "$REVIEWER_BOT missing required scopes"
        echo "  Current scopes: $(echo "$reviewer_section" | grep "Token scopes")"
    fi
}

test_worker_repo_access() {
    info "Testing if $WORKER_BOT can access repository..."

    if ! switch_to_account "$WORKER_BOT"; then
        fail "$WORKER_BOT repo access test (auth switch failed)"
        return
    fi

    if gh repo view "$REPO" --json name -q '.name' >/dev/null 2>&1; then
        pass "$WORKER_BOT can access repository"
    else
        fail "$WORKER_BOT cannot access repository"
    fi
}

test_worker_pr_api_access() {
    info "Testing if $WORKER_BOT can access PR API (needed to create PRs)..."

    if ! switch_to_account "$WORKER_BOT"; then
        fail "$WORKER_BOT PR API test (auth switch failed)"
        return
    fi

    if gh pr list --repo "$REPO" --limit 1 >/dev/null 2>&1; then
        pass "$WORKER_BOT can access PR API"
    else
        fail "$WORKER_BOT cannot access PR API"
    fi
}

test_reviewer_repo_access() {
    info "Testing if $REVIEWER_BOT can access repository..."

    if ! switch_to_account "$REVIEWER_BOT"; then
        fail "$REVIEWER_BOT repo access test (auth switch failed)"
        return
    fi

    if gh repo view "$REPO" --json name -q '.name' >/dev/null 2>&1; then
        pass "$REVIEWER_BOT can access repository"
    else
        fail "$REVIEWER_BOT cannot access repository"
    fi
}

test_reviewer_pr_api_access() {
    info "Testing if $REVIEWER_BOT can access PR API (needed to review PRs)..."

    if ! switch_to_account "$REVIEWER_BOT"; then
        fail "$REVIEWER_BOT PR API test (auth switch failed)"
        return
    fi

    if gh pr list --repo "$REPO" --limit 1 >/dev/null 2>&1; then
        pass "$REVIEWER_BOT can access PR API"
    else
        fail "$REVIEWER_BOT cannot access PR API"
    fi
}

test_branch_protection_active() {
    info "Testing if branch protection is active on main..."

    # Switch to any authenticated account
    switch_to_account "$WORKER_BOT" 2>/dev/null || true

    local ruleset=$(gh api "repos/$REPO/rulesets" --jq '.[] | select(.name | test("main|Protect"; "i"))' 2>/dev/null)

    if [ -n "$ruleset" ]; then
        local enforcement=$(echo "$ruleset" | jq -r '.enforcement' 2>/dev/null)
        if [ "$enforcement" == "active" ]; then
            pass "Branch protection is active on main"
        else
            fail "Branch protection exists but is not active (enforcement: $enforcement)"
        fi
    else
        fail "No branch protection ruleset found for main"
    fi
}

test_required_status_checks() {
    info "Testing if required status checks are configured..."

    switch_to_account "$WORKER_BOT" 2>/dev/null || true

    # Get ruleset ID first, then query its rules
    local ruleset_id=$(gh api "repos/$REPO/rulesets" --jq '.[0].id' 2>/dev/null)
    local checks=""
    if [ -n "$ruleset_id" ]; then
        checks=$(gh api "repos/$REPO/rulesets/$ruleset_id" --jq '.rules[] | select(.type=="required_status_checks") | .parameters.required_status_checks[].context' 2>/dev/null)
    fi

    if [ -n "$checks" ]; then
        # `version-parity` was previously named `typecheck` (renamed in #361
        # because the job runs JSON + version-parity validation, not `tsc`).
        # In #428 the umbrella was split: `json-validate` is now its own job,
        # and `version-parity` runs only the .gembaflow-version vs package.json
        # parity check. Forks with branch protection need BOTH in required-checks.
        # For future renames, see DEPRECATED_CHECK_ALIASES at the top of
        # this script — entries there let a deprecated old name satisfy
        # the corresponding new-name expectation for one release cycle.
        local expected_checks="lint json-validate version-parity build test"
        local missing=""
        local deprecated_accepted=""

        for check in $expected_checks; do
            if echo "$checks" | grep -q "^$check$"; then
                continue
            fi

            # Not found under the canonical name; try any deprecation
            # alias whose value maps to this expected check.
            local alias_satisfied=""
            for old_name in "${!DEPRECATED_CHECK_ALIASES[@]}"; do
                if [ "${DEPRECATED_CHECK_ALIASES[$old_name]}" = "$check" ] && echo "$checks" | grep -q "^$old_name$"; then
                    alias_satisfied="$old_name"
                    break
                fi
            done

            if [ -n "$alias_satisfied" ]; then
                deprecated_accepted="$deprecated_accepted ${alias_satisfied}→${check}"
            else
                missing="$missing $check"
            fi
        done

        if [ -z "$missing" ]; then
            pass "All required status checks configured (lint, json-validate, version-parity, build, test)"
            if [ -n "$deprecated_accepted" ]; then
                echo -e "  ${YELLOW}↳ accepted via deprecation alias:${NC}$deprecated_accepted"
                echo -e "  ${YELLOW}  rename the fork's CI job to the canonical name before the alias is removed.${NC}"
            fi
        else
            fail "Missing required status checks:$missing"
        fi
    else
        fail "No required status checks configured"
    fi
}

test_approval_required() {
    info "Testing if PR approval is required..."

    switch_to_account "$WORKER_BOT" 2>/dev/null || true

    local ruleset_id=$(gh api "repos/$REPO/rulesets" --jq '.[0].id' 2>/dev/null)
    local approval_count=""
    if [ -n "$ruleset_id" ]; then
        approval_count=$(gh api "repos/$REPO/rulesets/$ruleset_id" --jq '.rules[] | select(.type=="pull_request") | .parameters.required_approving_review_count' 2>/dev/null)
    fi

    if [ -n "$approval_count" ] && [ "$approval_count" -ge 1 ]; then
        pass "PR approval required (count: $approval_count)"
    else
        fail "PR approval not required or count is 0"
    fi
}

test_force_push_blocked() {
    info "Testing if force push is blocked..."

    switch_to_account "$WORKER_BOT" 2>/dev/null || true

    local ruleset_id=$(gh api "repos/$REPO/rulesets" --jq '.[0].id' 2>/dev/null)
    local non_ff=""
    if [ -n "$ruleset_id" ]; then
        non_ff=$(gh api "repos/$REPO/rulesets/$ruleset_id" --jq '.rules[] | select(.type=="non_fast_forward")' 2>/dev/null)
    fi

    if [ -n "$non_ff" ]; then
        pass "Force push blocked (non_fast_forward rule active)"
    else
        fail "Force push NOT blocked"
    fi
}

test_deletion_blocked() {
    info "Testing if branch deletion is blocked..."

    switch_to_account "$WORKER_BOT" 2>/dev/null || true

    local ruleset_id=$(gh api "repos/$REPO/rulesets" --jq '.[0].id' 2>/dev/null)
    local deletion=""
    if [ -n "$ruleset_id" ]; then
        deletion=$(gh api "repos/$REPO/rulesets/$ruleset_id" --jq '.rules[] | select(.type=="deletion")' 2>/dev/null)
    fi

    if [ -n "$deletion" ]; then
        pass "Branch deletion blocked"
    else
        fail "Branch deletion NOT blocked"
    fi
}

test_linear_history_required() {
    info "Testing if linear history is required..."

    switch_to_account "$WORKER_BOT" 2>/dev/null || true

    local ruleset_id=$(gh api "repos/$REPO/rulesets" --jq '.[0].id' 2>/dev/null)
    local linear=""
    if [ -n "$ruleset_id" ]; then
        linear=$(gh api "repos/$REPO/rulesets/$ruleset_id" --jq '.rules[] | select(.type=="required_linear_history")' 2>/dev/null)
    fi

    if [ -n "$linear" ]; then
        pass "Linear history required"
    else
        skip "Linear history not required (optional)"
    fi
}

# =============================================================================
# Main
# =============================================================================

main() {
    print_header

    # Store original account to restore later
    ORIGINAL_ACCOUNT=$(get_active_account)
    info "Current account: $ORIGINAL_ACCOUNT"
    info "Repository: $REPO"
    info "Main branch: $MAIN_BRANCH"

    # Run tests
    print_section "Account Existence Tests"
    test_worker_exists
    test_reviewer_exists

    print_section "PAT Scope Tests"
    test_worker_scopes
    test_reviewer_scopes

    print_section "Repository Access Tests"
    test_worker_repo_access
    test_worker_pr_api_access
    test_reviewer_repo_access
    test_reviewer_pr_api_access

    print_section "Branch Protection Tests"
    test_branch_protection_active
    test_required_status_checks
    test_approval_required
    test_force_push_blocked
    test_deletion_blocked
    test_linear_history_required

    # Summary
    print_section "Summary"
    echo ""
    echo -e "  ${GREEN}Passed:${NC}  $PASS"
    echo -e "  ${RED}Failed:${NC}  $FAIL"
    echo -e "  ${YELLOW}Skipped:${NC} $SKIP"
    echo ""

    # Document expected restrictions
    echo -e "${BLUE}Expected Permission Matrix:${NC}"
    echo ""
    echo "  | Action              | Worker    | Reviewer    | Human |"
    echo "  |---------------------|-----------|-------------|-------|"
    echo "  | Create branches     | Yes       | No          | Yes   |"
    echo "  | Push to branches    | Yes       | No          | Yes   |"
    echo "  | Create PRs          | Yes       | No          | Yes   |"
    echo "  | Review PRs          | No        | Yes         | Yes   |"
    echo "  | Approve PRs         | No        | Yes         | Yes   |"
    echo "  | Merge PRs           | No        | No          | Yes   |"
    echo "  | Push to main        | No        | No          | No    |"
    echo ""
    echo "  Worker bot: $WORKER_BOT"
    echo "  Reviewer bot: $REVIEWER_BOT"
    echo ""

    if [ $FAIL -eq 0 ]; then
        echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}║${NC}  ${GREEN}PASS: All bot restrictions verified${NC}                      ${GREEN}║${NC}"
        echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
        exit 0
    else
        echo -e "${RED}╔════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${RED}║${NC}  ${RED}FAIL: Some restrictions not working - review above${NC}        ${RED}║${NC}"
        echo -e "${RED}╚════════════════════════════════════════════════════════════╝${NC}"
        exit 1
    fi
}

# Run main
main "$@"
