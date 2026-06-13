"""
Unit tests for data quality check functions.

Tests functions that validate data quality during transformations,
including unmapped value detection and quality categorization.
"""

from datetime import date

import pytest
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, DoubleType, DateType
)

from src.transformations.data_quality import (
    check_unmapped,
    check_nulls,
    check_duplicates,
    validate_range,
    categorize_quality,
    count_out_of_range_dates,
    find_type_mismatches,
    count_incomplete_rows,
)


class TestCheckUnmapped:
    """Tests for check_unmapped() function."""

    @pytest.mark.unit
    def test_check_unmapped_no_issues(self, spark, sample_country_data):
        """Test check_unmapped with no unmapped records."""
        # All records have country keys (no nulls)
        df_with_keys = sample_country_data.withColumn("country_key", F.lit(1))

        unmapped_count = check_unmapped(
            df_with_keys,
            "country_key",
            "country",
            log_unmapped=False
        )

        assert unmapped_count == 0

    @pytest.mark.unit
    def test_check_unmapped_with_nulls(self, spark):
        """Test check_unmapped detects null keys."""
        data = [
            ("USA", 1),
            ("CHN", 2),
            ("Unknown Country", None),  # Unmapped
            ("Mystery Land", None)       # Unmapped
        ]
        df = spark.createDataFrame(data, ["country_name", "country_key"])

        unmapped_count = check_unmapped(
            df,
            "country_key",
            "country",
            log_unmapped=False
        )

        assert unmapped_count == 2

    @pytest.mark.unit
    def test_check_unmapped_raises_on_fail(self, spark):
        """Test that check_unmapped raises error when fail=True."""
        schema = StructType([
            StructField("name", StringType(), True),
            StructField("key", IntegerType(), True)
        ])
        data = [("Unknown", None)]
        df = spark.createDataFrame(data, schema)

        with pytest.raises(ValueError, match="Pipeline failed"):
            check_unmapped(
                df,
                "key",
                "test",
                fail=True,
                fail_on_unmapped=True,
                log_unmapped=False
            )


class TestCheckNulls:
    """Tests for check_nulls() function."""

    @pytest.mark.unit
    def test_check_nulls_no_nulls(self, spark):
        """Test check_nulls with no null values."""
        data = [(1.0,), (2.0,), (3.0,)]
        df = spark.createDataFrame(data, ["spend_eur"])

        null_count = check_nulls(df, "spend_eur", "fact_procurement")

        assert null_count == 0

    @pytest.mark.unit
    def test_check_nulls_with_nulls(self, spark):
        """Test check_nulls detects null values."""
        data = [(1.0,), (None,), (3.0,), (None,)]
        df = spark.createDataFrame(data, ["spend_eur"])

        null_count = check_nulls(df, "spend_eur", "fact_procurement")

        assert null_count == 2

    @pytest.mark.unit
    def test_check_nulls_raises_on_fail(self, spark):
        """Test that check_nulls raises error when fail_on_nulls=True."""
        data = [(1.0,), (None,)]
        df = spark.createDataFrame(data, ["spend_eur"])

        with pytest.raises(ValueError, match="Pipeline failed"):
            check_nulls(df, "spend_eur", "fact_procurement", fail_on_nulls=True)


