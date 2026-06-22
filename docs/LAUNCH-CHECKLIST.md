# M1 Launch Checklist / Go-Live Runbook

The gate for **M1: MVP Launch** ("All P0 features live; first users
onboarded" — see `docs/PRODUCT-ROADMAP.md`). Work top to bottom; the
**Go/No-Go sign-off** at the end is the launch decision. Re-run the
pre-flight before each cohort expansion, not just the first launch.

Project facts referenced below:

- Production URL (current Cloud Run revision): `https://agile-flow-app-heo5ry7rua-uc.a.run.app`
- Supabase project ref: `gnswmcgaztcxslirulwm`
- Repo: https://github.com/vibeacademy/cubrox · Board: https://github.com/orgs/vibeacademy/projects/29

---

## 1. M1 success criteria (from the roadmap)

| Criterion | Status | Where verified |
|-----------|--------|----------------|
| At least one configurable support mode per category (visual reformatting + comprehension), shipped and persisted per user | Met | Reading prefs (epic #5) + comprehension (epic #6), both persisted |
| WCAG-conformant reading surface verified by accessibility audit | Partial | Automated axe gate green (see §3); **human audit still owed** |
| 100,000 lines read/processed within 3 months of launch | Pending | Post-launch metric — `uv run python -m app.scripts.metric` |

---

## 2. Pre-launch gates

### A. Feature completeness

- [ ] All P0 epics closed (#3 Identity, #4 Ingestion, #5 Reading Surface, #6 Comprehension, #7 Metric, #8 A11y). *(All closed as of 2026-06-04.)*
- [ ] Paste + PDF ingestion both work end-to-end against production.
- [ ] Reading preferences persist per user across sessions.
- [ ] Comprehension questions generate, answer/self-check works, and per-passage disable works.

### B. Accessibility

- [ ] CI `a11y` job green on `main` (Playwright + axe; reading surface ×4 variants, login flow, comprehension panel; zero serious/critical WCAG 2.0 A+AA).
- [ ] **Human WCAG audit scheduled or completed** (a stated M1 criterion the automated gate does NOT satisfy — separate engagement). Owner: croissantfella  Date: 2026-06-29.

### C. Production infrastructure

- [ ] Latest `Deploy to Production` run is green (Actions → Deploy to Production).
- [ ] Warm instance confirmed: production runs `--min-instances=1` (OPS-1 #131) — no cold-start auth timeouts.
- [ ] Health probes pass:
  - `curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" <URL>/api/health` → `200`
  - `curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" <URL>/api/health/db` → `200` (DB reachable)
- [ ] Required secrets present (GitHub repo secrets + GCP Secret Manager): GCP auth (WIF provider or SA key), `PRODUCTION_DATABASE_URL`, `ANTHROPIC_API_KEY`, and Secret Manager `supabase-url` / `supabase-anon-key` / `supabase-service-key`.

### D. Auth + email (the "first users onboarded" path)

- [ ] **Real magic-link email delivery verified** — request a sign-in link for a real inbox on production, receive it, click it, land signed-in at `/passages/new`. *(The synthetic monitor uses a password-grant shortcut and does NOT exercise email delivery — this must be checked manually.)*
- [ ] Supabase Auth dashboard (project `gnswmcgaztcxslirulwm`): redirect allowlist includes the production origin + `/auth/callback`; magic-link email template reviewed; sender address acceptable.
- [ ] RLS spot-check (Supabase SQL editor): every public table has RLS on.
  ```sql
  SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname = 'public';
  -- expect rowsecurity = true for passage, preference, reading_event,
  -- comprehension_question_cache, rate_bucket
  ```

### E. Observability + monitoring

- [ ] `Synthetic Auth Monitor` is green on its recent scheduled runs (Actions; hourly at :17). A failure now auto-opens a deduped `[ALERT]` issue (`incident,synthetic-monitor`) — OPS-1 #131.
- [ ] Cloud Logging + Error Reporting reachable for the service (auto-wired by Cloud Run per ADR-004; Sentry deliberately deferred to Phase 2).
- [ ] Someone owns the `[ALERT]` issue label / is watching the monitor for launch week.

### F. Operational safety nets

- [ ] Rollback path known and tested: Actions → **Rollback Production** (`workflow_dispatch`; `revision` optional = previous ready revision, `reason` required).
- [ ] Release tagging understood: pushing a `v*` tag triggers `release.yml` (GitHub Release + changelog).
- [ ] On-call / escalation contact documented for launch week: _____.

---

## 3. First-user onboarding

1. Confirm §2.D (email delivery + redirect allowlist) is checked — this is the gate that most directly affects a new user.
2. Send the cohort the production URL; they sign in via magic link (no password).
3. Smoke-test as a real user: paste a passage → reading view renders with preferences → toggle a preference → comprehension panel loads → answer + reveal → disable/enable comprehension.
4. Confirm a `reading_event` is recorded on passage close (the 100k-line metric depends on it): `uv run python -m app.scripts.metric`.

---

## 4. Go / No-Go sign-off

| Gate | GO requires |
|------|-------------|
| Features (§2.A) | All P0 epics closed; ingestion + reading + comprehension verified on prod |
| Accessibility (§2.B) | Automated gate green AND human audit scheduled (or an explicit, recorded decision to launch before it) |
| Infrastructure (§2.C) | Deploy green, warm instance, health probes 200, secrets present |
| Auth + email (§2.D) | Real magic-link email delivery verified; RLS on; redirect allowlist correct |
| Monitoring (§2.E) | Synthetic monitor green; alerting wired and owned |
| Safety nets (§2.F) | Rollback understood; escalation contact named |

**Decision:** CONDITIONAL — *Launch to first users; human WCAG audit scheduled for 2026-06-29.*  **By:** croissantfella  **Date:** 2026-06-22

CONDITIONAL is valid (e.g. launch to a small cohort with the human WCAG
audit in flight) as long as the condition + owner + date are recorded here.

---

## 5. Incident response (launch week)

- **Auth probe failing** → the monitor opens/updates an `[ALERT]` issue with the run link. A single failure can be a transient blip; recurring failures are a real signal. Check the run log and `<URL>/api/health/db`.
- **Bad revision shipped** → Actions → Rollback Production (`reason` required); it shifts 100% traffic to the previous ready revision and smoke-tests `/api/health`.
- **DB unreachable** (`/api/health/db` non-200) → check Supabase project `gnswmcgaztcxslirulwm` status and `PRODUCTION_DATABASE_URL`; see `docs/PATTERN-LIBRARY.md` for known Cloud Run/Supabase silent failures.
- **Comprehension errors** → non-fatal by design (panel degrades to "unavailable"); check Error Reporting for `comprehension generator failed` WARN logs.

---

## 6. Post-launch watch (toward M2)

- [ ] Track lines processed weekly toward the 100,000-line / 3-month target (`app.scripts.metric`).
- [ ] Watch repeat-use (readers returning week-over-week) — the M2 PMF signal.
- [ ] Re-evaluate deferred items once real users exist: **#99** (per-PR Supabase DB isolation — escalate to P1 the moment real users are on prod), and Sentry (ADR-004 Phase-2 trigger if Cloud Logging grouping proves insufficient).
