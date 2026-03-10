# Decisions Reference

Guide for creating, documenting, and classifying project decisions.

---

## Record Template

### Filename Format

`decision-{NNN}-{slug}.md`

Examples: `decision-001-oauth-library.md`, `decision-002-database-choice.md`

### Template

```markdown
---
id: DEC-{NNN}
title: [Short descriptive title]
status: draft
category: [architecture | technology | process | scope | methodology | vendor]
created: YYYY-MM-DD
decided:
related:
  tasks: []
  decisions: []
implementation_anchors: []
inflection_point: false
spec_revised:
spec_revised_date:
blocks: []
---

# [Title]

## Select an Option

Mark your selection by checking one box:

- [ ] Option A: [Name]
- [ ] Option B: [Name]

*Check one box above, then fill in the Decision section below.*

## Background

[Why does this decision need to be made? What problem are we solving?
Include enough context for someone unfamiliar to understand.]

## Options Comparison

| Criteria | Option A | Option B | Option C |
|----------|----------|----------|----------|
| [Criterion 1] | | | |
| [Criterion 2] | | | |
| [Criterion 3] | | | |
| Overall | | | |

## Option Details

### Option A: [Name]

**Description:** [What this option entails]

**Strengths:**
- [Benefit 1]
- [Benefit 2]

**Weaknesses:**
- [Drawback 1]
- [Drawback 2]

**Research Notes:** [Links, experiments, spike findings]

### Option B: [Name]

**Description:** [What this option entails]

**Strengths:**
- [Benefit 1]
- [Benefit 2]

**Weaknesses:**
- [Drawback 1]
- [Drawback 2]

**Research Notes:** [Links, experiments, spike findings]

## Your Notes & Constraints

*Add any constraints, preferences, or context that should inform this decision. This section is yours — Claude reads it but never overwrites it.*

**Constraints:**
- [e.g., "Must integrate with existing Redis cluster"]

**Questions:**
- [e.g., "What's the expected data volume in year 2?"]


## Decision

**Selected:** [Option name]

**Rationale:**
[Why this option was chosen. Be specific about the criteria that mattered most.]

## Trade-offs

**Gaining:**
- [What we get from this choice]

**Giving Up:**
- [What we sacrifice or defer]

## Impact

**Implementation Notes:**
[How this affects the work, any immediate actions needed]

**Affected Areas:**
- [Files, components, or systems affected]
- [Related tasks: task IDs]

**Risks:**
- [Any risks introduced by this decision]
```

---

## Categories

| Category | Use For |
|----------|---------|
| `architecture` | System structure, component design, patterns |
| `technology` | Libraries, frameworks, languages, tools |
| `process` | Workflows, team practices, conventions |
| `scope` | Feature boundaries, priorities, trade-offs |
| `methodology` | Approaches, algorithms, techniques |
| `vendor` | Third-party services, APIs, integrations |

---

## Quick Start

1. Copy the template above into a new file
2. Update frontmatter (id, title, category, created)
3. Write Background section
4. Add options to comparison table
5. Fill in Option Details
6. Check your selection in "## Select an Option" (at the top of the doc) — `/work` auto-updates status to `approved` and sets the `decided` date
7. Complete Decision, Trade-offs, Impact sections
8. Regenerate the dashboard to include the new decision

**"Your Notes & Constraints" section:** This section in the template is user-owned. Claude reads it when processing the decision but never overwrites it. Use it to record constraints, preferences, or questions that should inform the choice. Content here persists across decision doc updates and dashboard regenerations.

---

## When to Create Records

### Create a Record For

