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
from the repo root, waits for `/api/health` to return 200, then runs
the tests against `http://localhost:8080`.

## What's here

| File                       | Purpose                                          |
| -------------------------- | ------------------------------------------------ |
| `package.json`             | Pinned Playwright + axe-core versions            |
| `playwright.config.ts`     | Chromium project, webServer wiring, base URL     |
| `smoke.spec.ts`            | Single test against `/api/health` proving setup  |

## What's coming

This ticket (#24, A11Y-1) is harness-only. Real accessibility assertions
land in:

- **A11Y-2 (#25)** — axe-core checks across the reading surface and
  sidebar for every preference combination (font, size, contrast,
  spacing, column width).
- **A11Y-3 (#26)** — CI job in `.github/workflows/` so every PR fails
  if axe-core finds a new violation.

## Why a separate `package.json`

A `package.json` at the repo root would activate the project's CI
`node` job (which currently auto-skips for Python-only repos). Keeping
Node scoped to `tests/a11y/` preserves that auto-skip and signals
clearly that Node isn't a runtime concern for Cubrox.
