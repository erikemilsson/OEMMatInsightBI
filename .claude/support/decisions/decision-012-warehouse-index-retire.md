---
id: DEC-012
title: Retire warehouse_indexes.sql rather than rewrite to CLUSTER BY
status: approved
category: scope
created: 2026-08-03
decided: 2026-08-03
decided_by: implement-agent
related:
  tasks: ["task-012_4", "task-012_5"]
  decisions: ["DEC-011"]
implementation_anchors:
  - file: "fabric/sql/warehouse_indexes.sql"
    description: "Retired — now a finding document (100% comments, zero executable statements) recording the Msg 22424 platform limitation and the no-slow-query evidence basis"
inflection_point: false
spec_revised:
spec_revised_date:
blocks: []
---

# Retire warehouse_indexes.sql Rather Than Rewrite to CLUSTER BY

## Select an Option

- [ ] Option A: Rewrite warehouse_indexes.sql to CLUSTER BY at CREATE TABLE / CTAS time, targeting the FK-join columns the original DDL assumed
- [x] Option B: Retire warehouse_indexes.sql under AC3 option (b) as a documented platform-limitation finding

*Decision recorded by implement-agent during task-012_4; approved 2026-08-03. Supersedes Erik's initial reopen-to-rewrite choice (option (a) of the dashboard's reopen-or-retire question) after the evidence-first analysis the rewritten AC1 requires found no defensible clustering target.*

## Background

task-012_4 originally authored `fabric/sql/warehouse_indexes.sql` with `CREATE INDEX` + `UPDATE STATISTICS` DDL and passed verification. Erik then deployed it against the Fabric Data Warehouse `oem_wh` and discovered the deliverable is inert:

- `CREATE INDEX` is rejected outright: `Msg 22424, Level 16, State 0 — CREATE INDEX is not a supported statement type.`
- `UPDATE STATISTICS ... WITH FULLSCAN` is accepted but a no-op: ACE statistics are auto-maintained; the engine ignores the DDL.

Erik reopened the task (option (a): rewrite toward CLUSTER BY). The acceptance criteria were rewritten to force an **evidence-first** approach: AC1 requires the clustering target to come from **actual query patterns** against `oem_wh`, not assumed FK-join shapes; AC3 explicitly permits retiring the file with a pointer to the finding (option (b)); AC4 requires any runtime claim to be measured and accepts a null result.

## Options Comparison

| Criteria | Option A (rewrite to CLUSTER BY) | Option B (retire as finding) |
|----------|-----------------------------------|------------------------------|
| AC1 evidence basis | Assumes FK-join columns are worth clustering — the same assumption-first error AC1 was rewritten to prevent | Honors AC1: no slow query identified, so no clustering target can be established |
| Reach of the mechanism | CLUSTER BY on the 8 warehouse tables — but the semantic model is DirectLake-only and reads OneLake parquet, bypassing the warehouse SQL endpoint, so CLUSTER BY cannot affect any Power BI report query | N/A — nothing deploys; documented as a platform limitation |
| Measured runtime claim (AC4) | None to support it; warm Power BI timings are 85–171 ms | Honest null result: no slow SQL-endpoint query to fix |
| Consistency with task-012_5 | task-012_5 found no pipeline-runtime problem; this targets the SQL-endpoint read path, which also shows no problem | Closes the optimization thread consistently with the null-result pattern |
| Overall | Repeats the assumption-first error; authors DDL the platform can reach but no query benefits from | Evidence-first, honest, AC-sanctioned; resolves the inert file under AC3 |

## Option Details

### Option A: Rewrite to CLUSTER BY at CREATE TABLE / CTAS time

**Description:** Replace the rejected `CREATE INDEX` DDL with `CLUSTER BY` clauses on `CREATE TABLE`/CTAS for the warehouse gold tables, targeting the dimension keys and fact foreign keys the original DDL assumed.

**Strengths:**
- Uses the one physical-clustering mechanism Fabric DW actually supports.
- Would leave a deployable artifact for AC5.

**Weaknesses:**
- Repeats the assumption-first error AC1 was rewritten to prevent: the target columns come from assumed FK-join shapes, not from evidence any query is slow.
- The semantic model is DirectLake-only — every partition in `fabric/OEMInsightBI_v2.SemanticModel/definition/tables/*.tmdl` is `mode: directLake`, and `expressions.tmdl` resolves to OneLake parquet on the lakehouse, not `oem_wh`. CLUSTER BY on warehouse tables cannot reach any Power BI report query.
- No documented SQL-endpoint consumer of `oem_wh` and no slow query to justify the rewrite.

### Option B: Retire as a documented platform-limitation finding

**Description:** Replace `warehouse_indexes.sql`'s inert DDL with a finding document (100% comments, zero executable statements) recording the Msg 22424 limitation, that CLUSTER BY is the only supported mechanism, that no slow query was identified, that DirectLake bypasses the warehouse so CLUSTER BY cannot reach the one slow read path, and a revisit trigger.

**Strengths:**
- Evidence-first and honest — the outcome the rewritten ACs force.
- Resolves AC3 (file no longer sits looking deployable while inert).
- Consistent with task-012_5's null result and the measured 85–171 ms warm Power BI timings.
- Documents the platform limitation for future revisits.

**Weaknesses:**
- Closes the optimization thread with "nothing built" — but that is the correct outcome when there is no problem to solve and the mechanism cannot reach the read path.

**Research Notes:** `fabric/OEMInsightBI_v2.SemanticModel/definition/relationships.tmdl`, `tables/*.tmdl`, `expressions.tmdl` (DirectLake → OneLake parquet); `docs/performance_optimized.md` § Power BI (warm timings 85–171 ms, cold-start 84 s diagnosed as DirectLake parquet transcoding of `gold_supply_risk`, not a DirectQuery fallback); task-012_5 (no pipeline-runtime problem); Msg 22424 verified by execution against `oem_wh` 2026-08-03.

## Decision

**Option B — Retire `warehouse_indexes.sql` under AC3 option (b) as a documented platform-limitation finding.**

## Trade-offs

We trade a deployable optimization artifact for an honest null result. The cost is that no physical-clustering optimization ships; the benefit is that we do not repeat the original assumption-first error (authoring DDL that the platform makes inert and no query benefits from). The revisit trigger in the finding document defines the four conditions under which the CLUSTER BY path would reopen (a SQL-endpoint consumer appears, a slow DirectQuery against `oem_wh` is measured, the semantic model moves off DirectLake, or the cold-start transcoding cost is shown to be warehouse-side).

## Impact

- `fabric/sql/warehouse_indexes.sql` is now a finding document, not deployable DDL. AC5 (Erik deploys + confirms) is N/A for the retire path — nothing deploys; Erik reviews the retirement rationale via `user_review_pending` after verification.
- Spec § Performance Optimization line 1283 ("Index creation in warehouse (task-012_4)") still lists the item as an open checkbox. It needs the same strike-through-with-pointer treatment that line 1275 (partitioning, task-012_2) received when that task retired. This is a spec edit and routes through `/iterate` (DEC-016); tracked as friction marker **FR-047**.
- Closes the task-012 optimization sub-thread (012_1 null, 012_2 retired, 012_3 V-Order per DEC-011, 012_4 retired, 012_5 null) — the Performance Optimization section's remaining live item is V-Order, already shipped.