#!/bin/bash
#
# Gemba Flow Account Setup
#
# Streamlined setup for the three-account GitHub configuration.
# Paste your PATs → done. No interactive gh prompts.
#
# Usage:
#   bash scripts/setup-accounts.sh
#
# Prerequisites:
#   - gh CLI installed
#   - Personal GitHub account already logged in via `gh auth login`
#   - Worker and reviewer PATs ready to paste

set -uo pipefail

# Ensure bash even if invoked as `zsh scripts/setup-accounts.sh`
if [ -z "$BASH_VERSION" ]; then
    exec bash "$0" "$@"
fi

# Dual-read shim for the agile-flow → Gemba Flow env-var rebrand.
# Prefers GEMBAFLOW_*, falls back to the deprecated AGILE_FLOW_*.
# See scripts/lib/env-compat.sh for the migration policy.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/env-compat.sh
source "${SCRIPT_DIR}/lib/env-compat.sh"

# Resolved values from the dual-read shim. Captured once at script start
# so the deprecation warning (if any) fires at most once per invocation.
SETUP_WORKER_ACCOUNT="$(gf_env GEMBAFLOW_WORKER_ACCOUNT AGILE_FLOW_WORKER_ACCOUNT)"
SETUP_REVIEWER_ACCOUNT="$(gf_env GEMBAFLOW_REVIEWER_ACCOUNT AGILE_FLOW_REVIEWER_ACCOUNT)"

# ───────────────────────────────────────────────────────────────────
#  Colors (from doctor.sh)
# ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# ───────────────────────────────────────────────────────────────────
#  Print helpers (from bootstrap.sh)
# ───────────────────────────────────────────────────────────────────
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}! $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${BLUE}→ $1${NC}"
}

# ───────────────────────────────────────────────────────────────────
#  Detect the user's shell profile file (~/.zshrc, ~/.bashrc, etc.)
#  (from bootstrap.sh)
# ───────────────────────────────────────────────────────────────────
detect_shell_profile() {
    if [ -n "${ZSH_VERSION:-}" ] || [ "$SHELL" = "/bin/zsh" ] || [ "$SHELL" = "/usr/bin/zsh" ]; then
        echo "$HOME/.zshrc"
    elif [ -n "${BASH_VERSION:-}" ] || [ "$SHELL" = "/bin/bash" ] || [ "$SHELL" = "/usr/bin/bash" ]; then
        if [ -f "$HOME/.bash_profile" ]; then
            echo "$HOME/.bash_profile"
        else
            echo "$HOME/.bashrc"
        fi
    else
        # Fallback: try zshrc, then bashrc
        if [ -f "$HOME/.zshrc" ]; then
            echo "$HOME/.zshrc"
        elif [ -f "$HOME/.bashrc" ]; then
            echo "$HOME/.bashrc"
        else
            echo "$HOME/.profile"
        fi
    fi
}

# ───────────────────────────────────────────────────────────────────
#  Persist an environment variable to the user's shell profile
#  (idempotent, from bootstrap.sh)
# ───────────────────────────────────────────────────────────────────
persist_env_var() {
    local var_name=$1
    local var_value=$2
    local profile
    profile=$(detect_shell_profile)

    # Export in the current session immediately
    export "$var_name=$var_value"

    # Check whether the export line already exists in the profile
    if grep -q "^export ${var_name}=" "$profile" 2>/dev/null; then
        # Update the existing line in-place
        if [[ "$OSTYPE" == darwin* ]]; then
            sed -i '' "s|^export ${var_name}=.*|export ${var_name}=\"${var_value}\"|" "$profile"
        else
            sed -i "s|^export ${var_name}=.*|export ${var_name}=\"${var_value}\"|" "$profile"
        fi
        print_info "Updated ${var_name} in ${profile}"
    else
        {
            echo ""
            echo "# Added by Gemba Flow setup-accounts"
            echo "export ${var_name}=\"${var_value}\""
        } >> "$profile"
        print_info "Added ${var_name} to ${profile}"
    fi
}

# ───────────────────────────────────────────────────────────────────
#  Track personal account for restore-on-exit
# ───────────────────────────────────────────────────────────────────
PERSONAL_USER=""

restore_personal() {
    if [ -n "$PERSONAL_USER" ]; then
        gh auth switch --user "$PERSONAL_USER" &>/dev/null 2>&1 || true
    fi
}

trap restore_personal EXIT

# ═══════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════

echo ""
echo -e "${CYAN}━━━ Gemba Flow Account Setup ━━━${NC}"
echo ""

