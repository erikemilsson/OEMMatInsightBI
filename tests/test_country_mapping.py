"""
Regression coverage for the gold country alias seed (task-063).

`country_aliases_with_confidence` is the seed for `mapping_country_aliases_confidence`
and, through the inner join in the `gold_dim_country_lookup` cell, for every country
resolution in `fact_procurement` and `fact_supply_share`. It shipped with **zero tests**
while `MATERIAL_ALIASES` had seven (`tests/test_material_mapping.py`), even though the
country seed is the larger, more error-prone one: it carries two different Congos, two
different Koreas, a mojibake family, and a row that maps a capital city to a country.

The failure mode this file exists to catch is silent. Country resolution runs through an
**inner** join from the seed to `gold_dim_country` (`ca.standard_name == dc.country_name_std`),
so an alias whose `standard_name` is a spelling no dimension row carries is dropped without
error — and the source spelling it was meant to rescue stays unmapped and lands on the
`Unknown - Global` placeholder. That has already bitten twice (`Russia -> Russian Federation`
was backwards; `Cape Verde` had to target the EPI-2024 spelling `Cabo Verde`), both fixed in
task-025. Nothing prevented a third.

Like `test_material_mapping.py`, these tests read the **live notebook text** via `ast` — no
notebook execution, no lakehouse — so editing the seed is what makes them fail, which is the
point. The `unmapped_gap` test additionally executes the notebook's *own* function through
`_notebook_loader.load_notebook_functions`, so the audit-row shape is pinned against
production code rather than a copy.

Contract sources:
  - `docs/transformations/alias_mappings.md` § "Confidence tiers and match_type taxonomy"
    (the banding table), § "Groups that must be edited as a set" (Congo / Korea / Türkiye),
    § "Direction rule (the orphaned-alias trap)".
  - `fabric/silver_to_gold.Notebook/notebook-content.py` — the seed itself, the lookup
    assembly cell, and the `Unknown - Global` fallback in the `fact_procurement` cell.

Scope note (task-063): there is **no `src/transformations/` mirror** for country aliases —
`src/` holds data_quality, key_generation, procurement_dates, supply_risk and watermark
only — and the seed is a literal assignment, not a function, so the notebook↔`src/` parity
shape used by e.g. `test_key_generation.py` does not apply to the seed. The precedent
followed here is `test_material_mapping.py`, which pins the same class of asset (a mapping
literal with no `src/` mirror) by extracting it from the notebook.
"""

import ast
import re
from functools import lru_cache

import pytest
from pyspark.sql import functions as F
from pyspark.sql import Window as W

# GOLD_NOTEBOOK is imported rather than re-derived: test_key_generation, test_data_quality,
# test_supply_risk and test_watermark all source it here, and a second local definition of
# the same path is one more place to miss on the next notebook rename (Phase 5 renamed this
# notebook once already: silver-to-gold2 -> silver_to_gold).
from tests._notebook_loader import GOLD_NOTEBOOK, load_notebook_functions

# The seed's declared columns, asserted below so a silent reshuffle is caught.
ALIAS, STANDARD, CONFIDENCE, MATCH_TYPE = 0, 1, 2, 3

# docs/transformations/alias_mappings.md § "Confidence tiers and match_type taxonomy".
# match_type is the REASON for the confidence, so the mapping is a function: one
# confidence per match_type. "Do not invent a confidence — the tiers are what
# gold_low_confidence_audit (< 0.95) and the data_quality_score are calibrated against."
DOCUMENTED_BANDS = {
    "exact_match": 1.00,
    "standard_alias": 0.95,
    "encoding_variant": 0.90,
    "partial_country": 0.90,
    "ambiguous": 0.90,
    "territory": 0.85,
    "typo": 0.85,
    "with_notation": 0.85,
    "corrupted_encoding": 0.80,
    "source_error": 0.60,
}

