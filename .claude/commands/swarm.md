---
description: Run N parallel implementations of one ticket — swarm-planner produces N briefs, then N github-ticket-workers run in isolated worktrees, then PRs are opened serially. Human picks the winner.
---

Launch the `swarm-planner` agent to generate N distinct implementation briefs, then fan out N `github-ticket-worker` agents in parallel — each in its own worktree, branch, and PR — and aggregate the result.

> **Reference:** See `docs/plans/SWARM-COMMAND-PLAN.md` for the full design rationale (worktree isolation, Option-A serialization, Phase decomposition). See `docs/TICKET-FORMAT.md` for the 4 Power Sections format that the DoR check enforces.

## Pre-Flight Verification (REQUIRED)

Before running any planner or worker, verify all checks below. STOP and report to the user if any fails.

1. **`gh` CLI authenticated** — `gh auth status` must succeed. Re-verify immediately before each `gh pr create` in Phase 4 — the account-switch hook can flip state mid-session.
2. **GitHub account is the configured worker bot** — Run `scripts/ensure-github-account.sh`. If only a personal account is active, STOP and instruct the user to fix.
3. **Project board accessible** — Verify the configured project board is readable. If access is denied or the board does not exist, STOP and report.
4. **Ticket exists and is open** — `gh issue view <N>` must return a non-closed issue.
5. **Definition of Ready** — Issue body contains all four Power Sections (A: Environment Context, B: Guardrails, C: Happy Path, D: Definition of Done), each non-empty. If any is missing, STOP and report which section(s). Do not invent missing content. See `docs/TICKET-FORMAT.md`.
6. **Ticket is NOT already In Progress** — Query the project board for the ticket's current status. If `In Progress`, STOP and report. The ticket may be under solo `/work-ticket`; swarming on top of in-flight work would collide on branches and PRs.
7. **Variant count is valid** — `--variants` defaults to 3. Reject `--variants 1` (pointless — use `/work-ticket`). Reject `--variants 0`, negative, or `> 5`. Max 5 per design-doc decision #1.
8. **Release-freeze warning (not a block)** — If your team has a release-freeze, blackout window, or other coordination pause in effect, print a warning before the cost prompt. User may proceed.

## Critical Rules

1. **Verify Definition of Ready before launching any worker.** A swarm on a thin ticket produces N versions of the same misunderstanding. The planner enforces this; the command must not bypass.
2. **Print a cost estimate and require confirmation unless `--yes`.** N variants is N times the compute, N times the preview-build minutes, and N times the human review burden. The user must opt in explicitly each time, or pass `--yes` to skip the prompt.
3. **Serialize PR creation across variants.** Workers implement, test, commit, push *in parallel*, but `gh pr create` is invoked one variant at a time by the orchestrator. The worker bot account's auth-switch hook has no mutex; concurrent PR creation would race. (Design doc, Option A, v1 decision.)
4. **Refuse to run if the ticket is already In Progress.** Pre-flight check #6 handles this. Do not override.
5. **Never auto-merge any PR.** Variants are for human comparison. The human picks one and merges manually.
6. **Never auto-close losing variants in v1.** Failed comparisons stay open until the human (or a future `/swarm-pick` command) closes them with a pointer to the merged winner.
7. **Default variant count: 3. Max: 5. Min: 2** (`--variants 1` is rejected — use `/work-ticket` instead).
8. **Failed-build variants get labeled `swarm-failed` and stay open.** A red CI run is information, not garbage. Do not delete or auto-close.
9. **Move the ticket to In Progress ONCE (at Phase 2 start), to In Review ONCE (at Phase 4 end).** Workers in swarm mode must NOT touch board state — the orchestrator owns it. (See `.claude/agents/github-ticket-worker.md` swarm-mode section.)

## Workflow

### Phase 1: Plan

1. Resolve `<issue-number>` and `N` (variant count) from arguments. Default N=3.
2. Print the cost estimate (see Reference: Cost Estimation Template).
3. If `--yes` was not passed, prompt the user `Proceed? (y/N)`. Abort on anything other than `y`.
4. Release-freeze warning: if the team has a release-freeze in effect, print the warning before the cost prompt (informational — does not block).
5. Invoke the `swarm-planner` agent via the Task tool with `(issue, N)`. Wait for it to complete.
6. The planner writes `reports/swarms/issue-{N}-briefs.md`. If the planner aborted on a failed DoR check, the command aborts here — report the missing sections and stop.
7. Print the briefs file path. Pause for human skim unless `--yes` was passed. The user reviews the briefs file, then resumes by responding `proceed` or aborts by responding `abort` or anything else.

