---
description: "Phase 4: Activate the development workflow"
---

Set up GitHub project board, branch protection, and create initial backlog from PRD features.

## Bootstrap Phase 4: Workflow Activation

**Prerequisites**:
- Phase 1 (Product Definition) complete
- Phase 2 (Technical Architecture) complete
- Phase 3 (Agent Specialization) complete

This is the final bootstrap phase. It activates the full agent workflow.

## Ticket Format Requirement

Before creating any issues, read `docs/TICKET-FORMAT.md` in full. Every issue
created in this phase — epics and features alike — MUST follow the Agentic PRD
Lite format. Tickets without the 4 Power Sections (A. Environment Context,
B. Guardrails, C. Happy Path, D. Definition of Done) will not pass grooming
and will have to be rewritten.

## What This Phase Does

### 1. GitHub Project Board Setup

Verify or create project board with columns:
- **Icebox** - Ideas not yet prioritized
- **Backlog** - Prioritized but not ready
- **Ready** - Well-defined, ready to work (2-5 items)
- **In Progress** - Currently being worked
- **In Review** - PR created, awaiting review
- **Done** - Merged and complete

### 2. Branch Protection Configuration

Verify or configure branch protection on `main`:
- [ ] Require pull request reviews before merging
- [ ] Require status checks to pass (if CI configured)
- [ ] Do not allow bypassing the above settings

### 3. Initial Backlog Creation

Convert PRD features into GitHub issues following `docs/TICKET-FORMAT.md`:
- Create epics for major feature areas (epics use Problem Statement + high-level scope)
- Create feature issues with ALL required fields:
  - Problem Statement, Parent Epic, Effort Estimate, Priority
  - A. Environment Context (from `docs/TECHNICAL-ARCHITECTURE.md`)
  - B. Guardrails (from `docs/AGENTIC-CONTROLS.md` + PRD constraints)
  - C. Happy Path (numbered steps: Input → Logic → Output)
  - D. Definition of Done (specific test assertions, lint commands, reviewer checks)
- Link issues to epics
- Add priority labels (P0/P1/P2/P3)

### 4. Ready Column Population

Move the highest-priority, well-defined tickets to Ready:
- Select 3-5 tickets for initial Ready column
- Ensure they meet Definition of Ready
- Add technical guidance and acceptance criteria

### 5. CLAUDE.md Finalization

Update CLAUDE.md with:
- Project board URL
- Repository URL
- Team/org information
- Any final configuration

## Pre-Flight Checklist

Before running this phase, ensure you have:

- [ ] GitHub repository created
- [ ] GitHub personal access token with repo, project, and workflow permissions
- [ ] Permission to create project boards
- [ ] Permission to configure branch protection

## Pre-Flight Verification (REQUIRED)

Before any board or ticket operations, verify the following. STOP and report
to the user if any check fails — do not continue with partial tooling.

1. **MCP GitHub server is reachable** — Attempt a GitHub MCP tool call (e.g.,
   list repos). If the MCP server is not connected, STOP. Do not fall back to
   CLI-only mode silently.
2. **GitHub account is correct** — Run `gh auth status` and confirm the active
   account matches the expected worker/bot account. If only a personal account
   is active, STOP and instruct the user to run `scripts/ensure-github-account.sh`.
3. **Claude hooks are registered** — Check that hook files referenced in
   `.claude/settings.local.json` exist and are executable. WARN if any hook is
   missing or not executable.
4. **Project board is accessible** — Attempt to read the project board. If
   access is denied or the board does not exist, STOP and report.

## Configuration Required

You'll be asked to provide:

```
GitHub Organization: [your-org]
Repository Name: [your-repo]
Project Board Name: [your-project-name]
```

## Process

The workflow activation agent will:

1. **Verify GitHub Access**
   - Test token permissions
   - Confirm org/repo access

2. **Create/Verify Project Board**
   - Check if board exists
   - Create columns if needed
   - Configure board settings

3. **Configure Branch Protection**
   - Check current settings
   - Apply protection rules
   - Verify configuration

4. **Generate Backlog**
   - Read `docs/TICKET-FORMAT.md` for the canonical ticket format
   - Read PRD features from `docs/PRODUCT-REQUIREMENTS.md`
   - Read `docs/TECHNICAL-ARCHITECTURE.md` for Environment Context content
   - Read `docs/AGENTIC-CONTROLS.md` for Guardrails content
   - Create epic issues (Problem Statement + scope description)
   - Create feature issues with all 4 Power Sections populated
   - Set initial priorities (P0-P3)
   - Self-check: before creating each issue, verify it contains sections A through D

