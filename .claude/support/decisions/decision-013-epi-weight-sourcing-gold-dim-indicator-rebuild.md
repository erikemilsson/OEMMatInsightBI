---
id: DEC-013
title: EPI weight sourcing — gold_dim_indicator rebuild (task-056)
status: approved
category: architecture
created: 2026-08-04
decided: 2026-08-04
decided_by: implement-agent
related:
  tasks: ["056", "055"]
  decisions: []
implementation_anchors:
  - file: "fabric/bronze_ingest_epi.Notebook/notebook-content.py"
    description: "Downloads epi{epi_year}weights.csv -> bronze_epi{epi_year}weights"
  - file: "fabric/silver-to-gold2.Notebook/notebook-content.py"
    description: "Builds silver_epi{EPI_YEAR}variables from bronze weights; retires NULL-weight fallback; parent_indicator self-join on NextLevel"
  - file: "fabric/OEMInsightBI_v2.SemanticModel/definition/tables/fact_epi_score.tmdl"
    description: "Weighted EPI Score measure hardened with type=\"Indicator\" filter"
inflection_point: false
spec_revised: false
blocks: []
---

# EPI weight sourcing — gold_dim_indicator rebuild (task-056)

## Select an Option

Mark your selection by checking one box:

- [x] Option A: Source EPI weights from Yale `epi2024weights.csv`, map `weight` ← `EPI Percent` (absolute), retire NULL-weight fallback, harden measure with `type="Indicator"`
- [ ] Option B: Keep the NULL-weight fallback; leave Weighted EPI Score BLANK

*Decision finalized by implement-agent 2026-08-04 during task-056 implementation.*

## Background

Weighted EPI Score rendered BLANK in the deployed semantic model (task-055 AC4 spot-check, 2026-08-04) because `gold_dim_indicator.weight` was NULL for all 73 rows. Root cause: `silver-to-gold2.Notebook` built `gold_dim_indicator` via a fallback path that hardcoded `weight=F.lit(None)` and flattened `type` to `'indicator'` for all rows, because the expected `silver_epi{EPI_YEAR}variables` table was never built — `bronze_ingest_epi` downloaded only `epi{year}results.csv`. This was pre-existing (not a task-055 regression): the measure has always relied on `RELATED(weight)`, and the weight column has always been NULL. task-056 sources the weights and rebuilds the dimension so the measure renders a real 0-100 value.

## Options Comparison