### Phase 2: Fan out

1. Move the ticket to **In Progress** on the configured project board (once — not N times).
2. For each variant letter `a, b, c, ...` up to N:
   - Compute the branch name: `feature/issue-{N}-{slug}-variant-{letter}` where `{slug}` is a short kebab-cased fragment derived from the ticket title (max 5 words).
   - Create the worktree: `git worktree add .claude/worktrees/swarm-{N}-{letter} -b feature/issue-{N}-{slug}-variant-{letter} origin/main`. The worktree directory should be gitignored so it does not show up in `git status` of the primary clone.
3. Confirm all N worktrees exist before launching workers. If any worktree create fails, clean up the successful ones and abort.

### Phase 3: Parallel implementation

1. Read the briefs file produced by the planner.
2. In a **single assistant turn**, issue N `Task` tool calls to launch N `github-ticket-worker` agents in parallel — one per variant. Each Task call passes:
   - `worktree`: the per-variant worktree path
   - `branch`: the per-variant branch name
   - `brief`: the per-variant brief content (extracted from the briefs file)
   - `swarm-mode`: true (this signals the worker to skip ticket selection, skip the "In Progress" move, and skip branch creation — see `.claude/agents/github-ticket-worker.md`'s swarm-mode section)
3. Each worker implements its variant inside its own worktree, runs local tests, commits, and pushes. Workers report back when each is ready for PR creation.

### Phase 4: Serialize PR creation + aggregate

1. As workers report `ready-to-open-PR`, the orchestrator opens PRs **one at a time** in receipt order. For each:
   - Re-verify `gh auth status` shows the worker bot account.
   - `gh pr create` with the worker-provided title and body.
   - Label the PR with `swarm-variant-{letter}`.
   - If the worker reported a build failure, additionally label `swarm-failed`. The PR is opened regardless — failures are information.
2. Collect all N PR numbers. Each PR triggers a Render preview deploy and a Supabase branch DB automatically via the existing `preview-deploy.yml` plumbing — no manual provisioning needed.
3. Post the aggregate comment on the source issue (see Reference: Aggregate Comment Template). Content includes per-variant PR link, per-variant preview URL, per-variant brief summary, per-variant build status, and any runtime-protected-path flags surfaced by the workers' fork-impact sections.
4. Move the ticket to **In Review** on the configured project board (once — not N times).

### Phase 5 (human, not the command)

The command's job ends at Phase 4. The human:
1. Clicks through the PRs and their preview URLs.
2. Picks one variant, merges its PR via the normal flow.
3. Closes the losing PRs with a comment pointing at the merged winner. A future `/swarm-pick <letter>` command will automate this step (out of scope for v1).

## Usage

```
/swarm 123                       # 3 variants (default)
/swarm 123 --variants 5          # 5 variants (max)
/swarm 123 --variants 4 --yes    # skip cost-prompt and brief-review pauses
/swarm 123 --strategy ux         # hint passed to the planner
```

---

## Reference Material

### Cost Estimation Template

Print this before any work begins. The user can refuse here at zero cost.

```
/swarm cost estimate — issue #{N} ({ticket title})
  Variants:           {N}
  Planner compute:    ~$0.10 (one swarm-planner run)
  Worker compute:     ~$0.30 × {N} = ~${0.30 * N}
  Preview builds:     ~3 build-minutes × {N} = ~{3 * N} build-minutes (Render free tier ceiling ~500/month)
  Human review cost:  {N} PRs to compare side-by-side
  ────────────────────────────────────────
  Estimated total:    ~${0.10 + 0.30 * N} + ~{3 * N} build-minutes

Skip this prompt with --yes.
Proceed? (y/N)
```

Dollar figures are order-of-magnitude estimates, not invoices. Tune to the project's actual model + variant length over time. Build minutes assume a typical Render deploy; tune per-project once real swarm runs land.

### Worktree Layout

```
.claude/worktrees/
  swarm-{N}-a/    # worktree on branch feature/issue-{N}-{slug}-variant-a
  swarm-{N}-b/    # worktree on branch feature/issue-{N}-{slug}-variant-b
  swarm-{N}-c/    # worktree on branch feature/issue-{N}-{slug}-variant-c
```

The `.claude/worktrees/` directory should be gitignored so worktree contents do not pollute `git status` of the primary clone. Worktree cleanup after merge is the human's responsibility in v1 (`git worktree remove .claude/worktrees/swarm-{N}-{letter}`); auto-cleanup is deferred to v2.

### Branch & PR Naming

- Branch: `feature/issue-{N}-{slug}-variant-{letter}` where `{slug}` is ≤ 5 kebab-cased words from the ticket title.
- PR title: prefix with `[swarm-{letter}]` to make the variant set obvious in any PR list. Example: `[swarm-a] feat(ui): onboarding redesign — modal-confirm shape`.
- PR labels: `swarm-variant-{letter}` (always); `swarm-failed` (if the worker reported a red build).

### Account-Switch Serialization (Option A, v1)

Workers run `git push` in parallel — no conflict because each is on a distinct branch in a distinct worktree. PR creation is the only operation that hits the worker bot's auth-switch hook, and it is serialized by the orchestrator (one `gh pr create` at a time). This avoids the account-switch race entirely without requiring per-variant bot accounts (Option B) or hook-level mutexes (Option C). See `docs/plans/SWARM-COMMAND-PLAN.md` § "Handling the Shared Worker Account" for the full rationale.

### Aggregate Comment Template

Post on the source issue at end of Phase 4. Replace placeholders.

```markdown
## /swarm summary — {N} variants

| Variant | PR | Preview | Build | Brief |
|---|---|---|---|---|
| **a** | #{PR_a} | [preview]({preview_url_a}) | {green/red} | {one-line brief summary} |
| **b** | #{PR_b} | [preview]({preview_url_b}) | {green/red} | {one-line brief summary} |
| **c** | #{PR_c} | [preview]({preview_url_c}) | {green/red} | {one-line brief summary} |

**Briefs file:** `reports/swarms/issue-{N}-briefs.md`

**Runtime-protected-path warnings:**
{If any variant touches a runtime-protected path (e.g., scripts/template-sync.sh), list them here with the variant letter and the path. Existing forks won't pick up that variant's fix on /upgrade until #371 (self-upgrade gap) ships. Otherwise: "none."}

**Next step:** Click through the previews to compare. Pick one, merge it. Close the others with a comment pointing at the merged winner (or wait for `/swarm-pick`, landing in v2).
```

### Failure Modes

| Mode | Behavior |
|---|---|
| Planner aborts on DoR fail | Command exits before Phase 2. No worktrees created, no board state changed. |
| User declines cost prompt | Command exits. No work done. |
| Worktree create fails for one variant | Clean up successful worktrees, abort, restore board state. |
| One worker's build fails | That variant's PR is opened with `swarm-failed` label. Other variants proceed normally. Preview deploy still runs — failed builds may still render. |
| All workers' builds fail | Aggregate comment still posts. Ticket still moves to In Review. The human decides whether to merge, debug, or close-all-and-retry. |
| Account-switch race during PR creation | Should not happen given serialization. If it does, the second `gh pr create` will fail with an auth error; the orchestrator must `gh auth status` check, re-switch to the worker bot, and retry that variant's PR. |
| Render preview build fails for a variant | The PR still opens; the preview link in the aggregate comment notes "preview build failed" with the Render logs link. Other variants unaffected. |

### Output Format

Report each phase with a Progress Line, then end your output with a Result Block.

```
→ Pre-flight checks passed
→ Cost estimate confirmed
→ Phase 1: planner produced briefs (reports/swarms/issue-{N}-briefs.md)
→ Human reviewed briefs, proceeded
→ Phase 2: ticket #N moved to In Progress; {N} worktrees created
→ Phase 3: {N} workers launched in parallel
→ Phase 3: variant-a worker reported ready-to-open-PR
→ Phase 3: variant-b worker reported ready-to-open-PR
→ Phase 3: variant-c worker reported ready-to-open-PR
→ Phase 4: PR #M_a created (variant-a) — preview deploying
→ Phase 4: PR #M_b created (variant-b) — preview deploying
→ Phase 4: PR #M_c created (variant-c) — preview deploying
→ Phase 4: aggregate comment posted on #N
→ Phase 4: ticket #N moved to In Review

---

**Result:** Swarm complete
Ticket: #N — <title> — moved to In Review
Variants: 3 (a, b, c)
PRs: #M_a, #M_b, #M_c
Preview URLs: <link a>, <link b>, <link c>
Build status: a=green, b=green, c=red (swarm-failed)
Briefs: reports/swarms/issue-N-briefs.md
Runtime-protected-path warnings: none
Next step: human picks winner from preview comparison
```

If `/swarm` aborts before Phase 4 completes, the Result Block should still print, naming the phase where it aborted and any state that needs manual cleanup (worktrees to remove, ticket to move back).
