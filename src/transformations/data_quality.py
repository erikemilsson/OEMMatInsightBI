"""
Data Quality Check Functions

This module provides functions for validating data quality during transformations,
including unmapped value detection, null checks, and quality scoring.
"""

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
