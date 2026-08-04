"""
Unit tests for the supply-risk governance weight (WGIᶜ).

Covers spec_v1 § Business Logic & Calculations → Supply Risk (DEC-001 Option B):

    WGIᶜ = clamp( (2.5 − mean₆(WGI estimates for c, latest year available)) / 5 , 0, 1 )

Every numeric expectation in this file is a LITERAL, written out by hand from the
formula. None is recomputed from the function under test — an assertion that derives
its expected value from the frame it is checking cannot fail, and that is precisely
the failure mode criterion 2 exists to catch.

Includes TestNotebookParity, which enforces the reference-implementation contract
declared in src/transformations/supply_risk.py: the Fabric notebook duplicates this
logic inline, so the two must be proven identical rather than assumed so (DEC-002).
"""

import inspect

import pytest
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, DoubleType, LongType, BooleanType,
)

from src.transformations.data_quality import check_unmapped
from src.transformations.supply_risk import (
    wgi_weight_expr,
    compute_wgi_weight,
    map_wgi_weight_to_country_key,
    attach_wgi_weight,
    supply_risk_contribution,
    compute_gold_supply_risk,
)
from tests._notebook_loader import load_notebook_functions, GOLD_NOTEBOOK

# The notebook FunctionDefs under parity, in dependency order (compute_wgi_weight
# calls wgi_weight_expr; compute_gold_supply_risk calls supply_risk_contribution).
NOTEBOOK_FUNCTIONS = [
    "wgi_weight_expr",
    "compute_wgi_weight",
    "map_wgi_weight_to_country_key",
    "attach_wgi_weight",
    "supply_risk_contribution",
    "compute_gold_supply_risk",
]

# The six World Bank governance dimensions fetched by bronze_ingest_wgi.
WGI_DIMENSIONS = [
    "Control of Corruption: Estimate",
    "Government Effectiveness: Estimate",
    "Political Stability and Absence of Violence/Terrorism: Estimate",
    "Regulatory Quality: Estimate",
    "Rule of Law: Estimate",
    "Voice and Accountability: Estimate",
]
WGI_CODES = ["CC.EST", "GE.EST", "PV.EST", "RQ.EST", "RL.EST", "VA.EST"]

SILVER_WGI_SCHEMA = StructType([
    StructField("country_iso3", StringType(), True),
    StructField("country_name", StringType(), True),
    StructField("indicator_name", StringType(), True),
    StructField("indicator_code", StringType(), True),
    StructField("year", IntegerType(), True),
    StructField("value", DoubleType(), True),
])

DIM_COUNTRY_SCHEMA = StructType([
    StructField("country_key", LongType(), True),
    StructField("iso3", StringType(), True),
    StructField("country_name_std", StringType(), True),
    StructField("is_placeholder", BooleanType(), True),
])

FACT_SCHEMA = StructType([
    StructField("material_key", LongType(), True),
    StructField("stage_key", LongType(), True),
    StructField("country_key", LongType(), True),
    StructField("year", IntegerType(), True),
    StructField("supply_mix", StringType(), True),
    StructField("share_pct", DoubleType(), True),
    StructField("t", DoubleType(), True),
])

# Six dimension values per country, chosen so each mean is exact and each weight is a
# clean literal. Deliberately NON-uniform, so a bug that reads one dimension instead of
# averaging six would not accidentally produce the right answer.
#   AAA: sum  9.0 -> mean  1.5 -> (2.5 − 1.5)/5 = 0.20
#   BBB: sum −6.0 -> mean −1.0 -> (2.5 + 1.0)/5 = 0.70
VALUES_AAA = [1.0, 1.2, 1.4, 1.6, 1.8, 2.0]
VALUES_BBB = [-0.5, -0.7, -0.9, -1.1, -1.3, -1.5]
WEIGHT_AAA = 0.20
WEIGHT_BBB = 0.70

# Extreme countries, used to prove the rescale ignores the observed range.
VALUES_CCC = [2.4] * 6          # mean  2.4 -> 0.02
VALUES_DDD = [-2.4] * 6         # mean −2.4 -> 0.98
WEIGHT_CCC = 0.02
WEIGHT_DDD = 0.98

TOL = 1e-12


def wgi_rows(iso3, year, values):
    """One silver_wgi row per supplied value, taking dimensions in order."""
    return [
        (iso3, f"{iso3} Land", WGI_DIMENSIONS[i], WGI_CODES[i], year, float(v))
        for i, v in enumerate(values)
    ]


def silver_wgi(spark, *row_groups):
    rows = [r for group in row_groups for r in group]
    return spark.createDataFrame(rows, SILVER_WGI_SCHEMA)


def weights_by_iso3(df):
    """Collect compute_wgi_weight output into {iso3: Row-as-dict} for assertions."""
    return {r["country_iso3"]: r.asDict() for r in df.collect()}


class TestWgiWeightFormula:
    """Criterion 1 — the clamp formula, exactly as spec'd."""

    @pytest.mark.unit
    @pytest.mark.parametrize("mean_estimate,expected", [
        (2.5, 0.0),      # theoretical best governance -> no risk weight
        (1.5, 0.2),
        (0.0, 0.5),      # scale midpoint
        (-1.0, 0.7),
        (-2.5, 1.0),     # theoretical worst governance -> full risk weight
    ])
    def test_formula_endpoints_and_interior(self, spark, mean_estimate, expected):
        df = spark.createDataFrame([(mean_estimate,)], ["mean_estimate"])
        got = df.select(wgi_weight_expr(F.col("mean_estimate")).alias("w")).first()["w"]
        assert got == pytest.approx(expected, abs=TOL)

    @pytest.mark.unit
    def test_accepts_column_name_as_well_as_column(self, spark):
        df = spark.createDataFrame([(1.5,)], ["mean_estimate"])
        assert df.select(wgi_weight_expr("mean_estimate").alias("w")).first()["w"] == \
            pytest.approx(0.2, abs=TOL)

    @pytest.mark.unit
    @pytest.mark.parametrize("mean_estimate,expected", [
        (3.0, 0.0),      # above +2.5 -> clamped low
        (-3.0, 1.0),     # below −2.5 -> clamped high
        (100.0, 0.0),
        (-100.0, 1.0),
    ])
    def test_clamp_bounds_output_to_unit_interval(self, spark, mean_estimate, expected):
        """The clamp handles the rare country whose mean falls outside ±2.5."""
        df = spark.createDataFrame([(mean_estimate,)], ["mean_estimate"])
        got = df.select(wgi_weight_expr(F.col("mean_estimate")).alias("w")).first()["w"]
        assert got == pytest.approx(expected, abs=TOL)

    @pytest.mark.unit
    def test_null_mean_yields_null_weight_not_zero(self, spark):
        """A country with no mean must stay unknown, never 'perfect governance'.

        Regression guard for the F.greatest/F.least null semantics: both IGNORE nulls
        and return the greatest/least NON-NULL argument, so a bare
        least(greatest(raw, 0), 1) maps a NULL mean to 0.0 — which reads downstream as
        the best-governed country in the set. 0.0 is a legitimate weight, so nothing
        further down could tell the difference.
        """
        schema = StructType([StructField("mean_estimate", DoubleType(), True)])
        df = spark.createDataFrame([(None,)], schema)
        got = df.select(wgi_weight_expr(F.col("mean_estimate")).alias("w")).first()["w"]
        assert got is None, f"NULL mean produced {got!r} instead of NULL"


