import { defineConfig, devices } from "@playwright/test";

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
      CUBROX_TEST_SEED_ENABLED: "true",
      // Harness runs over http://localhost; secure-only cookies would
      // never be sent back to the seed-issued session.
      SESSION_COOKIE_SECURE: "false",
      // Allow the dev-default session secret so seedAndLogin's signed
      // cookies are verifiable. Config's _refuse_sqlite_outside_dev
      // gate trips on "dev-only" outside development/test envs.
      ENVIRONMENT: "test",
    },
  },
});
