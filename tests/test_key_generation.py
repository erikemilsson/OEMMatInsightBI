"""
Unit tests for surrogate key generation functions.

Tests the stable_key() function and related key generation utilities
to ensure consistent, reproducible surrogate key creation.

Includes TestNotebookParity, which enforces the reference-implementation contract
declared in src/transformations/key_generation.py: the Fabric notebooks duplicate
this logic inline, so the two must be proven identical rather than assumed so.
"""

import ast
from pathlib import Path

import pytest
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType, DateType, IntegerType
from datetime import date

from src.transformations.key_generation import (
    stable_key,
    generate_country_key,
    generate_material_key,
    generate_date_key
)

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLD_NOTEBOOK = REPO_ROOT / "fabric" / "silver-to-gold2.Notebook" / "notebook-content.py"


def load_notebook_functions(names, extra_globals=None):
    """
    Extract named top-level functions from a Fabric notebook's source, without
    executing the notebook.

    The notebook file is valid Python (markdown cells are comments), so it can be
    parsed with `ast` and only the requested FunctionDef nodes compiled. That
    keeps the parity check bound to the *live* notebook text — if someone edits
    the notebook's key logic, these tests fail on the next run, which is the
    whole point of the reference-implementation contract.

    Args:
        names: Function names to extract, in dependency order (a function that
            calls another must come after it).
        extra_globals: Optional module-level names the extracted function reads
            from the notebook's global scope (e.g. the LOG_UNMAPPED /
            FAIL_ON_UNMAPPED config flags), since only the FunctionDefs are
            compiled.

    Returns:
        dict[str, callable]: the extracted functions, sharing one namespace so
        inter-function calls resolve to the notebook's own definitions.
    """
    assert GOLD_NOTEBOOK.exists(), f"Notebook not found: {GOLD_NOTEBOOK}"

    tree = ast.parse(GOLD_NOTEBOOK.read_text(encoding="utf-8"), filename=str(GOLD_NOTEBOOK))
    found = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in set(names)
    }

    missing = [n for n in names if n not in found]
    assert not missing, (
        f"Notebook no longer defines {missing} at top level — the parity harness "
        f"cannot verify src/ against production. Update the harness (or restore "
        f"the notebook definitions) rather than deleting this test."
    )

    module = ast.Module(body=[found[n] for n in names], type_ignores=[])
    ast.fix_missing_locations(module)

    namespace = {"F": F}
    if extra_globals:
        namespace.update(extra_globals)
    exec(compile(module, str(GOLD_NOTEBOOK), "exec"), namespace)  # noqa: S102

    return {n: namespace[n] for n in names}


def country_fixture(spark):
    """Country rows covering every branch of the iso3-preferred key contract."""
    schema = StructType([
        StructField("iso3", StringType(), True),
        StructField("country_name", StringType(), True),
    ])
    data = [
        ("USA", "United States"),
        ("USA", "US"),                  # same iso3, different spelling
        ("TUR", "Turkey"),              # curated spelling (missing_countries)
        ("TUR", "Türkiye"),             # EPI spelling — must collide with above
        ("CHN", "China"),
        ("UNK_GLOB", "Unknown - Global"),   # placeholder sentinel iso3
        (None, "Kosovo"),               # null iso3 -> name fallback
        (None, "Atlantis"),
        (None, None),                   # both null -> sentinel hash
    ]
    return spark.createDataFrame(data, schema)