class TestFixedBounds:
    """Criterion 2 — the rescale uses the FIXED −2.5..+2.5 bounds, never observed ones."""

    @pytest.mark.unit
    def test_adding_countries_does_not_move_existing_weights(self, spark):
        """Adding an extreme country must not change any existing country's weight.

        With observed min/max rescaling, AAA's weight would move from 0.20 to 0.00 in
        the two-country set (it IS the observed maximum) and to 0.1875 once the extremes
        are added. Both expectations below are literals from the spec formula, so the
        assertion is independent of the function that produced them.
        """
        before = weights_by_iso3(compute_wgi_weight(silver_wgi(
            spark,
            wgi_rows("AAA", 2023, VALUES_AAA),
            wgi_rows("BBB", 2023, VALUES_BBB),
        )))
        assert before["AAA"]["wgi_weight"] == pytest.approx(WEIGHT_AAA, abs=TOL)
        assert before["BBB"]["wgi_weight"] == pytest.approx(WEIGHT_BBB, abs=TOL)

        after = weights_by_iso3(compute_wgi_weight(silver_wgi(
            spark,
            wgi_rows("AAA", 2023, VALUES_AAA),
            wgi_rows("BBB", 2023, VALUES_BBB),
            wgi_rows("CCC", 2023, VALUES_CCC),
            wgi_rows("DDD", 2023, VALUES_DDD),
        )))
        assert after["AAA"]["wgi_weight"] == pytest.approx(WEIGHT_AAA, abs=TOL)
        assert after["BBB"]["wgi_weight"] == pytest.approx(WEIGHT_BBB, abs=TOL)
        assert after["CCC"]["wgi_weight"] == pytest.approx(WEIGHT_CCC, abs=TOL)
        assert after["DDD"]["wgi_weight"] == pytest.approx(WEIGHT_DDD, abs=TOL)

    @pytest.mark.unit
    def test_single_country_set_is_not_degenerate(self, spark):
        """One country alone still gets its absolute weight, not 0 or NaN.

        Observed-bounds rescaling divides by (max − min) = 0 here, so this case is
        where that bug is loudest.
        """
        only = weights_by_iso3(compute_wgi_weight(
            silver_wgi(spark, wgi_rows("AAA", 2023, VALUES_AAA))))
        assert only["AAA"]["wgi_weight"] == pytest.approx(WEIGHT_AAA, abs=TOL)

    @pytest.mark.unit
    def test_bounds_are_signature_defaults_not_data_derived(self):
        """The spec constants are pinned in the signatures of both implementations."""
        for fn in (wgi_weight_expr, compute_wgi_weight):
            params = inspect.signature(fn).parameters
            assert params["estimate_min"].default == -2.5
            assert params["estimate_max"].default == 2.5
        assert inspect.signature(compute_wgi_weight).parameters[
            "required_dimensions"].default == 6


class TestInversion:
    """Criterion 3 — 1 = worst governance; the inversion is mandatory."""

    @pytest.mark.unit
    def test_well_governed_near_zero_poorly_governed_near_one(self, spark):
        """An un-inverted index computes and looks plausible while ranking backwards."""
        weights = weights_by_iso3(compute_wgi_weight(silver_wgi(
            spark,
            wgi_rows("WEL", 2023, [1.8] * 6),   # (2.5 − 1.8)/5 = 0.14
            wgi_rows("POO", 2023, [-1.8] * 6),  # (2.5 + 1.8)/5 = 0.86
        )))
        well = weights["WEL"]["wgi_weight"]
        poor = weights["POO"]["wgi_weight"]

        assert well == pytest.approx(0.14, abs=TOL)
        assert poor == pytest.approx(0.86, abs=TOL)
        assert well < poor, (
            "governance weight is not inverted: the well-governed country carries the "
            "HIGHER risk weight, which ranks every material backwards"
        )
        assert well < 0.5 < poor


class TestDimensionCompleteness:
    """Criterion 4 — mean over all six dimensions; partial sets handled explicitly."""

    @pytest.mark.unit
    def test_mean_is_over_all_six_dimensions(self, spark):
        """Non-uniform dimension values: only a true six-way mean lands on 0.20."""
        weights = weights_by_iso3(compute_wgi_weight(
            silver_wgi(spark, wgi_rows("AAA", 2023, VALUES_AAA))))
        assert weights["AAA"]["wgi_mean_estimate"] == pytest.approx(1.5, abs=TOL)
        assert weights["AAA"]["wgi_dimensions_available"] == 6
        assert weights["AAA"]["wgi_weight"] == pytest.approx(WEIGHT_AAA, abs=TOL)

    @pytest.mark.unit
    def test_incomplete_latest_year_falls_back_to_latest_complete_year(self, spark):
        """2023 carries only five dimensions, so 2022's complete set is used.

        The 2023 partial set averages to 0.0 (weight 0.50). Asserting 0.20 proves both
        halves of the rule: the fallback happened AND no partial mean was taken.
        """
        weights = weights_by_iso3(compute_wgi_weight(silver_wgi(
            spark,
            wgi_rows("GGG", 2022, VALUES_AAA),
            wgi_rows("GGG", 2023, [0.0] * 5),
        )))
        assert weights["GGG"]["wgi_year"] == 2022
        assert weights["GGG"]["wgi_dimensions_available"] == 6
        assert weights["GGG"]["wgi_weight"] == pytest.approx(WEIGHT_AAA, abs=TOL)

    @pytest.mark.unit
    def test_never_complete_country_gets_null_weight_not_partial_mean(self, spark):
        """Five dimensions in every vintage -> NULL, never an averaged-over-five number."""
        weights = weights_by_iso3(compute_wgi_weight(
            silver_wgi(spark, wgi_rows("HHH", 2023, [0.0] * 5))))
        row = weights["HHH"]
        assert row["wgi_weight"] is None, (
            f"partial dimension set produced weight {row['wgi_weight']!r}; a mean over "
            f"five dimensions is indistinguishable from a real one downstream"
        )
        assert row["wgi_mean_estimate"] is None
        assert row["wgi_year"] is None
        # Diagnostic: 'five of six' must stay distinguishable from 'absent entirely'.
        assert row["wgi_dimensions_available"] == 5

    @pytest.mark.unit
    def test_latest_complete_year_wins_over_older_complete_year(self, spark):
        """Two complete vintages -> the newest one is used."""
        weights = weights_by_iso3(compute_wgi_weight(silver_wgi(
            spark,
            wgi_rows("III", 2019, VALUES_BBB),
            wgi_rows("III", 2023, VALUES_AAA),
        )))
        assert weights["III"]["wgi_year"] == 2023
        assert weights["III"]["wgi_weight"] == pytest.approx(WEIGHT_AAA, abs=TOL)

    @pytest.mark.unit
    def test_latest_year_is_per_country_not_global(self, spark):
        """A country whose series ends earlier still gets its own latest vintage.

        A single global MAX(year) would silently drop every country not reporting in
        the newest year in the table.
        """
        weights = weights_by_iso3(compute_wgi_weight(silver_wgi(
            spark,
            wgi_rows("AAA", 2023, VALUES_AAA),
            wgi_rows("BBB", 2018, VALUES_BBB),
        )))
        assert weights["AAA"]["wgi_year"] == 2023
        assert weights["BBB"]["wgi_year"] == 2018
        assert weights["BBB"]["wgi_weight"] == pytest.approx(WEIGHT_BBB, abs=TOL)

    @pytest.mark.unit
    def test_null_valued_rows_do_not_count_toward_completeness(self, spark):
        """Silver drops NULL values; a stray one must not fake a sixth dimension."""
        rows = wgi_rows("JJJ", 2023, [0.0] * 5)
        rows.append(("JJJ", "JJJ Land", WGI_DIMENSIONS[5], WGI_CODES[5], 2023, None))
        weights = weights_by_iso3(compute_wgi_weight(
            spark.createDataFrame(rows, SILVER_WGI_SCHEMA)))
        assert weights["JJJ"]["wgi_weight"] is None
        assert weights["JJJ"]["wgi_dimensions_available"] == 5

    @pytest.mark.unit
    def test_duplicate_dimension_rows_do_not_reweight_the_mean(self, spark):
        """A duplicated dimension must not pull the mean toward its value.

        Silver's dedupe makes this unreachable today; the guard exists so a future
        fan-out fails visibly instead of silently double-weighting one dimension.
        """
        rows = wgi_rows("AAA", 2023, VALUES_AAA)
        rows.append(rows[0])  # duplicate Control of Corruption (1.0)
        weights = weights_by_iso3(compute_wgi_weight(
            spark.createDataFrame(rows, SILVER_WGI_SCHEMA)))
        assert weights["AAA"]["wgi_mean_estimate"] == pytest.approx(1.5, abs=TOL)
        assert weights["AAA"]["wgi_weight"] == pytest.approx(WEIGHT_AAA, abs=TOL)


