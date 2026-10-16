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
# # **Source:** Yale's original release files, pinned in this repo under `reference_data/epi/`
# (`epi&lt;p_epi_year&gt;results.csv` and `epi&lt;p_epi_year&gt;weights.csv`) and fetched over HTTPS from
# https://raw.githubusercontent.com/erikemilsson/OEMMatInsightBI/main/reference_data/epi/ (task-082).
# Yale retired its `https://epi.yale.edu/downloads/epi2024*.csv` paths when EPI 2026 shipped
# (September 2026); they now answer HTTP 200 with an HTML page. Only the 2024 vintage is pinned.
# **Target:** bronze_epi&lt;p_epi_year&gt;results (Delta table, overwrite) — source URL and
# target table are both derived from the p_epi_year parameter, so each vintage lands in
# its own table (e.g. p_epi_year="2024" -> bronze_epi2024results).
# **License:** CC BY-NC-SA 4.0 (non-commercial use only)
# **Update frequency:** Annual (typically June)
# # Attribution: Environmental Performance Index 2024,
# Yale Center for Environmental Law & Policy, https://epi.yale.edu/

# PARAMETERS CELL ********************

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

# ## Download guard (task-082)
# Each download is checked before it is parsed. A non-CSV `Content-Type` or an HTML body
# raises `EpiSourceNotCsvError`, naming the URL and the content type. Without this check, a
# soft-404 (HTTP 200 with an HTML page, which Yale's retired 2024 paths now return) reaches
# `pd.read_csv` and fails as an opaque pandas `ParserError`.

# CELL ********************

# Media types accepted as CSV. text/plain is required, not lax: raw.githubusercontent.com
# serves every text file as "text/plain; charset=utf-8" (measured 2026-10-16), and that is
# where the pinned copy lives. The body check in assert_csv_response() is what catches an
# HTML page served under any of these types. Pinned by tests/test_epi_source_guard.py.
CSV_CONTENT_TYPES = {"text/csv", "application/csv", "text/plain"}


class EpiSourceNotCsvError(ValueError):
    """An EPI download answered with something that is not a CSV file."""


def assert_csv_response(response, url):
    """Raise EpiSourceNotCsvError unless `response` looks like a CSV file.

    Call it after a successful download and before pd.read_csv. It checks the
    Content-Type header against CSV_CONTENT_TYPES and sniffs the start of the body for
    an HTML page or an empty body, so a soft-404 fails with a named error that cites the
    URL and the content type instead of a pandas ParserError.
    """
    content_type = (response.headers.get("Content-Type") or "").strip()
    media_type = content_type.split(";", 1)[0].strip().lower()
    head = response.text[:2048].lstrip("\ufeff \t\r\n").lower()

    problems = []
    if media_type not in CSV_CONTENT_TYPES:
        problems.append(f"the Content-Type is not one of {sorted(CSV_CONTENT_TYPES)}")
    if head.startswith("<!doctype html") or "<html" in head:
        problems.append("the body is an HTML page")
    if not head:
        problems.append("the body is empty")
    if problems:
        raise EpiSourceNotCsvError(
            f"EPI download is not a CSV: {url} returned HTTP {response.status_code} with "
            f"Content-Type {content_type or '(missing)'!r}; {' and '.join(problems)}. "
            f"An HTTP 200 that is not a CSV is a soft-404: the file was moved or retired at "
            f"the source. See docs/epi_wgi_ingestion.md, 'Source pinning and the pre-parse guard'."
        )

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Download EPI CSV (repo-pinned copy of Yale's release)

# CELL ********************

# Where the CSVs come from (task-082). Yale retired https://epi.yale.edu/downloads/epi{year}*.csv
# when EPI 2026 shipped (September 2026). Those paths do not 404: they answer HTTP 200 with a
# 30 KB HTML page, which pd.read_csv failed on ("Expected 1 fields in line 15, saw 2") in every
# scheduled run from 2026-09-25. The files under reference_data/epi/ are byte-identical to
# Yale's 2024 originals (recovered from the Wayback Machine; provenance and sha256 in
# reference_data/epi/README.md). raw.githubusercontent.com serves them only while the repo is
# PUBLIC and the files are on main: otherwise it returns 404, which the handler below reports.
EPI_SOURCE_BASE_URL = "https://raw.githubusercontent.com/erikemilsson/OEMMatInsightBI/main/reference_data/epi"

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
epi_url = f"{EPI_SOURCE_BASE_URL}/epi{epi_year}results.csv"
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
                f"No pinned EPI {epi_year} results file at {epi_url} (HTTP 404). Only the "
                f"2024 vintage is pinned (task-082): a new vintage needs its CSVs committed "
                f"under reference_data/epi/ and pushed to main first. A 404 for 2024 means "
                f"the file moved or the repo is no longer public."
            ) from e
        if attempt == max_retries:
            raise RuntimeError(f"EPI download failed after {max_retries} attempts: {e}") from e
        print(f"  Attempt {attempt} failed ({e}), retrying...")
    except requests.exceptions.RequestException as e:
        if attempt == max_retries:
            raise RuntimeError(f"EPI download failed after {max_retries} attempts: {e}") from e
        print(f"  Attempt {attempt} failed ({e}), retrying...")

# Validate before parsing (task-082): an HTML page or a non-CSV Content-Type raises
# EpiSourceNotCsvError here, instead of reaching pd.read_csv as a ParserError.
assert_csv_response(response, epi_url)
print(f"  Content check passed (Content-Type: {response.headers.get('Content-Type')})")

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

# MARKDOWN ********************

