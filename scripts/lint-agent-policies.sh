#!/bin/bash
# Agent Policy Linter
# Runs in CI to prevent instruction drift and maintain safety protocols
#
# Purpose: Detect prohibited instructions that could violate safety controls:
# - Merge instructions in pr-reviewer
# - Push to main instructions in github-ticket-worker
# - Move to Done instructions without human context
# - Missing NON-NEGOTIABLE PROTOCOL blocks
#
# Usage:
#   ./scripts/lint-agent-policies.sh [--verbose]
#
# Exit codes:
#   0 = All checks passed (may have warnings)
#   1 = One or more errors found

set -e

ERRORS=0
WARNINGS=0
VERBOSE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --verbose)
      VERBOSE=true
      shift
      ;;
    --help)
      sed -n '2,16p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

# Color codes for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

verbose_log() {
  if [ "$VERBOSE" = true ]; then
    echo "  $1"
  fi
}

echo "=== Agent Policy Linter ==="
echo ""

# =============================================================================
# Check 1: Prohibited merge instructions in PR reviewer files
# =============================================================================

echo "Checking pr-reviewer files for prohibited terms..."
PROHIBITED_FOUND=0

# Check for "and merge" phrase which violates the protocol
# Exclude cases where it says "human...and merge" or "approval and merge" or is in a "cannot" context
if [ -f ".claude/agents/pr-reviewer.md" ]; then
  if grep -n "and merge" .claude/agents/pr-reviewer.md 2>/dev/null | grep -v "human.*and merge\|approval and merge\|review and merge\|cannot.*and merge\|NEVER.*and merge"; then
    echo -e "${RED}ERROR: Found 'and merge' instruction in pr-reviewer.md${NC}"
    ERRORS=$((ERRORS + 1))
    PROHIBITED_FOUND=1
  fi
fi

# Check for "move to Done" in pr-reviewer files (without negation)
if [ -f ".claude/agents/pr-reviewer.md" ]; then
  if grep -n "move to Done\|Move to Done" .claude/agents/pr-reviewer.md 2>/dev/null | grep -v "NEVER\|NOT\|cannot\|don't\|do not\|human does"; then
    echo -e "${RED}ERROR: Found 'move to Done' instruction in pr-reviewer.md (without negation)${NC}"
    ERRORS=$((ERRORS + 1))
    PROHIBITED_FOUND=1
  fi
fi

# Check for "close the issue" in pr-reviewer files (without negation)
if [ -f ".claude/agents/pr-reviewer.md" ]; then
  if grep -n "close the issue\|close.*issue" .claude/agents/pr-reviewer.md 2>/dev/null | grep -v "NEVER\|NOT\|cannot\|don't\|do not"; then
    echo -e "${RED}ERROR: Found 'close the issue' instruction in pr-reviewer.md (without negation)${NC}"
    ERRORS=$((ERRORS + 1))
    PROHIBITED_FOUND=1
  fi
fi

if [ $PROHIBITED_FOUND -eq 0 ]; then
  echo -e "${GREEN}No prohibited merge/done/close instructions found in PR reviewer files${NC}"
fi

echo ""

# =============================================================================
# Check 2: Prohibited instructions in github-ticket-worker files
# =============================================================================

echo "Checking github-ticket-worker files for prohibited terms..."
WORKER_PROHIBITED=0

if [ -f ".claude/agents/github-ticket-worker.md" ]; then
  # Check for "merge" (as an action the agent takes)
  # Exclude: negations, "human will merge", "after merge", "asked to merge", "to merge"
  if grep -n "\bmerge\b" .claude/agents/github-ticket-worker.md 2>/dev/null | grep -v "NEVER\|NOT\|cannot\|don't\|do not\|after merge\|human.*merge\|for merge\|to merge\|asked to merge\|will merge\|does.*merge\|performs.*merge\|only human"; then
    verbose_log "Note: 'merge' found but may be in allowed context"
  fi

  # Check for "push to main" (without negation)
  if grep -n "push to main\|Push to main" .claude/agents/github-ticket-worker.md 2>/dev/null | grep -v "NEVER\|NOT\|cannot\|don't\|do not\|asked to.*push to main"; then
    echo -e "${RED}ERROR: Found 'push to main' instruction in worker files (without negation)${NC}"
    ERRORS=$((ERRORS + 1))
    WORKER_PROHIBITED=1
  fi

  # Check for "move to Done" (without negation)
  if grep -n "move to Done\|Move to Done\|moves.*Done" .claude/agents/github-ticket-worker.md 2>/dev/null | grep -v "NEVER\|NOT\|cannot\|don't\|do not\|asked to.*move to Done\|human.*move\|human does"; then
    echo -e "${RED}ERROR: Found 'move to Done' instruction in worker files (without negation)${NC}"
    ERRORS=$((ERRORS + 1))
    WORKER_PROHIBITED=1
  fi
fi

if [ $WORKER_PROHIBITED -eq 0 ]; then
  echo -e "${GREEN}No prohibited merge/main/done instructions found in worker files${NC}"
fi

echo ""

# =============================================================================
# Check 3: NON-NEGOTIABLE PROTOCOL blocks in workflow-critical agents
# =============================================================================

echo "Checking for NON-NEGOTIABLE PROTOCOL blocks in workflow agents..."
MISSING_PROTOCOL=0

# Only check agents that are part of the critical workflow
CRITICAL_AGENTS=("pr-reviewer" "github-ticket-worker")

