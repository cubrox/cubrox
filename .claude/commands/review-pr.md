---
description: Review pull requests in the In Review column
---

Launch the pr-reviewer agent to review pull requests and provide go/no-go recommendations.

## Critical Rules

1. **Never merge PRs** — human reviewer makes the final merge decision
2. **Never approve PRs on GitHub** — provide recommendation only
3. **Automatic NO-GO for red flags** — see Red Flags section below
4. **Review ALL changed files** — not just the diff summary

## Workflow

1. **Find PR** — Query In Review column or use provided PR number
2. **Check CI** — Verify all checks pass before starting review
3. **Review Code** — Follow the review template below
4. **Post Assessment** — Comment on the PR with GO/NO-GO recommendation

## Usage

```
/review-pr
/review-pr #234
```

---

## Reference Material

### Review Template

Post a structured review comment using this format:

```markdown
## PR Review — #<number>

### Requirements
- [ ] Acceptance criteria from linked issue are met
- [ ] Feature works end-to-end as described
- [ ] No scope creep beyond ticket requirements

### Code Quality
- [ ] Follows existing patterns and conventions
- [ ] No unnecessary complexity or over-engineering
- [ ] Error handling is appropriate (not excessive)
- [ ] No hardcoded values that should be configurable

### Testing
- [ ] Tests cover acceptance criteria
- [ ] Tests are meaningful (not just asserting true)
- [ ] Edge cases considered where appropriate
- [ ] All tests pass in CI

### Tracking Issue Hygiene
- [ ] Any tracking issue linked in the PR has a close-out comment
- [ ] Tracking issue is closed, or explicitly marked for close-on-merge

### Security
- [ ] No hardcoded secrets, tokens, or credentials
- [ ] No SQL injection, XSS, or command injection vectors
- [ ] Dependencies are from trusted sources
- [ ] Sensitive data is not logged or exposed

### Recommendation
**GO** / **NO-GO**

[Rationale — 1-3 sentences explaining the decision]

### Required Changes (if NO-GO)
1. [Specific change needed]

### Suggestions (non-blocking)
- [Optional improvements]
```

### Red Flags — Automatic NO-GO

Any of these findings result in an immediate NO-GO recommendation:

| Red Flag | Why |
|----------|-----|
| Hardcoded secrets or API keys | Security — credentials must never be in source |
| Failing CI checks | Quality — all checks must pass before review |
| Linked tracking issue lacks close-out comment/closure plan | Process — unresolved coordination context before merge |
| SQL injection or command injection | Security — OWASP Top 10 vulnerability |
| Disabled security controls | Safety — `--no-verify`, disabled hooks, bypassed auth |
| Direct commits to main | Process — all changes go through feature branches |
| Missing tests for new functionality | Quality — untested code is unverifiable |
| Type errors or unresolved imports | Quality — code does not compile/run correctly |

### When to Request Changes vs Comment

| Action | When |
|--------|------|
| **Request Changes (NO-GO)** | Red flags present, acceptance criteria not met, tests missing or failing, security issues |
| **Comment (GO with suggestions)** | Minor style preferences, optional refactoring ideas, performance suggestions for non-critical paths, documentation improvements |

The threshold: if the code would cause problems in production or violates project standards, it's a NO-GO. If it works correctly but could be slightly better, it's a GO with suggestions.

### Escalation Criteria

Escalate to the human reviewer with a detailed comment when:

- **Architectural concerns** — PR introduces patterns that conflict with existing architecture
- **Scope questions** — Changes go significantly beyond the ticket scope
- **Ambiguous requirements** — Acceptance criteria are unclear and the implementation could be interpreted multiple ways
- **Cross-cutting impact** — Changes affect shared infrastructure, CI/CD, or security controls
- **Disagreement with approach** — The implementation works but a fundamentally different approach would be better

**Escalation format**: Start the comment with `⚠️ ESCALATION` and explain the concern, the options, and a recommendation.

### Output Format

End your output with a Result Block:

```
---

**Result:** Review posted — GO
PR: #108 — feat: add health check endpoint
Required changes: 0
Suggestions: 2 (non-blocking)
```
