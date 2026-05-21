---
description: "Phase 1: Create Product Requirements Document and Roadmap"
---

## Bootstrap Phase 1: Product Definition

Guide the user through a structured questionnaire to define their product. Ask questions ONE AT A TIME and wait for responses before proceeding.

## Instructions for the Agent

**IMPORTANT: Follow this exact question sequence. Do not skip or combine questions.**

For multiple-choice questions, present numbered options and ask the user to respond with the number OR type their own answer.

---

## Pre-Check: Research Artifacts

Before starting the questionnaire, check for these files:
- `docs/MARKET-RESEARCH.md`
- `docs/JOBS-TO-BE-DONE.md`
- `docs/POSITIONING-ANALYSIS.md`

**If any are found**, tell the user which artifacts were found. Example:
> "I found 2 research artifacts: Market Research and JTBD Analysis. I'll pre-populate several questions from these — you can confirm or override each one."

**Pre-population mapping** — for each question below, if the source artifact exists, show the pre-filled answer and ask "Is this correct? (yes to confirm, or type to override)":

| Question | Source Artifact | Section |
|----------|----------------|---------|
| Q0.1 (domain) | MARKET-RESEARCH.md | Product Concept |
| Q0.2 (value proposition) | POSITIONING-ANALYSIS.md | Positioning Statement |
| Q2.1 (problem) | JOBS-TO-BE-DONE.md | Core Job Statement + Pain Points |
| Q2.2 (who has problem) | POSITIONING-ANALYSIS.md | Best-Fit Customer |
| Q2.3 (current solutions) | POSITIONING-ANALYSIS.md | Competitive Alternatives |
| Q3.1 (primary user) | POSITIONING-ANALYSIS.md | Best-Fit Customer |
| Q3.2 (pain point) | JOBS-TO-BE-DONE.md | Underserved Needs |
| Q3.3 (secondary users) | MARKET-RESEARCH.md | Target Audience Insights |
| Q6.1 (competitors) | MARKET-RESEARCH.md | Competitor Analysis |
| Q6.2 (differentiator) | POSITIONING-ANALYSIS.md | Unique Attributes |

**If no artifacts are found**, proceed normally. Mention that running `/research`, `/jtbd`, and `/positioning` first would produce higher-quality results, but they are not required.

---

## Questionnaire

### Section 0: Your Domain

**Question 0.1**
```
What is your product's domain? Describe it in one sentence.

Example: "A fitness studio management platform for boutique gym owners"
Example: "A developer tool for managing database migrations"
Example: "An e-commerce marketplace for handmade crafts"

Your domain:
```

**Question 0.2**
```
What is your core value proposition in one sentence?

Example: "We help boutique gym owners fill every class slot automatically"
Example: "Ship database changes safely with zero-downtime migrations"

Your value proposition:
```

Use the domain and value proposition throughout the generated PRD and
Roadmap to make them specific to the founder's product, not generic
template content.

### Section 1: Product Type & Category

**Question 1.1**
```
What type of product are you building?

1. Web application
2. Mobile app (iOS/Android)
3. Desktop application
4. API/Backend service
5. CLI tool
6. Library/SDK
7. Hardware/IoT
8. Other (please describe)

Enter a number (1-8) or describe your product type:
```

**Question 1.2**
```
What category best describes your product?

1. B2B SaaS (business software)
2. B2C Consumer app
3. Developer tools
4. E-commerce/Marketplace
5. Content/Media platform
6. Productivity/Collaboration
7. Finance/Fintech
8. Healthcare/Wellness
9. Education/EdTech
10. Other (please describe)

Enter a number (1-10) or describe your category:
```

### Section 2: Problem & Vision

**Question 2.1**
```
Describe the problem your product solves in 1-3 sentences:
```

**Question 2.2**
```
Who experiences this problem most acutely?

1. Individual consumers
2. Small businesses (1-50 employees)
3. Mid-market companies (50-500 employees)
4. Enterprise organizations (500+ employees)
5. Developers/Technical users
6. Specific profession (please specify)
7. Other (please describe)

Enter a number (1-7) or describe your target:
```

**Question 2.3**
```
How do people currently solve this problem today?

1. Manual processes (spreadsheets, paper, etc.)
2. Existing software that's inadequate
3. Competitor products
4. They don't - they just live with the pain
5. Cobbled-together workarounds
6. Other (please describe)

Enter a number (1-6) or describe current solutions:
```

### Section 3: Target Users

**Question 3.1**
```
Describe your primary user in one sentence (role, context, goal):

Example: "A small business owner who needs to track inventory without complex software"
```

**Question 3.2**
```
What is the #1 pain point for this user?
```

**Question 3.3**
```
Will there be secondary user types?

1. No, just one user type
2. Yes, there's an admin/manager role
3. Yes, there are multiple distinct user types
4. Yes (please describe)

Enter a number (1-4) or describe:
```

### Section 4: Core Features (MVP)

**Question 4.1**
```
List 3-5 features that MUST be in your MVP (minimum viable product).

Be specific. Example:
- User authentication with email/password
- Dashboard showing key metrics
- Ability to create and edit projects

Your MVP features:
```

**Question 4.2**
```
What features are explicitly OUT OF SCOPE for v1?

(This is just as important as what's in scope)
```

**Question 4.3**
```
What's the ONE thing your product must do exceptionally well?
```

