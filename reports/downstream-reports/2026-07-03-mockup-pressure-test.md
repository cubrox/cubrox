---
report_type: downstream-pressure-test
capability: mockup-skill
upstream_repo: vibeacademy/gembaflow
upstream_plan: docs/plans/mockup-skill-downstream-implementation.md
upstream_plan_repo: vibeacademy/gembaflow-meta
downstream_repo: cubrox/masterkey
downstream_commit: 254ce9e0022648163585ac5067d82d1d288ff586
date: 2026-07-03
window: 2026-07-02 to 2026-07-03
verdict: shipped-with-reduced-scope
severity: p2
open_gaps: 5
open_followups: [258, 259, 261]
shipped_pr: 260
shipped_ticket: 256
parent_epic: 255
consumers:
  - agent: content-agent
    repo: vibeacademy/gembaflow-site
    purpose: blog post drafting
  - agent: planning-agent
    repo: vibeacademy/gembaflow-meta
    purpose: hardening and gap-closing work
---

# Downstream Pressure Test — `/mockup` Skill

## Executive summary

`cubrox/masterkey` adopted the upstream `/mockup` skill on 2026-07-03 with a **reduced-scope** implementation. The upstream plan was written for a pre-bootstrap fork and made five assumptions that did not hold on a post-bootstrap downstream fork. All five surfaced during the multi-agent design review before implementation; four were resolved by scope reduction, one is deferred to a follow-up test ticket. The skill ships as a **design-review gate for future major UX changes**, not a bootstrap-chain gate.

**Verdict:** the plan is directionally correct but downstream-fragile in ways that matter for adoption. Upstream should codify a post-bootstrap adoption path and specify concrete consumers for optional artifacts before shipping to the framework.

## The story

