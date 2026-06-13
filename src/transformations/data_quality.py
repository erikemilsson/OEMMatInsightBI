"""
Data Quality Check Functions

This module provides functions for validating data quality during transformations,
including unmapped value detection, null checks, and quality scoring.
"""

from datetime import date
from pyspark.sql import DataFrame, functions as F
from typing import Optional


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
    """
    unmapped = df.filter(F.col(join_col).isNull())
    count = unmapped.count()

    if count > 0:
        print(f"⚠️  Found {count:,} unmapped records for {name}")

        if log_unmapped:
            # Show distinct unmapped values with counts
            unmapped_summary = (unmapped
                               .groupBy(join_col)
                               .count()
                               .orderBy(F.desc("count"))
                               .limit(20))
            unmapped_summary.show(truncate=False)

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

    Args:
        df: DataFrame to check
        key_columns: List of column names that form the business key
        table_name: Table name for error messages
        fail_on_duplicates: Whether to raise error if duplicates found

    Returns:
        int: Count of duplicate records

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