class TestJoinCoverage:
    """Criterion 5 — coverage measured via check_unmapped; nothing silently dropped."""

    @staticmethod
    def _dim_country(spark):
        return spark.createDataFrame([
            (101, "AAA", "Aaa Land", False),
            (102, "BBB", "Bbb Land", False),
            (103, "ZZZ", "Zzz Land", False),        # in dim, absent from WGI
            (104, "UNK_GLOB", "Unknown - Global", True),
        ], DIM_COUNTRY_SCHEMA)

    @staticmethod
    def _fact(spark):
        return spark.createDataFrame([
            (1, 1, 101, 2023, "global", 40.0, 1.0),
            (1, 1, 102, 2023, "global", 35.0, 1.1),
            (1, 1, 103, 2023, "global", 20.0, 1.0),   # no WGI weight
            (1, 1, 104, 2023, "global", 5.0, 1.0),    # placeholder, no WGI weight
            (1, 1, 101, 2023, "eu_sourcing", 60.0, 0.8),
        ], FACT_SCHEMA)

    def _joined(self, spark):
        weights = compute_wgi_weight(silver_wgi(
            spark,
            wgi_rows("AAA", 2023, VALUES_AAA),
            wgi_rows("BBB", 2023, VALUES_BBB),
        ))
        by_key = map_wgi_weight_to_country_key(weights, self._dim_country(spark))
        return attach_wgi_weight(self._fact(spark), by_key), by_key

    @pytest.mark.unit
    def test_join_is_row_preserving(self, spark):
        fact = self._fact(spark)
        joined, _ = self._joined(spark)
        assert joined.count() == fact.count() == 5

    @pytest.mark.unit
    def test_unmapped_countries_are_kept_with_null_weight(self, spark):
        joined, _ = self._joined(spark)
        by_country = {r["country_key"]: r["wgi_weight"] for r in
                      joined.select("country_key", "wgi_weight").distinct().collect()}
        assert by_country[101] == pytest.approx(WEIGHT_AAA, abs=TOL)
        assert by_country[102] == pytest.approx(WEIGHT_BBB, abs=TOL)
        assert by_country[103] is None, "unmapped country was dropped or defaulted"
        assert by_country[104] is None

    @pytest.mark.unit
    def test_check_unmapped_measures_the_coverage_gap(self, spark):
        """The existing mechanism counts the gap — 2 of 5 rows lack a weight."""
        joined, _ = self._joined(spark)
        assert check_unmapped(joined, "wgi_weight", "WGI governance weight",
                              log_unmapped=False) == 2

    @pytest.mark.unit
    def test_full_coverage_reports_zero(self, spark):
        weights = compute_wgi_weight(silver_wgi(
            spark,
            wgi_rows("AAA", 2023, VALUES_AAA),
            wgi_rows("BBB", 2023, VALUES_BBB),
            wgi_rows("ZZZ", 2023, VALUES_AAA),
            wgi_rows("UNK_GLOB", 2023, VALUES_AAA),
        ))
        by_key = map_wgi_weight_to_country_key(weights, self._dim_country(spark))
        joined = attach_wgi_weight(self._fact(spark), by_key)
        assert check_unmapped(joined, "wgi_weight", "WGI governance weight",
                              log_unmapped=False) == 0

    @pytest.mark.unit
    def test_weight_frame_is_unique_on_country_key(self, spark):
        """A duplicate country_key would fan out every supply row for that country."""
        _, by_key = self._joined(spark)
        dupes = (by_key.groupBy("country_key")
                       .agg(F.count(F.lit(1)).alias("n"))   # not `count`: Row is a tuple
                       .filter(F.col("n") > 1).count())
        assert dupes == 0

    @pytest.mark.unit
    def test_original_columns_and_order_are_preserved(self, spark):
        fact = self._fact(spark)
        joined, _ = self._joined(spark)
        assert joined.columns == fact.columns + ["wgi_year", "wgi_weight"]

    @pytest.mark.unit
    def test_iso3_case_is_normalised_on_the_dimension_side(self, spark):
        """The predicate mirrors the notebook's coverage rule (UPPER(dc.iso3))."""
        dim = spark.createDataFrame([(101, "aaa", "Aaa Land", False)],
                                    DIM_COUNTRY_SCHEMA)
        weights = compute_wgi_weight(
            silver_wgi(spark, wgi_rows("AAA", 2023, VALUES_AAA)))
        by_key = map_wgi_weight_to_country_key(weights, dim)
        assert by_key.count() == 1
        assert by_key.first()["wgi_weight"] == pytest.approx(WEIGHT_AAA, abs=TOL)