# ───────────────────────────────────────────────────────────────────
#  Preflight: gh must be installed
# ───────────────────────────────────────────────────────────────────
if ! command -v gh &>/dev/null; then
    print_error "gh CLI is not installed."
    echo "  Install it from https://cli.github.com and re-run this script."
    exit 1
fi

# ───────────────────────────────────────────────────────────────────
#  Step 1/4: Personal account
# ───────────────────────────────────────────────────────────────────
echo -e "${CYAN}--- Step 1/4: Personal account ---${NC}"
echo ""

if gh auth status &>/dev/null 2>&1; then
    PERSONAL_USER=$(gh api user --jq '.login' 2>/dev/null || echo "unknown")
    print_success "Logged in as: ${PERSONAL_USER}"
else
    print_error "Not logged in to GitHub."
    echo "  Run 'gh auth login' first to authenticate your personal account,"
    echo "  then re-run this script."
    exit 1
fi

echo ""

# ───────────────────────────────────────────────────────────────────
#  Step 2/4: Worker bot account
# ───────────────────────────────────────────────────────────────────
echo -e "${CYAN}--- Step 2/4: Worker bot account ---${NC}"
echo ""

# Get org prefix
read -p "  Enter your org prefix (the part before -worker): " org_prefix
if [ -z "$org_prefix" ]; then
    print_error "Org prefix cannot be empty."
    exit 1
fi

worker_account="${org_prefix}-worker"
reviewer_account="${org_prefix}-reviewer"

# Check if worker already configured and matches
if [ -n "${SETUP_WORKER_ACCOUNT:-}" ] && [ "$SETUP_WORKER_ACCOUNT" = "$worker_account" ]; then
    # Verify it's actually in the keyring
    if gh auth switch --user "$worker_account" &>/dev/null 2>&1; then
        print_success "Worker account already configured: ${worker_account}"
        # Switch back to personal
        gh auth switch --user "$PERSONAL_USER" &>/dev/null 2>&1 || true
    else
        print_warning "Worker env var set but account not in keyring. Will re-authenticate."
        SETUP_WORKER_ACCOUNT=""
    fi
fi

if [ -z "${SETUP_WORKER_ACCOUNT:-}" ] || [ "${SETUP_WORKER_ACCOUNT:-}" != "$worker_account" ]; then
    echo ""
    echo "  Worker account: ${worker_account}"
    echo ""
    echo "  Required PAT scopes (classic): repo, workflow, project, gist, read:org"
    echo ""
    read -s -p "  Paste your WORKER PAT: " worker_pat
    echo ""

    if [ -z "$worker_pat" ]; then
        print_error "PAT cannot be empty."
        exit 1
    fi

    # Authenticate with the PAT
    print_info "Authenticating ${worker_account}..."
    if echo "$worker_pat" | gh auth login --with-token 2>/dev/null; then
        # Verify the username matches
        actual_user=$(gh api user --jq '.login' 2>/dev/null || echo "")
        if [ -z "$actual_user" ]; then
            print_error "Could not verify worker account. The PAT may be invalid."
            # Restore personal account before exiting
            gh auth switch --user "$PERSONAL_USER" &>/dev/null 2>&1 || true
            exit 1
        fi

        if [ "$actual_user" != "$worker_account" ]; then
            print_warning "Expected ${worker_account} but PAT belongs to ${actual_user}"
            print_info "Using ${actual_user} as worker account."
            worker_account="$actual_user"
        fi

        print_success "Authenticated as: ${worker_account}"

        # Check project scope
        print_info "Checking PAT scopes for ${worker_account}..."
        if gh project list --limit 1 &>/dev/null 2>&1; then
            print_success "Worker PAT has 'project' scope."
        else
            print_warning "Worker PAT may be missing the 'project' scope."
            echo "  Board operations require the 'project' scope on a classic PAT,"
            echo "  or the 'Projects' permission on a fine-grained PAT."
        fi

        # Restore personal before persisting env var
        gh auth switch --user "$PERSONAL_USER" &>/dev/null 2>&1 || true

        persist_env_var "GEMBAFLOW_WORKER_ACCOUNT" "$worker_account"
        SETUP_WORKER_ACCOUNT="$worker_account"
    else
        print_error "Worker account login failed. Check your PAT and try again."
        exit 1
    fi
fi

echo ""

# ───────────────────────────────────────────────────────────────────
#  Step 3/4: Reviewer bot account
# ───────────────────────────────────────────────────────────────────
echo -e "${CYAN}--- Step 3/4: Reviewer bot account ---${NC}"
echo ""

