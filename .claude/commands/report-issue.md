---
description: "Report a bug or issue from this fork back to the upstream Gemba Flow repo"
---

# /report-issue — Report an Issue to Upstream

File a structured bug report or feedback item against the upstream Gemba Flow repo
from this downstream fork. The report is delivered as a GitHub issue with a
`downstream-report` label so upstream maintainers can triage it automatically.

**Severity vs priority:** the `severity` field you'll be prompted for (p1/p2/p3)
is recorded in the report's YAML front matter, not applied as a repo label on
the upstream issue. **Priority is canonical on the upstream project board's
Priority field**, not on the issue itself — see `docs/TICKET-FORMAT.md`. If the
new issue belongs on the board, the upstream maintainer (or you, if you have
project access) adds it there and sets the Priority field.

## When to use this command

Use `/report-issue` when you have found:
- A bug in a framework script, workflow, or slash command
- A workflow that does not work as documented
- Missing or incorrect documentation
- A pattern or architectural suggestion

Do **not** use this for issues specific to your fork's customisations (those are local
issues you own). Use it for problems that exist in the upstream framework files.

## Instructions

1. **Verify `.gembaflow-version` exists**. If the file is missing, run `/upgrade`
   first to initialise the metadata file.

2. **Gather context before running the script**. Before invoking, note:
   - What went wrong (be specific)
   - Severity: p1 (critical, blocks everyone), p2 (significant, workaround exists),
     p3 (minor or improvement)
   - Component: You'll be prompted to select from available components in a two-step process

3. **Validate severity input**. Before running the script, ensure the severity is one of the valid values: p1, p2, or p3. If invalid, return error: "Invalid severity. Valid options: p1, p2, p3"

4. **Run the report script**:

   ```bash
   bash scripts/report-issue.sh
   ```

   The script will:
   - Read .gembaflow-version to identify the target repo and version
   - Capture fork_commit (current HEAD) and upstream_version automatically
   - Prompt for severity, component, and title
   - Open your $EDITOR (or use inline input) for the description
   - Submit via gh issue create with label downstream-report
   - Fall back to clipboard copy + pre-filled browser URL if gh access is denied

5. **Fill in the description**. Provide:
   - Description: what is happening and why it is a problem
   - Steps to Reproduce: numbered list, minimal and specific
   - Expected Behaviour: what should happen
   - Actual Behaviour: what actually happens
   - Error Output: paste relevant terminal output
   - Context: workshop date, participant count, track

6. **Handle the exit code**:

   | Code | Meaning | Action |
   |------|---------|--------|
   | 0 | Success - issue filed or fallback URL provided | Report the issue URL to the user |
   | 1 | Error - missing config or invalid input | Show the error message and fix the root cause |

7. **If gh access is denied** (fallback path):

   The script will save the report to .gembaflow-reports/report-<timestamp>.md,
   copy the body to clipboard if available, and print a pre-filled GitHub issue URL.

   Tell the user:
   > The report was saved locally and a pre-filled GitHub issue URL was generated.
   > Open the URL in your browser to submit it manually.

## Non-interactive mode (CI / automation)

```bash
bash scripts/report-issue.sh \
  --non-interactive \
  --severity p2 \
  --component provisioning \
  --title "Provision script fails when roster has special characters"
```

## Test / QE flags: `--dry-run` and `--fixture-repo`

Two flags exist to keep the upstream tracker clean while iterating on this
command or running QE checks. They never combine — pick one per invocation.

| Flag | Use when | Behavior |
|------|----------|----------|
| `--dry-run` | Iterating on the command itself, or any QE pass that should not file a real issue. | Generates the report file under `.gembaflow-reports/`, prints the issue preview, and exits 0. **Zero `api.github.com` calls** — safe to run in tight loops. |
| `--fixture-repo <slug>` | You actually want an issue created, but against a test repo (your own fork or a dedicated fixture), not the upstream. | Same flow as default mode, but `gh issue create --repo <slug>` is invoked instead of the upstream from `.gembaflow-version`. Slug must match `org/name`. |

`--dry-run` and `--fixture-repo` are **mutually exclusive**: the script exits 1
with a clear error if both are passed. Use `--dry-run` when you want to
preview without touching anyone's tracker; use `--fixture-repo` when you want
to exercise the real gh path against a repo you own.

The `--dry-run` flag is the supported tool for QE re-runs that previously
polluted upstream. If you want a recorded fixture issue (e.g. to test the
auto-triage workflow), use `--fixture-repo va-worker/<your-fixture-repo>`.

## Report format reference

The script generates a YAML front-matter Markdown file in .gembaflow-reports/:

```
---
agile_flow_report: true
upstream: https://github.com/vibeacademy/gembaflow
fork_commit: abc123def456...
upstream_version: v2.1.0 @ def789abc012
severity: p2
component: provisioning
title: "Provision script fails when roster has special characters"
---
```

The upstream field is read automatically from .gembaflow-version.

## Output Format

End your response with a Result Block:

```
---

**Result:** Issue filed
URL: https://github.com/vibeacademy/gembaflow/issues/42
Severity: p2
Component: provisioning
Report: .gembaflow-reports/report-20260508-143022.md
```

Or if fallback was used:

```
---

**Result:** Report saved (manual submission required)
Report: .gembaflow-reports/report-20260508-143022.md
Browser URL: https://github.com/vibeacademy/gembaflow/issues/new?...
```

Or on error:

```
---

**Result:** Error
Reason: .gembaflow-version not found - run /upgrade first
```
