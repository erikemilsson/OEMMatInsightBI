"""
Pytest configuration and fixtures for OEMMatInsightBI tests.

This module provides shared fixtures for unit and integration tests,
including SparkSession setup and sample data generators.
"""

import os
import sys

import pytest
from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, DateType
from datetime import date

# Pin PySpark's worker interpreter to the one running the tests.
#
# Without this, Spark launches Python workers via whatever bare `python3` is
# first on PATH, which is NOT necessarily the driver interpreter. When they
# differ, every Spark action dies with Py4JJavaError wrapping
# PYTHON_VERSION_MISMATCH — a traceback that reads exactly like a code defect
# and sends you hunting through transformation logic that is fine.
#
# Observed 2026-08-12: a run in this repo reported 143 failed / 157 passed,
# all from this cause (worker 3.9 vs driver 3.12), after a python.org 3.13
# framework install was removed and `python3` fell through to macOS's
# /usr/bin/python3. Setting these two vars produced 300/300 with no code change.
#
# setdefault, not assignment — an explicit override in the environment wins.
os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)


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
            # Match Fabric's Spark runtime (task-029 / root CLAUDE.md gotcha): local
            # pyspark 4.0.1 defaults ANSI mode ON; Fabric's Spark 3.4/3.5 defaults it
            # OFF. Cast semantics diverge under exactly the conditions transformation
            # code cares about (a malformed Year or unparseable amount silently becomes
            # NULL in Fabric but raises SparkNumberFormatException locally). Tests left
            # on the local default pass/fail for reasons the real runtime never
            # reproduces, and in the dangerous direction (local raises where Fabric
            # quietly nulls, so a "fix" targets a non-bug and misses the real null
            # propagation). Set OFF so local behavior matches the target runtime.
            .config("spark.sql.ansi.enabled", "false")
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