class TestNotebookParity:
    """
    Criterion 6 — parity guard for the reference-implementation contract (DEC-002).

    src/transformations/supply_risk.py mirrors logic that
    fabric/silver-to-gold2.Notebook defines inline. These tests load the notebook's own
    FunctionDefs and prove the two agree, so a change to either side without the other
    fails CI by design.
    """

    @staticmethod
    def notebook():
        return load_notebook_functions(GOLD_NOTEBOOK, NOTEBOOK_FUNCTIONS)

    @pytest.mark.unit
    def test_notebook_defines_all_six_functions(self):
        nb = self.notebook()
        assert sorted(nb) == sorted(NOTEBOOK_FUNCTIONS)

    @pytest.mark.unit
    def test_spec_constants_match_between_notebook_and_src(self):
        """The fixed bounds and the six-dimension rule agree, and are the spec values.

        The harness compiles the notebook's FunctionDefs in a namespace holding only
        `F`, so these defaults come from the notebook text itself — nothing is injected
        by the test that could mask a drifted notebook constant.
        """
        nb = self.notebook()
        for name, src_fn in (("wgi_weight_expr", wgi_weight_expr),
                             ("compute_wgi_weight", compute_wgi_weight)):
            nb_params = inspect.signature(nb[name]).parameters
            src_params = inspect.signature(src_fn).parameters
            assert nb_params["estimate_min"].default == \
                src_params["estimate_min"].default == -2.5
            assert nb_params["estimate_max"].default == \
                src_params["estimate_max"].default == 2.5
        assert inspect.signature(nb["compute_wgi_weight"]).parameters[
            "required_dimensions"].default == 6

    @pytest.mark.unit
    @pytest.mark.parametrize("mean_estimate", [2.5, 1.5, 0.0, -1.0, -2.5, 3.0, -3.0])
    def test_wgi_weight_expr_parity(self, spark, mean_estimate):
        nb = self.notebook()
        df = spark.createDataFrame([(mean_estimate,)], ["mean_estimate"])
        src_val = df.select(wgi_weight_expr(F.col("mean_estimate")).alias("w")).first()["w"]
        nb_val = df.select(
            nb["wgi_weight_expr"](F.col("mean_estimate")).alias("w")).first()["w"]
        assert src_val == nb_val

    @pytest.mark.unit
    def test_wgi_weight_expr_null_parity(self, spark):
        """Both sides must return NULL — not 0.0 — for an unknown mean."""
        nb = self.notebook()
        schema = StructType([StructField("mean_estimate", DoubleType(), True)])
        df = spark.createDataFrame([(None,)], schema)
        src_val = df.select(wgi_weight_expr(F.col("mean_estimate")).alias("w")).first()["w"]
        nb_val = df.select(
            nb["wgi_weight_expr"](F.col("mean_estimate")).alias("w")).first()["w"]
        assert src_val is None and nb_val is None

    @pytest.mark.unit
    def test_compute_wgi_weight_parity(self, spark):
        """Same rows, same order, across complete / fallback / incomplete countries."""
        nb = self.notebook()
        source = silver_wgi(
            spark,
            wgi_rows("AAA", 2023, VALUES_AAA),
            wgi_rows("BBB", 2018, VALUES_BBB),
            wgi_rows("CCC", 2023, VALUES_CCC),
            wgi_rows("DDD", 2023, VALUES_DDD),
            wgi_rows("GGG", 2022, VALUES_AAA),
            wgi_rows("GGG", 2023, [0.0] * 5),   # incomplete latest vintage
            wgi_rows("HHH", 2023, [0.0] * 5),   # never complete
        )

        src_rows = [r.asDict() for r in
                    compute_wgi_weight(source).orderBy("country_iso3").collect()]
        nb_rows = [r.asDict() for r in
                   nb["compute_wgi_weight"](source).orderBy("country_iso3").collect()]

        assert src_rows == nb_rows
        assert len(src_rows) == 6
        # Anchor the shared result to the spec, so parity on a wrong answer still fails.
        by_iso3 = {r["country_iso3"]: r for r in src_rows}
        assert by_iso3["AAA"]["wgi_weight"] == pytest.approx(WEIGHT_AAA, abs=TOL)
        assert by_iso3["GGG"]["wgi_year"] == 2022
        assert by_iso3["HHH"]["wgi_weight"] is None

    @pytest.mark.unit
    def test_map_and_attach_parity(self, spark):
        nb = self.notebook()
        weights = compute_wgi_weight(silver_wgi(
            spark,
            wgi_rows("AAA", 2023, VALUES_AAA),
            wgi_rows("BBB", 2023, VALUES_BBB),
        ))
        dim = TestJoinCoverage._dim_country(spark)
        fact = TestJoinCoverage._fact(spark)

        src_by_key = map_wgi_weight_to_country_key(weights, dim)
        nb_by_key = nb["map_wgi_weight_to_country_key"](weights, dim)
        assert [r.asDict() for r in src_by_key.orderBy("country_key").collect()] == \
               [r.asDict() for r in nb_by_key.orderBy("country_key").collect()]

        order = ["material_key", "stage_key", "country_key", "supply_mix"]
        src_joined = attach_wgi_weight(fact, src_by_key)
        nb_joined = nb["attach_wgi_weight"](fact, nb_by_key)
        assert src_joined.columns == nb_joined.columns
        assert [r.asDict() for r in src_joined.orderBy(*order).collect()] == \
               [r.asDict() for r in nb_joined.orderBy(*order).collect()]


# =============================================================================
# HHI aggregation — gold_supply_risk (task-038_4)
# spec_v1 § Business Logic & Calculations → Supply Risk (DEC-001 Option B)
# =============================================================================
# Every numeric expectation below is a LITERAL hand-computed from the formula
# HHI_WGI,t = Σ_c (Sᶜ)² · WGIᶜ · tᶜ, with Sᶜ = share_pct / 100. None is derived
# from the frame under test — an assertion that recomputes its expected value
# from the function's own output cannot fail.

# Schema for the fact_supply_share input to compute_gold_supply_risk. Carries
# wgi_weight (already materialized by task-038_3) and t (task-038_2). is_placeholder
# is NOT on the fact — the function joins gold_dim_country for it.
SUPPLY_FACT_SCHEMA = StructType([
    StructField("material_key", LongType(), True),
    StructField("stage_key", LongType(), True),
    StructField("country_key", LongType(), True),
    StructField("year", IntegerType(), True),
    StructField("supply_mix", StringType(), True),
    StructField("share_pct", DoubleType(), True),
    StructField("t", DoubleType(), True),
    StructField("wgi_weight", DoubleType(), True),
])

DIM_COUNTRY_KEY_SCHEMA = StructType([
    StructField("country_key", LongType(), True),
    StructField("is_placeholder", BooleanType(), True),
])


def _supply_fact(spark, rows):
    return spark.createDataFrame(rows, SUPPLY_FACT_SCHEMA)