class TestStableKey:
    """Tests for stable_key() function."""

    @pytest.mark.unit
    def test_stable_key_consistency(self, spark):
        """Test that stable_key generates consistent hash for same input."""
        data = [("USA", "United States")]
        df = spark.createDataFrame(data, ["iso3", "country_name"])

        # Generate key twice
        result1 = df.withColumn("key", stable_key("iso3"))
        result2 = df.withColumn("key", stable_key("iso3"))

        # Keys should be identical
        key1 = result1.collect()[0]["key"]
        key2 = result2.collect()[0]["key"]

        assert key1 == key2, "stable_key should produce consistent results"
        assert key1 > 0, "Key should be positive"

    @pytest.mark.unit
    def test_stable_key_uniqueness(self, spark):
        """Test that stable_key generates different hashes for different inputs."""
        data = [
            ("USA", "United States"),
            ("CHN", "China"),
            ("DEU", "Germany")
        ]
        df = spark.createDataFrame(data, ["iso3", "country_name"])

        result = df.withColumn("key", stable_key("iso3"))
        keys = [row["key"] for row in result.collect()]

        # All keys should be unique
        assert len(keys) == len(set(keys)), "Different inputs should produce different keys"

    @pytest.mark.unit
    def test_stable_key_multi_column(self, spark):
        """Test stable_key with multiple columns."""
        data = [
            ("Lithium", "Battery Materials"),
            ("Lithium", "Pharmaceuticals"),  # Same material, different category
            ("Copper", "Base Metals")
        ]
        df = spark.createDataFrame(data, ["material", "category"])

        result = df.withColumn("key", stable_key("material", "category"))
        keys = [row["key"] for row in result.collect()]

        # All composite keys should be unique
        assert len(keys) == len(set(keys))

        # Single column key should differ from multi-column key
        result_single = df.withColumn("key", stable_key("material"))
        key_single = result_single.collect()[0]["key"]

        assert key_single != keys[0], "Single column key should differ from composite"

    @pytest.mark.unit
    def test_stable_key_null_handling(self, spark):
        """Test that stable_key handles null values consistently."""
        data = [
            ("USA", None),
            ("USA", None),  # Duplicate row with null
            ("CHN", "China")
        ]
        df = spark.createDataFrame(data, ["iso3", "country_name"])

        result = df.withColumn("key", stable_key("iso3", "country_name"))
        keys = [row["key"] for row in result.collect()]

        # Rows with same values (including nulls) should have same key
        assert keys[0] == keys[1], "Null values should be handled consistently"
        assert keys[0] != keys[2], "Different values should produce different keys"

    @pytest.mark.unit
    def test_stable_key_empty_string(self, spark):
        """Test stable_key behavior with empty strings vs nulls."""
        data = [
            ("USA", ""),      # Empty string
            ("USA", None),    # Null
            ("USA", "USA")    # Value
        ]
        df = spark.createDataFrame(data, ["iso3", "name"])

        result = df.withColumn("key", stable_key("iso3", "name"))
        keys = [row["key"] for row in result.collect()]

        # Empty string and null should produce different keys
        assert keys[0] != keys[1], "Empty string should differ from null"
        assert keys[1] != keys[2], "Null should differ from value"
        assert keys[0] != keys[2], "Empty string should differ from value"

    @pytest.mark.unit
    def test_stable_key_error_on_no_columns(self):
        """Test that stable_key raises error with no columns."""
        with pytest.raises(ValueError, match="At least one column"):
            stable_key()


