"""
Supply Risk Transformations — the governance weight WGIᶜ

Implements the governance-weight half of the supply-risk model defined in
spec_v1 § Business Logic & Calculations → Supply Risk (DEC-001 Option B):

    HHI_WGI,t = Σ_c (Sᶜ)² · WGIᶜ · tᶜ

    WGIᶜ = clamp( (2.5 − mean₆(WGI estimates for c, latest year available)) / 5 , 0, 1 )

This module owns `WGIᶜ` only — the per-country weight and its join onto
`fact_supply_share`. The HHI aggregation itself (`gold_supply_risk`,
`contrast_ratio`, `is_bottleneck`) is task-038_4 and extends this module; the
function seam below is deliberately split so that work adds aggregation
functions without re-opening the weight computation.

REFERENCE IMPLEMENTATION — NOT IMPORTED BY THE NOTEBOOKS (DEC-002 / task-032)
----------------------------------------------------------------------------
Same contract as `key_generation.py` and `data_quality.py`: the Fabric notebooks
define this logic inline and import nothing from `src/`. This module is the
documented REFERENCE implementation and the duplication is guarded by parity
tests rather than by convention.

Production counterparts, per function — all in
`fabric/silver-to-gold2.Notebook/notebook-content.py`, in the cell that builds
`fact_supply_share`:

  - wgi_weight_expr              -> inline, same name
  - compute_wgi_weight           -> inline, same name
  - map_wgi_weight_to_country_key-> inline, same name
  - attach_wgi_weight            -> inline, same name

**If you change a function here, change the notebook to match (or vice versa).**
`tests/test_supply_risk.py::TestNotebookParity` loads the notebook's own
definitions and fails on divergence.

TWO CONSTANTS THAT MUST NOT BECOME DATA-DERIVED
-----------------------------------------------
`estimate_min` / `estimate_max` are the FIXED theoretical bounds of the World
Bank governance-estimate scale (−2.5..+2.5). They are function defaults, never
`F.min(...)` / `F.max(...)` over the loaded set. Spec line: *"Rescaling uses the
fixed theoretical bounds ... not the observed min/max of the loaded set. This is
a reproducibility requirement: with observed bounds, adding a country or a new
WGI vintage silently re-ranks every material."* Making them defaults (rather
than module constants read from the enclosing scope) is deliberate — it keeps
the spec values travelling inside the FunctionDef, so the parity harness, which
compiles the notebook's FunctionDef nodes in a fresh namespace, compares the
real values instead of values injected by the test.
"""

from pyspark.sql import Column, DataFrame, functions as F

# Named for readability at call sites and in the docs. The authoritative copies
# live in the function signatures below — see the module docstring.
WGI_ESTIMATE_MIN = -2.5
WGI_ESTIMATE_MAX = 2.5
WGI_DIMENSIONS_REQUIRED = 6


def wgi_weight_expr(mean_estimate, estimate_min=-2.5, estimate_max=2.5) -> Column:
    """
    The spec's clamp formula as a Spark Column expression.

        WGIᶜ = clamp( (2.5 − mean₆) / 5 , 0, 1 )

    where `5` is the FIXED span `estimate_max − estimate_min` of the World Bank
    estimate scale, not a data-derived range.

    THE INVERSION IS THE POINT. Raw WGI runs ≈ −2.5..+2.5 with *higher = better*
    governance. `(estimate_max − mean)` flips it so the output is `0 = best
    governance, 1 = worst`, which is the direction the HHI multiplier needs. An
    un-inverted index still computes and still looks plausible while ranking
    every material backwards — `tests/test_supply_risk.py::TestInversion` pins
    the direction for exactly that reason.

    NULL HANDLING — NOT COSMETIC. `F.greatest` / `F.least` IGNORE nulls and
    return the greatest/least non-null argument, so a naive
    `least(greatest(raw, 0), 1)` maps a NULL mean to **0.0** — i.e. "perfect
    governance" for a country with no data. The `F.when(...isNotNull())`
    wrapper (no `.otherwise`, so the else branch is NULL) is what keeps an
    unknown country unknown instead of silently best-in-class.

    Args:
        mean_estimate: Column (or column name) holding mean₆ for the country.
        estimate_min: Lower theoretical bound of the WGI estimate scale.
        estimate_max: Upper theoretical bound of the WGI estimate scale.

    Returns:
        Column: the weight in 0..1, or NULL where `mean_estimate` is NULL.
    """
    mean_col = F.col(mean_estimate) if isinstance(mean_estimate, str) else mean_estimate
    span = estimate_max - estimate_min  # 5.0 for the spec'd bounds
    raw = (F.lit(estimate_max) - mean_col) / F.lit(span)
    clamped = F.least(F.greatest(raw, F.lit(0.0)), F.lit(1.0))
    return F.when(mean_col.isNotNull(), clamped)


