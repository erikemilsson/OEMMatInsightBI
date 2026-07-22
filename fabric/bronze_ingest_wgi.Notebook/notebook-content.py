# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "488fb9f8-e635-4683-90c4-ba4fee9dfadb",
# META       "default_lakehouse_name": "oem_lh",
# META       "default_lakehouse_workspace_id": "99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9",
# META       "known_lakehouses": [
# META         {
# META           "id": "488fb9f8-e635-4683-90c4-ba4fee9dfadb"
# META         }
# META       ]
# META     }
# META   }
# META }

# MARKDOWN ********************

# # bronze_ingest_wgi
# # Automated ingestion of World Governance Indicators (WGI) data from the World Bank API.
# Replaces manual CSV upload via WGI_file2table.Dataflow.
# # **Source:** World Bank API v2 (https://api.worldbank.org/v2/)
# **Target:** bronze_WGI (Delta table, overwrite)
# **License:** World Bank Open Data (commercial use permitted)
# **Update frequency:** Annual (typically September)
# # Retrieves all 6 WGI dimensions (estimate scores):
# - CC.EST: Control of Corruption
# - GE.EST: Government Effectiveness
# - PV.EST: Political Stability and Absence of Violence
# - RL.EST: Rule of Law
# - RQ.EST: Regulatory Quality
# - VA.EST: Voice and Accountability
# # Attribution: Worldwide Governance Indicators, The World Bank Group

# CELL ********************

# Pipeline parameters — overridden by Fabric pipeline at runtime
p_start_year = "1996"
p_end_year = "2023"

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

import requests
import json
import time
from pyspark.sql import functions as F
from pyspark.sql import Row
from pyspark.sql.types import StructType, StructField, StringType, DoubleType
from datetime import datetime

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Configuration

# CELL ********************

# WGI indicator codes — all 6 governance dimensions (estimate scores)
WGI_INDICATORS = {
    "CC.EST": "Control of Corruption: Estimate",
    "GE.EST": "Government Effectiveness: Estimate",
    "PV.EST": "Political Stability and Absence of Violence/Terrorism: Estimate",
    "RL.EST": "Rule of Law: Estimate",
    "RQ.EST": "Regulatory Quality: Estimate",
    "VA.EST": "Voice and Accountability: Estimate",
}

# World Bank API v2 base URL
API_BASE = "https://api.worldbank.org/v2"

# Date range from parameters
start_year = p_start_year.strip()
end_year = p_end_year.strip()

