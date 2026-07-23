"""
Reachability tests for the gold material mapping (task-028).

The gold notebook initcap()s every material name BEFORE matching it against the
commodity-group map and the material-alias table:

    F.initcap(F.trim("materialname"))   # silver_procurement
    F.initcap(F.trim("material"))       # silver_globalsupplyshares

Spark's ``initcap`` uppercases the first character of each whitespace-delimited word
and lowercases everything else in that word — including letters after '(' and '-'.
So "Steel (High-Tensile)" arrives as "Steel (high-tensile)" and "Plastic (ABS)" as
"Plastic (abs)".

Consequence: any commodity-group key or alias LHS that is not its own initcap can
never be matched by any input. Materials silently classify as "Other/Unknown" and
aliases silently never fire — no error, no warning, just wrong commodity groups in
dim_material and in every report grouped by them. That defect shipped three times
(Steel (High-Tensile), Plastic (ABS), Rare Earths (NdPr)), and twice someone
hand-tuned a single key to initcap's output without noticing it was a class of bug.

These tests turn that class into a build failure. They read the LIVE notebook text via
``ast`` — no notebook execution, no lakehouse — so editing the notebook's mapping
tables is what makes them fail, which is the whole point.

The gold notebook carries the same assertion inline (next to ``grp_map``) so a Fabric
run fails too. This file is the local/CI half of the same contract; keep both.
"""

import ast
from pathlib import Path

import pytest
from pyspark.sql import functions as F

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLD_NOTEBOOK = REPO_ROOT / "fabric" / "silver-to-gold2.Notebook" / "notebook-content.py"


def _notebook_tree():
    assert GOLD_NOTEBOOK.exists(), f"Notebook not found: {GOLD_NOTEBOOK}"
    return ast.parse(GOLD_NOTEBOOK.read_text(encoding="utf-8"), filename=str(GOLD_NOTEBOOK))


def _literal_assignment(name):
    """
    Return the literal value assigned to a top-level ``name`` in the notebook.

    Uses ``ast.literal_eval`` rather than exec so the notebook's Spark calls are never
    touched. Requires the target to be a plain literal (dict / list of tuples), which is
    exactly why task-028 moved the mapping tables out of inline ``F.lit()`` pairs and
    into ``COMMODITY_GROUPS`` / ``MATERIAL_ALIASES``: a guard cannot enumerate keys it
    cannot read.
    """
    for node in _notebook_tree().body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(
        f"Notebook no longer defines a literal top-level `{name}`. The reachability "
        f"guard cannot enumerate the mapping keys. Restore the literal (or update this "
        f"harness deliberately) rather than deleting this test."
    )


@pytest.fixture(scope="module")
def commodity_groups():
    return _literal_assignment("COMMODITY_GROUPS")


@pytest.fixture(scope="module")
def material_aliases():
    return _literal_assignment("MATERIAL_ALIASES")


def _initcap(spark, values):
    """Real Spark initcap over ``values`` -> {original: initcap(original)}."""
    values = sorted(set(values))
    rows = (
        spark.createDataFrame([(v,) for v in values], ["v"])
        .select("v", F.initcap(F.col("v")).alias("ic"))
        .collect()
    )
    return {r["v"]: r["ic"] for r in rows}