class TestGenerateCountryKey:
    """Tests for generate_country_key() function."""

    @pytest.mark.unit
    def test_generate_country_key(self, spark):
        """Test country key generation with ISO3 code."""
        data = [("USA", "United States")]
        df = spark.createDataFrame(data, ["iso3", "country_name"])

        result = df.withColumn("country_key", generate_country_key("iso3", "country_name"))

        assert result.count() == 1
        assert result.collect()[0]["country_key"] > 0

    @pytest.mark.unit
    def test_generate_country_key_consistency(self, spark):
        """Same ISO3 must produce the same key even when the name differs.

        The production contract is iso3-PREFERRED, not composite: when iso3 is
        present the name does not participate in the hash. dim_country's
        precedence dedupe (task-025) depends on the curated row and the EPI row
        for one iso3 colliding on country_key.
        """
        data = [
            ("USA", "United States"),
            ("USA", "US"),  # Different name, same ISO3
        ]
        df = spark.createDataFrame(data, ["iso3", "country_name"])

        result = df.withColumn("country_key", generate_country_key("iso3", "country_name"))
        keys = [row["country_key"] for row in result.collect()]

        assert keys[0] == keys[1], (
            "Same ISO3 must yield the same country_key regardless of name — "
            "a composite iso3+name key would re-key every country and silently "
            "break all fact-dim joins."
        )

    @pytest.mark.unit
    def test_country_key_ignores_name_when_iso3_present(self, spark):
        """With a non-null ISO3, the key equals stable_key(iso3) alone."""
        data = [("TUR", "Turkey"), ("TUR", "Türkiye")]
        df = spark.createDataFrame(data, ["iso3", "country_name"])

        result = df.withColumn(
            "country_key", generate_country_key("iso3", "country_name")
        ).withColumn("iso3_only_key", stable_key("iso3"))

        rows = result.collect()

        # Name is not part of the hash at all.
        assert rows[0]["country_key"] == rows[0]["iso3_only_key"]
        assert rows[1]["country_key"] == rows[1]["iso3_only_key"]
        # ...and the curated/EPI spellings of TUR therefore collide, which is
        # exactly what the dim_country dedupe resolves deterministically.
        assert rows[0]["country_key"] == rows[1]["country_key"]

    @pytest.mark.unit
    def test_country_key_falls_back_to_name_when_iso3_null(self, spark):
        """With a null ISO3, the key equals stable_key(name)."""
        schema = StructType([
            StructField("iso3", StringType(), True),
            StructField("country_name", StringType(), True),
        ])
        df = spark.createDataFrame(
            [(None, "Kosovo"), (None, "Kosovo"), (None, "Atlantis")], schema
        )

        result = df.withColumn(
            "country_key", generate_country_key("iso3", "country_name")
        ).withColumn("name_only_key", stable_key("country_name"))

        rows = result.collect()

        assert rows[0]["country_key"] == rows[0]["name_only_key"], (
            "Null ISO3 must fall back to hashing the country name"
        )
        assert rows[0]["country_key"] == rows[1]["country_key"], (
            "Same fallback name must be stable across rows"
        )
        assert rows[0]["country_key"] != rows[2]["country_key"], (
            "Different fallback names must produce different keys"
        )

    @pytest.mark.unit
    def test_country_key_distinct_across_iso3(self, spark):
        """Different ISO3 codes must produce different keys."""
        data = [("USA", "United States"), ("CHN", "China"), ("DEU", "Germany")]
        df = spark.createDataFrame(data, ["iso3", "country_name"])

        result = df.withColumn("country_key", generate_country_key("iso3", "country_name"))
        keys = [row["country_key"] for row in result.collect()]

        assert len(keys) == len(set(keys))
        assert all(k > 0 for k in keys)


class TestGenerateMaterialKey:
    """Tests for generate_material_key() function."""

    @pytest.mark.unit
    def test_generate_material_key(self, spark):
        """Test material key generation."""
        data = [("Lithium",), ("Copper",), ("Aluminum",)]
        df = spark.createDataFrame(data, ["material_name_std"])

        result = df.withColumn("material_key", generate_material_key("material_name_std"))
        keys = [row["material_key"] for row in result.collect()]

        # All keys should be unique and positive
        assert len(keys) == len(set(keys))
        assert all(k > 0 for k in keys)


class TestGenerateDateKey:
    """Tests for generate_date_key() function."""

    @pytest.mark.unit
    def test_generate_date_key(self, spark):
        """Test date key generation in YYYYMMDD format."""
        data = [(date(2024, 1, 15),), (date(2024, 12, 31),), (date(2023, 3, 5),)]
        df = spark.createDataFrame(data, ["order_date"])

        result = df.withColumn("date_key", generate_date_key("order_date"))
        date_keys = [row["date_key"] for row in result.collect()]

        # Check format: YYYYMMDD
        assert date_keys[0] == 20240115
        assert date_keys[1] == 20241231
        assert date_keys[2] == 20230305

    @pytest.mark.unit
    def test_generate_date_key_type(self, spark):
        """Test that date key is integer type."""
        data = [(date(2024, 1, 15),)]
        df = spark.createDataFrame(data, ["order_date"])

        result = df.withColumn("date_key", generate_date_key("order_date"))

        # Check schema
        date_key_type = result.schema["date_key"].dataType
        assert isinstance(date_key_type, IntegerType)


class TestKeyCollisions:
    """Tests to verify low collision rates for keys."""

    @pytest.mark.unit
    def test_no_collisions_in_sample_countries(self, spark, sample_country_data):
        """Test that sample country data produces unique keys."""
        result = sample_country_data.withColumn(
            "country_key",
            stable_key("iso3")
        )

        keys = [row["country_key"] for row in result.collect()]

        # No collisions expected in small dataset
        assert len(keys) == len(set(keys))

    @pytest.mark.unit
    def test_no_collisions_in_sample_materials(self, spark, sample_material_data):
        """Test that sample material data produces unique keys."""
        result = sample_material_data.withColumn(
            "material_key",
            stable_key("material_name")
        )

        keys = [row["material_key"] for row in result.collect()]

        # No collisions expected in small dataset
        assert len(keys) == len(set(keys))


