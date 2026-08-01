---
id: DEC-010
title: "Supply Concentration migration: add the measure to the TMDL with the supply_mix='global' filter"
status: approved
category: implementation
created: 2026-08-01
decided: 2026-08-01
decided_by: implement-agent
recommended_by: implement-agent
recommendation_date: 2026-08-01
related:
  tasks: [task-038_5]
  decisions: [DEC-001]
implementation_anchors:
  - fabric/OEMInsightBI_v2.SemanticModel/definition/tables/fact_supply_share.tmdl
  - fabric/OEMInsightBI_v2.SemanticModel/definition/tables/gold_supply_risk.tmdl
inflection_point: false
spec_revised:
spec_revised_date:
blocks: []
---

# Supply Concentration migration: add the measure to the TMDL with the supply_mix='global' filter

## Select an Option

- [x] Option A: Add `Supply Concentration Index` to `fact_supply_share.tmdl` with the `supply_mix="global"` filter (requires declaring the `supply_mix` column) — satisfies criterion 3 in the semantic model itself
- [ ] Option B: Only update the measure in `dax_measure_library.md §6.1` (where it existed as `Max Supply Concentration %`) and leave the TMDL without the measure, flagging the gap

## Decision

**Selected: Option A** — task-038_5 criterion 3 ("the existing Supply Concentration measure is filtered to `supply_mix = 'global'`") was interpreted as *add it correctly the first time with the filter*, because the TMDL contained no pre-existing Supply Concentration measure to update. `Supply Concentration Index = CALCULATE(MAX(fact_supply_share[share_pct]), supply_mix="global")` was added to `fact_supply_share.tmdl`, and the `supply_mix` column was declared so the filter resolves.

## Background

task-038_5 acceptance criterion 3 frames the change as a *migration* of an "existing Supply Concentration measure" to the `supply_mix='global'` filter — the semantic-model half of the same double-count migration task-038_2 criterion 3 performed on the data side. But a grep of the TMDL confirmed **zero** pre-existing measures on `fact_supply_share.tmdl` (consistent with task-038_2's note that no measures had been authored against the table yet). The "existing measure" the criterion assumed lived only in `dax_measure_library.md` (as `Max Supply Concentration %`), not in the semantic model.

`spec_v1.md § Semantic Model & Reporting` (line ~797) lists `Supply Concentration Index = MAX(fact_supply_share[share_pct])` *filtered to `supply_mix=global`* as a representative measure that should be in the model — so the spec's intent is that the measure exists in the TMDL with the filter, and the gap was the TMDL never having received it. This gap is logged as **FR-042** (routes via `/iterate` if the spec's representative-measures list should be made explicit about presence-in-model).

## Options Comparison

| Criteria | A: add to TMDL with filter | B: library-only, flag the gap |
|----------|---------------------------|------------------------------|
| Satisfies criterion 3's intent (no double-count in the model) | **Yes** | No — model still lacks the filtered measure |
| Aligns TMDL with spec § Semantic Model representative-measures list (L797) | **Yes** | No |
| Within task-038_5 declared files_affected (whole semantic-model folder) | **Yes** | Yes |
| Risk | Declares a column + measure not previously in the TMDL | Leaves a spec-vs-model gap for a later task |
| Overall | **Selected** | Rejected |

## Option Details

### Option A: add the measure to the TMDL with the filter *(selected)*

**Strengths:**
- Resolves the double-count at the semantic-model layer, matching how task-038_2 resolved it on the data layer — the two halves of the migration now agree.
- Brings the TMDL into line with the spec's representative-measures list, closing FR-042's substance (the gap is now only that the spec doesn't *say* the measure must be present, not that it's absent).
- The `supply_mix` column declaration is required for the filter to resolve and is itself a correct addition (the column has been on the Delta table since task-038_2).

**Weaknesses:**
- Adds a measure + column the TMDL never had, which Erik must confirm resolves in the DirectLake refresh (criterion 5). This is the both-owned review gate, not a defect.

### Option B: library-only

Would leave the semantic model without the filtered measure, contradicting the spec's representative-measures list and leaving the double-count fix incomplete on the model side. Rejected.

## Consequences

- `fact_supply_share.tmdl` now carries the `Supply Concentration Index` measure (filtered to `supply_mix="global"`) and declares the `supply_mix` column. The `t` trade-parameter column (on the Delta table since task-038_2) remains undeclared — no current measure references it, so nothing breaks; declaring it is a minor completeness follow-up, not part of this decision.
- The three SR measures on `gold_supply_risk.tmdl` use `MAX(hhi_global)` / `MAX(hhi_eu_sourcing)` as their aggregation form. At the table's unique grain (material × stage × year) `SUM`/`MAX`/`AVERAGE` collapse to the same value, so the choice is stylistic; `MAX` was selected to match the existing `Max Supply Concentration` precedent on `fact_supply_share` and to avoid silently summing across stages/years when a report groups by material alone. Recorded here rather than as a separate decision because it does not block downstream work and collapses to the same value at grain.
- Erik's criterion-5 DirectLake refresh must confirm both the new `gold_supply_risk` measures and the new `Supply Concentration Index` resolve without errors.
- FR-043 (terminology mismatch: `Supply Concentration Index` vs `Supply Concentration` vs `Max Supply Concentration %`) is resolved by aligning both the TMDL and the library to the spec § Semantic Model name `Supply Concentration Index`; routes via `/iterate` if the spec should be made single-voiced.