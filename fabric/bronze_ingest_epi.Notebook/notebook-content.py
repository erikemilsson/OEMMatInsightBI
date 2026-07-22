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

# # bronze_ingest_epi
# # Automated ingestion of Environmental Performance Index (EPI) data from Yale.
# Replaces manual CSV upload via EPI_file2table.Dataflow.
# # **Source:** https://epi.yale.edu/downloads/epi2024results.csv
# **Target:** bronze_epi2024results (Delta table, overwrite)
# **License:** CC BY-NC-SA 4.0 (non-commercial use only)
# **Update frequency:** Annual (typically June)
# # Attribution: Environmental Performance Index 2024,
# Yale Center for Environmental Law & Policy, https://epi.yale.edu/

# CELL ********************

# Pipeline parameters — overridden by Fabric pipeline at runtime
p_epi_year = "2024"

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

import requests
import io
import csv
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, IntegerType
from datetime import datetime

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Download EPI CSV from Yale

# CELL ********************

# Build download URL based on year parameter
epi_year = p_epi_year.strip()
epi_url = f"https://epi.yale.edu/downloads/epi{epi_year}results.csv"

print(f"EPI Ingestion: Downloading {epi_year} data")
print(f"  URL: {epi_url}")

# Download with error handling and retry
max_retries = 3
response = None

for attempt in range(1, max_retries + 1):
    try:
        response = requests.get(
            epi_url,
            timeout=60,
            headers={"User-Agent": "OEMMatInsightBI-Pipeline/1.0"}
        )
        response.raise_for_status()
        print(f"  Download succeeded (attempt {attempt}, {len(response.content):,} bytes)")
        break
    except requests.exceptions.HTTPError as e:
        if response is not None and response.status_code == 404:
            raise ValueError(
                f"EPI {epi_year} data not found at {epi_url}. "
                f"Check if the year is correct or if Yale has changed the URL pattern."
            ) from e
        if attempt == max_retries:
            raise RuntimeError(f"EPI download failed after {max_retries} attempts: {e}") from e
        print(f"  Attempt {attempt} failed ({e}), retrying...")
    except requests.exceptions.RequestException as e:
        if attempt == max_retries:
            raise RuntimeError(f"EPI download failed after {max_retries} attempts: {e}") from e
        print(f"  Attempt {attempt} failed ({e}), retrying...")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Parse CSV and write to bronze layer

# CELL ********************

# Parse CSV content into a pandas DataFrame, then convert to Spark
import pandas as pd

csv_text = response.text
pdf = pd.read_csv(io.StringIO(csv_text))

print(f"  Parsed {len(pdf)} rows, {len(pdf.columns)} columns")
print(f"  Columns: {list(pdf.columns[:10])}{'...' if len(pdf.columns) > 10 else ''}")

# Validate expected columns exist
required_columns = ["code", "iso", "country", "EPI"]
missing = [c for c in required_columns if c not in pdf.columns]
if missing:
    raise ValueError(
        f"EPI CSV schema mismatch — missing required columns: {missing}. "
        f"Available columns: {list(pdf.columns)}"
    )

# Validate row count (EPI covers 180+ countries)
if len(pdf) < 100:
    print(f"  WARNING: Only {len(pdf)} rows — expected 180+. Data may be incomplete.")

# Convert to Spark DataFrame
spark_df = spark.createDataFrame(pdf)

# Write to bronze layer (overwrite — EPI is a full snapshot)
table_name = "bronze_epi2024results"
spark_df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(table_name)

row_count = spark.sql(f"SELECT COUNT(*) as cnt FROM oem_lh.{table_name}").first()["cnt"]
print(f"  Written to {table_name}: {row_count} rows")
print(f"  Ingestion complete at {datetime.now().isoformat()}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Validation

# CELL ********************

# Quick validation: show sample data and key stats
df_check = spark.sql("SELECT code, iso, country, EPI FROM oem_lh.bronze_epi2024results ORDER BY EPI DESC LIMIT 10")
print("Top 10 countries by EPI score:")
display(df_check)

# Check for nulls in key columns
null_counts = spark.sql("""
    SELECT
        SUM(CASE WHEN code IS NULL THEN 1 ELSE 0 END) as null_code,
        SUM(CASE WHEN iso IS NULL THEN 1 ELSE 0 END) as null_iso,
        SUM(CASE WHEN country IS NULL THEN 1 ELSE 0 END) as null_country,
        SUM(CASE WHEN EPI IS NULL THEN 1 ELSE 0 END) as null_epi,
        COUNT(*) as total_rows
    FROM oem_lh.bronze_epi2024results
""")
display(null_counts)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
