# Task: Configure Pipeline Scheduling

**Priority:** P3 (Infrastructure)
**Status:** Not Started
**Estimated Effort:** 0.5-1 day
**Owner:** TBD

## Problem Statement

Per project_definition.md line 697:
> "**Schedule:** Not configured. The pipeline is run manually."

The pipeline `orchestrator_pipeline_bronze_to_gold` currently requires manual execution. For a production-ready portfolio project, it should demonstrate:
- Automated scheduling configuration
- Appropriate refresh frequency
- Timezone handling
- Schedule documentation

## Current State

**What Exists:**
- ✅ Complete 4-stage pipeline (bronze → silver → gold → warehouse)
- ✅ Pipeline tested and working manually
- ✅ Dependencies configured correctly
- ❌ No schedule configured
- ❌ No automated execution

**Pipeline Runtime:** Unknown (needs measurement)

## Acceptance Criteria

### Must Have:

**1. Determine Refresh Frequency**
Document refresh requirements based on:
- Source data update frequency (Azure SQL, EPI, WGI, EU CRM)
- Stakeholder needs for data freshness
- Pipeline runtime vs resource costs

**Recommended Schedule:**
```
Azure SQL Procurement Data: Daily at 6:00 AM (after nightly transactional batch)
External Data (EPI/WGI/EU): Weekly on Sunday at 2:00 AM (low priority, annual updates)
```

**Alternative: Single Schedule**
```
Full Pipeline: Daily at 6:00 AM local time
```

**2. Configure Schedule in Fabric**
- Open `orchestrator_pipeline_bronze_to_gold` in Fabric workspace
- Navigate to Settings → Schedule
- Configure trigger:
  - **Type:** Scheduled
  - **Frequency:** Daily
  - **Time:** 06:00 (local timezone)
  - **Timezone:** Europe/Stockholm (Sweden Central datacenter)
  - **Start Date:** Today
  - **End Date:** None (recurring)

**3. Document Schedule**
- Update `project_definition.md` line 697 with schedule details
- Create `/.claude/context/pipeline_schedule.md` with:
  - Schedule configuration
  - Rationale for frequency
  - Expected completion time
  - Failure notification plan
  - Manual override process

**4. Test Scheduled Run**
- Wait for next scheduled execution
- Validate pipeline runs automatically
- Verify all activities complete successfully
- Check Power BI report reflects new data

### Nice to Have:
- Separate schedules for bronze vs gold layers
- Event-driven triggers (run when source data changes)
- Schedule notifications (start, success, failure)
- Holiday calendar (skip execution on holidays)
- Different schedules for dev vs prod environments

## Technical Approach

### Phase 1: Requirements Analysis (1-2 hours)

**Determine Refresh Frequency:**

| Data Source | Update Frequency | Recommended Refresh |
|-------------|------------------|---------------------|
| Azure SQL Procurement | Daily (transactional) | Daily 6:00 AM |
| Azure SQL Supplier Ref | Rare (reference data) | Daily (piggybacked) |
| EPI Dataset | Annual (Q2-Q3) | Weekly or Manual |
| WGI Dataset | Annual (Q3-Q4) | Weekly or Manual |
| EU CRM Supply Shares | Annual (unknown) | Weekly or Manual |

**Decision:** Run full pipeline daily at 6:00 AM. External data sources will refresh automatically but only show new data when annual releases occur.

### Phase 2: Schedule Configuration (30 minutes)

**In Fabric Workspace:**
1. Open pipeline
2. Click "Settings" or "Schedule" button
3. Enable scheduled execution
4. Configure trigger properties:
   ```json
   {
     "type": "ScheduleTrigger",
     "frequency": "Day",
     "interval": 1,
     "startTime": "06:00:00",
     "timeZone": "Europe/Stockholm",
     "recurrence": "Daily"
   }
   ```
5. Save configuration

**Alternative: ARM Template (for infrastructure-as-code):**
Export pipeline definition with schedule for version control.

### Phase 3: Monitoring Setup (1-2 hours)

**Configure Notifications:**
- Pipeline failure → Email alert to project owner
- Pipeline success → Log to execution history (no alert)
- Long-running pipeline (>2 hours) → Warning alert

**Set Up Monitoring Dashboard:**
- Create workspace monitoring page
- Track execution history (run date, duration, status)
- Alert on consecutive failures (2+ in a row)

### Phase 4: Documentation (1 hour)

Create `/.claude/context/pipeline_schedule.md`:
```markdown
# Pipeline Scheduling Configuration

## Current Schedule
- **Pipeline:** orchestrator_pipeline_bronze_to_gold
- **Frequency:** Daily
- **Time:** 06:00 AM Europe/Stockholm
- **Duration:** ~20-30 minutes (measured)

## Rationale
- Procurement data refreshed nightly in Azure SQL (by 5:00 AM)
- 6:00 AM start ensures fresh data available for morning reports
- External datasets (EPI, WGI) refresh weekly but data updates annually

## Manual Override
To run pipeline manually:
1. Navigate to Fabric workspace
2. Open pipeline
3. Click "Run" button
4. Optionally set parameters: p_full_load, p_from_date

## Failure Handling
- Pipeline failures send email alert
- Retries: 0 (fail fast, investigate immediately)
- On failure: Check execution logs, validate source connectivity

## Schedule Changes
To modify schedule:
1. Open pipeline settings
2. Update trigger configuration
3. Save changes
4. Update this document
```

## Runtime Expectations

**Estimated Stage Durations:**
- Stage 1 (Bronze Ingestion): 5-10 minutes (parallel execution)
- Stage 2 (Silver Transformation): 3-5 minutes
- Stage 3 (Gold Transformation): 5-10 minutes
- Stage 4 (Warehouse Sync): 2-5 minutes

**Total Pipeline Runtime:** 15-30 minutes

*Note: Measure actual runtime during first scheduled executions.*

## Dependencies
- Pipeline must be fully tested and working
- Source systems must be available at scheduled time
- Fabric workspace must have capacity for scheduled execution
- Notification email addresses configured

## Success Metrics
- ✅ Schedule configured and active
- ✅ First scheduled run completes successfully
- ✅ Documentation updated with schedule details
- ✅ Notifications working (test failure notification)
- ✅ Power BI reports refresh automatically after pipeline run

## Related Files
- `/fabric/orchestrator_pipeline_bronze_to_gold.DataPipeline/` - Pipeline to schedule
- To create: `/.claude/context/pipeline_schedule.md` - Schedule documentation
- `/project_definition.md` - Line 697 (to update)

## Notes
- Schedule timezone should match datacenter location (Sweden Central)
- Consider impact on DirectLake semantic model (automatic refresh)
- Pipeline runtime may increase as data volume grows
- Schedule can be paused for maintenance periods
- For portfolio showcase, document that scheduling is configured even if not actively running 24/7
