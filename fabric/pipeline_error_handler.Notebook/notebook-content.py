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
#
# **Purpose:** Centralized execution logging, error categorization, and reporting
# for the OEMMatInsightBI orchestrator pipeline.
#
# **Delta Table:** `gold_pipeline_execution_log`
#
# **Functions:**
# - `log_activity_start()` - Record when an activity begins
# - `log_activity_success()` - Update log entry on success
# - `log_activity_failure()` - Update log entry on failure with error categorization
# - `categorize_error()` - Classify errors as Transient / Permanent / Unknown
# - `get_execution_summary()` - Query recent execution history
# - `get_failure_report()` - Generate failure analysis report
#
# **Error Categories:**
# | Category   | Action                          | Retry Behavior         |
# |------------|--------------------------------|------------------------|
# | Transient  | Retry with backoff             | Up to max_retries      |
# | Permanent  | Fail immediately, alert        | No retry               |
# | Unknown    | Retry once cautiously, alert   | 1 retry max            |
#
# **Usage:** This notebook can be run standalone to create/inspect the log table,
# or its functions can be referenced from other notebooks via `%run`.

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
    "404 not found",
    "file not found",
    "path does not exist",
    "database does not exist",
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
#
# Schema for `gold_pipeline_execution_log`:
#
# | Column | Type | Description |
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

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Reporting & Summary Functions
#
# These functions query `gold_pipeline_execution_log` to provide
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
