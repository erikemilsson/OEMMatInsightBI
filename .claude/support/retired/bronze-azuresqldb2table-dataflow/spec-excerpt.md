# Spec excerpt — `bronze_azureSQLdb2table.Dataflow`

Captured from `.claude/spec_v1.md` at the retirement pin `04ed718d7e33120cacfc9957e573c34fbb45fa59` (2026-07-31).

This file is the **historical truth** for what the spec said about the dataflow while it
was live. The in-spec sections themselves are NOT excised — each carries a
`**Retired (2026-07-31)**` marker instead, per `.claude/rules/feature-retirement.md`
Step 4 (excising would change section fingerprints and trip drift reconciliation).

The retirement spans **four** spec locations. All four are reproduced below verbatim.

---

## 1. § Data Sources — Ingestion Method (line 150)

```markdown
**Ingestion Method:**

-   Fabric Dataflow: `bronze_azureSQLdb2table.Dataflow`

-   Frequency: Manual — pipeline triggered on demand

-   Incremental vs Full Load: Parameters exist (`p_full_load`, `p_from_date`); incremental logic implementation is task-006
```

---

## 2. § Orchestration — Stage 1 Bronze Ingestion activity table (line 628)

```markdown
**Stage 1: Bronze Ingestion (Parallel Execution)** — all activities timeout 12 hours

| # | Activity | Type | Sink / Output | Retry |
|---|----------|------|---------------|-------|
| 1 | `bronzecopy_EUSupplyShares` | Copy (HTTP → Lakehouse) | `bronze_EUSupplyShares` | 3 |
| 2 | `bronzecopy_GlobalSupplyShares` | Copy (HTTP → Lakehouse) | `bronze_GlobalSupplyShares` | 3 |
| 3 | `bronze_WGI` | Notebook | `bronze_WGI` | 2 |
| 4 | `bronze_procurement` | RefreshDataflow | `bronze_procurement_transactional`, `bronze_supplier_ref` | 3 |
| 5 | `bronze_EPI` | Notebook | `bronze_epi2024results` and related tables | 2 |
```

Row 4 is the retired surface. It becomes a Copy activity (or pair of Copy activities)
producing the same two tables under the same names.

---

## 3. § Current State Assessment — What's Implemented (line 828)

```markdown
**Bronze Layer:**

-   [x] Azure SQL dataflow (`bronze_azureSQLdb2table.Dataflow`)
```

---

## 4. § Naming Conventions — Dataflows (lines 991-993)

```markdown
**Dataflows:**

-   `[layer]_[source]_[method]2table.Dataflow`

-   Examples: `bronze_azureSQLdb2table`
```

Note: with this retirement the project has **no remaining Dataflow Gen2 items authored
under this convention for Azure SQL**. `EPI_file2table` and `WGI_file2table` still exist
as items but were superseded as *pipeline activities* by task-035's notebook migration.
The naming convention itself is not retired — only this example of it.

---

## What the dataflow actually did

Three shared queries in `mashup.pq` (see the snapshot alongside this file):

1. **`p_from_date`** — text parameter, default `"1900-01-01"`, `IsParameterQuery = true`.
2. **`procurement_transactional`** — reads `dbo.procurement_transactional` from
   `procurement-supplier.database.windows.net` / `procurement-supplier-db`
   (`EnableCrossDatabaseFolding = true`) into `bronze_procurement_transactional`.
   - When `p_from_date = "1900-01-01"` → full load.
   - Otherwise → `Value.NativeQuery` with `EnableFolding = true` and a **7-day look-back**:
     `SELECT * FROM dbo.procurement_transactional WHERE Date >= '<p_from_date minus 7 days>'`.
   - **`CorrectedDate` transformation** (the load-bearing subtlety):
     `#date(Date.Day([Date]) + 2000, Date.Month([Date]), Date.Year([Date]) - 2000)`
     — a deliberate day/year swap correcting malformed source dates. The original `Date`
     column is then **dropped** and `CorrectedDate` **renamed** to `Date`.
   - **Ordering matters:** the look-back filter runs against the RAW, still-malformed
     `Date`; the correction is applied afterwards.
3. **`supplier_ref`** — straight `dbo.supplier_ref` → `bronze_supplier_ref`, no transform,
   no parameter, always full load.

Both destinations write to lakehouse `oem_lh` (`488fb9f8-e635-4683-90c4-ba4fee9dfadb`)
in workspace `99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9` via `Lakehouse.Contents`, staging
`Kind = "FastCopy"`.
