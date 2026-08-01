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


# =============================================================================
# HHI aggregation — gold_supply_risk (task-038_4)
# spec_v1 § Business Logic & Calculations -> Supply Risk (DEC-001 Option B)
# =============================================================================
#   HHI_WGI,t = Σ_c (Sᶜ)² · WGIᶜ · tᶜ
#
# This block owns the AGGREGATION half of the supply-risk model — the per-mix
# HHI, the contrast_ratio, the bottleneck flag and the WGI-coverage flag. The
# per-country weight WGIᶜ is task-038_3 (above); this consumes it from
# fact_supply_share and never recomputes it.
#
# MIRRORED IN fabric/silver-to-gold2.Notebook (DEC-002). tests/test_supply_risk.py
# loads the notebook's own FunctionDefs and pins them against these src/
# versions — editing one side without the other fails CI by design.
#
# THE GRAIN IS material × stage × year (spec § Data Architecture → gold_supply_risk,
# § Business Logic & Calculations → Supply Risk). Both stages are retained and the
# bottleneck is FLAGGED rather than collapsed, so the extraction-vs-processing
# comparison stays available to the report while the headline figure needs no
# DAX ranking pattern.


def supply_risk_contribution(share_pct, wgi_weight, t):
    """The per-country contribution `(Sᶜ)² · WGIᶜ · tᶜ` as a Spark Column.

    `Sᶜ = share_pct / 100` — the FRACTION, not the 0-100 percentage. share_pct is
    stored 0-100 on fact_supply_share, so squaring the wrong scale silently
    inflates the index by 10^4 and produces a plausible-looking but wrong number;
    a parity test pins the division by 100 explicitly. `t` is the DEC-001 trade
    parameter (0.8 EU, 1.0 baseline non-EU, >1 export-restricted) and is nullable
    on the fact — a NULL t yields a NULL contribution, which F.sum skips, so a
    row with no trade parameter is excluded from the sum rather than zeroed.

    Accepts column names (str) or Column expressions for all three arguments, so
    the HHI aggregation can name its inputs either way.
    """
    def _col(x):
        return F.col(x) if isinstance(x, str) else x

    share_frac = _col(share_pct) / F.lit(100.0)
    return (share_frac * share_frac) * _col(wgi_weight) * _col(t)


