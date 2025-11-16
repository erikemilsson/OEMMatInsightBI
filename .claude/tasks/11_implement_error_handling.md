# Task: Implement Error Handling & Retry Logic

**Priority:** P3 (Infrastructure)
**Status:** ✅ Design Phase Complete
**Completion Date:** 2025-11-03 (Strategy & Design)
**Actual Effort:** 3 hours (design phase)
**Owner:** Claude Code

## Problem Statement

Per project_definition.md lines 699-703:
> "**Error Handling:** Fail-fast approach (0 retries, 30-second intervals)
> **Retry Logic:** None (0 retries on all activities)"

The current pipeline uses a fail-fast approach with no retry logic. While appropriate for catching issues quickly, this approach doesn't handle:
- Transient network failures
- Temporary source system unavailability
- Resource contention in Fabric
- Intermittent dataflow failures

For a production-ready portfolio project, demonstrate error handling best practices with:
- Intelligent retry logic for transient failures
- Dead-letter queue for permanent failures
- Error notifications and logging
- Graceful degradation strategies

## Current State

**What Exists:**
- ✅ Pipeline with 7 activities across 4 stages
- ✅ Dependency management (sequential stages)
- ✅ Timeout settings (12 hours per activity)
- ❌ No retry logic (0 retries on all activities)
- ❌ No error categorization (transient vs permanent)
- ❌ No dead-letter pattern
- ❌ Minimal notification config (NoNotification on dataflows)

**Current Behavior on Failure:**
- Pipeline stops immediately
- No automatic retry
- No error categorization
- No alerts configured

## Acceptance Criteria

### Must Have:

**1. Configure Retry Logic**
For each activity in `orchestrator_pipeline_bronze_to_gold`, configure appropriate retry settings:

| Activity | Current Retries | Recommended Retries | Retry Interval | Rationale |
|----------|----------------|---------------------|----------------|-----------|
| bronzecopy_EUSupplyShares | 0 | 3 | 5 minutes | HTTP endpoint may be temporarily unavailable |
| bronze_WGI | 0 | 2 | 3 minutes | Dataflow refresh may have resource contention |
| bronze_procurement | 0 | 3 | 5 minutes | Azure SQL connection may timeout |
| bronze_EPI | 0 | 2 | 3 minutes | Dataflow refresh may have resource contention |
| bronze-to-silver (Notebook) | 0 | 2 | 2 minutes | Spark session may fail to start |
| silver-to-gold (Notebook) | 0 | 2 | 2 minutes | Spark session may fail to start |
| Copy job1 | 0 | 1 | 5 minutes | Warehouse sync may have lock contention |

**2. Error Categorization**
Implement logic to distinguish:
- **Transient Errors:** Network timeouts, resource unavailable, connection resets
  - Action: Retry with exponential backoff
- **Permanent Errors:** Schema mismatch, authentication failure, source table not found
  - Action: Fail immediately, send alert, log to error table

**3. Error Logging Table**
Create `gold_pipeline_execution_log`:
```python
execution_log_schema = StructType([
    StructField("execution_id", StringType(), False),
    StructField("pipeline_name", StringType(), False),
    StructField("activity_name", StringType(), False),
    StructField("start_time", TimestampType(), False),
    StructField("end_time", TimestampType(), True),
    StructField("status", StringType(), False),  # Running, Succeeded, Failed, Retrying
    StructField("error_message", StringType(), True),
    StructField("error_type", StringType(), True),  # Transient, Permanent, Unknown
    StructField("retry_attempt", IntegerType(), True),
    StructField("rows_processed", LongType(), True)
])
```

**4. Notification Configuration**
- **On Success:** Log to execution table (no email)
- **On Retry:** Log to execution table with retry count
- **On Final Failure:** Send email alert with error details and pipeline run ID

**5. Documentation**
Create `/.claude/context/error_handling_strategy.md`:
- Error categorization logic
- Retry configuration by activity
- Notification recipients and channels
- Troubleshooting guide by error type
- Incident response playbook

### Nice to Have:
- Dead-letter storage for failed records (quarantine pattern)
- Exponential backoff for retries
- Circuit breaker pattern (stop retries if source is down)
- Slack/Teams webhook notifications
- PagerDuty integration for critical failures
- Automated rollback on failure

