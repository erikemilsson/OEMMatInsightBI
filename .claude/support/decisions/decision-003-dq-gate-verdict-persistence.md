---
id: DEC-003
title: Record the DQ gate verdict as entity='gate' rows in gold_quality_history rather than a new table
status: proposed
category: architecture
created: 2026-07-23
decided:
recommended_by: implement-agent
recommendation_date: 2026-07-22
related:
  tasks: [task-040, task-026]
  decisions: []
implementation_anchors:
  - fabric/data_quality_checks.Notebook/notebook-content.py
  - fabric/silver-to-gold2.Notebook/notebook-content.py
inflection_point: false
spec_revised:
spec_revised_date:
blocks: []
---

# Record the DQ gate verdict as entity='gate' rows in gold_quality_history rather than a new table

> **Status note.** implement-agent selected and implemented this option while executing task-040
> (acceptance criterion 2 requires *a* durable verdict but does not prescribe the shape). Per
> `.claude/rules/decisions.md`, selection authority is Erik's, so this record is filed as
> `proposed` for ratification rather than self-approved — the same correction verify-agent applied
> to DEC-002. Tick the box below to ratify, or pick another option and the implementation will be
> reworked. See FR-010 / FR-011: `work-procedures.md § State Persistence Protocol` says to write
> these as `approved`, which contradicts `rules/decisions.md`; this record follows the rule, not
> the procedure.

## Select an Option

Mark your selection by checking one box:

- [ ] Option A: Three `entity='gate'` rows appended by the enforcement cell before the raise  *(recommended — implemented under task-040)*
- [ ] Option B: A new `gold_dq_gate_log` table
- [ ] Option C: Move the `BLOCKING_CHECKS` definition above the persistence cell and emit the verdict from there

*Check one box above, then fill in the Decision section below.*

## Background

task-026 wired the data-quality gate and it works, but its outcome was not recoverable after the
fact. The halt is decided by `result["status"] == "fail"` over the `BLOCKING_CHECKS` set; what
`gold_quality_history` persisted was `breach_flag`, an unrelated score threshold (`score < 70.0`).
The two diverge in practice — `grain_uniqueness` failing on 2 grains out of 2,561 rows scores ~99.9,
never breaches, and still halts the pipeline — so the only durable record could not distinguish a
clean run from a blocked one. The notebook's printed enforcement block is not a fallback: the
pipeline editor's Output panel only shows runs from the current editor session.

task-040 criterion 2 requires a per-run gate verdict to be *durably recorded*, answerable "by a
single query with no reference to notebook code". It does not prescribe where. That is this decision.

## Options Comparison

| Criteria | A: `entity='gate'` rows | B: new `gold_dq_gate_log` table | C: hoist `BLOCKING_CHECKS` |
|----------|--------------------------|----------------------------------|-----------------------------|
| New DDL required | No | Yes | No |
| New semantic-model binding required | No | Yes | No |
| Touches task-026's working code | No | No | Yes — relocates it |
| Gate question answerable from one table | Yes | No — split across two | Yes |
| Verdict persisted before the raise | Yes | Yes | Yes |
| Overall | Recommended | Higher cost, splits the answer | Violates task-040's scope boundary |

## Option Details

### Option A: Three `entity='gate'` rows appended by the enforcement cell before the raise

**Description:** The section-7 enforcement cell appends `dq_gate_blocking_evaluated`,
`dq_gate_blocking_failures` and `dq_gate_raised` as `entity='gate'` rows carrying
`status='pass'|'fail'`, written *before* the `DataQualityException` is raised.

**Strengths:**
- Keeps the gate question in the one table people already query and the semantic model already binds.
- No new DDL, no new model binding.
- Leaves task-026's severity model and aggregated-raise design physically untouched — the scope
  boundary task-040 set.
- Preserves and extends task-026's persist-then-raise ordering, so a failing run still leaves the
  full picture.

**Weaknesses:**
- Overloads `gold_quality_history`'s `entity` column with a non-table sentinel value (`'gate'`).
- The verdict is three rows rather than one, so a consumer must know the three metric names.

### Option B: A new `gold_dq_gate_log` table

**Description:** A dedicated one-row-per-run gate audit table.

**Strengths:**
- Clean grain: exactly one row per run, no sentinel values.
- No overloading of an existing schema.

**Weaknesses:**
- Splits "what happened to quality on run X" across two tables.
- Needs new DDL plus a second semantic-model binding to be visible in Power BI.

### Option C: Move `BLOCKING_CHECKS` above the persistence cell and emit the verdict there

**Description:** Relocate the blocking-set definition so the main persistence cell can compute and
write the verdict itself.

**Strengths:**
- Single write site; no separate append in the enforcement cell.

**Weaknesses:**
- Relocates task-026's code, which task-040's notes explicitly place out of scope.
- Higher regression risk against a gate that is currently proven green in both directions.

## Your Notes & Constraints

*This section is yours — Claude reads it but never overwrites it.*

**Constraints:**
-

**Questions:**
-

## Decision

**Selected:** *(awaiting ratification)*

**Rationale:**


## Trade-offs

**Gaining:**
- One-query answerability of "did the gate pass on run X" with no new artifacts to deploy or bind.

**Giving Up:**
- Schema purity on `gold_quality_history.entity`, which now carries a `'gate'` sentinel alongside
  real table names.

## Impact

**Implementation Notes:**
Implemented under task-040 ahead of ratification; task-040 is Awaiting Verification. If Option B or
C is selected instead, task-040's data_quality_checks changes are reworked — the `status` /
`producer` column additions are common to all three options and are unaffected.
