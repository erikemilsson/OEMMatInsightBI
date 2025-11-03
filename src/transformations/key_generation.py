"""
Surrogate Key Generation Functions

This module provides functions for generating deterministic surrogate keys
using xxhash64 hashing algorithm. These keys are used throughout the data
pipeline to create stable, reproducible dimension and fact table keys.
"""

from pyspark.sql import functions as F
from typing import List, Union


def stable_key(*cols: Union[str, List[str]]) -> F.Column:
    """
    Generate deterministic 64-bit surrogate key using xxhash64.

    This function creates stable, reproducible surrogate keys by hashing
    business key columns. The same input values will always produce the
    same key, enabling incremental loads and idempotent pipeline runs.

    Args:
        *cols: Variable number of column names (strings) or a list of column names
               to be hashed together. Columns are coalesced with '∅' for nulls.

    Returns:
        pyspark.sql.Column: A bigint column containing the generated surrogate key.
                           Keys are always positive (uses absolute value).

    Algorithm:
        1. For each column, cast to string and coalesce nulls to '∅'
        2. Compute xxhash64 over all columns
        3. Take absolute value to ensure positive keys
        4. Cast to bigint

    Examples:
        >>> # Single column key
        >>> df.withColumn("country_key", stable_key("iso3"))

        >>> # Multi-column composite key
        >>> df.withColumn("material_key", stable_key("material_name", "commodity_group"))

        >>> # Using list of columns
        >>> business_keys = ["date", "material", "supplier"]
        >>> df.withColumn("fact_key", stable_key(*business_keys))

    Notes:
        - Null values are explicitly handled with '∅' character to ensure
          consistent hashing behavior
        - xxhash64 is a non-cryptographic hash optimized for speed
        - Keys are reproducible across pipeline runs
        - Collision rate is extremely low for typical data volumes
        - Keys are NOT sequential - no ordering relationship to data
    """
    # Handle both positional args and list of columns
    if len(cols) == 1 and isinstance(cols[0], list):
        col_list = cols[0]
    else:
        col_list = list(cols)

    # Validate input
    if not col_list:
        raise ValueError("At least one column name must be provided")

    # Generate hash over all columns
    hash_cols = [
        F.coalesce(F.col(c).cast("string"), F.lit("∅"))
        for c in col_list
    ]

    return F.abs(F.xxhash64(*hash_cols)).cast("bigint")


def generate_country_key(iso3_col: str, name_col: str) -> F.Column:
    """
    Generate surrogate key for country dimension using ISO3 code.

    This is a specialized wrapper around stable_key() that prioritizes
    ISO3 code for country key generation. ISO3 is the preferred business
    key for countries as it's standardized and stable.

    Args:
        iso3_col: Column name containing ISO3 country code (e.g., 'USA', 'CHN')
        name_col: Column name containing country name (fallback if ISO3 is null)

    Returns:
        pyspark.sql.Column: Country surrogate key (bigint)

    Examples:
        >>> df.withColumn("country_key", generate_country_key("iso3", "country_name"))

    Notes:
        - Prefers ISO3 code as it's more stable than country names
        - Falls back to country name if ISO3 is not available
        - Same ISO3 code always produces the same key
    """
    return stable_key(iso3_col, name_col)


def generate_material_key(material_name_col: str) -> F.Column:
    """
    Generate surrogate key for material dimension.

    Args:
        material_name_col: Column name containing standardized material name

    Returns:
        pyspark.sql.Column: Material surrogate key (bigint)

    Examples:
        >>> df.withColumn("material_key", generate_material_key("material_name_std"))

    Notes:
        - Uses standardized material name (after alias resolution)
        - Distinct materials get distinct keys
        - Spelling variants should be resolved before key generation
    """
    return stable_key(material_name_col)


def generate_date_key(date_col: str) -> F.Column:
    """
    Generate integer date key in YYYYMMDD format.

    Date keys are stored as integers for efficient storage and filtering.
    Format: YYYYMMDD (e.g., 20240115 for January 15, 2024)

    Args:
        date_col: Column name containing date value (DateType or TimestampType)

    Returns:
        pyspark.sql.Column: Date key as integer in YYYYMMDD format

    Examples:
        >>> df.withColumn("date_key", generate_date_key("order_date"))
        >>> # 2024-01-15 -> 20240115

    Notes:
        - Uses YYYYMMDD format (not YYMMDD) to avoid Y2K-style issues
        - Integer type enables efficient range filtering
        - Compatible with date slicers in Power BI
    """
    return F.date_format(F.col(date_col), "yyyyMMdd").cast("int")
