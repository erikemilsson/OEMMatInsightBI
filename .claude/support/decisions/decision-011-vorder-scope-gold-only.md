---
id: DEC-011
title: V-Order scope — gold notebook only, not bronze-to-silver
status: approved
category: scope
created: 2026-08-02
decided: 2026-08-02
decided_by: implement-agent
related:
  tasks: ["task-012_3"]
  decisions: []
implementation_anchors:
  - file: "fabric/silver-to-gold2.Notebook/notebook-content.py"
    description: "spark.sql.parquet.vorder.enabled=true set at session start (gold writes only)"
inflection_point: false
spec_revised:
spec_revised_date:
blocks: []
---

# V-Order Scope — Gold Notebook Only, Not Bronze-to-Silver

## Select an Option

- [ ] Option A: Set V-Order in both bronze-to-silver and silver-to-gold2
- [x] Option B: Set V-Order in silver-to-gold2 only

*Decision recorded by implement-agent during task-012_3; approved 2026-08-02.*

## Background

task-012_3 enables V-Order (`spark.sql.parquet.vorder.enabled=true`) for DirectLake columnar read performance. V-Order reorders parquet data on write to match the Power BI VertiPaq engine's columnar layout, improving DirectLake scan performance at the cost of higher write CPU. The question is which notebook(s) should set it: both the bronze-to-silver and silver-to-gold notebooks, or only silver-to-gold2.

The spec (§ Performance Optimization) names this as "DirectLake optimization (V-Order columnar format)". DirectLake binds to the **gold** tables — bronze and silver tables are not scanned by the semantic model.

## Options Comparison

| Criteria | Option A (both notebooks) | Option B (gold only) |
|----------|---------------------------|----------------------|
| DirectLake read benefit | Gold gets it | Gold gets it |
| Write cost paid | Bronze + silver + gold writes | Gold writes only |
| Alignment with spec wording ("DirectLake optimization") | Partial — applies V-Order where DirectLake doesn't read | Full — V-Order lands where DirectLake reads |
| Overall | Pays write cost with no read benefit on bronze/silver | Write cost paid exactly where the read benefit lands |

## Option Details

### Option A: Set V-Order in both bronze-to-silver and silver-to-gold2

**Description:** Enable `spark.sql.parquet.vorder.enabled=true` in both transformation notebooks.

**Strengths:**
- Uniform config across the transformation chain.
- Bronze/silver parquet files are V-Ordered if anything ever reads them via DirectLake.

**Weaknesses:**
- Bronze/silver tables are not DirectLake-bound — the V-Order write cost is paid with no read benefit.
- Slower bronze/silver writes for no portfolio-relevant gain.

**Research Notes:** None.

### Option B: Set V-Order in silver-to-gold2 only

**Description:** Enable V-Order only in the gold notebook. Bronze-to-silver writes parquet without V-Order (it is in `files_affected` for the caching deliverable, not V-Order).

**Strengths:**
- Write cost is paid exactly where the DirectLake read benefit lands (gold tables).
- Matches the spec's "DirectLake optimization" framing — gold-specific.
- Bronze/silver writes stay cheaper.

**Weaknesses:**
- Config differs across notebooks (minor — documented inline).

**Research Notes:** task-012_1 baseline identified silver-to-gold as the runtime bottleneck; V-Order's read benefit accrues to the gold tables DirectLake scans.

## Your Notes & Constraints

*User-owned section — Claude reads but never overwrites.*

**Constraints:**
- DirectLake semantic model binds to gold tables only.

**Questions:**
- None open.

## Decision

**Selected:** Option B — Set V-Order in silver-to-gold2 only.

**Rationale:**
DirectLake reads gold tables; V-Order's write cost on bronze/silver would be paid with no DirectLake read benefit. The spec section names "DirectLake optimization (V-Order columnar format)", which is gold-specific. bronze-to-silver is in task-012_3's `files_affected` for the caching deliverable, not V-Order. Concentrating the write cost where the read benefit lands is the correct trade.

## Trade-offs

**Gaining:**
- Gold tables V-Ordered for DirectLake scan performance.
- No wasted write cost on bronze/silver.

**Giving Up:**
- V-Order is not applied to bronze/silver parquet (no loss, since DirectLake doesn't read them).

## Impact

**Implementation Notes:**
- `spark.sql.parquet.vorder.enabled=true` set at session start in `fabric/silver-to-gold2.Notebook/notebook-content.py`.
- Erik's one-time `OPTIMIZE` step on existing gold tables (task-012_3 AC2) converts already-written gold parquet to V-Order layout — documented as a deploy note in the notebook, run by Erik in Fabric.

**Affected Areas:**
- `fabric/silver-to-gold2.Notebook/notebook-content.py`
- Related task: task-012_3

**Risks:**
- None material. If a future consumer DirectLake-binds a silver table, revisit (would require V-Order on silver writes).