"""
Procurement Date Correction — the day/year swap inherited from the source system

`dbo.procurement_transactional` in the Azure SQL source stores each transaction
date with its **day and year components transposed**: the calendar year lives in
the date's *day* position and the day-of-month lives in the *year* position (as
an offset from 2000). A raw value of `2015-01-24` therefore means `2024-01-15`.

Until task-048 this was corrected during ingestion, by the
`bronze_azureSQLdb2table` Dataflow Gen2 (`mashup.pq`), which built

    CorrectedDate = #date(Date.Day([Date]) + 2000,
                          Date.Month([Date]),
                          Date.Year([Date]) - 2000)

then dropped the original `Date` and renamed `CorrectedDate` to `Date` — a
net in-place replacement that preserved column order.

That dataflow is retired (task-048): a service principal cannot refresh a
Dataflow Gen2, and every `fabric-cicd` publish strips its credentials. It is
replaced by a Copy activity, and **a Copy activity cannot transform**. The
correction therefore moves *down* one layer, into `bronze_to_silver`: bronze now
lands the source's raw (malformed) `Date`, and silver corrects it. Keeping
bronze byte-faithful to the source is also better medallion practice than
folding the fix into the Copy activity's source query.

REFERENCE IMPLEMENTATION — NOT IMPORTED BY THE NOTEBOOKS (task-032)
------------------------------------------------------------------
The Fabric notebooks do NOT import this package; `fabric/bronze_to_silver.Notebook`
defines `correct_procurement_date` inline. The mirror is enforced, not trusted —
`tests/test_procurement_dates.py::TestNotebookParity` parses the notebook,
extracts its own definition, and asserts it produces identical dates to this
function over a fixture. Divergence fails CI by design.

**If you change this function, change the notebook to match (or vice versa).**

WHERE IT MUST BE APPLIED (load-bearing ordering)
------------------------------------------------
`bronze_to_silver` applies the correction **immediately after reading bronze and
before the incremental look-back filter**, not at the end of the procurement
block. Two things downstream are expressed in *corrected*-date space and would
silently break otherwise:

  * the watermark. `bronze_load_metadata.last_load_date` is written from
    `silver_df.agg(F.max("date"))`, i.e. a corrected date. Filtering raw bronze
    dates against a corrected-space watermark compares two different calendars.
  * the delete-insert boundary. `window_min_date` is the minimum date in the
    read window; if the window were selected on raw dates but the boundary
    computed on corrected ones, the DELETE would clear a range the subsequent
    append does not restore — silent data loss.

This is the *silver* look-back filter only. The **source-side** `p_from_date`
window (the `WHERE Date >= '<lookback>'` pushdown that the retired mashup ran via
`Value.NativeQuery`, and that the replacing Copy activity inherits) deliberately
runs against the RAW column — the correction was always applied after it. That
ordering is part of the `p_from_date` parameter contract and is unchanged.

NULL SEMANTICS
--------------
Power Query's `#date(...)` raises on an out-of-range component; Spark's
`make_date` returns NULL instead when `spark.sql.ansi.enabled = false` (Fabric's
default — see the root `CLAUDE.md` gotcha, and `tests/conftest.py`, which pins
the same setting locally). A malformed row that would have failed the whole
dataflow refresh now yields a NULL `Date` and is visible to the data-quality
checks. Out-of-range cases, all of which produce NULL:

  * raw year outside 2001..2031  -> corrected day outside 1..31
  * raw day 0 or > 31            -> impossible in a stored date, but a NULL raw
                                    date propagates
  * a valid-looking combination that is not a real calendar date, e.g. raw
    `2029-02-23` -> `2023-02-29` (2023 is not a leap year)

Note that corrected year 2000 is structurally unrepresentable: it requires a raw
day of 0.
"""

from pyspark.sql import DataFrame, functions as F


# The offset that separates the two halves of the swap: the raw day-of-month is
# a two-digit year (24 -> 2024) and the raw year is a day-of-month offset from
# 2000 (2015 -> 15). Same constant on both sides, exactly as in the mashup.
DATE_SWAP_EPOCH = 2000

# The column the correction is applied to, in bronze_procurement_transactional.
PROCUREMENT_DATE_COLUMN = "Date"


def correct_procurement_date(df: DataFrame, column: str = "Date") -> DataFrame:
    """
    Undo the source system's day/year transposition on a procurement date column.

    Replaces `column` in place (preserving its position, matching the retired
    mashup's add/drop/rename sequence) with
    `make_date(day(raw) + 2000, month(raw), year(raw) - 2000)`.

    Args:
        df: a DataFrame carrying the raw bronze procurement date column.
        column: the column to correct. Defaults to "Date", the bronze name.

    Returns:
        The DataFrame with `column` replaced by the corrected DateType value.
        Rows whose corrected components do not form a real calendar date — and
        rows whose raw date is NULL — yield NULL rather than raising, matching
        Fabric's non-ANSI cast semantics.

    Note:
        `to_date` is applied first so the function is indifferent to whether the
        Copy activity landed bronze `Date` as a Spark date or as a string; both
        produce identical output.
    """
    raw = F.to_date(F.col(column))
    return df.withColumn(
        column,
        F.make_date(
            F.dayofmonth(raw) + F.lit(DATE_SWAP_EPOCH),
            F.month(raw),
            F.year(raw) - F.lit(DATE_SWAP_EPOCH),
        ),
    )
