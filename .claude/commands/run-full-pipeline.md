# Run Full Pipeline (Bronze → Gold)

Execute the complete end-to-end data pipeline from ingestion to warehouse sync.

## What This Command Does

This command runs `orchestrator_pipeline_bronze_to_gold` with all 4 stages:
1. **Bronze Ingestion** (Parallel) - Azure SQL, EPI, WGI, EU CRM → Bronze tables
2. **Silver Transformation** (Sequential) - Data cleaning → Silver tables
3. **Gold Transformation** (Sequential) - Business logic → Gold star schema
4. **Warehouse Sync** (Sequential) - Gold lakehouse → Warehouse tables

**Total Runtime:** ~20-30 minutes (measured estimate)

## Prerequisites

- Microsoft Fabric workspace access
- Source systems available (Azure SQL, data files)
- Lakehouse `oem_lh` and Warehouse `oem_wh` accessible
- Pipeline not already running (avoid concurrent executions)

## Steps

### Option 1: Run via Fabric UI (Recommended)

1. Navigate to Fabric workspace
2. Open pipeline: `orchestrator_pipeline_bronze_to_gold`
3. Click "Run" button
4. Configure parameters:
   ```
   p_full_load: true           # Full refresh (vs incremental)
   p_from_date: "1900-01-01"   # Load all historical data
   ```
5. Click "OK" to start execution
6. Monitor progress in "Output" tab

**Expected Timeline:**
```
00:00 - Start pipeline
00:00-08:00 - Bronze ingestion (4 sources in parallel)
08:00-13:00 - Silver transformation (data cleaning)
13:00-25:00 - Gold transformation (star schema creation)
25:00-28:00 - Warehouse sync
28:00 - Complete ✓
```

### Option 2: Run via the Fabric REST API (For automation)

Drives the pipeline over authenticated REST instead of the UI — no browser, no
Playwright. Uses the Fabric REST API at `api.fabric.microsoft.com`, **not** the
Azure Data Factory ARM management API (Fabric Data Pipelines are not exposed via
`management.azure.com/...Microsoft.DataFactory` — that path 404s, and a Fabric
trial capacity has no Azure subscription to target anyway).

**Prerequisite — authenticate once per session:**

```bash
az login --allow-no-subscriptions
# --allow-no-subscriptions is required: Fabric trial capacities have no Azure
# subscription, so plain `az login` errors with "No subscriptions found".
# This logs in at the tenant level, which is all the Fabric API needs.
az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv
# A long JWT printed = authenticated (~85 min token lifetime).
```

**Run via the project's REST driver:**

```bash
python3 -u .claude/support/workspace/run_orchestrator.py
# -u = unbuffered, so progress (itemId → trigger 202 → per-poll status →
# activity-run table) streams live instead of block-buffering.
```

What it does, end to end:
1. Lists workspace items to resolve the pipeline's REST itemId (the `.platform`
   `logicalId` ≠ REST itemId — they're byte-reversed renderings of the same GUID).
2. `POST /v1/workspaces/{ws}/dataPipelines/{itemId}/jobs/execute/instances` →
   `202` with a `Location` header whose trailing GUID is the job instance id.
3. Polls `GET /v1/workspaces/{ws}/items/{itemId}/jobs/instances/{jobId}` until
   terminal (Completed/Failed/Cancelled).
4. `POST .../datapipelines/pipelineruns/{runId}/queryactivityruns` (mandatory
   wide `lastUpdatedAfter`/`Before` window) → prints the activity-run table
   with per-activity status and duration.

Verified 2026-07-28 against the live workspace — full Bronze→Gold run, all 9
activities Succeeded. Operational contracts pinned in memory:
`az-login-fabric-trial-no-subscription`, `fabric-datapipeline-trigger-endpoint`,
`fabric-queryactivityruns-api`.

**Note — this fires the real pipeline.** No dry-run. To validate the plumbing
without a full run, stop after the item-id lookup (add a `--dry-run` flag, or
comment out the trigger POST) and print the resolved itemId + trigger payload.

### Option 3: Scheduled Execution

If pipeline scheduling is configured (see Task 10):
- Pipeline runs automatically at scheduled time (e.g., daily 6:00 AM)
- Check execution history to verify scheduled runs
- Monitor for failures via email notifications

## Pipeline Structure

```
orchestrator_pipeline_bronze_to_gold
│
├─[1] Bronze Layer (Parallel — 6 activities)
│   ├── bronze_copy_eu_supply_shares (Copy) ───────────┐
│   ├── bronze_copy_global_supply_shares (Copy) ───────┤
│   ├── bronze_copy_procurement_transactional (Copy) ┤
│   ├── bronze_copy_supplier_ref (Copy) ─────────────┤
│   ├── bronze_WGI (Notebook) ─────────────────────┤
│   └── bronze_EPI (Notebook) ─────────────────────┤
│                                                     ▼
├─[2] Silver Layer (Sequential) ────────────── [Wait for all 6 Bronze]
│   └── bronze_to_silver_cleaning (Notebook)
│                                                     │
├─[3] Gold Layer (Sequential) ───────────────────────┤
│   └── silver-to-gold (Notebook)                    │
│                                                     │
├─[4] Data Quality (Sequential) ─────────────────────┤
│   └── data_quality_checks (Notebook)               │
│                                                     │
└─[5] Error-Log Harvest (Sequential) ─────────────────┘
    └── pipeline_error_handler (Notebook)

No RefreshDataflow activities remain (task-035, task-048) — the pipeline is
SPN-safe. There is no Warehouse Sync stage; earlier revisions of this file
showed a "Copy job1 (InvokeCopyJob)" that does not exist in the pipeline.
```

