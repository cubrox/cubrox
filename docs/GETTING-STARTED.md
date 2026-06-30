# Getting Started with Agile Flow

A step-by-step guide to set up your project using the Agile Flow template.
This guide is written for founders and non-engineers -- every step includes
what you should see when it works.

---

## Prerequisites

You need four things installed before you start. If you already have them,
skip to Step 1.

1. **Git** -- version control (tracks every change to your project).
   Install from <https://git-scm.com/downloads>.

2. **Node.js 18 or newer** -- needed for some background tools.
   Install from <https://nodejs.org>.

3. **Claude Code CLI** -- the AI assistant that powers the agents.
   Install from <https://claude.ai/code>.

4. **A GitHub account** -- where your code and project board live.
   Sign up at <https://github.com>.

You will also need a **GitHub personal access token** so the tools can
talk to GitHub on your behalf. To create one:

1. Go to <https://github.com/settings/tokens>.
2. Click **"Generate new token (classic)"**.
3. Check the `repo`, `project`, and `workflow` boxes.
4. Click **Generate token** and copy it somewhere safe.

---

## Step 1: Create Your Project from the Template

Go to the [Agile Flow template](https://github.com/vibeacademy/agile-flow)
on GitHub and click **"Use this template" > "Create a new repository"**.

- **Owner**: Choose your GitHub account or organization.
- **Repository name**: Pick a name for your project (e.g., `my-app`).
- **Visibility**: Public or Private -- your choice.

Click **Create repository**.

> **Why "Use this template" instead of Fork?** A template creates a fresh
> repo with no upstream link, its own issue tracker, and its own project
> board -- exactly what you need for a new project.

**You should see:** Your own repository at
`https://github.com/your-name/my-app`.

You now have two paths to set up your dev environment. **Pick one.**

### Path A: GitHub Codespace (recommended)

A Codespace is a preconfigured Linux container running in the cloud.
It eliminates the entire "make my laptop work" surface — Python, Node,
`gh`, `gcloud`, and the `AGILE_FLOW_SOLO_MODE` env var are all set up
for you, identically across all attendees.

1. On your repo's GitHub page, click **Code → Codespaces → Create
   codespace on `main`** (or click the **Open in GitHub Codespaces**
   badge in the README).
2. Wait ~60 seconds for the container to provision.
3. Run `gcloud auth login` in the integrated terminal to authenticate
   with GCP (browser OAuth flow).
4. Skip to **Step 2: Set Up GitHub Access** below — except gh is
   already authenticated, so you can skip Step 2 entirely.

The container runs `scripts/setup-solo-mode.sh` automatically as
`postCreateCommand`, so the pre-push hook is already active and your
gh scopes are already verified.

> **Workshop note for facilitators:** Codespaces is per-attendee
> billing on a 2-core machine — roughly $15-25 of compute per cohort
> for a 2-day workshop. See `docs/PLATFORM-GUIDE.md` "Codespace cost
> estimate" for current numbers.
>
> **Closed-network attendees:** if your corporate firewall blocks
> `*.github.dev` or VS Code Server, Codespaces won't work — use Path B
> below instead.

### Path B: Local clone (fallback)

```bash
cd ~/projects   # or wherever you keep repos
git clone https://github.com/your-name/my-app.git
cd my-app
bash scripts/setup-solo-mode.sh
npm install
```

`scripts/setup-solo-mode.sh` is the bootstrap for solo mode (one
personal account plays all roles — workshop attendees, individual
learners, framework evaluators). It activates the pre-push quality
gate, persists `AGILE_FLOW_SOLO_MODE=true` to your shell rc, audits
stale `GITHUB_PERSONAL_ACCESS_TOKEN*` env vars (which silently override
`gh auth switch`), verifies your gh token has the required scopes, and
confirms you have admin access on the fork. It does NOT cache tokens
to disk and does NOT modify your shell rc to remove tokens — it
surfaces them with the exact removal command.

After it completes, **restart your shell or Claude Code** so the new
`AGILE_FLOW_SOLO_MODE` env var is picked up by agent subprocesses.

If you prefer the minimal manual path (no env-var management, no scope
verification), the single command the script wraps for activating the
hook is:

```bash
git config --local core.hooksPath scripts/hooks
```

For multi-bot setups (worker + reviewer + human merger, with
provisioned bot accounts), use `scripts/setup-accounts.sh` instead.
Solo mode is the default for new forks; multi-bot mode is the
production opt-in.

**You should see:** Dependencies installed with no errors.

---

## Step 2: Set Up GitHub Access

Give the tools permission to use GitHub by storing your personal access
token. Run one of these in your terminal:

```bash
# Option 1: Set it for this terminal session only
export GITHUB_TOKEN=paste_your_token_here

# Option 2: Save it permanently (recommended)
# For Mac/Linux:
echo 'export GITHUB_TOKEN=paste_your_token_here' >> ~/.zshrc
source ~/.zshrc
```

**You should see:** No output (that means it worked). To verify, run:

```bash
echo $GITHUB_TOKEN
```

You should see your token printed back.

---

## Step 2b: Configure Claude Code MCP Servers

Claude Code uses MCP (Model Context Protocol) servers for agent memory
and structured reasoning. The bootstrap wizard creates a `.mcp.json`
file for you. GitHub operations use the `gh` CLI (configured in Step 2),
not MCP.

### MCP Servers

| Server | Required? | What It Does | Token |
|--------|-----------|--------------|-------|
| `memory` | Yes | Agent context persistence across sessions | none |
| `sequential-thinking` | No | Structured reasoning for complex tasks | none |

### Verify MCP is working

After running `claude` for the first time, you should see MCP servers
listed in the startup output. Run `/mcp` inside Claude Code to confirm
servers are connected.

> **Bot accounts**: If you are using separate worker and reviewer bot
> accounts, each needs `gh auth login`. See `.claude/README.md` for
> full bot account setup.

---

## Step 3: Run the Bootstrap Wizard

The bootstrap wizard walks you through setting up your project in four
phases. It asks you questions and generates configuration files based on
your answers.

```bash
bash bootstrap.sh
```

**You should see:** A welcome screen with four phases listed.

### Phase 1: Define Your Product

The AI asks you about your product -- what problem it solves, who your
users are, and what features you need.

```bash
# Open the AI assistant
claude

# Then type this command inside Claude Code
/bootstrap-product
```

Answer the questions. When it finishes, it creates two files:

- `docs/PRODUCT-REQUIREMENTS.md` -- what you are building and why
- `docs/PRODUCT-ROADMAP.md` -- the plan, broken into phases

**You should see:** Both files appear in your `docs/` folder. Open them
to verify they match what you described.

### Phase 2: Define Your Technical Architecture

The AI reads what you described in Phase 1 and helps pick the right
technology.

```bash
# Inside Claude Code
/bootstrap-architecture
```

**You should see:** A new file at `docs/TECHNICAL-ARCHITECTURE.md`.

### Phase 3: Configure the AI Agents

The AI updates its own configuration files so the agents understand your
specific project.

```bash
# Inside Claude Code
/bootstrap-agents
```

**You should see:** Updated files inside the `.claude/` folder. The
agents now know about your tech stack and project details.

### Phase 4: Set Up Your Project Board

The AI creates your GitHub project board and populates it with your first
set of tasks (called "tickets").

```bash
# Inside Claude Code
/bootstrap-workflow
```

You will be asked for your GitHub organization name, repository name, and
project board name.

**You should see:** A project board on GitHub with columns like Backlog,
Ready, In Progress, In Review, and Done.

---

## Step 4: Protect Your Main Branch

The bootstrap wizard (`bash bootstrap.sh`, Phase 4) automatically
creates a GitHub **Ruleset** that protects your `main` branch. It
requires pull requests and passing status checks before code can be
merged.

If the automated step fails (e.g., insufficient permissions), you can
create the ruleset manually:

1. Go to your repository on GitHub.
2. Click **Settings** (top menu bar).
3. Click **Rules > Rulesets** (left sidebar).
4. Click **New ruleset > New branch ruleset**.
5. Name it `Protect main`.
6. Under **Target branches**, add `main`.
7. Enable these rules:
   - "Require a pull request before merging"
   - "Require status checks to pass before merging" (if you have CI)
   - "Block force pushes"
8. Click **Create**.

**You should see:** A ruleset listed under Settings > Rules > Rulesets.

> **Note:** The legacy Settings > Branches page still works but GitHub
> recommends Rulesets for new repositories.

---

## Step 5: Make Your First Commit

Save everything and push it to GitHub.

```bash
# Stage all files (prepare them to be saved)
git add -A

# Save a snapshot with a description
git commit -m "Initialize project with Agile Flow template"

# Upload to GitHub
git push -u origin main
```

**You should see:** Output ending with something like
`Branch 'main' set up to track remote branch 'main' from 'origin'.`

---

## Step 6: Work on Your First Ticket

Now that setup is complete, here is how day-to-day work looks.

```bash
# Open the AI assistant
claude

# Check what is on the board
/sprint-status

# Tell the AI to pick up the next task and start coding
/work-ticket
```

The AI will:

1. Pick the top task from the Ready column.
2. Create a branch (a separate workspace so `main` stays safe).
3. Write the code and tests.
4. Open a **pull request** (a proposal to add the changes).

**You should see:** A new pull request on your GitHub repository.

---

## Step 7: Review and Merge

After the AI finishes a task, review its work before adding it to the
main project.

```bash
# Ask the AI reviewer to check the code
/review-pr
```

Then go to the pull request on GitHub:

1. Read the AI review comments.
2. Look over the changes yourself.
3. If everything looks good, click **"Squash and merge"**.
4. Move the ticket to the **Done** column on your project board.

**You should see:** The pull request status changes to "Merged" (purple
icon on GitHub).

---

## Command Reference

| Command | What it does |
|---------|-------------|
| `/sprint-status` | Shows the current state of your project board |
| `/work-ticket` | Picks up the next task and writes the code |
| `/review-pr` | Reviews a pull request and recommends approve or reject |
| `/groom-backlog` | Organizes and prioritizes your task list |
| `/check-milestone` | Shows progress toward a goal (e.g., MVP) |
| `/evaluate-feature` | Evaluates whether a feature idea is worth building |
| `/release-decision` | Helps decide if you are ready to ship |
| `/test-feature` | Creates a test plan for a feature |
| `/architect-review` | Gets technical design advice |

For a full explanation of how agents work together, see
[AGENT-WORKFLOW-SUMMARY.md](AGENT-WORKFLOW-SUMMARY.md).

For details about each AI agent's role and rules, see the agent files in
`.claude/agents/`.

---

## Troubleshooting

### "Ready column is empty"

The AI has nothing to work on. Fill it by running:

```bash
/groom-backlog
```

This looks at your backlog and moves well-defined tasks into the Ready
column.

### "Bootstrap phase failed"

- Make sure you completed earlier phases first (they build on each other).
- Check the `docs/` folder -- if files from earlier phases are missing,
  re-run those phases.
- Re-run the failed phase command.

### "GitHub token not working"

- Make sure your token has `repo`, `project`, and `workflow` permissions (see Step 2).
- Tokens expire. If yours is old, create a new one.
- Verify the token is set by running `echo $GITHUB_TOKEN` in your
  terminal.

### "Agent gives generic advice"

This usually means Phase 3 (agent configuration) did not complete. Run:

```bash
/bootstrap-agents
```

### "Pull request reviewer cannot find PRs"

- Make sure the ticket is in the "In Review" column on your project board.
- Check that the pull request is linked to a GitHub issue.
- Verify the project board URL is set in `CLAUDE.md`.

---

## Checking for Updates

Agile Flow tracks its version in the `.gembaflow-version` file at your
project root. To check which version you are running:

```bash
jq .version .gembaflow-version
```

To see if a newer version is available, visit the
[Agile Flow releases page](https://github.com/vibeacademy/agile-flow/releases).

The `/doctor` command also checks for updates automatically and will warn
you if a newer version is available.

To upgrade, run `/upgrade` from Claude Code. See [UPGRADING.md](UPGRADING.md)
for the full upgrade guide, alternative methods, and troubleshooting.

---

## Next Steps

1. **Fill your backlog** -- run `/groom-backlog` to prioritize tasks.
2. **Work your first ticket** -- run `/work-ticket` to start building.
3. **Set up CI/CD** -- see [CI-CD-GUIDE.md](CI-CD-GUIDE.md) for
   automated checks.
4. **Invite team members** -- share repository access on GitHub.
5. **Check the FAQ** -- see [FAQ.md](FAQ.md) for common questions.

---

For questions not covered here, see the [FAQ](FAQ.md).