class TestNotebookParity:
    """
    Parity guard for the reference-implementation contract (task-032).

    The Fabric notebooks cannot import `src/`, so `src.transformations.key_generation`
    is documented as the REFERENCE implementation of logic that lives inline in
    `fabric/silver-to-gold2.Notebook`. These tests parse the notebook, run its own
    definitions, and require identical output — so silent divergence fails CI
    instead of being discovered as unmatched relationships in Power BI.
    """

    @pytest.mark.unit
    def test_stable_key_parity_with_notebook(self, spark):
        """src.stable_key matches the notebook's inline stable_key."""
        nb = load_notebook_functions(["stable_key"])
        nb_stable_key = nb["stable_key"]

        df = country_fixture(spark)

        # Notebook signature takes a list; src accepts a list or varargs.
        result = (df
                  .withColumn("nb_single", nb_stable_key(["iso3"]))
                  .withColumn("src_single", stable_key("iso3"))
                  .withColumn("src_single_list", stable_key(["iso3"]))
                  .withColumn("nb_multi", nb_stable_key(["iso3", "country_name"]))
                  .withColumn("src_multi", stable_key("iso3", "country_name")))

        for row in result.collect():
            assert row["nb_single"] == row["src_single"], f"single-column drift on {row['iso3']!r}"
            assert row["src_single_list"] == row["src_single"], "list/varargs forms must agree"
            assert row["nb_multi"] == row["src_multi"], f"multi-column drift on {row['iso3']!r}"

    @pytest.mark.unit
    def test_generate_country_key_parity_with_notebook(self, spark):
        """src.generate_country_key matches the notebook's inline version.

        This is the test that would have caught the original defect: src hashed
        iso3 AND name together while production hashed iso3 alone.
        """
        nb = load_notebook_functions(["stable_key", "generate_country_key"])
        nb_country_key = nb["generate_country_key"]

        df = country_fixture(spark)

        result = (df
                  .withColumn("nb_key", nb_country_key("iso3", "country_name"))
                  .withColumn("src_key", generate_country_key("iso3", "country_name")))

        mismatches = [
            (row["iso3"], row["country_name"], row["nb_key"], row["src_key"])
            for row in result.collect()
            if row["nb_key"] != row["src_key"]
        ]

        assert not mismatches, (
            "src/transformations/key_generation.generate_country_key has drifted "
            f"from fabric/silver-to-gold2.Notebook: {mismatches}. Align src TO the "
            "notebook — never the reverse; the notebook's keys are already "
            "materialized in the gold Delta tables."
        )

    @pytest.mark.unit
    def test_country_key_golden_values(self, spark):
        """Pin actual key values so a change to BOTH implementations still fails.

        Parity alone cannot catch an edit applied to the notebook and src at the
        same time (e.g. a different null sentinel or an added salt). These
        constants are the keys the existing gold_dim_country rows were built
        with; changing them silently re-keys every fact-dim relationship.
        """
        schema = StructType([
            StructField("iso3", StringType(), True),
            StructField("country_name", StringType(), True),
        ])
        expected = {
            ("USA", "United States"): 2495174926603723698,
            ("TUR", "Türkiye"): 5291645484684744615,
            ("UNK_GLOB", "Unknown - Global"): 2182860759765913374,
            (None, "Kosovo"): 3499860001858543104,
        }
        df = spark.createDataFrame(list(expected.keys()), schema)

        result = df.withColumn("country_key", generate_country_key("iso3", "country_name"))

        actual = {(row["iso3"], row["country_name"]): row["country_key"] for row in result.collect()}

        assert actual == expected, (
            "country_key values changed. Every gold fact-dim join is keyed on "
            "these hashes; a change here requires a full gold rebuild, not a "
            "fixture update."
        )

    @pytest.mark.unit
    def test_material_key_golden_value(self, spark):
        """Pin the material key hash for the same reason as country keys."""
        df = spark.createDataFrame([("Lithium",)], ["material_name_std"])

        key = df.withColumn(
            "material_key", generate_material_key("material_name_std")
        ).collect()[0]["material_key"]

        assert key == 330553000305089562
