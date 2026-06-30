#!/bin/bash
#
# Gemba Flow Doctor — Local Diagnostic Script
#
# Validates the full configuration needed for the workshop:
#   CLI tools, git config, GitHub auth, MCP config, Claude settings,
#   CLAUDE.md placeholders, bootstrap status, and docs.
#
# Usage:
#   bash scripts/doctor.sh          # standalone
#   /doctor                         # via Claude Code slash command (adds remote checks)
#
# Output format per check:
#   [PASS] Category: Description
#   [FAIL] Category: Description — fix instruction
#   [WARN] Category: Description — optional guidance
#   [SKIP] Category: Description — reason
#
# Ends with a machine-readable summary block for the slash command to parse.

set -uo pipefail

# Ensure bash even if invoked as `zsh scripts/doctor.sh`
if [ -z "$BASH_VERSION" ]; then
    exec bash "$0" "$@"
fi

# Dual-read shim for the agile-flow → Gemba Flow env-var rebrand.
# Prefers GEMBAFLOW_*, falls back to the deprecated AGILE_FLOW_*.
# See scripts/lib/env-compat.sh for the migration policy.
DOCTOR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/env-compat.sh
source "${DOCTOR_DIR}/lib/env-compat.sh"

# ───────────────────────────────────────────────────────────────────
#  Colors
# ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# ───────────────────────────────────────────────────────────────────
#  Counters
# ───────────────────────────────────────────────────────────────────
PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0
SKIP_COUNT=0
FAIL_DESCRIPTIONS=""
WARN_DESCRIPTIONS=""

# ───────────────────────────────────────────────────────────────────
#  Output helpers
# ───────────────────────────────────────────────────────────────────
pass() {
    echo -e "${GREEN}[PASS]${NC} $1: $2"
    PASS_COUNT=$((PASS_COUNT + 1))
}

fail() {
    echo -e "${RED}[FAIL]${NC} $1: $2 — $3"
    FAIL_COUNT=$((FAIL_COUNT + 1))
    if [ -n "$FAIL_DESCRIPTIONS" ]; then
        FAIL_DESCRIPTIONS="${FAIL_DESCRIPTIONS}|$2"
    else
        FAIL_DESCRIPTIONS="$2"
    fi
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1: $2 — $3"
    WARN_COUNT=$((WARN_COUNT + 1))
    if [ -n "$WARN_DESCRIPTIONS" ]; then
        WARN_DESCRIPTIONS="${WARN_DESCRIPTIONS}|$2"
    else
        WARN_DESCRIPTIONS="$2"
    fi
}

skip() {
    echo -e "${BLUE}[SKIP]${NC} $1: $2 — $3"
    SKIP_COUNT=$((SKIP_COUNT + 1))
}

section() {
    echo ""
    echo -e "${CYAN}━━━ $1 ━━━${NC}"
}

# ───────────────────────────────────────────────────────────────────
#  resolve_cmd — find a CLI tool even in restricted PATH environments
# ───────────────────────────────────────────────────────────────────
# Usage: resolve_cmd <name>
# Prints the resolved path on stdout.  Returns 0 if found, 1 if not.
resolve_cmd() {
    local cmd="$1"
    # Try PATH first
    local found
    found=$(command -v "$cmd" 2>/dev/null) && { echo "$found"; return 0; }
    # Probe well-known install locations
    local dir
    for dir in \
        /opt/homebrew/bin \
        /usr/local/bin \
        "$HOME/.local/bin" \
        "$HOME/.cargo/bin" \
        "$HOME/.claude/local"; do
        if [ -x "$dir/$cmd" ]; then
            echo "$dir/$cmd"
            return 0
        fi
    done
    return 1
}

