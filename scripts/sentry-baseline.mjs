#!/usr/bin/env node
// provider: sentry-only
// scripts/sentry-baseline.mjs
//
// Measures the 30-day rolling baseline error rate from Sentry.
// Consumed by the `/goal deploy` (#118) and `/goal drain` (#126)
// validation workflows as a pre-deploy reference.
//
// Output: a single JSON line on stdout —
//   { baseline_errors_per_min: <number|null>, source: "sentry"|"unavailable",
//     reason?: "...", window_days: 30, sample_count: <number> }
//
// Exit codes: 0 always. If Sentry is unreachable or unconfigured, we emit
// source="unavailable" and let the caller decide whether to skip the gate
// per devops review item 3 in reports/deployment-architecture-2026-06-03.md §10.
//
// API contract (Sentry project stats):
//   GET ${SENTRY_API_URL}/projects/${SENTRY_ORG}/${SENTRY_PROJECT}/stats/
//       ?stat=received&resolution=1h&since=<unix>&until=<unix>
//   Bearer ${SENTRY_AUTH_TOKEN}
// Response: array of [unix_seconds, count] tuples — one per hour bucket.

export const WINDOW_DAYS = 30;
export const RESOLUTION = "1h";
const RESOLUTION_SECONDS = 60 * 60;
const MINUTES_PER_BUCKET = RESOLUTION_SECONDS / 60;

function readConfig(env) {
  const apiUrl = env.SENTRY_API_URL;
  const authToken = env.SENTRY_AUTH_TOKEN;
  const org = env.SENTRY_ORG;
  const project = env.SENTRY_PROJECT;
  const missing = [];
  if (!apiUrl) missing.push("SENTRY_API_URL");
  if (!authToken) missing.push("SENTRY_AUTH_TOKEN");
  if (!org) missing.push("SENTRY_ORG");
  if (!project) missing.push("SENTRY_PROJECT");
  if (missing.length > 0) {
    return { configured: false, missing };
  }
  return { configured: true, apiUrl, authToken, org, project };
}

function median(values) {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[mid - 1] + sorted[mid]) / 2
    : sorted[mid];
}

/**
 * @param {{
 *   now?: number,
 *   env?: Record<string, string | undefined>,
 *   fetchImpl?: typeof fetch,
 * }} [options]
 */
export async function measureBaseline({
  now = Date.now(),
  env = process.env,
  fetchImpl = globalThis.fetch,
} = {}) {
  const config = readConfig(env);
  if (!config.configured) {
    return {
      baseline_errors_per_min: null,
      source: "unavailable",
      reason: `missing env: ${config.missing.join(", ")}`,
      window_days: WINDOW_DAYS,
      sample_count: 0,
    };
  }

  const until = Math.floor(now / 1000);
  const since = until - WINDOW_DAYS * 24 * 60 * 60;
  const url = `${config.apiUrl.replace(/\/$/, "")}/projects/${config.org}/${config.project}/stats/?stat=received&resolution=${RESOLUTION}&since=${since}&until=${until}`;

  try {
    const response = await fetchImpl(url, {
      headers: { Authorization: `Bearer ${config.authToken}` },
    });
    if (!response.ok) {
      return {
        baseline_errors_per_min: null,
        source: "unavailable",
        reason: `HTTP ${response.status}`,
        window_days: WINDOW_DAYS,
        sample_count: 0,
      };
    }
    const series = await response.json();
    const perMinute = series.map(([, count]) => count / MINUTES_PER_BUCKET);
    return {
      baseline_errors_per_min: median(perMinute),
      source: "sentry",
      window_days: WINDOW_DAYS,
      sample_count: perMinute.length,
    };
  } catch (err) {
    return {
      baseline_errors_per_min: null,
      source: "unavailable",
      reason: `fetch failed: ${err instanceof Error ? err.message : String(err)}`,
      window_days: WINDOW_DAYS,
      sample_count: 0,
    };
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const result = await measureBaseline();
  if (result.source === "unavailable") {
    console.error(`sentry-baseline: ${result.reason}`);
  }
  console.log(JSON.stringify(result));
}
