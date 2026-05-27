#!/bin/bash
#
# Claude Code PreToolUse Hook: GitHub Account Switcher
#
# Automatically switches to the correct GitHub account before PR creation
# and review operations. Prevents the wrong account from being attributed
# to automated work.
#
# Account model (configure these for your org):
#   - WORKER_ACCOUNT: Used for ticket work, commits, PRs
#   - REVIEWER_ACCOUNT: Used for PR reviews
#
# Configure via environment variables or edit the defaults below.
#

set -euo pipefail

WORKER_ACCOUNT="${AGILE_FLOW_WORKER_ACCOUNT:-va-worker}"
REVIEWER_ACCOUNT="${AGILE_FLOW_REVIEWER_ACCOUNT:-va-reviewer}"

# Read JSON input from stdin
input=$(cat)

# Extract tool name and command (for Bash tool)
tool_name=$(echo "$input" | jq -r '.tool_name // empty')
tool_command=$(echo "$input" | jq -r '.tool_input.command // empty')

# Determine required account based on tool
#
# Routing rules (narrow on purpose):
#   - `gh pr create`                     -> WORKER   (PR authorship)
#   - `gh pr review` / `gh pr comment`   -> REVIEWER (PR approval / review comments)
#   - all other gh commands              -> passthrough (no enforcement)
#
# Why so narrow: command patterns alone cannot reliably distinguish
# "issue created during work" (worker) from "issue created during review
# as a follow-up" (reviewer). The same applies to `gh project item-*`
# board moves. Slash commands that need a specific account (e.g. the
# reviewer when `/review-pr` files a follow-up ticket) are responsible
# for calling `gh auth switch --user <account>` explicitly before
# those operations. This hook only enforces the two cases where the
# command name itself is unambiguous about which account should own it.
required_account=""
case "$tool_name" in
  Bash)
    case "$tool_command" in
      *"gh pr create"*)
        required_account="$WORKER_ACCOUNT"
        ;;
      *"gh pr review"*|*"gh pr comment"*)
        required_account="$REVIEWER_ACCOUNT"
        ;;
      *)
        exit 0
        ;;
    esac
    ;;
  *)
    exit 0
    ;;
esac

# Get current active account
current_account=$(gh auth status 2>&1 | grep -B2 "Active account: true" | grep "Logged in to" | sed 's/.*account \([^ ]*\).*/\1/')

# Switch if needed
if [[ "$current_account" != "$required_account" ]]; then
  echo "Switching GitHub account from '$current_account' to '$required_account' for $tool_name" >&2

  if gh auth switch --user "$required_account" 2>&1; then
    echo "Successfully switched to $required_account" >&2
  else
    echo "ERROR: Failed to switch to $required_account account" >&2
    echo "Please ensure $required_account is authenticated: gh auth login --user $required_account" >&2
    exit 2
  fi
fi

exit 0
