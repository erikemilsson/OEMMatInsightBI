"""
Pytest configuration and fixtures for OEMMatInsightBI tests.

This module provides shared fixtures for unit and integration tests,
including SparkSession setup and sample data generators.
"""

import pytest
from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, IntegerType, DateType
from datetime import date


@pytest.fixture(scope="session")
def spark():
    """
    Create a SparkSession for testing.

    Scope: session - SparkSession is created once per test session.
    Yields: SparkSession configured for local testing.
    """
    spark = (SparkSession.builder
            .master("local[2]")
            .appName("OEMMatInsightBI-Tests")
            .config("spark.sql.shuffle.partitions", "2")  # Reduce partitions for tests
            .config("spark.default.parallelism", "2")
            .getOrCreate())

    # Set log level to WARN to reduce test output noise
    spark.sparkContext.setLogLevel("WARN")

    yield spark

    # Cleanup: Stop SparkSession after all tests
    spark.stop()


@pytest.fixture
def sample_procurement_data(spark):
    """
    Create sample procurement DataFrame for testing.

    Returns:
        DataFrame with columns: Date, MaterialName, SupplierName, Region,
                               Quantity, Unit, UnitPriceEUR
    """
    schema = StructType([
        StructField("Date", DateType(), False),
        StructField("MaterialName", StringType(), False),
        StructField("SupplierName", StringType(), False),
        StructField("Region", StringType(), False),
        StructField("Quantity", DoubleType(), False),
        StructField("Unit", StringType(), False),
        StructField("UnitPriceEUR", DoubleType(), False)
    ])

    data = [
        (date(2024, 1, 15), "Lithium", "Acme Corp", "Americas", 1000.0, "kg", 45.5),
        (date(2024, 1, 16), "Copper", "Global Metals", "Europe", 500.0, "t", 8000.0),
        (date(2024, 1, 17), "Aluminum", "Asia Suppliers", "Asia", 2500.0, "kg", 2.5)
    ]

    return spark.createDataFrame(data, schema)


@pytest.fixture
def sample_country_data(spark):
    """
    Create sample country reference DataFrame for testing.

    Returns:
        DataFrame with columns: iso3, country_name, region
    """
    schema = StructType([
        StructField("iso3", StringType(), False),
        StructField("country_name", StringType(), False),
        StructField("region", StringType(), False)
    ])

    data = [
        ("USA", "United States", "Americas"),
        ("CHN", "China", "Asia"),
        ("DEU", "Germany", "Europe"),
        ("JPN", "Japan", "Asia"),
        ("GBR", "United Kingdom", "Europe")
    ]

    return spark.createDataFrame(data, schema)


@pytest.fixture
def sample_material_data(spark):
    """
    Create sample material reference DataFrame for testing.

    Returns:
        DataFrame with columns: material_name, commodity_group
    """
    schema = StructType([
        StructField("material_name", StringType(), False),
        StructField("commodity_group", StringType(), False)
    ])

    data = [
        ("Lithium", "Battery Materials"),
        ("Copper", "Base Metals"),
        ("Aluminum", "Base Metals"),
        ("Nickel", "Base Metals"),
        ("Cobalt", "Battery Materials")
    ]

    return spark.createDataFrame(data, schema)


@pytest.fixture
def sample_epi_scores(spark):
    """
    Create sample EPI (Environmental Performance Index) scores for testing.

    Returns:
        DataFrame with columns: country_key, indicator_key, year, score
    """
    schema = StructType([
        StructField("country_key", IntegerType(), False),
        StructField("indicator_key", IntegerType(), False),
        StructField("year", IntegerType(), False),
        StructField("score", DoubleType(), False)
    ])

    data = [
        (1, 1, 2024, 85.5),
        (1, 2, 2024, 72.3),
        (2, 1, 2024, 45.2),
        (2, 2, 2024, 38.9),
        (3, 1, 2024, 90.1)
    ]

    return spark.createDataFrame(data, schema)


@pytest.fixture
def sample_country_aliases(spark):
    """
    Create sample country alias lookup data for testing.

    Returns:
        DataFrame with columns: alias, country_name_std, iso3, confidence
    """
    schema = StructType([
        StructField("alias", StringType(), False),
        StructField("country_name_std", StringType(), False),
        StructField("iso3", StringType(), False),
        StructField("confidence", DoubleType(), False)
    ])

    data = [
        ("USA", "United States", "USA", 1.0),
        ("United States", "United States", "USA", 1.0),
        ("United States of America", "United States", "USA", 1.0),
        ("US", "United States", "USA", 0.95),
        ("China", "China", "CHN", 1.0),
        ("People's Republic of China", "China", "CHN", 0.95),
        ("PRC", "China", "CHN", 0.85)
    ]

    return spark.createDataFrame(data, schema)


@pytest.fixture
def empty_dataframe(spark):
    """
    Create an empty DataFrame for testing edge cases.

    Returns:
        Empty DataFrame with string columns: col1, col2
    """
    schema = StructType([
        StructField("col1", StringType(), True),
        StructField("col2", StringType(), True)
    ])

    return spark.createDataFrame([], schema)
