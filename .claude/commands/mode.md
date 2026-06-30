---
description: "Select, list, or inspect the assistant mode for the main Claude session"
---

# /mode — Select or inspect the assistant mode

The main Claude Code session can run in any of several **modes** that bias its tone, verbosity, and explanation depth without changing framework guardrails. See `.claude/modes/README.md` for the registry.

## Activation surface

There are two layers:

- `.claude/settings.json` `"assistantMode"` — **canonical**, version-controlled, team-shared. This is the form recommended for teams.
- `.claude/mode.local` — **personal override**, gitignored. `/mode <name>` writes here. Use this when you want a different mode than the rest of the team without committing the change.

`/mode` is a convenience wrapper around the second layer. To change the team-wide canonical setting, edit `.claude/settings.json` directly.

## Instructions

Parse the argument(s) after `/mode`:

### Case 1 — `/mode` (no argument): print the resolved mode and each layer

1. Read `.claude/settings.json` and extract `"assistantMode"` if present.
2. Read `.claude/mode.local` if it exists; trim whitespace and treat its entire contents as the local override name.
3. Compute the resolved mode using this precedence:
   - If `settings.json` `assistantMode` is set, the resolved mode is that value, **unless** `.claude/mode.local` is also present, in which case `mode.local` overrides it for this machine.
   - Else if `.claude/mode.local` is present, the resolved mode is its contents.
   - Else the resolved mode is `default`.
4. Print the chain explicitly. Example output:

   ```
   settings.json: scaffolded | mode.local: terse-expert | resolved: terse-expert
   ```

   If a layer is unset, print `(unset)` for that layer.

5. End with the footer:

   ```
   Canonical setting: .claude/settings.json "assistantMode". Personal override: .claude/mode.local (gitignored).
   ```

### Case 2 — `/mode list`: print all available modes

1. List every file in `.claude/modes/` matching `*.md` (excluding `README.md`).
2. For each mode, read the first non-empty line under the `## Headline behavior` heading and print:

   ```
   <name>  —  <headline behavior line>
   ```

3. After the list, print the footer:

   ```
   Canonical setting: .claude/settings.json "assistantMode". Personal override: .claude/mode.local (gitignored).
   ```

### Case 3 — `/mode <name>`: set the local override

1. Verify `.claude/modes/<name>.md` exists.
   - If it does not, error with:

     ```
     Unknown mode: <name>. Run `/mode list` to see available modes.
     ```

     and exit.

2. Write the single line `<name>` (no trailing whitespace, no newline-only file) to `.claude/mode.local`.

3. Print exactly:

   ```
   Mode set to <name> via .claude/mode.local (local override of settings.json:assistantMode).
   ```

   This phrasing matters — it tells the operator the change is local-only.

4. Note: this does NOT modify `.claude/settings.json`. If the operator wants a team-shared mode, they edit `settings.json` directly (or remove `.claude/mode.local` first so settings.json wins).

## Notes for the agent

- Do not modify any sub-agent files. Mode selection affects only the main session.
- The new mode takes effect on the next operator message — the current `/mode` invocation's response itself does not need to switch tone mid-flight.
- `.claude/mode.local` must remain gitignored. Do not commit it.