### Section 5: Success Metrics

**Question 5.1**
```
How will you measure success? Select your primary metric:

1. User signups/registrations
2. Daily/Monthly active users
3. Revenue/MRR
4. User retention rate
5. Task completion rate
6. Time saved for users
7. Customer satisfaction (NPS/CSAT)
8. Other (please describe)

Enter a number (1-8) or describe your metric:
```

**Question 5.2**
```
What's your target for this metric in the first 3 months post-launch?

Example: "500 registered users" or "$5k MRR"
```

### Section 6: Competitive Landscape

**Question 6.1**
```
Who are your main competitors or alternatives? (List 1-3)

If none, write "No direct competitors"
```

**Question 6.2**
```
What's your key differentiator? Why would someone choose you over alternatives?
```

### Section 7: Timeline & Constraints

**Question 7.1**
```
When do you need to launch?

1. ASAP (1-2 weeks)
2. 1 month
3. 2-3 months
4. 3-6 months
5. 6+ months
6. No fixed deadline

Enter a number (1-6):
```

**Question 7.2**
```
What are your biggest constraints?

1. Time - need to launch quickly
2. Budget - limited resources
3. Technical - specific tech requirements
4. Regulatory - compliance requirements
5. Team - limited expertise in certain areas
6. Multiple constraints (please list)
7. No major constraints

Enter a number (1-7) or describe:
```

**Question 7.3**
```
Any technical requirements or preferences?

1. Must use specific tech stack (please specify)
2. Must integrate with existing systems (please specify)
3. Must meet specific compliance (SOC2, HIPAA, etc.)
4. No specific requirements
5. Other (please describe)

Enter a number (1-5) or describe:
```

---

## After Collecting All Responses

Once all questions are answered, synthesize the responses into two documents:

1. **docs/PRODUCT-REQUIREMENTS.md** - Structured PRD
2. **docs/PRODUCT-ROADMAP.md** - Phased roadmap

Present a summary to the user and confirm before writing files.

## Output Templates

Use these templates when generating the documents:

### docs/PRODUCT-REQUIREMENTS.md
```markdown
# Product Requirements Document

## Product Overview
- **Type**: [From Q1.1]
- **Category**: [From Q1.2]

## Vision & Problem Statement
[Synthesized from Q2.1]

## Target Audience
- **Primary**: [From Q2.2]
- **User Description**: [From Q3.1]
- **Key Pain Point**: [From Q3.2]
- **Secondary Users**: [From Q3.3]

### Current Solutions
[From Q2.3]

## Features

### MVP (Must Have)
[From Q4.1]

### Out of Scope (v1)
[From Q4.2]

### Core Value Proposition
[From Q4.3]

## Success Metrics
- **Primary Metric**: [From Q5.1]
- **3-Month Target**: [From Q5.2]

## Competitive Analysis
- **Competitors**: [From Q6.1]
- **Differentiator**: [From Q6.2]

## Constraints & Requirements
- **Timeline**: [From Q7.1]
- **Constraints**: [From Q7.2]
- **Technical Requirements**: [From Q7.3]

## Research Foundation
{Include this section only if research artifacts were used}
- [Market Research](./MARKET-RESEARCH.md) {if available}
- [Jobs-to-be-Done Analysis](./JOBS-TO-BE-DONE.md) {if available}
- [Positioning Analysis](./POSITIONING-ANALYSIS.md) {if available}
```

### docs/PRODUCT-ROADMAP.md
```markdown
# Product Roadmap

## Overview
[Timeline summary based on Q7.1]

## Phase 1: MVP
- **Target**: [Based on Q7.1]
- **Goal**: Deliver core value proposition
- **Features**: [From Q4.1]
- **Success Criteria**: [From Q5.1 + Q5.2]

## Phase 2: Iteration
- **Target**: Post-MVP
- **Goal**: Expand based on feedback
- **Features**: TBD based on user feedback

## Constraints & Risks
[From Q7.2 and Q7.3]
```

## Tips for Users

1. **Be specific** - Vague answers lead to vague products
2. **Prioritize ruthlessly** - Everything can't be MVP
3. **Define "not building"** - Scope clarity prevents scope creep
4. **Set measurable goals** - "Better UX" isn't measurable

## Finish Up

The following files were created:
- docs/PRODUCT-REQUIREMENTS.md
- docs/PRODUCT-ROADMAP.md

Would you like me to commit these to a feature branch? (Recommended to keep `main` clean)

If yes, I will:
1. Create branch `docs/bootstrap-product`
2. Commit with message `docs: add product requirements and roadmap`
3. Push and offer to create a PR

## What Happens Next

After completing this questionnaire:
1. Review the generated PRD and Roadmap
2. Run `/bootstrap-architecture` for Phase 2 (Technical Architecture)
3. The System Architect will reference your PRD for technical decisions

### Output Format

Report each phase with a Progress Line, then end with a Result Block:

```
→ Loaded 2 research artifacts
→ Completed questionnaire (25 questions)
→ Generated PRODUCT-REQUIREMENTS.md
→ Generated PRODUCT-ROADMAP.md

---

**Result:** Product definition complete
Documents: docs/PRODUCT-REQUIREMENTS.md, docs/PRODUCT-ROADMAP.md
Features defined: 8 (3 MVP, 5 future)
Next: /bootstrap-architecture
```