# populate_low_confidence_audit() captures matches with confidence < 0.95, i.e. every
# band except these two. A row that drifts up out of its band would disappear from
# gold_low_confidence_audit — the surface that keeps questionable mappings reviewable.
FULL_CONFIDENCE_TYPES = frozenset({"exact_match", "standard_alias"})

# Names gold_dim_country carries that originate in silver_epi, which is a lakehouse table
# with no local fixture — so it cannot be enumerated in a unit test.
#
# This is therefore a MANUALLY-VERIFIED ALLOWLIST, not a measurement: its job is to force
# a human to run the direction-rule check when a NEW alias target appears, not to prove the
# current ones exist. Per alias_mappings.md § "Direction rule":
#
#     SELECT country_name_std FROM oem_lh.gold_dim_country
#     WHERE country_name_std = '<your standard_name>';
#
# Adding an entry here without running that query re-opens exactly the orphaned-alias hole
# task-025 closed. Corroboration on file: "Cabo Verde", "Brazil" and "Russia" are named as
# the EPI-2024 spellings in alias_mappings.md § "Direction rule" and in the seed's own
# task-025 comments; "Dem. Rep. Congo" appears with ISO3 COD in a measured coverage run
# (docs/data_coverage_flow.md). The rest are asserted by the direction rule itself.
EPI_SOURCED_DIM_NAMES = frozenset({
    "United States of America",
    "United Kingdom",
    "Dem. Rep. Congo",
    "Republic of Congo",
    "South Korea",
    "Cabo Verde",
    "Brazil",
    "Czech Republic",
    "United Arab Emirates",
    "Russia",
    "Viet Nam",
    "China",
    "France",
})


# ---------------------------------------------------------------------------
# Notebook extraction
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _notebook_source():
    assert GOLD_NOTEBOOK.exists(), f"Notebook not found: {GOLD_NOTEBOOK}"
    return GOLD_NOTEBOOK.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _notebook_tree():
    return ast.parse(_notebook_source(), filename=str(GOLD_NOTEBOOK))


def _createdataframe_literal(name):
    """
    Return ``(rows, columns)`` for a top-level ``name = spark.createDataFrame(...)``.

    ``ast.literal_eval`` on the call's first argument — never ``exec`` — so the notebook's
    Spark calls are not touched. ``columns`` is None when the schema is passed as a variable
    (``unknown_countries`` passes a StructType), which callers that only need rows ignore.

    Unlike ``test_material_mapping._literal_assignment``, this unwraps a Call rather than
    reading a bare literal: the country seed is built inline as
    ``spark.createDataFrame([...], [...])`` where ``MATERIAL_ALIASES`` is a plain list.
    """
    for node in _notebook_tree().body:
        if not (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == name for t in node.targets)
        ):
            continue
        call = node.value
        assert (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "createDataFrame"
        ), (
            f"`{name}` is no longer assigned from spark.createDataFrame(...). The guard "
            f"cannot enumerate its rows; update this harness deliberately rather than "
            f"deleting the test."
        )
        rows = ast.literal_eval(call.args[0])
        columns = None
        if len(call.args) > 1:
            try:
                columns = ast.literal_eval(call.args[1])
            except ValueError:  # schema passed as a variable (StructType)
                columns = None
        return rows, columns
    raise AssertionError(
        f"Notebook no longer defines a top-level `{name}`. Country-alias regression "
        f"coverage cannot enumerate the mapping. Restore the assignment (or update this "
        f"harness deliberately) rather than deleting this test."
    )


@pytest.fixture(scope="module")
def country_seed():
    """The (alias, standard_name, confidence, match_type) rows, live from the notebook."""
    rows, _ = _createdataframe_literal("country_aliases_with_confidence")
    return rows


@pytest.fixture(scope="module")
def seed_columns():
    _, columns = _createdataframe_literal("country_aliases_with_confidence")
    return columns


@pytest.fixture(scope="module")
def curated_dim_names():
    """`missing_countries` — the canonical names curated in the notebook itself."""
    rows, _ = _createdataframe_literal("missing_countries")
    return {row[0] for row in rows}


