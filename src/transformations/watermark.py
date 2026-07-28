"""
High-Water Mark Tracking — bronze_load_metadata

This module implements the watermark system that drives incremental loads for
the procurement pipeline. The metadata table `bronze_load_metadata` records one
row per pipeline run per tracked source table; `get_last_load_date` reads the
last SUCCESSful run's max date and `update_load_metadata` appends a new row.

REFERENCE IMPLEMENTATION — NOT IMPORTED BY THE NOTEBOOKS (task-032)
------------------------------------------------------------------
The Fabric notebooks do NOT import this package; both `bronze-to-silver.Notebook`
and `silver-to-gold2.Notebook` define these functions inline. The mirror is
enforced, not trusted — `tests/test_watermark.py::TestNotebookParity` parses
each notebook, extracts its own definitions, and asserts they produce identical
results to these functions over a fixture. Divergence fails CI.

**If you change a function here, change the notebook(s) to match (or vice versa).**

DESIGN NOTES — see `.claude/support/documents/incremental_load_strategy.md § 4`
for the full contract. Summary:

  * One watermark mechanism per tracked source. The procurement pipeline uses a
    single source_table key, `bronze_procurement_transactional`, shared by both
    the silver and gold layers — that gives ONE effective watermark value per
    run, consumed identically by both notebooks (criterion 4).

  * Precedence (criterion 3):
        p_full_load == "true"          -> "1900-01-01"   (full load; load from epoch)
        p_from_date  != "1900-01-01"   -> p_from_date     (explicit manual override)
        else                            -> last SUCCESSful load's last_load_date
                                          (auto-retrieve; "1900-01-01" if no row)
    The default `p_from_date == "1900-01-01"` is the "not explicitly set" sentinel;
    `p_full_load=true` is the "load from epoch" case. This avoids a three-way
    ambiguity between "default", "explicit full", and "explicit override".

  * Gold coordination: silver-to-gold2 calls `get_last_load_date` with the SAME
    `source_table` key, but excludes the CURRENT run's execution_id so it reads
    the PREVIOUS run's watermark (bronze-to-silver has already written its SUCCESS
    row by the time silver-to-gold2 starts). Both layers therefore window on the
    same effective watermark for a given run — no second watermark mechanism.
"""

from datetime import datetime, date
from typing import Optional

from pyspark.sql import DataFrame, SparkSession, functions as F
from pyspark.sql.types import (
    StructType,
    StructField,
    StringType,
    DateType,
    TimestampType,
    LongType,
)


# ---------------------------------------------------------------------------
# Schema / constants
# ---------------------------------------------------------------------------

METADATA_SCHEMA = StructType([
    StructField("source_table", StringType(), False),       # e.g. "bronze_procurement_transactional"
    StructField("last_load_date", DateType(), False),       # max date loaded (watermark)
    StructField("load_timestamp", TimestampType(), False),   # when this row was written
    StructField("rows_loaded", LongType(), True),            # row count in this load (NULL on FAILED)
    StructField("load_status", StringType(), False),         # SUCCESS | FAILED | IN_PROGRESS
    StructField("execution_id", StringType(), True),          # pipeline run id (for gold coordination)
])

DEFAULT_WATERMARK = "1900-01-01"
DEFAULT_SOURCE_TABLE = "bronze_procurement_transactional"
DEFAULT_METADATA_TABLE_FQN = "oem_lh.bronze_load_metadata"


# ---------------------------------------------------------------------------
# Pure functions (testable without Spark writes)
# ---------------------------------------------------------------------------

def resolve_effective_watermark(
    p_full_load: str,
    p_from_date: str,
    last_load_date: Optional[date],
) -> str:
    """
    Resolve the effective watermark for this run as a "YYYY-MM-DD" string.

    Precedence (criterion 3):
      1. p_full_load == "true" (case-insensitive) -> "1900-01-01" (full load)
      2. p_from_date != "1900-01-01"              -> p_from_date  (explicit override)
      3. last_load_date is not None               -> strftime of last_load_date
      4. otherwise                                -> "1900-01-01" (no prior SUCCESS)

    The "1900-01-01" value of p_from_date is the "not explicitly set" sentinel:
    p_full_load=true is the explicit "load from epoch" path, so a caller that
    wants a full refresh sets p_full_load rather than relying on the default.
    """
    if (p_full_load or "").strip().lower() == "true":
        return DEFAULT_WATERMARK
    override = (p_from_date or "").strip()
    if override and override != DEFAULT_WATERMARK:
        return override
    if last_load_date is not None:
        return last_load_date.strftime("%Y-%m-%d")
    return DEFAULT_WATERMARK