- Technology choices (libraries, frameworks, services)
- Architectural patterns (how components connect)
- Scope decisions (what's in/out of MVP)
- Process changes (how work gets done)
- Anything that took significant discussion to resolve

### Skip Records For

- Obvious choices with no real alternatives
- Trivial implementation details
- Decisions already documented elsewhere (e.g., in specs)
- Temporary workarounds (use code comments instead)

> **Rule of thumb:** If someone might reasonably ask "why did we do it this way?" in 3 months, create a record.

---

## Decision Lifecycle

```
draft → proposed → approved → implemented
                      ↓
                 superseded
```

- **draft**: Research phase. Gathering options, running experiments.
- **proposed**: Options documented, recommendation made. Ready for stakeholder input.
- **approved**: Decision finalized. May await implementation.
- **implemented**: Decision reflected in project. Common end state.
- **superseded**: Replaced by a newer decision. Link to replacement in Impact section.

### Revisiting Decisions

Decisions aren't permanent. Revisit when circumstances change, trade-offs prove worse than expected, or better options become available.

When superseding: create a new record, reference the old one, mark old as `superseded`, note the replacement in the old record's Impact section.

---

## Choice Classification: Spec vs Implementation

Complex projects benefit from separating **what** to do from **how** to do it. This prevents implementation details from driving design.

### Spec-Level Choices (What)

Define requirements, scope, and approach at a design level. Affects user-visible behavior or system architecture. Should be decided before implementation. Changes require spec revision.

**Examples:** Which features to include in MVP, authentication strategy (OAuth vs magic links), data model structure, API design patterns, user-facing workflows.

### Implementation-Level Choices (How)

Define tools, libraries, and technical details. Affects developer experience, not user-visible behavior. Can be decided during implementation. Changes don't require spec revision.

**Examples:** Which OAuth library, database engine selection, testing framework, CSS approach, build tool configuration.

### Classification Checklist

| Question | Spec-Level | Implementation-Level |
|----------|------------|---------------------|
| Does it change what the system does? | Yes | No |
| Would users notice if it changed? | Yes | No |
| Can it be swapped without redesign? | No | Yes |
| Is it about *behavior* or *tooling*? | Behavior | Tooling |

**When in doubt:** If changing it would require rewriting the spec's acceptance criteria, it's spec-level.

### Integration with Decision Records

- **Spec-Level choices**: Always warrant a decision record if non-obvious
- **Implementation-Level choices**: Create records for significant choices (libraries with long-term commitment, major infrastructure tools)
- **Trivial Implementation choices**: Document inline or skip

---

## Research Archives

Store significant research in `.claude/support/decisions/.archive/`:
- `YYYY-MM-DD_topic.md` - Research notes, findings
- Link from the decision record's Research Notes

This keeps decision records focused while preserving detailed findings.

---

## Optional: Weighted Scoring Matrix

For high-stakes decisions, use weighted scoring to make evaluation explicit:

```markdown
## Weighted Scoring

| Criteria | Weight | Option A | Option B | Option C |
|----------|--------|----------|----------|----------|
| [Criterion 1] | 30% | 4/5 | 3/5 | 5/5 |
| [Criterion 2] | 25% | 5/5 | 4/5 | 3/5 |
| [Criterion 3] | 25% | 3/5 | 5/5 | 4/5 |
| [Criterion 4] | 20% | 4/5 | 3/5 | 4/5 |
| **Weighted Total** | | **4.05** | **3.75** | **4.05** |
```

**Scoring:** 5/5 = Fully meets, 4/5 = Mostly meets, 3/5 = Partial, 2/5 = Weak, 1/5 = Does not meet.

**When to use:** Decisions affecting architecture, multiple strong alternatives, need to communicate rationale to stakeholders.

**Calculating:** For each option: `(Weight1 x Score1) + (Weight2 x Score2) + ...`

---

## Optional: Fallback Plan

For decisions with uncertainty, document what happens if the primary choice doesn't work out:

```markdown
## Fallback Plan

**Trigger condition:** [When would we reconsider this decision?]
**Fallback approach:** [What's the alternative if the primary fails?]
**Migration path:**
1. [Step to transition from primary to fallback]
2. [Data migration or refactoring needed]
**Sunk cost if triggered:** [What work would be lost or need rework?]
```

**When to include:** New/unproven technology, expensive-to-reverse decisions, external dependencies, tight timelines.

---

## Implementation Anchors

When a decision reaches `implemented` status, add anchors to track where the decision is realized in code:

```yaml
implementation_anchors:
  - file: "src/auth/oauth.ts"
    line: 45
    description: "OAuth provider configuration"
  - file: "src/middleware/auth.ts"
    line: 12
    description: "JWT validation middleware"
```

| Field | Required | Description |
|-------|----------|-------------|
| `file` | Yes | Relative path from project root |
| `line` | No | Line number (approximate is fine) |
| `description` | Yes | Brief description of what this anchor represents |

**Why anchors matter:** Drift detection (`/health-check` validates anchor files exist), impact analysis when revisiting decisions, tracing decisions to code during refactoring.

---