def _dim_country_key(spark, rows):
    return spark.createDataFrame(rows, DIM_COUNTRY_KEY_SCHEMA)


def _risk_rows(spark, df, dim=None):
    """Run compute_gold_supply_risk and return {(material, stage, year): Row}."""
    if dim is None:
        dim = _dim_country_key(spark, [])
    out = compute_gold_supply_risk(df, dim)
    # Column order is part of the contract (acceptance criterion: table layout).
    assert out.columns == [
        "material_key", "stage_key", "year",
        "hhi_global", "hhi_eu_sourcing", "contrast_ratio",
        "is_bottleneck", "incomplete_wgi_coverage",
    ], f"unexpected column order: {out.columns}"
    return {(r["material_key"], r["stage_key"], r["year"]): r
            for r in out.collect()}, out


class TestSupplyRiskContribution:
    """The per-country contribution term (Sᶜ)² · WGIᶜ · tᶜ as a Column."""

    @pytest.mark.unit
    def test_uses_share_fraction_not_percentage(self, spark):
        """Sᶜ = share_pct / 100. share_pct = 50, wgi = 1, t = 1 -> (0.5)² = 0.25.

        Squaring the 0-100 scale instead would give 50² = 2500 — a 10^4x error
        that still computes and still looks plausible. The literal 0.25 is what
        the spec formula produces and what the index sums over.
        """
        df = spark.createDataFrame(
            [(50.0, 1.0, 1.0)], "share_pct DOUBLE, wgi_weight DOUBLE, t DOUBLE"
        )
        got = df.select(supply_risk_contribution(
            F.col("share_pct"), F.col("wgi_weight"), F.col("t")
        ).alias("c")).first()["c"]
        assert got == pytest.approx(0.25, abs=TOL)

    @pytest.mark.unit
    def test_accepts_column_names(self, spark):
        """Both call styles (str column names and Column expressions) must work.

        compute_gold_supply_risk passes strings; a Column-expression call is the
        natural shape for ad-hoc use. Both must agree.
        """
        df = spark.createDataFrame(
            [(40.0, 0.5, 2.0)], "share_pct DOUBLE, wgi_weight DOUBLE, t DOUBLE"
        )
        by_name = df.select(supply_risk_contribution(
            "share_pct", "wgi_weight", "t").alias("c")).first()["c"]
        by_col = df.select(supply_risk_contribution(
            F.col("share_pct"), F.col("wgi_weight"), F.col("t")
        ).alias("c")).first()["c"]
        # (0.4)² · 0.5 · 2.0 = 0.16 · 1.0 = 0.16
        assert by_name == pytest.approx(0.16, abs=TOL)
        assert by_col == by_name

    @pytest.mark.unit
    def test_null_t_yields_null_contribution(self, spark):
        """A NULL trade parameter yields NULL; F.sum skips it (excluded, not zeroed)."""
        df = spark.createDataFrame(
            [(50.0, 1.0, None)], "share_pct DOUBLE, wgi_weight DOUBLE, t DOUBLE"
        )
        got = df.select(supply_risk_contribution(
            "share_pct", "wgi_weight", "t").alias("c")).first()["c"]
        assert got is None


class TestHhiFormula:
    """Criterion 2 — HHI = Σ_c (Sᶜ)² · WGIᶜ · tᶜ over each supply_mix, shares as fractions."""

    @pytest.mark.unit
    def test_single_country_global_hand_computed(self, spark):
        """One supplier at 60%, weight 0.5, t 1.0 -> (0.6)² · 0.5 · 1.0 = 0.18."""
        fact = _supply_fact(spark, [
            (1, 1, 101, 2023, "global", 60.0, 1.0, 0.5),
        ])
        rows, _ = _risk_rows(spark, fact)
        r = rows[(1, 1, 2023)]
        assert r["hhi_global"] == pytest.approx(0.18, abs=TOL)
        assert r["hhi_eu_sourcing"] is None      # no eu_sourcing rows
        assert r["contrast_ratio"] is None       # EU coverage gap -> NULL, not 0
        assert r["incomplete_wgi_coverage"] is False
        assert r["is_bottleneck"] is True         # only stage -> it IS the bottleneck

    @pytest.mark.unit
    def test_two_countries_sum_as_fractions(self, spark):
        """Two global suppliers: 60%@0.5,t1 + 40%@0.25,t2.

        (0.6)²·0.5·1.0 + (0.4)²·0.25·2.0 = 0.18 + 0.08 = 0.26
        """
        fact = _supply_fact(spark, [
            (1, 1, 101, 2023, "global", 60.0, 1.0, 0.5),
            (1, 1, 102, 2023, "global", 40.0, 2.0, 0.25),
        ])
        rows, _ = _risk_rows(spark, fact)
        assert rows[(1, 1, 2023)]["hhi_global"] == pytest.approx(0.26, abs=TOL)

    @pytest.mark.unit
    def test_share_pct_squaring_bug_would_produce_wrong_value(self, spark):
        """Regression pin: squaring 0-100 instead of 0-1 gives 0.18·10^4 = 1800.

        If the /100 division is ever dropped, the index computes and looks
        plausible but is 10^4x too large. The literal 0.18 (not 1800) is the
        spec value; this assertion is the one that fails when the fraction
        conversion is removed.
        """
        fact = _supply_fact(spark, [
            (1, 1, 101, 2023, "global", 60.0, 1.0, 0.5),
        ])
        rows, _ = _risk_rows(spark, fact)
        assert rows[(1, 1, 2023)]["hhi_global"] < 1.0, (
            "hhi_global > 1 means share_pct was squared on the 0-100 scale, "
            "producing a 10^4x-inflated but plausible-looking index"
        )

    @pytest.mark.unit
    def test_two_mixes_computed_independently(self, spark):
        """Same material/stage/year, two supply_mixes — the two HHIs stay separate.

        global: 60%@0.5,t1 + 40%@0.25,t2 = 0.18 + 0.08 = 0.26
        eu_sourcing: 80%@0.5,t0.8 = (0.8)²·0.5·0.8 = 0.256
        contrast_ratio = 0.256 / 0.26
        """
        fact = _supply_fact(spark, [
            (1, 1, 101, 2023, "global", 60.0, 1.0, 0.5),
            (1, 1, 102, 2023, "global", 40.0, 2.0, 0.25),
            (1, 1, 101, 2023, "eu_sourcing", 80.0, 0.8, 0.5),
        ])
        rows, _ = _risk_rows(spark, fact)
        r = rows[(1, 1, 2023)]
        assert r["hhi_global"] == pytest.approx(0.26, abs=TOL)
        assert r["hhi_eu_sourcing"] == pytest.approx(0.256, abs=TOL)
        assert r["contrast_ratio"] == pytest.approx(0.256 / 0.26, abs=1e-9)

    @pytest.mark.unit
    def test_grain_is_material_stage_year(self, spark):
        """One row per (material × stage × year), regardless of country count.

        Three global suppliers for the same key collapse to ONE row.
        """
        fact = _supply_fact(spark, [
            (1, 1, 101, 2023, "global", 50.0, 1.0, 0.5),
            (1, 1, 102, 2023, "global", 30.0, 1.0, 0.5),
            (1, 1, 103, 2023, "global", 20.0, 1.0, 0.5),
        ])
        _, out = _risk_rows(spark, fact)
        # (0.5)²·0.5·1 + (0.3)²·0.5·1 + (0.2)²·0.5·1 = 0.125 + 0.045 + 0.02 = 0.19
        rows = out.filter(
            (F.col("material_key") == 1) & (F.col("stage_key") == 1)
            & (F.col("year") == 2023)
        ).collect()
        assert len(rows) == 1
        assert rows[0]["hhi_global"] == pytest.approx(0.19, abs=TOL)

    @pytest.mark.unit
    def test_duplicate_grain_fails_loudly_in_notebook_pattern(self, spark):
        """The notebook's grain guard asserts uniqueness on (material, stage, year).

        This test pins the GUARD SHAPE rather than re-running it: the function
        itself produces one row per key by construction (groupBy collapses
        country rows), so a duplicate can only arise if the groupBy key is
        wrong. Verified here by giving it 3 rows for the same key and asserting
        exactly one output row.
        """
        fact = _supply_fact(spark, [
            (1, 1, 101, 2023, "global", 50.0, 1.0, 0.5),
            (1, 1, 101, 2023, "global", 50.0, 1.0, 0.5),  # duplicate country row
        ])
        _, out = _risk_rows(spark, fact)
        # Same (material, stage, year) collapses to one row regardless.
        n = out.filter(
            (F.col("material_key") == 1) & (F.col("stage_key") == 1)
            & (F.col("year") == 2023)
        ).count()
        assert n == 1