def compute_wgi_weight(
    silver_wgi: DataFrame,
    required_dimensions: int = 6,
    estimate_min: float = -2.5,
    estimate_max: float = 2.5,
) -> DataFrame:
    """
    Compute WGIᶜ per country from the long-format `silver_wgi`.

    Input grain (task-031/task-035): one row per
    (country_iso3, indicator_name, year) carrying `value`, the World Bank
    ESTIMATE (−2.5..+2.5) — NOT a percentile rank. Rows with a NULL `value` are
    already dropped at silver; the filter here is defensive so the function is
    correct standalone.

    COMPLETENESS RULE (acceptance criterion 4) — the mean is over ALL SIX WGI
    dimensions, never a partial mean:

      `wgi_year` is the LATEST year for which the country has the full set of
      `required_dimensions` distinct indicators. A country whose most recent
      year is incomplete falls back to its most recent COMPLETE year rather
      than averaging whatever subset that year happens to carry. A country with
      no complete year in any vintage gets `wgi_year = NULL`,
      `wgi_mean_estimate = NULL` and `wgi_weight = NULL` — it is reported as a
      coverage gap, not given an averaged-over-four-dimensions number that
      would be indistinguishable from a real one downstream.

      `wgi_dimensions_available` is diagnostic: the dimension count at
      `wgi_year` when a complete year exists, otherwise the best count the
      country reaches in ANY single year (so "5 of 6, one dimension missing"
      is distinguishable from "country absent from WGI entirely").

    DELIBERATE DIVERGENCE FROM THE DATA-GAPS COVERAGE FLAG. `create_data_gaps_table`
    in the same notebook counts a country as governance-covered when it has
    `COUNT(DISTINCT indicator_name) >= WGI_REQUIRED_INDICATORS` across ALL years
    — vintage-agnostic by design, because that flag answers "do we hold
    governance data for this country at all?". WGIᶜ needs the six dimensions in
    ONE year, because a mean mixing 2019's rule-of-law with 2023's voice-and-
    accountability is not a measurement of any year. The two rules therefore
    differ on purpose (a country with six dimensions spread across years counts
    as covered there and as a gap here), and the divergence is documented rather
    than reconciled by weakening either rule. The coverage flag is NOT modified
    by this task.

    Args:
        silver_wgi: DataFrame with country_iso3, indicator_name, year, value.
        required_dimensions: Distinct WGI dimensions a year must carry to be
            usable. Six is the full World Bank set fetched by
            `bronze_ingest_wgi` (CC/GE/PV/RL/RQ/VA) and matches
            `WGI_REQUIRED_INDICATORS` in the notebook's coverage rule. `>=`
            rather than `==` mirrors that rule's phrasing.
        estimate_min: Fixed lower bound of the estimate scale. See module docstring.
        estimate_max: Fixed upper bound of the estimate scale. See module docstring.

    Returns:
        DataFrame: one row per country_iso3 present in `silver_wgi`, with
        columns country_iso3, wgi_year, wgi_dimensions_available,
        wgi_mean_estimate, wgi_weight.
    """
    observed = (
        silver_wgi
        .filter(F.col("value").isNotNull())
        # Silver already dedupes on (country_iso3, indicator_code, year) and
        # asserts indicator_name <-> indicator_code is 1:1, so this is a no-op
        # today. It is here so `F.avg` is provably a mean over DISTINCT
        # dimensions rather than a mean over rows: if silver ever fanned out, an
        # undetected duplicate would silently re-weight one dimension.
        .dropDuplicates(["country_iso3", "indicator_name", "year"])
        .groupBy("country_iso3", "year")
        .agg(
            F.countDistinct("indicator_name").alias("dimensions_available"),
            F.avg("value").alias("mean_estimate"),
        )
    )

    # Latest COMPLETE year per country, in one pass. F.max over a struct orders
    # lexicographically by its first field (year), and F.max ignores NULLs — so
    # the F.when yields the newest year that reached the required dimension
    # count, or NULL when the country never does. `year` is unique within a
    # country group here (observed is grouped by country x year), so the
    # remaining struct fields never act as tie-breaks; they ride along to avoid
    # a self-join back onto `observed`.
    latest_complete = F.max(
        F.when(
            F.col("dimensions_available") >= F.lit(required_dimensions),
            F.struct(
                F.col("year").alias("year"),
                F.col("dimensions_available").alias("dimensions_available"),
                F.col("mean_estimate").alias("mean_estimate"),
            ),
        )
    ).alias("_latest")

    return (
        observed
        .groupBy("country_iso3")
        .agg(latest_complete, F.max("dimensions_available").alias("_best_dimensions"))
        .select(
            F.col("country_iso3"),
            F.col("_latest.year").alias("wgi_year"),
            F.coalesce(
                F.col("_latest.dimensions_available"), F.col("_best_dimensions")
            ).alias("wgi_dimensions_available"),
            F.col("_latest.mean_estimate").alias("wgi_mean_estimate"),
            wgi_weight_expr(
                F.col("_latest.mean_estimate"), estimate_min, estimate_max
            ).alias("wgi_weight"),
        )
    )


