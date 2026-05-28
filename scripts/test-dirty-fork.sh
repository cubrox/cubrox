#!/bin/bash
#
# test-dirty-fork.sh — Simulate various fork states for upgrade testing
#
# Creates realistic "dirty" states that a user might have before running
# /upgrade, without going through the full bootstrap process.
#
# Usage:
#   bash scripts/test-dirty-fork.sh <scenario>
#
# Scenarios:
#   post-bootstrap-product  — User completed /bootstrap-product (has PRODUCT-*.md)
#   post-bootstrap-full     — User completed full bootstrap (product + architecture + workflow)
#   modified-agents         — User has customized agent definitions
#   modified-commands       — User has customized command files
#   has-overrides           — User has .gembaflow-overrides configured
#   uncommitted-framework   — User has uncommitted changes in framework files
#   uncommitted-userland    — User has uncommitted changes in user content only
#   mid-feature             — User is mid-feature branch with changes
#   stale-version           — User is on an old upstream version
#   mixed-mess              — Combination of multiple scenarios (stress test)
#   clean                   — Reset to clean state
#   list                    — Show all scenarios
#
# Exit codes:
#   0 — scenario applied successfully
#   1 — error or unknown scenario

set -euo pipefail

SCENARIO="${1:-list}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Ensure we're in a git repo
ensure_git_repo() {
  if [ ! -d ".git" ]; then
    log_error "Not in a git repository. Run from repo root."
    exit 1
  fi
}

# Safety warning for destructive scenarios
warn_will_modify() {
  log_warn "⚠️  This will modify your working tree!"
  log_warn "Run in a TEST FORK, not your main development repo."
  log_warn "Press Ctrl+C within 3 seconds to abort..."
  sleep 3
}

# Scenario: post-bootstrap-product
# Simulates user who ran /bootstrap-product
scenario_post_bootstrap_product() {
  log_info "Applying scenario: post-bootstrap-product"
  
  mkdir -p docs
  
  cat > docs/PRODUCT-DEFINITION.md << 'EOF'
# Product Definition

## Vision
A SaaS platform for small business inventory management.

## Target Users
- Small retail store owners
- E-commerce sellers managing physical inventory
- Warehouse managers at SMBs

## Core Problem
Manual inventory tracking leads to stockouts, overstocking, and lost sales.

## Key Features
1. Real-time inventory tracking
2. Low stock alerts
3. Multi-location support
4. Barcode scanning
5. Sales integration

## Success Metrics
- Reduce stockouts by 50%
- Save 5 hours/week on inventory tasks
- 95% inventory accuracy

## MVP Scope
- Single location inventory tracking
- Manual entry + barcode scan
- Low stock email alerts
- Basic reporting dashboard
EOF

  cat > docs/PRODUCT-ROADMAP.md << 'EOF'
# Product Roadmap

## Phase 1: MVP (Weeks 1-4)
- [ ] User authentication
- [ ] Product catalog CRUD
- [ ] Inventory count management
- [ ] Low stock alerts
- [ ] Basic dashboard

## Phase 2: Growth (Weeks 5-8)
- [ ] Barcode scanning
- [ ] Bulk import/export
- [ ] Multi-user support
- [ ] Advanced reporting

## Phase 3: Scale (Weeks 9-12)
- [ ] Multi-location
- [ ] API integrations
- [ ] Mobile app
- [ ] Forecasting
EOF

  git add docs/PRODUCT-*.md 2>/dev/null || true
  log_info "Created PRODUCT-DEFINITION.md and PRODUCT-ROADMAP.md"
}

