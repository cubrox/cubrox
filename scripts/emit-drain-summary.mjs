#!/usr/bin/env node
// scripts/emit-drain-summary.mjs
//
// Renders the wake-up summary for a /drain run (#131, closes; implements
// the "Wake-up summary (end of run)" section of .claude/commands/drain.md).
// Extended by #189 to add the `mergedNotDeployed` outcome distinct from
// rolledBack (Render deploy never landed → no rollback target).
//
// The drain skill collects per-ticket outcomes into a state JSON during
// its 13-step per-iteration cycle. At the end of the run, this script
// reads that state and emits the canonical Markdown summary that the
// operator wakes up to.
//
// State buckets (per ticket goes into exactly one):
//   shipped[]            — merged + deployed + validated (Done outcome)
//   blocked[]            — could not progress before merge or gate refused
//   rolledBack[]         — merged + deployed but post-deploy validation failed → rollback fired
//   mergedNotDeployed[]  — merged but Render deploy never landed (build_failed
//                          or fetched stuck). No rollback possible (nothing
//                          to revert to at Render's level; previous deploy
//                          is still live). Per #189.
//   skipped[]            — :hot tickets the drain refused, or rate-limited
//                          :reversible tickets that didn't get a turn
//
// Resumption fields (per #204 — Anthropic-API-survivable drain runs):
//   resumedFromInterruption — bool; true means the run was halted (Anthropic
//                          API error, operator session closed, etc.) and
//                          re-entered via `/drain --resume`. Renderer
//                          prepends a banner so the audit trail carries
//                          the discontinuity signal.
//   originalStartTime    — ISO timestamp; the first start (used to compute
//                          the resumption gap)
//   resumedAt            — ISO timestamp; when --resume was invoked
//
// Mid-run state-write fields (written by drain skill at 9 trigger points,
// read by `/drain --resume` to reconcile with real-world state):
//   currentCycle         — 1-indexed cycle number of the last in-flight cycle
//   currentCycleStep     — e.g. "3-in-progress", "7-bridge-dispatch",
//                          "9-poll-render", "10-validation"
//   currentTicket        — {issue, prNumber, mergeSha, bridgeRunId} for
//                          the ticket that was in flight at write time
//   snapshotOrder        — int[]; initial topo-sorted ticket array, used to
//                          determine which tickets still need processing
//   lastWriteTime        — ISO timestamp of the most recent state write
//
// The renderer only reads the resumption fields; the mid-run fields are
// consumed by the skill's resume-reconciliation logic. They are documented
// here as the canonical contract.
//
// Architecture note: the ticket body (#131) mentions extending
// .github/workflows/goal-drain.yml — that workflow was superseded by
// ADR-006 (PR #162) which pivoted /drain to a Claude Code skill at
// .claude/commands/drain.md. This script is wired into the skill's
// "Wake-up summary" step instead.
//
// Usage:
//   node scripts/emit-drain-summary.mjs <state.json>   # prints Markdown to stdout
//   cat state.json | node scripts/emit-drain-summary.mjs -
//
// Optional Slack posting (no-op when env unset, per DoD):
//   DRAIN_SLACK_WEBHOOK_URL=https://hooks.slack.com/... \
//       node scripts/emit-drain-summary.mjs state.json --slack

import { readFileSync } from "node:fs";
import { spawn } from "node:child_process";

const LARGE_DRAIN_THRESHOLD = 20;

/**
 * Pure renderer: takes a drain state object and returns the canonical
 * Markdown wake-up summary.
 *
 * @param {object} state - drain run outcome state (see top-of-file shape)
 * @returns {string} rendered Markdown
 */
