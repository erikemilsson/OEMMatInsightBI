# Microsoft Fabric Workspace Configuration

## Workspace Details

**Workspace Name:** (TBD - verify in Fabric UI)

**Workspace ID:** `99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9`
- Source: Notebook metadata files in `/fabric` directory

**Capacity:** Trial-20240714 (F64 SKU)
- **Capacity Units:** 64 CU
- **Region:** Sweden Central
- **Type:** Trial capacity (for portfolio development)

**Environment:** Personal Development / Portfolio Project

## Workspace Architecture

### Lakehouse: `oem_lh`

**Lakehouse ID:** `488fb9f8-e635-4683-90c4-ba4fee9dfadb`

**Purpose:** Primary data storage using Delta Lake format

**Storage Structure:**
```
oem_lh/
├── Files/
│   ├── /config/ (configuration files if used)
│   ├── /schema_exports/ (for Claude Code sync)
│   ├── /dq_reports/ (data quality exports)
│   └── /scripts/ (utility scripts)
└── Tables/
    ├── bronze_* (raw ingestion tables)
    ├── silver_* (cleaned/validated tables)
    └── gold_* (business-ready star schema)
```

**Format:** Delta Lake (Apache Parquet with transaction log)

**Optimization:**
- V-Order: Pending implementation (Task 12)
- Partitioning: Pending implementation (Task 12)
- Compaction: Automatic via Delta Lake

### Warehouse: `oem_wh`

**Warehouse ID:** `b1cb7506-8d2d-4e4a-97cc-2b580da8eda0`

**Purpose:** SQL-queryable layer over gold — **not currently in the data flow**

**Connection:**
- **Endpoint:** `2BINPJYTVAEEVEF26XKMILPX4E-NXGOJGODN2TUTLWZW2NQJKL2VE.datawarehouse.fabric.microsoft.com`
- **Database ID:** `b1cb7506-8d2d-4e4a-97cc-2b580da8eda0`
- **Authentication:** Workspace identity (automatic)

**Tables/Views:**
- `fabric/oem_wh.Warehouse/dbo/Tables/` holds DDL for the 3 facts + 5 dimensions
- Schema: `dbo` (default)

> ⚠️ **Nothing populates this warehouse.** No pipeline activity syncs gold → `oem_wh`,
> and the semantic model does not read from it (see below). The DDL is real; the data
> flow into it is not. Treat the warehouse as a future SQL-interface option, not as part
> of the current architecture — see `architecture/medallion_architecture.md`.

### Semantic Model: `OEMInsightBI_v2`

**Type:** DirectLake

**Connection:** DirectLake on the **`oem_lh` lakehouse** — `definition/expressions.tmdl`
declares a single expression, `'DirectLake - oem_lh'`. It does **not** connect to the
`oem_wh` warehouse; the report reads the gold Delta tables in the lakehouse directly.

**Refresh:** Automatic (no explicit refresh needed with DirectLake)

**Tables:**
- 3 fact tables: fact_procurement, fact_supply_share, fact_epi_score
- 5 dimension tables: gold_dim_country, gold_dim_date, gold_dim_indicator, gold_dim_material, gold_dim_stage

### Power BI Report: `report2.Report`

**Connected Model:** `OEMInsightBI_v2`

**Theme:** CY24SU10.json (Fabric default theme)

**Pages:** (Pending redesign - see Task 03)

## Artifacts Inventory

### Notebooks (8)

All PySpark, all attached to the `oem_lh` lakehouse.

**In the orchestrator pipeline:**
1. **bronze_ingest_epi.Notebook** — downloads the EPI CSV → `bronze_epi{year}results`, parameterised on `p_epi_year`
2. **bronze_ingest_wgi.Notebook** — World Bank API v2 → `bronze_WGI`
3. **bronze-to-silver.Notebook** — Bronze → Silver transformation
4. **silver-to-gold2.Notebook** — Silver → Gold transformation
5. **data_quality_checks.Notebook** — post-gold DQ checks; raises the blocking gate

**Not in the pipeline (run on demand):**
6. **pipeline_error_handler.Notebook** — error-path handling
7. **data_quality_analysis.Notebook** — ad-hoc quality analysis
8. **sample-quality-data.Notebook** — seeds sample rows into the observability tables

### Dataflows (1 live, 2 retired)
1. **bronze_azureSQLdb2table.Dataflow** — ✅ live
   - Source: Azure SQL Database
   - Destination: bronze_procurement_transactional, bronze_supplier_ref
   - Language: Power Query M
   - Driven by the pipeline's `bronze_procurement` RefreshDataflow activity

2. **EPI_file2table.Dataflow** — ⚠️ retired
   - Superseded by `bronze_ingest_epi.Notebook`. The artifact is still on disk but no
     pipeline activity refreshes it.

3. **WGI_file2table.Dataflow** — ⚠️ retired
   - Superseded by `bronze_ingest_wgi.Notebook`. It wrote `bronze_WB_ESGCSV` +
     `bronze_WB_ESGSeries` (wide Excel extract, 2023 percentile ranks); those tables no
     longer exist and `bronze-to-silver` hard-fails if `bronze_WGI` still carries that
     shape. See `schemas/bronze_tables.md`.