The operator picked masterkey over the plan-recommended `vibeacademy/gembaflow-site` deliberately — masterkey is a **forward-designed** fork (PRD-first, product being built), whereas gembaflow-site is **reverse-designed** (existing product surface, mockup would be documentation of what's there). The plan's §8 called this the "sharper test" case for the skill. So we ran it.

The multi-agent flow — system-architect and devops-engineer reviewing in parallel, then agile-backlog-prioritizer grooming, then github-ticket-worker implementing, then pr-reviewer verifying — surfaced the plan's downstream-fragility inside two turns. Both reviewers returned CONDITIONAL. Both flagged the same core issue: the plan's Phase 2 (adding a gate to `bootstrap-architecture`) would either lock out re-runs on masterkey or become dead code, because masterkey has already been bootstrapped.

The reduced-scope implementation resolved that by explicitly refusing the gate coupling. A header comment inside the skill file names the decision so future contributors don't re-litigate it. The skill was implemented, reviewed GO with 0 required changes + 3 non-blocking suggestions, and merged the same day — 24 hours from plan-read to production.

The one surprise: the ticket's Environment Context claimed all four PRD-family docs exist in masterkey. Only `docs/PRODUCT-REQUIREMENTS.md` actually does. The implementation adapted to this on the fly by splitting the preflight into hard-required (PRD + TECHNICAL-ARCHITECTURE) and soft-checked (positioning / JTBD / market / roadmap), rather than shipping a skill that would immediately halt on a valid fork.

## What was tested

- **Capability:** the upstream `/mockup` skill as specified in `vibeacademy/gembaflow-meta:docs/plans/mockup-skill-downstream-implementation.md`
- **Downstream state:** post-bootstrap (masterkey has run `/bootstrap-product` and `/bootstrap-architecture`; TECHNICAL-ARCHITECTURE.md, ADRs, and four bounded contexts exist; ~165 merged PRs)
- **Doc landscape:** `PRODUCT-REQUIREMENTS.md` present; `POSITIONING-ANALYSIS.md`, `JOBS-TO-BE-DONE.md`, `MARKET-RESEARCH.md` absent (masterkey's bootstrap history did not produce them)
- **Generator access:** operator has Claude Pro → Path A (Claude Design) is realistic; Path B (Artifacts) is a natural fallback
- **Content-marketing enrichment:** not installed in masterkey → not exercised
- **Method:** multi-agent orchestration — system-architect + devops-engineer in parallel, then agile-backlog-prioritizer, then github-ticket-worker, then pr-reviewer

## Findings

Numbered for the planning agent's convenience.

### F1 — Plan assumes pre-bootstrap fork; downstream reality is often post-bootstrap

**Severity:** high

The plan's Phase 2 (§9) adds a gate to `.claude/commands/bootstrap-architecture.md` that halts unless `docs/MOCKUP.yaml` exists. On masterkey (already bootstrapped), that gate is either:

- Permanently blocked (blocks future `/bootstrap-architecture` re-runs like the ones `/upgrade` may trigger), or
- Dead code (never fires because architecture already exists)

**Downstream resolution:** dropped Phase 2 entirely; the skill file explicitly documents that future gate coupling must key on **absence of `docs/TECHNICAL-ARCHITECTURE.md`**, NOT absence of a mockup, so re-runs stay idempotent.

**Upstream implication:** plan should either add a post-bootstrap adoption path or restrict itself to pre-bootstrap forks and say so explicitly.

### F2 — Sidecar YAML has no identified consumer

**Severity:** medium

The plan's §7 specifies `docs/MOCKUP.yaml` as "structured design intent for downstream agents to read." In masterkey, all existing agents (`system-architect`, `agile-product-manager`, `github-ticket-worker`) already read `docs/TECHNICAL-ARCHITECTURE.md`, PRD, and per-context ubiquitous language. Adding YAML makes it a fifth source of truth competing with four established ones — a canonical `CLAUDE.md rule #7` (one canonical location per fact) violation.

**Downstream resolution:** dropped the YAML sidecar.

**Upstream implication:** name the concrete consumer of the YAML before shipping it. If no consumer exists, drop it. If a consumer is planned, sequence the consumer's implementation before the YAML's producer.

### F3 — Ticket's stated inputs may not match downstream reality

**Severity:** medium (downstream-specific, but generalizable)

The ticket derived from the plan claimed all four PRD-family docs exist "per `/bootstrap-product` having run." Empirically, only PRD did. This is a general downstream-drift class: a plan authored against an assumed-clean bootstrap state does not survive contact with forks whose bootstrap history diverged.

**Downstream resolution:** split preflight into hard (PRD + TECHNICAL-ARCHITECTURE) and soft (four PRD-family docs); soft misses log gaps but do not halt.

**Upstream implication:** the hard/soft preflight discipline is a **pattern worth codifying upstream**. Any skill that consumes bootstrap-time doc outputs should specify per-input `required` vs `optional` and degrade gracefully.

### F4 — Path C (starter-template hand-authoring) has no realistic consumer

**Severity:** low

Path C exists for operators with no Claude access at all. In practice, anyone running the framework is a Claude user (the framework depends on Claude Code). The path adds surface area with no consumer.

**Downstream resolution:** dropped Path C.

**Upstream implication:** upstream may want to keep Path C for pedagogical completeness (showing operators what the mockup looks like conceptually without depending on Claude Design specifically), but should mark it clearly as pedagogical rather than adoption-ready.

### F5 — No testing pattern for human-in-the-loop skills

**Severity:** medium

The DoD for the implementation ticket required "preflight failure path is exercised at least once." For a skill file (Markdown instructions to an agent, not runtime code), "exercise" is ambiguous. The team resolved this by treating the halt behavior as inspectable rather than executed — the reviewer accepted this as proportionate, but flagged it as a suggestion.

**Downstream resolution:** filed as follow-up #259 (halt-path smoke check with fixture-based renames).

**Upstream implication:** the framework needs a **testing convention for skill files**: what does "verify a skill works" mean when the skill is instructions to an agent? Options include fixture-based tests that check the skill's emitted output shape, agent-driven smoke tests, or explicit "skills are not tested; PRs are the review gate" documentation.

## What worked

Worth calling out separately — the content agent may find quotable material here.

- **Multi-agent orchestration surfaced downstream-fragility in two turns.** System-architect and devops-engineer, both instructed to consider masterkey specifically, produced CONDITIONAL verdicts naming the same core gap (post-bootstrap gate coupling) from independent angles. Adversarial verification without duplication.
- **Reduced-scope discipline shipped a leaner skill.** The plan proposed 4 phases; masterkey shipped Phase 1 only, with Phases 2-4 explicitly deferred. The follow-up tickets (#258, #259, #261) preserve the design intent without carrying its overhead into v1.
- **Preflight halt semantics worked cleanly.** The hard/soft split kept the skill usable on a fork with incomplete doc coverage, without silently degrading behavior. The halt path is inspectable in-file.
- **Path A + Path B degradation is genuine.** Both paths are documented as first-class; neither is a hidden dependency. Operators without Claude Design access get a working fallback.
- **PR-link SOP applied cleanly.** Every child ticket (#256) and the parent epic (#255) got explicit PR-link comments on merge, per the fork's established convention.

## Quotable takeaways

For content agents drafting a blog post:

- "The mockup exists to be reacted to, then discarded." — the throwaway discipline as the whole point
- "The gate is human-facing, not agent-facing." — mockup is context engineering applied to the supervisor's attention budget, not the agent's
- "The mockup can end up ratifying ossification instead of challenging it." — the failure mode of a poorly-anchored brief
- "Cheap gate before expensive-to-reverse decisions." — the core value proposition
- "Adversarial verification without duplication." — what the parallel architect + devops review actually delivered
- "24 hours from plan-read to production." — the speed of the multi-agent path when scope is well-reduced
- "A plan authored against an assumed-clean bootstrap state does not survive contact with forks whose bootstrap history diverged." — the general lesson from F3

## Hardening candidates

Numbered upstream ticket candidates. All would be filed against `vibeacademy/gembaflow`.

### H1 — Post-bootstrap adoption path in the plan

**Type:** plan revision
**Scope:** documentation
**Effort:** S (1-4h)

Add a Phase 0 to the plan naming what "adopt `/mockup` on an already-bootstrapped fork" looks like. Options: no gate coupling (masterkey's choice), gate keyed on architecture absence, or explicit refusal (post-bootstrap forks skip the skill). Ships as a plan amendment, not code.

### H2 — Hard/soft preflight discipline codified

**Type:** framework convention
**Scope:** upstream `CLAUDE.md` + all bootstrap-emitting skills
**Effort:** M (0.5-2d)

Codify the hard-required vs soft-optional input pattern the downstream discovered. Every skill that consumes bootstrap-time doc outputs should declare per-input `required` vs `optional` in its preflight, and degrade gracefully when optional inputs are absent.

### H3 — Sidecar-consumer sequencing rule

**Type:** framework convention
**Scope:** meta-planning
**Effort:** S (1-4h)

Add a rule to the upstream plan-review checklist: any planned artifact (YAML, JSON, sidecar file) must name its concrete consumer(s) in the same plan. If no consumer, drop the artifact. If a consumer is planned, sequence the consumer's implementation before the producer.

### H4 — Skill-file testing convention

**Type:** framework convention
**Scope:** upstream `CLAUDE.md` + `docs/AGENT-OUTPUT-STANDARD.md`
**Effort:** M (0.5-2d)

Define what "test a skill file" means. Options: fixture-based halt-path smoke tests (masterkey's #259 will produce a candidate pattern), agent-driven end-to-end tests, or explicit "skills are validated at PR time only" documentation. Downstream forks are currently guessing.

### H5 — Path C pedagogical vs adoption-ready labeling

**Type:** plan clarification
**Scope:** documentation
**Effort:** XS (< 1h)

Label Path C as pedagogical (for operators to see the mockup shape) rather than adoption-ready. This resolves the ambiguity that led masterkey to drop it entirely.

## Open downstream follow-ups

Three tickets remain open in masterkey's backlog. Their disposition is informative for upstream:

- **#258** — ADR-008 recording the retrofit reframing. Downstream-specific; will not surface upstream.
- **#259** — halt-path fixture test. Generalizable; will feed H4.
- **#261** — replace local absolute path in the skill file with an upstream GitHub URL. Downstream hygiene; will not surface upstream but flags a pattern worth checking in the plan authorship template (avoid hardcoded local paths in shipped artifacts).

## Artifacts and cross-references

- **Shipped PR:** https://github.com/cubrox/masterkey/pull/260 (merged 2026-07-03T11:27:29Z, commit `254ce9e`)
- **Shipped skill file:** `.claude/commands/mockup.md`
- **Dry-run output:** `docs/mockups/test-mockup-2026-07-02.html`
- **Parent epic:** https://github.com/cubrox/masterkey/issues/255
- **Implementation ticket:** https://github.com/cubrox/masterkey/issues/256
- **Review comment on #260:** GO verdict from `va-reviewer` (0 required changes, 3 suggestions)
- **Follow-ups:** #258 (ADR), #259 (halt-path test), #261 (path portability)
- **Upstream plan:** `vibeacademy/gembaflow-meta:docs/plans/mockup-skill-downstream-implementation.md`
- **Related upstream historical plans:** `vibeacademy/gembaflow-meta:docs/plans/mockup-feature-spec.md` (2026-06-04, PM), `docs/plans/mockup-implementation-plan.md` (2026-06-04, framework-architect)
- **Reticle precedent:** `feature-x/reticle:docs/MOCKUP.html` (empirical single-file shape the plan was designed against)

## Metadata

- **Downstream fork:** `cubrox/masterkey` @ `254ce9e`
- **Framework version at test time:** gembaflow v1.5.0 (see `.gembaflow-version`)
- **Operator mode:** solo-with-worker-account (`tck517` as worker on solo mode)
- **MCP servers active:** `memory`, `supabase`, `sequential-thinking`
- **Session type:** continuation from prior session compaction; work performed 2026-07-02 → 2026-07-03
- **Report author:** github-ticket-worker (this session), reviewed by no independent agent (single-author downstream synthesis)