# ───────────────────────────────────────────────────────────────────
#  Header
# ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║${NC}              ${BLUE}Gemba Flow Doctor${NC}                              ${CYAN}║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ───────────────────────────────────────────────────────────────────
#  Restricted PATH banner
# ───────────────────────────────────────────────────────────────────
if [[ ":$PATH:" != *":/opt/homebrew/bin:"* ]] && [[ ":$PATH:" != *":/usr/local/bin:"* ]]; then
    echo -e "${YELLOW}Note: Running with restricted PATH — using fallback path detection${NC}"
    echo ""
fi

# ═══════════════════════════════════════════════════════════════════
#  0. Framework Version
# ═══════════════════════════════════════════════════════════════════
section "Framework Version"

VERSION_MANIFEST=".gembaflow-version"

if [ -f "$VERSION_MANIFEST" ]; then
    if JQ_CMD=$(resolve_cmd jq); then
        local_version=$("$JQ_CMD" -r '.version' "$VERSION_MANIFEST" 2>/dev/null || echo "")
        if [ -n "$local_version" ]; then
            # Fetch latest release from GitHub
            latest_json=$(curl -s --max-time 5 https://api.github.com/repos/vibeacademy/gembaflow/releases/latest 2>/dev/null || echo "")
            if [ -n "$latest_json" ]; then
                latest_version=$(echo "$latest_json" | "$JQ_CMD" -r '.tag_name // empty' 2>/dev/null | sed 's/^v//')
                release_url=$(echo "$latest_json" | "$JQ_CMD" -r '.html_url // empty' 2>/dev/null)
                if [ -n "$latest_version" ]; then
                    if [ "$local_version" = "$latest_version" ]; then
                        pass "Framework Version" "Gemba Flow v${local_version} (up to date)"
                    else
                        warn "Framework Version" "Gemba Flow v${local_version} (update available: v${latest_version})" "${release_url}"
                    fi
                else
                    warn "Framework Version" "Gemba Flow v${local_version} (could not check for updates)" "GitHub API returned unexpected response"
                fi
            else
                warn "Framework Version" "Gemba Flow v${local_version} (could not check for updates)" "GitHub API unreachable"
            fi
        else
            warn "Framework Version" "Version manifest unreadable" "Check $VERSION_MANIFEST format"
        fi
    else
        skip "Framework Version" "Version check" "jq not installed"
    fi
else
    warn "Framework Version" "Version manifest not found" "Run bootstrap.sh to create .gembaflow-version"
fi

# ═══════════════════════════════════════════════════════════════════
#  0.5. Clone Freshness (vs origin)
# ═══════════════════════════════════════════════════════════════════
# Mirrors the early step in .claude/commands/doctor.md (#430): a stale clone
# is a silent failure mode that can produce obsolete plans and missing-file
# diagnostics whose root cause is "you needed to git pull an hour ago." This
# check surfaces the gap before anything else relies on the local state.
#
# Read-only by construction: git fetch --quiet and git rev-list --count only;
# no git pull, no git checkout. Never fails the doctor run — a stale clone is
# a signal, not a fatal error.
section "Clone Freshness"

if GIT_CMD=$(resolve_cmd git); then
    if "$GIT_CMD" rev-parse --git-dir >/dev/null 2>&1; then
        # Try to fetch quietly; capture failure for the SKIP branch (offline / auth).
        if "$GIT_CMD" fetch --quiet >/dev/null 2>&1; then
            current_branch=$("$GIT_CMD" symbolic-ref --short HEAD 2>/dev/null || echo "")
            if [ -n "$current_branch" ]; then
                # Count commits behind origin/<branch>. If the upstream tracking ref
                # doesn't exist (detached HEAD, branch not pushed), git rev-list returns
                # non-zero — capture as "?" so we SKIP cleanly rather than misreport.
                behind_count=$("$GIT_CMD" rev-list --count "HEAD..origin/$current_branch" 2>/dev/null || echo "?")
                if [ "$behind_count" = "0" ]; then
                    pass "Clone Freshness" "Local is current with origin/$current_branch"
                elif [ "$behind_count" != "?" ] && [ "$behind_count" -gt 0 ] 2>/dev/null; then
                    latest_subject=$("$GIT_CMD" log "HEAD..origin/$current_branch" --pretty=format:'%s' -1 2>/dev/null || echo "(could not read most-recent subject)")
                    warn "Clone Freshness" "Local is $behind_count commits behind origin/$current_branch" "Most recent upstream commit: \"$latest_subject\". Run \`git pull\` before any planning, architecture, or /upgrade work."
                else
                    skip "Clone Freshness" "Could not count commits behind origin" "Unusual git state — no upstream tracking ref for $current_branch"
                fi
            else
                skip "Clone Freshness" "Could not determine current branch" "Detached HEAD or unusual git state"
            fi
        else
            skip "Clone Freshness" "Could not fetch from origin" "Offline or auth issue — if you're online, check \`gh auth status\` and network"
        fi
    else
        skip "Clone Freshness" "Not in a git repository" "doctor.sh is being run outside a checkout"
    fi
else
    skip "Clone Freshness" "git not installed" "Install git to enable this check"
fi

# ═══════════════════════════════════════════════════════════════════
#  1. CLI Tools
# ═══════════════════════════════════════════════════════════════════
section "CLI Tools"

# git (FAIL)
if GIT_CMD=$(resolve_cmd git); then
    pass "CLI Tools" "git found ($("$GIT_CMD" --version | head -1))"
else
    fail "CLI Tools" "git not found" "Install from https://git-scm.com/downloads"
fi

# gh (FAIL)
if GH_CMD=$(resolve_cmd gh); then
    pass "CLI Tools" "gh found ($("$GH_CMD" --version | head -1))"
else
    fail "CLI Tools" "gh not found" "brew install gh  or  https://cli.github.com"
fi

# claude (FAIL)
if CLAUDE_CMD=$(resolve_cmd claude); then
    pass "CLI Tools" "claude found at $CLAUDE_CMD"
else
    if [[ "${CODESPACES:-}" == "true" ]] || [[ "${TERM_PROGRAM:-}" == "vscode" ]]; then
        pass "CLI Tools" "claude CLI (IDE-provided via Claude Code extension)"
    else
        fail "CLI Tools" "claude not found" "npm install -g @anthropic-ai/claude-code"
    fi
fi

# jq (FAIL)
if JQ_CMD=$(resolve_cmd jq); then
    pass "CLI Tools" "jq found"
else
    fail "CLI Tools" "jq not found" "brew install jq  or  https://jqlang.github.io/jq/download/"
fi

# npx (WARN)
if NPX_CMD=$(resolve_cmd npx); then
    pass "CLI Tools" "npx found"
else
    warn "CLI Tools" "npx not found" "Install Node.js from https://nodejs.org (needed for MCP servers)"
fi

# uv — WARN if pyproject.toml exists
if [ -f "pyproject.toml" ]; then
    if resolve_cmd uv &>/dev/null; then
        pass "CLI Tools" "uv found (Python project detected)"
    else
        warn "CLI Tools" "uv not found but pyproject.toml exists" "curl -LsSf https://astral.sh/uv/install.sh | sh"
    fi
fi

# node — WARN if package.json exists
if [ -f "package.json" ]; then
    if NODE_CMD=$(resolve_cmd node); then
        pass "CLI Tools" "node found ($("$NODE_CMD" --version))"
    else
        warn "CLI Tools" "node not found but package.json exists" "Install from https://nodejs.org"
    fi
fi

# ═══════════════════════════════════════════════════════════════════
#  2. Git Config
# ═══════════════════════════════════════════════════════════════════
section "Git Config"

# user.name (FAIL)
git_name=$(git config user.name 2>/dev/null || true)
if [ -n "$git_name" ]; then
    pass "Git Config" "user.name set: $git_name"
else
    fail "Git Config" "user.name not set" "git config --global user.name \"Your Name\""
fi

# user.email (FAIL)
git_email=$(git config user.email 2>/dev/null || true)
if [ -n "$git_email" ]; then
    pass "Git Config" "user.email set: $git_email"
else
    fail "Git Config" "user.email not set" "git config --global user.email \"you@example.com\""
fi

# core.hooksPath (WARN)
hooks_path=$(git config --local core.hooksPath 2>/dev/null || true)
if [ "$hooks_path" = "scripts/hooks" ]; then
    pass "Git Config" "core.hooksPath set to scripts/hooks"
else
    warn "Git Config" "core.hooksPath is '${hooks_path:-unset}' (expected scripts/hooks)" "git config --local core.hooksPath scripts/hooks"
fi

# pre-push exists + executable (WARN)
if [ -f "scripts/hooks/pre-push" ]; then
    if [ -x "scripts/hooks/pre-push" ]; then
        pass "Git Config" "pre-push hook exists and is executable"
    else
        warn "Git Config" "pre-push hook exists but is not executable" "chmod +x scripts/hooks/pre-push"
    fi
else
    warn "Git Config" "pre-push hook not found at scripts/hooks/pre-push" "The hook enforces lint+test before push"
fi

# remote origin (WARN)
remote_url=$(git remote get-url origin 2>/dev/null || true)
if [ -n "$remote_url" ]; then
    pass "Git Config" "remote origin set: $remote_url"
else
    warn "Git Config" "No remote origin configured" "git remote add origin <url>"
fi

# ═══════════════════════════════════════════════════════════════════
#  3. GitHub Auth
# ═══════════════════════════════════════════════════════════════════
section "GitHub Auth"

if ! GH_CMD=$(resolve_cmd gh); then
    skip "GitHub Auth" "All checks" "gh CLI not installed"
else

# Save current gh user for safe restore after switch tests
ORIGINAL_GH_USER=$("$GH_CMD" api user --jq '.login' 2>/dev/null || echo "")

# Human account (FAIL)
if "$GH_CMD" auth status &>/dev/null 2>&1; then
    current_user=$("$GH_CMD" api user --jq '.login' 2>/dev/null || echo "unknown")
    pass "GitHub Auth" "Human account authenticated: $current_user"
else
    fail "GitHub Auth" "Not authenticated with gh" "Run: gh auth login"
fi

# Worker account env var (WARN) — dual-read GEMBAFLOW_* / AGILE_FLOW_*
DOCTOR_WORKER_ACCOUNT="$(gf_env GEMBAFLOW_WORKER_ACCOUNT AGILE_FLOW_WORKER_ACCOUNT)"
DOCTOR_WORKER_SRC="$(gf_env_source_label GEMBAFLOW_WORKER_ACCOUNT AGILE_FLOW_WORKER_ACCOUNT)"
if [ -n "$DOCTOR_WORKER_ACCOUNT" ]; then
    pass "GitHub Auth" "Worker account env set (${DOCTOR_WORKER_SRC}): $DOCTOR_WORKER_ACCOUNT"

    # Test worker account is in keyring
    if "$GH_CMD" auth switch --user "$DOCTOR_WORKER_ACCOUNT" &>/dev/null 2>&1; then
        pass "GitHub Auth" "Worker account ($DOCTOR_WORKER_ACCOUNT) in gh keyring"
        # Restore original user
        if [ -n "$ORIGINAL_GH_USER" ]; then
            "$GH_CMD" auth switch --user "$ORIGINAL_GH_USER" &>/dev/null 2>&1 || true
        fi
    else
        warn "GitHub Auth" "Worker account ($DOCTOR_WORKER_ACCOUNT) not in gh keyring" "Run: gh auth login for this account"
    fi

    # Nudge users still on the deprecated name to migrate.
    if [ -z "${GEMBAFLOW_WORKER_ACCOUNT:-}" ] && [ -n "${AGILE_FLOW_WORKER_ACCOUNT:-}" ]; then
        warn "GitHub Auth" "AGILE_FLOW_WORKER_ACCOUNT is deprecated" "Rename to GEMBAFLOW_WORKER_ACCOUNT in your shell rc"
    fi
else
    warn "GitHub Auth" "GEMBAFLOW_WORKER_ACCOUNT not set" "export GEMBAFLOW_WORKER_ACCOUNT=\"{org}-worker\""
fi

# Reviewer account env var (WARN) — dual-read GEMBAFLOW_* / AGILE_FLOW_*
DOCTOR_REVIEWER_ACCOUNT="$(gf_env GEMBAFLOW_REVIEWER_ACCOUNT AGILE_FLOW_REVIEWER_ACCOUNT)"
DOCTOR_REVIEWER_SRC="$(gf_env_source_label GEMBAFLOW_REVIEWER_ACCOUNT AGILE_FLOW_REVIEWER_ACCOUNT)"
if [ -n "$DOCTOR_REVIEWER_ACCOUNT" ]; then
    pass "GitHub Auth" "Reviewer account env set (${DOCTOR_REVIEWER_SRC}): $DOCTOR_REVIEWER_ACCOUNT"

    # Test reviewer account is in keyring
    if "$GH_CMD" auth switch --user "$DOCTOR_REVIEWER_ACCOUNT" &>/dev/null 2>&1; then
        pass "GitHub Auth" "Reviewer account ($DOCTOR_REVIEWER_ACCOUNT) in gh keyring"
        # Restore original user
        if [ -n "$ORIGINAL_GH_USER" ]; then
            "$GH_CMD" auth switch --user "$ORIGINAL_GH_USER" &>/dev/null 2>&1 || true
        fi
    else
        warn "GitHub Auth" "Reviewer account ($DOCTOR_REVIEWER_ACCOUNT) not in gh keyring" "Run: gh auth login for this account"
    fi

    # Nudge users still on the deprecated name to migrate.
    if [ -z "${GEMBAFLOW_REVIEWER_ACCOUNT:-}" ] && [ -n "${AGILE_FLOW_REVIEWER_ACCOUNT:-}" ]; then
        warn "GitHub Auth" "AGILE_FLOW_REVIEWER_ACCOUNT is deprecated" "Rename to GEMBAFLOW_REVIEWER_ACCOUNT in your shell rc"
    fi
else
    warn "GitHub Auth" "GEMBAFLOW_REVIEWER_ACCOUNT not set" "export GEMBAFLOW_REVIEWER_ACCOUNT=\"{org}-reviewer\""
fi

# Final restore — ensure we always end on the original user
if [ -n "$ORIGINAL_GH_USER" ]; then
    "$GH_CMD" auth switch --user "$ORIGINAL_GH_USER" &>/dev/null 2>&1 || true
fi

fi  # end gh guard

# ═══════════════════════════════════════════════════════════════════
#  4. MCP Config
# ═══════════════════════════════════════════════════════════════════
section "MCP Config"

# .mcp.json exists (FAIL)
if [ -f ".mcp.json" ]; then
    pass "MCP Config" ".mcp.json exists"

    if ! JQ_CMD=$(resolve_cmd jq); then
        skip "MCP Config" "Content checks (memory server, npx path)" "jq not installed"
    else
        # memory server (WARN)
        if "$JQ_CMD" -e '.mcpServers.memory' .mcp.json &>/dev/null; then
            pass "MCP Config" "memory server configured"
        else
            warn "MCP Config" "memory server missing from .mcp.json" "Optional but recommended for agent context"
        fi

        # npx path resolves (WARN)
        mcp_npx_path=$("$JQ_CMD" -r '.mcpServers.memory.command // empty' .mcp.json 2>/dev/null)
        if [ -n "$mcp_npx_path" ]; then
            if resolve_cmd "$mcp_npx_path" &>/dev/null; then
                pass "MCP Config" "npx command in .mcp.json resolves: $mcp_npx_path"
                # Also check that node is available (npx shim needs it)
                if resolve_cmd node &>/dev/null; then
                    pass "MCP Config" "node available (required by npx)"
                else
                    warn "MCP Config" "npx found but node not resolvable" "npx requires node — install from https://nodejs.org"
                fi
            else
                warn "MCP Config" "npx path in .mcp.json does not resolve: $mcp_npx_path" "Update .mcp.json command path or install npx"
            fi
        fi
    fi  # end jq guard
else
    fail "MCP Config" ".mcp.json not found" "Run bootstrap.sh Phase 0 to create it"
fi

# GITHUB_PERSONAL_ACCESS_TOKEN (WARN — optional, only needed for direct GraphQL API calls)
if [ -n "${GITHUB_PERSONAL_ACCESS_TOKEN:-}" ]; then
    # Mask the token in output — guard against short tokens
    if [ ${#GITHUB_PERSONAL_ACCESS_TOKEN} -ge 12 ]; then
        token_preview="${GITHUB_PERSONAL_ACCESS_TOKEN:0:4}...${GITHUB_PERSONAL_ACCESS_TOKEN: -4}"
    else
        token_preview="(set, ${#GITHUB_PERSONAL_ACCESS_TOKEN} chars)"
    fi
    pass "MCP Config" "GITHUB_PERSONAL_ACCESS_TOKEN set ($token_preview)"
else
    skip "MCP Config" "GITHUB_PERSONAL_ACCESS_TOKEN not set" "Optional — gh auth handles GitHub access"
fi

# ═══════════════════════════════════════════════════════════════════
#  5. Claude Settings
# ═══════════════════════════════════════════════════════════════════
section "Claude Settings"

settings_file=".claude/settings.local.json"
if [ -f "$settings_file" ]; then
    pass "Claude Settings" "$settings_file exists"

    if JQ_CMD=$(resolve_cmd jq); then
        # merge-PR deny rule (WARN)
        if "$JQ_CMD" -e '.deny // [] | map(select(test("merge|Merge";"i"))) | length > 0' "$settings_file" &>/dev/null 2>&1; then
            pass "Claude Settings" "Merge-PR deny rule present"
        else
            warn "Claude Settings" "No merge-PR deny rule found" "Add a deny rule to prevent agents from merging PRs"
        fi

        # .env read deny rule (WARN)
        if "$JQ_CMD" -e '.deny // [] | map(select(test("\\.env|dotenv";"i"))) | length > 0' "$settings_file" &>/dev/null 2>&1; then
            pass "Claude Settings" ".env read deny rule present"
        else
            warn "Claude Settings" "No .env read deny rule found" "Add a deny rule to prevent agents from reading .env files"
        fi
    else
        skip "Claude Settings" "Deny rule checks" "jq not installed"
    fi
else
    if [ -f ".claude/settings.template.json" ]; then
        warn "Claude Settings" "$settings_file not found (template exists)" "cp .claude/settings.template.json $settings_file"
    else
        warn "Claude Settings" "$settings_file not found" "Create it with appropriate deny rules for agent safety"
    fi
fi

# ═══════════════════════════════════════════════════════════════════
#  6. CLAUDE.md
# ═══════════════════════════════════════════════════════════════════
section "CLAUDE.md"

if [ -f "CLAUDE.md" ]; then
    # Placeholder text check (WARN)
    if grep -q '\[Your project name\]' CLAUDE.md 2>/dev/null; then
        warn "CLAUDE.md" "Placeholder text found: [Your project name]" "Fill in project-specific details in CLAUDE.md"
    else
        pass "CLAUDE.md" "No placeholder text found"
    fi

    # Build commands populated (WARN)
    if grep -q '^\(uv run\|npm run\|yarn\|pnpm\|bun\|go \|make\|cargo\)' CLAUDE.md 2>/dev/null || \
       grep -q 'Dev server\|Lint\|Tests' CLAUDE.md 2>/dev/null; then
        pass "CLAUDE.md" "Build commands appear populated"
    else
        warn "CLAUDE.md" "Build commands may not be populated" "Fill in the Build & Test Commands section in CLAUDE.md"
    fi
else
    warn "CLAUDE.md" "CLAUDE.md not found" "This file is required for agent context"
fi

# ═══════════════════════════════════════════════════════════════════
#  7. Bootstrap Status
# ═══════════════════════════════════════════════════════════════════
section "Bootstrap Status"

STATUS_FILE=".claude/.bootstrap-status"
if [ -f "$STATUS_FILE" ]; then
    pass "Bootstrap" ".bootstrap-status file exists"

    for phase in phase0 phase1 phase2 phase3; do
        if grep -q "^${phase}:complete$" "$STATUS_FILE" 2>/dev/null; then
            pass "Bootstrap" "$phase complete"
        else
            warn "Bootstrap" "$phase not complete" "Run: bash bootstrap.sh and complete $phase"
        fi
    done
else
    warn "Bootstrap" ".bootstrap-status not found" "Run: bash bootstrap.sh to start the bootstrap wizard"
fi

# ═══════════════════════════════════════════════════════════════════
#  8. Docs
# ═══════════════════════════════════════════════════════════════════
section "Docs"

for doc in PRODUCT-REQUIREMENTS.md PRODUCT-ROADMAP.md TECHNICAL-ARCHITECTURE.md; do
    if [ -f "docs/$doc" ]; then
        pass "Docs" "docs/$doc exists"
    else
        warn "Docs" "docs/$doc not found" "Created during bootstrap Phase 1-2"
    fi
done

# ═══════════════════════════════════════════════════════════════════
#  9. Remote Checks (if gh CLI available and authenticated)
# ═══════════════════════════════════════════════════════════════════
section "Remote Checks"

if ! GH_CMD=$(resolve_cmd gh); then
    skip "Remote Checks" "All checks" "gh CLI not installed"
elif ! "$GH_CMD" auth status &>/dev/null 2>&1; then
    skip "Remote Checks" "All checks" "gh CLI not authenticated"
else
    # Extract owner/repo from git remote
    remote_url=$(git remote get-url origin 2>/dev/null || true)
    if [ -n "$remote_url" ]; then
        # Parse GitHub repo from URL (supports both HTTPS and SSH)
        if [[ "$remote_url" =~ github\.com[:/]([^/]+)/([^/]+)(\.git)?$ ]]; then
            owner="${BASH_REMATCH[1]}"
            repo="${BASH_REMATCH[2]}"
            repo="${repo%.git}"  # Remove .git suffix if present
            
            # Branch Protection Rulesets
            rulesets_response=$("$GH_CMD" api "repos/$owner/$repo/rulesets" 2>&1 || true)
            if echo "$rulesets_response" | grep -q "HTTP 403"; then
                warn "Remote Checks" "Branch protection rulesets" "Could not verify (token scope) — 403 Forbidden"
            elif echo "$rulesets_response" | grep -q "HTTP 404"; then
                warn "Remote Checks" "Branch protection rulesets" "Could not verify (resource not found) — 404 Not Found"
            elif [ "$rulesets_response" = "[]" ] || [ -z "$rulesets_response" ]; then
                warn "Remote Checks" "Branch protection rulesets" "No rulesets found — branch protection may not be configured"
            else
                # Check if any ruleset targets main branch (only if jq is available)
                if JQ_CMD=$(resolve_cmd jq); then
                    main_rulesets=$(echo "$rulesets_response" | "$JQ_CMD" -r '.[] | select(.target=="branch") | select(.conditions.ref_name.include[] | test("main|DEFAULT_BRANCH"))' 2>/dev/null || echo "")
                    if [ -n "$main_rulesets" ]; then
                        pass "Remote Checks" "Branch protection rulesets configured for main branch"
                    else
                        warn "Remote Checks" "Branch protection rulesets exist but may not protect main branch" "Verified — check ruleset configuration"
                    fi
                else
                    pass "Remote Checks" "Branch protection rulesets found (jq not available for detailed analysis)"
                fi
            fi
            
            # Repository Secrets
            secrets_response=$("$GH_CMD" secret list --repo "$owner/$repo" 2>&1 || true)
            if echo "$secrets_response" | grep -q "HTTP 403"; then
                warn "Remote Checks" "Repository secrets" "Could not verify (token scope) — 403 Forbidden"
            elif echo "$secrets_response" | grep -q "HTTP 404"; then
                warn "Remote Checks" "Repository secrets" "Could not verify (resource not found) — 404 Not Found"
            else
                # Check for common deployment secrets
                secrets_found=0
                for secret in RENDER_API_KEY RENDER_SERVICE_ID SUPABASE_ACCESS_TOKEN SUPABASE_PROJECT_REF; do
                    if echo "$secrets_response" | grep -q "^$secret"; then
                        secrets_found=$((secrets_found + 1))
                    fi
                done
                if [ "$secrets_found" -gt 0 ]; then
                    pass "Remote Checks" "Repository secrets configured ($secrets_found deployment secrets found)"
                else
                    warn "Remote Checks" "Repository secrets" "No deployment secrets found (RENDER_*, SUPABASE_*) — verified"
                fi
            fi
            
            # GitHub Project Board
            projects_response=$("$GH_CMD" project list --owner "$owner" --format json 2>&1 || true)
            if echo "$projects_response" | grep -q "HTTP 403"; then
                warn "Remote Checks" "GitHub project board" "Could not verify (token scope) — 403 Forbidden"
            elif echo "$projects_response" | grep -q "HTTP 404"; then
                warn "Remote Checks" "GitHub project board" "Could not verify (resource not found) — 404 Not Found"
            elif [ "$projects_response" = "[]" ] || [ -z "$projects_response" ]; then
                warn "Remote Checks" "GitHub project board" "No project boards found — verified"
            else
                # Count projects (only if jq is available)
                if JQ_CMD=$(resolve_cmd jq); then
                    project_count=$(echo "$projects_response" | "$JQ_CMD" -r 'length' 2>/dev/null || echo "0")
                    if [ "$project_count" -gt 0 ] 2>/dev/null; then
                        pass "Remote Checks" "GitHub project board configured ($project_count project(s) found)"
                    else
                        warn "Remote Checks" "GitHub project board" "Could not parse project list response"
                    fi
                else
                    pass "Remote Checks" "GitHub project board found (jq not available for detailed analysis)"
                fi
            fi
        else
            skip "Remote Checks" "All checks" "Could not parse GitHub repo from remote URL: $remote_url"
        fi
    else
        skip "Remote Checks" "All checks" "No git remote origin configured"
    fi
fi

# ═══════════════════════════════════════════════════════════════════
#  Summary
# ═══════════════════════════════════════════════════════════════════
echo ""
echo -e "${CYAN}━━━ Summary ━━━${NC}"
echo ""
echo -e "  ${GREEN}PASS${NC}: $PASS_COUNT    ${YELLOW}WARN${NC}: $WARN_COUNT    ${RED}FAIL${NC}: $FAIL_COUNT    ${BLUE}SKIP${NC}: $SKIP_COUNT"
echo ""

if [ "$FAIL_COUNT" -eq 0 ] && [ "$WARN_COUNT" -eq 0 ]; then
    echo -e "${GREEN}All checks passed. Ready for workshop!${NC}"
elif [ "$FAIL_COUNT" -eq 0 ]; then
    echo -e "${YELLOW}No failures, but $WARN_COUNT warning(s) to review.${NC}"
else
    echo -e "${RED}$FAIL_COUNT failure(s) must be fixed before the workshop.${NC}"
fi

echo ""

# Machine-readable summary for the /doctor slash command
echo "=== DOCTOR_SUMMARY ==="
echo "PASS: $PASS_COUNT  WARN: $WARN_COUNT  FAIL: $FAIL_COUNT  SKIP: $SKIP_COUNT"
echo "FAILS: $FAIL_DESCRIPTIONS"
echo "WARNS: $WARN_DESCRIPTIONS"
echo "=== END_SUMMARY ==="
