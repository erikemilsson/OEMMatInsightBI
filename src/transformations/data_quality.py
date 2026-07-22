"""
Data Quality Check Functions

This module provides functions for validating data quality during transformations,
including unmapped value detection, null checks, and quality scoring.

REFERENCE IMPLEMENTATION — NOT IMPORTED BY THE NOTEBOOKS (task-032)
------------------------------------------------------------------
Same contract as `key_generation.py`: the Fabric notebooks define their quality
checks inline and do not import this package. Option (ii) was chosen — this module
is the documented REFERENCE implementation, and the duplication is guarded by
parity tests rather than by convention. See `key_generation.py`'s module docstring
for why option (i) (notebooks importing `src/`) was rejected.

Production counterparts, per function:
  - check_unmapped            -> fabric/silver-to-gold2.Notebook (inline, ~L95)
  - categorize_quality        -> fabric/silver-to-gold2.Notebook `quality_category`
                                 CASE ladder (~L1230); thresholds match exactly
  - count_out_of_range_dates  -> fabric/data_quality_checks.Notebook
                                 `validate_date_range`
  - find_type_mismatches      -> fabric/data_quality_checks.Notebook
                                 `validate_data_type_consistency`
  - count_incomplete_rows     -> fabric/data_quality_checks.Notebook
                                 `validate_silver_completeness`
  - check_duplicates          -> NO exact counterpart; see its docstring for the
                                 deliberate semantic difference vs the notebook's
                                 `detect_duplicates`
  - check_nulls, validate_range, find_unreachable_initcap_keys -> local helpers
    with no single inline twin.

**If you change a function here, change the notebook to match (or vice versa).**
"""

from datetime import date
from pyspark.sql import DataFrame, SparkSession, functions as F
from typing import List, Optional


def check_unmapped(
    df: DataFrame,
    join_col: str,
    name: str,
    fail: bool = False,
    log_unmapped: bool = True,
    fail_on_unmapped: bool = False
) -> int:
    """
    Check for unmapped values after a join operation.

    This function identifies records where a join failed to find a matching key,
    indicating missing reference data or data quality issues.

    Args:
        df: DataFrame after join operation
        join_col: Name of the joined column to check for nulls (e.g., "country_key")
        name: Descriptive name for logging (e.g., "country", "material")
        fail: Whether to raise error if unmapped records found
        log_unmapped: Whether to print unmapped values to console
        fail_on_unmapped: Global flag to control failure behavior

    Returns:
        int: Count of unmapped records

    Raises:
        ValueError: If fail=True and unmapped records are found

    Examples:
        >>> df_with_keys = df.join(country_lookup, "country_name", "left")
        >>> unmapped_count = check_unmapped(df_with_keys, "country_key", "country")
        >>> # ⚠️  Found 5 unmapped records for country

    Notes:
        - Designed for left joins where null in join_col indicates no match
        - Prints sample of unmapped values for troubleshooting
        - Can optionally fail pipeline to enforce data quality
        - Mirrors the notebook's inline version, whose module-level LOG_UNMAPPED
          and FAIL_ON_UNMAPPED globals map to the `log_unmapped` and
          `fail_on_unmapped` parameters here (parameterised for testability).
    """
    unmapped = df.filter(F.col(join_col).isNull())
    count = unmapped.count()

    if count > 0:
        print(f"⚠️  Found {count:,} unmapped records for {name}")

        if log_unmapped:
            # Show distinct unmapped values — same display as the notebook's
            # inline check_unmapped. (Was a groupBy(join_col).count() summary,
            # which drifted from production for no gain: join_col is null for
            # every filtered row, so the "summary" was always a single row.)
            unmapped.select(join_col).distinct().show(20, truncate=False)

        if fail and fail_on_unmapped:
            raise ValueError(f"Pipeline failed: {count} unmapped {name} records")

    return count


def check_nulls(
    df: DataFrame,
    column: str,
    table_name: str,
    fail_on_nulls: bool = False
) -> int:
    """
    Check for null values in a required column.

    Args:
        df: DataFrame to check
        column: Column name to check for nulls
        table_name: Table name for error messages
        fail_on_nulls: Whether to raise error if nulls found

    Returns:
        int: Count of null values

    Raises:
        ValueError: If fail_on_nulls=True and nulls are found

    Examples:
        >>> null_count = check_nulls(df, "spend_eur", "fact_procurement")
    """
    null_count = df.filter(F.col(column).isNull()).count()

    if null_count > 0:
        print(f"⚠️  Found {null_count:,} null values in {table_name}.{column}")

        if fail_on_nulls:
            raise ValueError(f"Pipeline failed: {null_count} nulls in {table_name}.{column}")

    return null_count