for agent in "${CRITICAL_AGENTS[@]}"; do
  file=".claude/agents/${agent}.md"
  if [ -f "$file" ]; then
    if ! grep -q "NON-NEGOTIABLE PROTOCOL" "$file"; then
      echo -e "${RED}ERROR: Missing NON-NEGOTIABLE PROTOCOL in $file${NC}"
      ERRORS=$((ERRORS + 1))
      MISSING_PROTOCOL=1
    else
      verbose_log "Found NON-NEGOTIABLE PROTOCOL in $agent"
    fi
  else
    verbose_log "$file not found (may not be configured yet)"
  fi
done

if [ $MISSING_PROTOCOL -eq 0 ]; then
  echo -e "${GREEN}All workflow-critical agent files contain NON-NEGOTIABLE PROTOCOL block${NC}"
fi

echo ""

# =============================================================================
# Check 4: Required "NEVER merge" statements
# =============================================================================

echo "Checking for 'NEVER merge' statements..."
MISSING_NEVER_MERGE=0

for file in .claude/agents/pr-reviewer.md .claude/agents/github-ticket-worker.md; do
  if [ -f "$file" ]; then
    if ! grep -qi "NEVER merge\|NEVER.*merge" "$file"; then
      echo -e "${RED}ERROR: Missing 'NEVER merge' statement in $file${NC}"
      ERRORS=$((ERRORS + 1))
      MISSING_NEVER_MERGE=1
    else
      verbose_log "Found 'NEVER merge' in $(basename "$file")"
    fi
  fi
done

if [ $MISSING_NEVER_MERGE -eq 0 ]; then
  echo -e "${GREEN}Required 'NEVER merge' statements found in workflow agent files${NC}"
fi

echo ""

# =============================================================================
# Check 5: Human context in approval workflow
# =============================================================================

echo "Checking for 'human' in context of final approval..."
MISSING_HUMAN_CONTEXT=0

for file in .claude/agents/pr-reviewer.md .claude/agents/github-ticket-worker.md; do
  if [ -f "$file" ]; then
    # Check if file mentions merge/approval but doesn't mention human
    if grep -q "merge\|approval\|Merge\|Approval" "$file" && ! grep -qi "human" "$file"; then
      echo -e "${YELLOW}WARNING: File $(basename "$file") mentions merge/approval but may lack 'human' context${NC}"
      WARNINGS=$((WARNINGS + 1))
      MISSING_HUMAN_CONTEXT=1
    fi
  fi
done

if [ $MISSING_HUMAN_CONTEXT -eq 0 ]; then
  echo -e "${GREEN}All workflow agent files with merge/approval context mention 'human' reviewer${NC}"
fi

echo ""

# =============================================================================
# Check 6: Bot account identity instructions
# =============================================================================

echo "Checking for bot account identity instructions..."
MISSING_IDENTITY=0

for file in .claude/agents/pr-reviewer.md .claude/agents/github-ticket-worker.md; do
  if [ -f "$file" ]; then
    if ! grep -qi "gh auth switch\|GitHub Account Identity\|bot.*account" "$file"; then
      echo -e "${YELLOW}WARNING: $file may be missing bot account identity instructions${NC}"
      WARNINGS=$((WARNINGS + 1))
      MISSING_IDENTITY=1
    else
      verbose_log "Found bot account instructions in $(basename "$file")"
    fi
  fi
done

if [ $MISSING_IDENTITY -eq 0 ]; then
  echo -e "${GREEN}Bot account identity instructions found in workflow agent files${NC}"
fi

echo ""

# =============================================================================
# Check 7: Three-stage workflow consistency
# =============================================================================

echo "Checking for three-stage workflow consistency..."
WORKFLOW_INCONSISTENT=0

for file in .claude/agents/pr-reviewer.md .claude/agents/github-ticket-worker.md; do
  if [ -f "$file" ]; then
    if grep -q "THREE-STAGE WORKFLOW\|three.*stage" "$file"; then
      # Check if all three roles are mentioned
      if ! grep -qi "worker\|ticket.*worker\|github-ticket" "$file" || \
         ! grep -qi "reviewer\|pr-reviewer" "$file" || \
         ! grep -qi "human" "$file"; then
        echo -e "${YELLOW}WARNING: THREE-STAGE WORKFLOW in $(basename "$file") may be incomplete${NC}"
        WARNINGS=$((WARNINGS + 1))
        WORKFLOW_INCONSISTENT=1
      fi
    fi
  fi
done

if [ $WORKFLOW_INCONSISTENT -eq 0 ]; then
  echo -e "${GREEN}Three-stage workflow descriptions are consistent${NC}"
fi

echo ""

# =============================================================================
# Summary
# =============================================================================

echo "=== Lint Summary ==="
echo -e "Errors: ${RED}$ERRORS${NC}"
echo -e "Warnings: ${YELLOW}$WARNINGS${NC}"
echo ""

if [ $ERRORS -gt 0 ]; then
  echo -e "${RED}FAILED: $ERRORS error(s) found${NC}"
  echo ""
  echo "Agent policies contain instructions that violate safety protocols."
  echo "Please review and fix the issues listed above."
  echo ""
  echo "Common fixes:"
  echo "  - Add NON-NEGOTIABLE PROTOCOL blocks to workflow agents"
  echo "  - Add 'NEVER merge' statements to pr-reviewer and github-ticket-worker"
  echo "  - Ensure prohibited actions are negated (NEVER, cannot, do not)"
  exit 1
fi

if [ $WARNINGS -gt 0 ]; then
  echo -e "${YELLOW}PASSED with warnings: $WARNINGS warning(s) found${NC}"
  echo ""
  echo "Agent policies pass all critical checks but have some warnings."
  echo "Consider addressing the warnings to maintain consistency."
else
  echo -e "${GREEN}PASSED: All agent policies conform to safety standards${NC}"
  echo ""
  echo "No errors or warnings found. Agent policies are compliant."
fi

exit 0
