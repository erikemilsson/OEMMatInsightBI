# Pipeline Orchestration - OEMMatInsightBI

## Overview

**Pipeline Name:** `orchestrator_pipeline_bronze_to_gold.DataPipeline`
**Purpose:** End-to-end data orchestration from source ingestion to warehouse sync
**Execution:** Scheduled — daily 06:00 Europe/Stockholm, active since 2026-08-05 (task-010). Manual on-demand runs remain available.
**Runtime:** ~18-19 minutes (measured 2026-07-31, run `b56a43b9`)

> **Accuracy note (2026-07-31).** This document had drifted badly: it described 4
> bronze activities (there are 6), called `bronze_wgi` / `bronze_EPI`
> RefreshDataflows (task-035 made them notebooks), claimed 0 retries everywhere
> (task-011 set real policies), omitted `data_quality_checks` and
> `pipeline_error_handler` (task-022 / task-026), and documented a Stage 4
> `InvokeCopyJob` that is not in the pipeline. Every activity/type/policy figure
> below is now read from the live definition, and runtimes are measured from run
> `b56a43b9` rather than estimated.

## Pipeline Architecture

```
START
  │
  ├──[STAGE 1: Bronze Ingestion - PARALLEL]──────────────┐
  │   │                                                    │
  │   ├─ bronze_copy_eu_supply_shares            (Copy)      │
  │   ├─ bronze_copy_global_supply_shares        (Copy)      │
  │   ├─ bronze_copy_procurement_transactional (Copy)      │
  │   ├─ bronze_copy_supplier_ref              (Copy)      │
  │   ├─ bronze_wgi                           (Notebook)  │
  │   └─ bronze_EPI                           (Notebook)  │
  │                                                        │
  │   [All 6 activities complete]                         │
  │                      ▼                                 │
  ├──[STAGE 2: Silver Transformation - SEQUENTIAL]────────┤
  │   │                                                    │
  │   └─ bronze_to_silver_cleaning       (Notebook)  │
  │                      ▼                                 │
  ├──[STAGE 3: Gold Transformation - SEQUENTIAL]──────────┤
  │   │                                                    │
  │   └─ silver_to_gold                       (Notebook)  │
  │                      ▼                                 │
  ├──[STAGE 4: Data Quality - SEQUENTIAL]─────────────────┤
  │   │                                                    │
  │   └─ data_quality_checks                  (Notebook)  │
  │                      ▼                                 │
  └──[STAGE 5: Error Handling - SEQUENTIAL]───────────────┘
      │
      └─ pipeline_error_handler               (Notebook)
                      ▼
                    END
```

**No RefreshDataflow activities remain.** This is deliberate and load-bearing for
CI/CD: a service principal cannot refresh a Dataflow Gen2
(`SPNBasedRefreshNotAllowed`), and every `fabric-cicd` publish strips a Gen2's
stored credentials. task-035 converted WGI/EPI to notebooks; task-048 replaced the
last one (`bronze_procurement`) with two Copy activities and retired
`bronze_azureSQLdb2table`. The pipeline is therefore SPN-safe end to end.

## Activity Details

### Stage 1: Bronze Ingestion (Parallel)

**Execution:** All 6 activities run simultaneously (each has an empty `dependsOn`)

All activities carry a 12-hour timeout. Retry columns are the live values set by
task-011; runtimes are measured from run `b56a43b9` (2026-07-31).

| # | Activity | Type | Source → Output | Retry | Runtime |
|---|----------|------|-----------------|-------|---------|
| 1 | `bronze_copy_eu_supply_shares` | Copy | HTTP (GitHub CSV) → `bronze_eu_supply_shares` | 3 / 300s | 28s |
| 2 | `bronze_copy_global_supply_shares` | Copy | HTTP (GitHub CSV) → `bronze_global_supply_shares` | 3 / 300s | 25s |
| 3 | `bronze_copy_procurement_transactional` | Copy | Azure SQL `dbo.procurement_transactional` → `bronze_procurement_transactional` | 3 / 300s | 27s |
| 4 | `bronze_copy_supplier_ref` | Copy | Azure SQL `dbo.supplier_ref` → `bronze_supplier_ref` | 3 / 300s | 25s |
| 5 | `bronze_wgi` | Notebook | World Bank API → `bronze_wgi` | 2 / 30s | 119s |
| 6 | `bronze_EPI` | Notebook | Yale EPI CSV → `bronze_epi2024results` + related | 2 / 30s | 104s |

