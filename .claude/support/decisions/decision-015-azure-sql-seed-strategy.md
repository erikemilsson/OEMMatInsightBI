---
id: DEC-015
title: Azure SQL seed — literal INSERT dump for both tables, and the coupled DDL table-name correction
status: approved
category: data-architecture
created: 2026-08-11
decided: 2026-08-11
decided_by: implement-agent
related:
  tasks: ["064"]
  decisions: []
implementation_anchors:
  - file: "azure/procurement.sql"
    description: "DDL, retargeted to dbo.procurement_transactional (step 1 of 2)"
  - file: "azure/procurement_seed.sql"
    description: "132 transaction rows as literal INSERTs (step 2 of 2)"
  - file: "azure/supplier_info.sql"
    description: "DDL, retargeted to dbo.supplier_ref (step 1 of 2)"
  - file: "azure/supplier_info_seed.sql"
    description: "11 supplier reference rows as literal INSERTs (step 2 of 2)"
inflection_point: false
spec_revised: false
blocks: []
---

# Azure SQL seed — literal INSERT dump for both tables, and the coupled DDL table-name correction

## Select an Option

Mark your selection by checking one box:

- [x] Option A: Literal `INSERT` dump for both tables
- [ ] Option B: Literal dump for `supplier_ref`, seeded generator for `procurement_transactional`
- [ ] Option C: Deterministic generator for both

*Decided by implement-agent 2026-08-11 during task-064, on measured row counts.*

## Background

task-064 required a fresh clone to rebuild both Azure SQL source tables from repo contents alone. The task anticipated deciding per table — `supplier_ref` as small reference data, `procurement_transactional` as "transactional volume" where a pinned-seed generator might fit better.

## Options Comparison

| Criteria | A (dump both) | B (mixed) | C (generate both) |
|----------|---------------|-----------|-------------------|
| Reproduces the source | **Exactly** | Plausibly, for procurement | Plausibly |
| Determinism risk | None — no RNG | Seed must be pinned | Seed must be pinned |
| Code volume | Lowest | Higher | Highest |
| Curated structure preserved | Free | Must be hard-coded anyway | Must be hard-coded anyway |
| Overall | **Selected** | Rejected | Rejected |

## Option Details

**Option A (selected).** `procurement_transactional` measured at **132 rows** (11 materials × 12 month-end dates), not the volume the task's framing assumed. At that size a dump is both simpler and *exactly* reproducible, where a generator is only plausibly so — and the generator would still have to hard-code the same curated structure (one supplier per material, the 108/24 kg/pcs split, the day/year-transposed dates). Exact beats plausible. With no RNG there is also no seed to pin, so **AC4's determinism requirement is not triggered** — stated rather than silently skipped. The export was nonetheless run twice and produced byte-identical output.

Rows were read from the **lakehouse bronze copies** over OneLake's DFS API (Delta versions 101 and 99), not from Azure SQL. The `erik-laptop` firewall rule stays deleted (AC3, FB-009).

## Coupled sub-decision — the DDL table names were corrected

**This was not in the task's stated scope and is the more consequential half of the change.**

The committed DDL created `dbo.Procurement` and `dbo.SupplierInfo`. Every ingestion artifact that has ever existed — the current Copy activities *and* the retired `bronze_azureSQLdb2table` dataflow's `mashup.pq` — reads `dbo.procurement_transactional` and `dbo.supplier_ref`. The DDL therefore described objects the pipeline could never ingest, and AC1 ("a fresh clone can populate both tables") would have been satisfied only on paper. The dataflow evidence establishes this as a **long-standing error, not recent drift**.

The identifiers were corrected; column definitions were left untouched, keeping the diff to two identifiers per file.

## ⚠ Consequence — a harmless DROP became a live-data DROP

`IF OBJECT_ID(...) IS NOT NULL DROP TABLE ...` was **already in both DDL scripts** before this change — it was not added here. But its meaning changed:

| | Before | After |
|---|---|---|
| Drops | `dbo.Procurement` — a name nothing uses, almost certainly absent | `dbo.procurement_transactional` — **the live table the pipeline reads** |
| Effect of running the DDL alone | No-op | **Destroys the live source data** |

Mitigations, both of which must hold when this is run:

1. **Run each DDL and its seed as one script**, so a mid-run failure cannot leave the table created-but-empty. Each seed opens with a `DELETE` (idempotent on repeat runs) and closes with a row-count `THROW` guard.
2. The data is synthetic and now **fully recoverable from the repo** — which is the point of task-064. Before task-064 this drop would have been unrecoverable.

This is the same hazard class as the project's standing lakehouse rule that `DROP TABLE` on a case-variant name destroys the live table: a rename that looks cosmetic changes what a destructive statement targets.

## Consequences

- `UnitPriceEUR` is written at 2 decimals to match the declared `DECIMAL(18,2)`, while the live column is an **8-byte float (`double`)** carrying noise (`18.670000076293945` for `18.67`). All 132 values were verified to be the exact float32 *image* of their 2-decimal value, so a rebuild yields clean decimals identical to the cent. Documented in the seed header; the one deliberate divergence under AC2.

  > **Corrected 2026-08-12 (task-069 AC4, closing FR-080).** This line previously read "a 4-byte float". It is wrong and it was load-bearing: the noise is a property of the *values* (float32 images stored in a wide column), not of the column width. A fix built on the 4-byte premise would choose T-SQL `REAL` = `FLOAT(24)` → Spark `float`, which still mismatches a `double` silver column and breaks the pipeline from the opposite side. Only `FLOAT` = `FLOAT(53)` lands as `double`. Verified against Microsoft Learn, *float and real (Transact-SQL)*: "The ISO synonym for **real** is **float(24)**."
- The DDL keeps `DECIMAL(18,2)` for `Quantity`/`UnitPriceEUR` per the spec and `docs/schemas/bronze_tables.md`, though bronze lands int16/**float64**. The `data_quality_checks` schema assertion leaves both types unasserted, so either passes.

  > **Corrected 2026-08-12 (task-069 AC4).** Previously read "int16/float32". `int16` was right; `float32` was not — bronze landed `double`. The `DECIMAL(18,2)` half of this sentence **remains true** and is now the ratified contract: DEC-016 selected B-minimal, which keeps the DDL as written and instead stops `bronze_to_silver` from inheriting the source's physical type.
- Spec lines 140/144/174/192/1481/1552 and four `docs/` files still name the tables `dbo.Procurement` / `dbo.SupplierInfo` — a follow-up sweep is needed (spec half via `/iterate`, docs half directly).
- AC5's three spec statements are drafted but unapplied; they route through `/iterate` and are parked in the merge queue as **MQ-002**. (Verification attempt 1 failed because this record and the task notes asserted they were parked before they actually were — an orchestrator hand-off gap, remediated 2026-08-11. Note the § Setup Scripts target needs an *addition*, not a correction: `procurement.sql - ... (DDL only)` remains literally true.)
- Erik's half depends on the `oem_azuresql_procurement` connection having **write** permission — the Copy activities only ever needed `SELECT`. A permissions failure on the Script activity points there, not at the seed.
