"""
Unit tests for the procurement date correction relocated by task-048.

`bronze_azureSQLdb2table` (Dataflow Gen2) used to undo the source system's
day/year transposition during ingestion. That dataflow is retired — an SPN
cannot refresh it and every `fabric-cicd` publish strips its credentials — and
its Copy-activity replacement cannot transform. The correction therefore moved
into `bronze-to-silver`.

task-048 acceptance criterion 4 requires *proof* that silver `Date` values are
unchanged versus the pre-migration behaviour. That is what
`TestPreVsPostMigrationParity` does: it runs both paths over one fixture of raw
source rows —

    PRE  : dataflow corrects during ingestion -> bronze holds corrected dates
           -> silver passes them through unchanged
    POST : bronze holds RAW dates
           -> silver applies `correct_procurement_date`

— and asserts the resulting silver `Date` columns are identical. The
pre-migration side is modelled by `_mashup_corrected_date`, an independent
pure-Python transcription of the retired `mashup.pq` step, so the two sides do
not share an implementation and the comparison is meaningful.

Also covered:
  * value / boundary / NULL semantics of the correction itself
  * indifference to whether the Copy activity lands bronze `Date` as a Spark
    date or as a string
  * equivalence of the incremental look-back window across the migration, plus
    the regression guard showing that windowing on RAW dates selects a
    different row set (the failure mode the ordering in the notebook prevents)
  * notebook parity (reference-implementation contract, task-032)
"""

import ast
from datetime import date

import pytest
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, DateType, DoubleType,
)

from src.transformations.procurement_dates import (
    DATE_SWAP_EPOCH,
    PROCUREMENT_DATE_COLUMN,
    correct_procurement_date,
)
from tests._notebook_loader import load_notebook_functions, BRONZE_NOTEBOOK

# correct_procurement_date reads the notebook-global DATE_SWAP_EPOCH; only the
# FunctionDef is compiled by the harness, so it must be injected per call.
_EPOCH_GLOBALS = {"DATE_SWAP_EPOCH": DATE_SWAP_EPOCH}


# ---------------------------------------------------------------------------
# Pre-migration reference: the retired mashup.pq step, in pure Python
# ---------------------------------------------------------------------------

def _mashup_corrected_date(raw):
    """Transcription of the retired dataflow's CorrectedDate step.

        CorrectedDate = #date(Date.Day([Date]) + 2000,
                              Date.Month([Date]),
                              Date.Year([Date]) - 2000)

    Power Query's `#date()` RAISES on an out-of-range component (which failed the
    whole refresh); `datetime.date()` raises `ValueError` in the same cases, so the
    raise is left to propagate here. Callers that want the post-migration NULL
    behaviour use `_mashup_corrected_date_or_none`.
    """
    if raw is None:
        return None
    return date(raw.day + 2000, raw.month, raw.year - 2000)


def _mashup_corrected_date_or_none(raw):
    """As above, but maps the Power Query error case to None.

    Post-migration, Spark's `make_date` returns NULL where `#date()` raised
    (`spark.sql.ansi.enabled=false`, Fabric's default). This models that.
    """
    try:
        return _mashup_corrected_date(raw)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Raw rows as they sit in dbo.procurement_transactional, with the corrected date
# each one is supposed to produce. Read a raw value as:
#     corrected.year  = raw.day + 2000
#     corrected.month = raw.month          (unchanged)
#     corrected.day   = raw.year - 2000
VALID_RAW_CASES = [
    # (raw date, expected corrected date, why this case is here)
    (date(2015, 1, 24), date(2024, 1, 15), "ordinary mid-month date"),
    (date(2031, 3, 24), date(2024, 3, 31), "max day-of-month (raw year 2031 -> day 31)"),
    (date(2001, 12, 23), date(2023, 12, 1), "min day-of-month (raw year 2001 -> day 1)"),
    (date(2029, 2, 24), date(2024, 2, 29), "leap day, valid in the corrected year"),
    (date(2001, 1, 1), date(2001, 1, 1), "lowest representable corrected year (2001)"),
    (date(2010, 7, 25), date(2025, 7, 10), "another ordinary date, different year"),
]

# Raw rows whose corrected components are NOT a real calendar date. Power Query's
# #date() raised on these (failing the refresh); make_date returns NULL.
INVALID_RAW_CASES = [
    (date(2029, 2, 23), "corrected 2023-02-29 — 2023 is not a leap year"),
    (date(2045, 5, 24), "raw year 2045 -> corrected day 45, out of 1..31"),
    (date(1999, 5, 24), "raw year 1999 -> corrected day -1, out of 1..31"),
    (date(2000, 6, 24), "raw year 2000 -> corrected day 0, out of 1..31"),
]