## Monitoring

**During Execution:**
- Check "Output" tab in pipeline UI for activity status
- Green check = Activity succeeded
- Red X = Activity failed
- Yellow spinner = Activity running

**Post-Execution:**
1. **Execution History:**
   - Navigate to pipeline → "Runs" tab
   - View past executions with timestamps and status

2. **Lakehouse Tables:**
   - Open `oem_lh` lakehouse
   - Verify tables exist in Tables folder
   - Check table properties for row counts and refresh times

3. **Warehouse Tables:**
   - Open `oem_wh` warehouse
   - Query tables via SQL endpoint
   - Verify data matches lakehouse

4. **Semantic Model:**
   - Open `OEMInsightBI_v2`
   - DirectLake should automatically reflect new data
   - No manual refresh needed

5. **Power BI Report:**
   - Open report in Fabric or Power BI Service
   - Verify visuals show updated data
   - Check last refresh timestamp

## Validation

After pipeline completes successfully:

```python
# Comprehensive validation script
from pyspark.sql import SparkSession

# Bronze layer validation
bronze_counts = {
    "bronze_procurement_transactional": spark.table("oem_lh.bronze_procurement_transactional").count(),
    "bronze_supplier_ref": spark.table("oem_lh.bronze_supplier_ref").count(),
    "bronze_epi2024results": spark.table("oem_lh.bronze_epi2024results").count(),
    "bronze_WB_ESGCSV": spark.table("oem_lh.bronze_WB_ESGCSV").count(),
    "bronze_GlobalSupplyShares": spark.table("oem_lh.bronze_GlobalSupplyShares").count()
}

# Silver layer validation
silver_counts = {
    "silver_procurement": spark.table("oem_lh.silver_procurement").count(),
    "silver_epi2024results": spark.table("oem_lh.silver_epi2024results").count(),
    "silver_WB": spark.table("oem_lh.silver_WB").count(),
    "silver_globalsupplyshares": spark.table("oem_lh.silver_globalsupplyshares").count()
}

# Gold layer validation
gold_counts = {
    "fact_procurement": spark.table("oem_lh.fact_procurement").count(),
    "fact_supply_share": spark.table("oem_lh.fact_supply_share").count(),
    "fact_epi_score": spark.table("oem_lh.fact_epi_score").count(),
    "gold_dim_country": spark.table("oem_lh.gold_dim_country").count(),
    "gold_dim_material": spark.table("oem_lh.gold_dim_material").count()
}

# Print validation report
for layer, counts in [("Bronze", bronze_counts), ("Silver", silver_counts), ("Gold", gold_counts)]:
    print(f"\n{layer} Layer:")
    for table, count in counts.items():
        print(f"  {table}: {count:,} rows")

# Data quality check
unmapped_count = spark.table("oem_lh.gold_unmapped_procurement_audit").count()
print(f"\nUnmapped procurement records: {unmapped_count} (lower is better)")
```

## Troubleshooting

**Pipeline Fails at Bronze Stage:**
- Check source system connectivity (Azure SQL, HTTP endpoints)
- Verify the Fabric connection `oem_azuresql_procurement` is bound (Manage connections
  and gateways → Connections) — bronze ingestion is via Copy activities (Azure SQL) and
  TridentNotebook activities (EPI/WGI), not dataflow refreshes (task-035, task-048)
- Review activity error message in "Output" tab
- See `/run-bronze` command for detailed troubleshooting

**Pipeline Fails at Silver Stage:**
- Check bronze tables exist and have data
- Review notebook execution logs
- Verify Spark compute pool is running
- See `/run-silver` command for detailed troubleshooting

**Pipeline Fails at Gold Stage:**
- Check silver tables exist and have expected row counts
- Review gold transformation notebook logs
- Check for memory issues (increase Spark executor memory)
- See `/run-gold` command for detailed troubleshooting

**Pipeline Fails at Warehouse Sync:**
- Verify warehouse is online and accessible
- Check for schema mismatches between lakehouse and warehouse
- Review copy job configuration

**Pipeline Succeeds but Data Looks Wrong:**
- Run `/check-quality` to review data quality metrics
- Run `/view-unmapped` to see unmapped values
- Compare row counts across layers (bronze → silver → gold)
- Check audit tables for warnings

## Performance Optimization

If pipeline runtime exceeds 30 minutes, consider:
1. Implement incremental load (Task 06)
2. Optimize notebook transformations (Task 12)
3. Add partitioning to large fact tables
4. Review Spark configuration (executor memory, cores)

## Next Steps

After successful pipeline execution:
1. Run `/check-quality` to validate data quality
2. Review Power BI report to verify visuals updated
3. Check semantic model refresh time
4. If issues found, investigate with specific `/run-*` commands

## Related Files

- `/fabric/orchestrator_pipeline_bronze_to_gold.DataPipeline/`
- `/docs/architecture/orchestration.md`
- `/.claude/tasks/10_configure_pipeline_scheduling.md`
- `/.claude/tasks/11_implement_error_handling.md`
- `/.claude/tasks/12_optimize_performance.md`
