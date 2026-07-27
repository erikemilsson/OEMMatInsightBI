# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "488fb9f8-e635-4683-90c4-ba4fee9dfadb",
# META       "default_lakehouse_name": "oem_lh",
# META       "default_lakehouse_workspace_id": "99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9"
# META     }
# META   }
# META }

# MARKDOWN ********************

# # Pipeline Error Handler (Task 011)
# # **Purpose:** Centralized execution logging, error categorization, and reporting
# for the OEMMatInsightBI orchestrator pipeline.
# # **Delta Table:** `gold_pipeline_execution_log`
# # **Functions:**
# - `log_activity_start()` - Record when an activity begins
# - `log_activity_success()` - Update log entry on success
# - `log_activity_failure()` - Update log entry on failure with error categorization
# - `categorize_error()` - Classify errors as Transient / Permanent / Unknown
# - `get_execution_summary()` - Query recent execution history
# - `get_failure_report()` - Generate failure analysis report
# # **Error Categories:**
# | Category   | Action                          | Retry Behavior         |
# |------------|--------------------------------|------------------------|
# | Transient  | Retry with backoff             | Up to max_retries      |
# | Permanent  | Fail immediately, alert        | No retry               |
# | Unknown    | Retry once cautiously, alert   | 1 retry max            |
# # **Usage:** This notebook can be run standalone to create/inspect the log table,
# or its functions can be referenced from other notebooks via `%run`.


# PARAMETERS CELL ********************

p_run_id = ""

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, TimestampType,
    IntegerType, FloatType
)
from datetime import datetime
import uuid

# =============================================================================
# CONFIGURATION
# =============================================================================

DB = "oem_lh"
spark.sql(f"USE {DB}")

PIPELINE_NAME = "orchestrator_pipeline_bronze_to_gold"

print("=" * 70)
print("PIPELINE ERROR HANDLER - OEMMatInsightBI")
print("=" * 70)
print(f"Database: {DB}")
print(f"Pipeline: {PIPELINE_NAME}")
print("=" * 70)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# =============================================================================
# ERROR CATEGORIZATION
# =============================================================================

TRANSIENT_ERROR_PATTERNS = [
    # Network & Connectivity
    "timeout",
    "connection reset",
    "connection refused",
    "network unreachable",
    "socket timeout",
    # Resource Contention
    "temporarily unavailable",
    "resource busy",
    "too many connections",
    "capacity exceeded",
    "throttled",
    "rate limit exceeded",
    # Transient Service Issues
    "service unavailable",
    "503 service unavailable",
    "502 bad gateway",
    "504 gateway timeout",
    "deadlock detected",
    # HTTP status codes - retryable (5xx server-side, plus 429 throttling).
    # TWO phrasings occur in practice and both must be matched: Fabric/ADF's
    # HybridDeliveryException writes "status code 429 TooManyRequests" (no space
    # in the reason phrase), while the inner System.Net.WebException writes
    # "The remote server returned an error: (429)". Neither matches a naive
    # "429 too many requests" pattern. See the note on PERMANENT below.
    # These are listed BEFORE the permanent 4xx block matters, because
    # categorize_error checks TRANSIENT first - which is what keeps 429 out of
    # the permanent client-error bucket.
    "status code 429",
    "(429)",
    "toomanyrequests",
    "status code 500",
    "(500)",
    "status code 502",
    "(502)",
    "status code 503",
    "(503)",
    "status code 504",
    "(504)",
    # Spark-Specific
    "spark session failed to start",
    "executor lost",
    "stage retry",
]

PERMANENT_ERROR_PATTERNS = [
    # Authentication & Authorization
    "authentication failed",
    "unauthorized",
    "access denied",
    "403 forbidden",
    "401 unauthorized",
    "invalid credentials",
    "token expired",
    # Configuration Errors
    "table not found",
    "schema not found",
    "column not found",
    "invalid syntax",
    "schema mismatch",
    "type mismatch",
    # Resource Not Found
    # "404 not found" is kept for completeness but does NOT match real Fabric
    # output - see the HTTP block below. Verified 2026-07-27 against orchestrator
    # run 742ff1ff-42d8-4fb6-9845-8c7a183c060d, where a deliberately-broken Copy
    # source produced:
    #   ErrorCode=HttpRequestFailedWithClientError,...Message=Http request failed
    #   with client error, status code 404 NotFound, ... ''Type=System.Net.
    #   WebException,Message=The remote server returned an error: (404) Not Found.
    # "404 NotFound" has no space; "(404) Not Found" has a parenthesis in the way.
    # The whole list was written from imagination rather than a real error string,
    # so this textbook-permanent failure was categorised "Unknown". Do not add
    # patterns here without checking them against text a live run actually emits.
    "404 not found",
    "file not found",
    "path does not exist",
    "database does not exist",
    # HTTP status codes - not retryable (4xx client-side). 429 is deliberately
    # absent: it is throttling, and is matched by the TRANSIENT list above, which
    # categorize_error checks first.
    "status code 400",
    "(400)",
    "status code 401",
    "(401)",
    "status code 403",
    "(403)",
    "status code 404",
    "(404)",
    "status code 409",
    "(409)",
    "http request failed with client error",
    # Data Quality Issues
    "constraint violation",
    "duplicate key",
    "null value not allowed",
    "value out of range",
]


