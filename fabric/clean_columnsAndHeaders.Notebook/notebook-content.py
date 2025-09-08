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
display(df_multi_casted)


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

df_multi_casted.write.format("delta").mode("overwrite").saveAsTable('silver_epi2024results')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## epi2024variables2024-12-11: bronze --> silver

# CELL ********************

df = spark.sql("SELECT * FROM oem_lh.`bronze_epi2024variables2024-12-11`")

# rename column headers
new_columns = [c.lower().replace(' ', '_') for c in df.columns] # create a list of new, clean column names
df_newheaders = df.toDF(*new_columns)

display(df_newheaders)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

df_newheaders.write.format("delta").mode("overwrite").saveAsTable('`silver_epi2024variables2024-12-11`')

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
df_newheaders = df.toDF(*new_columns)

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

# ## WB_ESGCSV & EBESGSeries: bronze --> silver

# CELL ********************

df = spark.sql("SELECT * FROM oem_lh.`bronze_WB_ESGCSV`")

# unpivot year rows
id_cols = ["Country Name", "Country Code", "Indicator Name", "Indicator Code"] # columns to keep fixed
unpivot_cols = [col for col in df.columns if col not in id_cols] # columns to unpivot
stack_expr_str = ", ".join([f"'{col}', `{col}`" for col in unpivot_cols]) # Build the stack expression dynamically
unpivot_expr = f"stack({len(unpivot_cols)}, {stack_expr_str}) as (Year, Score)" # Final expression
unpivoted_df = df.select(   # Apply the transformation
    *id_cols,
    expr(unpivot_expr)
)
cleaned_df = unpivoted_df.withColumn( # remove the _y prefix
    "Year",
    regexp_replace(col("Year"), "^y_", "")
)

# filter for only year 2020
filtered_df = cleaned_df.filter(col("Year") == "2020")

# rename column headers
new_columns = [c.lower().replace(' ', '_') for c in filtered_df.columns] # create a list of new, clean column names
df_newheaders = filtered_df.toDF(*new_columns)

display(df_newheaders)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

df2 = spark.sql("SELECT `Series Code`, `Topic` FROM oem_lh.`bronze_WB_ESGSeries`")

# rename column headers
new_columns = [c.lower().replace(' ', '_') for c in df2.columns] # create a list of new, clean column names
df2_newheaders = df2.toDF(*new_columns)

display(df2_newheaders)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Join ESG CSV with Series metadata to align codes with topics
left_join_df = df_newheaders.join(
    df2_newheaders,
    df_newheaders.indicator_code == df2_newheaders.series_code, # The join condition
    "left"  # The type of join
)

df_multi_casted = left_join_df.withColumn("score", col("score").cast(DoubleType())) # change datatype
df_filtered = df_multi_casted.filter((F.col("score") >= 0) & (F.col("score") <= 100)) # filter for under 100 & over 0
df_no_year = df_filtered.drop("year") # remove year column
display(df_no_year)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

df_no_year.write.format("delta").mode("overwrite").saveAsTable('silver_WB')

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

# ##