def check_duplicates(
    df: DataFrame,
    key_columns: list,
    table_name: str,
    fail_on_duplicates: bool = False
) -> int:
    """
    Check for duplicate records based on key columns.

    SEMANTICS — deliberately different from the notebook's `detect_duplicates`
    (fabric/data_quality_checks.Notebook). This function returns the number of
    DISTINCT KEY COMBINATIONS occurring more than once; the notebook returns the
    number of EXCESS ROWS (`total_rows - distinct_key_rows`). For three identical
    rows this function returns 1 and the notebook returns 2. Both are valid
    metrics; they are not interchangeable, so do not "unify" one into the other
    without also updating the gold_quality_check_results interpretation. Pinned by
    tests/test_data_quality.py::test_check_duplicates_semantics_differ_from_notebook.

    Args:
        df: DataFrame to check
        key_columns: List of column names that form the business key
        table_name: Table name for error messages
        fail_on_duplicates: Whether to raise error if duplicates found

    Returns:
        int: Count of key combinations that occur more than once

    Raises:
        ValueError: If fail_on_duplicates=True and duplicates are found

    Examples:
        >>> dup_count = check_duplicates(
        ...     df,
        ...     ["date_key", "material_key", "supplier_key"],
        ...     "fact_procurement"
        ... )
    """
    duplicates = (df
                 .groupBy(*key_columns)
                 .count()
                 .filter(F.col("count") > 1))

    dup_count = duplicates.count()

    if dup_count > 0:
        print(f"⚠️  Found {dup_count:,} duplicate keys in {table_name}")
        duplicates.show(10, truncate=False)

        if fail_on_duplicates:
            raise ValueError(f"Pipeline failed: {dup_count} duplicates in {table_name}")

    return dup_count


def validate_range(
    df: DataFrame,
    column: str,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    table_name: str = ""
) -> int:
    """
    Validate that numeric column values are within expected range.

    Args:
        df: DataFrame to check
        column: Column name to validate
        min_value: Minimum acceptable value (None = no minimum)
        max_value: Maximum acceptable value (None = no maximum)
        table_name: Table name for error messages

    Returns:
        int: Count of out-of-range values

    Examples:
        >>> # Check EPI scores are between 0 and 100
        >>> invalid_count = validate_range(df, "score", 0.0, 100.0, "fact_epi_score")
    """
    if min_value is not None and max_value is not None:
        out_of_range = df.filter(
            (F.col(column) < min_value) | (F.col(column) > max_value)
        )
    elif min_value is not None:
        out_of_range = df.filter(F.col(column) < min_value)
    elif max_value is not None:
        out_of_range = df.filter(F.col(column) > max_value)
    else:
        return 0

    count = out_of_range.count()

    if count > 0:
        print(f"⚠️  Found {count:,} out-of-range values in {table_name}.{column}")
        print(f"    Expected range: [{min_value}, {max_value}]")
        out_of_range.select(column).describe().show()

    return count


def categorize_quality(confidence: float) -> str:
    """
    Categorize data quality based on confidence score.

    Confidence scores (0-1) are mapped to quality categories:
    - High: >= 0.90 (Tier 1 matches, exact ISO3 codes)
    - Medium: >= 0.70 (Tier 2 matches, fuzzy matches)
    - Low: >= 0.50 (Tier 3 matches, weak matches)
    - Unmapped: < 0.50 (No match or very low confidence)

    Args:
        confidence: Confidence score between 0.0 and 1.0

    Returns:
        str: Quality category ('High', 'Medium', 'Low', or 'Unmapped')

    Examples:
        >>> categorize_quality(1.0)   # 'High'
        >>> categorize_quality(0.85)  # 'Medium'
        >>> categorize_quality(0.60)  # 'Low'
        >>> categorize_quality(0.30)  # 'Unmapped'
    """
    if confidence >= 0.90:
        return "High"
    elif confidence >= 0.70:
        return "Medium"
    elif confidence >= 0.50:
        return "Low"
    else:
        return "Unmapped"


def count_out_of_range_dates(
    df: DataFrame,
    date_column: str,
    min_date: date,
    max_date: date,
    table_name: str = ""
) -> int:
    """
    Count rows whose date falls outside an expected [min_date, max_date] window.

    Detects two classes of date-quality problems:
    - Future dates: dates after `max_date` (typically current_date()).
    - Implausibly old / out-of-range dates: dates before `min_date` (a project
      floor such as the earliest plausible procurement date).

    Rows with a NULL date are NOT counted here (null handling is the concern of
    the completeness check, not the range check) so the two checks stay
    orthogonal and neither double-flags the same row.

    Args:
        df: DataFrame to check.
        date_column: Name of the date/timestamp column to validate.
        min_date: Earliest acceptable date (inclusive).
        max_date: Latest acceptable date (inclusive).
        table_name: Table name for log messages.

    Returns:
        int: Count of rows with a non-null date outside [min_date, max_date].

    Examples:
        >>> # Flag procurement dates in the future or before 2015
        >>> bad = count_out_of_range_dates(df, "Date", date(2015, 1, 1), date.today())
    """
    out_of_range = df.filter(
        F.col(date_column).isNotNull()
        & (
            (F.col(date_column) < F.lit(min_date))
            | (F.col(date_column) > F.lit(max_date))
        )
    )

    count = out_of_range.count()

    if count > 0:
        print(f"ℹ️  Found {count:,} out-of-range dates in {table_name}.{date_column}")
        print(f"    Expected window: [{min_date}, {max_date}]")

    return count