@pytest.fixture(scope="module")
def placeholder_dim_names():
    """`unknown_countries` — the UNK_* placeholders unmapped values are routed to."""
    rows, _ = _createdataframe_literal("unknown_countries")
    return {row[0] for row in rows}


@pytest.fixture(scope="module")
def dim_names(curated_dim_names):
    """Every non-placeholder name gold_dim_country is expected to carry."""
    return curated_dim_names | EPI_SOURCED_DIM_NAMES


def _orphaned(seed, known_dim_names):
    """Alias targets absent from the dimension — the inner join drops these silently."""
    return sorted({row[STANDARD] for row in seed} - set(known_dim_names))


# ---------------------------------------------------------------------------
# Seed structure
# ---------------------------------------------------------------------------

class TestSeedStructure:
    @pytest.mark.unit
    def test_seed_shape_is_alias_standard_confidence_match_type(self, country_seed, seed_columns):
        assert country_seed, "country_aliases_with_confidence is empty"
        assert seed_columns == ["alias", "standard_name", "confidence", "match_type"], (
            f"Seed column names changed to {seed_columns}. Downstream code reads "
            f"mapping_country_aliases_confidence and gold_dim_country_lookup by these "
            f"names (silver_to_gold lookup cell; data_quality_analysis alias statistics)."
        )
        malformed = [row for row in country_seed if len(row) != 4]
        assert not malformed, f"Seed row(s) are not 4-tuples: {malformed}"
        bad_types = [
            row for row in country_seed
            if not (
                isinstance(row[ALIAS], str)
                and isinstance(row[STANDARD], str)
                and isinstance(row[CONFIDENCE], float)
                and isinstance(row[MATCH_TYPE], str)
            )
        ]
        assert not bad_types, (
            f"Seed row(s) have wrong column types — createDataFrame infers the schema from "
            f"these literals, so an int confidence makes the column LongType and breaks the "
            f"< 0.95 audit comparison: {bad_types}"
        )

    @pytest.mark.unit
    def test_alias_left_hand_sides_are_unique(self, country_seed):
        """
        A repeated alias is either dead weight or an ambiguity bug.

        `gold_dim_country_lookup` dedupes on `lookup_name` (task-023) to stop fact joins
        fanning out, so a duplicated alias never surfaces as an error — it is resolved by a
        tie-break the author never saw. Two rows with the same alias and DIFFERENT targets
        means the winner is decided by confidence/country_key ordering, not by intent.
        """
        seen = {}
        collisions = {}
        for row in country_seed:
            if row[ALIAS] in seen and seen[row[ALIAS]] != row[STANDARD]:
                collisions[row[ALIAS]] = sorted({seen[row[ALIAS]], row[STANDARD]})
            elif row[ALIAS] in seen:
                collisions.setdefault(row[ALIAS], [seen[row[ALIAS]]])
            seen[row[ALIAS]] = row[STANDARD]
        assert not collisions, (
            f"Duplicate alias key(s) — resolution is decided by the lookup dedupe tie-break "
            f"rather than by the seed: {collisions}"
        )

    @pytest.mark.unit
    def test_self_rows_are_only_the_tier_one_exact_matches(self, country_seed):
        """
        `alias == standard_name` is redundant with the self-lookup the dimension generates.
        It is tolerated at Tier 1 (documented as "only needed where a self-row is not
        otherwise generated") but must never carry a reduced confidence, which would compete
        with the 1.0 self-lookup for the same `lookup_name`.
        """
        wrong = [
            row for row in country_seed
            if row[ALIAS] == row[STANDARD]
            and (row[MATCH_TYPE] != "exact_match" or row[CONFIDENCE] != 1.00)
        ]
        assert not wrong, (
            f"Self-mapping row(s) not banded as exact_match/1.00: {wrong}. A self-row below "
            f"1.0 loses the lookup tie-break to the generated self-lookup and is dead weight "
            f"that reads like a live mapping."
        )


