# Medallion Architecture - OEMMatInsightBI

## Overview

The project implements a **medallion architecture** (bronze → silver → gold) for data transformation, following lakehouse best practices.

## Architecture Diagram

```
┌─────────────────────┐
│   Source Systems    │
│  - Azure SQL DB     │
│  - EPI CSV (HTTP)   │
│  - World Bank API   │
│  - EU CRM HTTP      │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   BRONZE LAYER      │
│   (Raw Ingestion)   │
│                     │
│ - bronze_           │
│   procurement_      │
│   transactional     │
│ - bronze_           │
│   supplier_ref      │
│ - bronze_           │
│   epi{year}results  │
│ - bronze_wgi        │
│ - bronze_Global     │
│   SupplyShares      │
│ - bronze_EU         │
│   SupplyShares      │
└──────────┬──────────┘
           │
      /run-bronze
           │
           ▼
┌─────────────────────┐
│   SILVER LAYER      │
│  (Clean & Validate) │
│                     │
│ - silver_           │
│   procurement       │
│ - silver_           │
│   epi{year}results  │
│ - silver_wgi        │
│ - silver_global     │
│   supplyshares      │
└──────────┬──────────┘
           │
      /run-silver
           │
           ▼
┌─────────────────────┐
│    GOLD LAYER       │
│ (Business Logic)    │
│                     │
│ FACTS:              │
│ - fact_procurement  │
│ - fact_supply_share │
│ - fact_epi_score    │
│                     │
│ DIMENSIONS:         │
│ - gold_dim_country  │
│ - gold_dim_date     │
│ - gold_dim_material │
│ - gold_dim_indicator│
│ - gold_dim_stage    │
└──────────┬──────────┘
           │
       /run-gold
           │
           ▼
┌─────────────────────┐
│ DATA QUALITY CHECKS │
│ (blocking gate)     │
│                     │
│ data_quality_checks │
│ .Notebook           │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  SEMANTIC MODEL     │
│  (DirectLake on     │
│   oem_lh lakehouse) │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   POWER BI REPORT   │
│  (Visualizations)   │
└─────────────────────┘
```

> **There is no Warehouse Sync stage.** This diagram used to place an `oem_wh`
> warehouse mirror between gold and the semantic model. The `oem_wh.Warehouse` artifact
> does exist in `fabric/` (table DDL only), but **no pipeline activity populates it** and
> the semantic model reads DirectLake directly off the `oem_lh` lakehouse
> (`expressions.tmdl`: `expression 'DirectLake - oem_lh'`). If a SQL-interface mirror is
> ever wanted it needs its own task; until then it is not part of the flow.

## Layer Definitions

### Bronze Layer - Raw Ingestion

**Purpose:** Capture raw data from source systems as-is

**Characteristics:**
- ✅ Exact copy of source data
- ✅ No transformations (except basic type inference)
- ✅ No data quality checks
- ✅ Preserves all columns and rows
- ✅ Append-only or full refresh

**Data Format:** Delta Lake (Parquet + transaction log)

**Tables:**

| Table | Contents | Ingested by |
|---|---|---|
| `bronze_procurement_transactional` | Procurement transactions (RAW dates — see note) | Copy activity `bronze_copy_procurement_transactional` |
| `bronze_supplier_ref` | Supplier reference data | Copy activity `bronze_copy_supplier_ref` |
| `bronze_epi{year}results` | Environmental Performance Index (e.g. `bronze_epi2024results`) | `bronze_ingest_epi.Notebook`, parameterised on `p_epi_year` |
| `bronze_wgi` | World Bank governance indicators, long format | `bronze_ingest_wgi.Notebook` (World Bank API v2) |
| `bronze_global_supply_shares` | Global supply concentration | Copy activity `bronze_copy_global_supply_shares` (HTTP) |
| `bronze_eu_supply_shares` | EU supply concentration | Copy activity `bronze_copy_eu_supply_shares` (HTTP) |

> **Retired lineage.** `bronze_WB_ESGCSV`, `bronze_WB_ESGSeries` and the
> `WGI_file2table.Dataflow` that produced them are retired; those tables no longer exist
> and nothing downstream reads them. WGI now arrives from the World Bank API as
> `bronze_wgi`. See `schemas/bronze_tables.md` for the shape.

