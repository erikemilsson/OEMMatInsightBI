"""
Unit tests for data quality check functions.

Tests functions that validate data quality during transformations,
including unmapped value detection and quality categorization.
"""

import ast
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
from tests._notebook_loader import load_notebook_functions, GOLD_NOTEBOOK


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
            GOLD_NOTEBOOK,
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
            GOLD_NOTEBOOK,
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


# ---------------------------------------------------------------------------
# gold_data_gaps — create_data_gaps_table() coverage (task-078)
# ---------------------------------------------------------------------------
#
# WHY THIS EXISTS. create_data_gaps_table shipped two consecutive GRAIN defects with
# zero test coverage: task-071's 158.33% coverage rate and task-074's +23.7% spend
# inflation, both caused by a (country_key, country_role)-grained population under
# country-grained payload columns. task-074's fix added a grain guard that could never
# fire — it counted the frame AFTER dropDuplicates(["country_key"]), where rows and
# distinct countries are equal by construction for every possible input. These tests
# close that gap: they pin the function's core invariants and, critically, prove the
# repaired guard RAISES on an upstream fan-out.
#
# HARNESS. The function takes no arguments — it reads the notebook globals `spark`,
# `DB`, `write_tbl` and `WGI_REQUIRED_INDICATORS` and addresses its inputs as
# `{DB}.<table>`. So each input is registered as a GLOBAL temp view and DB is injected
# as "global_temp": no metastore database, no on-disk warehouse, and no Delta writer
# (write_tbl is stubbed to capture the frame it is handed, which also lets a test prove
# nothing was written when the guard fires).

_GAPS_DB = "global_temp"  # global temp views are addressable as global_temp.<name>

_DIM_COUNTRY_DDL = (
    "country_key INT, country_name_std STRING, iso3 STRING, region STRING, "
    "is_placeholder BOOLEAN"
)
_FACT_PROCUREMENT_DDL = (
    "supplier_hq_country_key INT, production_country_key INT, spend_eur DOUBLE"
)
_FACT_EPI_DDL = "country_key INT, indicator_key INT, score DOUBLE"
_DIM_INDICATOR_DDL = "indicator_key INT, abbrev STRING"
_SILVER_WGI_DDL = "country_iso3 STRING, indicator_name STRING, value DOUBLE"

_WGI_SIX = [
    "Control of Corruption",
    "Government Effectiveness",
    "Political Stability and Absence of Violence/Terrorism",
    "Regulatory Quality",
    "Rule of Law",
    "Voice and Accountability",
]

# Country fixture: key -> (name, iso3, region, is_placeholder)
_DEU, _CHN, _TWN, _BRA, _UNK = 1, 2, 3, 4, 9

_DIM_COUNTRY_ROWS = [
    (_DEU, "Germany", "DEU", "Europe", False),
    (_CHN, "China", "CHN", "Asia", False),
    (_TWN, "Taiwan", "TWN", "Asia", False),
    (_BRA, "Brazil", "BRA", "Americas", False),
    (_UNK, "Unknown - Global", "UNK_GLOBAL", "Unknown", True),
]

# Every fact row is booked against a NON-placeholder supplier HQ, so total spend over
# gold_data_gaps must reconcile to fact_procurement exactly (see the reconciliation test
# for the boundary condition that qualifies this contract).
_FACT_PROCUREMENT_ROWS = [
    (_DEU, _DEU, 100.0),   # Germany is both supplier HQ and production country
    (_DEU, _TWN, 50.0),    # Taiwan appears ONLY as a production country -> 0.0 spend
    (_CHN, _UNK, 40.0),    # placeholder appears only as a production country
    (_BRA, None, 10.0),
]
_FACT_TOTAL_SPEND = 200.0

# indicator_key 1 = the EPI composite; 2 = a sub-indicator that must NOT count as EPI
# coverage (task-054: the fact carries 30+ sub-indicator rows per country).
_DIM_INDICATOR_ROWS = [(1, "EPI"), (2, "AIR")]
_FACT_EPI_ROWS = [
    (_DEU, 1, 55.0),
    (_CHN, 1, 42.0),
    (_TWN, 1, None),   # null composite score -> not covered
    (_BRA, 2, 61.0),   # sub-indicator only -> not covered
]

# Germany + Brazil hold all six governance dimensions; China holds five real ones plus a
# null-valued sixth, which the `value IS NOT NULL` filter must drop; Taiwan holds none
# (the real, permanent TWN governance gap).
_SILVER_WGI_ROWS = (
    [("DEU", ind, 0.5) for ind in _WGI_SIX]
    + [("BRA", ind, -0.1) for ind in _WGI_SIX]
    + [("CHN", ind, -0.3) for ind in _WGI_SIX[:5]]
    + [("CHN", _WGI_SIX[5], None)]
)