# ---------------------------------------------------------------------------
# Direction rule — every alias target must exist in the dimension
# ---------------------------------------------------------------------------

class TestDirectionRule:
    @pytest.mark.unit
    def test_every_alias_target_exists_in_the_country_dimension(self, country_seed, dim_names):
        orphans = _orphaned(country_seed, dim_names)
        assert not orphans, (
            f"Alias target(s) name no dimension row: {orphans}. gold_dim_country_lookup is "
            f"built with an INNER join from the seed to gold_dim_country, so these aliases "
            f"are dropped silently and the source spellings they rescue stay unmapped. "
            f"Confirm the target with alias_mappings.md's direction-rule query, then add it "
            f"to EPI_SOURCED_DIM_NAMES (or to the notebook's missing_countries)."
        )

    @pytest.mark.unit
    def test_targets_the_notebook_curates_are_present_in_missing_countries(
        self, country_seed, curated_dim_names
    ):
        """
        Non-circular half of the direction rule: these targets exist ONLY because the
        notebook's own `missing_countries` list creates them, and both literals are read
        live — so deleting a curated row while leaving its aliases behind fails here.
        """
        for target in ("Turkey", "Syria", "North Korea"):
            assert target in curated_dim_names, (
                f"{target!r} left missing_countries but is still an alias target "
                f"(e.g. the Türkiye family / 'Syrian Arab Republic' / 'Korea, North'). "
                f"Those aliases are now orphaned."
            )
        aliased = {row[STANDARD] for row in country_seed}
        assert {"Turkey", "Syria", "North Korea"} <= aliased

    @pytest.mark.unit
    def test_direction_rule_probe_detects_an_orphaned_target(self, dim_names):
        """
        Positive control: a guard that only ever reports "nothing wrong" is
        indistinguishable from a broken guard.

        Probes the exact regression task-025 fixed — the alias used to run
        `Russia -> Russian Federation`, and "Russian Federation" is not a name the
        dimension carries, so the row was dropped and BOTH spellings lost their route.
        """
        backwards = [("Russia", "Russian Federation", 0.95, "standard_alias")]
        corrected = [("Russian Federation", "Russia", 0.95, "standard_alias")]
        assert _orphaned(backwards, dim_names) == ["Russian Federation"], (
            "Probe failed to flag the known-orphaned target — the direction-rule guard "
            "above cannot be trusted."
        )
        assert _orphaned(corrected, dim_names) == [], (
            "Probe wrongly flagged the corrected direction."
        )


# ---------------------------------------------------------------------------
# Confidence banding
# ---------------------------------------------------------------------------