**Ingestion Methods:**
- Copy activities (Azure SQL, HTTP sources)
- Notebooks (World Bank API, EPI download)

**Commands:** `/run-bronze`

### Silver Layer - Cleaned & Validated

**Purpose:** Standardize and validate data for downstream consumption

**Characteristics:**
- ✅ Column naming standardized (lowercase, underscores)
- ✅ Data types cast correctly
- ✅ Basic quality checks (nulls, ranges)
- ✅ Unpivoting/reshaping where needed
- ✅ Joins to enrich data
- ❌ No business logic yet
- ❌ No surrogate keys yet

**Transformations:**
1. **EPI:** Drop .old columns, remove .new suffixes, cast types
2. **Supply Shares:** Lowercase headers, replace spaces with underscores
3. **WGI:** Standardize ISO3, preserve `Indicator Code`/`Year`/`Value`, drop
   null-valued observations, deduplicate to grain (country × indicator × year)
4. **Procurement:** Join with supplier_ref, standardize column names

> **WGI is already long-format — nothing is unpivoted.** This step used to read
> `bronze_WB_ESGCSV` + `bronze_WB_ESGSeries` (a wide Excel extract), unpivot year
> columns, filter to 2020 and write `silver_WB`. That lineage is retired and none of
> those tables exist. The live source is the World Bank API via
> `bronze_ingest_wgi.Notebook`, which delivers one row per country per indicator per
> year. Silver preserves `Year`/`Value` because they are the `WGIᶜ` governance weight
> in the supply-risk model (DEC-001); dropping them was the defect task-031 fixed.

**Tables:**
- `silver_procurement` - Cleaned procurement with supplier info
- `silver_epi{year}results` - Cleaned EPI data (e.g. `silver_epi2024results`; the vintage
  follows the `p_epi_year` pipeline parameter)
- `silver_wgi` - Governance indicators, grain (country_iso3, indicator_name, year),
  columns `country_iso3`, `country_name`, `indicator_name`, `indicator_code`,
  `year`, `value`
- `silver_globalsupplyshares` - Cleaned supply shares

**Notebook:** `bronze_to_silver.Notebook`

**Commands:** `/run-silver`

### Gold Layer - Business-Ready

**Purpose:** Apply business logic and create dimensional model (star schema)

**Characteristics:**
- ✅ Star schema design (facts + dimensions)
- ✅ Surrogate keys (xxhash64)
- ✅ Alias resolution (country/material names)
- ✅ Confidence scoring and data quality tracking
- ✅ Unit normalization (all quantities in kg)
- ✅ Business calculations (spend = quantity × price)
- ✅ Unmapped value handling (placeholders + audit)

**Outputs:**

**Fact Tables:**
- `fact_procurement` - Procurement transactions with surrogate keys
- `fact_supply_share` - Global supply concentration by material/country/stage
- `fact_epi_score` - Environmental scores by country/indicator

**Dimension Tables:**
- `gold_dim_country` - Country master (ISO3 codes, names, regions)
- `gold_dim_date` - Date dimension (calendar attributes)
- `gold_dim_material` - Material master (names, commodity groups)
- `gold_dim_indicator` - EPI/WGI indicator metadata
- `gold_dim_stage` - Production stages (Extraction, Processing)

**Supporting Tables:**
- `gold_dim_country_lookup` - Country alias mappings
- `gold_dim_material_lookup` - Material alias mappings
- `gold_unmapped_procurement_audit` - Unmapped procurement values
- `gold_unmapped_supply_audit` - Unmapped supply values
- `gold_unmapped_unit_audit` - Units outside the kg conversion map
- `gold_data_quality_metrics` - Quality summary statistics
- `gold_country_coverage_matrix` - Country presence across sources
- `gold_data_gaps` / `gold_data_gaps_summary` - EPI/WGI coverage per country

**Observability Tables** (also written by this notebook — see `data_quality_architecture.md`):
- `gold_quality_history` - Append-only quality metrics per run
- `gold_gap_registry` - Lifecycle tracking of distinct unmapped values
- `gold_low_confidence_audit` - Matches that succeeded below 0.95 confidence