def map_wgi_weight_to_country_key(
    wgi_weight: DataFrame, dim_country: DataFrame
) -> DataFrame:
    """
    Re-key the per-ISO3 weight onto `country_key`, the fact tables' country grain.

    The join predicate mirrors the one the notebook's WGI coverage rule already
    uses (`sw.country_iso3 = UPPER(dc.iso3)`) so the two cannot drift apart.
    `silver_wgi.country_iso3` is already UPPER+TRIM'd at silver, so only the
    dimension side needs normalising.

    INNER join on purpose: a WGI country with no `gold_dim_country` row has no
    fact rows either, so carrying it forward would only add unjoinable noise.
    The gap that matters — a dim country with no WGI weight — is created by the
    LEFT join in `attach_wgi_weight` and measured there.

    The result is expected to be unique on `country_key` (country_key is a
    function of iso3 alone, and `gold_dim_country` is deduped on country_key),
    but this function does not enforce it: the notebook asserts uniqueness at
    the call site, where a failure can name the offending keys and stop the run
    before the fact fans out.

    Args:
        wgi_weight: Output of `compute_wgi_weight`.
        dim_country: `gold_dim_country` (needs country_key, iso3).

    Returns:
        DataFrame: country_key, wgi_year, wgi_weight.
    """
    return (
        wgi_weight.alias("w")
        .join(
            dim_country.alias("dc"),
            F.col("w.country_iso3") == F.upper(F.col("dc.iso3")),
            "inner",
        )
        .select(
            F.col("dc.country_key").alias("country_key"),
            F.col("w.wgi_year").alias("wgi_year"),
            F.col("w.wgi_weight").alias("wgi_weight"),
        )
    )


def attach_wgi_weight(fact_df: DataFrame, wgi_by_country_key: DataFrame) -> DataFrame:
    """
    LEFT-join the governance weight onto a fact keyed by `country_key`.

    LEFT, never INNER: a country with no usable WGI vintage must keep its supply
    rows and surface as a measured coverage gap (`wgi_weight IS NULL`, counted
    by `check_unmapped`), because dropping it would silently shrink the supply
    base the HHI is computed over and make a material look less concentrated
    than it is.

    The original column order is preserved and the two new columns are appended,
    so the written table's layout stays stable for readers (a join on a column
    name list would otherwise promote `country_key` to position 0).

    Args:
        fact_df: Fact with a `country_key` column (e.g. fact_supply_share).
        wgi_by_country_key: Output of `map_wgi_weight_to_country_key`.

    Returns:
        DataFrame: `fact_df` plus `wgi_year` and `wgi_weight`.
    """
    original_columns = fact_df.columns
    joined = fact_df.join(wgi_by_country_key, "country_key", "left")
    return joined.select(*original_columns, "wgi_year", "wgi_weight")
