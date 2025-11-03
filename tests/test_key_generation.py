"""
Unit tests for surrogate key generation functions.

Tests the stable_key() function and related key generation utilities
to ensure consistent, reproducible surrogate key creation.
"""

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
        """Test that same ISO3 always produces same country key."""
        data = [
            ("USA", "United States"),
            ("USA", "US"),  # Different name, same ISO3
        ]
        df = spark.createDataFrame(data, ["iso3", "country_name"])

        result = df.withColumn("country_key", generate_country_key("iso3", "country_name"))
        keys = [row["country_key"] for row in result.collect()]

        # Keys should be different because name differs (both columns used in hash)
        assert keys[0] != keys[1]


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
