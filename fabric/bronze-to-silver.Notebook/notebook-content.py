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
#
# This notebook does the following:
# - cleans headers,
# - trims entries,
# - type casts,
# - light normalization (no business joins).
#
# Supports incremental loading for procurement data via p_full_load / p_from_date parameters.


# CELL ********************

# Pipeline parameters — overridden by Fabric pipeline at runtime
p_full_load = "false"
p_from_date = "1900-01-01"

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark",
# META   "inputParameters": {
# META     "p_full_load": {
# META       "type": "string",
# META       "defaultValue": "false"
# META     },
# META     "p_from_date": {
# META       "type": "string",
# META       "defaultValue": "1900-01-01"
# META     }
# META   }
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
#
# Supports incremental loading via Delta MERGE when p_full_load is "false".
# MERGE key: natural key (date + materialname + suppliername).
# Uses a 7-day look-back window for late-arriving data during incremental loads.

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

# Write silver_procurement — full overwrite or Delta MERGE
if is_full_load:
    silver_df.write.format("delta").mode("overwrite").saveAsTable("silver_procurement")
    print(f"Procurement: full overwrite complete ({silver_df.count():,} rows)")
else:
    # Incremental: Delta MERGE on natural key
    if not spark.catalog.tableExists("oem_lh.silver_procurement"):
        # First load — create table via overwrite
        silver_df.write.format("delta").mode("overwrite").saveAsTable("silver_procurement")
        print(f"Procurement: initial table created ({silver_df.count():,} rows)")
    else:
        merge_condition = """
            target.date = source.date AND
            target.materialname = source.materialname AND
            target.suppliername = source.suppliername
        """

        target_table = DeltaTable.forName(spark, "oem_lh.silver_procurement")
        (target_table.alias("target")
         .merge(silver_df.alias("source"), merge_condition)
         .whenMatchedUpdateAll()
         .whenNotMatchedInsertAll()
         .execute())

        print(f"Procurement: Delta MERGE complete ({silver_df.count():,} rows merged)")

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