**Notebook:** `silver_to_gold.Notebook`

**Commands:** `/run-gold`

## Data Flow Rules

### Bronze → Silver
- **Row count:** Should match (no filtering)
- **Columns:** May be added/removed (standardization)
- **Data types:** May change (casting)
- **Quality:** Basic validation only

### Silver → Gold
- **Row count:** May differ (pivoting, unmapped filtering)
- **Columns:** Significant changes (surrogate keys, calculated fields)
- **Data types:** Final types enforced
- **Quality:** Comprehensive scoring and tracking

## Orchestration

**Pipeline:** `orchestrator_pipeline_bronze_to_gold.DataPipeline`

**Stages** (8 activities — grounded against `pipeline-content.json`):

1. **Bronze (Parallel):** 5 activities with no interdependencies —
   `bronze_copy_global_supply_shares` and `bronze_copy_eu_supply_shares` (Copy),
   `bronze_copy_procurement_transactional` + `bronze_copy_supplier_ref` (Copy), `bronze_wgi` and `bronze_EPI`
   (TridentNotebook).
2. **Silver (Sequential):** `bronze_to_silver_cleaning` — depends on all five
   bronze activities succeeding.
3. **Gold (Sequential):** `silver_to_gold` — depends on silver.
4. **Data Quality (Sequential):** `data_quality_checks` — depends on gold. Raises the
   blocking gate; see `data_quality_framework.md § 6`.

**Pipeline parameters:** `p_full_load`, `p_from_date`, `p_epi_year`. `p_epi_year` is
single-sourced to both EPI-aware notebooks; `p_full_load` / `p_from_date` drive the
incremental window in `bronze_to_silver` and `silver_to_gold`.

**Runtime:** ~20-30 minutes end-to-end (estimate)

**Commands:** `/run-full-pipeline`

## Best Practices Implemented

✅ **Immutable Bronze:** Never modify bronze data, always reprocess from source
✅ **Idempotent Transformations:** Running twice produces the same result. This became
true with task-024: `silver_procurement` and `fact_procurement` use **delete-insert over
the load window** (delete every row at or after the window's minimum date, then append the
window) rather than a natural-key MERGE. Re-running deletes and re-inserts exactly the
same rows. The earlier MERGE was *not* idempotent — it collapsed legitimate same-day
transactions onto one key, crashing on same-batch duplicates and silently overwriting
cross-run ones. See `incremental_load_strategy.md § 3`.
✅ **Delta Lake Format:** ACID transactions, time travel, schema evolution
✅ **Audit Trail:** Track all unmapped values and quality issues
✅ **No Data Loss:** Use placeholders instead of dropping unmapped data. No deduplication
is applied to procurement — two same-day purchases of the same material from the same
supplier are distinct transactions and both survive.

## Future Enhancements

📋 **True Incremental Load:** the delete-insert machinery is in place, but `p_from_date`
still defaults to `1900-01-01`, so today's "incremental" window is the full history —
correct and idempotent, just not yet efficient. Becomes genuinely incremental when the
high-water-mark tracking lands (task-029).
📋 **Partitioning:** (Task 12) - Partition by date for query performance
📋 **V-Order:** (Task 12) - Optimize for DirectLake queries
📋 **Silver Join Metrics:** capture per-join match rates (`data_quality_architecture.md § [1]`)
📋 **Warehouse Sync:** populate `oem_wh` as a SQL interface over gold, if wanted — no
pipeline activity does this today

## Related Files

- `/fabric/bronze_to_silver.Notebook/` - Silver transformation
- `/fabric/silver_to_gold.Notebook/` - Gold transformation
- `/fabric/orchestrator_pipeline_bronze_to_gold.DataPipeline/` - Orchestration
- `/.claude/commands/run-bronze.md` - Bronze ingestion guide
- `/.claude/commands/run-silver.md` - Silver transformation guide
- `/.claude/commands/run-gold.md` - Gold transformation guide
- `/project_definition.md` - Lines 109-320 (Data Architecture)
