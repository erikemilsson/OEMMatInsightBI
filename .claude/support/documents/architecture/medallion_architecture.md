# Medallion Architecture - OEMMatInsightBI

## Overview

The project implements a **medallion architecture** (bronze → silver → gold) for data transformation, following lakehouse best practices.

## Architecture Diagram

```
┌─────────────────────┐
│   Source Systems    │
│  - Azure SQL DB     │
│  - EPI CSV Files    │
│  - WGI CSV Files    │
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
│   epi2024results    │
│ - bronze_WB_ESGCSV  │
│ - bronze_WB_        │
│   ESGSeries         │
│ - bronze_Global     │
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
│   epi2024results    │
│ - silver_WB         │
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
│   WAREHOUSE SYNC    │
│  (SQL Interface)    │
│                     │
│ oem_wh warehouse    │
│ (mirrors gold)      │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  SEMANTIC MODEL     │
│  (DirectLake)       │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   POWER BI REPORT   │
│  (Visualizations)   │
└─────────────────────┘
```

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
- `bronze_procurement_transactional` - Procurement transactions
- `bronze_supplier_ref` - Supplier reference data
- `bronze_epi2024results` - Environmental Performance Index
- `bronze_WB_ESGCSV` - World Bank WGI data
- `bronze_WB_ESGSeries` - WGI metadata
- `bronze_GlobalSupplyShares` - EU CRM supply concentration

**Ingestion Methods:**
- Dataflows (Azure SQL, file uploads)
- Copy activities (HTTP sources)

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
3. **WGI:** Unpivot year columns, filter to 2020, join with metadata
4. **Procurement:** Join with supplier_ref, standardize column names

**Tables:**
- `silver_procurement` - Cleaned procurement with supplier info
- `silver_epi2024results` - Cleaned EPI data
- `silver_WB` - Unpivoted and filtered WGI data
- `silver_globalsupplyshares` - Cleaned supply shares

**Notebook:** `bronze-to-silver.Notebook`

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
- `gold_data_quality_metrics` - Quality summary statistics
- `gold_country_coverage_matrix` - Country presence across sources

**Notebook:** `silver-to-gold2.Notebook`

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

**Stages:**
1. **Bronze (Parallel):** 4 sources ingested simultaneously
2. **Silver (Sequential):** Wait for all bronze, then transform
3. **Gold (Sequential):** Wait for silver, then apply business logic
4. **Warehouse Sync (Sequential):** Copy gold to warehouse for BI

**Runtime:** ~20-30 minutes end-to-end (estimate)

**Commands:** `/run-full-pipeline`

## Best Practices Implemented

✅ **Immutable Bronze:** Never modify bronze data, always reprocess from source
✅ **Idempotent Transformations:** Running twice produces same result
✅ **Delta Lake Format:** ACID transactions, time travel, schema evolution
✅ **Audit Trail:** Track all unmapped values and quality issues
✅ **No Data Loss:** Use placeholders instead of dropping unmapped data

## Future Enhancements

📋 **Incremental Load:** (Task 06) - Only process changed records
📋 **Partitioning:** (Task 12) - Partition by date for query performance
📋 **V-Order:** (Task 12) - Optimize for DirectLake queries
📋 **Data Quality Checks:** (Task 07) - Automated validation at each layer

## Related Files

- `/fabric/bronze-to-silver.Notebook/` - Silver transformation
- `/fabric/silver-to-gold2.Notebook/` - Gold transformation
- `/fabric/orchestrator_pipeline_bronze_to_gold.DataPipeline/` - Orchestration
- `/.claude/commands/run-bronze.md` - Bronze ingestion guide
- `/.claude/commands/run-silver.md` - Silver transformation guide
- `/.claude/commands/run-gold.md` - Gold transformation guide
- `/project_definition.md` - Lines 109-320 (Data Architecture)