class TestCheckDuplicates:
    """Tests for check_duplicates() function."""

    @pytest.mark.unit
    def test_check_duplicates_no_duplicates(self, spark):
        """Test check_duplicates with unique records."""
        data = [
            (20240101, 1, 1),
            (20240101, 1, 2),  # Different supplier
            (20240102, 1, 1),  # Different date
        ]
        df = spark.createDataFrame(data, ["date_key", "material_key", "supplier_key"])

        dup_count = check_duplicates(
            df,
            ["date_key", "material_key", "supplier_key"],
            "fact_procurement"
        )

        assert dup_count == 0

    @pytest.mark.unit
    def test_check_duplicates_with_duplicates(self, spark):
        """Test check_duplicates detects duplicate records."""
        data = [
            (20240101, 1, 1),
            (20240101, 1, 1),  # Duplicate
            (20240102, 2, 2),
        ]
        df = spark.createDataFrame(data, ["date_key", "material_key", "supplier_key"])

        dup_count = check_duplicates(
            df,
            ["date_key", "material_key", "supplier_key"],
            "fact_procurement"
        )

        assert dup_count == 1  # 1 unique duplicate key combination

    @pytest.mark.unit
    def test_check_duplicates_raises_on_fail(self, spark):
        """Test that check_duplicates raises error when fail_on_duplicates=True."""
        data = [(1, 1), (1, 1)]  # Duplicate
        df = spark.createDataFrame(data, ["key1", "key2"])

        with pytest.raises(ValueError, match="Pipeline failed"):
            check_duplicates(
                df,
                ["key1", "key2"],
                "test_table",
                fail_on_duplicates=True
            )


class TestValidateRange:
    """Tests for validate_range() function."""

    @pytest.mark.unit
    def test_validate_range_all_valid(self, spark):
        """Test validate_range with all values in range."""
        data = [(50.0,), (75.5,), (100.0,)]
        df = spark.createDataFrame(data, ["score"])

        invalid_count = validate_range(
            df,
            "score",
            min_value=0.0,
            max_value=100.0,
            table_name="fact_epi_score"
        )

        assert invalid_count == 0

    @pytest.mark.unit
    def test_validate_range_below_minimum(self, spark):
        """Test validate_range detects values below minimum."""
        data = [(-5.0,), (50.0,), (75.0,)]
        df = spark.createDataFrame(data, ["score"])

        invalid_count = validate_range(
            df,
            "score",
            min_value=0.0,
            max_value=100.0
        )

        assert invalid_count == 1

    @pytest.mark.unit
    def test_validate_range_above_maximum(self, spark):
        """Test validate_range detects values above maximum."""
        data = [(50.0,), (105.0,), (200.0,)]
        df = spark.createDataFrame(data, ["score"])

        invalid_count = validate_range(
            df,
            "score",
            min_value=0.0,
            max_value=100.0
        )

        assert invalid_count == 2

    @pytest.mark.unit
    def test_validate_range_only_minimum(self, spark):
        """Test validate_range with only minimum constraint."""
        data = [(-5.0,), (0.0,), (1000.0,)]
        df = spark.createDataFrame(data, ["price"])

        invalid_count = validate_range(
            df,
            "price",
            min_value=0.0
        )

        assert invalid_count == 1

    @pytest.mark.unit
    def test_validate_range_only_maximum(self, spark):
        """Test validate_range with only maximum constraint."""
        data = [(5.0,), (10.0,), (15.0,)]
        df = spark.createDataFrame(data, ["quantity"])

        invalid_count = validate_range(
            df,
            "quantity",
            max_value=10.0
        )

        assert invalid_count == 1  # 15.0 exceeds max

    @pytest.mark.unit
    def test_validate_range_no_constraints(self, spark):
        """Test validate_range with no constraints returns 0."""
        data = [(100.0,)]
        df = spark.createDataFrame(data, ["value"])

        invalid_count = validate_range(df, "value")

        assert invalid_count == 0


