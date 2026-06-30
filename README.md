<!-- FRAMEWORK:START -->
# Gemba Flow (GCP Edition)

[![License: BSL 1.1](https://img.shields.io/badge/License-BSL_1.1-blue.svg)](LICENSE) [![Version](https://img.shields.io/badge/version-0.1.0-green.svg)](.gembaflow-version) [![Use this template](https://img.shields.io/badge/Use_this-template-2ea44f)](https://github.com/vibeacademy/gembaflow-gcp/generate) [![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/vibeacademy/gembaflow-gcp)

A Claude Code project template that bootstraps a complete agile development workflow with specialized AI agents, **configured for Google Cloud Platform**.

> **New here?** Click the **Open in GitHub Codespaces** badge above to spin up a preconfigured Linux container with Python, Node, `gh`, and `gcloud` already installed and `AGILE_FLOW_SOLO_MODE` already set. The Codespace path is the recommended setup for workshops, tutorials, and first-time evaluation. See [`docs/GETTING-STARTED.md`](docs/GETTING-STARTED.md) for the full walkthrough.
>
> **Not on GCP?** This is the GCP-specific fork. The upstream [vibeacademy/agile-flow](https://github.com/vibeacademy/agile-flow) ships with Render + Supabase as the default and supports Vercel, Cloudflare, Railway, and Fly.io. Use that one if you're deploying anywhere other than GCP.

[![Watch the video](https://img.youtube.com/vi/rkHxmnsyTiM/maxresdefault.jpg)](https://youtu.be/rkHxmnsyTiM)

## Why This Exists

In lean manufacturing, a **gemba walk** is when a manager goes to the
factory floor to observe work as it actually happens — not through
reports or dashboards, but firsthand. The word *gemba* (現場) means "the
actual place." You cannot improve a process you have not seen. You
cannot catch problems from a summary.

Agile Flow applies the same principle to AI-assisted development. When
agents write code on your behalf, you are the factory manager. If you
are not observing the work as it actually happens, you cannot be a
responsible supervisor — and you expose yourself to risks you cannot
see.

Every practice in this template exists to keep your observation loop
tight:

- **Short-lived branches** so changes are small enough to actually read
- **Structured commit messages** so you can scan the history at a glance
- **Preview environments** so you can see what the change looks like live
- **CI checks** so quality is verified before you even look at the PR
- **Small, focused pull requests** so reviewing is a gemba walk through
  the actual work — not a rubber stamp on a 2,000-line report

A 2,000-line diff is not a gemba walk. It is a report you will skim and
approve because reviewing it properly is too expensive. That is where
risk hides. The specific intent of this template is to make it easy for
human supervisors to walk the *gemba*.

## What This Is

Agile Flow provides a team of AI agents that work together to manage your software project:

| Agent | Role |
|-------|------|
| Product Manager | Strategy, vision, go/no-go decisions |
| Product Owner | Backlog management, ticket quality |
| Ticket Worker | Implementation, PRs |
| PR Reviewer | Code review, quality gate |
| Quality Engineer | Test planning, validation |
| System Architect | Design guidance, patterns |
| DevOps Engineer | Deployment, infrastructure, previews |

The agents hand off work to each other through a structured workflow, with humans making final merge decisions.

### What This Does NOT Include

Agile Flow GCP is a **workflow template**, not a full application. You provide:

- **Your application code** — the template ships a minimal FastAPI + HTMX todo app as a reference; you delete it and build your own
- **Your GCP project** — you create and fund the GCP project; see `docs/PLATFORM-GUIDE.md` for setup
- **Your Neon account** — you create the Neon project and paste the credentials into GitHub secrets
- **Your domain logic** — agents help you build, but you define what to build

### What This DOES Include

- **A working FastAPI + Jinja2 + HTMX starter** — reference todo app with database persistence, Alembic migrations, and HTMX-driven interactivity
- **A minimal Dockerfile** (~20 lines, single-stage, Python 3.12 + uv) targeting Cloud Run
- **GitHub Actions workflows** for production deploys and ephemeral PR previews
- **Neon branching integration** — every PR gets its own database branch, migrated automatically before deploy
- **Cloud Run revision tagging** — every PR gets a stable preview URL with zero production traffic
- **Workload Identity Federation support** (with SA key fallback for workshops)
- **Stack-specific agent guardrails** — the `github-ticket-worker` agent knows about Cloud Run, Neon, FastAPI, and SQLModel gotchas

## Prerequisites

- [Claude Code](https://claude.ai/code) CLI installed
- GitHub repository with project board
- Node.js 18+ (for MCP servers: memory, sequential-thinking)

## How It Works: Progressive Refinement

Agile Flow uses **progressive refinement** - each phase builds context that makes subsequent phases more focused and effective.

```
Phase 1: Product Definition
    |
    | Creates: PRODUCT-REQUIREMENTS.md
    | Unlocks: Product context for all agents
    v
Phase 2: Technical Architecture
    |
    | Creates: TECHNICAL-ARCHITECTURE.md
    | Unlocks: Tech stack context, coding standards
    v
Phase 3: Agent Specialization
    |
    | Updates: Agent configs with project context
    | Unlocks: Project-specific agent behavior
    v
Phase 4: Workflow Activation
    |
    | Creates: GitHub board, branch protection
    | Unlocks: Full agent workflow
    v
Ready for Development
```

### Why Progressive Refinement?

Generic agents produce generic results. By building context progressively:

1. **Product Manager** creates PRD → agents understand *what* we're building
2. **System Architect** creates tech architecture → agents understand *how* we're building
3. **Agents get specialized** → agents give project-specific guidance
4. **Workflow activates** → agents can execute with full context

## Quick Start

```bash
./bootstrap.sh
```

The interactive wizard walks you through four phases: product definition,
technical architecture, agent specialization, and workflow activation.

For step-by-step instructions, see
[docs/GETTING-STARTED.md](./docs/GETTING-STARTED.md).

## After Bootstrap

Once bootstrap is complete, use the standard workflow:

```bash
# Daily development
/sprint-status          # Check board health
/work-ticket            # Pick up next ticket
/review-pr              # Review pending PRs

# Planning
/groom-backlog          # Manage backlog
/check-milestone        # Track progress

# Decisions
/evaluate-feature       # Assess feature requests
/release-decision       # Go/no-go for releases
/architect-review       # Design guidance
```

## Project Structure

```
your-project/
├── .claude/
│   ├── agents/                 # Agent definitions
│   │   ├── agile-product-manager.md
│   │   ├── agile-backlog-prioritizer.md
│   │   ├── github-ticket-worker.md
│   │   ├── pr-reviewer.md
│   │   ├── quality-engineer.md
│   │   ├── system-architect.md
│   │   └── devops-engineer.md
│   ├── commands/               # Slash commands
│   │   ├── bootstrap-product.md
│   │   ├── bootstrap-architecture.md
│   │   ├── bootstrap-agents.md
│   │   ├── bootstrap-workflow.md
│   │   ├── groom-backlog.md
│   │   ├── work-ticket.md
│   │   └── ... (other commands)
│   └── settings.local.json     # MCP configuration
├── docs/
│   ├── PRODUCT-REQUIREMENTS.md # Created in Phase 1
│   ├── PRODUCT-ROADMAP.md      # Created in Phase 1
│   └── TECHNICAL-ARCHITECTURE.md # Created in Phase 2
├── CLAUDE.md                   # Project configuration
├── bootstrap.sh                # Bootstrap wizard
└── README.md                   # This file
```

## Requirements

### Trunk-Based Development (Required)

This template **requires** trunk-based development:
- `main` branch is protected
- All work on feature branches
- All changes via pull requests
- Human performs final merge

The agent workflow depends on this structure. See [docs/BRANCHING-STRATEGY.md](./docs/BRANCHING-STRATEGY.md) for the reasoning and [CLAUDE.md](./CLAUDE.md) for the rules.

### GitHub Configuration

You'll need:
- A GitHub repository
- Permission to create project boards
- Permission to configure branch protection
- GitHub accounts authenticated via `gh auth login`

#### Authenticating with GitHub

Agile Flow uses the `gh` CLI for all GitHub operations. Authenticate
each account (human + bot accounts) using the `gh` keyring:

```bash
gh auth login          # Human account (for merging PRs)
gh auth login          # Worker bot account (for creating PRs)
gh auth login          # Reviewer bot account (for reviewing PRs)
```

Each account needs a PAT with these permissions:

| Permission | Access Level | Why Needed |
|------------|--------------|------------|
| Contents | Read and write | Create branches, push commits |
| Issues | Read and write | Create/update tickets |
| Pull requests | Read and write | Create PRs, add comments |
| Projects | Read and write | Manage project board columns |
| Metadata | Read-only | Required for API access |

The bootstrap wizard walks you through this. See
[docs/GETTING-STARTED.md](./docs/GETTING-STARTED.md#step-2-set-up-github-access)
for detailed setup options.

### MCP Servers

Claude Code uses MCP (Model Context Protocol) servers for agent memory
and structured reasoning. GitHub operations use the `gh` CLI instead.

| Server | Package | Required | Purpose |
|--------|---------|----------|---------|
| `memory` | `@modelcontextprotocol/server-memory` | Yes | Persistent agent context across sessions |
| `sequential-thinking` | `@modelcontextprotocol/server-sequential-thinking` | Recommended | Structured multi-step reasoning |

Setup differs depending on how you run Claude Code:

#### Option A: Terminal CLI

The bootstrap wizard creates `.mcp.json` automatically, but you can also
create it manually in your project root:

```json
{
  "mcpServers": {
    "memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"]
    },
    "sequential-thinking": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
    }
  }
}
```

#### Option B: Claude Desktop app

The desktop app does **not** read `.mcp.json` from your project. Instead,
add the same `mcpServers` block to your desktop config file:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

If the file already exists, merge the `mcpServers` entries into it. If
it doesn't exist, create it with the same JSON shown above.

> **Note:** MCP servers configured in the desktop app and in the CLI are
> independent. If you use both, configure servers in both places.

#### Verifying MCP

In any Claude Code session (terminal or desktop), run `/mcp` to confirm
servers are connected.

## Customization

### Adding Project-Specific Context

After bootstrap, you can further refine agents by editing their definitions in `.claude/agents/`. Look for `<!-- TEMPLATE: ... -->` comments indicating where to add project-specific context.

### Adding Custom Commands

Create new `.md` files in `.claude/commands/` following the existing patterns.

### Extending the Workflow

The agent workflow can be extended by:
1. Adding new agents in `.claude/agents/`
2. Creating commands that invoke them
3. Updating CLAUDE.md with new handoff protocols

## Philosophy

### Quality of Internal Deliverables

The core assumption is: **quality of internal deliverables drives final product quality**.

- Good PRD → Good architecture decisions
- Good tickets → Good implementations
- Good reviews → Good merges
- Good tests → Confident releases

Each agent is accountable for the quality of their outputs.

### Agents as Team Members

Treat agents as team members with specific roles:
- They have expertise (defined in their config)
- They have boundaries (what they can/cannot do)
- They hand off work (via project board)
- They need context (provided progressively)

### Human in the Loop

Humans remain in control of:
- Final merge decisions
- Release approvals
- Strategic pivots
- Conflict resolution

Agents provide recommendations; humans make decisions.

### Scope Lock

Scope lock is a formal checkpoint that signals MVP scope is finalized and development can begin with confidence.

**Criteria for Scope Lock:**

| Criteria | Locked | Not Locked |
|----------|--------|------------|
| Feature list | Fixed: "We're building A, B, C" | Fluid: "Maybe C or D" |
| Acceptance criteria | Each feature has testable conditions | Features are vague ideas |
| Open questions | Major decisions resolved | "TBD" items remain |
| Change process | Adding scope requires trade-offs | "Let's add that too" |
| Timeline | Dates based on defined scope | Dates slide with scope |

**When to Lock:**
- After PRD is complete (`/bootstrap-product`)
- After technical feasibility confirmed (`/bootstrap-architecture`)
- After backlog has tickets for all MVP features (`/groom-backlog`)
- Before significant development begins

**Why Lock Matters:**
- **Engineering** can commit to realistic timelines
- **Stakeholders** are aligned on what "done" means
- **Scope creep** becomes visible (requires unlocking)

**Run `/lock-scope` to:**
1. Verify all lock criteria are met
2. Document the locked scope
3. Create `docs/SCOPE-LOCK.md` as the contract

## Troubleshooting

### Bootstrap Issues

**"Phase X requires Phase Y to be complete"**
- Run phases in order: Product → Architecture → Agents → Workflow

**"GitHub token not configured"**
- Set `GITHUB_TOKEN` environment variable
- Or configure in `.claude/settings.local.json`

### Workflow Issues

**"Ready column is empty"**
- Run `/groom-backlog` to populate from backlog

**"Agent doesn't have project context"**
- Ensure you completed Phase 3 (Agent Specialization)
- Check agent configs for project-specific sections

**"PR reviewer can't find PRs"**
- Ensure tickets are moved to "In Review" column
- Check that PRs are linked to issues

## Contributing

This is a template project. To contribute:
1. Fork the repository
2. Make improvements to agent definitions or commands
3. Submit PR with clear description of changes

## Attribution

Built with [Agile Flow](https://github.com/vibeacademy/agile-flow) by
[VibeAcademy](https://vibeacademy.com).
## License

Business Source License 1.1 — see [LICENSE](LICENSE) for full terms.

You may use Agile Flow for any purpose, including production use, except
for offering a commercial product that competes with Agile Flow (a
developer workflow automation framework). On 2029-03-06, this version
converts to the Apache License 2.0.
<!-- FRAMEWORK:END -->