BRONZE_SCHEMA_DATE = StructType([
    StructField("Date", DateType(), True),
    StructField("MaterialName", StringType(), True),
    StructField("SupplierName", StringType(), True),
    StructField("Region", StringType(), True),
    StructField("Quantity", DoubleType(), True),
    StructField("Unit", StringType(), True),
    StructField("UnitPriceEUR", DoubleType(), True),
])

BRONZE_SCHEMA_STRING_DATE = StructType(
    [StructField("Date", StringType(), True)] + BRONZE_SCHEMA_DATE.fields[1:]
)


def _payload(i):
    """Non-date columns for row i — kept stable so rows are identifiable."""
    return (f"Material{i}", f"Supplier{i}", "Europe", float(100 + i), "kg", float(10 + i))


def _bronze_rows(raw_dates):
    return [(d,) + _payload(i) for i, d in enumerate(raw_dates)]


@pytest.fixture
def raw_bronze_df(spark):
    """Bronze as the Copy activity lands it post-migration: RAW, transposed dates."""
    raws = [c[0] for c in VALID_RAW_CASES]
    return spark.createDataFrame(_bronze_rows(raws), schema=BRONZE_SCHEMA_DATE)


@pytest.fixture
def pre_migration_bronze_df(spark):
    """Bronze as the retired dataflow landed it: dates ALREADY corrected."""
    raws = [c[0] for c in VALID_RAW_CASES]
    corrected = [_mashup_corrected_date(d) for d in raws]
    return spark.createDataFrame(_bronze_rows(corrected), schema=BRONZE_SCHEMA_DATE)


def _dates(df):
    """Ordered list of Date values, for comparison. Row.Date is safe (not a tuple method)."""
    return [r["Date"] for r in df.orderBy("MaterialName").select("Date").collect()]


# ---------------------------------------------------------------------------
# 1. The correction itself — values, boundaries, NULLs
# ---------------------------------------------------------------------------

class TestCorrectProcurementDate:
    """`correct_procurement_date` reproduces the mashup's #date(day+2000, month, year-2000)."""

    @pytest.mark.unit
    def test_valid_dates_match_expected(self, spark, raw_bronze_df):
        got = _dates(correct_procurement_date(raw_bronze_df))
        expected = [c[1] for c in VALID_RAW_CASES]
        assert got == expected, (
            "corrected dates diverge from the hand-computed expectations:\n"
            + "\n".join(
                f"  raw={c[0]} why={c[2]!r} expected={c[1]} got={g}"
                for c, g in zip(VALID_RAW_CASES, got)
                if c[1] != g
            )
        )

    @pytest.mark.unit
    def test_valid_dates_match_the_retired_mashup(self, spark, raw_bronze_df):
        """Independent check against the pure-Python transcription of mashup.pq."""
        got = _dates(correct_procurement_date(raw_bronze_df))
        expected = [_mashup_corrected_date(c[0]) for c in VALID_RAW_CASES]
        assert got == expected

    @pytest.mark.unit
    def test_column_is_replaced_in_place(self, spark, raw_bronze_df):
        """The mashup's add/drop/rename netted out to an in-place replace; so must this.

        No `CorrectedDate` column may survive into silver, and column ORDER must be
        preserved — the downstream join and lowercase-rename assume the bronze shape.
        """
        out = correct_procurement_date(raw_bronze_df)
        assert out.columns == raw_bronze_df.columns
        assert "CorrectedDate" not in out.columns
        assert dict(out.dtypes)["Date"] == "date"

    @pytest.mark.unit
    def test_invalid_components_yield_null_not_an_exception(self, spark):
        """Power Query raised; Spark (ANSI off, as in Fabric) must NULL instead."""
        rows = _bronze_rows([c[0] for c in INVALID_RAW_CASES])
        df = spark.createDataFrame(rows, schema=BRONZE_SCHEMA_DATE)
        got = _dates(correct_procurement_date(df))
        assert got == [None] * len(INVALID_RAW_CASES), (
            "expected NULL for every out-of-range case:\n"
            + "\n".join(
                f"  raw={c[0]} why={c[1]!r} got={g}"
                for c, g in zip(INVALID_RAW_CASES, got)
                if g is not None
            )
        )

    @pytest.mark.unit
    def test_null_raw_date_propagates_as_null(self, spark):
        df = spark.createDataFrame(_bronze_rows([None, date(2015, 1, 24)]),
                                   schema=BRONZE_SCHEMA_DATE)
        assert _dates(correct_procurement_date(df)) == [None, date(2024, 1, 15)]

    @pytest.mark.unit
    def test_empty_input_is_not_an_error(self, spark):
        empty = spark.createDataFrame([], schema=BRONZE_SCHEMA_DATE)
        out = correct_procurement_date(empty)
        assert out.count() == 0
        assert out.columns == BRONZE_SCHEMA_DATE.fieldNames()

    @pytest.mark.unit
    def test_string_typed_bronze_date_gives_identical_results(self, spark):
        """The Copy activity's landing type for `Date` is not pinned by this task.

        Whether Fabric writes a Spark date or an ISO string, the correction must
        produce the same values — that is why `to_date` is applied first.
        """
        raws = [c[0] for c in VALID_RAW_CASES]
        as_date = spark.createDataFrame(_bronze_rows(raws), schema=BRONZE_SCHEMA_DATE)
        as_string = spark.createDataFrame(
            _bronze_rows([d.isoformat() for d in raws]),
            schema=BRONZE_SCHEMA_STRING_DATE,
        )
        assert _dates(correct_procurement_date(as_string)) == \
               _dates(correct_procurement_date(as_date))

    @pytest.mark.unit
    def test_correcting_a_custom_column_name(self, spark, raw_bronze_df):
        renamed = raw_bronze_df.withColumnRenamed("Date", "TxnDate")
        out = correct_procurement_date(renamed, column="TxnDate")
        got = [r["TxnDate"] for r in out.orderBy("MaterialName").select("TxnDate").collect()]
        assert got == [c[1] for c in VALID_RAW_CASES]

    @pytest.mark.unit
    def test_constants_match_the_mashup(self):
        assert DATE_SWAP_EPOCH == 2000
        assert PROCUREMENT_DATE_COLUMN == "Date"