**Stage 1 Total:** ~2 minutes (parallel; bounded by `bronze_wgi`)

#### Azure SQL ingestion notes (activities 3 and 4)

Both bind to the Fabric connection `oem_azuresql_procurement`
(`da9667d6-9df0-492e-83e0-de4a55fc388e`, path
`procurement-supplier.database.windows.net;procurement-supplier-db`, Basic auth).
The connection must be shared with the `Fabric-SPN-Access` security group or an
SPN-driven publish fails with *"User does not have access to the connection used
in the Pipeline"*.

**Bronze is deliberately raw here.** The retired dataflow corrected the source's
day/year-transposed dates during ingestion; a Copy activity cannot transform, so
that correction now lives in `bronze_to_silver` as `correct_procurement_date`, and
bronze holds the source's malformed dates verbatim. This is better medallion
practice, but it means **bronze `Date` values are not directly usable** — read
silver instead.

**The database is Azure SQL serverless** (`GP_S_Gen5`, `autoPauseDelay: 60`). A run
starting after 60 minutes of database idleness hits the resume window and the first
Copy attempt fails with *"Database ... is not currently available"* — which is a
pause, not a credential problem. The 300-second retry interval comfortably exceeds
the observed ~41s resume, so attempt 2 succeeds. **Do not set these two activities
to retry 0.**

### Stage 2: Silver Transformation (Sequential)

**Depends On:** All **6** bronze activities (Succeeded)

#### 7. bronze_to_silver_cleaning
- **Type:** Notebook Activity
- **Notebook:** `bronze_to_silver.Notebook`
- **Output:** `silver_epi2024results`, `silver_globalsupplyshares`, `silver_wgi`, `silver_procurement`
- **Timeout:** 12 hours — **Retry:** 2 / 120s — **Runtime:** 141s (measured)
- **Owns the procurement date correction** (task-048): `correct_procurement_date`
  undoes the source's day/year transposition —
  `make_date(day + 2000, month, year - 2000)` — and is applied **at the bronze read,
  before the incremental look-back window**. That ordering is load-bearing: the
  watermark (`bronze_load_metadata.last_load_date`) and the delete-insert boundary
  (`window_min_date`) are both expressed in corrected-date space, so windowing raw
  dates would delete a range the append never restores. Rows whose corrected
  components are not a real calendar date become NULL rather than failing the run.

### Stage 3: Gold Transformation (Sequential)

**Depends On:** bronze_to_silver_cleaning (Succeeded)

#### 8. silver_to_gold
- **Type:** Notebook Activity
- **Notebook:** `silver_to_gold.Notebook`
- **Output:** Gold fact and dimension tables (8 tables + supporting tables)
- **Timeout:** 12 hours — **Retry:** 2 / 120s — **Runtime:** 488s (measured; the slowest activity)

### Stage 4: Data Quality (Sequential)

**Depends On:** silver_to_gold (Succeeded)

#### 9. data_quality_checks
- **Type:** Notebook Activity
- **Notebook:** `data_quality_checks.Notebook`
- **Output:** Quality observability tables
- **Timeout:** 12 hours — **Retry:** 1 / 120s — **Runtime:** 263s (measured)

### Stage 5: Error Handling (Sequential)

**Depends On:** data_quality_checks (Succeeded)

#### 10. pipeline_error_handler
- **Type:** Notebook Activity
- **Notebook:** `pipeline_error_handler.Notebook`
- **Purpose:** Harvest per-activity outcomes into `gold_pipeline_execution_log`
- **Timeout:** 12 hours — **Retry:** 0 / 30s — **Runtime:** 82s (measured)
- **Note:** this runs on the *Succeeded* path as the pipeline's final step — it is a
  logging/harvest stage, not a failure branch.

> **There is no Warehouse Sync stage, and no warehouse.** Earlier revisions of this
> document described a Stage 4 `Copy job1` (`InvokeCopyJob`) syncing gold to `oem_wh`;
> no such activity ever existed. A later revision claimed a separately-maintained
> "warehouse analytics layer (4 views + 2 stored procedures in `oem_wh`)" — that was
> also wrong. A live catalogue query on 2026-08-10 returned 8 tables and **zero views,
> zero stored procedures**; those objects were specified but never built. The `oem_wh`
> warehouse was retired the same day
> (`.claude/support/retired/oem-wh-warehouse/manifest.json`). The three `v_*` view names
> that do exist are Spark-catalog views created inside `silver_to_gold.Notebook` over the
> lakehouse, invisible to any SQL endpoint.