class TestCategorizeQuality:
    """Tests for categorize_quality() function."""

    @pytest.mark.unit
    def test_categorize_quality_high(self):
        """Test quality categorization for high confidence scores."""
        assert categorize_quality(1.0) == "High"
        assert categorize_quality(0.95) == "High"
        assert categorize_quality(0.90) == "High"

    @pytest.mark.unit
    def test_categorize_quality_medium(self):
        """Test quality categorization for medium confidence scores."""
        assert categorize_quality(0.85) == "Medium"
        assert categorize_quality(0.75) == "Medium"
        assert categorize_quality(0.70) == "Medium"

    @pytest.mark.unit
    def test_categorize_quality_low(self):
        """Test quality categorization for low confidence scores."""
        assert categorize_quality(0.65) == "Low"
        assert categorize_quality(0.55) == "Low"
        assert categorize_quality(0.50) == "Low"

    @pytest.mark.unit
    def test_categorize_quality_unmapped(self):
        """Test quality categorization for unmapped scores."""
        assert categorize_quality(0.45) == "Unmapped"
        assert categorize_quality(0.20) == "Unmapped"
        assert categorize_quality(0.0) == "Unmapped"

    @pytest.mark.unit
    def test_categorize_quality_boundary_values(self):
        """Test quality categorization at boundary values."""
        # Test boundaries between categories
        assert categorize_quality(0.899) == "Medium"  # Just below High threshold
        assert categorize_quality(0.900) == "High"    # At High threshold

        assert categorize_quality(0.699) == "Low"     # Just below Medium threshold
        assert categorize_quality(0.700) == "Medium"  # At Medium threshold

        assert categorize_quality(0.499) == "Unmapped"  # Just below Low threshold
        assert categorize_quality(0.500) == "Low"       # At Low threshold


class TestCountOutOfRangeDates:
    """Tests for count_out_of_range_dates() — bronze date_range_validation logic."""

    def _date_df(self, spark, dates):
        schema = StructType([StructField("Date", DateType(), True)])
        return spark.createDataFrame([(d,) for d in dates], schema)

    @pytest.mark.unit
    def test_all_dates_in_window(self, spark):
        """No false positives when all dates fall inside the plausible window."""
        df = self._date_df(spark, [date(2020, 1, 1), date(2022, 6, 15), date(2023, 12, 31)])

        count = count_out_of_range_dates(
            df, "Date", min_date=date(2015, 1, 1), max_date=date(2024, 12, 31)
        )

        assert count == 0

    @pytest.mark.unit
    def test_detects_future_dates(self, spark):
        """Dates after max_date (future) are flagged."""
        df = self._date_df(spark, [date(2023, 1, 1), date(2030, 1, 1), date(2099, 12, 31)])

        count = count_out_of_range_dates(
            df, "Date", min_date=date(2015, 1, 1), max_date=date(2024, 12, 31)
        )

        assert count == 2

    @pytest.mark.unit
    def test_detects_implausibly_old_dates(self, spark):
        """Dates before min_date (implausibly old) are flagged."""
        df = self._date_df(spark, [date(1900, 1, 1), date(2010, 1, 1), date(2020, 1, 1)])

        count = count_out_of_range_dates(
            df, "Date", min_date=date(2015, 1, 1), max_date=date(2024, 12, 31)
        )

        assert count == 2  # 1900 and 2010 are before the 2015 floor

    @pytest.mark.unit
    def test_boundary_dates_are_inclusive(self, spark):
        """Dates exactly on min/max boundaries are in range (inclusive window)."""
        df = self._date_df(spark, [date(2015, 1, 1), date(2024, 12, 31)])

        count = count_out_of_range_dates(
            df, "Date", min_date=date(2015, 1, 1), max_date=date(2024, 12, 31)
        )

        assert count == 0

    @pytest.mark.unit
    def test_null_dates_not_counted(self, spark):
        """Null dates are ignored here — they are the completeness check's concern."""
        df = self._date_df(spark, [None, date(2020, 1, 1), None])

        count = count_out_of_range_dates(
            df, "Date", min_date=date(2015, 1, 1), max_date=date(2024, 12, 31)
        )

        assert count == 0