export function render(state) {
  const lines = [];
  const shipped = state.shipped ?? [];
  const blocked = state.blocked ?? [];
  const rolledBack = state.rolledBack ?? [];
  const mergedNotDeployed = state.mergedNotDeployed ?? [];
  const skipped = state.skipped ?? [];

  lines.push(`# Drain wake-up summary — ${state.drainId}`);
  lines.push("");
  lines.push(`**Started:** ${state.startTime}`);
  lines.push(`**Ended:** ${state.endTime}`);
  lines.push(`**Duration:** ${formatDuration(state.startTime, state.endTime)}`);
  lines.push("");

  if (state.resumedFromInterruption) {
    const orig = state.originalStartTime ?? state.startTime;
    const resumed = state.resumedAt ?? "(unknown)";
    const gap = state.originalStartTime && state.resumedAt
      ? formatDuration(state.originalStartTime, state.resumedAt)
      : "unknown";
    lines.push(
      `> ⚠ **This drain run was resumed after an interruption.** Originally started at ${orig}; resumed at ${resumed}; gap of ${gap}.`,
    );
    lines.push("");
  }

  if (state.aborted) {
    lines.push(`> ⚠ **Drain aborted early.** Reason: ${state.abortReason ?? "(not provided)"}`);
    lines.push("");
  }

  if (shipped.length > LARGE_DRAIN_THRESHOLD) {
    lines.push(
      `> ⚠ **Large drain — flagged for daytime human review** (${shipped.length} tickets shipped, threshold ${LARGE_DRAIN_THRESHOLD}).`,
    );
    lines.push("");
  }

  lines.push(...renderSection("Tickets shipped", shipped, renderShippedRow, [
    "#",
    "Title",
    "Class",
    "PR",
    "Merge",
    "Audit",
  ]));
  lines.push(...renderSection("Tickets blocked", blocked, renderBlockedRow, [
    "#",
    "Title",
    "Reason",
    "PR",
    "Audit",
  ]));
  lines.push(...renderSection("Tickets rolled back", rolledBack, renderRolledBackRow, [
    "#",
    "Title",
    "PR",
    "Rollback run",
    "Audit",
  ]));
  lines.push(...renderSection(
    "Tickets merged but not deployed",
    mergedNotDeployed,
    renderMergedNotDeployedRow,
    ["#", "Title", "Class", "PR", "Merge", "Reason", "Audit"],
  ));
  lines.push(...renderSection("Tickets skipped", skipped, renderSkippedRow, [
    "#",
    "Title",
    "Reason",
  ]));

  lines.push("## Production status");
  lines.push("");
  const prod = state.productionStatus ?? { healthCheckOk: false };
  lines.push(`- Sentry baseline at start: ${formatBaseline(prod.sentryBaselineBefore)}`);
  lines.push(`- Sentry baseline at end: ${formatBaseline(prod.sentryBaselineAfter)}`);
  lines.push(`- Health check at end of run: ${prod.healthCheckOk ? "OK" : "DEGRADED"}`);
  lines.push(`- Overall: **${productionVerdict(prod)}**`);
  lines.push("");

  lines.push("## Recommended morning actions");
  lines.push("");
  const recs = recommendedActions(state);
  if (recs.length === 0) {
    lines.push("- _No follow-up actions recommended; drain ran clean._");
  } else {
    for (const rec of recs) lines.push(`- [ ] ${rec}`);
  }
  lines.push("");

  return lines.join("\n");
}

function renderSection(heading, items, rowRenderer, columns) {
  const out = [`## ${heading} (${items.length})`, ""];
  if (items.length === 0) {
    out.push(`_None this run._`);
    out.push("");
    return out;
  }
  out.push(`| ${columns.join(" | ")} |`);
  out.push(`|${columns.map(() => "---").join("|")}|`);
  for (const item of items) out.push(rowRenderer(item));
  out.push("");
  return out;
}

function renderShippedRow(t) {
  return `| #${t.number} | ${escapeCell(t.title)} | ${t.safetyClass ?? "-"} | ${prLink(t.prNumber)} | ${shortSha(t.mergeSha)} | ${linkOrDash(t.auditCommentUrl, "comment")} |`;
}

function renderBlockedRow(t) {
  return `| #${t.number} | ${escapeCell(t.title)} | ${escapeCell(t.reason)} | ${prLink(t.prNumber)} | ${linkOrDash(t.auditCommentUrl, "comment")} |`;
}