## Pipeline Parameters

### p_full_load (Boolean)
- **Default:** false
- **Purpose:** Force a full reload rather than the incremental path
- **Usage:** Read by `bronze_to_silver`; when true, silver reads all of bronze

### p_from_date (String)
- **Default:** "1900-01-01"
- **Purpose:** Start date driving the incremental look-back
- **Usage:** Read by `bronze_to_silver`, which applies a **7-day look-back** window
  (`Date >= p_from_date − 7 days`) against the **corrected** silver dates. The
  default `1900-01-01` yields a look-back of 1899-12-25, i.e. effectively a full
  load.
- **Scope:** this parameter has **never** reached bronze ingestion. The retired
  `bronze_procurement` RefreshDataflow activity passed no parameters, so the
  dataflow's own `p_from_date` always sat at its `"1900-01-01"` default and bronze
  always full-loaded (independently confirmed by task-029). The replacing Copy
  activities are likewise full-table copies. **Incrementality lives in silver, not
  in bronze** — the parameter contract is unchanged, only its documented location.

### procurement_array (Array)
- **Purpose:** Source-to-sink mappings (`dbo.Suppliers`→`bronze_suppliers`,
  `dbo.Materials`→`bronze_materials`, `dbo.Purchases`→`bronze_purchases`)
- **Usage:** **Not consumed by any current activity.** The sink names do not match
  the tables the pipeline actually produces. Treat as vestigial pending an audit.

## Error Handling

**Current Strategy:** Retry-then-fail, with policies set per activity by task-011.
Copy activities retry 3× at 300s; bronze notebooks 2× at 30s; silver/gold 2× at
120s; `data_quality_checks` 1× at 120s; `pipeline_error_handler` 0×.

The 300s Copy interval is sized for the Azure SQL serverless resume window (see
Stage 1 notes) — it is not arbitrary.

**Error logging:** `pipeline_error_handler` harvests per-activity outcomes into
`gold_pipeline_execution_log`, deriving the retry ordinal by ranking same-activity
rows on `activityRunStart`. This is deliberate: Fabric's `queryactivityruns` API
returns `retryAttempt: null` even for activities that did retry, so the field
cannot be trusted (task-037 / task-041).

**Notifications:** **descoped 2026-08-05** (task-010) — no email sink is configured
and none is planned. The tenant cannot deliver one: the Schedule pane's
Failure-notifications field rejects addresses outside the organization, and the
only tenant principal is a `.onmicrosoft.com` account with no Exchange mailbox, so
a configured alert would fire into a void. Failure **detection** is unaffected and
is the load-bearing property: `pipeline_error_handler` runs on every outcome,
logs per-activity rows to `gold_pipeline_execution_log`, and re-raises on a
final-attempt FAILED. Resolves the criterion DEC-004 parked at task-010; see
`docs/guides/pipeline_schedule.md § Failure Notifications` for upgrade paths.

## Dependencies

**Execution Order:**
```
6 Bronze Activities (parallel, no dependencies)
    ↓ (wait for all 6)
Silver Transformation
    ↓ (wait for completion)
Gold Transformation
    ↓ (wait for completion)
Data Quality Checks
    ↓ (wait for completion)
Error-Log Harvest
```

Every edge uses `dependencyConditions: ["Succeeded"]`.

**Data Dependencies:**
- Silver requires bronze tables
- Gold requires silver tables
- Report requires gold (DirectLake)

## Monitoring

### During Execution
- Open pipeline in Fabric workspace
- View "Output" tab for real-time activity status
- Green check = Success, Red X = Failure, Yellow spinner = Running

### Post-Execution
- **Run History:** View past executions with status, duration, timestamps
- **Activity Logs:** Click individual activity for detailed logs
- **Error Messages:** Available in failed activity details

### Metrics to Track
- Pipeline success rate (target: >95%)
- Runtime trends (identify slowdowns)
- Activity failure patterns (which activities fail most?)
- Data volume growth (row counts over time)

## Scheduling (Active since 2026-08-05 — task-010)

