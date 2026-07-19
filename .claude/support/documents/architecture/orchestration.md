# Pipeline Orchestration - OEMMatInsightBI

## Overview

**Pipeline Name:** `orchestrator_pipeline_bronze_to_gold.DataPipeline`
**Purpose:** End-to-end data orchestration from source ingestion to warehouse sync
**Execution:** Currently manual (scheduled execution planned in Task 10)
**Runtime:** ~20-30 minutes (estimated)

## Pipeline Architecture

```
START
  │
  ├──[STAGE 1: Bronze Ingestion - PARALLEL]──────────────┐
  │   │                                                    │
  │   ├─ bronzecopy_EUSupplyShares (Copy Activity)        │
  │   ├─ bronze_WGI (RefreshDataflow)                     │
  │   ├─ bronze_procurement (RefreshDataflow)             │
  │   └─ bronze_EPI (RefreshDataflow)                     │
  │                                                        │
  │   [All 4 activities complete]                         │
  │                      ▼                                 │
  ├──[STAGE 2: Silver Transformation - SEQUENTIAL]────────┤
  │   │                                                    │
  │   └─ bronze-to-silver data cleaning (Notebook)        │
  │                      ▼                                 │
  ├──[STAGE 3: Gold Transformation - SEQUENTIAL]──────────┤
  │   │                                                    │
  │   └─ silver-to-gold (Notebook)                        │
  │                      ▼                                 │
  └──[STAGE 4: Warehouse Sync - SEQUENTIAL]───────────────┘
      │
      └─ Copy job1 (InvokeCopyJob)
                      ▼
                    END
```

## Activity Details

### Stage 1: Bronze Ingestion (Parallel)

**Execution:** All 4 activities run simultaneously

#### 1. bronzecopy_EUSupplyShares
- **Type:** Copy Activity
- **Source:** HTTP (GitHub CSV)
- **Destination:** bronze_GlobalSupplyShares (oem_lh)
- **Timeout:** 12 hours
- **Retry:** 0 attempts (planned improvement in Task 11)
- **Runtime:** ~2-5 minutes

#### 2. bronze_WGI
- **Type:** RefreshDataflow Activity
- **Dataflow:** WGI_file2table.Dataflow
- **Output:** bronze_WB_ESGCSV, bronze_WB_ESGSeries
- **Timeout:** 12 hours
- **Retry:** 0 attempts
- **Runtime:** ~3-5 minutes

#### 3. bronze_procurement
- **Type:** RefreshDataflow Activity
- **Dataflow:** bronze_azureSQLdb2table.Dataflow
- **Output:** bronze_procurement_transactional, bronze_supplier_ref
- **Timeout:** 12 hours
- **Retry:** 0 attempts
- **Runtime:** ~5-10 minutes

#### 4. bronze_EPI
- **Type:** RefreshDataflow Activity
- **Dataflow:** EPI_file2table.Dataflow
- **Output:** bronze_epi2024results, related tables
- **Timeout:** 12 hours
- **Retry:** 0 attempts
- **Runtime:** ~3-5 minutes

**Stage 1 Total:** ~5-10 minutes (parallel execution)

### Stage 2: Silver Transformation (Sequential)

**Depends On:** All 4 bronze activities (Succeeded)

#### 5. bronze-to-silver data cleaning
- **Type:** Notebook Activity
- **Notebook:** bronze-to-silver.Notebook
- **Output:** silver_epi2024results, silver_globalsupplyshares, silver_WB, silver_procurement
- **Timeout:** 12 hours
- **Retry:** 0 attempts
- **Runtime:** ~3-5 minutes

### Stage 3: Gold Transformation (Sequential)

**Depends On:** bronze-to-silver data cleaning (Succeeded)

#### 6. silver-to-gold
- **Type:** Notebook Activity
- **Notebook:** silver-to-gold2.Notebook
- **Output:** Gold fact and dimension tables (8 tables + supporting tables)
- **Timeout:** 12 hours
- **Retry:** 0 attempts
- **Runtime:** ~10-15 minutes

### Stage 4: Warehouse Sync (Sequential)

**Depends On:** silver-to-gold (Succeeded)

#### 7. Copy job1
- **Type:** InvokeCopyJob Activity
- **Purpose:** Sync gold tables from lakehouse to warehouse
- **Output:** Tables in oem_wh warehouse
- **Timeout:** 12 hours
- **Retry:** 0 attempts
- **Runtime:** ~2-5 minutes

## Pipeline Parameters

### p_full_load (Boolean)
- **Default:** false
- **Purpose:** Control full vs incremental load
- **Usage:** Currently not implemented (Task 06)
- **Future:** When true, truncate and reload all data; when false, use incremental logic

### p_from_date (String)
- **Default:** "1900-01-01"
- **Purpose:** Start date for incremental load
- **Usage:** Currently not implemented (Task 06)
- **Future:** Filter bronze ingestion to Date >= p_from_date

### procurement_array (Array)
- **Purpose:** Configuration for procurement source-to-sink mappings
- **Usage:** (TBD - verify usage in dataflow)

## Error Handling

**Current Strategy:** Fail-fast (0 retries on all activities)
- **Pros:** Immediate failure detection, no cascading issues
- **Cons:** No resilience to transient failures

**Notifications:** NoNotification configured on dataflow refreshes

**Planned Improvements (Task 11):**
- Add retry logic (2-3 retries with 3-5 minute intervals)
- Implement error categorization (transient vs permanent)
- Configure email alerts on failure
- Add error logging table

## Dependencies

**Execution Order:**
```
Bronze Activities (parallel, no dependencies)
    ↓ (wait for all)
Silver Transformation
    ↓ (wait for completion)
Gold Transformation
    ↓ (wait for completion)
Warehouse Sync
```

**Data Dependencies:**
- Silver requires bronze tables
- Gold requires silver tables
- Warehouse requires gold tables
- Report requires warehouse (DirectLake)

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

## Scheduling (Planned - Task 10)

**Proposed Schedule:**
- **Frequency:** Daily
- **Time:** 06:00 AM Europe/Stockholm
- **Timezone:** Sweden Central (datacenter region)
- **Trigger Type:** Scheduled (time-based)

**Rationale:**
- Procurement data refreshed nightly in Azure SQL (by 5:00 AM)
- 6:00 AM ensures fresh data for morning reports
- External datasets (EPI, WGI) refresh automatically but only change annually

## Performance Optimization (Task 12)

**Current Bottlenecks:** (To be measured)
- Bronze ingestion: Dataflow refresh times
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
- Check notebook/dataflow logs for infinite loops or hangs
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