def find_type_mismatches(
    df: DataFrame,
    expected_types: dict
) -> list:
    """
    Compare a DataFrame's actual column types against an expected-type mapping.

    Used by the silver data-type-consistency check to confirm that bronze→silver
    casts produced the intended Spark types. Matching is case-insensitive on the
    column name and uses a substring match on the simple Spark type string
    (e.g. expected "double" matches actual "DoubleType()") so it tolerates the
    differing `str(dataType)` representations across PySpark versions.

    Columns present in `df` but absent from `expected_types` are ignored (extra
    columns are not a type-consistency failure). Columns named in `expected_types`
    but missing from `df` are reported as a mismatch.

    Args:
        df: DataFrame whose schema is inspected.
        expected_types: dict of {column_name: expected_type_substring}, e.g.
            {"quantity_base": "double", "date_key": "int"}.

    Returns:
        list[str]: Human-readable mismatch descriptions. Empty list = all conform.

    Examples:
        >>> find_type_mismatches(df, {"quantity": "double", "unit": "string"})
        []
    """
    actual_map = {
        field.name.lower(): str(field.dataType)
        for field in df.schema.fields
    }

    mismatches = []
    for col_name, expected_type in expected_types.items():
        col_lower = col_name.lower()
        if col_lower not in actual_map:
            mismatches.append(f"{col_name}: column missing")
        elif expected_type.lower() not in actual_map[col_lower].lower():
            mismatches.append(
                f"{col_name}: expected {expected_type}, got {actual_map[col_lower]}"
            )

    return mismatches


def count_incomplete_rows(
    df: DataFrame,
    required_columns: list
) -> int:
    """
    Count rows where ANY of the given required columns is null.

    This is a row-level completeness measure (a row is incomplete if at least one
    required column is null), distinct from the bronze field-level null rate. It
    is the right shape for post-join completeness on silver tables, where a join
    miss leaves an otherwise-valid row with nulls in the joined-in columns.

    Args:
        df: DataFrame to check.
        required_columns: Columns that must all be non-null for a row to be complete.

    Returns:
        int: Count of rows missing at least one required column value.

    Examples:
        >>> # Rows where a supplier_ref join failed to populate HQ country
        >>> incomplete = count_incomplete_rows(df, ["headquarterscountry"])
    """
    if not required_columns:
        return 0

    condition = F.col(required_columns[0]).isNull()
    for col_name in required_columns[1:]:
        condition = condition | F.col(col_name).isNull()

    return df.filter(condition).count()


def find_unreachable_initcap_keys(
    spark: SparkSession,
    keys: List[str]
) -> List[str]:
    """
    Find mapping keys that an initcap-normalized input can never match.

    The gold notebook applies `F.initcap()` to material names BEFORE joining them
    against the alias table and the commodity-group map. Spark's `initcap`
    uppercases the first character of each whitespace-delimited word and
    LOWERCASES every other character — including letters after '(' or '-'. So a
    mapping key such as 'Steel (High-Tensile)' is dead on arrival: no
    initcap-normalized input can ever equal it, and the rows it was meant to
    classify fall through to Other/Unknown silently.

    This is the reachability guard for that class of bug: a key is reachable iff
    `initcap(key) == key`. Feeding it the mapping's key set turns "we believe
    these keys are matchable" into a failing test when they are not.

    Args:
        spark: Active SparkSession (evaluation uses Spark's own initcap, not a
            Python re-implementation, so the guard tracks real engine behavior).
        keys: Mapping keys to check (non-null strings — e.g. grp_map keys or the
            left-hand side of alias pairs).

    Returns:
        list[str]: The unreachable keys, in input order. Empty list = all keys
        are reachable from initcap-normalized input.

    Examples:
        >>> find_unreachable_initcap_keys(spark, ["Copper", "Steel (High-Tensile)"])
        ['Steel (High-Tensile)']

    Notes:
        - The fix for an unreachable key is either to restate it in
          initcap-canonical form or to make the join case-insensitive on both
          sides (see task-028).
        - Null keys are ignored (a null key cannot be matched by anything, which
          is a different defect).
    """
    if not keys:
        return []

    df = spark.createDataFrame([(k,) for k in keys], ["key"])

    unreachable = {
        row["key"]
        for row in (df
                    .filter(F.col("key").isNotNull())
                    .filter(F.col("key") != F.initcap(F.col("key")))
                    .select("key")
                    .distinct()
                    .collect())
    }

    # Preserve caller order (and any intentional duplicates) in the result.
    return [k for k in keys if k in unreachable]