# ---------------------------------------------------------------------------
# 2. Criterion 4 — silver dates unchanged across the migration
# ---------------------------------------------------------------------------

class TestPreVsPostMigrationParity:
    """The proof task-048 criterion 4 asks for.

    PRE : dataflow corrected during ingestion, silver passed bronze through.
    POST: bronze lands raw, silver corrects.
    The silver `Date` column must be byte-identical between the two.
    """

    @pytest.mark.unit
    def test_silver_dates_identical(self, spark, raw_bronze_df, pre_migration_bronze_df):
        silver_pre = _dates(pre_migration_bronze_df)          # passthrough
        silver_post = _dates(correct_procurement_date(raw_bronze_df))
        assert silver_post == silver_pre, (
            "silver Date values changed across the task-048 migration — "
            "the relocated correction is not equivalent to the retired dataflow"
        )

    @pytest.mark.unit
    def test_silver_dates_identical_including_full_row_payload(
        self, spark, raw_bronze_df, pre_migration_bronze_df
    ):
        """Not just the date column — the whole silver row must be unchanged."""
        pre = [tuple(r) for r in pre_migration_bronze_df.orderBy("MaterialName").collect()]
        post = [tuple(r) for r in
                correct_procurement_date(raw_bronze_df).orderBy("MaterialName").collect()]
        assert post == pre

    @pytest.mark.unit
    def test_schema_unchanged(self, spark, raw_bronze_df, pre_migration_bronze_df):
        assert correct_procurement_date(raw_bronze_df).schema == pre_migration_bronze_df.schema


# ---------------------------------------------------------------------------
# 3. The incremental look-back window survives the migration
# ---------------------------------------------------------------------------

class TestIncrementalWindowEquivalence:
    """The silver 7-day look-back must select the SAME rows before and after.

    The notebook applies `correct_procurement_date` BEFORE the window for exactly
    this reason: the watermark (`bronze_load_metadata.last_load_date`) and the
    delete-insert boundary (`window_min_date`) are both expressed in corrected-date
    space. `test_windowing_on_raw_dates_is_wrong` pins the failure mode that the
    ordering prevents, so a future reordering fails here rather than silently in
    Fabric.
    """

    LOOKBACK = "2024-01-20"

    def _window(self, df):
        return df.filter(F.col("Date") >= F.to_date(F.lit(self.LOOKBACK)))

    @pytest.mark.unit
    def test_window_selects_the_same_rows(self, spark, raw_bronze_df, pre_migration_bronze_df):
        pre = sorted(r["MaterialName"] for r in self._window(pre_migration_bronze_df).collect())
        post = sorted(r["MaterialName"] for r in
                      self._window(correct_procurement_date(raw_bronze_df)).collect())
        assert post == pre
        assert pre, "fixture selects no rows — the window test would pass vacuously"

    @pytest.mark.unit
    def test_windowing_on_raw_dates_is_wrong(self, spark, raw_bronze_df,
                                             pre_migration_bronze_df):
        """Regression guard: correcting AFTER the window changes the row set.

        This is the failure mode of the naive relocation (leave the read filter alone,
        correct at the end). It is asserted, not fixed — if this ever stops differing,
        the fixture no longer exercises the hazard.
        """
        pre = sorted(r["MaterialName"] for r in self._window(pre_migration_bronze_df).collect())
        wrong = sorted(r["MaterialName"] for r in
                       correct_procurement_date(self._window(raw_bronze_df)).collect())
        assert wrong != pre, (
            "windowing raw dates happened to match — the fixture no longer covers the "
            "ordering hazard the notebook's correct-then-window sequence guards against"
        )

    @pytest.mark.unit
    def test_delete_insert_boundary_matches(self, spark, raw_bronze_df,
                                            pre_migration_bronze_df):
        """`window_min_date` (the DELETE boundary) must be identical across migration."""
        pre_min = self._window(pre_migration_bronze_df).agg(F.min("Date")).first()[0]
        post_min = self._window(
            correct_procurement_date(raw_bronze_df)
        ).agg(F.min("Date")).first()[0]
        assert post_min == pre_min

    @pytest.mark.unit
    def test_watermark_max_date_matches(self, spark, raw_bronze_df, pre_migration_bronze_df):
        """`last_load_date` is max(silver.date); it must not shift across migration."""
        pre_max = pre_migration_bronze_df.agg(F.max("Date")).first()[0]
        post_max = correct_procurement_date(raw_bronze_df).agg(F.max("Date")).first()[0]
        assert post_max == pre_max