## Technical Approach

### Phase 1: Configure Retry Logic (2 hours)

**In Fabric Pipeline:**
1. Open `orchestrator_pipeline_bronze_to_gold`
2. For each activity, configure:
   - Retry count: 1-3 (based on table above)
   - Retry interval: 2-5 minutes (exponential if supported)
   - Timeout: Keep at 12 hours (or adjust based on runtime)

**Activity Configuration Example:**
```json
{
  "name": "bronze_procurement",
  "type": "RefreshDataflow",
  "policy": {
    "timeout": "12:00:00",
    "retry": 3,
    "retryIntervalInSeconds": 300,
    "secureInput": false,
    "secureOutput": false
  }
}
```

### Phase 2: Implement Error Logging (3-4 hours)

**Create Logging Notebook:**
`/fabric/pipeline_error_handler.Notebook`

```python
from pyspark.sql import SparkSession
from datetime import datetime
import uuid

def log_pipeline_execution(pipeline_name, activity_name, status, error_message=None, error_type=None, retry_attempt=0):
    """Log pipeline execution to audit table"""

    execution_log = spark.createDataFrame([{
        "execution_id": str(uuid.uuid4()),
        "pipeline_name": pipeline_name,
        "activity_name": activity_name,
        "start_time": datetime.now(),
        "end_time": datetime.now() if status != "Running" else None,
        "status": status,
        "error_message": error_message,
        "error_type": categorize_error(error_message) if error_message else None,
        "retry_attempt": retry_attempt,
        "rows_processed": None
    }])

    # Append to execution log table
    execution_log.write.format("delta").mode("append").saveAsTable("oem_lh.gold_pipeline_execution_log")

def categorize_error(error_message):
    """Categorize error as Transient, Permanent, or Unknown"""

    transient_keywords = ["timeout", "connection reset", "temporarily unavailable", "resource busy"]
    permanent_keywords = ["authentication failed", "table not found", "schema mismatch", "access denied"]

    error_lower = error_message.lower()

    if any(keyword in error_lower for keyword in transient_keywords):
        return "Transient"
    elif any(keyword in error_lower for keyword in permanent_keywords):
        return "Permanent"
    else:
        return "Unknown"
```

**Add Error Handlers to Notebooks:**
```python
# In clean_columnsAndHeaders.Notebook and silver-to-gold2.Notebook
try:
    # Transformation logic
    process_data()
    log_pipeline_execution("orchestrator_pipeline_bronze_to_gold", "bronze-to-silver", "Succeeded")
except Exception as e:
    log_pipeline_execution("orchestrator_pipeline_bronze_to_gold", "bronze-to-silver", "Failed",
                          error_message=str(e))
    raise  # Re-raise to fail pipeline
```

### Phase 3: Configure Notifications (1-2 hours)

**Email Alert Template:**
```
Subject: [OEMMatInsightBI] Pipeline Failure Alert

Pipeline: orchestrator_pipeline_bronze_to_gold
Activity: bronze_procurement (RefreshDataflow)
Status: Failed after 3 retries
Error: Connection timeout to Azure SQL Database

Execution ID: 12345-abcde
Timestamp: 2024-01-15 06:23:45 UTC

Action Required:
1. Check Azure SQL Database connectivity
2. Review execution logs in Fabric workspace
3. Check gold_pipeline_execution_log table for details
4. Retry pipeline manually if issue resolved

Pipeline Run Link: [URL to Fabric pipeline run]
```

**Configure in Fabric:**
- Navigate to pipeline settings
- Add email notification on failure
- Configure recipient list
- Test notification with intentional failure

### Phase 4: Documentation & Testing (2-3 hours)

**Create Error Handling Documentation:**
`/.claude/context/error_handling_strategy.md`

**Test Scenarios:**
1. **Simulate transient failure:** Temporarily block network to Azure SQL
2. **Verify retry logic:** Confirm pipeline retries 3 times with 5-minute intervals
3. **Test notification:** Verify email sent after final failure
4. **Validate logging:** Check `gold_pipeline_execution_log` for error details
5. **Test permanent failure:** Use invalid connection string (should fail immediately after categorization)