class TestConfidenceBanding:
    @pytest.mark.unit
    def test_every_row_uses_a_documented_match_type(self, country_seed):
        unknown = sorted({row[MATCH_TYPE] for row in country_seed} - set(DOCUMENTED_BANDS))
        assert not unknown, (
            f"match_type(s) absent from alias_mappings.md's taxonomy: {unknown}. match_type "
            f"is carried into gold_dim_country_lookup and is what makes a questionable "
            f"mapping auditable — document the tier before seeding it."
        )

    @pytest.mark.unit
    def test_confidence_matches_the_documented_band_for_its_match_type(self, country_seed):
        """
        The banding is a function: one confidence per match_type. Inventing a confidence
        decouples the seed from `gold_low_confidence_audit` (< 0.95) and from
        `data_quality_score`, which are calibrated against these tiers.
        """
        mismatched = [
            (row[ALIAS], row[MATCH_TYPE], row[CONFIDENCE], DOCUMENTED_BANDS[row[MATCH_TYPE]])
            for row in country_seed
            if row[MATCH_TYPE] in DOCUMENTED_BANDS
            and row[CONFIDENCE] != DOCUMENTED_BANDS[row[MATCH_TYPE]]
        ]
        assert not mismatched, (
            "Row(s) off their documented band (alias, match_type, seeded, documented): "
            f"{mismatched}"
        )

    @pytest.mark.unit
    def test_deliberate_sub_one_bands_are_preserved(self, country_seed):
        """
        The seed's judgement calls. Each of these is deliberately BELOW full confidence,
        and each records *why* in its match_type. Silently promoting any of them to
        `standard_alias`/0.95 would launder a known-questionable mapping out of
        `gold_low_confidence_audit` and inflate `data_quality_score` for the rows it touches.
        """
        expected = {
            # a constituent country standing in for the sovereign state
            "England": ("United Kingdom", 0.90, "partial_country"),
            # bare "Congo" is TWO real countries; one is chosen, and that stays visible
            "Congo": ("Republic of Congo", 0.90, "ambiguous"),
            # source attached an HQ annotation to the country name
            "DRC (HQ in South Africa)": ("Dem. Rep. Congo", 0.85, "with_notation"),
            # a capital city, not a country — mapped, but kept reportable
            "Brasilia": ("Brazil", 0.60, "source_error"),
            # dependencies rolled up to the sovereign state
            "Hong Kong": ("China", 0.85, "territory"),
            "French Guiana": ("France", 0.85, "territory"),
            # correct native spelling vs. a recognisable misspelling
            "Türkiye": ("Turkey", 0.90, "encoding_variant"),
            "Turkyie": ("Turkey", 0.85, "typo"),
        }
        by_alias = {row[ALIAS]: (row[STANDARD], row[CONFIDENCE], row[MATCH_TYPE])
                    for row in country_seed}
        actual = {alias: by_alias.get(alias) for alias in expected}
        assert actual == expected

    @pytest.mark.unit
    def test_reduced_confidence_rows_stay_inside_the_audit_threshold(self, country_seed):
        """
        `populate_low_confidence_audit()` captures matches with confidence < 0.95. Every
        band that exists *because* the match is questionable must stay under it; the two
        full-confidence types must stay at or above it.
        """
        leaked = [
            (row[ALIAS], row[MATCH_TYPE], row[CONFIDENCE])
            for row in country_seed
            if row[MATCH_TYPE] not in FULL_CONFIDENCE_TYPES and row[CONFIDENCE] >= 0.95
        ]
        assert not leaked, (
            f"Questionable mapping(s) at or above the 0.95 audit threshold, so they never "
            f"reach gold_low_confidence_audit for review: {leaked}"
        )
        demoted = [
            (row[ALIAS], row[MATCH_TYPE], row[CONFIDENCE])
            for row in country_seed
            if row[MATCH_TYPE] in FULL_CONFIDENCE_TYPES and row[CONFIDENCE] < 0.95
        ]
        assert not demoted, (
            f"Unambiguous mapping(s) below the 0.95 threshold — they will flood "
            f"gold_low_confidence_audit with rows nobody needs to review: {demoted}"
        )

    @pytest.mark.unit
    def test_the_mojibake_family_is_banded_as_corrupted_encoding(self, country_seed):
        """
        UTF-8-read-as-Latin-1 variants of "Türkiye" (sometimes double-encoded). They must
        all resolve to Turkey at the corrupted_encoding band — never be promoted to
        standard_alias, which would hide a real upstream encoding defect.
        """
        mojibake = [row for row in country_seed
                    if row[MATCH_TYPE] == "corrupted_encoding"]
        assert len(mojibake) >= 4, (
            f"Expected the mojibake family (>= 4 rows); found {len(mojibake)}. Dropping "
            f"variants silently un-maps the corrupted spellings the source emits."
        )
        assert all(row[STANDARD] == "Turkey" for row in mojibake), mojibake
        assert all(row[CONFIDENCE] == 0.80 for row in mojibake), mojibake
        assert all("rkiye" in row[ALIAS] for row in mojibake), (
            f"corrupted_encoding is the Türkiye-family band; a non-Türkiye row here is "
            f"probably mis-banded: {mojibake}"
        )


