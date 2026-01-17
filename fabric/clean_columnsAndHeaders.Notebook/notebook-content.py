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


# CELL ********************

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.functions import col, expr, regexp_replace, substring
from pyspark.sql.types import (IntegerType,StringType,DoubleType,StructType,StructField)

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

# CELL ********************

df1 = spark.sql("SELECT * FROM oem_lh.bronze_procurement_transactional")
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
left_join_df = df1.join(
    df2,
    df1.SupplierName == df2.SupplierName, # The join condition
    "left"  # The type of join
)
display(left_join_df)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# rename column headers
new_columns = [c.lower().replace(' ', '_') for c in left_join_df.columns] # create a list of new, clean column names
df2_newheaders = left_join_df.toDF(*new_columns)
display(df2_newheaders)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

df_dropped = df2_newheaders.drop("region", "suppliername") # drop repeated columns
display(df_dropped)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

df_dropped.write.format("delta").mode("overwrite").saveAsTable('silver_procurement')

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

# Standardize columns: snake_case names, UPPER ISO3, cast percentile to DOUBLE
df_wgi_clean = df_wgi.select(
    F.upper(F.trim(F.col("`Country Code`"))).alias("country_iso3"),
    F.trim(F.col("`Country Name`")).alias("country_name"),
    F.trim(F.col("`Series Name`")).alias("indicator_name"),
    F.col("`Percentile Rank 2023`").cast(DoubleType()).alias("percentile_rank_2023")
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