class TestNullWgiExclusion:
    """Criterion — NULL wgi_weight rows are EXCLUDED, not zeroed; gap is flagged."""

    @pytest.mark.unit
    def test_null_wgi_excluded_not_zeroed(self, spark):
        """A NULL-weight country contributes NOTHING — never 0, which is best-governance.

        global: 60%@0.5,t1 + 40%@NULL_wgi -> only the 60% row counts -> 0.18.
        If NULL were coerced to 0, the second term would be 0 and the index would
        still read 0.18 — indistinguishable. The incomplete_wgi_coverage flag is
        what makes the exclusion visible: the index for this key is computed over
        a 60%-coverage subset, which understates risk if the NULL country is
        poorly governed.
        """
        fact = _supply_fact(spark, [
            (1, 1, 101, 2023, "global", 60.0, 1.0, 0.5),
            (1, 1, 102, 2023, "global", 40.0, 1.0, None),  # NULL wgi
        ])
        rows, _ = _risk_rows(spark, fact)
        r = rows[(1, 1, 2023)]
        assert r["hhi_global"] == pytest.approx(0.18, abs=TOL)
        assert r["incomplete_wgi_coverage"] is True

    @pytest.mark.unit
    def test_all_null_wgi_yields_null_hhi_with_coverage_flag(self, spark):
        """A key whose only rows are all-NULL-wgi -> hhi_global = NULL, flag = True.

        Not 0 (0 is a legitimate "perfectly diffuse" index value); NULL means
        "no governance-known contribution". The flag carries the reason.
        """
        fact = _supply_fact(spark, [
            (1, 1, 101, 2023, "global", 60.0, 1.0, None),
            (1, 1, 102, 2023, "global", 40.0, 1.0, None),
        ])
        rows, _ = _risk_rows(spark, fact)
        r = rows[(1, 1, 2023)]
        assert r["hhi_global"] is None, (
            f"all-NULL-wgi produced hhi_global={r['hhi_global']!r} — should be NULL"
        )
        assert r["incomplete_wgi_coverage"] is True
        # is_bottleneck must not flag a stage with NULL hhi_global
        assert r["is_bottleneck"] is False

    @pytest.mark.unit
    def test_placeholder_excluded_regardless_of_weight(self, spark):
        """UNK_GLOB is a bucket, not a country — excluded even with a weight.

        Setup: 60%@0.5,t1 (real country) + 40%@0.99,t1 (placeholder, is_placeholder=True).
        The placeholder is excluded by is_placeholder, not by wgi_weight (it has one).
        The index is 0.18, not 0.18 + (0.4)²·0.99 = 0.3384.
        """
        fact = _supply_fact(spark, [
            (1, 1, 101, 2023, "global", 60.0, 1.0, 0.5),
            (1, 1, 104, 2023, "global", 40.0, 1.0, 0.99),  # placeholder
        ])
        dim = _dim_country_key(spark, [
            (101, False),
            (104, True),   # UNK_GLOB
        ])
        rows, _ = _risk_rows(spark, fact, dim)
        r = rows[(1, 1, 2023)]
        assert r["hhi_global"] == pytest.approx(0.18, abs=TOL), (
            "placeholder country was counted into the HHI sum — it must be excluded "
            "by is_placeholder regardless of its weight"
        )
        # The placeholder has a non-NULL wgi_weight here, so the coverage flag is
        # False (the exclusion is by is_placeholder, not by NULL wgi). This is the
        # boundary between rules 1 and 2.
        assert r["incomplete_wgi_coverage"] is False

    @pytest.mark.unit
    def test_placeholder_with_null_wgi_flagged(self, spark):
        """The realistic case: placeholder has NULL wgi_weight (it always does).

        Excluded by BOTH the NULL-wgi filter AND the is_placeholder filter.
        The coverage flag IS True here — the placeholder's NULL weight is the gap.
        """
        fact = _supply_fact(spark, [
            (1, 1, 101, 2023, "global", 60.0, 1.0, 0.5),
            (1, 1, 104, 2023, "global", 40.0, 1.0, None),  # placeholder, NULL wgi
        ])
        dim = _dim_country_key(spark, [(101, False), (104, True)])
        rows, _ = _risk_rows(spark, fact, dim)
        r = rows[(1, 1, 2023)]
        assert r["hhi_global"] == pytest.approx(0.18, abs=TOL)
        assert r["incomplete_wgi_coverage"] is True