## Error Recovery Playbook

Create `/.claude/reference/error_recovery_playbook.md`:

### Scenario 1: Azure SQL Connection Failure
**Symptoms:** bronze_procurement activity fails with "connection timeout"
**Diagnosis:** Check Azure SQL firewall, verify Fabric IP is whitelisted
**Resolution:** Add Fabric service tag to firewall rules, retry pipeline

### Scenario 2: Dataflow Refresh Timeout
**Symptoms:** bronze_WGI fails with "dataflow refresh timeout"
**Diagnosis:** Check dataflow execution time, review source data size
**Resolution:** Increase timeout, optimize Power Query logic, split into smaller dataflows

### Scenario 3: Notebook Spark Failure
**Symptoms:** bronze-to-silver fails with "Spark session error"
**Diagnosis:** Check Fabric capacity usage, review Spark logs
**Resolution:** Restart Spark pool, increase capacity units, optimize PySpark code

## Dependencies
- Pipeline edit permissions in Fabric
- Email server configuration for notifications
- Access to execution logs in Fabric
- Ability to create lakehouse tables (error log)

## Success Metrics
- ✅ Retry logic configured for all 7 activities
- ✅ Error logging table created and populated
- ✅ Email notifications configured and tested
- ✅ Documentation complete with playbook
- ✅ Test scenarios validated (transient and permanent failures)
- ✅ Error recovery time reduced by >50%

## Related Files
- `/fabric/orchestrator_pipeline_bronze_to_gold.DataPipeline/` - Pipeline to update
- To create: `/fabric/pipeline_error_handler.Notebook/` - Error logging logic
- To create: `/.claude/context/error_handling_strategy.md` - Strategy documentation
- To create: `/.claude/reference/error_recovery_playbook.md` - Recovery procedures
- `/project_definition.md` - Lines 699-715 (Error Handling section)

## Notes
- Balance retries vs fail-fast: don't mask real issues with excessive retries
- Exponential backoff prevents overwhelming failing systems
- Dead-letter pattern useful for data quality issues (bad records)
- Consider cost: retries consume capacity units
- For portfolio, demonstrate understanding of error handling patterns
- Pipeline should be self-healing for transient issues, alerting for permanent issues

---

## Completion Summary (2025-11-03)

### Design Phase ✅ COMPLETE

**Comprehensive Strategy Document Created:**

✅ **Document:** `.claude/context/error_handling_strategy.md` (~1,200 lines, 12 sections)

**Key Deliverables:**

1. **Error Categorization Framework**
   - Three categories: Transient (retryable), Permanent (non-retryable), Unknown
   - 20+ error patterns mapped with keywords
   - Automated classification function with `categorize_error()` and `should_retry()`

2. **Activity-Specific Retry Configuration**
   - 7 activities analyzed with tailored retry settings
   - Retry counts: 1-3 based on failure patterns
   - Retry intervals: 2-5 minutes with exponential backoff option
   - Timeout settings: 1-4 hours based on activity complexity

3. **Execution Logging System**
   - Table: `gold_pipeline_execution_log` (14 columns)
   - Functions: `log_activity_start()`, `log_activity_success()`, `log_activity_failure()`
   - Tracks: execution_id, error_type, retry_attempt, duration, rows_processed
   - Troubleshooting queries for failure analysis

4. **Notification Strategy**
   - Smart notification logic: No alerts on transient retries, alerts on final failure
   - Three email templates: Final Failure, Permanent Error, Repeated Failures
   - Multiple channels: Email (primary), Slack/Teams webhooks (optional)
   - Notification function: `should_send_notification()` with business logic

5. **Troubleshooting Guide**
   - Matrix of 7 common error patterns with diagnosis and resolution steps
   - Step-by-step diagnostic process (6 steps, 11-43 minutes total)
   - Testing functions for connection validation
   - Historical log analysis queries

6. **Incident Response Playbook**
   - Four severity levels: P0-Critical (15 min), P1-High (1 hour), P2-Medium (4 hours), P3-Low (next day)
   - Detailed response procedures for P0/P1 incidents
   - Communication templates for incident declaration and resolution
   - Post-incident review process