# ## Download EPI weights CSV (indicator hierarchy + absolute weights)
# # Yale's release also included `epi{epi_year}weights.csv`, pinned next to the results file
# under `reference_data/epi/` (task-082). It is a small (~7 KB) metadata table with the
# full indicator hierarchy: one row per node (EPI composite, 3 PolicyObjective, 11
# IssueCategory, 58 Indicator in the 2024 file), columns `Type`, `Abbreviation`, `Variable`, `Weight`
# (relative within parent), `NextLevel` (parent abbrev pointer), `IssueCategory`,
# `PolicyObjective`, `EPI Percent` (absolute contribution to the EPI composite — this is
# the value `gold_dim_indicator.weight` needs for leaf indicators).
# # task-056: this file was previously listed as unimplemented in
# `epi_wgi_ingestion.md`'s `download_epi_data()` design. Without it,
# `silver-to-gold2.Notebook` fell back to a NULL-weight fallback path that left
# `gold_dim_indicator.weight` NULL for all 73 rows, which made the `Weighted EPI Score`
# DAX measure render BLANK.

# CELL ********************

# Download the weights file using the same year parameter, source, retry/error handling and
# pre-parse guard as the results download above. The bronze table name mirrors the results
# naming: bronze_epi{epi_year}weights.
weights_url = f"{EPI_SOURCE_BASE_URL}/epi{epi_year}weights.csv"
weights_table = f"bronze_epi{epi_year}weights"

print(f"\nEPI Weights Ingestion: Downloading {epi_year} weights")
print(f"  URL: {weights_url}")
print(f"  Target table: {weights_table}")

weights_response = None
for attempt in range(1, max_retries + 1):
    try:
        weights_response = requests.get(
            weights_url,
            timeout=60,
            headers={"User-Agent": "OEMMatInsightBI-Pipeline/1.0"}
        )
        weights_response.raise_for_status()
        print(f"  Download succeeded (attempt {attempt}, {len(weights_response.content):,} bytes)")
        break
    except requests.exceptions.HTTPError as e:
        if weights_response is not None and weights_response.status_code == 404:
            raise ValueError(
                f"No pinned EPI {epi_year} weights file at {weights_url} (HTTP 404). Only "
                f"the 2024 vintage is pinned (task-082): a new vintage needs its CSVs "
                f"committed under reference_data/epi/ and pushed to main first. A 404 for "
                f"2024 means the file moved or the repo is no longer public."
            ) from e
        if attempt == max_retries:
            raise RuntimeError(f"EPI weights download failed after {max_retries} attempts: {e}") from e
        print(f"  Attempt {attempt} failed ({e}), retrying...")
    except requests.exceptions.RequestException as e:
        if attempt == max_retries:
            raise RuntimeError(f"EPI weights download failed after {max_retries} attempts: {e}") from e
        print(f"  Attempt {attempt} failed ({e}), retrying...")

# Validate before parsing (task-082), same guard as the results file.
assert_csv_response(weights_response, weights_url)
print(f"  Content check passed (Content-Type: {weights_response.headers.get('Content-Type')})")

# Parse CSV — preserve the source columns as-is (bronze is the raw landing zone;
# silver-to-gold2.Notebook maps them to the silver_epi{EPI_YEAR}variables shape the
# gold_dim_indicator primary path selects from).
weights_pdf = pd.read_csv(io.StringIO(weights_response.text))
print(f"  Parsed {len(weights_pdf)} rows, {len(weights_pdf.columns)} columns")
print(f"  Columns: {list(weights_pdf.columns)}")

# Validate expected weights columns. The header is the load-bearing contract for
# silver-to-gold2's column mapping — if Yale renames a column, the silver build silently
# NPEs and gold_dim_indicator goes empty, so fail loudly here at the bronze gate.
required_weights_columns = [
    "Type", "Abbreviation", "Variable", "Weight",
    "NextLevel", "IssueCategory", "PolicyObjective", "EPI Percent"
]
missing_weights = [c for c in required_weights_columns if c not in weights_pdf.columns]
if missing_weights:
    raise ValueError(
        f"EPI weights CSV schema mismatch — missing required columns: {missing_weights}. "
        f"Available columns: {list(weights_pdf.columns)}"
    )

# Validate row count: 73 rows in the 2024 file (1 EPI + 3 PolicyObjective + 11 IssueCategory + 58 Indicator).
if len(weights_pdf) < 50:
    print(f"  WARNING: Only {len(weights_pdf)} rows — expected ~73. Data may be incomplete.")

weights_spark_df = spark.createDataFrame(weights_pdf)

# Delta Lake rejects column names containing ' ,;{}()\n\t=' unless Column Mapping
# is enabled on the table. Yale's header "EPI Percent" (space) violates this — the
# bronze write fails with DELTA_INVALID_CHARACTERS_IN_COLUMN_NAMES at saveAsTable.
# The other 7 source columns (Type, Abbreviation, Variable, Weight, NextLevel,
# IssueCategory, PolicyObjective) are Delta-valid (no spaces). Rename only the
# offender to snake_case; the validation above still gates against Yale's real
# header (the external contract), and silver-to-gold2 references this renamed
# column as `epi_percent`. Surfaced by Erik's 2026-08-04 pipeline run — local
# verification couldn't catch it (Delta writes are the documented local ceiling:
# delta-spark is not installed, so local tests ran the DataFrame logic in-memory
# and never invoked a Delta writer).
weights_spark_df = weights_spark_df.withColumnRenamed("EPI Percent", "epi_percent")

weights_spark_df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(weights_table)

weights_row_count = spark.sql(f"SELECT COUNT(*) as cnt FROM oem_lh.{weights_table}").first()["cnt"]
print(f"  Written to {weights_table}: {weights_row_count} rows")
print(f"  Weights ingestion complete at {datetime.now().isoformat()}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