def _notebook_int_constant(name):
    """Read a module-level int constant from the gold notebook's own source.

    The loader compiles only FunctionDefs, so notebook globals must be injected. Reading
    the value from the notebook text (rather than restating it here) keeps the injected
    value bound to the notebook — a threshold change there cannot silently pass under an
    old value pinned in the test.
    """
    tree = ast.parse(GOLD_NOTEBOOK.read_text(encoding="utf-8"), filename=str(GOLD_NOTEBOOK))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(
        f"{name} is no longer a module-level constant in {GOLD_NOTEBOOK.name}"
    )


def _run_create_data_gaps(spark, dim_country_rows=None, written=None):
    """Run the notebook's own create_data_gaps_table over in-memory fixtures.

    Returns (written, data_gaps_df, summary_df) where `written` maps table name ->
    DataFrame handed to write_tbl. Callers that outlive the view registrations must
    materialize before the next call replaces the views.

    `written` may be supplied by the caller so it stays inspectable when the function
    raises — a dict created inside this helper would be unreachable after an exception,
    which would make a "nothing was written" assertion vacuously true.
    """
    views = {
        "gold_dim_country": (dim_country_rows or _DIM_COUNTRY_ROWS, _DIM_COUNTRY_DDL),
        "fact_procurement": (_FACT_PROCUREMENT_ROWS, _FACT_PROCUREMENT_DDL),
        "fact_epi_score": (_FACT_EPI_ROWS, _FACT_EPI_DDL),
        "gold_dim_indicator": (_DIM_INDICATOR_ROWS, _DIM_INDICATOR_DDL),
        "silver_wgi": (_SILVER_WGI_ROWS, _SILVER_WGI_DDL),
    }
    for name, (rows, ddl) in views.items():
        spark.createDataFrame(rows, ddl).createOrReplaceGlobalTempView(name)

    written = {} if written is None else written

    def _write_tbl(df, tbl_name):
        written[tbl_name] = df

    nb = load_notebook_functions(
        GOLD_NOTEBOOK,
        ["create_data_gaps_table"],
        extra_globals={
            "spark": spark,
            "DB": _GAPS_DB,
            "write_tbl": _write_tbl,
            "WGI_REQUIRED_INDICATORS": _notebook_int_constant("WGI_REQUIRED_INDICATORS"),
        },
    )
    data_gaps, summary = nb["create_data_gaps_table"]()
    return written, data_gaps, summary


@pytest.fixture(scope="module")
def data_gaps_result(spark):
    """One run of create_data_gaps_table over the default fixture, fully materialized.

    Materialized to plain dicts on purpose: the input tables are global temp views, and a
    later test replaces them, so a lazily-held DataFrame would silently re-evaluate
    against another test's inputs. Dicts also sidestep the Row/tuple hazard — pyspark Row
    subclasses tuple, so `row.count` on a column named `count` returns a bound method.
    """
    written, data_gaps, summary = _run_create_data_gaps(spark)
    return {
        "rows": [r.asDict() for r in data_gaps.collect()],
        "summary": {r["metric_name"]: r["metric_value"] for r in summary.collect()},
        "written": sorted(written),
        "written_rows": {
            name: [r.asDict() for r in df.collect()] for name, df in written.items()
        },
    }