### Pipelines (1)
1. **orchestrator_pipeline_bronze_to_gold.DataPipeline**
   - Purpose: End-to-end orchestration
   - Activities: **8** — 5 bronze (2 Copy, 1 RefreshDataflow, 2 TridentNotebook),
     1 silver, 1 gold, 1 data-quality. **No warehouse-sync activity.**
   - Parameters: `p_full_load`, `p_from_date`, `p_epi_year`
   - Schedule: Manual (pending Task 10)

### Copy Jobs (0)

None. `copyjob1.CopyJob` ("sync gold lakehouse → warehouse") was **archived** in the
2025-12-15 artifact cleanup and exists only under
`.archive/fabric-cleanup-20251215-132143/` — it is not a workspace artifact and nothing
triggers it. See `docs/architecture/fabric-artifacts-inventory.md`.

## Git Integration

**Status:** Project connected to Git repository

**Current Approach:**
- Direct commits to main branch
- Single developer workflow
- Manual sync between local and Fabric

**Desired Workflow (from project_definition.md):**
- Morning: Pull from Git → Fabric
- Development: Local changes → commit → push
- Evening: Fabric changes → commit → pull locally

**Configuration:** (Needs verification)
- Repository: Local git repository synced to Fabric
- Branch: main
- Sync Frequency: Manual

## Access Control

**Current:** Single developer (personal workspace)

**Authentication:**
- Workspace access: Owner permissions
- Azure SQL: Service identity or SQL authentication (TBD)
- External data sources: No authentication (public data)

**Row-Level Security:** Not implemented (see Task 04)

**Future State:**
- RLS roles for regional/category managers
- Read-only access for stakeholders
- Admin access for data engineering team

## Resource Quotas & Limits

**Fabric Trial Capacity (F64):**
- Compute Units: 64 CU
- Storage: Limited by trial terms
- Refresh frequency: No strict limits during trial
- Concurrent operations: Limited by capacity

**Known Limits:**
- Notebook size: Max 10MB
- Dataflow size: Max 100MB
- Pipeline timeout: 12 hours per activity
- DirectLake: Table size recommendations (<1GB per table for optimal performance)

## Monitoring & Operations

**Available Monitoring:**
- Workspace monitoring page (pipeline runs, notebook executions)
- Lakehouse table metrics (row counts, storage size, last refresh)
- Warehouse query performance metrics
- Capacity metrics (CU consumption)

**Logging:**
- Pipeline execution history
- Notebook run logs
- Error messages and stack traces

**Alerting:** Not configured (see Task 11)

## Backup & Recovery

**Git-Tracked Artifacts:**
- All artifact definitions backed up in Git
- Notebooks, pipelines, dataflows version-controlled

**Data:**
- Lakehouse data: No automatic backup (Delta Lake provides versioning)
- Time travel: Delta Lake retains history (default 30 days)
- Recovery: Re-run pipeline from source systems

**Disaster Recovery Plan:**
- Recreate workspace from Git repository
- Re-run full pipeline (p_full_load=true)
- Rebuild semantic model connections
- Republish Power BI report

## Development Workflow

**Current State:**
1. Develop in Fabric UI (notebooks, dataflows)
2. Test with real data in workspace
3. Manually export/commit to Git (inconsistent)

**Desired State (see project_definition.md lines 997-1013):**
1. **Morning (Claude Code):** Pull from Git, sync state, review tasks, develop locally
2. **Afternoon (Fabric UI):** Pull branch, test with real data, run DQ checks, commit results
3. **Evening (Claude Code):** Pull latest, review issues, create tasks, plan next day

## Environment Separation

**Current:** Single environment (dev/prod combined)

**Future Enhancement:**
- **Dev Workspace:** For active development and testing
- **Prod Workspace:** For stakeholder consumption (read-only)
- **CI/CD Pipeline:** Automated deployment from Git

## Performance Optimization Status

**Current:**
- Default Spark configurations
- No partitioning
- No V-Order optimization
- No warehouse indexing

**Planned (Task 12):**
- V-Order enabled on gold tables
- Partitioning on large fact tables (by date)
- Warehouse indexes on foreign keys
- Query performance monitoring

## Troubleshooting

**Common Issues:**

1. **Lakehouse not accessible:**
   - Check workspace permissions
   - Verify lakehouse is online (not paused)
   - Restart Spark session in notebook

2. **Pipeline halts after `silver-to-gold`:**
   - The `data_quality_checks` activity raised the **blocking gate** — a check in
     `BLOCKING_CHECKS` returned `status = 'fail'`
   - Read the failing check from `gold_quality_history` (`producer = 'data_quality_checks'`,
     `status = 'fail'`) rather than from the score, which does not drive the gate
   - See `data_quality_framework.md § 6` for the blocking set and the
     score-vs-gate distinction

3. **DirectLake not working:**
   - Verify the semantic model's `'DirectLake - oem_lh'` expression points at the
     **lakehouse** (`oem_lh`), not the warehouse
   - Check table schemas match model definitions
   - Refresh semantic model metadata

4. **Pipeline timeouts:**
   - Review activity timeout settings (currently 12 hours)
   - Check Spark logs for performance issues
   - Consider incremental load (Task 06)

## Related Files

- `/fabric/` - All Fabric artifacts
- `/.claude/commands/sync-from-fabric.md` - Pull changes from workspace
- `/.claude/commands/sync-to-fabric.md` - Push changes to workspace
- `/project_definition.md` - Lines 1176-1260 (Infrastructure section)