# Check if reviewer already configured and matches
if [ -n "${SETUP_REVIEWER_ACCOUNT:-}" ] && [ "$SETUP_REVIEWER_ACCOUNT" = "$reviewer_account" ]; then
    if gh auth switch --user "$reviewer_account" &>/dev/null 2>&1; then
        print_success "Reviewer account already configured: ${reviewer_account}"
        gh auth switch --user "$PERSONAL_USER" &>/dev/null 2>&1 || true
    else
        print_warning "Reviewer env var set but account not in keyring. Will re-authenticate."
        SETUP_REVIEWER_ACCOUNT=""
    fi
fi

if [ -z "${SETUP_REVIEWER_ACCOUNT:-}" ] || [ "${SETUP_REVIEWER_ACCOUNT:-}" != "$reviewer_account" ]; then
    echo ""
    echo "  Reviewer account: ${reviewer_account}"
    echo ""
    echo "  Required PAT scopes (classic): repo, workflow, project, gist, read:org"
    echo "  NOTE: 'project' scope is required so the reviewer can file"
    echo "        follow-up issues onto the project board after /review-pr."
    echo "        If you have an existing PAT without 'project', upgrade with:"
    echo "          gh auth refresh --user ${reviewer_account} \\"
    echo "            --scopes repo,workflow,project,gist,read:org"
    echo ""
    read -s -p "  Paste your REVIEWER PAT: " reviewer_pat
    echo ""

    if [ -z "$reviewer_pat" ]; then
        print_error "PAT cannot be empty."
        exit 1
    fi

    # Authenticate with the PAT
    print_info "Authenticating ${reviewer_account}..."
    if echo "$reviewer_pat" | gh auth login --with-token 2>/dev/null; then
        actual_user=$(gh api user --jq '.login' 2>/dev/null || echo "")
        if [ -z "$actual_user" ]; then
            print_error "Could not verify reviewer account. The PAT may be invalid."
            gh auth switch --user "$PERSONAL_USER" &>/dev/null 2>&1 || true
            exit 1
        fi

        if [ "$actual_user" != "$reviewer_account" ]; then
            print_warning "Expected ${reviewer_account} but PAT belongs to ${actual_user}"
            print_info "Using ${actual_user} as reviewer account."
            reviewer_account="$actual_user"
        fi

        print_success "Authenticated as: ${reviewer_account}"

        # Check project scope
        print_info "Checking PAT scopes for ${reviewer_account}..."
        if gh project list --limit 1 &>/dev/null 2>&1; then
            print_success "Reviewer PAT has 'project' scope."
        else
            print_warning "Reviewer PAT may be missing the 'project' scope."
            echo "  Board operations require the 'project' scope on a classic PAT,"
            echo "  or the 'Projects' permission on a fine-grained PAT."
        fi

        # Restore personal before persisting env var
        gh auth switch --user "$PERSONAL_USER" &>/dev/null 2>&1 || true

        persist_env_var "GEMBAFLOW_REVIEWER_ACCOUNT" "$reviewer_account"
        SETUP_REVIEWER_ACCOUNT="$reviewer_account"
    else
        print_error "Reviewer account login failed. Check your PAT and try again."
        exit 1
    fi
fi

echo ""

# ───────────────────────────────────────────────────────────────────
#  Step 4/4: Restore & verify
# ───────────────────────────────────────────────────────────────────
echo -e "${CYAN}--- Step 4/4: Restore & verify ---${NC}"
echo ""

# Restore personal account (trap also does this, but be explicit)
gh auth switch --user "$PERSONAL_USER" &>/dev/null 2>&1 || true

# Build summary
worker_display="${SETUP_WORKER_ACCOUNT:-$worker_account}"
reviewer_display="${SETUP_REVIEWER_ACCOUNT:-$reviewer_account}"

# Check keyring status for each bot
worker_status="in keyring"
if ! gh auth switch --user "$worker_display" &>/dev/null 2>&1; then
    worker_status="NOT in keyring"
fi
gh auth switch --user "$PERSONAL_USER" &>/dev/null 2>&1 || true

reviewer_status="in keyring"
if ! gh auth switch --user "$reviewer_display" &>/dev/null 2>&1; then
    reviewer_status="NOT in keyring"
fi
gh auth switch --user "$PERSONAL_USER" &>/dev/null 2>&1 || true

echo "  Account Summary:"
echo ""
echo "    Personal:   ${PERSONAL_USER} (active)"
echo "    Worker:     ${worker_display} (${worker_status})"
echo "    Reviewer:   ${reviewer_display} (${reviewer_status})"
echo ""

profile=$(detect_shell_profile)
print_success "Account setup complete."
echo ""
print_info "Run 'source ${profile}' then 'bash scripts/doctor.sh' to verify."
echo ""
