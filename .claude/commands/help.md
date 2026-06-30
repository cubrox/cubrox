---
description: "List available slash commands with a one-line description of each"
---

# /help — Available commands

Prints the available Gemba Flow slash commands with a one-line description of each.

## Instructions

Print the following table to the operator.

| Command | Description |
|---------|-------------|
| `/groom-backlog` | Prioritize tickets, populate Ready column |
| `/work-ticket` | Pick up next ticket and implement |
| `/review-pr` | Review PRs in In Review column |
| `/review-to-tickets` | Convert review Suggestions into Backlog tickets |
| `/swarm` | Run N parallel implementations of one ticket |
| `/check-milestone` | Check milestone progress |
| `/sprint-status` | Board health overview |
| `/research` | Market research with web search |
| `/jtbd` | Jobs-to-be-Done user analysis |
| `/positioning` | Product positioning analysis |
| `/evaluate-feature` | Evaluate feature for strategic fit |
| `/release-decision` | Go/no-go decision |
| `/test-feature` | Create test plan and validate |
| `/architect-review` | Architectural guidance |
| `/lock-scope` | Lock MVP scope |
| `/doctor` | Environment health check (local + remote) |
| `/upgrade` | Upgrade framework files to latest release |
| `/mode` | Select, list, or inspect the assistant mode for the main session. Available modes ship in `.claude/modes/` — `default`, `scaffolded`, `socratic`, `terse-expert`, `shipping-coach`. |
| `/report-issue` | Report a bug back to the upstream framework |
| `/quick-fix` | Skip ticket ceremony for <20-line non-behavioral fixes |
| `/create-ticket` | File a new ticket on the project board |
| `/log-session` | Capture a session journal |
| `/eli5` | Plain-language summary comment on a ticket or PR |

After the table, print one line:

```
For details on a specific command, open .claude/commands/<name>.md.
```