class TestFindTypeMismatches:
    """Tests for find_type_mismatches() — silver data_type_consistency logic."""

    @pytest.mark.unit
    def test_all_types_conform(self, spark, sample_procurement_data):
        """No mismatches when expected types match the actual schema."""
        # sample_procurement_data: Date=date, MaterialName=string, Quantity=double, ...
        expected = {
            "Date": "date",
            "MaterialName": "string",
            "Quantity": "double",
            "UnitPriceEUR": "double",
        }

        mismatches = find_type_mismatches(sample_procurement_data, expected)

        assert mismatches == []

    @pytest.mark.unit
    def test_case_insensitive_column_match(self, spark, sample_procurement_data):
        """Column-name matching is case-insensitive (silver lowercases names)."""
        expected = {"date": "date", "materialname": "string", "quantity": "double"}

        mismatches = find_type_mismatches(sample_procurement_data, expected)

        assert mismatches == []

    @pytest.mark.unit
    def test_detects_type_mismatch(self, spark):
        """A column whose actual type differs from expected is reported."""
        schema = StructType([
            StructField("quantity", StringType(), True),  # should be numeric
            StructField("unit", StringType(), True),
        ])
        df = spark.createDataFrame([("100", "kg")], schema)

        mismatches = find_type_mismatches(df, {"quantity": "double", "unit": "string"})

        assert len(mismatches) == 1
        assert "quantity" in mismatches[0]

    @pytest.mark.unit
    def test_detects_missing_column(self, spark):
        """A column named in expected_types but absent from the schema is a mismatch."""
        schema = StructType([StructField("unit", StringType(), True)])
        df = spark.createDataFrame([("kg",)], schema)

        mismatches = find_type_mismatches(df, {"quantity": "double", "unit": "string"})

        assert len(mismatches) == 1
        assert "quantity" in mismatches[0]
        assert "missing" in mismatches[0]

    @pytest.mark.unit
    def test_extra_columns_ignored(self, spark, sample_procurement_data):
        """Columns present in the DataFrame but not in expected_types are not failures."""
        expected = {"Date": "date"}  # only check one of many columns

        mismatches = find_type_mismatches(sample_procurement_data, expected)

        assert mismatches == []


class TestCountIncompleteRows:
    """Tests for count_incomplete_rows() — silver completeness logic."""

    @pytest.mark.unit
    def test_all_rows_complete(self, spark):
        """No incomplete rows when every required column is populated."""
        data = [("USA", "DE"), ("CHN", "CN")]
        df = spark.createDataFrame(data, ["headquarterscountry", "productioncountry"])

        count = count_incomplete_rows(df, ["headquarterscountry", "productioncountry"])

        assert count == 0

    @pytest.mark.unit
    def test_detects_join_miss_nulls(self, spark):
        """Rows with a null in any required column (e.g. a join miss) are counted."""
        data = [
            ("USA", "DE"),
            ("CHN", None),   # production country join miss
            (None, "FR"),    # hq country join miss
        ]
        df = spark.createDataFrame(data, ["headquarterscountry", "productioncountry"])

        count = count_incomplete_rows(df, ["headquarterscountry", "productioncountry"])

        assert count == 2

    @pytest.mark.unit
    def test_row_counted_once_when_multiple_nulls(self, spark):
        """A row missing several required columns counts once, not per-null."""
        data = [(None, None), ("USA", "DE")]
        df = spark.createDataFrame(data, ["headquarterscountry", "productioncountry"])

        count = count_incomplete_rows(df, ["headquarterscountry", "productioncountry"])

        assert count == 1

    @pytest.mark.unit
    def test_single_required_column(self, spark):
        """Works with a single required column."""
        data = [("USA",), (None,), ("CHN",)]
        df = spark.createDataFrame(data, ["headquarterscountry"])

        count = count_incomplete_rows(df, ["headquarterscountry"])

        assert count == 1

    @pytest.mark.unit
    def test_empty_required_columns_returns_zero(self, spark):
        """No required columns means nothing can be incomplete."""
        data = [("USA",), (None,)]
        df = spark.createDataFrame(data, ["headquarterscountry"])

        count = count_incomplete_rows(df, [])

        assert count == 0