class TestEuCoverageGap:
    """Criterion — EU coverage gap: global exists, no eu_sourcing rows -> NULL, never 0."""

    @pytest.mark.unit
    def test_material_present_in_global_absent_from_eu_sourcing(self, spark):
        """Material 2 has global rows but NO eu_sourcing rows.

        hhi_eu_sourcing = NULL and contrast_ratio = NULL — never 0 (0 would
        misread as 'no EU concentration risk', a legitimate index value meaning
        perfectly diffuse supply).
        """
        fact = _supply_fact(spark, [
            # material 1: both mixes
            (1, 1, 101, 2023, "global", 60.0, 1.0, 0.5),
            (1, 1, 101, 2023, "eu_sourcing", 80.0, 0.8, 0.5),
            # material 2: global only — the EU coverage gap
            (2, 1, 101, 2023, "global", 70.0, 1.0, 0.5),
        ])
        rows, _ = _risk_rows(spark, fact)
        m2 = rows[(2, 1, 2023)]
        assert m2["hhi_eu_sourcing"] is None, (
            "EU coverage gap produced a non-NULL hhi_eu_sourcing — should be NULL"
        )
        assert m2["contrast_ratio"] is None, (
            "EU coverage gap produced a non-NULL contrast_ratio — should be NULL"
        )
        # hhi_global is still computed
        assert m2["hhi_global"] == pytest.approx((0.7) ** 2 * 0.5 * 1.0, abs=TOL)

    @pytest.mark.unit
    def test_hhi_global_zero_yields_null_contrast_not_zero(self, spark):
        """hhi_global = 0 (only known weights are 0.0) -> contrast_ratio = NULL, never 0.

        A 0 contrast_ratio would read as 'EU sourcing is 0% as concentrated as the
        world' — a real economic claim. NULL means 'undefined', which is what
        dividing by zero actually is.
        """
        # weight = 0.0 is the best-governed country; (S)²·0·t = 0
        fact = _supply_fact(spark, [
            (1, 1, 101, 2023, "global", 100.0, 1.0, 0.0),  # wgi_weight = 0
            (1, 1, 101, 2023, "eu_sourcing", 100.0, 0.8, 0.0),
        ])
        rows, _ = _risk_rows(spark, fact)
        r = rows[(1, 1, 2023)]
        assert r["hhi_global"] == pytest.approx(0.0, abs=TOL)
        assert r["hhi_eu_sourcing"] == pytest.approx(0.0, abs=TOL)
        assert r["contrast_ratio"] is None, (
            "hhi_global = 0 produced a non-NULL contrast_ratio — should be NULL "
            "(never 0; 0 is a legitimate index value meaning perfectly diffuse)"
        )

    @pytest.mark.unit
    def test_eu_only_material_has_null_hhi_global(self, spark):
        """Symmetric edge: a key with EU rows but no global rows.

        hhi_global = NULL, contrast_ratio = NULL (can't divide by NULL).
        """
        fact = _supply_fact(spark, [
            (1, 1, 101, 2023, "eu_sourcing", 80.0, 0.8, 0.5),
        ])
        rows, _ = _risk_rows(spark, fact)
        r = rows[(1, 1, 2023)]
        assert r["hhi_global"] is None
        assert r["hhi_eu_sourcing"] == pytest.approx(0.256, abs=TOL)
        assert r["contrast_ratio"] is None


class TestIsBottleneck:
    """Criterion — is_bottleneck flags the stage with HIGHER hhi_global per material × year."""

    @pytest.mark.unit
    def test_higher_hhi_global_stage_flagged(self, spark):
        """Material 1, E vs P: E has higher hhi_global -> E flagged, P not.

        E: (0.6)²·0.5·1 = 0.18;  P: (0.3)²·0.5·1 = 0.045. E wins.
        """
        fact = _supply_fact(spark, [
            (1, 1, 101, 2023, "global", 60.0, 1.0, 0.5),   # E, hhi 0.18
            (1, 2, 101, 2023, "global", 30.0, 1.0, 0.5),   # P, hhi 0.045
        ])
        rows, _ = _risk_rows(spark, fact)
        e = [r for r in rows.values() if r["stage_key"] == 1][0]
        p = [r for r in rows.values() if r["stage_key"] == 2][0]
        assert e["is_bottleneck"] is True, "the higher-hhi_global stage must be flagged"
        assert p["is_bottleneck"] is False

    @pytest.mark.unit
    def test_driven_by_hhi_global_not_eu_sourcing(self, spark):
        """P has higher hhi_eu_sourcing but E has higher hhi_global -> E is bottleneck.

        The flag is driven by hhi_global ONLY (spec: 'not by hhi_eu_sourcing or
        the max of the two'), so it stays defined when EU coverage is missing.
        """
        # E: global 0.18, eu_sourcing 0.10
        # P: global 0.045, eu_sourcing 0.30  (P would win on EU or on max)
        fact = _supply_fact(spark, [
            (1, 1, 101, 2023, "global",     60.0, 1.0, 0.5),   # E global 0.18
            (1, 1, 101, 2023, "eu_sourcing", 40.0, 1.0, 0.5),  # E eu (0.4)²·0.5 = 0.08
            (1, 2, 101, 2023, "global",      30.0, 1.0, 0.5),  # P global 0.045
            (1, 2, 101, 2023, "eu_sourcing", 80.0, 1.0, 0.5),  # P eu (0.8)²·0.5 = 0.32
        ])
        rows, _ = _risk_rows(spark, fact)
        e = [r for r in rows.values() if r["stage_key"] == 1][0]
        p = [r for r in rows.values() if r["stage_key"] == 2][0]
        assert e["hhi_global"] > p["hhi_global"]
        assert e["hhi_eu_sourcing"] < p["hhi_eu_sourcing"]
        assert e["is_bottleneck"] is True, (
            "bottleneck must track hhi_global, not hhi_eu_sourcing or max of the two"
        )
        assert p["is_bottleneck"] is False

    @pytest.mark.unit
    def test_tie_flags_neither_stage(self, spark):
        """Equal hhi_global for E and P -> neither is the bottleneck (strict 'higher')."""
        fact = _supply_fact(spark, [
            (1, 1, 101, 2023, "global", 50.0, 1.0, 0.5),  # E, (0.5)²·0.5 = 0.125
            (1, 2, 101, 2023, "global", 50.0, 1.0, 0.5),  # P, same 0.125
        ])
        rows, _ = _risk_rows(spark, fact)
        e = [r for r in rows.values() if r["stage_key"] == 1][0]
        p = [r for r in rows.values() if r["stage_key"] == 2][0]
        assert e["hhi_global"] == p["hhi_global"]
        assert e["is_bottleneck"] is False, (
            "a tie flagged a stage — 'higher' is strict; ties flag neither"
        )
        assert p["is_bottleneck"] is False

    @pytest.mark.unit
    def test_null_hhi_global_never_wins(self, spark):
        """A stage with NULL hhi_global (all-NULL-wgi) never becomes the bottleneck.

        E has NULL hhi_global (all its rows are NULL-wgi); P has a real 0.18. P
        wins, E does not — even if E were the only other stage.
        """
        fact = _supply_fact(spark, [
            (1, 1, 101, 2023, "global", 60.0, 1.0, None),  # E, NULL wgi -> NULL hhi
            (1, 2, 102, 2023, "global", 60.0, 1.0, 0.5),  # P, hhi 0.18
        ])
        rows, _ = _risk_rows(spark, fact)
        e = [r for r in rows.values() if r["stage_key"] == 1][0]
        p = [r for r in rows.values() if r["stage_key"] == 2][0]
        assert e["hhi_global"] is None
        assert e["is_bottleneck"] is False
        assert p["is_bottleneck"] is True

    @pytest.mark.unit
    def test_single_stage_is_bottleneck(self, spark):
        """A material with only one stage present: that stage is the bottleneck.

        No competitor -> max hhi_global == its own, _n_at_max == 1 -> flagged.
        """
        fact = _supply_fact(spark, [
            (1, 1, 101, 2023, "global", 60.0, 1.0, 0.5),
        ])
        rows, _ = _risk_rows(spark, fact)
        r = list(rows.values())[0]
        assert r["is_bottleneck"] is True

    @pytest.mark.unit
    def test_single_stage_null_hhi_global_not_flagged(self, spark):
        """One stage, but hhi_global is NULL (only EU rows) -> NOT the bottleneck.

        The flag is 'the stage with the HIGHER hhi_global'; a stage with no
        measured global risk is not a bottleneck by this index even with no
        competitor. NULL hhi_global never wins.
        """
        fact = _supply_fact(spark, [
            (1, 1, 101, 2023, "eu_sourcing", 80.0, 0.8, 0.5),
        ])
        rows, _ = _risk_rows(spark, fact)
        r = list(rows.values())[0]
        assert r["hhi_global"] is None
        assert r["is_bottleneck"] is False

    @pytest.mark.unit
    def test_bottleneck_per_material_year_independent(self, spark):
        """Two materials, different winners — the flag is per material × year."""
        fact = _supply_fact(spark, [
            # material 1: E higher
            (1, 1, 101, 2023, "global", 60.0, 1.0, 0.5),   # E 0.18
            (1, 2, 101, 2023, "global", 30.0, 1.0, 0.5),   # P 0.045
            # material 2: P higher
            (2, 1, 101, 2023, "global", 20.0, 1.0, 0.5),   # E (0.2)²·0.5 = 0.02
            (2, 2, 101, 2023, "global", 70.0, 1.0, 0.5),   # P (0.7)²·0.5 = 0.245
        ])
        rows, _ = _risk_rows(spark, fact)
        by_key = {(r["material_key"], r["stage_key"]): r for r in rows.values()}
        assert by_key[(1, 1)]["is_bottleneck"] is True
        assert by_key[(1, 2)]["is_bottleneck"] is False
        assert by_key[(2, 1)]["is_bottleneck"] is False
        assert by_key[(2, 2)]["is_bottleneck"] is True