def categorize_error(error_message: str) -> str:
    """Classify an error message as Transient, Permanent, or Unknown.

    Args:
        error_message: Full error message string from the exception.

    Returns:
        One of "Transient", "Permanent", or "Unknown".
    """
    if not error_message:
        return "Unknown"

    error_lower = error_message.lower()

    for pattern in TRANSIENT_ERROR_PATTERNS:
        if pattern in error_lower:
            return "Transient"

    for pattern in PERMANENT_ERROR_PATTERNS:
        if pattern in error_lower:
            return "Permanent"

    return "Unknown"


# Quick demo of categorization
_demo_errors = [
    "Connection timeout after 30s",
    "401 Unauthorized: invalid credentials",
    "Something unexpected happened",
]
for _err in _demo_errors:
    print(f"  '{_err}' -> {categorize_error(_err)}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Execution Log Table
# # Schema for `gold_pipeline_execution_log`:
# # | Column | Type | Description |
# |--------|------|-------------|
# | execution_id | string | Unique ID for this log entry (UUID) |
# | activity_name | string | Pipeline activity name |
# | status | string | STARTED, SUCCESS, FAILED, RETRYING |
# | start_time | timestamp | When the activity started |
# | end_time | timestamp | When the activity completed (null if running) |
# | duration_seconds | float | Elapsed time in seconds |
# | error_category | string | Transient / Permanent / Unknown |
# | error_message | string | Full error text (null on success) |
# | retry_attempt | int | 0 for first attempt, 1+ for retries |
# | pipeline_run_id | string | Fabric pipeline run ID for traceability |

# CELL ********************

# =============================================================================
# EXECUTION LOG TABLE - SCHEMA AND CREATION
# =============================================================================

EXECUTION_LOG_TABLE = "gold_pipeline_execution_log"

execution_log_schema = StructType([
    StructField("execution_id", StringType(), False),
    StructField("activity_name", StringType(), False),
    StructField("status", StringType(), False),
    StructField("start_time", TimestampType(), False),
    StructField("end_time", TimestampType(), True),
    StructField("duration_seconds", FloatType(), True),
    StructField("error_category", StringType(), True),
    StructField("error_message", StringType(), True),
    StructField("retry_attempt", IntegerType(), False),
    StructField("pipeline_run_id", StringType(), True),
])


def ensure_log_table_exists():
    """Create the execution log Delta table if it does not already exist."""
    if not spark.catalog.tableExists(f"{DB}.{EXECUTION_LOG_TABLE}"):
        empty_df = spark.createDataFrame([], schema=execution_log_schema)
        (
            empty_df.write
            .format("delta")
            .mode("overwrite")
            .saveAsTable(f"{DB}.{EXECUTION_LOG_TABLE}")
        )
        print(f"Created table: {DB}.{EXECUTION_LOG_TABLE}")
    else:
        print(f"Table already exists: {DB}.{EXECUTION_LOG_TABLE}")


# Create on first run
ensure_log_table_exists()

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# =============================================================================
# LOGGING FUNCTIONS
# =============================================================================


def log_activity_start(
    activity_name: str,
    pipeline_run_id: str = None,
    retry_attempt: int = 0,
) -> str:
    """Record that a pipeline activity has started.

    Args:
        activity_name: Name of the pipeline activity.
        pipeline_run_id: Fabric pipeline run ID (optional).
        retry_attempt: 0 for first attempt, 1+ for retries.

    Returns:
        execution_id (UUID string) for use in subsequent log calls.
    """
    execution_id = str(uuid.uuid4())
    status = "RETRYING" if retry_attempt > 0 else "STARTED"

    row = spark.createDataFrame(
        [{
            "execution_id": execution_id,
            "activity_name": activity_name,
            "status": status,
            "start_time": datetime.now(),
            "end_time": None,
            "duration_seconds": None,
            "error_category": None,
            "error_message": None,
            "retry_attempt": retry_attempt,
            "pipeline_run_id": pipeline_run_id,
        }],
        schema=execution_log_schema,
    )

    row.write.format("delta").mode("append").saveAsTable(
        f"{DB}.{EXECUTION_LOG_TABLE}"
    )

    print(f"[{status}] {activity_name} (attempt {retry_attempt}, id={execution_id[:8]}...)")
    return execution_id


def log_activity_success(execution_id: str, rows_processed: int = None):
    """Update a log entry to record successful completion.

    Args:
        execution_id: The UUID returned by log_activity_start.
        rows_processed: Optional count of rows processed (logged in message).
    """
    spark.sql(f"""
        UPDATE {DB}.{EXECUTION_LOG_TABLE}
        SET
            end_time = current_timestamp(),
            duration_seconds = CAST(
                unix_timestamp(current_timestamp()) - unix_timestamp(start_time) AS FLOAT
            ),
            status = 'SUCCESS'
        WHERE execution_id = '{execution_id}'
    """)

    suffix = f", {rows_processed} rows" if rows_processed is not None else ""
    print(f"[SUCCESS] execution_id={execution_id[:8]}...{suffix}")


def log_activity_failure(execution_id: str, error_message: str):
    """Update a log entry to record a failure with error categorization.

    Args:
        execution_id: The UUID returned by log_activity_start.
        error_message: Full error message from the exception.
    """
    error_category = categorize_error(error_message)

    # Escape single quotes for safe SQL interpolation
    escaped_msg = error_message.replace("'", "''")

    spark.sql(f"""
        UPDATE {DB}.{EXECUTION_LOG_TABLE}
        SET
            end_time = current_timestamp(),
            duration_seconds = CAST(
                unix_timestamp(current_timestamp()) - unix_timestamp(start_time) AS FLOAT
            ),
            status = 'FAILED',
            error_category = '{error_category}',
            error_message = '{escaped_msg}'
        WHERE execution_id = '{execution_id}'
    """)

    print(f"[FAILED] execution_id={execution_id[:8]}... | {error_category}: {error_message[:120]}")


def log_activity_outcome(
    activity_name: str,
    status: str,
    error_message: str = None,
    pipeline_run_id: str = None,
    retry_attempt: int = 0,
    start_time: datetime = None,
    end_time: datetime = None,
    duration_seconds: float = None,
) -> str:
    """Record a terminal activity outcome in a SINGLE append (one-shot).

    The two-phase log_activity_start / log_activity_success|failure pair assumes the
    logger runs *inside* the activity and holds the execution_id across its lifetime.
    The DEC-004 Option A topology instead runs a pipeline-level failure branch AFTER
    the guarded activities have finished, reading their outcomes from POST
    queryactivityruns — so there is no prior log_activity_start UUID to UPDATE. This
    one-shot writes a fully-formed row from an already-known outcome and is the only
    logging entry point that fits a pipeline-level branch. Needed identically whether
    the branch reads queryactivityruns (recommended shape) or falls back to per-activity
    @activity('X').Error handlers.

    Args:
        activity_name: Name of the pipeline activity.
        status: Terminal status — "SUCCESS" or "FAILED".
        error_message: Full error text; required when status == "FAILED".
        pipeline_run_id: Fabric pipeline run ID for traceability.
        retry_attempt: 0 for first attempt, 1+ for retries.
        start_time: Activity start (e.g. from queryactivityruns); defaults to now.
        end_time: Activity end (e.g. from queryactivityruns); defaults to now.
        duration_seconds: Precomputed duration; derived from start/end when omitted.

    Returns:
        execution_id (UUID string) of the row written.
    """
    execution_id = str(uuid.uuid4())
    now = datetime.now()
    start_time = start_time or now
    end_time = end_time or now
    if duration_seconds is None:
        duration_seconds = (end_time - start_time).total_seconds()

    error_category = (
        categorize_error(error_message)
        if status == "FAILED" and error_message
        else None
    )

    row = spark.createDataFrame(
        [{
            "execution_id": execution_id,
            "activity_name": activity_name,
            "status": status,
            "start_time": start_time,
            "end_time": end_time,
            "duration_seconds": float(duration_seconds) if duration_seconds is not None else None,
            "error_category": error_category,
            "error_message": error_message,
            "retry_attempt": retry_attempt,
            "pipeline_run_id": pipeline_run_id,
        }],
        schema=execution_log_schema,
    )

    row.write.format("delta").mode("append").saveAsTable(
        f"{DB}.{EXECUTION_LOG_TABLE}"
    )

    label = error_category or status
    tail = f" | {error_message[:120]}" if error_message else ""
    print(f"[{status}] {activity_name} (one-shot, id={execution_id[:8]}...) {label}{tail}")
    return execution_id

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Reporting & Summary Functions
# # These functions query `gold_pipeline_execution_log` to provide
# operational insights.

# CELL ********************

# =============================================================================
# REPORTING FUNCTIONS
# =============================================================================


def get_execution_summary(days: int = 7):
    """Print a summary of pipeline execution over the last N days.

    Args:
        days: Number of days to look back (default 7).

    Returns:
        DataFrame with summary statistics per activity.
    """
    query = f"""
        SELECT
            activity_name,
            COUNT(*) AS total_runs,
            SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) AS successes,
            SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) AS failures,
            SUM(CASE WHEN retry_attempt > 0 THEN 1 ELSE 0 END) AS retries,
            ROUND(AVG(CASE WHEN status = 'SUCCESS' THEN duration_seconds END) / 60.0, 2)
                AS avg_success_min,
            ROUND(
                100.0 * SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) / COUNT(*),
                1
            ) AS success_rate_pct
        FROM {DB}.{EXECUTION_LOG_TABLE}
        WHERE start_time >= current_timestamp() - INTERVAL {days} DAYS
        GROUP BY activity_name
        ORDER BY failures DESC, activity_name
    """

    print(f"\n{'=' * 70}")
    print(f"EXECUTION SUMMARY (last {days} days)")
    print(f"{'=' * 70}")

    df = spark.sql(query)
    df.show(truncate=False)
    return df


def get_failure_report(days: int = 7):
    """Print a detailed failure report over the last N days.

    Includes error category distribution and most recent failures.

    Args:
        days: Number of days to look back (default 7).

    Returns:
        DataFrame with recent failures.
    """
    # Error category distribution
    cat_query = f"""
        SELECT
            error_category,
            COUNT(*) AS error_count,
            ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct_of_total
        FROM {DB}.{EXECUTION_LOG_TABLE}
        WHERE status = 'FAILED'
          AND start_time >= current_timestamp() - INTERVAL {days} DAYS
          AND error_category IS NOT NULL
        GROUP BY error_category
        ORDER BY error_count DESC
    """

    print(f"\n{'=' * 70}")
    print(f"FAILURE REPORT (last {days} days)")
    print(f"{'=' * 70}")

    print("\n--- Error Category Distribution ---")
    cat_df = spark.sql(cat_query)
    cat_df.show(truncate=False)

    # Recent failures
    recent_query = f"""
        SELECT
            activity_name,
            start_time,
            error_category,
            SUBSTRING(error_message, 1, 100) AS error_excerpt,
            retry_attempt,
            pipeline_run_id
        FROM {DB}.{EXECUTION_LOG_TABLE}
        WHERE status = 'FAILED'
          AND start_time >= current_timestamp() - INTERVAL {days} DAYS
        ORDER BY start_time DESC
        LIMIT 20
    """

    print("--- Recent Failures (up to 20) ---")
    df = spark.sql(recent_query)
    df.show(truncate=False)
    return df


def get_retry_effectiveness(days: int = 30):
    """Analyze how often retries lead to eventual success.

    Checks whether activities that had retry_attempt > 0 eventually
    succeeded (i.e., a SUCCESS row exists for the same activity and
    pipeline_run_id).

    Args:
        days: Number of days to look back (default 30).

    Returns:
        DataFrame with retry effectiveness per activity.
    """
    query = f"""
        SELECT
            activity_name,
            COUNT(*) AS retry_attempts,
            SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) AS retry_successes,
            ROUND(
                100.0 * SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) / COUNT(*),
                1
            ) AS retry_success_rate_pct
        FROM {DB}.{EXECUTION_LOG_TABLE}
        WHERE retry_attempt > 0
          AND start_time >= current_timestamp() - INTERVAL {days} DAYS
        GROUP BY activity_name
        ORDER BY retry_attempts DESC
    """

    print(f"\n{'=' * 70}")
    print(f"RETRY EFFECTIVENESS (last {days} days)")
    print(f"{'=' * 70}")

    df = spark.sql(query)
    df.show(truncate=False)
    return df

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# =============================================================================
# DEMO / SELF-TEST
# =============================================================================
# When this notebook is run standalone, it creates the table (if needed)
# and shows the current state of the execution log.

print("\n--- Current Execution Log (most recent 10 entries) ---")
spark.sql(f"""
    SELECT execution_id, activity_name, status, start_time,
           duration_seconds, error_category, retry_attempt
    FROM {DB}.{EXECUTION_LOG_TABLE}
    ORDER BY start_time DESC
    LIMIT 10
""").show(truncate=False)

print("\n--- Table Row Count ---")
count = spark.sql(f"SELECT COUNT(*) AS total FROM {DB}.{EXECUTION_LOG_TABLE}").collect()[0]["total"]
print(f"Total log entries: {count}")

print("\nPipeline error handler ready.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# =============================================================================
# PIPELINE-LEVEL RUN HARVEST (DEC-004 Option A, as amended) - task-041
# =============================================================================
# Runs as the orchestrator's terminal activity: one activity hanging off
# data_quality_checks via dependencyConditions ["Succeeded", "Failed",
# "Skipped"] - i.e. on EVERY outcome, not just failures. Because that pipeline
# is a single convergent DAG, and "Skipped" propagates transitively, this one
# handler covers all upstream activities.
#
# It reads per-activity outcomes from POST queryactivityruns rather than
# @activity('X').Error, because a SKIPPED activity carries no error field.
#
# WHY IT RUNS ON SUCCESS TOO, and why it re-raises:
# DEC-004 originally paired a failure-only handler with a trailing native Fail
# activity, because attaching a handler to the terminal activity produces the
# Try-Catch shape in which the whole run reports Succeeded once the handler
# succeeds - silently undoing task-026's DQ gate. But a failure-only handler
# never fires on a clean run, so the log only ever contained failures, and
# criterion 3 (a successful run must populate the log, so get_execution_summary
# and get_retry_effectiveness have both outcomes to compare) could not be met.
# Proven by orchestrator run b5d799b1-3643-45d9-9a63-bcae0cc8199a on 2026-07-27:
# 8 activities all Succeeded, 0 log rows written.
# Running on every outcome and re-raising when a FAILED row was logged serves
# both criteria with one activity: the log is always written, and a failing run
# still ends red because this activity fails. The trailing Fail activity is not
# merely redundant under this shape - it would fail a healthy run - so it was
# removed with this change.
#
# Empirically established 2026-07-27 (scratch_qar_test run
# 7c2781b8-6ad2-4bd6-bf0d-ff8acccf6991), because the docs address none of it:
#   * queryactivityruns DOES return rows while the run is still in progress -
#     which is the only reason this shape works at all, since the handler
#     executes inside the run it queries.
#   * lastUpdatedAfter / lastUpdatedBefore are MANDATORY in practice. Omit them
#     and the endpoint returns HTTP 200 with an empty value array for every run,
#     which mimics both a wrong run id and an in-progress limitation. This cost
#     three misdiagnosed runs; do not "simplify" them away.
#   * The response is an OBJECT ({"value": [...], "continuationToken": ...}),
#     not the bare array shown in the Microsoft Learn sample.
#   * The handler sees ITSELF in the results, with status "InProgress" - hence
#     the self-skip below, without which every run logs a phantom row.
#   * "error" is always present, even on success, as a dict of empty strings.
#     Branch on status; `if a["error"]` is truthy for every activity.
# =============================================================================

import requests
import notebookutils
from datetime import datetime

WORKSPACE_ID = "99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9"

# This notebook's own activity name in orchestrator_pipeline_bronze_to_gold.
# Must match the activity name in pipeline-content.json.
SELF_ACTIVITY_NAME = "pipeline_error_handler"

# Fabric activity status -> gold_pipeline_execution_log status.
# Anything not listed (InProgress, Queued, Skipped, Cancelled) is not a terminal
# outcome this log models, and is counted-and-reported rather than written.
_TERMINAL_STATUS = {"Succeeded": "SUCCESS", "Failed": "FAILED"}


def _parse_activity_ts(value):
    """Parse a queryactivityruns ISO-8601 timestamp to a naive datetime.

    Fabric returns 7 fractional-second digits (e.g. 2026-07-26T22:01:31.5737206Z);
    datetime.fromisoformat accepts at most 6, so the fraction is truncated.
    """
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    if "." in text:
        head, rest = text.split(".", 1)
        digits = ""
        for char in rest:
            if not char.isdigit():
                break
            digits += char
        text = head + "." + digits[:6] + rest[len(digits):]
    return datetime.fromisoformat(text).replace(tzinfo=None)


def fetch_activity_runs(run_id):
    """Return the activity-run records for one pipeline run."""
    token = notebookutils.credentials.getToken("pbi")
    url = (
        "https://api.fabric.microsoft.com/v1/workspaces/"
        + WORKSPACE_ID
        + "/datapipelines/pipelineruns/"
        + run_id
        + "/queryactivityruns"
    )
    body = {
        "filters": [],
        "orderBy": [{"orderBy": "ActivityRunStart", "order": "DESC"}],
        # Mandatory - see header note. A missing window yields 200 + [].
        "lastUpdatedAfter": "2020-01-01T00:00:00.0000000Z",
        "lastUpdatedBefore": "2030-01-01T00:00:00.0000000Z",
    }
    response = requests.post(
        url,
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
        },
        json=body,
    )
    response.raise_for_status()
    return response.json().get("value", [])


def harvest_pipeline_run(run_id):
    """Write one execution-log row per terminal activity in run_id.

    Logs successes as well as failures, so get_execution_summary() and
    get_retry_effectiveness() have both outcomes to compare.

    Raises RuntimeError, after all rows are written, if any activity failed -
    which is what makes the orchestrator run report Failed. See the cell header.
    """
    activities = fetch_activity_runs(run_id)

    # Fail loud rather than logging nothing. This branch only fires when an
    # upstream activity failed, so at least that activity must come back. An
    # empty result means the query is broken (bad window, bad run id, lost
    # permission) - exactly the silent-no-op this task exists to eliminate.
    if not activities:
        raise RuntimeError(
            "queryactivityruns returned no activities for pipeline run "
            + str(run_id)
            + ". This handler runs on every outcome, so the upstream activities "
            "must exist. Check the lastUpdatedAfter/lastUpdatedBefore window "
            "and the token scope before trusting an empty execution log."
        )

    written = 0
    skipped = []
    failures = []

    for activity in activities:
        name = activity.get("activityName")
        raw_status = activity.get("status")

        if name == SELF_ACTIVITY_NAME:
            continue

        log_status = _TERMINAL_STATUS.get(raw_status)
        if log_status is None:
            skipped.append(str(name) + " (" + str(raw_status) + ")")
            continue

        error = activity.get("error") or {}
        message = (error.get("message") or "").strip() or None

        start_time = _parse_activity_ts(activity.get("activityRunStart"))
        end_time = _parse_activity_ts(activity.get("activityRunEnd"))
        duration_ms = activity.get("durationInMs")

        log_activity_outcome(
            activity_name=name,
            status=log_status,
            error_message=message,
            pipeline_run_id=activity.get("pipelineRunId") or run_id,
            retry_attempt=activity.get("retryAttempt") or 0,
            start_time=start_time,
            end_time=end_time,
            duration_seconds=(duration_ms / 1000.0) if duration_ms is not None else None,
        )
        written += 1
        if log_status == "FAILED":
            failures.append(str(name) + ": " + str(message or "no error message"))

    print("Harvested pipeline run " + str(run_id) + ": " + str(written) + " row(s) logged.")
    if skipped:
        print("Non-terminal activities not logged: " + ", ".join(skipped))

    # Re-raise AFTER every row is written, so the log survives the failure.
    # This is what keeps a failing run red: without it, the Try-Catch shape
    # would report the whole run as Succeeded once this handler succeeded,
    # silently undoing task-026's DQ gate. Confirmed live 2026-07-27.
    if failures:
        raise RuntimeError(
            "Orchestrator run "
            + str(run_id)
            + " had "
            + str(len(failures))
            + " failed activity(ies); "
            + str(written)
            + " row(s) were written to the execution log first. "
            + " | ".join(failures)
        )

    return written


# -----------------------------------------------------------------------------
# Entry point. p_run_id is injected by the pipeline (parameter cell at the top).
# Empty means the notebook is being run standalone, where there is no run to
# harvest - so this is a no-op rather than an error.
# -----------------------------------------------------------------------------
if p_run_id:
    harvest_pipeline_run(p_run_id)
else:
    print("No p_run_id supplied - standalone mode, nothing harvested.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