def compute_gold_supply_risk(fact_supply_share: DataFrame,
                             dim_country: DataFrame) -> DataFrame:
    """
    Build the `gold_supply_risk` table content from `fact_supply_share`.

    Spec: § Business Logic & Calculations → Supply Risk (DEC-001 Option B) +
    § Data Architecture → gold_supply_risk.

    Grain: one row per `(material_key, stage_key, year)`. Both stages (E/P) are
    retained; the bottleneck is FLAGGED (`is_bottleneck`) rather than collapsed,
    so the extraction-vs-processing comparison stays available to the report.

    Output columns:
      hhi_global              Σ_c (Sᶜ)²·WGIᶜ·tᶜ over supply_mix='global'
      hhi_eu_sourcing         same over supply_mix='eu_sourcing'; NULL when the
                              material × stage × year has no EU sourcing rows
                              (the EU coverage gap — never 0)
      contrast_ratio          hhi_eu_sourcing / hhi_global; NULL when hhi_global
                              is 0 or NULL, or when hhi_eu_sourcing is NULL
                              (never 0 — 0 is a legitimate "perfectly diffuse"
                              index value and must not be conflated with "no EU
                              data")
      is_bottleneck           BOOLEAN — the stage with the HIGHER hhi_global per
                              material × year. Driven by hhi_global ONLY (not
                              hhi_eu_sourcing, not max of the two) so it stays
                              defined when EU coverage is missing. Strict: a
                              tie flags neither stage. NULL hhi_global never wins.
      incomplete_wgi_coverage BOOLEAN — TRUE when any supplier row for this
                              material × stage × year was excluded due to NULL
                              wgi_weight (e.g. TWN — World Bank publishes no WGI
                              for Taiwan, ever; or a placeholder bucket). The
                              HHI is then computed over the governance-known
                              subset only, which UNDERSTATES risk for
                              Taiwan-heavy materials. The flag makes that gap
                              VISIBLE rather than silent; it is an accepted,
                              documented tradeoff, not a bug.

    NULL RULES (each is pinned by a test):
      1. NULL wgi_weight rows are EXCLUDED from the Σ_c sum — never coerced to 0.
         0.0 is a legitimate weight meaning *best governance*, so coercing NULL
         to 0 would read as a perfectly-governed country and silently re-rank
         every material. `F.greatest`/`F.least` IGNORE nulls and would swallow
         them the way task-038_3 found; the `.filter(wgi_weight.isNotNull())`
         guard is explicit.
      2. Placeholder countries (gold_dim_country.is_placeholder = TRUE, e.g.
         UNK_GLOB) are excluded from the country-level HHI sum regardless of
         their weight — a placeholder is a bucket, not a country. The weight is
         NULL by construction but the guard is defensive.
      3. EU coverage gap (global rows exist, no eu_sourcing rows) →
         hhi_eu_sourcing = NULL, contrast_ratio = NULL — never 0.
      4. hhi_global = 0 → contrast_ratio = NULL, never 0.

    Args:
        fact_supply_share: the written fact, carrying at least material_key,
            stage_key, country_key, year, supply_mix, share_pct, t, wgi_weight.
        dim_country: gold_dim_country — joined for is_placeholder (not carried
            on the fact). Needs country_key, is_placeholder.

    Returns:
        DataFrame at grain (material_key, stage_key, year) with the five output
        columns above, in that order.
    """
    # Bring is_placeholder onto the fact — it is not carried on fact_supply_share,
    # only on gold_dim_country. LEFT so a fact row whose country_key is missing
    # from the dim (should not happen post-silver, but defensive) keeps its
    # supply row and is excluded by the wgi_weight filter rather than dropped here.
    fs = fact_supply_share.join(
        dim_country.select("country_key", "is_placeholder"),
        "country_key", "left",
    )

    contribution = supply_risk_contribution("share_pct", "wgi_weight", "t")

    # HHI per (material × stage × year × supply_mix), summed over the
    # governance-known, non-placeholder subset only. NULL wgi_weight rows are
    # excluded, NOT zeroed (rule 1). Placeholders excluded by rule 2.
    per_mix = (
        fs
        .filter(F.col("wgi_weight").isNotNull())
        .filter(~F.coalesce(F.col("is_placeholder"), F.lit(False)))
        .groupBy("material_key", "stage_key", "year", "supply_mix")
        .agg(F.sum(contribution).alias("hhi"))
    )

    hhi_global = (
        per_mix.filter(F.col("supply_mix") == "global")
        .select("material_key", "stage_key", "year", F.col("hhi").alias("hhi_global"))
    )
    hhi_eu = (
        per_mix.filter(F.col("supply_mix") == "eu_sourcing")
        .select("material_key", "stage_key", "year", F.col("hhi").alias("hhi_eu_sourcing"))
    )

    # The grain is every (material × stage × year) appearing in EITHER mix. A
    # material present in global but absent from eu_sourcing (the EU coverage
    # gap) still gets a row, with hhi_eu_sourcing = NULL (rule 3). The reverse
    # is symmetric — a key with only EU rows gets hhi_global = NULL. Starting
    # from `fs` (pre-filter) rather than `per_mix` (post-filter) means a key
    # whose only rows were all-NULL-wgi still appears, with both HHIs NULL and
    # incomplete_wgi_coverage = TRUE.
    grain_keys = (
        fs.select("material_key", "stage_key", "year").distinct()
    )

    result = (
        grain_keys
        .join(hhi_global, ["material_key", "stage_key", "year"], "left")
        .join(hhi_eu, ["material_key", "stage_key", "year"], "left")
    )

    # contrast_ratio (rules 3 + 4): NULL when hhi_global is NULL or 0, or when
    # hhi_eu_sourcing is NULL. The `F.when` guard is what keeps 0/0 from returning
    # a sentinel; in ANSI-off mode 0/0 is NULL anyway, but the explicit guard is
    # readable and survives an ANSI-on regression.
    result = result.withColumn(
        "contrast_ratio",
        F.when(
            (F.col("hhi_global").isNotNull())
            & (F.col("hhi_global") != F.lit(0.0))
            & (F.col("hhi_eu_sourcing").isNotNull()),
            F.col("hhi_eu_sourcing") / F.col("hhi_global"),
        ),
    )

    # incomplete_wgi_coverage (rule 1 visibility): TRUE when any supplier row for
    # this material × stage × year was excluded due to NULL wgi_weight. Computed
    # across BOTH mixes — wgi_weight is a country property, not a mix property,
    # so the gap is the same in either. A placeholder bucket (UNK_GLOB) also
    # carries NULL wgi_weight and is flagged here; that is correct — the index
    # for that key IS computed over an incomplete governance subset.
    excluded = (
        fs
        .filter(F.col("wgi_weight").isNull())
        .groupBy("material_key", "stage_key", "year")
        .agg(F.count(F.lit(1)).alias("_n_excluded"))
    )
    result = (
        result
        .join(excluded, ["material_key", "stage_key", "year"], "left")
        .withColumn(
            "incomplete_wgi_coverage",
            F.col("_n_excluded").isNotNull() & (F.col("_n_excluded") > 0),
        )
        .drop("_n_excluded")
    )

    # is_bottleneck: the stage with the HIGHER hhi_global per material × year.
    # Driven by hhi_global ONLY (spec: "not by hhi_eu_sourcing or the max of the
    # two") so it stays defined when EU coverage is missing. Strict comparison —
    # a tie flags NEITHER stage; NULL hhi_global never wins. Implemented without
    # a Window so the parity harness (which compiles only these FunctionDefs in
    # a namespace holding `F` alone) needs no extra imports.
    maxes = (
        result
        .filter(F.col("hhi_global").isNotNull())
        .groupBy("material_key", "year")
        .agg(F.max("hhi_global").alias("_max_hhi"))
    )
    at_max = (
        result
        .filter(F.col("hhi_global").isNotNull())
        .join(maxes, ["material_key", "year"], "inner")
        .filter(F.col("hhi_global") == F.col("_max_hhi"))
        .groupBy("material_key", "year")
        .agg(F.count(F.lit(1)).alias("_n_at_max"))
    )
    result = (
        result
        .join(maxes, ["material_key", "year"], "left")
        .join(at_max, ["material_key", "year"], "left")
        .withColumn(
            "is_bottleneck",
            (F.col("hhi_global").isNotNull())
            & (F.col("hhi_global") == F.col("_max_hhi"))
            & (F.col("_n_at_max") == F.lit(1)),
        )
        .drop("_max_hhi", "_n_at_max")
    )

    return result.select(
        "material_key", "stage_key", "year",
        "hhi_global", "hhi_eu_sourcing", "contrast_ratio",
        "is_bottleneck", "incomplete_wgi_coverage",
    )