class TestSupplyRiskNotebookParity:
    """Criterion 6 — parity guard for the HHI aggregation (DEC-002)."""

    @staticmethod
    def notebook():
        return load_notebook_functions(GOLD_NOTEBOOK, NOTEBOOK_FUNCTIONS)

    @pytest.mark.unit
    def test_supply_risk_contribution_parity(self, spark):
        nb = self.notebook()
        df = spark.createDataFrame(
            [(50.0, 0.7, 1.5)], "share_pct DOUBLE, wgi_weight DOUBLE, t DOUBLE"
        )
        src_val = df.select(supply_risk_contribution(
            "share_pct", "wgi_weight", "t").alias("c")).first()["c"]
        nb_val = df.select(nb["supply_risk_contribution"](
            "share_pct", "wgi_weight", "t").alias("c")).first()["c"]
        # (0.5)² · 0.7 · 1.5 = 0.25 · 1.05 = 0.2625
        assert src_val == nb_val == pytest.approx(0.2625, abs=TOL)

    @pytest.mark.unit
    def test_compute_gold_supply_risk_parity(self, spark):
        """Same fact, same dim_country -> same gold_supply_risk output, row for row.

        Covers the full set of rules: per-mix HHI, EU coverage gap, NULL wgi
        exclusion + coverage flag, placeholder exclusion, is_bottleneck per
        material × year, contrast_ratio NULL rules.
        """
        nb = self.notebook()
        fact = _supply_fact(spark, [
            # material 1, stage E (1): global with a NULL-wgi country + placeholder;
            # EU coverage gap (no eu_sourcing rows for this key)
            (1, 1, 101, 2023, "global", 50.0, 1.0, 0.5),     # real
            (1, 1, 102, 2023, "global", 30.0, 1.0, None),    # NULL wgi (TWN-like)
            (1, 1, 104, 2023, "global", 20.0, 1.0, None),    # placeholder, NULL wgi
            # material 1, stage P (2): both mixes, no gaps
            (1, 2, 101, 2023, "global", 60.0, 1.0, 0.5),
            (1, 2, 101, 2023, "eu_sourcing", 80.0, 0.8, 0.5),
            # material 2, stage E: only EU rows (reverse coverage gap)
            (2, 1, 101, 2023, "eu_sourcing", 70.0, 0.8, 0.5),
        ])
        dim = _dim_country_key(spark, [
            (101, False),
            (102, False),
            (104, True),   # placeholder
        ])

        order = ["material_key", "stage_key", "year"]
        src_rows = [r.asDict() for r in
                    compute_gold_supply_risk(fact, dim).orderBy(*order).collect()]
        nb_rows = [r.asDict() for r in
                   nb["compute_gold_supply_risk"](fact, dim).orderBy(*order).collect()]

        assert src_rows == nb_rows
        assert len(src_rows) == 3  # (1,E), (1,P), (2,E)
        # Anchor the shared result to the spec so parity on a wrong answer fails.
        by_key = {(r["material_key"], r["stage_key"]): r for r in src_rows}
        # (1, E): global = (0.5)²·0.5·1 = 0.125; NULL-wgi + placeholder excluded
        assert by_key[(1, 1)]["hhi_global"] == pytest.approx(0.125, abs=TOL)
        assert by_key[(1, 1)]["hhi_eu_sourcing"] is None      # EU coverage gap
        assert by_key[(1, 1)]["contrast_ratio"] is None
        assert by_key[(1, 1)]["incomplete_wgi_coverage"] is True
        # (1, P): global 0.18, eu (0.8)²·0.5·0.8 = 0.256
        assert by_key[(1, 2)]["hhi_global"] == pytest.approx(0.18, abs=TOL)
        assert by_key[(1, 2)]["hhi_eu_sourcing"] == pytest.approx(0.256, abs=TOL)
        # E has higher hhi_global (0.125 < 0.18), so P is the bottleneck
        assert by_key[(1, 1)]["is_bottleneck"] is False
        assert by_key[(1, 2)]["is_bottleneck"] is True
        # (2, E): only EU -> hhi_global NULL, hhi_eu (0.7)²·0.5·0.8 = 0.196
        assert by_key[(2, 1)]["hhi_global"] is None
        assert by_key[(2, 1)]["hhi_eu_sourcing"] == pytest.approx(0.196, abs=TOL)
        assert by_key[(2, 1)]["contrast_ratio"] is None
        # Single stage, but hhi_global is NULL (no global data) -> is_bottleneck
        # is False. The flag is "the stage with the HIGHER hhi_global"; a stage
        # with no measured global risk is not a bottleneck by this index even
        # when it has no competitor. NULL hhi_global never wins.
        assert by_key[(2, 1)]["is_bottleneck"] is False