**Configured Schedule:**
- **Frequency:** Daily
- **Time:** 06:00 Europe/Stockholm
- **Timezone:** `W. Europe Standard Time` — the Windows zone id Fabric stores, whose label reads "(UTC+01:00) Amsterdam, Berlin, Bern, Rome, **Stockholm**, Vienna". Tracks CET/CEST DST automatically. *(Corrected 2026-08-05: previously read "Sweden Central (datacenter region)", which conflated a capacity region with a time zone — they are unrelated.)*
- **Trigger Type:** Scheduled (time-based), schedule id `17288b67-a36f-4db8-88fe-cfa4ce1dba61`, enabled, end date 2099-01-01
- **Verified:** a test firing **against a temporary 22:20 test time** started at `2026-08-05T20:20:00.63Z` — the exact specified minute — and completed in 21.9 min as the first `invokeType=Scheduled` invocation in 58 runs. The schedule was then reset to 06:00; **that first morning firing is unobserved until 2026-08-06.**

**Rationale:**
- Procurement data refreshed nightly in Azure SQL (by 5:00 AM)
- 6:00 AM ensures fresh data for morning reports
- External datasets (EPI, WGI) refresh automatically but only change annually

## Performance Optimization (Task 12)

**Current Bottlenecks:** (To be measured)
- Bronze ingestion: Copy activity throughput (Azure SQL) and TridentNotebook run times
  (EPI/WGI) — there are no dataflow refreshes on the pipeline (task-035, task-048)
- Gold transformation: Complex surrogate key generation and alias resolution
- Warehouse sync: Large table copy

**Optimization Strategies:**
1. **Incremental Load** (Task 06) - Only process changed data
2. **Partitioning** - Partition large facts by date
3. **Parallel Activities** - Already implemented in Stage 1
4. **Caching** - Cache frequently accessed DataFrames in notebooks
5. **Broadcast Joins** - Use broadcast hints for small dimensions

## Execution Commands

### Run Full Pipeline
```bash
# Via Fabric UI
1. Navigate to workspace
2. Open "orchestrator_pipeline_bronze_to_gold"
3. Click "Run"
4. Set parameters: p_full_load=true, p_from_date="1900-01-01"
5. Monitor in Output tab
```

**Claude Code Command:** `/run-full-pipeline`

### Run Individual Stages
- Bronze only: `/run-bronze`
- Silver only: `/run-silver`
- Gold only: `/run-gold`

**Note:** Running individual stages requires previous stage completion.

## Troubleshooting

### Pipeline Stuck/Not Starting
- Check Fabric capacity status (may be paused or over-utilized)
- Verify no concurrent pipeline runs (limit: depends on capacity)
- Restart pipeline manually

### Activity Timeout
- Review activity timeout setting (currently 12 hours - very generous)
- Check notebook activity logs for infinite loops or hangs (there are no dataflow
  refreshes on the pipeline path — task-035, task-048)
- Increase timeout if legitimately long-running

### Activity Failure - Retry Exhausted
- Check activity error message in "Output" tab
- Review source system connectivity (Azure SQL, HTTP endpoints)
- Validate data schemas haven't changed
- See activity-specific troubleshooting in `/run-*` commands

### Data Quality Issues Post-Pipeline
- Run `/check-quality` to review DQ metrics
- Run `/view-unmapped` to see unmapped values
- Check audit tables: gold_unmapped_procurement_audit, gold_unmapped_supply_audit

## Pipeline Maintenance

**Weekly:**
- Review execution history for patterns
- Check for new unmapped values
- Validate data quality trends

**Monthly:**
- Review pipeline runtime trends (identify slowdowns)
- Optimize slow activities
- Update retry/timeout settings based on experience

**Annually:**
- Update external data sources (EPI, WGI) when new releases available
- Review and update business rules
- Refactor notebooks for maintainability

## Related Files

- `/fabric/orchestrator_pipeline_bronze_to_gold.DataPipeline/` - Pipeline definition
- `/.claude/commands/run-full-pipeline.md` - Execution guide
- `/.claude/commands/run-bronze.md` - Bronze stage details
- `/.claude/commands/run-silver.md` - Silver stage details
- `/.claude/commands/run-gold.md` - Gold stage details
- `/.claude/tasks/10_configure_pipeline_scheduling.md` - Scheduling task
- `/.claude/tasks/11_implement_error_handling.md` - Error handling improvements
- `/project_definition.md` - Lines 604-716 (Orchestration section)
