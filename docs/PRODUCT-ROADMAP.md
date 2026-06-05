# Product Roadmap

## Overview

This roadmap delivers a tailored reading experience for neurodivergent
readers of Baha'i writings, launching in a 3–6 month window
(target: 2026-08 to 2026-11). Phase 1 proves the core thesis — that a
configurable reading-support toolkit increases the volume of text people
actually read. Subsequent phases expand support modes and corpus reach
based on what real users tell us works.

## Phase 1: MVP

- **Target**: 2026-08 to 2026-11 (3–6 months from 2026-05-01)
- **Goal**: Deliver the core value proposition — make text easier to read
  and understand — to a first cohort of neurodivergent readers.
- **Status (as of 2026-06-05)**: all P0 features shipped to production; the
  app is live. Launch is now gated on the operator pre-flight, not feature
  work — see `docs/LAUNCH-CHECKLIST.md`.

### Features

| Feature                                                          | Priority | Status  |
|------------------------------------------------------------------|----------|---------|
| Text passage input (paste/type)                                  | P0       | Shipped |
| Document upload (PDF)                                            | P0       | Shipped |
| Reading-support toolkit (visual reformatting + comprehension Qs) | P0       | Shipped |
| Email login                                                      | P0       | Shipped |
| Saved per-user preferences                                       | P0       | Shipped |

### Success Criteria

- [ ] 100,000 lines of text read/processed through the product within
      3 months of launch. *(Post-launch metric; instrumented — `app.scripts.metric`.)*
- [x] At least one configurable support mode per category (visual
      reformatting + comprehension checks) shipped and persisted per user.
- [ ] WCAG-conformant reading surface verified by accessibility audit.
      *(Automated axe gate green across the reading surface, login, and
      comprehension panel; the separate human audit is still owed — see
      `docs/LAUNCH-CHECKLIST.md` §2.B.)*

## Phase 2: Iteration

- **Target**: 1–2 months post-MVP launch
- **Goal**: Expand the support toolkit based on which modes actual readers
  reach for, and close gaps the first cohort surfaces.

### Features

| Feature                                                       | Priority | Status  |
|---------------------------------------------------------------|----------|---------|
| Additional reading-support modes (driven by Phase 1 feedback) | TBD      | Backlog |
| Improved PDF ingestion fidelity                               | TBD      | Backlog |
| Reader analytics — track which modes correlate with retention | TBD      | Backlog |

### Success Criteria

- [ ] Repeat-use rate (readers returning week-over-week) trending up.
- [ ] At least one new support mode shipped from real user demand.

## Phase 3: Growth

- **Target**: 3–6 months post-launch
- **Goal**: Scale beyond the initial cohort and broaden corpus access.

### Features

| Feature                                                  | Priority | Status  |
|----------------------------------------------------------|----------|---------|
| Curated Baha'i writings library (in-product, no upload)  | TBD      | Backlog |
| Mobile-optimized reading surface                         | TBD      | Backlog |
| Internationalization (deferred from v1)                  | TBD      | Backlog |

## Milestone Definitions

| Milestone               | Criteria                                                              | Target Date     |
|-------------------------|-----------------------------------------------------------------------|-----------------|
| M1: MVP Launch          | All P0 features live; first users onboarded                           | 2026-08 / 2026-11 |
| M2: Product-Market Fit  | 100,000 lines processed; week-over-week repeat use                    | +3 months       |
| M3: Growth              | Curated library live; mobile reading surface; i18n groundwork started | +6–9 months     |

## Constraints and Risks

| Risk                                                              | Phase | Mitigation                                                                  |
|-------------------------------------------------------------------|-------|-----------------------------------------------------------------------------|
| Readability needs vary widely across users                        | 1     | Modular support toolkit + per-user saved preferences; diverse beta cohort   |
| Comprehension-question quality on sacred/poetic text              | 1     | Source-grounded prompts; user can disable; tighten in Phase 2 from feedback |
| PDF ingestion produces messy text that defeats reading aids       | 1     | Validate parser early on representative docs; surface errors clearly        |
| Scope creep into i18n / non-Baha'i corpora before MVP is proven   | 1, 2  | i18n explicitly out of scope for v1; broaden corpus only after M2           |

## Dependencies

```text
Phase 1: MVP (P0 features, accessibility audit)
    |
    v
Phase 2: Iteration (requires real-user usage data from Phase 1)
    |
    v
Phase 3: Growth (requires product-market fit signal from Phase 2)
```

## Revision History

| Date       | Change                                       | Author       |
|------------|----------------------------------------------|--------------|
| 2026-05-01 | Initial roadmap from /bootstrap-product run  | cubrox       |
