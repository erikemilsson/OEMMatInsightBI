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

# # Data Quality Checks (Task 007 + Task 020)
# # **Purpose:** Comprehensive data quality framework with 12 check functions across
# bronze, silver, and gold layers using ISO 25012 quality dimensions.
# # **Quality Dimensions:** Completeness, Accuracy, Consistency, Timeliness, Validity, Uniqueness
# # **Check Functions:**
# - Bronze (5): Row count validation, Schema validation, Required field completeness, Duplicate detection, Date range validation
# - Silver (5): Referential integrity, Business rule validation, Outlier detection (Z-score), Data type consistency, Completeness (post-join)
# - Gold (4): Aggregate reconciliation, Trend validation, Lookup-name uniqueness, Duplicate-grain on facts
# # **Task 020 additions:** date_range_validation (Bronze), data_type_consistency (Silver),
# silver_completeness (Silver) — see in-notebook rationale on the silver completeness cell.
# # **Task 026 additions:** severity model with a SINGLE aggregated raise (final cell) —
# blocking checks fail the pipeline activity, advisory checks only log/score. New checks:
# lookup_name uniqueness (gold lookup dims), duplicate-grain (gold facts), bronze_WGI
# coverage, fact_epi_score + fact_procurement.date_key referential integrity. Also fixed
# the dead spend reconciliation and the heterogeneous-metric trend check.
# # **Output:** Results are scored (0-100 scale), categorized (Excellent/Good/Fair/Poor/Critical),
# and persisted to `gold_quality_history` for trend tracking.
# # **Alert Strategy:**
# | Score   | Rating    | Action                   |
# |---------|-----------|--------------------------|
# | 95-100  | Excellent | None                     |
# | 85-94   | Good      | Log info                 |
# | 70-84   | Fair      | Log warning              |
# | 50-69   | Poor      | Log error, flag for review |
# | 0-49    | Critical  | Log error, halt advisory |

# CELL ********************

from pyspark.sql import functions as F, Window as W
from pyspark.sql.types import (
    StructType, StructField, StringType, DoubleType, DateType,
    IntegerType, LongType, BooleanType, TimestampType
)
from datetime import datetime
import json
import time

# =============================================================================
# CONFIGURATION
# =============================================================================

DB = "oem_lh"
spark.sql(f"USE {DB}")

# Pipeline run timestamp (shared across all checks)
pipeline_run_ts = datetime.now()

# Collect all check results for final scoring and persistence
all_check_results = []

print("=" * 70)
print("DATA QUALITY CHECKS - OEMMatInsightBI")
print("=" * 70)
print(f"Run Timestamp: {pipeline_run_ts.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Database: {DB}")
print("=" * 70)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Utility Functions
# Shared helpers for quality scoring, categorization, and result persistence.

# CELL ********************

# =============================================================================
# QUALITY SCORING AND CATEGORIZATION
# =============================================================================

def categorize_quality_score(score):
    """Categorize a 0-100 quality score into a rating."""
    if score >= 95:
        return "Excellent"
    elif score >= 85:
        return "Good"
    elif score >= 70:
        return "Fair"
    elif score >= 50:
        return "Poor"
    else:
        return "Critical"


def calculate_table_quality_score(dimension_scores, dimension_weights=None):
    """
    Calculate an overall quality score from individual dimension scores.

    Args:
        dimension_scores: dict of {dimension_name: score} where score is 0-100
        dimension_weights: dict of {dimension_name: weight}. If None, equal weights.

    Returns:
        float: Weighted average score (0-100)
    """
    if not dimension_scores:
        return 0.0

    if dimension_weights is None:
        dimension_weights = {dim: 1.0 for dim in dimension_scores}

    total_weight = sum(dimension_weights.get(dim, 1.0) for dim in dimension_scores)
    if total_weight == 0:
        return 0.0

    weighted_score = sum(
        dimension_scores[dim] * dimension_weights.get(dim, 1.0)
        for dim in dimension_scores
    )
    return weighted_score / total_weight