function renderRolledBackRow(t) {
  return `| #${t.number} | ${escapeCell(t.title)} | ${prLink(t.prNumber)} | ${t.rollbackRunId ?? "-"} | ${linkOrDash(t.auditCommentUrl, "comment")} |`;
}

function renderMergedNotDeployedRow(t) {
  return `| #${t.number} | ${escapeCell(t.title)} | ${t.safetyClass ?? "-"} | ${prLink(t.prNumber)} | ${shortSha(t.mergeSha)} | ${escapeCell(t.reason)} | ${linkOrDash(t.auditCommentUrl, "comment")} |`;
}

function renderSkippedRow(t) {
  return `| #${t.number} | ${escapeCell(t.title)} | ${escapeCell(t.reason)} |`;
}

function escapeCell(s) {
  return String(s ?? "").replaceAll("|", "\\|").replaceAll("\n", " ");
}

function shortSha(sha) {
  if (!sha) return "-";
  return String(sha).slice(0, 7);
}

function prLink(n) {
  return n ? `#${n}` : "-";
}

function linkOrDash(url, label) {
  return url ? `[${label}](${url})` : "-";
}

function formatBaseline(v) {
  return typeof v === "number" ? `${v.toFixed(2)} errors/min` : "n/a";
}

function productionVerdict(prod) {
  if (!prod.healthCheckOk) return "DEGRADED";
  const before = prod.sentryBaselineBefore;
  const after = prod.sentryBaselineAfter;
  if (typeof before === "number" && typeof after === "number" && after > before * 2) {
    return "DEGRADED";
  }
  return "healthy";
}

function formatDuration(start, end) {
  if (!start || !end) return "n/a";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  if (!Number.isFinite(ms) || ms < 0) return "n/a";
  const totalSeconds = Math.floor(ms / 1000);
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = totalSeconds % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

/**
 * Synthesizes the morning-action checklist from drain state.
 * Per #131 + #189 guardrails:
 *  - safety:flagged shipped tickets → release-flip prompt
 *  - blocked tickets → triage prompt
 *  - safety:hot skipped → manual-queue promotion
 *  - rolled-back tickets → investigation prompt
 *  - merged-but-not-deployed → deploy pipeline investigation prompt (per #189)
 *  - aborted runs → abort-cause investigation
 */
export function recommendedActions(state) {
  const out = [];
  for (const t of state.shipped ?? []) {
    if (t.safetyClass === "flagged") {
      out.push(
        `Review release flip for #${t.number} — \`safety:flagged\` shipped dark; toggle the feature flag to **on** after eyeballing production.`,
      );
    }
  }
  for (const t of state.blocked ?? []) {
    out.push(`Triage blocked #${t.number} — ${t.reason ?? "(no reason captured)"}.`);
  }
  for (const t of state.mergedNotDeployed ?? []) {
    out.push(
      `Investigate Render deploy for #${t.number} — merge \`${shortSha(t.mergeSha)}\` reached \`main\` but the deploy did not land; code is on the server but not live. Likely a deploy-pipeline issue (e.g., #194-class auto-deploy reliability), not a code issue.`,
    );
  }
  for (const t of state.rolledBack ?? []) {
    out.push(
      `Investigate rolled-back #${t.number} — rollback run ${t.rollbackRunId ?? "(none)"}; do not re-merge until root-caused.`,
    );
  }
  for (const t of state.skipped ?? []) {
    if (t.reason === "safety:hot") {
      out.push(`Promote #${t.number} to the morning manual queue — \`safety:hot\` was skipped by drain.`);
    }
  }
  if (state.aborted) {
    out.push(
      `Investigate drain abort cause — \`${state.abortReason ?? "unknown"}\` — before invoking \`/drain\` again.`,
    );
  }
  return out;
}

/**
 * Optional Slack posting. No-op (no fetch, no error) when the webhook
 * env var is unset. Errors during posting are caught and reported to
 * stderr so the renderer never fails the drain workflow per the DoD
 * guardrail.
 *
 * @param {string} renderedMarkdown - the full rendered summary
 * @param {object} state - drain state (for the short-form summary)
 * @returns {Promise<{posted: boolean, error?: string}>}
 */
export async function postSlackSummary(renderedMarkdown, state) {
  const webhook = process.env.DRAIN_SLACK_WEBHOOK_URL;
  if (!webhook) return { posted: false };
  const short = shortSummary(state);
  try {
    const res = await fetch(webhook, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ text: short }),
    });
    if (!res.ok) return { posted: false, error: `HTTP ${res.status}` };
    return { posted: true };
  } catch (err) {
    return { posted: false, error: String(err) };
  }
}