def metadata_row(
    source_table: str,
    last_load_date,
    rows_loaded: Optional[int],
    status: str,
    execution_id: Optional[str] = None,
    now: Optional[datetime] = None,
):
    """
    Build ONE metadata row tuple matching METADATA_SCHEMA, for append.

    `now` is injectable so tests can pin the timestamp; the notebook call site
    passes `now=datetime.now()` (the default at write time).
    """
    ts = now if now is not None else datetime.now()
    # Coerce last_load_date to a datetime.date so the row matches DateType().
    # Accepts either a datetime.date or a "YYYY-MM-DD" string; the FAILED path
    # passes the effective watermark string (criterion: FAILED rows record the
    # watermark that was attempted, not a new max date — there is no new max).
    if isinstance(last_load_date, str):
        last_load_date = datetime.strptime(last_load_date, "%Y-%m-%d").date()
    elif isinstance(last_load_date, datetime):
        last_load_date = last_load_date.date()
    return (source_table, last_load_date, ts, rows_loaded, status, execution_id)


# ---------------------------------------------------------------------------
# Spark-dependent functions (the read side is testable via a DataFrame fixture;
# the write side is a thin Delta append that runs in Fabric)
# ---------------------------------------------------------------------------

def get_last_load_date(
    metadata_df: DataFrame,
    source_table: str,
    exclude_execution_id: Optional[str] = None,
) -> Optional[date]:
    """
    Return the last SUCCESSful load's `last_load_date` for `source_table`, or
    None if no such row exists.

    Args:
        metadata_df: the bronze_load_metadata table (or a fixture DataFrame).
        source_table: the source_table key to filter on.
        exclude_execution_id: if non-empty, exclude rows with this execution_id.
            Used by silver-to-gold2 to skip the CURRENT run's SUCCESS row
            (bronze-to-silver writes it before gold starts) and read the
            PREVIOUS run's watermark — so both layers window on the same value.

    Returns:
        A datetime.date, or None if no SUCCESS row matches.
    """
    q = (
        metadata_df
        .filter(F.col("source_table") == source_table)
        .filter(F.col("load_status") == "SUCCESS")
    )
    if exclude_execution_id:
        # Empty string or None: don't filter (manual notebook runs have no id).
        q = q.filter(F.col("execution_id") != F.lit(exclude_execution_id))
    row = (
        q.orderBy(F.col("load_timestamp").desc())
        .limit(1)
        .select("last_load_date")
        .collect()
    )
    if not row:
        return None
    ld = row[0]["last_load_date"]
    if ld is None:
        return None
    if isinstance(ld, datetime):
        return ld.date()
    return ld  # already a datetime.date


def update_load_metadata(
    spark: SparkSession,
    source_table: str,
    last_load_date,
    rows_loaded: Optional[int],
    status: str,
    execution_id: Optional[str] = None,
    table_fqn: str = DEFAULT_METADATA_TABLE_FQN,
    now: Optional[datetime] = None,
) -> None:
    """
    Append one metadata row to `bronze_load_metadata`.

    Idempotent table creation: the table is created IF NOT EXISTS with
    METADATA_SCHEMA on first call. In Fabric this is a Delta CREATE TABLE;
    locally the table_fqn would need to be a writable parquet path — the local
    test suite does NOT exercise this write path (delta-spark is not installed),
    it exercises the row construction via `metadata_row` and the read path via
    `get_last_load_date` over a fixture DataFrame.
    """
    row = metadata_row(
        source_table=source_table,
        last_load_date=last_load_date,
        rows_loaded=rows_loaded,
        status=status,
        execution_id=execution_id,
        now=now,
    )
    df = spark.createDataFrame([row], schema=METADATA_SCHEMA)
    # Ensure the table exists with the right schema (no-op if it already does).
    # Delta-only; runs in Fabric, not in local pytest.
    try:
        spark.sql(
            f"CREATE TABLE IF NOT EXISTS {table_fqn} "
            f"USING DELTA AS SELECT * FROM df"
        )
    except Exception:
        # Fall back to a plain append; the table is expected to exist in Fabric
        # after the first run. Swallowing here is acceptable because the append
        # below will re-raise if the table genuinely cannot be written.
        pass
    df.write.format("delta").mode("append").saveAsTable(table_fqn)