class TestDataGapsTable:
    """Core invariants of create_data_gaps_table — the coverage two grain defects shipped
    through (task-078 acceptance criterion 4)."""

    @pytest.mark.unit
    def test_one_row_per_country(self, data_gaps_result):
        """THE grain contract: one row per country, role carried as attributes."""
        rows = data_gaps_result["rows"]
        keys = [r["country_key"] for r in rows]

        assert len(keys) == len(set(keys)), f"gold_data_gaps fanned out: {sorted(keys)}"
        assert set(keys) == {_DEU, _CHN, _TWN, _BRA}

        germany = next(r for r in rows if r["country_key"] == _DEU)
        assert germany["is_supplier_hq"] is True
        assert germany["is_production"] is True, (
            "a dual-role country must be ONE row carrying both role flags, never two rows"
        )

    @pytest.mark.unit
    def test_written_table_has_the_same_grain(self, data_gaps_result):
        """The guard protects the WRITE, not just the returned frame."""
        assert data_gaps_result["written"] == ["gold_data_gaps", "gold_data_gaps_summary"]
        written_keys = [
            r["country_key"] for r in data_gaps_result["written_rows"]["gold_data_gaps"]
        ]
        assert len(written_keys) == len(set(written_keys)) == 4

    @pytest.mark.unit
    def test_spend_reconciles_to_fact_procurement_total(self, data_gaps_result):
        """SUM(spend_eur) over the country-grained table == fact_procurement's total.

        This is the +23.7% inflation regression (task-074): with a role-grained
        population, dual-role countries were counted twice and this equality broke.

        Boundary of the contract: it holds because spend is grouped on
        supplier_hq_country_key (partitioning the fact exactly once) and no placeholder
        country is a supplier HQ here — placeholders are filtered out of the table, so
        spend booked against one would sit outside it.
        """
        total = sum(r["spend_eur"] for r in data_gaps_result["rows"])
        assert total == pytest.approx(_FACT_TOTAL_SPEND)
        assert data_gaps_result["summary"]["Total Procurement Spend (EUR)"] == pytest.approx(
            _FACT_TOTAL_SPEND
        )

    @pytest.mark.unit
    def test_spend_is_supplier_hq_spend_only(self, data_gaps_result):
        """spend_eur is supplier-HQ spend by definition; a production-only country is 0.0.

        task-074 defect #2: under the role grain, a row whose role was 'Production'
        carried that country's supplier-HQ spend — a wrong value per row, not just a
        double count.
        """
        by_key = {r["country_key"]: r for r in data_gaps_result["rows"]}

        assert by_key[_DEU]["spend_eur"] == pytest.approx(150.0)
        assert by_key[_DEU]["transaction_count"] == 2
        assert by_key[_TWN]["spend_eur"] == pytest.approx(0.0)
        assert by_key[_TWN]["transaction_count"] == 0
        assert by_key[_TWN]["is_production"] is True
        assert by_key[_TWN]["is_supplier_hq"] is False

    @pytest.mark.unit
    def test_placeholder_countries_are_excluded(self, data_gaps_result):
        """Unknown - Global reaches procurement_countries but must not reach the table."""
        assert _UNK not in {r["country_key"] for r in data_gaps_result["rows"]}

    @pytest.mark.unit
    def test_coverage_flags_and_data_status(self, data_gaps_result):
        """EPI needs the abbrev='EPI' composite with a non-null score; WGI needs all six
        dimensions with non-null values."""
        by_key = {r["country_key"]: r for r in data_gaps_result["rows"]}

        assert by_key[_DEU]["data_status"] == "Full Coverage"
        assert by_key[_CHN]["data_status"] == "EPI Only"    # 5 of 6 WGI (6th is null)
        assert by_key[_BRA]["data_status"] == "WGI Only"    # sub-indicator is not EPI
        assert by_key[_TWN]["data_status"] == "No Coverage"  # null EPI score, no WGI

        assert by_key[_BRA]["has_epi_score"] is False
        assert by_key[_TWN]["has_epi_score"] is False
        assert by_key[_CHN]["has_wgi_score"] is False

    @pytest.mark.unit
    def test_summary_counts_and_percentages_are_country_grained(self, data_gaps_result):
        """task-071 regression: coverage rates over a fanned-out grain exceeded 100%."""
        summary = data_gaps_result["summary"]

        assert summary["Total Procurement Countries"] == 4.0
        assert summary["Countries with EPI Data"] == 2.0
        assert summary["Countries without EPI Data"] == 2.0
        assert summary["EPI Country Coverage %"] == pytest.approx(50.0)
        assert summary["Full Coverage (EPI + WGI)"] == 1.0
        assert summary["Full Coverage %"] == pytest.approx(25.0)

        over_100 = {
            name: value
            for name, value in summary.items()
            if name.endswith("%") and value > 100.0
        }
        assert not over_100, f"coverage rate above 100% implies a fanned-out grain: {over_100}"


class TestDataGapsGrainGuard:
    """task-078 — the guard must be able to FAIL.

    Referenced by name from the notebook's guard comment. Before task-078 the guard sat
    below `.dropDuplicates(["country_key"])` and compared two counts that are equal by
    construction, so this test failed: the duplicate was silently collapsed to one
    ARBITRARY surviving row and no ValueError was raised.
    """

    @staticmethod
    def _dim_country_with_duplicate_key():
        # A second row for country_key 1 — what a regression in gold_dim_country's
        # country_key uniqueness (task-025's row_number dedup) would look like here.
        return _DIM_COUNTRY_ROWS + [(_DEU, "Deutschland", "DEU", "Europe", False)]

    @pytest.mark.unit
    def test_duplicate_dim_country_row_raises_grain_violation(self, spark):
        with pytest.raises(ValueError, match=r"grain violation") as excinfo:
            _run_create_data_gaps(
                spark, dim_country_rows=self._dim_country_with_duplicate_key()
            )

        message = str(excinfo.value)
        assert "5 rows for 4 distinct countries" in message, message
        assert str(_DEU) in message, (
            f"the guard must name the duplicated country_key: {message}"
        )

    @pytest.mark.unit
    def test_fan_out_is_caught_before_the_table_is_written(self, spark):
        """The guard runs upstream of write_tbl, so an inflated table never lands."""
        written = {}
        try:
            _run_create_data_gaps(
                spark,
                dim_country_rows=self._dim_country_with_duplicate_key(),
                written=written,
            )
        except ValueError:
            pass
        else:  # pragma: no cover - the guard is expected to raise
            pytest.fail("create_data_gaps_table did not raise on a fanned-out grain")

        assert written == {}, (
            "gold_data_gaps must not be written when the grain guard fires"
        )