# ---------------------------------------------------------------------------
# Groups that must be edited as a set
# ---------------------------------------------------------------------------

class TestCriticalGroups:
    @pytest.mark.unit
    def test_congo_spellings_never_collapse_two_countries(self, country_seed):
        """
        `Dem. Rep. Congo` and `Republic of Congo` are different countries. A DRC spelling
        landing on the Republic (or vice versa) attributes cobalt sourcing to the wrong
        country — wrong HHI, wrong risk, no error.
        """
        by_alias = {row[ALIAS]: row[STANDARD] for row in country_seed}
        drc_spellings = [
            "DR Congo", "DRC", "DRC (HQ in South Africa)",
            "Congo, Dem. Rep.", "Congo, D.R.", "Democratic Republic of the Congo",
        ]
        for alias in drc_spellings:
            assert by_alias.get(alias) == "Dem. Rep. Congo", (
                f"{alias!r} resolves to {by_alias.get(alias)!r}, not 'Dem. Rep. Congo'."
            )
        assert by_alias.get("Congo") == "Republic of Congo", (
            "The bare 'Congo' must stay on the Republic at the `ambiguous` band rather than "
            "being guessed into the DRC (alias_mappings.md § Groups that must be edited as "
            "a set)."
        )

    @pytest.mark.unit
    def test_korea_spellings_never_collapse_north_and_south(self, country_seed):
        by_alias = {row[ALIAS]: row[STANDARD] for row in country_seed}
        expected = {
            "Korea, South": "South Korea",
            "Republic of Korea": "South Korea",
            "Korea, Rep.": "South Korea",
            "Korea, North": "North Korea",
            "Korea, Dem. People's Rep.": "North Korea",
        }
        assert {a: by_alias.get(a) for a in expected} == expected
        crossed = [
            row for row in country_seed
            if "Korea" in row[STANDARD]
            and (
                ("North" in row[ALIAS] or "Dem. People" in row[ALIAS])
                != (row[STANDARD] == "North Korea")
            )
        ]
        assert not crossed, f"Korea alias crosses the DPRK/ROK line: {crossed}"


# ---------------------------------------------------------------------------
# Resolution behaviour under Spark
# ---------------------------------------------------------------------------

def _build_lookup(spark, seed, dim_rows):
    """
    Reproduce the `gold_dim_country_lookup` assembly: every dimension name as an exact
    self-lookup at confidence 1.0, UNION the seed inner-joined to the dimension, deduped
    on `lookup_name` by (confidence desc, exact-first, country_key asc).

    Mirrors the notebook's lookup cell so the join semantics under test are the real ones —
    the content invariants above are what pin the seed itself.
    """
    dim = spark.createDataFrame(dim_rows, ["country_key", "country_name_std"])
    aliases = spark.createDataFrame(seed, ["alias", "standard_name", "confidence", "match_type"])

    self_lookup = dim.select(
        F.col("country_name_std").alias("lookup_name"),
        "country_key", "country_name_std",
        F.lit(1.0).alias("match_confidence"),
        F.lit("exact").alias("match_type"),
    )
    alias_lookup = (
        aliases.alias("ca")
        .join(dim.alias("dc"), F.col("ca.standard_name") == F.col("dc.country_name_std"), "inner")
        .select(
            F.col("ca.alias").alias("lookup_name"),
            "dc.country_key", "dc.country_name_std",
            F.col("ca.confidence").alias("match_confidence"),
            F.col("ca.match_type"),
        )
    )
    win = W.partitionBy("lookup_name").orderBy(
        F.col("match_confidence").desc(),
        F.when(F.col("match_type") == "exact", 0).otherwise(1).asc(),
        F.col("country_key").asc(),
    )
    return (
        self_lookup.unionByName(alias_lookup)
        .withColumn("_rn", F.row_number().over(win))
        .filter(F.col("_rn") == 1)
        .drop("_rn")
    )


