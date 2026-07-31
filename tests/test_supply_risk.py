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
)
from tests.test_key_generation import load_notebook_functions

# The four notebook FunctionDefs under parity, in dependency order (compute_wgi_weight
# calls wgi_weight_expr, so the expression helper must be compiled first).
NOTEBOOK_FUNCTIONS = [
    "wgi_weight_expr",
    "compute_wgi_weight",
    "map_wgi_weight_to_country_key",
    "attach_wgi_weight",
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
        return load_notebook_functions(NOTEBOOK_FUNCTIONS)

    @pytest.mark.unit
    def test_notebook_defines_all_four_functions(self):
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