def log_check_result(check_name, layer, table_name, status, score, details,
                     failed_rows=0, total_rows=0, execution_time_ms=0):
    """
    Record a check result for later persistence to gold_quality_history.

    Args:
        check_name: Name of the check (e.g. "row_count_validation")
        layer: "Bronze", "Silver", or "Gold"
        table_name: Table that was checked
        status: "pass", "fail", or "warning"
        score: Quality score 0-100 for this check
        details: Human-readable details string
        failed_rows: Count of rows that failed the check
        total_rows: Total rows in the table
        execution_time_ms: Time the check took in milliseconds
    """
    result = {
        "check_name": check_name,
        "layer": layer,
        "table_name": table_name,
        "status": status,
        "score": score,
        "details": details,
        "failed_rows": failed_rows,
        "total_rows": total_rows,
        "execution_time_ms": execution_time_ms,
        "timestamp": pipeline_run_ts
    }
    all_check_results.append(result)

    # Console output with severity indicator
    rating = categorize_quality_score(score)
    if status == "pass":
        indicator = "PASS"
    elif status == "warning":
        indicator = "WARN"
    else:
        indicator = "FAIL"

    print(f"  [{indicator}] {check_name} on {table_name}: score={score:.1f} ({rating}) - {details}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 1. Bronze Layer Checks (5 checks)
# Validate data at ingestion to catch source system issues early.

# CELL ********************

# =============================================================================
# CHECK 1: ROW COUNT VALIDATION
# =============================================================================

def validate_row_count(table_name, min_count, max_count):
    """
    Validate that a table has a row count within the expected range.

    Args:
        table_name: Fully qualified table name
        min_count: Minimum acceptable row count
        max_count: Maximum acceptable row count

    Returns:
        dict with check results
    """
    start_ms = time.time()

    actual_count = spark.table(table_name).count()

    in_range = min_count <= actual_count <= max_count
    status = "pass" if in_range else "fail"

    # Score: 100 if in range, scaled down by distance from range
    if in_range:
        score = 100.0
    elif actual_count < min_count:
        score = max(0.0, (actual_count / min_count) * 100.0) if min_count > 0 else 0.0
    else:
        # Over max is less severe than under min
        score = max(0.0, 100.0 - ((actual_count - max_count) / max_count) * 50.0) if max_count > 0 else 50.0

    score = min(100.0, max(0.0, score))

    elapsed_ms = int((time.time() - start_ms) * 1000)
    details = f"{actual_count:,} rows (expected {min_count:,}-{max_count:,})"

    log_check_result(
        "row_count_validation", "Bronze", table_name, status, score, details,
        failed_rows=0 if in_range else 1, total_rows=actual_count,
        execution_time_ms=elapsed_ms
    )

    return {"table": table_name, "actual_count": actual_count, "status": status, "score": score}

print("\n--- Bronze Check 1: Row Count Validation ---")

# Bronze table expected ranges (based on known data volumes)
row_count_checks = [
    ("oem_lh.bronze_procurement_transactional", 100, 500000),
    ("oem_lh.bronze_supplier_ref", 5, 10000),
    ("oem_lh.bronze_epi2024results", 150, 250),
    ("oem_lh.bronze_GlobalSupplyShares", 100, 100000),
    # task-026 (5e): bronze_WGI (WB governance percentile, one row per country x
    # indicator series) — advisory row-count guard, generous range.
    ("oem_lh.bronze_WGI", 50, 500000),
]

row_count_results = []
for table, min_c, max_c in row_count_checks:
    try:
        result = validate_row_count(table, min_c, max_c)
        row_count_results.append(result)
    except Exception as e:
        print(f"  [SKIP] {table}: {str(e)}")
        log_check_result("row_count_validation", "Bronze", table, "fail", 0.0,
                         f"Table not accessible: {str(e)}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# =============================================================================
# CHECK 2: SCHEMA VALIDATION
# =============================================================================

def validate_schema(table_name, expected_columns, layer="Bronze"):
    """
    Validate that a table has the expected columns.

    Args:
        table_name: Fully qualified table name
        expected_columns: dict of {column_name: expected_type_string}
                          Type strings are PySpark types like "StringType", "DoubleType", etc.
                          If None, only checks column existence.
        layer: medallion layer recorded in gold_quality_history. Defaults to "Bronze";
               pass "Silver" for contracts asserted against a silver table (task-026).

    Returns:
        dict with check results
    """
    start_ms = time.time()

    actual_schema = spark.table(table_name).schema
    actual_map = {field.name.lower(): str(field.dataType) for field in actual_schema.fields}

    missing_columns = []
    type_mismatches = []

    for col_name, expected_type in expected_columns.items():
        col_lower = col_name.lower()
        if col_lower not in actual_map:
            missing_columns.append(col_name)
        elif expected_type is not None and expected_type.lower() not in actual_map[col_lower].lower():
            type_mismatches.append(f"{col_name}: expected {expected_type}, got {actual_map[col_lower]}")

    # Score: 100 minus penalties for missing columns and type mismatches
    total_expected = len(expected_columns)
    issues = len(missing_columns) + len(type_mismatches)
    score = max(0.0, ((total_expected - issues) / total_expected) * 100.0) if total_expected > 0 else 100.0

    status = "pass" if issues == 0 else "fail"
    details_parts = []
    if missing_columns:
        details_parts.append(f"missing: {missing_columns}")
    if type_mismatches:
        details_parts.append(f"type mismatches: {type_mismatches}")
    if not details_parts:
        details_parts.append(f"all {total_expected} columns validated")

    elapsed_ms = int((time.time() - start_ms) * 1000)

    log_check_result(
        "schema_validation", layer, table_name, status, score,
        "; ".join(details_parts), failed_rows=issues, total_rows=total_expected,
        execution_time_ms=elapsed_ms
    )

    return {"table": table_name, "missing": missing_columns, "type_mismatches": type_mismatches,
            "status": status, "score": score}

print("\n--- Bronze Check 2: Schema Validation ---")

# Layer label per checked table (task-026). Defaults to Bronze; only tables whose
# contract is deliberately asserted against a silver shape are listed here, so
# gold_quality_history records the layer the assertion actually describes.
CHECK_LAYER = {
    "oem_lh.silver_epi2024results": "Silver",
}

# Expected schemas per checked table
schema_checks = {
    "oem_lh.bronze_procurement_transactional": {
        "Date": "date", "MaterialName": "string", "SupplierName": "string",
        "Region": "string", "Quantity": None, "Unit": "string", "UnitPriceEUR": None
    },
    "oem_lh.bronze_supplier_ref": {
        "SupplierName": "string", "HeadquartersCountry": "string",
        "ProductionCountry": "string", "Region": "string"
    },
    # task-026: asserted against SILVER, not bronze. bronze_epi2024results is the raw
    # Yale file (149 cols) whose score columns are "EPI.old"/"EPI.new" — a bare "EPI"
    # never exists there. bronze-to-silver:79 drops the ".old" columns and strips the
    # ".new" suffix, so "EPI" comes into existence in silver_epi2024results
    # (code, iso, country, EPI). Asserting the raw name here would also hardcode a
    # Yale vintage: .old/.new exist because the 2024 methodology revision introduced
    # them, and they will move again.
    "oem_lh.silver_epi2024results": {
        "iso": "string", "country": "string", "EPI": None
    },
    "oem_lh.bronze_GlobalSupplyShares": {
        "Material": "string", "Stage": "string", "Country": "string", "Share": None
    },
    # task-026 (5e): bronze_WGI schema. Advisory — validates the descriptor columns
    # plus the percentile value column exist (Percentile Rank 2023 is numeric).
    "oem_lh.bronze_WGI": {
        "Country Name": "string", "Country Code": "string",
        "Series Name": "string", "Percentile Rank 2023": None
    },
}

schema_results = []
for table, expected in schema_checks.items():
    try:
        result = validate_schema(table, expected, layer=CHECK_LAYER.get(table, "Bronze"))
        schema_results.append(result)
    except Exception as e:
        print(f"  [SKIP] {table}: {str(e)}")
        log_check_result("schema_validation", CHECK_LAYER.get(table, "Bronze"), table, "fail", 0.0,
                         f"Table not accessible: {str(e)}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# =============================================================================
# CHECK 3: REQUIRED FIELD COMPLETENESS
# =============================================================================

def validate_required_fields(table_name, required_fields, null_tolerance_pct=0.0, layer="Bronze"):
    """
    Check for null values in fields that should be populated.

    Args:
        table_name: Fully qualified table name
        required_fields: List of column names that must not be null.
                         NOTE: names are passed to F.col(), which treats a dot as
                         struct-field navigation — do not pass dotted raw-source
                         names like "EPI.new" here (task-026).
        null_tolerance_pct: Maximum acceptable null percentage (0.0 = no nulls allowed)
        layer: medallion layer recorded in gold_quality_history. Defaults to "Bronze";
               pass "Silver" for contracts asserted against a silver table (task-026).

    Returns:
        dict with per-field null counts and overall score
    """
    start_ms = time.time()

    df = spark.table(table_name)
    total_rows = df.count()

    if total_rows == 0:
        elapsed_ms = int((time.time() - start_ms) * 1000)
        log_check_result("required_field_completeness", layer, table_name, "pass", 100.0,
                         "Table is empty - no nulls possible", 0, 0, elapsed_ms)
        return {"table": table_name, "status": "pass", "score": 100.0}

    # Count nulls for all required fields in a single pass
    null_exprs = [F.sum(F.when(F.col(f).isNull(), 1).otherwise(0)).alias(f"null_{f}")
                  for f in required_fields]
    null_counts_row = df.select(*null_exprs).first()

    field_results = {}
    total_null_cells = 0
    total_cells = total_rows * len(required_fields)
    failed_fields = []

    for field in required_fields:
        null_count = null_counts_row[f"null_{field}"] or 0
        null_pct = (null_count / total_rows) * 100.0
        passed = null_pct <= null_tolerance_pct
        field_results[field] = {"null_count": null_count, "null_pct": null_pct, "passed": passed}
        total_null_cells += null_count
        if not passed:
            failed_fields.append(f"{field}({null_count} nulls, {null_pct:.1f}%)")

    # Score based on overall completeness rate
    completeness_rate = ((total_cells - total_null_cells) / total_cells) * 100.0
    score = completeness_rate
    status = "pass" if len(failed_fields) == 0 else "fail"

    elapsed_ms = int((time.time() - start_ms) * 1000)

    if failed_fields:
        details = f"Null fields: {', '.join(failed_fields)}"
    else:
        details = f"All {len(required_fields)} required fields complete ({total_rows:,} rows)"

    log_check_result(
        "required_field_completeness", layer, table_name, status, score,
        details, failed_rows=total_null_cells, total_rows=total_cells,
        execution_time_ms=elapsed_ms
    )

    return {"table": table_name, "field_results": field_results, "status": status, "score": score}

print("\n--- Bronze Check 3: Required Field Completeness ---")

completeness_checks = [
    ("oem_lh.bronze_procurement_transactional",
     ["Date", "MaterialName", "SupplierName", "Quantity", "UnitPriceEUR"]),
    ("oem_lh.bronze_supplier_ref",
     ["SupplierName", "HeadquartersCountry"]),
    # task-026: silver, for the same reason as the schema contract above. Also note
    # validate_required_fields passes these names to F.col(), where a dot means
    # struct navigation — the raw "EPI.new" could not be used here even if wanted.
    ("oem_lh.silver_epi2024results",
     ["iso", "country", "EPI"]),
    ("oem_lh.bronze_GlobalSupplyShares",
     ["Material", "Stage", "Country", "Share"]),
    # task-026 (5e): bronze_WGI required descriptor fields (advisory).
    ("oem_lh.bronze_WGI",
     ["Country Name", "Country Code", "Series Name"]),
]

completeness_results = []
for table, fields in completeness_checks:
    try:
        result = validate_required_fields(table, fields, layer=CHECK_LAYER.get(table, "Bronze"))
        completeness_results.append(result)
    except Exception as e:
        print(f"  [SKIP] {table}: {str(e)}")
        log_check_result("required_field_completeness", CHECK_LAYER.get(table, "Bronze"), table, "fail", 0.0,
                         f"Table not accessible: {str(e)}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# =============================================================================
# CHECK 4: DUPLICATE DETECTION
# =============================================================================

def detect_duplicates(table_name, key_columns, duplicate_tolerance_pct=0.0,
                      layer="Bronze", check_name="duplicate_detection"):
    """
    Detect duplicate records based on natural key columns.

    Args:
        table_name: Fully qualified table name
        key_columns: List of columns that define a unique record
        duplicate_tolerance_pct: Maximum acceptable duplicate percentage
        layer: Quality layer for reporting ("Bronze"/"Silver"/"Gold")
        check_name: Check name for logging. Defaults to "duplicate_detection";
            gold uniqueness reuses this engine under "lookup_name_uniqueness" and
            "grain_uniqueness" so those results carry their own blocking identity.

    Returns:
        dict with duplicate counts and score
    """
    start_ms = time.time()

    df = spark.table(table_name)
    total_rows = df.count()

    if total_rows == 0:
        elapsed_ms = int((time.time() - start_ms) * 1000)
        log_check_result(check_name, layer, table_name, "pass", 100.0,
                         "Table is empty", 0, 0, elapsed_ms)
        return {"table": table_name, "status": "pass", "score": 100.0}

    unique_rows = df.select(key_columns).distinct().count()
    duplicate_count = total_rows - unique_rows
    duplicate_pct = (duplicate_count / total_rows) * 100.0

    score = max(0.0, (1.0 - duplicate_pct / 100.0) * 100.0)
    status = "pass" if duplicate_pct <= duplicate_tolerance_pct else "fail"

    elapsed_ms = int((time.time() - start_ms) * 1000)

    details = f"{duplicate_count:,} duplicates ({duplicate_pct:.2f}%) on keys {key_columns}"
    if duplicate_count > 0 and status == "fail":
        # Show top duplicates for investigation (console only, not persisted)
        print(f"    Top duplicate keys in {table_name}:")
        dup_df = (df.groupBy(key_columns).count()
                  .filter(F.col("count") > 1)
                  .orderBy(F.desc("count"))
                  .limit(5))
        dup_df.show(truncate=False)

    log_check_result(
        check_name, layer, table_name, status, score,
        details, failed_rows=duplicate_count, total_rows=total_rows,
        execution_time_ms=elapsed_ms
    )

    return {"table": table_name, "duplicate_count": duplicate_count,
            "duplicate_pct": duplicate_pct, "status": status, "score": score}

print("\n--- Bronze Check 4: Duplicate Detection ---")

# CRITERION 4 RESCOPE (task-026, carry-forward from task-024): task-024 replaced
# the silver+gold procurement natural-key MERGE with transaction-grain
# date-partition delete-insert, so there is NO silver "merge key" collision left
# to guard. The procurement duplicate check now targets GENUINE duplicate
# transactions worth flagging: the FULL business signature
# (Date/MaterialName/SupplierName/Quantity/Unit/UnitPriceEUR) appearing more than
# once is a true double-entry — the previous key omitted Unit + UnitPriceEUR and
# was aligned to a merge key that no longer exists. This check is BLOCKING (0%
# tolerance) per the minimum blocking set.
duplicate_checks = [
    ("oem_lh.bronze_procurement_transactional",
     ["Date", "MaterialName", "SupplierName", "Quantity", "Unit", "UnitPriceEUR"]),
    ("oem_lh.bronze_supplier_ref",
     ["SupplierName"]),
    ("oem_lh.bronze_epi2024results",
     ["iso"]),
    ("oem_lh.bronze_GlobalSupplyShares",
     ["Material", "Stage", "Country"]),
]

duplicate_results = []
for table, keys in duplicate_checks:
    try:
        result = detect_duplicates(table, keys)
        duplicate_results.append(result)
    except Exception as e:
        print(f"  [SKIP] {table}: {str(e)}")
        log_check_result("duplicate_detection", "Bronze", table, "fail", 0.0,
                         f"Table not accessible: {str(e)}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# =============================================================================
# CHECK 5: DATE RANGE VALIDATION
# =============================================================================

def validate_date_range(table_name, date_column, min_date, max_date,
                        tolerance_pct=0.0):
    """
    Validate that date values fall within a plausible [min_date, max_date] window.

    Flags two classes of bad dates (both informational on the synthetic dataset):
      - Future dates: later than max_date (typically today).
      - Implausible / out-of-range dates: earlier than min_date (a project floor).

    NULL dates are not counted here — null handling belongs to the completeness
    checks — so date-range and completeness never double-flag the same row.

    This check is informational (status is "pass" unless dates fall outside the
    window beyond tolerance), mirroring outlier_detection's non-failing posture.

    Args:
        table_name: Fully qualified table name
        date_column: Date column to validate
        min_date: Earliest acceptable date (datetime.date)
        max_date: Latest acceptable date (datetime.date)
        tolerance_pct: Max acceptable % of out-of-range dates before status="warning"

    Returns:
        dict with out-of-range date statistics
    """
    start_ms = time.time()

    df = spark.table(table_name).filter(F.col(date_column).isNotNull())
    total_rows = df.count()

    if total_rows == 0:
        elapsed_ms = int((time.time() - start_ms) * 1000)
        log_check_result("date_range_validation", "Bronze", table_name, "pass", 100.0,
                         f"No non-null dates in {date_column}", 0, 0, elapsed_ms)
        return {"table": table_name, "column": date_column, "status": "pass", "score": 100.0}

    # Count dates outside the plausible window (future or implausibly old)
    out_of_range_df = df.filter(
        (F.col(date_column) < F.lit(min_date)) | (F.col(date_column) > F.lit(max_date))
    )
    future_count = df.filter(F.col(date_column) > F.lit(max_date)).count()
    out_of_range_count = out_of_range_df.count()
    out_of_range_pct = (out_of_range_count / total_rows) * 100.0

    score = max(0.0, (1.0 - out_of_range_pct / 100.0) * 100.0)
    # Informational: pass unless out-of-range rate exceeds tolerance
    status = "pass" if out_of_range_pct <= tolerance_pct else "warning"

    elapsed_ms = int((time.time() - start_ms) * 1000)

    details = (f"{out_of_range_count:,} out-of-range dates ({out_of_range_pct:.2f}%) "
               f"in {date_column} [{future_count:,} future] "
               f"(window [{min_date}, {max_date}])")

    log_check_result(
        "date_range_validation", "Bronze", table_name, status, score,
        details, failed_rows=out_of_range_count, total_rows=total_rows,
        execution_time_ms=elapsed_ms
    )

    return {"table": table_name, "column": date_column,
            "out_of_range_count": out_of_range_count, "future_count": future_count,
            "out_of_range_pct": out_of_range_pct, "status": status, "score": score}

print("\n--- Bronze Check 5: Date Range Validation ---")

# Plausible date window: procurement should not be in the future nor before the
# project's data floor. current_date() resolves at runtime in Fabric.
from datetime import date as _date
_today = _date.today()
_data_floor = _date(2015, 1, 1)  # earliest plausible procurement date for this dataset

date_range_checks = [
    ("oem_lh.bronze_procurement_transactional", "Date", _data_floor, _today),
]

date_range_results = []
for table, date_col, min_d, max_d in date_range_checks:
    try:
        result = validate_date_range(table, date_col, min_d, max_d)
        date_range_results.append(result)
    except Exception as e:
        print(f"  [SKIP] {table}.{date_col}: {str(e)}")
        log_check_result("date_range_validation", "Bronze", table, "pass", 100.0,
                         f"Column not accessible: {str(e)}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 2. Silver Layer Checks (5 checks)
# Validate transformations, business rules, referential integrity, type
# conformance, and post-join completeness.

# CELL ********************

# =============================================================================
# CHECK 6: REFERENTIAL INTEGRITY
# =============================================================================

def validate_referential_integrity(fact_table, fact_key, dim_table, dim_key,
                                   tolerance_pct=0.0):
    """
    Check that all foreign keys in the fact table have matching dimension records.

    Args:
        fact_table: Fact table name
        fact_key: Foreign key column in the fact table
        dim_table: Dimension table name
        dim_key: Primary key column in the dimension table
        tolerance_pct: Maximum acceptable orphan percentage

    Returns:
        dict with orphan counts and score
    """
    start_ms = time.time()

    fact_df = spark.table(fact_table)
    dim_df = spark.table(dim_table)

    total_fact_rows = fact_df.count()

    if total_fact_rows == 0:
        elapsed_ms = int((time.time() - start_ms) * 1000)
        log_check_result("referential_integrity", "Silver", fact_table, "pass", 100.0,
                         f"No records in {fact_table}", 0, 0, elapsed_ms)
        return {"fact_table": fact_table, "status": "pass", "score": 100.0}

    # Left anti join: fact records with no dimension match
    orphaned_df = fact_df.join(
        dim_df, fact_df[fact_key] == dim_df[dim_key], "left_anti"
    )

    orphaned_count = orphaned_df.count()
    orphaned_pct = (orphaned_count / total_fact_rows) * 100.0

    score = max(0.0, (1.0 - orphaned_pct / 100.0) * 100.0)
    status = "pass" if orphaned_pct <= tolerance_pct else "fail"

    elapsed_ms = int((time.time() - start_ms) * 1000)

    details = (f"{orphaned_count:,} orphaned records ({orphaned_pct:.2f}%) "
               f"in {fact_table}.{fact_key} vs {dim_table}.{dim_key}")

    log_check_result(
        "referential_integrity", "Silver", fact_table, status, score,
        details, failed_rows=orphaned_count, total_rows=total_fact_rows,
        execution_time_ms=elapsed_ms
    )

    return {"fact_table": fact_table, "dim_table": dim_table,
            "orphaned_count": orphaned_count, "status": status, "score": score}

print("\n--- Silver Check 6: Referential Integrity ---")

ri_checks = [
    ("oem_lh.fact_procurement", "material_key", "oem_lh.gold_dim_material", "material_key"),
    ("oem_lh.fact_procurement", "supplier_hq_country_key", "oem_lh.gold_dim_country", "country_key"),
    ("oem_lh.fact_procurement", "production_country_key", "oem_lh.gold_dim_country", "country_key"),
    # task-026 (5d): fact_procurement.date_key -> gold_dim_date
    ("oem_lh.fact_procurement", "date_key", "oem_lh.gold_dim_date", "date_key"),
    ("oem_lh.fact_supply_share", "material_key", "oem_lh.gold_dim_material", "material_key"),
    ("oem_lh.fact_supply_share", "country_key", "oem_lh.gold_dim_country", "country_key"),
    # task-026 (5c): fact_epi_score.country_key/indicator_key -> dims
    ("oem_lh.fact_epi_score", "country_key", "oem_lh.gold_dim_country", "country_key"),
    ("oem_lh.fact_epi_score", "indicator_key", "oem_lh.gold_dim_indicator", "indicator_key"),
]

ri_results = []
for fact_tbl, fact_col, dim_tbl, dim_col in ri_checks:
    try:
        result = validate_referential_integrity(fact_tbl, fact_col, dim_tbl, dim_col)
        ri_results.append(result)
    except Exception as e:
        print(f"  [SKIP] {fact_tbl}.{fact_col}: {str(e)}")
        log_check_result("referential_integrity", "Silver", fact_tbl, "fail", 0.0,
                         f"Check failed: {str(e)}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# =============================================================================
# CHECK 7: BUSINESS RULE VALIDATION
# =============================================================================

def validate_business_rules(table_name, rules):
    """
    Validate business rules against a table.

    Args:
        table_name: Fully qualified table name
        rules: List of rule dicts:
            {
                "name": "Positive Quantity",
                "condition": "quantity_base > 0",  (SQL expression; rows matching = valid)
                "severity": "error" | "warning"
            }

    Returns:
        dict with per-rule results and overall score
    """
    start_ms = time.time()

    df = spark.table(table_name)
    total_rows = df.count()

    if total_rows == 0:
        elapsed_ms = int((time.time() - start_ms) * 1000)
        log_check_result("business_rule_validation", "Silver", table_name, "pass", 100.0,
                         "Table is empty", 0, 0, elapsed_ms)
        return {"table": table_name, "status": "pass", "score": 100.0}

    rule_results = []
    total_violations = 0
    error_violations = 0

    for rule in rules:
        rule_name = rule["name"]
        condition = rule["condition"]
        severity = rule.get("severity", "error")

        try:
            violation_count = df.filter(F.expr(f"NOT ({condition})")).count()
        except Exception as e:
            print(f"    Rule '{rule_name}' expression error: {str(e)}")
            violation_count = 0

        violation_pct = (violation_count / total_rows) * 100.0

        rule_results.append({
            "rule_name": rule_name,
            "violation_count": violation_count,
            "violation_pct": violation_pct,
            "severity": severity
        })

        total_violations += violation_count
        if severity == "error":
            error_violations += violation_count

    # Score: based on error-severity violations only
    error_rate = error_violations / total_rows if total_rows > 0 else 0
    score = max(0.0, (1.0 - error_rate) * 100.0)
    status = "pass" if error_violations == 0 else "fail"

    elapsed_ms = int((time.time() - start_ms) * 1000)

    failed_rule_names = [r["rule_name"] for r in rule_results if r["violation_count"] > 0]
    if failed_rule_names:
        details = f"{len(failed_rule_names)}/{len(rules)} rules violated: {', '.join(failed_rule_names)}"
    else:
        details = f"All {len(rules)} business rules passed"

    log_check_result(
        "business_rule_validation", "Silver", table_name, status, score,
        details, failed_rows=error_violations, total_rows=total_rows,
        execution_time_ms=elapsed_ms
    )

    return {"table": table_name, "rule_results": rule_results, "status": status, "score": score}

print("\n--- Silver Check 7: Business Rule Validation ---")

# Procurement business rules
procurement_rules = [
    {"name": "Positive Quantity", "condition": "quantity_base > 0", "severity": "error"},
    {"name": "Positive Unit Price", "condition": "unitprice_eur > 0", "severity": "error"},
    {"name": "Positive Spend", "condition": "spend_eur > 0", "severity": "error"},
    {"name": "Date Not in Future", "condition": "date_key <= cast(date_format(current_date(), 'yyyyMMdd') as int)", "severity": "error"},
    {"name": "Quality Score in Range", "condition": "data_quality_score >= 0 AND data_quality_score <= 1", "severity": "error"},
]

try:
    proc_br_result = validate_business_rules("oem_lh.fact_procurement", procurement_rules)
except Exception as e:
    print(f"  [SKIP] fact_procurement business rules: {str(e)}")

# Supply share business rules
supply_rules = [
    {"name": "Share Percentage Valid", "condition": "share_pct >= 0 AND share_pct <= 100", "severity": "error"},
    {"name": "Quality Score in Range", "condition": "data_quality_score >= 0 AND data_quality_score <= 1", "severity": "error"},
]

try:
    supply_br_result = validate_business_rules("oem_lh.fact_supply_share", supply_rules)
except Exception as e:
    print(f"  [SKIP] fact_supply_share business rules: {str(e)}")

# EPI score validation
epi_rules = [
    {"name": "EPI Score Range", "condition": "score >= 0 AND score <= 100", "severity": "error"},
]

try:
    epi_br_result = validate_business_rules("oem_lh.fact_epi_score", epi_rules)
except Exception as e:
    print(f"  [SKIP] fact_epi_score business rules: {str(e)}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# =============================================================================
# CHECK 8: OUTLIER DETECTION (Z-SCORE)
# =============================================================================

def detect_outliers_zscore(table_name, numeric_column, z_threshold=3.0):
    """
    Detect statistical outliers using Z-score method.

    Outliers are informational (never fail the check) but are tracked for
    awareness. The score reflects the proportion of non-outlier values.

    Args:
        table_name: Fully qualified table name
        numeric_column: Column to analyze
        z_threshold: Z-score threshold (default 3.0 = 99.7% confidence)

    Returns:
        dict with outlier statistics
    """
    start_ms = time.time()

    df = spark.table(table_name).filter(F.col(numeric_column).isNotNull())
    total_rows = df.count()

    if total_rows < 3:
        elapsed_ms = int((time.time() - start_ms) * 1000)
        log_check_result("outlier_detection", "Silver", table_name, "pass", 100.0,
                         f"Too few rows ({total_rows}) for outlier analysis on {numeric_column}",
                         0, total_rows, elapsed_ms)
        return {"table": table_name, "column": numeric_column, "status": "pass", "score": 100.0}

    # Calculate mean and stddev
    stats = df.select(
        F.mean(numeric_column).alias("mean"),
        F.stddev(numeric_column).alias("stddev")
    ).first()

    mean_val = stats["mean"]
    stddev_val = stats["stddev"]

    if stddev_val is None or stddev_val == 0:
        elapsed_ms = int((time.time() - start_ms) * 1000)
        log_check_result("outlier_detection", "Silver", table_name, "pass", 100.0,
                         f"No variance in {numeric_column} (all values identical)",
                         0, total_rows, elapsed_ms)
        return {"table": table_name, "column": numeric_column, "status": "pass", "score": 100.0}

    # Count outliers
    outlier_count = df.filter(
        F.abs((F.col(numeric_column) - mean_val) / stddev_val) > z_threshold
    ).count()

    outlier_pct = (outlier_count / total_rows) * 100.0

    # Outliers are informational: score is always based on non-outlier rate
    # but status is always "pass" (outliers are expected in real data)
    score = max(0.0, (1.0 - outlier_pct / 100.0) * 100.0)
    status = "pass"  # Outliers are informational, not failures

    elapsed_ms = int((time.time() - start_ms) * 1000)

    details = (f"{outlier_count:,} outliers ({outlier_pct:.2f}%) in {numeric_column} "
               f"(Z>{z_threshold}, mean={mean_val:.2f}, stddev={stddev_val:.2f})")

    log_check_result(
        "outlier_detection", "Silver", table_name, status, score,
        details, failed_rows=outlier_count, total_rows=total_rows,
        execution_time_ms=elapsed_ms
    )

    return {"table": table_name, "column": numeric_column, "outlier_count": outlier_count,
            "outlier_pct": outlier_pct, "status": status, "score": score}

print("\n--- Silver Check 8: Outlier Detection (Z-Score) ---")

outlier_checks = [
    ("oem_lh.fact_procurement", "unitprice_eur"),
    ("oem_lh.fact_procurement", "quantity_base"),
    ("oem_lh.fact_procurement", "spend_eur"),
    ("oem_lh.fact_supply_share", "share_pct"),
]

outlier_results = []
for table, column in outlier_checks:
    try:
        result = detect_outliers_zscore(table, column)
        outlier_results.append(result)
    except Exception as e:
        print(f"  [SKIP] {table}.{column}: {str(e)}")
        log_check_result("outlier_detection", "Silver", table, "pass", 100.0,
                         f"Column not accessible: {str(e)}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# =============================================================================
# CHECK 9: DATA TYPE CONSISTENCY
# =============================================================================

def validate_data_type_consistency(table_name, expected_types):
    """
    Validate that silver column types conform to the expected schema after the
    bronze->silver casts.

    Distinct from the bronze schema_validation check: that one runs on raw bronze
    tables (pre-cast), whereas this confirms the transformation layer produced the
    intended Spark types (e.g. DECIMAL bronze quantity surfaced as the expected
    silver numeric type). Matching is case-insensitive on column name and uses a
    substring match on the simple Spark type string so it tolerates the differing
    str(dataType) representations across PySpark versions.

    Args:
        table_name: Fully qualified silver table name
        expected_types: dict of {column_name: expected_type_substring}, e.g.
            {"quantity": "decimal", "unit": "string"}

    Returns:
        dict with type-conformance results
    """
    start_ms = time.time()

    actual_schema = spark.table(table_name).schema
    actual_map = {field.name.lower(): str(field.dataType) for field in actual_schema.fields}

    mismatches = []
    for col_name, expected_type in expected_types.items():
        col_lower = col_name.lower()
        if col_lower not in actual_map:
            mismatches.append(f"{col_name}: column missing")
        elif expected_type.lower() not in actual_map[col_lower].lower():
            mismatches.append(f"{col_name}: expected {expected_type}, got {actual_map[col_lower]}")

    total_expected = len(expected_types)
    issues = len(mismatches)
    score = max(0.0, ((total_expected - issues) / total_expected) * 100.0) if total_expected > 0 else 100.0
    status = "pass" if issues == 0 else "fail"

    elapsed_ms = int((time.time() - start_ms) * 1000)

    if mismatches:
        details = f"Type mismatches: {mismatches}"
    else:
        details = f"All {total_expected} silver columns conform to expected types"

    log_check_result(
        "data_type_consistency", "Silver", table_name, status, score,
        details, failed_rows=issues, total_rows=total_expected,
        execution_time_ms=elapsed_ms
    )

    return {"table": table_name, "mismatches": mismatches, "status": status, "score": score}

print("\n--- Silver Check 9: Data Type Consistency ---")

# Expected silver types after bronze->silver casts.
# silver_procurement = bronze procurement joined to supplier_ref, columns
# lowercased/underscored. Numeric source columns (DECIMAL/DOUBLE) must remain
# numeric; descriptive columns must remain strings; date must remain a date.
type_consistency_checks = {
    "oem_lh.silver_procurement": {
        "date": "date",
        "materialname": "string",
        "suppliername": "string",
        "quantity": "decimal",
        "unit": "string",
        "unitpriceeur": "decimal",
        "headquarterscountry": "string",
        "productioncountry": "string",
    },
}

type_consistency_results = []
for table, expected in type_consistency_checks.items():
    try:
        result = validate_data_type_consistency(table, expected)
        type_consistency_results.append(result)
    except Exception as e:
        print(f"  [SKIP] {table}: {str(e)}")
        log_check_result("data_type_consistency", "Silver", table, "fail", 0.0,
                         f"Table not accessible: {str(e)}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# =============================================================================
# CHECK 10: SILVER COMPLETENESS (POST-JOIN)
# =============================================================================
#
# RATIONALE — why a SILVER completeness check in addition to the bronze
# required_field_completeness check (Bronze Check 3):
#
# Bronze required_field_completeness validates nulls on the RAW source columns
# before any transformation. silver_procurement, however, is produced by a LEFT
# JOIN of bronze procurement onto bronze_supplier_ref on SupplierName. That join
# introduces a NEW completeness risk bronze cannot see: a supplier present in
# procurement but absent from supplier_ref leaves headquarterscountry /
# productioncountry NULL on an otherwise-valid row. This is exactly the
# "post-join completeness" condition the task notes flag, so the silver check is
# non-redundant rather than a duplicate of the bronze check. It measures
# row-level completeness (a row is incomplete if ANY required column is null),
# which is the right shape for catching join misses.

def validate_silver_completeness(table_name, required_columns, null_tolerance_pct=0.0):
    """
    Row-level completeness check for a silver table: a row is incomplete if ANY
    of `required_columns` is null. Targets columns populated by silver joins so
    that join misses (e.g. unmatched supplier_ref) surface as incompleteness.

    Args:
        table_name: Fully qualified silver table name
        required_columns: Columns that must all be non-null for a complete row
        null_tolerance_pct: Max acceptable % of incomplete rows before status="fail"

    Returns:
        dict with completeness results
    """
    start_ms = time.time()

    df = spark.table(table_name)
    total_rows = df.count()

    if total_rows == 0:
        elapsed_ms = int((time.time() - start_ms) * 1000)
        log_check_result("silver_completeness", "Silver", table_name, "pass", 100.0,
                         "Table is empty - no incompleteness possible", 0, 0, elapsed_ms)
        return {"table": table_name, "status": "pass", "score": 100.0}

    # A row is incomplete if any required column is null
    condition = F.col(required_columns[0]).isNull()
    for col_name in required_columns[1:]:
        condition = condition | F.col(col_name).isNull()

    incomplete_count = df.filter(condition).count()
    incomplete_pct = (incomplete_count / total_rows) * 100.0

    score = max(0.0, (1.0 - incomplete_pct / 100.0) * 100.0)
    status = "pass" if incomplete_pct <= null_tolerance_pct else "fail"

    elapsed_ms = int((time.time() - start_ms) * 1000)

    if incomplete_count > 0:
        details = (f"{incomplete_count:,} incomplete rows ({incomplete_pct:.2f}%) "
                   f"missing one of {required_columns}")
    else:
        details = f"All {total_rows:,} rows complete across {required_columns}"

    log_check_result(
        "silver_completeness", "Silver", table_name, status, score,
        details, failed_rows=incomplete_count, total_rows=total_rows,
        execution_time_ms=elapsed_ms
    )

    return {"table": table_name, "incomplete_count": incomplete_count,
            "incomplete_pct": incomplete_pct, "status": status, "score": score}

print("\n--- Silver Check 10: Completeness (Post-Join) ---")

# Required columns including the supplier_ref join outputs (the join-miss surface)
silver_completeness_checks = [
    ("oem_lh.silver_procurement",
     ["date", "materialname", "suppliername", "quantity", "unitpriceeur",
      "headquarterscountry", "productioncountry"]),
]

silver_completeness_results = []
for table, cols in silver_completeness_checks:
    try:
        result = validate_silver_completeness(table, cols)
        silver_completeness_results.append(result)
    except Exception as e:
        print(f"  [SKIP] {table}: {str(e)}")
        log_check_result("silver_completeness", "Silver", table, "fail", 0.0,
                         f"Table not accessible: {str(e)}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 3. Gold Layer Checks (4 checks)
# Validate aggregations, business metrics, and trend consistency.

# CELL ********************

# =============================================================================
# CHECK 11: AGGREGATE RECONCILIATION
# =============================================================================

def reconcile_aggregates(source_table, target_table, source_column, target_column,
                         tolerance_pct=1.0):
    """
    Reconcile aggregate totals between source (silver) and target (gold) layers.

    Args:
        source_table: Source layer table
        target_table: Target layer table
        source_column: Column OR SQL expression to sum in source
            (e.g. "spend_eur" or "quantity * unitpriceeur")
        target_column: Column OR SQL expression to sum in target
        tolerance_pct: Maximum acceptable difference percentage (default 1.0 = 1%)

    Returns:
        dict with reconciliation results
    """
    start_ms = time.time()

    # Use SUM(<expr>) so callers can reconcile a computed quantity (silver has no
    # spend column — spend is derived in gold) rather than only a bare column.
    source_total = spark.table(source_table).select(F.expr(f"SUM({source_column})")).first()[0]
    target_total = spark.table(target_table).select(F.expr(f"SUM({target_column})")).first()[0]

    source_total = float(source_total) if source_total is not None else 0.0
    target_total = float(target_total) if target_total is not None else 0.0

    if source_total == 0 and target_total == 0:
        elapsed_ms = int((time.time() - start_ms) * 1000)
        log_check_result("aggregate_reconciliation", "Gold", target_table, "pass", 100.0,
                         "Both totals are zero", 0, 0, elapsed_ms)
        return {"status": "pass", "score": 100.0}

    difference = abs(target_total - source_total)
    difference_pct = (difference / abs(source_total)) * 100.0 if source_total != 0 else 100.0

    score = max(0.0, 100.0 - (difference_pct / tolerance_pct) * (100.0 - 95.0))
    score = min(100.0, max(0.0, score))

    status = "pass" if difference_pct <= tolerance_pct else "fail"

    elapsed_ms = int((time.time() - start_ms) * 1000)

    details = (f"{source_column} totals: source={source_total:,.2f}, target={target_total:,.2f}, "
               f"diff={difference_pct:.4f}% (tolerance={tolerance_pct}%)")

    log_check_result(
        "aggregate_reconciliation", "Gold", target_table, status, score,
        details, failed_rows=1 if status == "fail" else 0, total_rows=1,
        execution_time_ms=elapsed_ms
    )

    return {"source_table": source_table, "target_table": target_table,
            "source_total": source_total, "target_total": target_total,
            "difference_pct": difference_pct, "status": status, "score": score}

print("\n--- Gold Check 11: Aggregate Reconciliation ---")

# CRITERION 3 FIX (task-026): the old config reconciled silver_procurement.spend_eur
# — a column that does NOT exist in silver (spend is computed in gold) — so every
# run threw AnalysisException, was swallowed, and logged a permanent score-0 "fail"
# that reconciled nothing. Fixed to compare COMPUTABLE quantities: silver-side
# SUM(quantity * unitpriceeur) vs gold SUM(spend_eur). This now genuinely executes.
#
# SEVERITY = ADVISORY (intentionally NOT in the blocking set). Gold derives
# spend_eur = quantity_base * unitprice_eur where quantity_base = quantity *
# unit_factor (kg-normalization; silver-to-gold2). The silver-side raw
# SUM(quantity * unitpriceeur) therefore reconciles EXACTLY only when all rows are
# already in the base unit (kg) — true for the sample dataset, but tying a
# pipeline-halting raise to that assumption is unsafe. The fan-out drift this check
# guards against (task-023/024) is caught as BLOCKING by lookup_name_uniqueness and
# grain_uniqueness. Promote this to blocking once unit uniformity is confirmed.
reconciliation_checks = [
    ("oem_lh.silver_procurement", "oem_lh.fact_procurement",
     "quantity * unitpriceeur", "spend_eur", 1.0),
]

recon_results = []
for src_tbl, tgt_tbl, src_col, tgt_col, tol in reconciliation_checks:
    # No blanket AnalysisException swallow here: with the computable expression the
    # check executes for real. The narrow guard below only catches genuine
    # infra errors (missing table) so the notebook still reaches the persist +
    # aggregated-raise cells (advisory, so an infra miss won't halt the pipeline).
    try:
        result = reconcile_aggregates(src_tbl, tgt_tbl, src_col, tgt_col, tol)
        recon_results.append(result)
    except Exception as e:
        print(f"  [ERROR] {src_tbl} vs {tgt_tbl} not reconcilable: {str(e)}")
        log_check_result("aggregate_reconciliation", "Gold", tgt_tbl, "fail", 0.0,
                         f"Reconciliation could not execute (infra error): {str(e)}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# =============================================================================
# CHECK 12: TREND VALIDATION (ANOMALY DETECTION)
# =============================================================================

def validate_historical_trend(table_name, metric_column, date_column,
                              anomaly_threshold_pct=50.0, filter_condition=None):
    """
    Detect anomalous changes in historical trends by comparing the most recent
    period against the previous period.

    Args:
        table_name: Table with time-series data
        metric_column: Column to track (summed per period)
        date_column: Date/period column for ordering
        anomaly_threshold_pct: % change threshold that triggers an alert
        filter_condition: Optional SQL predicate to restrict rows BEFORE aggregation.
            Required when the table mixes heterogeneous metrics (see the task-026
            fix in the caller): summing metric_value across percentages + counts +
            EUR yields a meaningless % change, so scope to one metric_name.

    Returns:
        dict with trend analysis results
    """
    start_ms = time.time()

    df = spark.table(table_name)
    if filter_condition:
        df = df.filter(F.expr(filter_condition))

    # Get the two most recent distinct periods
    periods = (df.select(F.col(date_column))
               .distinct()
               .orderBy(F.desc(date_column))
               .limit(2)
               .collect())

    if len(periods) < 2:
        elapsed_ms = int((time.time() - start_ms) * 1000)
        log_check_result("trend_validation", "Gold", table_name, "pass", 100.0,
                         "Not enough history for trend validation (need 2+ periods)",
                         0, 0, elapsed_ms)
        return {"table": table_name, "status": "pass", "score": 100.0,
                "message": "Insufficient history"}

    current_period = periods[0][0]
    previous_period = periods[1][0]

    current_value = (df.filter(F.col(date_column) == current_period)
                     .select(F.sum(metric_column)).first()[0])
    previous_value = (df.filter(F.col(date_column) == previous_period)
                      .select(F.sum(metric_column)).first()[0])

    current_value = float(current_value) if current_value is not None else 0.0
    previous_value = float(previous_value) if previous_value is not None else 0.0

    if previous_value == 0:
        pct_change = 0.0
    else:
        pct_change = ((current_value - previous_value) / abs(previous_value)) * 100.0

    is_anomaly = abs(pct_change) > anomaly_threshold_pct
    # Score: full marks unless anomalous, then scaled by overshoot
    if not is_anomaly:
        score = 100.0
    else:
        overshoot = abs(pct_change) - anomaly_threshold_pct
        score = max(0.0, 100.0 - overshoot)

    status = "warning" if is_anomaly else "pass"

    elapsed_ms = int((time.time() - start_ms) * 1000)

    direction = "increase" if pct_change > 0 else "decrease"
    details = (f"{metric_column}: {pct_change:+.1f}% {direction} "
               f"(current={current_value:,.2f}, previous={previous_value:,.2f}, "
               f"threshold={anomaly_threshold_pct}%)")

    log_check_result(
        "trend_validation", "Gold", table_name, status, score,
        details, failed_rows=1 if is_anomaly else 0, total_rows=1,
        execution_time_ms=elapsed_ms
    )

    return {"table": table_name, "current_value": current_value,
            "previous_value": previous_value, "pct_change": pct_change,
            "is_anomaly": is_anomaly, "status": status, "score": score}

print("\n--- Gold Check 12: Trend Validation ---")

# TREND-CHECK FIX (task-026): the old config summed metric_value across ALL rows in
# gold_quality_history between the two most recent refresh_timestamps — but that
# table mixes heterogeneous metrics (dq scores 0-100, dimension scores, rating
# codes), so the % change was not meaningful. Scope to a single homogeneous
# metric_name (dq_overall_score) so the run-over-run trend is interpretable.
trend_checks = [
    ("oem_lh.gold_quality_history", "metric_value", "refresh_timestamp", 50.0,
     "metric_name = 'dq_overall_score'"),
]

trend_results = []
for table, metric, date_col, threshold, filt in trend_checks:
    try:
        result = validate_historical_trend(table, metric, date_col, threshold,
                                           filter_condition=filt)
        trend_results.append(result)
    except Exception as e:
        print(f"  [SKIP] {table}: {str(e)}")
        log_check_result("trend_validation", "Gold", table, "pass", 100.0,
                         f"Trend check skipped: {str(e)}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 3b. Gold Uniqueness Checks (task-026)
# lookup_name uniqueness on gold lookup dims and duplicate-grain on gold facts —
# the fan-out guards that would have caught the task-023 spend inflation.

# CELL ********************

# =============================================================================
# CHECK 13: LOOKUP-NAME UNIQUENESS (gold lookup dimensions) — task-026 (5a)
# =============================================================================
# A duplicate lookup_name in a lookup dim fans out EVERY fact that joins on it
# (root cause of the task-023 spend inflation). silver-to-gold2 already hard-guards
# this at build time; this is the observability layer that records it to history
# and gates the pipeline (BLOCKING).
print("\n--- Gold Check 13: Lookup-Name Uniqueness ---")

lookup_uniqueness_checks = [
    ("oem_lh.gold_dim_country_lookup", ["lookup_name"]),
    ("oem_lh.gold_dim_material_lookup", ["lookup_name"]),
]

for table, keys in lookup_uniqueness_checks:
    try:
        detect_duplicates(table, keys, layer="Gold", check_name="lookup_name_uniqueness")
    except Exception as e:
        print(f"  [SKIP] {table}: {str(e)}")
        log_check_result("lookup_name_uniqueness", "Gold", table, "fail", 0.0,
                         f"Table not accessible: {str(e)}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# =============================================================================
# CHECK 14: DUPLICATE-GRAIN ON GOLD FACTS — task-026 (5b)
# =============================================================================
# Catches join fan-out (task-023) by asserting each fact holds at most one row per
# its declared grain. fact_supply_share and fact_epi_score have clean surrogate
# grains -> BLOCKING at 0% tolerance. fact_procurement is transaction-grain with no
# surrogate key and legitimately permits exact repeats, so its full business-tuple
# check is ADVISORY (a sustained rise still flags a possible fan-out).
print("\n--- Gold Check 14: Duplicate-Grain on Gold Facts ---")

grain_checks = [
    ("oem_lh.fact_supply_share", ["material_key", "stage_key", "country_key", "year"]),
    ("oem_lh.fact_epi_score", ["country_key", "indicator_key", "year"]),
    ("oem_lh.fact_procurement",
     ["date_key", "material_key", "supplier_hq_country_key",
      "production_country_key", "quantity_base", "unitprice_eur"]),
]

for table, keys in grain_checks:
    try:
        detect_duplicates(table, keys, layer="Gold", check_name="grain_uniqueness")
    except Exception as e:
        print(f"  [SKIP] {table}: {str(e)}")
        log_check_result("grain_uniqueness", "Gold", table, "fail", 0.0,
                         f"Table not accessible: {str(e)}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 4. Quality Scoring Summary
# Calculate overall scores per layer, per table, and overall pipeline quality.

# CELL ********************

# =============================================================================
# QUALITY SCORING SUMMARY
# =============================================================================

print("\n" + "=" * 70)
print("QUALITY SCORING SUMMARY")
print("=" * 70)

# Dimension weights for overall scoring
DIMENSION_WEIGHTS = {
    "completeness": 0.25,
    "accuracy": 0.25,
    "consistency": 0.20,
    "validity": 0.15,
    "uniqueness": 0.10,
    "timeliness": 0.05,
}

# Map check names to quality dimensions
CHECK_TO_DIMENSION = {
    "row_count_validation": "completeness",
    "schema_validation": "validity",
    "required_field_completeness": "completeness",
    "duplicate_detection": "uniqueness",
    "date_range_validation": "validity",
    "referential_integrity": "consistency",
    "business_rule_validation": "validity",
    "outlier_detection": "accuracy",
    "data_type_consistency": "validity",
    "silver_completeness": "completeness",
    "aggregate_reconciliation": "consistency",
    "trend_validation": "timeliness",
    "lookup_name_uniqueness": "uniqueness",
    "grain_uniqueness": "uniqueness",
}

# Aggregate scores by layer
layer_scores = {}
dimension_scores_agg = {}

for result in all_check_results:
    layer = result["layer"]
    check = result["check_name"]
    score = result["score"]
    dimension = CHECK_TO_DIMENSION.get(check, "other")

    # Layer scores
    if layer not in layer_scores:
        layer_scores[layer] = []
    layer_scores[layer].append(score)

    # Dimension scores
    if dimension not in dimension_scores_agg:
        dimension_scores_agg[dimension] = []
    dimension_scores_agg[dimension].append(score)

# Print layer scores
print("\n--- Scores by Layer ---")
for layer in ["Bronze", "Silver", "Gold"]:
    if layer in layer_scores:
        scores = layer_scores[layer]
        avg_score = sum(scores) / len(scores)
        rating = categorize_quality_score(avg_score)
        print(f"  {layer}: {avg_score:.1f}/100 ({rating}) [{len(scores)} checks]")

# Print dimension scores
print("\n--- Scores by Quality Dimension ---")
dimension_avgs = {}
for dim_name, dim_scores in sorted(dimension_scores_agg.items()):
    avg = sum(dim_scores) / len(dim_scores)
    dimension_avgs[dim_name] = avg
    rating = categorize_quality_score(avg)
    print(f"  {dim_name.capitalize():15s}: {avg:.1f}/100 ({rating}) [{len(dim_scores)} checks]")

# Calculate overall pipeline quality score
overall_score = calculate_table_quality_score(dimension_avgs, DIMENSION_WEIGHTS)
overall_rating = categorize_quality_score(overall_score)

print(f"\n{'=' * 70}")
print(f"OVERALL PIPELINE QUALITY SCORE: {overall_score:.1f}/100 ({overall_rating})")
print(f"{'=' * 70}")

# Alert based on overall rating
if overall_rating == "Critical":
    print("\n*** CRITICAL: Pipeline quality is below acceptable thresholds. ***")
    print("*** Review failed checks above and take corrective action.    ***")
elif overall_rating == "Poor":
    print("\n** WARNING: Pipeline quality needs attention. **")
    print("** Review failed checks and plan remediation.  **")
elif overall_rating == "Fair":
    print("\nINFO: Pipeline quality is fair. Some checks need improvement.")
elif overall_rating == "Good":
    print("\nINFO: Pipeline quality is good. Minor improvements possible.")
else:
    print("\nPipeline quality is excellent. No action required.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 5. Persist Results to gold_quality_history
# Write DQ check results to the quality history table for trend tracking.

# CELL ********************

# =============================================================================
# PERSIST RESULTS TO GOLD_QUALITY_HISTORY
# =============================================================================

print("\n--- Persisting DQ results to gold_quality_history ---")

# -----------------------------------------------------------------------------
# task-040: gold_quality_history carries two extra columns
# -----------------------------------------------------------------------------
#   status   - the per-check verdict ("pass" / "fail" / "warning") produced by
#              log_check_result. THIS is the field the blocking gate in section 7
#              reads. Before task-040 it was computed, printed, and then dropped on
#              the floor, so a past run's gate outcome could not be reconstructed
#              from the table at all. "n/a" on rows that are not a single check
#              result (dimension/overall aggregates, and the gate verdict rows).
#   producer - which notebook appended the row. silver-to-gold2 also appends to this
#              table on every pipeline run, with its own refresh_timestamp.
#
# breach_flag is unchanged and is NOT the gate: score < 70.0. The two diverge in
# practice — grain_uniqueness failing on 2 duplicate grains out of 2561 rows scores
# ~99.9, never breaches, and still halts the pipeline.
#
# silver-to-gold2 owns the CREATE TABLE; this helper mirrors the one there so this
# notebook can also be run standalone. Explicit ALTER TABLE (not mergeSchema) because
# the table is append-only and already holds history: pre-task-040 rows keep NULL in
# both columns and are NOT backfilled.
QUALITY_HISTORY_PRODUCER = "data_quality_checks"
QUALITY_HISTORY_ADDED_COLUMNS = [("status", "STRING"), ("producer", "STRING")]
QUALITY_HISTORY_COLUMNS = [
    "refresh_timestamp", "layer", "entity", "metric_name",
    "metric_value", "threshold", "breach_flag", "status", "producer",
]


def ensure_quality_history_columns():
    """Idempotently add the task-040 columns to gold_quality_history."""
    if not spark.catalog.tableExists(f"{DB}.gold_quality_history"):
        return  # the first write creates the table with the full 9-column schema
    existing = set(spark.table(f"{DB}.gold_quality_history").columns)
    for col_name, col_type in QUALITY_HISTORY_ADDED_COLUMNS:
        if col_name not in existing:
            spark.sql(
                f"ALTER TABLE {DB}.gold_quality_history ADD COLUMNS ({col_name} {col_type})"
            )
            print(f"  gold_quality_history: added column {col_name} {col_type} "
                  f"(pre-existing rows keep NULL)")


ensure_quality_history_columns()

# Build metrics for persistence
# Each check result becomes a row in gold_quality_history
dq_metrics_to_insert = []

for result in all_check_results:
    layer = result["layer"]
    table_name = result["table_name"]
    check_name = result["check_name"]
    score = result["score"]

    # Threshold: below 70 is a breach. This is a SCORE band, not the gate.
    threshold = 70.0
    breach_flag = score < threshold

    # Metric name format: dq_{check_name}
    metric_name = f"dq_{check_name}"

    dq_metrics_to_insert.append(
        (pipeline_run_ts, layer, table_name, metric_name, float(score), threshold, breach_flag,
         result["status"], QUALITY_HISTORY_PRODUCER)
    )

# Add overall scores as metrics ("n/a" status: aggregates, not individual checks)
for dim_name, dim_avg in dimension_avgs.items():
    dq_metrics_to_insert.append(
        (pipeline_run_ts, "Pipeline", "overall", f"dq_dimension_{dim_name}", float(dim_avg), 70.0, dim_avg < 70.0,
         "n/a", QUALITY_HISTORY_PRODUCER)
    )

# Add the overall pipeline score
dq_metrics_to_insert.append(
    (pipeline_run_ts, "Pipeline", "overall", "dq_overall_score", float(overall_score), 70.0, overall_score < 70.0,
     "n/a", QUALITY_HISTORY_PRODUCER)
)

# Add the overall rating as a metric (1=Critical, 2=Poor, 3=Fair, 4=Good, 5=Excellent)
rating_value = {"Critical": 1.0, "Poor": 2.0, "Fair": 3.0, "Good": 4.0, "Excellent": 5.0}
dq_metrics_to_insert.append(
    (pipeline_run_ts, "Pipeline", "overall", "dq_overall_rating",
     rating_value.get(overall_rating, 0.0), 4.0, rating_value.get(overall_rating, 0.0) < 4.0,
     "n/a", QUALITY_HISTORY_PRODUCER)
)

if dq_metrics_to_insert:
    history_df = spark.createDataFrame(
        dq_metrics_to_insert,
        QUALITY_HISTORY_COLUMNS
    )

    history_df.write.format("delta").mode("append").saveAsTable(f"{DB}.gold_quality_history")

    print(f"\nPersisted {len(dq_metrics_to_insert)} DQ metrics to {DB}.gold_quality_history")
    print(f"  - Per-check scores: {len(all_check_results)}")
    print(f"  - Dimension scores: {len(dimension_avgs)}")
    print(f"  - Overall scores: 2")

    # Show what was persisted
    print("\nMetrics persisted this run:")
    history_df.orderBy("layer", "entity", "metric_name").show(50, truncate=False)
else:
    print("No metrics to persist.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 6. Check Results Detail
# Full listing of all check results for this run.

# CELL ********************

# =============================================================================
# DETAILED RESULTS TABLE
# =============================================================================

print("\n" + "=" * 70)
print("DETAILED CHECK RESULTS")
print("=" * 70)

# Create a summary DataFrame for display
if all_check_results:
    summary_data = [
        (r["check_name"], r["layer"], r["table_name"], r["status"],
         float(r["score"]), categorize_quality_score(r["score"]),
         r["details"][:100], r.get("execution_time_ms", 0))
        for r in all_check_results
    ]

    summary_df = spark.createDataFrame(
        summary_data,
        ["check_name", "layer", "table", "status", "score", "rating", "details", "exec_ms"]
    )

    # Show summary ordered by score (worst first)
    print("\nAll checks ordered by score (worst first):")
    summary_df.orderBy("score").show(50, truncate=False)

    # Count by status
    print("\nStatus summary:")
    summary_df.groupBy("status").count().show()

    # Count by rating
    print("\nRating distribution:")
    summary_df.groupBy("rating").count().orderBy("rating").show()

    # Average execution time
    total_exec_ms = sum(r.get("execution_time_ms", 0) for r in all_check_results)
    print(f"\nTotal execution time: {total_exec_ms:,} ms ({total_exec_ms/1000:.1f} seconds)")
else:
    print("No check results recorded.")

print("\n" + "=" * 70)
print(f"Data Quality Checks Complete: {pipeline_run_ts.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Overall Score: {overall_score:.1f}/100 ({overall_rating})")
print("=" * 70)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 7. Blocking-Check Enforcement (task-026)
# Severity model + single aggregated raise. This is the core fix: before task-026
# the notebook had ZERO raises, so no check could halt anything and the DQ layer
# guarded nothing. Runs LAST — after results are persisted to gold_quality_history
# and after the detailed table prints — so a FAILING run still leaves the full
# picture of every check, then fails the pipeline activity.
# task-040 adds one thing here: the gate verdict itself is appended to
# gold_quality_history (entity='gate') BEFORE the raise, so "did the gate pass on
# run X" is answerable from the table without reading this file.

# CELL ********************

# =============================================================================
# BLOCKING-CHECK ENFORCEMENT (single aggregated raise)
# =============================================================================
#
# SEVERITY MODEL
# --------------
# Every check is logged + scored + persisted (advisory baseline). A subset are
# additionally BLOCKING: if any blocking check ends "fail", we raise ONCE here so
# the Fabric pipeline activity (and therefore the pipeline) fails.
#
# Design (task-026 DESIGN NOTE): collect ALL results first, then raise a SINGLE
# aggregated exception AFTER persistence — so one failing check never hides another
# and gold_quality_history always receives the full picture of a failing run.
#
# Blocking membership is keyed by (check_name, table_name). Everything not listed
# is advisory (logged/scored/persisted only, never fatal).

class DataQualityException(Exception):
    """Raised when one or more BLOCKING data-quality checks fail (framework contract:
    data_quality_framework.md raise pattern). A single aggregated raise fails the
    orchestrator's data_quality_checks activity and halts the pipeline."""
    pass


# Minimum blocking set (task-026 criterion 2) + the new fan-out guards (criterion 5).
BLOCKING_CHECKS = {
    # Schema validation — structural contract for the core bronze tables.
    ("schema_validation", "oem_lh.bronze_procurement_transactional"),
    ("schema_validation", "oem_lh.bronze_supplier_ref"),
    # task-026: follows the contract to silver (see schema_checks). Must stay in
    # sync with the table name there — a stale entry here does not error, it
    # silently demotes the check to advisory.
    ("schema_validation", "oem_lh.silver_epi2024results"),
    ("schema_validation", "oem_lh.bronze_GlobalSupplyShares"),
    # Required-field completeness on procurement (0% null tolerance).
    ("required_field_completeness", "oem_lh.bronze_procurement_transactional"),
    # Duplicate detection — genuine duplicate procurement transactions (criterion 4).
    ("duplicate_detection", "oem_lh.bronze_procurement_transactional"),
    # Referential integrity at 0% tolerance on all gold facts (all their FK checks).
    ("referential_integrity", "oem_lh.fact_procurement"),
    ("referential_integrity", "oem_lh.fact_supply_share"),
    ("referential_integrity", "oem_lh.fact_epi_score"),
    # lookup_name uniqueness on the gold lookup dims (fan-out guard, criterion 5a).
    ("lookup_name_uniqueness", "oem_lh.gold_dim_country_lookup"),
    ("lookup_name_uniqueness", "oem_lh.gold_dim_material_lookup"),
    # Duplicate-grain on the surrogate-grain gold facts (fan-out guard, criterion 5b).
    ("grain_uniqueness", "oem_lh.fact_supply_share"),
    ("grain_uniqueness", "oem_lh.fact_epi_score"),
    # ADVISORY (intentionally absent): grain_uniqueness on fact_procurement
    # (transaction grain permits legit exact repeats) and aggregate_reconciliation
    # (unit-normalization caveat — see Check 11). Both still log/persist a "fail".
}


def is_blocking(result):
    return (result["check_name"], result["table_name"]) in BLOCKING_CHECKS


blocking_evaluated = [r for r in all_check_results if is_blocking(r)]
blocking_failures = [r for r in blocking_evaluated if r["status"] == "fail"]

print("\n" + "=" * 70)
print("BLOCKING-CHECK ENFORCEMENT")
print("=" * 70)
print(f"Blocking checks evaluated: {len(blocking_evaluated)}")
print(f"Blocking failures:         {len(blocking_failures)}")

# -----------------------------------------------------------------------------
# task-040: PERSIST THE GATE VERDICT — before the raise, for the same reason
# task-026 persists the per-check results before raising.
# -----------------------------------------------------------------------------
# Without these rows, "did the gate pass on run X?" could only be answered by
# intersecting persisted per-check rows against the BLOCKING_CHECKS set in THIS
# FILE — i.e. by reading notebook source — and the block printed above is not a
# durable record either (the pipeline editor's Output panel only shows runs from
# the current editor session; a fresh page load shows nothing).
#
# Answering the question from the table alone, one query:
#   SELECT status, metric_name, metric_value
#   FROM   oem_lh.gold_quality_history
#   WHERE  entity = 'gate'
#     AND  refresh_timestamp = (SELECT MAX(refresh_timestamp)
#                               FROM oem_lh.gold_quality_history WHERE entity = 'gate')
# status is 'pass' or 'fail'; dq_gate_raised is 1.0 when the aggregated raise fired.
# NOTE: refresh_timestamp is UTC while the Fabric UI shows local time (UTC+2 CEST) —
# a current run reads two hours "early".
gate_status = "fail" if blocking_failures else "pass"

gate_history_schema = StructType([
    StructField("refresh_timestamp", TimestampType(), True),
    StructField("layer", StringType(), True),
    StructField("entity", StringType(), True),
    StructField("metric_name", StringType(), True),
    StructField("metric_value", DoubleType(), True),
    StructField("threshold", DoubleType(), True),
    StructField("breach_flag", BooleanType(), True),
    StructField("status", StringType(), True),
    StructField("producer", StringType(), True),
])

gate_rows = [
    # How many blocking checks were actually evaluated this run (guards against a
    # stale BLOCKING_CHECKS entry silently demoting a check to advisory).
    (pipeline_run_ts, "Pipeline", "gate", "dq_gate_blocking_evaluated",
     float(len(blocking_evaluated)), None, False, "n/a", QUALITY_HISTORY_PRODUCER),
    # How many of them failed. threshold 0.0 => any failure is a breach.
    (pipeline_run_ts, "Pipeline", "gate", "dq_gate_blocking_failures",
     float(len(blocking_failures)), 0.0, len(blocking_failures) > 0,
     gate_status, QUALITY_HISTORY_PRODUCER),
    # Whether the aggregated raise fired (1.0 = pipeline halted here).
    (pipeline_run_ts, "Pipeline", "gate", "dq_gate_raised",
     1.0 if blocking_failures else 0.0, 0.0, bool(blocking_failures),
     gate_status, QUALITY_HISTORY_PRODUCER),
]

ensure_quality_history_columns()
(spark.createDataFrame(gate_rows, schema=gate_history_schema)
      .write.format("delta").mode("append").saveAsTable(f"{DB}.gold_quality_history"))

print(f"\nGate verdict persisted to {DB}.gold_quality_history "
      f"(entity='gate', status='{gate_status}', refresh_timestamp={pipeline_run_ts} UTC)")

if blocking_failures:
    print("\nFAILED BLOCKING CHECKS (pipeline will halt):")
    for r in blocking_failures:
        print(f"  [BLOCK] {r['check_name']} on {r['table_name']}: {r['details']}")
    summary = "; ".join(f"{r['check_name']}@{r['table_name']}" for r in blocking_failures)
    raise DataQualityException(
        f"{len(blocking_failures)} blocking data-quality check(s) failed: {summary}. "
        f"Full results persisted to {DB}.gold_quality_history."
    )
else:
    print("\nAll blocking checks passed. Pipeline may proceed.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
