---
description: Make a go/no-go decision for a release
---

Launch the agile-product-manager agent to evaluate release readiness and make a go/no-go recommendation.

**Usage**: `/release-decision <version-or-release-name>`

**Example**: `/release-decision v2.0`

## What This Command Does

### 1. Product Quality Assessment
- Core functionality complete and tested
- Critical bugs resolved (check for P0/P1 open issues)
- Performance meets acceptable thresholds
- Security review completed (if applicable)

### 2. Market Readiness Assessment
- Target customers can derive value immediately
- Competitive positioning maintained or improved
- Pricing/packaging finalized (if applicable)
- Support team prepared for inquiries

### 3. Business Readiness Assessment
- Success metrics defined and instrumented
- Rollback plan exists if needed
- Legal/compliance requirements met
- Revenue recognition requirements satisfied

### 4. Communication Readiness Assessment
- Release notes prepared
- **Release notes include a "Fork-maintained files you must update" section** (required on every release per `docs/SDLC.md`; reads "None required" if the release introduces no fork-side edits — the absence is made explicit, never omitted)
- Customer communication planned
- Internal stakeholders informed
- Documentation updated

### 5. Risk Assessment
- Identify high/medium/low risks
- Evaluate blast radius if issues occur
- Verify mitigation strategies exist

### 6. Make Recommendation
- **GO**: Proceed with release
- **NO-GO**: Specify what must change, set review date
- **CONDITIONAL GO**: Define gates that must pass before release

## Output Format

```markdown
## Release Decision: <Version/Name>

### Assessment Summary
| Criteria | Status | Notes |
|----------|--------|-------|
| Product Quality | Pass/Warn/Fail | [Details] |
| Market Readiness | Pass/Warn/Fail | [Details] |
| Business Readiness | Pass/Warn/Fail | [Details] |
| Communication | Pass/Warn/Fail | [Details] |

### Open Issues
- P0 bugs: [Count]
- P1 bugs: [Count]
- Blocking issues: [List]

### Risk Assessment
- **High Risks**: [List any blocking concerns]
- **Medium Risks**: [List manageable concerns]
- **Mitigations**: [How risks are addressed]

### Decision: [GO / NO-GO / CONDITIONAL GO]

**Rationale**: [Why this decision]

### If NO-GO:
- Required changes:
  1. [Change 1]
  2. [Change 2]
- Next review date: [Date]

### If CONDITIONAL GO:
- Conditions that must be met:
  - [ ] [Condition 1]
  - [ ] [Condition 2]
- Release authorized when conditions pass

### If GO:
- Recommended release date: [Date]
- Post-release monitoring: [What to watch]
- Success metrics to track: [Metrics]
```

## Who Makes the Decision

The **Product Manager** (agile-product-manager) owns the go/no-go decision.

This is a STRATEGIC decision about:
- Is the product ready for customers?
- Is the market timing right?
- Are the business risks acceptable?

The Product Owner provides input on:
- Delivery completeness
- Technical quality
- Team readiness

### Output Format

End your output with a Result Block:

```
---

**Result:** Release decision — GO
Release: v2.0
Risks: 1 medium (monitoring coverage)
Conditions: none
Recommended date: March 15
```
