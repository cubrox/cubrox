import { defineConfig, devices } from "@playwright/test";

/**
 * Only forward an env var to the spawned uvicorn process if it's
 * actually set in our own environment. Used for the SUPABASE_* keys:
 * in CI they come from `$GITHUB_ENV` (set by the "Start local Supabase
 * stack" step), so we forward them explicitly. In local dev, the
 * developer's `.env` file is read directly by pydantic-settings inside
 * the subprocess — forwarding empty strings here would override that
 * `.env` value with `""` and break the config validator.
 */
function envIfSet(...keys: string[]): Record<string, string> {
  const result: Record<string, string> = {};
  for (const key of keys) {
    const value = process.env[key];
    if (value) result[key] = value;
  }
  return result;
}

/**
 * Playwright config for Cubrox accessibility tests.
 *
 * The harness spawns the real FastAPI app via `uv run uvicorn` and
 * waits for /api/health to return 200 before tests start. Tests run in a
 * single chromium project — axe-core's rule set is browser-independent,
 * so multi-browser coverage adds no a11y signal.
 *
 * Production stays Node-free. This config lives under tests/a11y/ only;
 * the repo root has no package.json on purpose.
 */
export default defineConfig({
  testDir: ".",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? "github" : "list",

  use: {
    baseURL: "http://localhost:8080",
    trace: "retain-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  webServer: {
    // Run from repo root so `app.main:app` resolves and uv finds pyproject.toml.
    command: "uv run uvicorn app.main:app --port 8080",
    cwd: "../..",
    url: "http://localhost:8080/api/health",
    timeout: 60_000,
    reuseExistingServer: !process.env.CI,
    stdout: "pipe",
    stderr: "pipe",
    env: {
      // Enable the test-only seed router (POST /test/seed-passage-and-login)
      // used by reading_surface.spec.ts. See app/api/test_seed.py for the
      // module-level guardrail; production Cloud Run never sets this.
      MASTERKEY_TEST_SEED_ENABLED: "true",
      // Harness runs over http://localhost; secure-only cookies would
      // never be sent back to the seed-issued session.
      SESSION_COOKIE_SECURE: "false",
      // Allow the dev-default session secret so seedAndLogin's signed
      // cookies are verifiable. Config's _refuse_sqlite_outside_dev
      // gate trips on "dev-only" outside development/test envs.
      ENVIRONMENT: "test",
      // Supabase backend the seed router talks to + local DATABASE_URL
      // (Postgres inside the local Supabase stack — has the migrated
      // schema, so Passage / Preference INSERTs land in a real table).
      // In CI all four are exported by the "Start local Supabase stack"
      // step in ci.yml. In local dev the developer's .env file is read
      // directly by pydantic-settings (see envIfSet doc above) — we
      // only forward when actually present in process.env to avoid
      // overriding .env with empty strings.
      ...envIfSet(
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_KEY",
        "DATABASE_URL",
      ),
    },
  },
});