@pytest.fixture(scope="module")
def resolution(spark, country_seed, dim_names):
    """A country_lookup built from the LIVE seed over a stand-in dimension."""
    dim_rows = [(f"K{i:03d}", name) for i, name in enumerate(sorted(dim_names))]
    lookup = _build_lookup(spark, country_seed, dim_rows).cache()
    yield lookup
    lookup.unpersist()


class TestResolution:
    @pytest.mark.unit
    def test_known_dead_country_names_now_resolve(self, spark, resolution):
        """
        The spellings that historically failed to resolve — plus a representative from each
        deliberately-reduced band — matched the way the fact joins match them: an exact
        string equality against `lookup_name`.
        """
        expected = {
            # task-025: both of these used to miss the dimension entirely
            "Cape Verde": ("Cabo Verde", 0.95),
            "Russian Federation": ("Russia", 0.95),
            # a capital city in the source data, mapped honestly rather than dropped
            "Brasilia": ("Brazil", 0.60),
            # everyday abbreviations
            "USA": ("United States of America", 0.95),
            "UK": ("United Kingdom", 0.95),
            # the reduced-confidence judgement calls still have to RESOLVE
            "Türkiye": ("Turkey", 0.90),
            "TÃ¼rkiye": ("Turkey", 0.80),
            "DRC (HQ in South Africa)": ("Dem. Rep. Congo", 0.85),
            "England": ("United Kingdom", 0.90),
            "Hong Kong": ("China", 0.85),
        }
        src = spark.createDataFrame([(k,) for k in expected], ["source_country"])
        rows = (
            src.join(resolution, src["source_country"] == resolution["lookup_name"], "left")
            .select("source_country", "country_name_std", "match_confidence")
            .collect()
        )
        actual = {r["source_country"]: (r["country_name_std"], r["match_confidence"]) for r in rows}
        assert len(rows) == len(expected), (
            f"Lookup fanned out — {len(rows)} rows for {len(expected)} source values. A "
            f"duplicate lookup_name multiplies every fact row that joins on it."
        )
        assert actual == expected

    @pytest.mark.unit
    def test_tier_one_self_rows_lose_the_tiebreak_to_the_generated_self_lookup(
        self, country_seed, resolution
    ):
        """
        The two Tier-1 `exact_match` seed rows duplicate a `lookup_name` the dimension
        already generates. task-023 made that collision resolve deterministically toward the
        `exact` self-lookup; before it, an arbitrary winner doubled the joined fact rows and
        inflated SUM(spend_eur).
        """
        tier1 = [row[ALIAS] for row in country_seed if row[MATCH_TYPE] == "exact_match"]
        assert tier1, "Expected the Tier-1 exact_match seed rows to still exist"
        won = {
            r["lookup_name"]: r["match_type"]
            for r in resolution.filter(F.col("lookup_name").isin(tier1)).collect()
        }
        assert won == {name: "exact" for name in tier1}, (
            f"Tier-1 seed row(s) beat the generated self-lookup: {won}"
        )

    @pytest.mark.unit
    def test_lookup_name_is_unique(self, resolution):
        """The notebook asserts this inline (task-023). Fail locally too, before a run."""
        dupes = (
            resolution.groupBy("lookup_name").agg(F.count(F.lit(1)).alias("n"))
            .filter(F.col("n") > 1)
            .collect()
        )
        assert not dupes, f"Duplicate lookup_name value(s) — fact joins fan out: {dupes}"

    @pytest.mark.unit
    def test_unmapped_country_surfaces_rather_than_silently_defaulting(
        self, spark, resolution, placeholder_dim_names
    ):
        """
        An unresolvable country must do three things at once: NOT acquire a real country,
        NOT vanish from the fact, and appear in the unmapped audit under its own spelling.

        The audit row is built with the notebook's OWN `unmapped_gap`, loaded from the live
        notebook text — so a change to the audit-row shape breaks this test rather than
        silently changing what `/view-unmapped` and `gold_gap_registry` receive.
        """
        unmapped_gap = load_notebook_functions(GOLD_NOTEBOOK, ["unmapped_gap"])["unmapped_gap"]

        assert "Unknown - Global" in placeholder_dim_names, (
            "The fact_procurement cell resolves the fallback key with "
            "`... WHERE country_name_std = 'Unknown - Global'` and subscripts .first()[0]; "
            "renaming the placeholder in unknown_countries makes that a TypeError at runtime."
        )
        unknown_key = "K_UNK_GLOB"

        src = spark.createDataFrame(
            [("USA",), ("Wakanda",), ("Kongo",)], ["source_country"]
        )
        joined = src.join(
            resolution, src["source_country"] == resolution["lookup_name"], "left"
        )
        resolved = (
            joined
            # the notebook's placeholder fallback: no data loss, but never a real country
            .withColumn(
                "country_key_final",
                F.when(F.col("country_key").isNull(), F.lit(unknown_key))
                .otherwise(F.col("country_key")),
            )
            .withColumn(
                "gap",
                unmapped_gap(
                    F.col("country_key").isNull(),
                    "hq_country",
                    "country",
                    F.col("source_country"),
                ),
            )
            .select("source_country", "country_name_std", "country_key_final", "gap")
            .collect()
        )
        by_src = {r["source_country"]: r for r in resolved}
        assert len(resolved) == 3, "Fallback dropped or duplicated a source row"

        # 1. the mapped value resolves and raises no audit row
        assert by_src["USA"]["country_name_std"] == "United States of America"
        assert by_src["USA"]["gap"] is None, (
            "A successfully-mapped country produced an audit row — the gap registry would "
            "fill with false positives."
        )

        # 2. the unmapped values are NOT silently attached to a real country
        for miss in ("Wakanda", "Kongo"):
            assert by_src[miss]["country_name_std"] is None, (
                f"{miss!r} resolved to {by_src[miss]['country_name_std']!r}. An unmapped "
                f"country must never acquire a real one — note 'Kongo' is deliberately "
                f"close to the Congo aliases: resolution is exact-match, not fuzzy."
            )
            # 3. the row survives into the fact on the placeholder key
            assert by_src[miss]["country_key_final"] == unknown_key
            # 4. and it surfaces in the audit under its OWN spelling
            gap = by_src[miss]["gap"]
            assert gap is not None, f"{miss!r} produced no unmapped audit row"
            assert gap["unmapped_type"] == "hq_country"
            assert gap["gap_dimension"] == "country"
            assert gap["unmapped_value"] == miss, (
                f"Audit row carries {gap['unmapped_value']!r} instead of the value that "
                f"failed to join ({miss!r}) — task-027 fixed exactly this: the registry used "
                f"to COALESCE across dimensions and filed country gaps under material names."
            )


# ---------------------------------------------------------------------------
# Placeholder wiring
# ---------------------------------------------------------------------------

_PLACEHOLDER_PREDICATE = re.compile(r"country_name_std\s*=\s*'([^']+)'")


@pytest.mark.unit
def test_placeholder_names_used_in_sql_exist_in_the_dimension_seed(placeholder_dim_names):
    """
    Every literal `country_name_std = '<name>'` in the notebook is a placeholder lookup whose
    result is subscripted (`.first()[0]`). If the name drifts from `unknown_countries`, the
    query returns no row and the notebook dies with `TypeError: 'NoneType' object is not
    subscriptable` — mid-run, after the dimensions are already written.
    """
    referenced = set(_PLACEHOLDER_PREDICATE.findall(_notebook_source()))
    assert referenced, (
        "Positive control failed: no literal country_name_std predicate found in the "
        "notebook, so this guard is inert. Re-target it rather than deleting it."
    )
    missing = sorted(referenced - placeholder_dim_names)
    assert not missing, (
        f"Notebook SQL selects country_name_std value(s) the unknown_countries seed does not "
        f"define: {missing}. The .first()[0] subscript raises TypeError at runtime."
    )