# ---------------------------------------------------------------------------
# 4. Notebook parity (reference-implementation contract, task-032)
# ---------------------------------------------------------------------------

class TestNotebookParity:
    """bronze-to-silver defines `correct_procurement_date` inline; it must match src/."""

    @pytest.mark.unit
    def test_notebook_defines_the_function(self):
        tree = ast.parse(BRONZE_NOTEBOOK.read_text(encoding="utf-8"))
        names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
        assert "correct_procurement_date" in names, (
            "bronze-to-silver.Notebook no longer defines correct_procurement_date; "
            "the source date correction relocated by task-048 would be silently lost "
            "and every silver transaction date would be wrong."
        )

    @pytest.mark.unit
    def test_parity_on_valid_dates(self, spark, raw_bronze_df):
        nb = load_notebook_functions(
            BRONZE_NOTEBOOK, ["correct_procurement_date"], extra_globals=_EPOCH_GLOBALS,
        )
        assert _dates(nb["correct_procurement_date"](raw_bronze_df)) == \
               _dates(correct_procurement_date(raw_bronze_df))

    @pytest.mark.unit
    def test_parity_on_invalid_and_null_dates(self, spark):
        nb = load_notebook_functions(
            BRONZE_NOTEBOOK, ["correct_procurement_date"], extra_globals=_EPOCH_GLOBALS,
        )
        raws = [c[0] for c in INVALID_RAW_CASES] + [None, date(2015, 1, 24)]
        df = spark.createDataFrame(_bronze_rows(raws), schema=BRONZE_SCHEMA_DATE)
        assert _dates(nb["correct_procurement_date"](df)) == _dates(correct_procurement_date(df))

    @pytest.mark.unit
    def test_parity_on_string_typed_dates(self, spark):
        nb = load_notebook_functions(
            BRONZE_NOTEBOOK, ["correct_procurement_date"], extra_globals=_EPOCH_GLOBALS,
        )
        raws = [c[0].isoformat() for c in VALID_RAW_CASES]
        df = spark.createDataFrame(_bronze_rows(raws), schema=BRONZE_SCHEMA_STRING_DATE)
        assert _dates(nb["correct_procurement_date"](df)) == _dates(correct_procurement_date(df))

    @pytest.mark.unit
    def test_notebook_corrects_before_windowing(self):
        """Pin the ORDERING in the notebook, not just the function.

        The relocated correction is only equivalent to the retired dataflow if it runs
        before the incremental look-back filter (see TestIncrementalWindowEquivalence).
        A refactor that reads bronze straight into `df1` and corrects later would pass
        every other test in this file while corrupting the delete-insert window.
        """
        source = BRONZE_NOTEBOOK.read_text(encoding="utf-8")

        call_at = source.find("correct_procurement_date(\n"
                              "    spark.sql(\"SELECT * FROM oem_lh.bronze_procurement_transactional\")")
        assert call_at != -1, (
            "bronze-to-silver no longer wraps the bronze_procurement_transactional read "
            "in correct_procurement_date — the correction must be applied at the read, "
            "before the look-back window."
        )

        filter_at = source.find('df1 = df1_all.filter(F.col("Date")')
        assert filter_at != -1, (
            "the incremental look-back no longer filters the corrected DataFrame "
            "(`df1_all`); windowing raw dates against a corrected-space watermark "
            "silently corrupts the delete-insert range."
        )
        assert call_at < filter_at, "correction must precede the look-back window"

        assert "WHERE Date >= '{lookback_str}'" not in source, (
            "the old raw-date SQL pushdown filter is back; post-task-048 bronze holds "
            "RAW transposed dates, so that predicate no longer means what it says."
        )
