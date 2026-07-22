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

# This notebook fixes headers, drops extra rows, normalize basic types, add metadata columns (ingest_ts, run_id, source_system).

# MARKDOWN ********************

# # nb_silver_standardize
# # This notebook does the following:
# - cleans headers,
# - trims entries,
# - type casts,
# - light normalization (no business joins).
# # Supports incremental loading for procurement data via p_full_load / p_from_date parameters.


# CELL ********************

# Pipeline parameters — overridden by Fabric pipeline at runtime
p_full_load = "false"
p_from_date = "1900-01-01"

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.functions import col, expr, regexp_replace, substring
from pyspark.sql.types import (IntegerType,StringType,DoubleType,StructType,StructField)
from delta.tables import DeltaTable
from datetime import datetime, timedelta

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## epi2024results: bronze --> silver

# CELL ********************

# Load dataframe to session
df = spark.sql("SELECT * FROM oem_lh.bronze_epi2024results")

# Clean + rename in one go (PySpark)
from pyspark.sql import functions as F

def clean_and_rename(df):
    # Drop all columns that end with ".old"
    old_cols = [c for c in df.columns if c.endswith(".old")]
    df = df.drop(*old_cols)

    # Rename: remove ".new" suffix, handle dots safely with backticks
    new_columns = [
        F.col(f"`{c}`").alias(c[:-4]) if c.endswith(".new") else F.col(f"`{c}`")
        for c in df.columns
    ]

    return df.select(*new_columns)

df_cleaned = clean_and_rename(df)

df_multi_casted = df_cleaned.withColumn("code", F.col("code").cast(IntegerType())) # cast code as integer
df_selected = df_multi_casted.select("code", "iso", "country", "EPI")
display(df_selected)


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

df_selected.write.format("delta").mode("overwrite").saveAsTable('silver_epi2024results')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## GlobalSupplyShares: bronze --> silver

# CELL ********************

df = spark.sql("SELECT * FROM oem_lh.`bronze_GlobalSupplyShares`")

# rename column headers
new_columns = [c.lower().replace(' ', '_') for c in df.columns] # create a list of new, clean column names
df_newheaders = df.toDF(*new_columns).drop('t')


display(df_newheaders)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

df_newheaders.write.format("delta").mode("overwrite").saveAsTable('silver_globalsupplyshares')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## procurement: bronze --> silver
# # Supports incremental loading when p_full_load is "false". Uses a date-partition
# DELETE-INSERT (not a natural-key MERGE) to preserve transaction grain: two same-day
# purchases of the same material/supplier are legitimate distinct transactions, so no
# merge key or dedupe is applied (see task-024, 2026-07-14). A 7-day look-back window
# handles late-arriving data during incremental loads.

# CELL ********************

# Read bronze procurement data — apply date filter for incremental loads
is_full_load = p_full_load.strip().lower() == "true"

if is_full_load:
    df1 = spark.sql("SELECT * FROM oem_lh.bronze_procurement_transactional")
    print("Procurement: FULL LOAD — reading all bronze records")
else:
    # Apply 7-day look-back window for late-arriving data
    watermark_date = datetime.strptime(p_from_date, "%Y-%m-%d")
    lookback_date = watermark_date - timedelta(days=7)
    lookback_str = lookback_date.strftime("%Y-%m-%d")
    df1 = spark.sql(
        f"SELECT * FROM oem_lh.bronze_procurement_transactional WHERE Date >= '{lookback_str}'"
    )
    print(f"Procurement: INCREMENTAL LOAD — reading records from {lookback_str} (7-day look-back from {p_from_date})")

df2 = spark.sql("SELECT * FROM oem_lh.bronze_supplier_ref")
display(df1)
display(df2)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Join procurement_transactional & supplier_ref
# Use list-based join key to avoid duplicate SupplierName columns in output
left_join_df = df1.join(df2, ["SupplierName"], "left")

# Rename columns to lowercase with underscores
new_columns = [c.lower().replace(' ', '_') for c in left_join_df.columns]
df_joined = left_join_df.toDF(*new_columns)

# Drop region column (not needed in silver layer)
silver_df = df_joined.drop("region")

display(silver_df)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Write silver_procurement — full overwrite, first-load create, or transaction-grain delete-insert.
# task-024 decision (2026-07-14): keep one-row-per-transaction grain and ABANDON the natural-key
# MERGE. Bronze grain is "one row per material purchase", so two same-day purchases of the same
# material from the same supplier are LEGITIMATE distinct transactions. The old MERGE on
# (date, materialname, suppliername) collapsed them: a same-batch pair threw Delta's "multiple
# source rows matched" (crash) and a cross-run pair was silently overwritten by whenMatchedUpdateAll
# (data loss). We deliberately do NOT dedupe — the strategy doc's dedupe step would silently drop
# legitimate duplicate transactions, contradicting the transaction-grain decision. Delete-insert
# over the incremental date window is lossless (every transaction preserved) and idempotent.
if is_full_load:
    silver_df.write.format("delta").mode("overwrite").saveAsTable("silver_procurement")
    print(f"Procurement: full overwrite complete ({silver_df.count():,} rows)")
else:
    if not spark.catalog.tableExists("oem_lh.silver_procurement"):
        # First load — create table via overwrite
        silver_df.write.format("delta").mode("overwrite").saveAsTable("silver_procurement")
        print(f"Procurement: initial table created ({silver_df.count():,} rows)")
    else:
        # Incremental: delete-insert over the look-back window. Delete boundary = the minimum date
        # actually present in this run's window. silver_df was read with the same 7-day look-back,
        # so it contains every bronze row with date >= look-back; deleting silver rows with
        # date >= that minimum and appending silver_df replaces EXACTLY the window — no duplication
        # in the look-back range and re-running is idempotent. (This is why the boundary is the
        # window's min date, not p_from_date: deleting only >= p_from_date would leave the
        # [look-back, p_from_date) rows un-deleted and then re-append them, duplicating that range.)
        # task-029 DEPENDENCY: p_from_date defaults to "1900-01-01" until the high-water-mark lands,
        # so today the window == full history (full rewrite each run — correct + idempotent, just
        # not yet incremental-efficient). Becomes truly incremental once task-029 lands.
        window_min_date = silver_df.agg(F.min("date")).first()[0]
        if window_min_date is None:
            print("Procurement: incremental window is empty — nothing to delete-insert")
        else:
            target_table = DeltaTable.forName(spark, "oem_lh.silver_procurement")
            target_table.delete(F.col("date") >= F.lit(window_min_date))
            silver_df.write.format("delta").mode("append").saveAsTable("silver_procurement")
            print(f"Procurement: delete-insert complete for date >= {window_min_date} "
                  f"({silver_df.count():,} rows re-inserted)")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## WGI (World Governance Indicators): bronze --> silver

# CELL ********************

# Load WGI data and standardize columns
df_wgi = spark.sql("SELECT * FROM oem_lh.bronze_WGI")

# Standardize columns: snake_case names, UPPER ISO3
# Note: bronze_WGI has 3 columns: Country Name, Country Code, Series Name
# (Score column not present in current dataflow - used for coverage check only)
df_wgi_clean = df_wgi.select(
    F.upper(F.trim(F.col("`Country Code`"))).alias("country_iso3"),
    F.trim(F.col("`Country Name`")).alias("country_name"),
    F.trim(F.col("`Series Name`")).alias("indicator_name")
).filter(
    (F.col("country_iso3").isNotNull()) &
    (F.col("indicator_name").isNotNull())
)

display(df_wgi_clean)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

df_wgi_clean.write.format("delta").mode("overwrite").saveAsTable("silver_wgi")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