function shortSummary(state) {
  const shipped = (state.shipped ?? []).length;
  const blocked = (state.blocked ?? []).length;
  const rolledBack = (state.rolledBack ?? []).length;
  const skipped = (state.skipped ?? []).length;
  return `Drain ${state.drainId}: shipped ${shipped}, blocked ${blocked}, rolled back ${rolledBack}, skipped ${skipped}${state.aborted ? " (ABORTED)" : ""}.`;
}

/**
 * Optional GH-issue/PR posting. Shells to `gh issue comment N --body-file -`
 * with the rendered Markdown on stdin. Reuses the operator's existing `gh`
 * auth — no API token or env var required. Catches all errors so the
 * drain workflow never fails on this per the wake-up summary contract.
 *
 * @param {string} renderedMarkdown - the full rendered summary
 * @param {string|number} issueNumber - the GH issue or PR number to comment on
 * @param {{ spawnImpl?: typeof spawn }} [options] - test seam
 * @returns {Promise<{posted: boolean, error?: string}>}
 */
export async function postIssueComment(renderedMarkdown, issueNumber, options = {}) {
  if (!issueNumber) return { posted: false, error: "missing issueNumber" };
  const spawnImpl = options.spawnImpl ?? spawn;
  return new Promise((resolve) => {
    let stderr = "";
    let child;
    try {
      child = spawnImpl("gh", ["issue", "comment", String(issueNumber), "--body-file", "-"], {
        stdio: ["pipe", "pipe", "pipe"],
      });
    } catch (err) {
      resolve({ posted: false, error: String(err) });
      return;
    }
    child.stderr?.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("error", (err) => {
      resolve({ posted: false, error: String(err) });
    });
    child.on("close", (code) => {
      if (code === 0) resolve({ posted: true });
      else resolve({ posted: false, error: `gh exited ${code}${stderr ? `: ${stderr.trim()}` : ""}` });
    });
    try {
      child.stdin?.write(renderedMarkdown);
      child.stdin?.end();
    } catch (err) {
      resolve({ posted: false, error: String(err) });
    }
  });
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const args = process.argv.slice(2);
  const postIssueIdx = args.indexOf("--post-issue");
  const postIssueValue = postIssueIdx !== -1 ? args[postIssueIdx + 1] : undefined;
  const stateArg = args.find((a, i) =>
    a !== "--slack" &&
    a !== "--post-issue" &&
    !(postIssueIdx !== -1 && i === postIssueIdx + 1),
  );
  if (!stateArg) {
    console.error("Usage: node scripts/emit-drain-summary.mjs <state.json> [--slack] [--post-issue <N>]");
    process.exit(2);
  }
  if (postIssueIdx !== -1 && !postIssueValue) {
    console.error("--post-issue requires an issue/PR number argument");
    process.exit(2);
  }
  const raw = stateArg === "-" ? readFileSync(0, "utf8") : readFileSync(stateArg, "utf8");
  const state = JSON.parse(raw);
  const md = render(state);
  process.stdout.write(md);
  if (args.includes("--slack")) {
    const result = await postSlackSummary(md, state);
    if (result.error) {
      console.error(`[emit-drain-summary] Slack post failed: ${result.error}`);
    } else if (result.posted) {
      console.error("[emit-drain-summary] Slack summary posted.");
    }
  }
  if (postIssueValue) {
    const result = await postIssueComment(md, postIssueValue);
    if (result.error) {
      console.error(`[emit-drain-summary] gh issue comment failed: ${result.error}`);
    } else if (result.posted) {
      console.error(`[emit-drain-summary] Posted to #${postIssueValue}.`);
    }
  }
}