# Scenario: post-bootstrap-full
# Simulates user who completed full bootstrap
scenario_post_bootstrap_full() {
  log_info "Applying scenario: post-bootstrap-full"
  
  # First apply product bootstrap
  scenario_post_bootstrap_product
  
  # Add architecture artifacts
  cat > docs/ARCHITECTURE.md << 'EOF'
# System Architecture

## Tech Stack
- Frontend: Next.js 14 + TypeScript
- Backend: Next.js API Routes
- Database: Supabase (PostgreSQL)
- Auth: Supabase Auth
- Hosting: Vercel

## Data Model
- users (id, email, name, created_at)
- products (id, user_id, name, sku, description)
- inventory (id, product_id, quantity, location)
- alerts (id, user_id, product_id, threshold, enabled)

## API Structure
- /api/auth/* - Authentication endpoints
- /api/products/* - Product CRUD
- /api/inventory/* - Inventory management
- /api/alerts/* - Alert configuration
EOF

  # Add some initial tickets (simulating workflow bootstrap)
  mkdir -p .github/ISSUE_TEMPLATE
  
  git add docs/ARCHITECTURE.md .github/ 2>/dev/null || true
  log_info "Created architecture docs and workflow artifacts"
}

# Scenario: modified-agents
# Simulates user who customized agent definitions
scenario_modified_agents() {
  log_info "Applying scenario: modified-agents"
  
  if [ -f ".claude/agents/github-ticket-worker.md" ]; then
    # Add custom section to worker
    {
      echo ""
      echo "## Custom Team Guidelines"
      echo ""
      echo "- Always use TypeScript strict mode"
      echo "- Prefer functional components over class components"
      echo "- Use Tailwind CSS for styling"
      echo "- All API routes must have Zod validation"
    } >> .claude/agents/github-ticket-worker.md
    
    git add .claude/agents/github-ticket-worker.md 2>/dev/null || true
    log_info "Modified github-ticket-worker.md with custom guidelines"
  else
    log_warn "Agent file not found, skipping"
  fi
}

# Scenario: modified-commands
# Simulates user who customized command files
scenario_modified_commands() {
  log_info "Applying scenario: modified-commands"
  
  if [ -f ".claude/commands/work-ticket.md" ]; then
    # Add custom section
    {
      echo ""
      echo "## Team-Specific Workflow"
      echo ""
      echo "Before starting work:"
      echo "1. Check #dev-standup Slack for blockers"
      echo "2. Verify Figma designs are approved"
      echo "3. Update ticket status in Linear"
    } >> .claude/commands/work-ticket.md
    
    git add .claude/commands/work-ticket.md 2>/dev/null || true
    log_info "Modified work-ticket.md with custom workflow"
  else
    log_warn "Command file not found, skipping"
  fi
}

# Scenario: has-overrides
# Simulates user who configured overrides
scenario_has_overrides() {
  log_info "Applying scenario: has-overrides"
  
  cat > .gembaflow-overrides << 'EOF'
# Files that should not be overwritten during /upgrade
# One path per line, relative to repo root

# Custom agent modifications
.claude/agents/github-ticket-worker.md
.claude/agents/pr-reviewer.md

# Team-specific commands
.claude/commands/work-ticket.md

# Custom CI workflow
.github/workflows/custom-deploy.yml
EOF

  git add .gembaflow-overrides 2>/dev/null || true
  log_info "Created .gembaflow-overrides with protected paths"
}

# Scenario: uncommitted-framework
# Simulates uncommitted changes in framework-controlled files
scenario_uncommitted_framework() {
  log_info "Applying scenario: uncommitted-framework"
  
  if [ -f "scripts/doctor.sh" ]; then
    echo "# Local debug modification" >> scripts/doctor.sh
    echo "echo 'DEBUG: Running modified doctor'" >> scripts/doctor.sh
    log_info "Modified scripts/doctor.sh (uncommitted)"
  fi
  
  if [ -f ".claude/agents/pr-reviewer.md" ]; then
    echo "" >> .claude/agents/pr-reviewer.md
    echo "<!-- Local testing note -->" >> .claude/agents/pr-reviewer.md
    log_info "Modified pr-reviewer.md (uncommitted)"
  fi
  
  log_warn "Framework files modified but NOT staged/committed"
}

# Scenario: uncommitted-userland
# Simulates uncommitted changes in user content only
scenario_uncommitted_userland() {
  log_info "Applying scenario: uncommitted-userland"
  
  mkdir -p app/components
  cat > app/components/Button.tsx << 'EOF'
// Work in progress - do not commit yet
export function Button({ children }: { children: React.ReactNode }) {
  return (
    <button className="bg-blue-500 text-white px-4 py-2 rounded">
      {children}
    </button>
  );
}
EOF

  mkdir -p docs
  echo "# WIP: API Documentation" > docs/API.md
  echo "" >> docs/API.md
  echo "TODO: Document all endpoints" >> docs/API.md
  
  log_info "Created uncommitted user content (app/, docs/)"
  log_warn "User files modified but NOT staged/committed"
}

# Scenario: mid-feature
# Simulates being mid-feature branch
scenario_mid_feature() {
  log_info "Applying scenario: mid-feature"
  
  # Create and switch to feature branch
  BRANCH_NAME="feature/test-user-auth-$(date +%s)"
  git checkout -b "$BRANCH_NAME" 2>/dev/null || git checkout "$BRANCH_NAME"
  
  # Add some feature work
  mkdir -p app/auth
  cat > app/auth/login.tsx << 'EOF'
'use client';

import { useState } from 'react';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    // TODO: Implement actual auth
    console.log('Login attempt:', email);
  };
  
  return (
    <form onSubmit={handleSubmit}>
      <input 
        type="email" 
        value={email} 
        onChange={(e) => setEmail(e.target.value)}
        placeholder="Email"
      />
      <input 
        type="password" 
        value={password} 
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Password"
      />
      <button type="submit">Login</button>
    </form>
  );
}
EOF

  git add app/auth/
  git commit -m "WIP: Add login page skeleton" 2>/dev/null || true
  
  # Add more uncommitted work
  echo "// More WIP" >> app/auth/login.tsx
  
  log_info "Created feature branch: $BRANCH_NAME"
  log_info "Has 1 commit + uncommitted changes"
}

# Scenario: stale-version
# Simulates being on an old upstream version
scenario_stale_version() {
  log_info "Applying scenario: stale-version"
  
  if [ -f ".gembaflow-meta/version" ]; then
    echo "v0.9.0" > .gembaflow-meta/version
    git add .gembaflow-meta/version 2>/dev/null || true
    log_info "Set .gembaflow-meta/version to v0.9.0 (stale)"
  else
    mkdir -p .gembaflow-meta
    echo "v0.9.0" > .gembaflow-meta/version
    log_info "Created .gembaflow-meta/version at v0.9.0 (stale)"
  fi
}

# Scenario: mixed-mess
# Combination stress test
scenario_mixed_mess() {
  log_info "Applying scenario: mixed-mess (stress test)"
  
  scenario_post_bootstrap_full
  scenario_modified_agents
  scenario_has_overrides
  scenario_stale_version
  scenario_uncommitted_userland
  
  log_warn "Applied multiple scenarios - this is a stress test state"
}

# Reset to clean state
scenario_clean() {
  log_info "Resetting to clean state"
  
  # Discard uncommitted changes
  git checkout -- . 2>/dev/null || true
  git clean -fd 2>/dev/null || true
  
  # Return to main
  git checkout main 2>/dev/null || git checkout master 2>/dev/null || true
  
  # Delete test branches
  git branch | grep "feature/test-" | xargs -r git branch -D 2>/dev/null || true
  
  log_info "Cleaned up test artifacts"
}

# List all scenarios
list_scenarios() {
  echo ""
  echo "Available scenarios:"
  echo ""
  echo "  post-bootstrap-product  — User completed /bootstrap-product (has PRODUCT-*.md)"
  echo "  post-bootstrap-full     — User completed full bootstrap (product + architecture)"
  echo "  modified-agents         — User has customized agent definitions"
  echo "  modified-commands       — User has customized command files"
  echo "  has-overrides           — User has .gembaflow-overrides configured"
  echo "  uncommitted-framework   — User has uncommitted changes in framework files"
  echo "  uncommitted-userland    — User has uncommitted changes in user content only"
  echo "  mid-feature             — User is mid-feature branch with changes"
  echo "  stale-version           — User is on an old upstream version"
  echo "  mixed-mess              — Combination of multiple scenarios (stress test)"
  echo "  clean                   — Reset to clean state"
  echo ""
  echo "Usage: bash scripts/test-dirty-fork.sh <scenario>"
  echo ""
}

# Main dispatch
main() {
  case "$SCENARIO" in
    post-bootstrap-product)
      ensure_git_repo
      warn_will_modify
      scenario_post_bootstrap_product
      ;;
    post-bootstrap-full)
      ensure_git_repo
      warn_will_modify
      scenario_post_bootstrap_full
      ;;
    modified-agents)
      ensure_git_repo
      warn_will_modify
      scenario_modified_agents
      ;;
    modified-commands)
      ensure_git_repo
      warn_will_modify
      scenario_modified_commands
      ;;
    has-overrides)
      ensure_git_repo
      warn_will_modify
      scenario_has_overrides
      ;;
    uncommitted-framework)
      ensure_git_repo
      warn_will_modify
      scenario_uncommitted_framework
      ;;
    uncommitted-userland)
      ensure_git_repo
      warn_will_modify
      scenario_uncommitted_userland
      ;;
    mid-feature)
      ensure_git_repo
      warn_will_modify
      scenario_mid_feature
      ;;
    stale-version)
      ensure_git_repo
      warn_will_modify
      scenario_stale_version
      ;;
    mixed-mess)
      ensure_git_repo
      warn_will_modify
      scenario_mixed_mess
      ;;
    clean)
      ensure_git_repo
      scenario_clean
      ;;
    list|--help|-h|"")
      list_scenarios
      ;;
    *)
      log_error "Unknown scenario: $SCENARIO"
      list_scenarios
      exit 1
      ;;
  esac
}

main