7. **Graceful Degradation Strategies**
   - Continue on failure for non-critical activities (EPI, WGI)
   - Cached data fallback for external sources
   - Data quality quarantine pattern for bad records
   - Failure threshold logic (e.g., fail if >10% invalid records)

8. **Monitoring & Alerting**
   - Six key metrics: success rate, duration, retry rate, consecutive failures, data freshness, error distribution
   - Proactive health check notebook (scheduled daily)
   - Power BI monitoring dashboard design
   - Threshold-based alerting rules

9. **Implementation Checklist**
   - 5 phases: Retry Logic (0.5d), Error Logging (1d), Notifications (0.5d), Testing (0.5d), Documentation (0.5d)
   - Total estimated effort: 3 days implementation
   - Detailed test scenarios for validation

10. **Future Enhancements**
    - Circuit breaker pattern to prevent overwhelming failing systems
    - Exponential backoff with jitter to prevent thundering herd
    - Dead letter queue for invalid data records
    - Automated rollback using Delta Lake time travel

### Technical Highlights

**Error Categorization Example:**
```python
TRANSIENT_ERROR_PATTERNS = [
    "timeout", "connection reset", "temporarily unavailable",
    "resource busy", "throttled", "503 service unavailable"
]

PERMANENT_ERROR_PATTERNS = [
    "authentication failed", "access denied", "table not found",
    "schema mismatch", "invalid syntax", "constraint violation"
]

def categorize_error(error_message: str) -> str:
    error_lower = error_message.lower()
    if any(p in error_lower for p in TRANSIENT_ERROR_PATTERNS):
        return "Transient"
    elif any(p in error_lower for p in PERMANENT_ERROR_PATTERNS):
        return "Permanent"
    return "Unknown"
```

**Retry Configuration Table:**
| Activity | Retries | Interval | Timeout | Rationale |
|----------|---------|----------|---------|-----------|
| bronze_procurement | 3 | 5 min | 2 hours | Azure SQL timeouts, highest priority |
| clean_columnsAndHeaders | 2 | 2 min | 4 hours | Spark session failures |
| bronzecopy_EUSupplyShares | 3 | 5 min | 1 hour | HTTP endpoint availability |

**Notification Logic:**
```python
def should_send_notification(log_id: str) -> bool:
    # Always notify on permanent errors
    if error_type == "Permanent":
        return True

    # Notify only on final failure (after all retries)
    if status == "Failed" and retry_attempt >= max_retries:
        return True

    # Don't notify on intermediate retries
    return False
```

**Graceful Degradation:**
```python
def load_external_data_with_fallback(source_name: str):
    try:
        df = load_external_data(source_name)
        df.write.saveAsTable(f"bronze_{source_name}_cached")
        return df
    except Exception as e:
        print(f"⚠️  Using cached {source_name} data")
        return spark.table(f"bronze_{source_name}_cached")
```

### What's Next (Implementation Phase)

⏭️ **Implementation** (requires Fabric workspace access)
- Phase 1: Configure retry logic in pipeline JSON
- Phase 2: Create execution log table and implement logging functions
- Phase 3: Set up email notifications (Fabric or Logic App)
- Phase 4: Test with simulated failures (transient, permanent, unknown)
- Phase 5: Create monitoring dashboard and documentation

**Status:** Design complete and implementation-ready. Implementation deferred until Fabric workspace access is available.

### Files Created

```
.claude/context/error_handling_strategy.md (~1,200 lines, comprehensive design)
```

### Portfolio Value

This design demonstrates:
✅ **Reliability Engineering:** Intelligent retry strategies and error categorization
✅ **Observability:** Comprehensive logging and execution tracking
✅ **Operational Excellence:** Incident response playbooks and troubleshooting guides
✅ **Graceful Degradation:** Fallback strategies for non-critical failures
✅ **Monitoring:** Proactive health checks and alerting
✅ **Best Practices:** Circuit breaker, exponential backoff, dead letter queue patterns
✅ **Documentation:** Implementation-ready design with code examples and templates
