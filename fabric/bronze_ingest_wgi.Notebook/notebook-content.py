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
import random
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

# WGI indicator codes — all 6 governance dimensions (estimate scores).
# NOTE (2026-07-26): the World Bank re-coded WGI in the API. The classic CC.EST / GE.EST / …
# codes were ARCHIVED to source 57 ("WDI Database Archives") and now return
# "indicator not found"; the LIVE estimate series under source 3 are GOV_WGI_*.EST.
# We fetch with the new API codes but STORE the classic short code + name, so the bronze_WGI
# contract (Indicator Code, Series Name) is unchanged for every downstream layer.
# Map: API code -> (canonical Indicator Code, canonical Series Name)
WGI_INDICATORS = {
    "GOV_WGI_CC.EST": ("CC.EST", "Control of Corruption: Estimate"),
    "GOV_WGI_GE.EST": ("GE.EST", "Government Effectiveness: Estimate"),
    "GOV_WGI_PV.EST": ("PV.EST", "Political Stability and Absence of Violence/Terrorism: Estimate"),
    "GOV_WGI_RL.EST": ("RL.EST", "Rule of Law: Estimate"),
    "GOV_WGI_RQ.EST": ("RQ.EST", "Regulatory Quality: Estimate"),
    "GOV_WGI_VA.EST": ("VA.EST", "Voice and Accountability: Estimate"),
}

# World Bank API v2 base URL
API_BASE = "https://api.worldbank.org/v2"

# Retry tuning (task-050). The World Bank API degrades intermittently: on 2026-08-03 it
# timed out on roughly half of all requests for over 75 minutes, and bronze_WGI could not
# complete in either a pipeline run or a standalone probe. The old policy was
# max_retries=3 with `time.sleep(2 * attempt)` — a 2s then 4s wait after a 60s read
# timeout, i.e. it retried straight back into the same congestion and gave the remote side
# no time to recover.
#
# One run fetches 6 indicators x ~6 pages (~5,150 records each at per_page=1000) = ~36
# requests, so at a 50% per-request failure rate a clean run was effectively impossible.
#
# These constants govern the FAILURE PATH ONLY. A run in which nothing times out issues the
# identical request sequence in the identical time, which is what keeps the task-012_1
# performance baseline (bronze_WGI 73s) comparable for the task-012_5 retest.
#
# DO NOT RAISE API_PAGE_SIZE. Tried and measured 2026-08-03 (task-052), on the theory that
# fewer requests means fewer chances to hit the intermittent read timeout. That is wrong for
# this API, in both directions:
#   * SLOWER. At per_page=10000 the API does return pages=1 per indicator (~6 requests per
#     run instead of ~36), but each request cost ~53s against ~0.4-3.9s at per_page=1000.
#     The fetch cell went 265s -> 496s. Serialising one large page costs the server far more
#     than six small ones, and that swamps the request-count saving.
#   * MORE FRAGILE, not less. At ~53s against a 120s read timeout every request sits at ~44%
#     of its budget; at per_page=1000 each uses under 3%. Large pages move every request
#     close to the ceiling rather than reducing exposure - which is how VA.EST page 1 timed
#     out during the very run meant to demonstrate the improvement.
# Data was identical either way (31,122 records; per-indicator counts unchanged), so this is
# purely a latency and robustness finding. Reverted the same day. task-050's backoff is what
# actually fixed the degraded-API case.
API_PAGE_SIZE = 1000     # measured optimum - read the note above before changing
API_READ_TIMEOUT = 120   # was 60 — the server is slow, not absent; give it room to answer
API_MAX_RETRIES = 5      # was 3
API_BACKOFF_BASE = 5     # seconds; doubles per attempt -> 5, 10, 20, 40
API_BACKOFF_CAP = 60     # seconds; ceiling on any single wait
API_BACKOFF_JITTER = 0.25  # +/- fraction added to each wait, to de-synchronise retries

# Date range from parameters
start_year = p_start_year.strip()
end_year = p_end_year.strip()

print(f"WGI Ingestion: Fetching {len(WGI_INDICATORS)} indicators for {start_year}-{end_year}")
for api_code, (short_code, name) in WGI_INDICATORS.items():
    print(f"  - {short_code} (API {api_code}): {name}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Fetch data from World Bank API

# CELL ********************

def fetch_indicator(api_code, short_code, series_name, start_year, end_year,
                    max_retries=API_MAX_RETRIES):
    """
    Fetch all country data for a single WGI indicator from the World Bank API.
    Uses JSON format with pagination. Queries the live API code (api_code, e.g.
    GOV_WGI_CC.EST) but records the canonical short_code / series_name so the bronze
    contract stays stable for downstream.

    Returns a list of dicts with keys: country_name, country_code, indicator_code,
    indicator_name, year, value.
    """
    records = []
    page = 1
    total_pages = 1  # Will be updated from API response

    while page <= total_pages:
        url = f"{API_BASE}/country/all/indicator/{api_code}"
        params = {
            "source": "3",  # WGI source ID
            "format": "json",
            "date": f"{start_year}:{end_year}",
            "per_page": str(API_PAGE_SIZE),
            "page": str(page),
        }

        for attempt in range(1, max_retries + 1):
            try:
                response = requests.get(url, params=params, timeout=API_READ_TIMEOUT)
                response.raise_for_status()
                break
            except requests.exceptions.RequestException as e:
                if attempt == max_retries:
                    raise RuntimeError(
                        f"World Bank API call failed for {api_code} "
                        f"(page {page}) after {max_retries} attempts: {e}"
                    ) from e
                # Exponential backoff, capped, with jitter (task-050). Doubling gives the
                # remote side progressively more room to recover; the cap stops a single
                # dead page stalling the notebook; the jitter de-synchronises retries so
                # successive pages don't re-hit the API in lockstep.
                delay = min(API_BACKOFF_BASE * (2 ** (attempt - 1)), API_BACKOFF_CAP)
                delay += random.uniform(-API_BACKOFF_JITTER, API_BACKOFF_JITTER) * delay
                delay = max(delay, 0.0)
                print(
                    f"  Retry {attempt}/{max_retries} for {api_code} page {page} "
                    f"in {delay:.1f}s: {e}"
                )
                time.sleep(delay)

        data = response.json()

        # World Bank API returns [metadata, records] — check for valid response
        if not isinstance(data, list) or len(data) < 2:
            print(f"  WARNING: Unexpected API response for {api_code} page {page}")
            break

        metadata = data[0]
        entries = data[1]

        if entries is None:
            print(f"  No data returned for {api_code} page {page}")
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
                "indicator_code": short_code,
                "indicator_name": series_name,
                "year": entry.get("date", ""),
                "value": float(value),
            })

        page += 1

    return records


# Fetch all indicators
all_records = []
for api_code, (short_code, series_name) in WGI_INDICATORS.items():
    print(f"  Fetching {short_code} (API {api_code})...")
    indicator_records = fetch_indicator(api_code, short_code, series_name, start_year, end_year)
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