| Criteria | Option A (EPI Percent, rebuild) | Option B (keep BLANK) |
|----------|--------------------------------|----------------------|
| Measure renders real value | Yes | No (BLANK) |
| Hierarchy preserved (4 Types) | Yes | No (flattened to 'indicator') | 
| New bronze dependency | Yes (weights.csv download) | No |
| Risk to unrelated gold tables | Low (fallback now warns + empty, doesn't crash) | None |
| Overall | Selected | Rejected |

## Option Details

### Option A: Source weights from epi2024weights.csv, rebuild gold_dim_indicator

**Description:** Extend `bronze_ingest_epi` to also download `epi{epi_year}weights.csv` → `bronze_epi{epi_year}weights`. Build `silver_epi{EPI_YEAR}variables` from the bronze weights table. Rebuild `gold_dim_indicator` via the existing primary path (now it has a real source). Retire the NULL-hardcoding fallback to a loud-warning + empty EPI df.

**Strengths:**
- Measure renders the true EPI composite (weighted average of leaf indicators by absolute contribution).
- Preserves the real 4-value `type` hierarchy (EPI/PolicyObjective/IssueCategory/Indicator).
- `parent_indicator` populated from `NextLevel` via self-join — real hierarchy for the dimension.

**Weaknesses:**
- Adds a bronze download dependency (epi{year}weights.csv); if Yale's URL scheme changes, both results + weights break together (same pattern, so no new failure mode).
- Mild medallion layering compromise: `silver_epi{EPI_YEAR}variables` is built in `silver-to-gold2.Notebook` (a gold notebook) rather than `bronze-to-silver.Notebook`, because the task's `files_affected` listed silver-to-gold2 and the brief allowed it (logged as an `informal_decision` friction marker).

**Research Notes:** Yale `epi2024weights.csv` carries: Type, Abbreviation, Variable, Weight (relative within parent), NextLevel, IssueCategory, PolicyObjective, EPI Percent (absolute contribution to the EPI composite). ~73 rows (1 EPI + 2 PolicyObjective + 11 IssueCategory + ~58 Indicator).

### Option B: Keep the NULL-weight fallback (leave measure BLANK)

**Description:** Make no change; accept Weighted EPI Score = BLANK.

**Strengths:** No new code/dependency.

**Weaknesses:** The portfolio's headline EPI measure stays non-functional; the dimension hierarchy stays flattened.

## Decision

**Selected:** Option A. Three sub-decisions made during implementation:

1. **`weight` ← `EPI Percent` (absolute), not relative `Weight`.** The measure computes `SUM(score * RELATED(weight)) / SUM(weight)` over leaf indicators — it needs the absolute contribution so the result is the true EPI composite. The relative `Weight` would give a weighted average within a parent, not the composite. `EPI Percent` is NULL for aggregate rows (EPI/PO/IC), which is exactly what the measure needs to drop aggregates from both numerator and denominator via `RELATED(weight)=NULL`.

2. **Retire the fallback to a loud-warning + empty EPI df (not raise, not keep silent NULLs).** Raising would abort the whole gold notebook and block unrelated gold tables. Keeping the NULL-weight fallback would re-introduce the silent BLANK measure. An empty EPI df makes `gold_dim_indicator` obviously empty so the problem surfaces in any downstream check without blocking other gold writes. In a normal pipeline run the silver-build cell above always produces the table, so this path only fires on a genuine upstream failure.

3. **Apply the optional `type="Indicator"` measure harden.** With real weights, aggregates drop out via `RELATED(weight)=NULL` anyway, so the filter is functionally redundant. But explicit is safer than relying on NULL-weight exclusion — it makes the leaf-only intent legible in the measure and survives any future change that populated aggregate weights. task-055's `abbrev <> "EPI"` double-count fix is retained.

**Rationale:** The absolute-vs-relative weight semantics is the load-bearing choice: only `EPI Percent` produces the true EPI composite. The fallback retirement choice prioritizes visible breakage over silent BLANK. The measure harden makes the leaf-only intent explicit.

## Trade-offs

**Gaining:**
- A working Weighted EPI Score (the portfolio's headline EPI measure).
- A real 4-value `type` hierarchy and `parent_indicator` from `NextLevel`.
- Visible-failure fallback (no more silent NULL-weight masking).

**Giving Up:**
- A bronze download dependency (shared with the existing results download pattern).
- Strict medallion layering (silver table built in a gold notebook — logged).

## Impact

**Implementation Notes:** task-056 implements AC1-3 (code + local Spark verification, 11/11 assertions). AC4 (push → fabric-cicd redeploy → Power BI REST spot-check) is Erik-gated and not part of this decision's verification. Deployed-model assertions (`weight_count_nonblank > 0`, `COUNT(DISTINCT type)=4`, Avg EPI Score=46.95 sanity) require the redeploy.

**Affected Areas:**
- `fabric/bronze_ingest_epi.Notebook/notebook-content.py` — weights download
- `fabric/silver-to-gold2.Notebook/notebook-content.py` — silver variables build, fallback retirement, parent_indicator self-join
- `fabric/OEMInsightBI_v2.SemanticModel/definition/tables/fact_epi_score.tmdl` — measure harden
- `docs/epi_wgi_ingestion.md`, `dax_measure_library.md` — doc updates
- Spec drift: `spec_v1.md § Data Transformations → gold_dim_indicator` (L558-574) is now stale — Source says `silver_epi2024variables2024-12-11` and `parent_indicator (currently NULL)`. Tracked as FR-051; reconcile via `/iterate` (DEC-016).
- Related tasks: task-056, task-055

**Risks:**
- If Yale changes the weights CSV column names or URL scheme, the bronze download breaks (same risk as the existing results download — no new failure mode).
- The silver-table-built-in-gold-notebook layering compromise could surprise a reader expecting medallion purity; documented here and in the `informal_decision` friction marker.