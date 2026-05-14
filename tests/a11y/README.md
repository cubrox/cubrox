# Cubrox accessibility tests

Playwright + axe-core harness for WCAG conformance. Production stays
Node-free; Node lives only in this directory.

## Run locally

```bash
cd tests/a11y
npm ci                              # install Playwright + axe-core
npx playwright install chromium     # one-time browser download (~100 MB)
npx playwright test                 # spawns the FastAPI app, runs tests
```

The config's `webServer` block starts `uv run uvicorn app.main:app --port 8080`
from the repo root with `CUBROX_TEST_SEED_ENABLED=true` and a few other
test-only env vars, waits for `/api/health` to return 200, then runs the
specs against `http://localhost:8080`.

## What's here

| File                              | Purpose                                            |
| --------------------------------- | -------------------------------------------------- |
| `package.json`                    | Pinned Playwright + axe-core versions              |
| `playwright.config.ts`            | Chromium project, webServer wiring, env vars       |
| `smoke.spec.ts`                   | Single test against `/api/health` proving setup    |
| `reading_surface.spec.ts`         | Four axe-core tests across preference variants     |
| `fixtures/seed.ts`                | Helper that calls the seed route + sets the cookie |

## Test-only seed router

`reading_surface.spec.ts` provisions an authenticated session + a real
passage on a fresh user via `POST /test/seed-passage-and-login`. This
route is implemented in [app/api/test_seed.py](../../app/api/test_seed.py)
and gated by **two layers**:

1. **Module guard** — `app/api/test_seed.py` raises `RuntimeError` on
   import unless `CUBROX_TEST_SEED_ENABLED=true` OR `ENVIRONMENT=test`.
2. **Registration guard** — `app/main.py` only imports + mounts the
   router when `CUBROX_TEST_SEED_ENABLED=true`. Production Cloud Run
   revisions do not set this var, so the seed router is never loaded.

The Python test suite covers the import guard
(`tests/test_test_seed_guard.py`) and the route's variant matrix
(`tests/test_seed_route.py`), so regressions are caught in pytest
before they ever reach Playwright.

## Preference variants

Each variant in `reading_surface.spec.ts` exercises ONE axis at a time
so an a11y regression points clearly at which preference broke:

| Variant         | Preference row                                | What it tests             |
| --------------- | --------------------------------------------- | ------------------------- |
| `default`       | (no row — falls back to DEFAULT_PREFERENCES)  | The default reading view  |
| `high-contrast` | `{bg: "#1a1a1a", fg: "#e8e8e8"}`              | Dark-mode contrast        |
| `large-text`    | `{size: "28px"}`                              | Low-vision text size      |
| `bionic`        | `{bionic_enabled: true}`                      | The bionicize transform   |

Gate: **zero `serious` or `critical` axe violations** under WCAG 2.0
A+AA rules. `moderate` and `minor` findings are logged to stdout for
future tickets to address but do not fail the build.

## CI integration

A11Y-3 (#26) adds a GitHub Actions job that runs this suite on every PR.
Until that lands, the harness is local-only.

## Why a separate `package.json`

A `package.json` at the repo root would activate the project's CI
`node` job (which currently auto-skips for Python-only repos). Keeping
Node scoped to `tests/a11y/` preserves that auto-skip and signals
clearly that Node isn't a runtime concern for Cubrox.

## One-time devcontainer setup

Playwright's Chromium needs OS-level libraries (glib, gtk, x11, etc.)
that aren't in the default devcontainer. If `npx playwright test` errors
with `libglib-2.0.so.0: cannot open shared object file`:

```bash
sudo env "PATH=$PATH" npx playwright install-deps chromium
```

Installs ~30 apt packages and only needs to run once per container.