5. **Populate Ready Column**
   - Select MVP tickets
   - Ensure Definition of Ready met
   - Move to Ready column

6. **Update Configuration**
   - Add URLs to CLAUDE.md
   - Verify agent configs reference correct board

## Example Backlog Generation

> Every issue MUST follow `docs/TICKET-FORMAT.md`. The example below shows the
> expected structure. Do NOT create bare-title issues without Power Sections.

From a PRD feature like:
```markdown
### MVP Features
- User authentication (email/password)
```

Create an epic:
```
Epic: User Authentication

Problem Statement:
The application has no way to identify users. All routes are public.
We need email/password authentication to gate access to user-specific data.

Scope: signup, login, password reset, session management.
Priority: P0
```

Then create feature issues with full Power Sections:
```
TICKET: Implement email/password signup

Problem Statement:
New users cannot create accounts. We need a signup endpoint that accepts
email + password, validates input, and creates a user record.

Parent Epic: #<epic-number>
Effort Estimate: M
Priority: P0

--- A. Environment Context ---
- Stack: (from TECHNICAL-ARCHITECTURE.md)
- Existing pattern: (reference a similar route in the codebase)
- Files to create/modify: (list explicitly)

--- B. Guardrails ---
- (from AGENTIC-CONTROLS.md + PRD constraints)
- Do NOT store plaintext passwords
- Do NOT modify existing auth middleware

--- C. Happy Path ---
1. Client sends POST /auth/signup with {email, password}
2. Server validates email format and password strength
3. Server hashes password, creates user record
4. Server returns 201 with {id, email}

--- D. Definition of Done ---
- Test asserts POST /auth/signup with valid data returns 201
- Test asserts duplicate email returns 409
- Test asserts weak password returns 422
- Lint and type checks pass with zero errors
- PR reviewer can run the signup flow manually
```

## What Gets Unlocked

After Phase 4, the full workflow is active:

```
/groom-backlog  →  Works with your project board
/work-ticket    →  Picks up tickets from your Ready column
/review-pr      →  Reviews PRs in your repository
/sprint-status  →  Shows your board status
```

## Verification

After this phase, verify the workflow:

1. **Check Project Board**
   - Visit the GitHub project board URL
   - Verify columns exist
   - Verify issues created

2. **Check Branch Protection**
   - Go to repo Settings → Branches
   - Verify `main` is protected

3. **Test Workflow**
   ```bash
   claude
   > /sprint-status
   ```
   Should show your board status

## Post-Bootstrap

Your project is now ready for development!

**Daily workflow:**
```bash
/sprint-status    # Morning check
/work-ticket      # Pick up work
/review-pr        # Review PRs
```

**Weekly planning:**
```bash
/check-milestone  # Track progress
/groom-backlog    # Maintain backlog
```

## Troubleshooting

**"GitHub token not authorized"**
- Ensure token has `repo`, `project`, and `workflow` scopes
- Check token isn't expired

**"Cannot create project board"**
- Verify org permissions
- Try creating manually, then link

**"Branch protection failed"**
- Verify you have admin access to repo
- Configure manually in GitHub settings

**"Issues not appearing on board"**
- Check issue labels match board filters
- Manually add issues to project

## Running This Command

1. Ensure Phases 1-3 are complete
2. Have GitHub credentials ready
3. Type `/bootstrap-workflow`
4. Provide org/repo information
5. Review proposed changes
6. Confirm to apply

When complete, your Agile Flow project is fully operational!

## Next Steps

After bootstrap:

1. **Review the backlog** - `/groom-backlog`
2. **Start first ticket** - `/work-ticket`
3. **Invite team members** - Share repo access
4. **Set up CI/CD** - Configure GitHub Actions
5. **Schedule standups** - Daily `/sprint-status`

### Output Format

Report each phase with a Progress Line, then end with a Result Block:

```
→ Configured GitHub project board
→ Set up branch protection rules
→ Generated backlog from PRD (12 issues)
→ Populated Ready column (4 tickets)

---

**Result:** Workflow setup complete
Project board: configured
Issues created: 12
Ready column: 4 tickets
Status: ready for development
```