class TestInitcapReachability:
    """Every mapping key must survive the initcap() applied to its inputs."""

    @pytest.mark.unit
    def test_commodity_group_keys_are_initcap_stable(self, spark, commodity_groups):
        assert commodity_groups, "COMMODITY_GROUPS is empty"
        ic = _initcap(spark, commodity_groups.keys())
        dead = {k: ic[k] for k in commodity_groups if ic[k] != k}
        assert not dead, (
            "Commodity-group key(s) unreachable — material_name_std is initcap'd before "
            "the map lookup, so these can never match and their materials fall through "
            "to 'Other/Unknown': "
            + ", ".join(f"{k!r} (initcap -> {v!r})" for k, v in sorted(dead.items()))
        )

    @pytest.mark.unit
    def test_material_alias_lhs_are_initcap_stable(self, spark, material_aliases):
        assert material_aliases, "MATERIAL_ALIASES is empty"
        lhs = [row[0] for row in material_aliases]
        ic = _initcap(spark, lhs)
        dead = {a: ic[a] for a in lhs if ic[a] != a}
        assert not dead, (
            "Material alias LHS unreachable — source material names are initcap'd before "
            "the alias join, so these rows can never fire: "
            + ", ".join(f"{k!r} (initcap -> {v!r})" for k, v in sorted(dead.items()))
            + ". Case-only variants never need an alias row; initcap collapses them."
        )

    @pytest.mark.unit
    def test_guard_actually_detects_an_unreachable_key(self, spark):
        """
        Positive control: prove the probe can fail.

        A guard that only ever reports 'nothing wrong' is indistinguishable from a guard
        that is silently broken, so assert that known-bad spellings — the exact three that
        shipped as dead keys — are still detected as unreachable, and that a known-good
        one is not.
        """
        bad = ["Steel (High-Tensile)", "Plastic (ABS)", "Rare Earths (NdPr)"]
        good = ["Steel (high-tensile)", "Plastic (abs)", "Rare Earths (ndpr)"]
        ic = _initcap(spark, bad + good)
        assert all(ic[b] != b for b in bad), f"probe failed to flag known-bad keys: {ic}"
        assert all(ic[g] == g for g in good), f"probe wrongly flagged good keys: {ic}"


class TestMappingContent:
    """Content invariants the reachability guard cannot express on its own."""

    @pytest.mark.unit
    def test_known_dead_materials_now_resolve_to_a_commodity_group(self, spark, commodity_groups):
        """
        The three materials that used to classify as Other/Unknown must now resolve —
        matched the way the notebook matches them, i.e. through initcap.
        """
        expected = {
            "Steel (High-Tensile)": "Manufactured products",
            "STEEL (HIGH-TENSILE)": "Manufactured products",
            "Plastic (ABS)": "Manufactured products",
            "Rare Earths (NdPr)": "Rare earth elements",
            # already-correct spellings must keep working
            "Electronics (Controllers, Sensors)": "Manufactured products",
            "iron ore": "Base metals",
        }
        ic = _initcap(spark, expected.keys())
        actual = {raw: commodity_groups.get(ic[raw], "Other/Unknown") for raw in expected}
        assert actual == expected

    @pytest.mark.unit
    def test_alias_targets_exist_in_the_commodity_map(self, commodity_groups, material_aliases):
        """
        An alias resolves a material to its standard name; that standard name is what
        gets probed against COMMODITY_GROUPS. A target missing from the map silently
        downgrades the material to Other/Unknown.
        """
        missing = sorted({row[1] for row in material_aliases} - set(commodity_groups))
        assert not missing, (
            f"Alias target(s) absent from COMMODITY_GROUPS, so aliased materials land in "
            f"'Other/Unknown': {missing}"
        )

    @pytest.mark.unit
    def test_phosphorus_spellings_are_unified(self, commodity_groups, material_aliases):
        """
        task-028 / alias_mappings.md § Spelling Variants: the two spellings must collapse
        to ONE dim_material row, and must agree on the commodity group so the collapse is
        lossless.
        """
        by_alias = {row[0]: row[1] for row in material_aliases}
        assert by_alias.get("Phosphorus") == "Phosphorous", (
            "Missing the Phosphorus -> Phosphorous alias; both spellings would enter "
            "dim_material as distinct materials."
        )
        assert "Phosphorous" not in by_alias, (
            "Both spellings alias to each other — dim_material resolution would depend on "
            "join order. Pick one canonical spelling."
        )
        assert commodity_groups["Phosphorus"] == commodity_groups["Phosphorous"]

    @pytest.mark.unit
    def test_no_alias_is_its_own_target(self, material_aliases):
        """
        A self-alias is a no-op row that also collides with the exact self-lookup in
        gold_dim_material_lookup. The three rows removed by task-028 were all effectively
        this (after initcap, LHS == RHS).
        """
        selfies = [row[0] for row in material_aliases if row[0] == row[1]]
        assert not selfies, f"Redundant self-alias row(s): {selfies}"
