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
# # **Source:** https://epi.yale.edu/downloads/epi&lt;p_epi_year&gt;results.csv
# **Target:** bronze_epi&lt;p_epi_year&gt;results (Delta table, overwrite) — source URL and
# target table are both derived from the p_epi_year parameter, so each vintage lands in
# its own table (e.g. p_epi_year="2024" -> bronze_epi2024results).
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

# Build download URL AND target table name from the same year parameter (task-028).
# These must stay coupled: the URL was already parameterised while the target table was
# hardcoded to bronze_epi2024results, so a 2025 run would have downloaded 2025 data and
# overwritten the 2024 table with it — 2025 numbers living under a 2024 name.
epi_year = p_epi_year.strip()
if not (epi_year.isdigit() and len(epi_year) == 4):
    raise ValueError(
        f"p_epi_year must be a 4-digit year, got {p_epi_year!r}. "
        f"It names both the source URL and the bronze table."
    )
epi_url = f"https://epi.yale.edu/downloads/epi{epi_year}results.csv"
table_name = f"bronze_epi{epi_year}results"

print(f"EPI Ingestion: Downloading {epi_year} data")
print(f"  URL: {epi_url}")
print(f"  Target table: {table_name}")

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

# Validate expected columns exist.
# Yale ships some releases with vintage-suffixed metric columns ("EPI.new"/"EPI.old"),
# which is why bronze-to-silver.Notebook's clean_and_rename() drops ".old" and strips
# ".new" before selecting plain names. Bronze is the raw landing zone, so this notebook
# does NOT rename — it only asserts that each required field is present in one of the two
# shapes, and leaves normalisation to silver. Accepting only the plain names (the
# pre-task-028 behaviour) would hard-fail on any suffixed release even though the
# downstream pipeline handles it fine.
required_columns = ["code", "iso", "country", "EPI"]
missing = [
    c for c in required_columns
    if c not in pdf.columns and f"{c}.new" not in pdf.columns
]
if missing:
    raise ValueError(
        f"EPI CSV schema mismatch — missing required columns: {missing} "
        f"(neither plain nor '.new'-suffixed). Available columns: {list(pdf.columns)}"
    )

# Validate row count (EPI covers 180+ countries)
if len(pdf) < 100:
    print(f"  WARNING: Only {len(pdf)} rows — expected 180+. Data may be incomplete.")

# Convert to Spark DataFrame
spark_df = spark.createDataFrame(pdf)

# Write to bronze layer (overwrite — EPI is a full snapshot).
# table_name was derived from p_epi_year in the download cell; each vintage lands in its
# own table, so re-running for a new year never clobbers a previous year's snapshot.
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

# Quick validation: show sample data and key stats.
# Reads the same year-derived table_name as the write above (task-028) — a hardcoded
# bronze_epi2024results here would have silently validated last year's data.
# The EPI column may be plain or ".new"-suffixed (see the schema check above); backtick
# the resolved name so the dotted form parses in Spark SQL.
_written_cols = spark.table(f"oem_lh.{table_name}").columns
epi_col = "EPI" if "EPI" in _written_cols else "EPI.new"

df_check = spark.sql(
    f"SELECT code, iso, country, `{epi_col}` AS EPI FROM oem_lh.{table_name} "
    f"ORDER BY `{epi_col}` DESC LIMIT 10"
)
print("Top 10 countries by EPI score:")
display(df_check)

# Check for nulls in key columns
null_counts = spark.sql(f"""
    SELECT
        SUM(CASE WHEN code IS NULL THEN 1 ELSE 0 END) as null_code,
        SUM(CASE WHEN iso IS NULL THEN 1 ELSE 0 END) as null_iso,
        SUM(CASE WHEN country IS NULL THEN 1 ELSE 0 END) as null_country,
        SUM(CASE WHEN `{epi_col}` IS NULL THEN 1 ELSE 0 END) as null_epi,
        COUNT(*) as total_rows
    FROM oem_lh.{table_name}
""")
display(null_counts)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