print(f"WGI Ingestion: Fetching {len(WGI_INDICATORS)} indicators for {start_year}-{end_year}")
for code, name in WGI_INDICATORS.items():
    print(f"  - {code}: {name}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Fetch data from World Bank API

# CELL ********************

def fetch_indicator(indicator_code, start_year, end_year, max_retries=3):
    """
    Fetch all country data for a single WGI indicator from the World Bank API.
    Uses JSON format with pagination.

    Returns a list of dicts with keys: country_name, country_code, indicator_code,
    indicator_name, year, value.
    """
    records = []
    page = 1
    total_pages = 1  # Will be updated from API response

    while page <= total_pages:
        url = f"{API_BASE}/country/all/indicator/{indicator_code}"
        params = {
            "source": "3",  # WGI source ID
            "format": "json",
            "date": f"{start_year}:{end_year}",
            "per_page": "1000",
            "page": str(page),
        }

        for attempt in range(1, max_retries + 1):
            try:
                response = requests.get(url, params=params, timeout=60)
                response.raise_for_status()
                break
            except requests.exceptions.RequestException as e:
                if attempt == max_retries:
                    raise RuntimeError(
                        f"World Bank API call failed for {indicator_code} "
                        f"(page {page}) after {max_retries} attempts: {e}"
                    ) from e
                print(f"  Retry {attempt} for {indicator_code} page {page}: {e}")
                time.sleep(2 * attempt)  # Simple backoff

        data = response.json()

        # World Bank API returns [metadata, records] — check for valid response
        if not isinstance(data, list) or len(data) < 2:
            print(f"  WARNING: Unexpected API response for {indicator_code} page {page}")
            break

        metadata = data[0]
        entries = data[1]

        if entries is None:
            print(f"  No data returned for {indicator_code} page {page}")
            break

        total_pages = metadata.get("pages", 1)

        for entry in entries:
            # Skip entries with no value
            value = entry.get("value")
            if value is None:
                continue

            records.append({
                "country_name": entry.get("country", {}).get("value", ""),
                "country_code": entry.get("countryiso3code", ""),
                "indicator_code": indicator_code,
                "indicator_name": entry.get("indicator", {}).get("value", ""),
                "year": entry.get("date", ""),
                "value": float(value),
            })

        page += 1

    return records


# Fetch all indicators
all_records = []
for code, name in WGI_INDICATORS.items():
    print(f"  Fetching {code} ({name})...")
    indicator_records = fetch_indicator(code, start_year, end_year)
    all_records.extend(indicator_records)
    print(f"    -> {len(indicator_records)} records")
    # Brief pause between indicators to be a good API citizen
    time.sleep(0.5)

print(f"\n  Total records fetched: {len(all_records):,}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Write to bronze layer
# # The downstream `bronze-to-silver` notebook reads `bronze_WGI` and expects columns:
# `Country Name`, `Country Code`, `Series Name`.
# # We write the full API data to `bronze_WGI` with those columns plus additional
# fields (indicator_code, year, value) that enrich the dataset beyond what the
# manual CSV upload provided.

# CELL ********************

if len(all_records) == 0:
    raise RuntimeError(
        "No WGI records fetched from API. Check network connectivity, "
        "API availability, and date range parameters."
    )

# Define schema matching downstream expectations
# Column names match what bronze-to-silver expects: "Country Name", "Country Code", "Series Name"
schema = StructType([
    StructField("Country Name", StringType(), True),
    StructField("Country Code", StringType(), True),
    StructField("Series Name", StringType(), True),
    StructField("Indicator Code", StringType(), True),
    StructField("Year", StringType(), True),
    StructField("Value", DoubleType(), True),
])

# Build rows
rows = [
    Row(
        **{
            "Country Name": r["country_name"],
            "Country Code": r["country_code"],
            "Series Name": r["indicator_name"],
            "Indicator Code": r["indicator_code"],
            "Year": r["year"],
            "Value": r["value"],
        }
    )
    for r in all_records
]

spark_df = spark.createDataFrame(rows, schema)

# Write to bronze layer (overwrite — WGI is a full snapshot refresh)
table_name = "bronze_WGI"
spark_df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(table_name)

row_count = spark.sql(f"SELECT COUNT(*) as cnt FROM oem_lh.{table_name}").first()["cnt"]
print(f"  Written to {table_name}: {row_count:,} rows")
print(f"  Ingestion complete at {datetime.now().isoformat()}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Validation

# CELL ********************

# Quick validation: show sample data and coverage stats
print("Sample records:")
df_sample = spark.sql("""
    SELECT `Country Name`, `Country Code`, `Series Name`, `Indicator Code`, `Year`, `Value`
    FROM oem_lh.bronze_WGI
    WHERE `Country Code` IN ('USA', 'CHN', 'DEU', 'SWE', 'JPN')
    AND `Year` = '2022'
    ORDER BY `Country Name`, `Indicator Code`
""")
display(df_sample)

# Coverage summary
print("\nCoverage by indicator:")
df_coverage = spark.sql("""
    SELECT
        `Indicator Code`,
        `Series Name`,
        COUNT(DISTINCT `Country Code`) as countries,
        COUNT(DISTINCT `Year`) as years,
        COUNT(*) as total_records,
        ROUND(MIN(`Value`), 2) as min_value,
        ROUND(MAX(`Value`), 2) as max_value
    FROM oem_lh.bronze_WGI
    GROUP BY `Indicator Code`, `Series Name`
    ORDER BY `Indicator Code`
""")
display(df_coverage)

# Check for null country codes
null_check = spark.sql("""
    SELECT
        SUM(CASE WHEN `Country Name` IS NULL OR `Country Name` = '' THEN 1 ELSE 0 END) as null_country_name,
        SUM(CASE WHEN `Country Code` IS NULL OR `Country Code` = '' THEN 1 ELSE 0 END) as null_country_code,
        SUM(CASE WHEN `Series Name` IS NULL OR `Series Name` = '' THEN 1 ELSE 0 END) as null_series_name,
        COUNT(*) as total_rows
    FROM oem_lh.bronze_WGI
""")
display(null_check)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
