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
    find_unreachable_initcap_keys,
)
from tests.test_key_generation import load_notebook_functions


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

    @pytest.mark.unit
    def test_check_duplicates_semantics_differ_from_notebook(self, spark):
        """Pin the deliberate semantic gap vs the notebook's detect_duplicates.

        src.check_duplicates counts DISTINCT KEY COMBINATIONS occurring more than
        once; fabric/data_quality_checks.Notebook's detect_duplicates counts
        EXCESS ROWS (total_rows - distinct_key_rows). Both are legitimate
        metrics, but they are not interchangeable — this test exists so nobody
        "unifies" them by accident and shifts what
        gold_quality_check_results.failed_rows means.
        """
        data = [(1, 1), (1, 1), (1, 1), (2, 2)]  # one key combo repeated 3x
        df = spark.createDataFrame(data, ["key1", "key2"])
        key_columns = ["key1", "key2"]

        src_count = check_duplicates(df, key_columns, "test_table")

        # The notebook's arithmetic, restated:
        total_rows = df.count()
        unique_rows = df.select(key_columns).distinct().count()
        notebook_count = total_rows - unique_rows

        assert src_count == 1, "src counts duplicated key combinations"
        assert notebook_count == 2, "notebook counts excess rows"
        assert src_count != notebook_count, (
            "This test is only meaningful while the two metrics differ; if they "
            "were unified, update both the docstring and the quality-results "
            "interpretation deliberately."
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


class TestFindUnreachableInitcapKeys:
    """
    Tests for find_unreachable_initcap_keys() — the initcap-reachability guard.

    The gold notebook initcaps material names before joining them to the alias
    table and commodity-group map, so any mapping key that initcap can never
    produce is dead: its rows silently classify as Other/Unknown (task-028 finding
    A). These tests execute Spark's real initcap, turning that belief into a
    checkable property.
    """

    @pytest.mark.unit
    def test_reachable_keys_return_empty(self, spark):
        """Keys already in initcap-canonical form are reachable."""
        keys = ["Copper", "Lithium", "Rare Earths"]

        assert find_unreachable_initcap_keys(spark, keys) == []

    @pytest.mark.unit
    def test_detects_parenthesized_capitals(self, spark):
        """Capitals after '(' or '-' survive initcap nowhere — those keys are dead."""
        keys = ["Steel (High-Tensile)", "Plastic (Abs)", "Rare Earths (Ndpr)"]

        assert find_unreachable_initcap_keys(spark, keys) == keys

    @pytest.mark.unit
    def test_hand_tuned_keys_are_reachable(self, spark):
        """The keys already hand-fitted to initcap's output must NOT be flagged.

        These two are the tell that this bug was hit before and only partially
        fixed — they are spelled the way initcap emits them.
        """
        keys = ["Electronics (controllers, Sensors)", "Tires (rubber Compound)"]

        assert find_unreachable_initcap_keys(spark, keys) == []

    @pytest.mark.unit
    def test_mixed_set_reports_only_unreachable_in_order(self, spark):
        """Only the dead keys are returned, in caller order."""
        keys = ["Copper", "Steel (High-Tensile)", "Lithium", "Plastic (Abs)"]

        result = find_unreachable_initcap_keys(spark, keys)

        assert result == ["Steel (High-Tensile)", "Plastic (Abs)"]

    @pytest.mark.unit
    def test_all_caps_key_is_unreachable(self, spark):
        """An all-caps alias LHS can never match initcap-normalized input."""
        keys = ["STEEL (High-Tensile)", "steel (high-tensile)"]

        assert find_unreachable_initcap_keys(spark, keys) == keys

    @pytest.mark.unit
    def test_empty_key_list(self, spark):
        """No keys means nothing unreachable."""
        assert find_unreachable_initcap_keys(spark, []) == []


class TestNotebookParity:
    """
    Parity guard for the reference-implementation contract (task-032).

    src/transformations/data_quality.py mirrors logic that the Fabric notebooks
    define inline. check_unmapped is the shared function whose return value the
    pipeline acts on, so its count semantics are pinned against the notebook's
    own definition.
    """

    @pytest.mark.unit
    def test_check_unmapped_count_parity_with_notebook(self, spark):
        """src.check_unmapped returns the same count as the notebook's version."""
        nb = load_notebook_functions(
            ["check_unmapped"],
            extra_globals={"LOG_UNMAPPED": False, "FAIL_ON_UNMAPPED": False},
        )
        nb_check_unmapped = nb["check_unmapped"]

        schema = StructType([
            StructField("country_name", StringType(), True),
            StructField("country_key", IntegerType(), True),
        ])
        df = spark.createDataFrame(
            [("USA", 1), ("CHN", 2), ("Unknown Country", None), ("Mystery Land", None)],
            schema,
        )

        src_count = check_unmapped(df, "country_key", "country", log_unmapped=False)
        nb_count = nb_check_unmapped(df, "country_key", "country")

        assert src_count == nb_count == 2

    @pytest.mark.unit
    def test_check_unmapped_zero_parity_with_notebook(self, spark):
        """Both versions agree when nothing is unmapped."""
        nb = load_notebook_functions(
            ["check_unmapped"],
            extra_globals={"LOG_UNMAPPED": False, "FAIL_ON_UNMAPPED": False},
        )

        df = spark.createDataFrame([("USA", 1), ("CHN", 2)], ["country_name", "country_key"])

        assert check_unmapped(df, "country_key", "country", log_unmapped=False) == 0
        assert nb["check_unmapped"](df, "country_key", "country") == 0

    @pytest.mark.unit
    def test_categorize_quality_matches_notebook_thresholds(self, spark):
        """categorize_quality mirrors the gold notebook's quality_category ladder.

        The notebook computes the same buckets as a Spark CASE expression
        (>= 0.9 High, >= 0.7 Medium, >= 0.5 Low, else Unmapped); this asserts the
        Python helper agrees at and around every boundary.
        """
        scores = [1.0, 0.9, 0.899, 0.7, 0.699, 0.5, 0.499, 0.0]
        df = spark.createDataFrame([(s,) for s in scores], ["data_quality_score"])

        notebook_category = (
            F.when(F.col("data_quality_score") >= 0.9, "High")
             .when(F.col("data_quality_score") >= 0.7, "Medium")
             .when(F.col("data_quality_score") >= 0.5, "Low")
             .otherwise("Unmapped")
        )

        rows = df.withColumn("quality_category", notebook_category).collect()

        for row in rows:
            assert categorize_quality(row["data_quality_score"]) == row["quality_category"], (
                f"threshold drift at score {row['data_quality_score']}"
            )
