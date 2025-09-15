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

# ## Silver → Gold with PySpark (Lakehouse)

# MARKDOWN ********************

# #### Conventions

# CELL ********************

from pyspark.sql import functions as F, Window as W
from pyspark.sql.types import IntegerType, StringType, FloatType, DateType

DB = "oem_lh"  # Lakehouse database/schema

def stable_key(cols):
    # Deterministic 32-bit surrogate over business keys
    return (F.abs(F.xxhash64(*[F.coalesce(F.col(c).cast("string"), F.lit("∅")) for c in cols]))).cast("bigint")

def write_tbl(df, tbl_name):
    (df.write
       .format("delta")
       .mode("overwrite")
       .option("overwriteSchema","true")
       .saveAsTable(f"{DB}.{tbl_name}"))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# #### Dimensions
# 
# gold.dim_country

# CELL ********************

from pyspark.sql import functions as F
from pyspark.sql.types import IntegerType

spark.sql(f"CREATE DATABASE IF NOT EXISTS {DB}")
spark.sql(f"USE {DB}")

def stable_key(cols):
    return (F.abs(F.xxhash64(*[F.coalesce(F.col(c).cast("string"), F.lit("∅")) for c in cols]))).cast("bigint")

def write_tbl(df, name):      # name is just the table name, not qualified
    (df.write
       .format("delta")
       .mode("overwrite")
       .option("overwriteSchema","true")
       .saveAsTable(name))

# --- build dim_country exactly as before (no changes needed to the join logic) ---
epi = spark.table(f"{DB}.silver_epi2024results").select(
    F.col("iso").alias("iso3"),
    F.col("code").cast(IntegerType()).alias("iso_numeric"),
    F.col("country").alias("country_name_epi")
).dropna(subset=["iso3"]).dropDuplicates(["iso3"])

wb  = spark.table(f"{DB}.silver_wb").select(
    F.col("country_code").alias("wb_code"),
    F.col("country_name").alias("country_name_wb")
).dropna(subset=["wb_code"]).dropDuplicates(["wb_code"])

dim_country = (epi.alias("e")
  .join(wb.alias("w"), F.upper(F.col("e.iso3")) == F.upper(F.col("w.wb_code")), "left")
  .select(
      F.coalesce(F.col("e.country_name_epi"), F.col("w.country_name_wb")).alias("country_name_std"),
      F.col("e.iso3"),
      F.col("e.iso_numeric"),
      F.col("w.wb_code")
  )
  .dropDuplicates(["iso3"])
  .withColumn("country_key", stable_key(["iso3"]))
  .select("country_key","iso3","iso_numeric","wb_code","country_name_std")
)

# Save as oem_lh.gold_dim_country  (note underscore, not dot)
write_tbl(dim_country, "gold_dim_country")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# gold.dim_material

# CELL ********************

proc = spark.table(f"{DB}.silver_procurement").select(
    F.initcap(F.trim("materialname")).alias("material")
)
sup  = spark.table(f"{DB}.silver_globalsupplyshares").select(
    F.initcap(F.trim("material")).alias("material")
)
materials = (proc.union(sup)
                  .dropna()
                  .dropDuplicates()
                  .withColumn("material_name_std", F.regexp_replace("material", r"\s+", " "))
)

# simple grouping rules (extend as needed)
grp_map = F.create_map(
    [F.lit(x) for x in [
      "Lithium","Battery metals","Graphite","Battery metals",
      "Copper","Base metals","Nickel","Battery metals","Cobalt","Battery metals",
      "Lead","Base metals","Aluminum","Base metals"
    ]]
)
dim_material = (materials
  .withColumn("commodity_group", grp_map.getItem(F.col("material_name_std")))
  .withColumn("unit_base", F.lit("kg"))
  .withColumn("material_key", stable_key(["material_name_std"]))
  .select("material_key","material_name_std","commodity_group","unit_base")
)

write_tbl(dim_material, "gold_dim_material")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# gold.dim_indicator (EPI + WB, no bridge; optional parent for rollups)

# CELL ********************

epi_vars = spark.table(f"{DB}.`silver_epi2024variables2024-12-11`").select(
    F.lit("EPI").alias("source_system"),
    "type",
    F.col("abbreviation").alias("abbrev"),
    F.col("variable").alias("variable_name"),
    "policyobjective","issuecategory","weight","description",
    F.lit(None).cast(StringType()).alias("indicator_code"),
    # Parent logic: EPI → policyobjective or issuecategory (light touch)
    F.coalesce("policyobjective","issuecategory").alias("parent_label")
).withColumn("indicator_key", stable_key(["source_system","abbrev","variable_name"]))

wb_vars = (spark.table(f"{DB}.silver_wb")
  .select("indicator_code","indicator_name","topic")
  .dropna(subset=["indicator_code"])
  .dropDuplicates(["indicator_code","indicator_name"])
  .select(
      F.lit("WB").alias("source_system"),
      F.lit(None).cast(StringType()).alias("type"),
      F.lit(None).cast(StringType()).alias("abbrev"),
      F.col("indicator_name").alias("variable_name"),
      F.lit(None).cast(StringType()).alias("policyobjective"),
      F.lit(None).cast(StringType()).alias("issuecategory"),
      F.lit(None).cast(FloatType()).alias("weight"),
      F.lit(None).cast(StringType()).alias("description"),
      "indicator_code",
      F.col("topic").alias("parent_label")
  ).withColumn("indicator_key", stable_key(["source_system","indicator_code"]))
)

dim_indicator_base = epi_vars.unionByName(wb_vars, allowMissingColumns=True)

# self-parent map (label→key) only where label exists
parents = (dim_indicator_base.filter(F.col("parent_label").isNotNull())
           .select("source_system", F.col("parent_label").alias("variable_name"))
           .dropDuplicates()
           .withColumn("parent_indicator_key", stable_key(["source_system","variable_name"])))

dim_indicator = (dim_indicator_base
  .join(parents, on=["source_system","variable_name"], how="left")
  .select("indicator_key","source_system","type","abbrev","variable_name",
          "policyobjective","issuecategory","indicator_code","weight","description",
          "parent_indicator_key")
)

write_tbl(dim_indicator, "gold_dim_indicator")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# gold.dim_stage

# CELL ********************

dim_stage = spark.createDataFrame(
    [("E","Extraction"),("P","Processing")],
    ["stage_code","stage_name"]
).withColumn("stage_key", stable_key(["stage_code"])
).select("stage_key","stage_code","stage_name")

write_tbl(dim_stage, "gold_dim_stage")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# gold.dim_date

# CELL ********************

from pyspark.sql import functions as F
from pyspark.sql.types import IntegerType, DateType

DB = "oem_lh"  # per your quick-fix naming

# 1) Get min/max date from procurement (guard for empty/nulls)
src_dates = (spark.table(f"{DB}.silver_procurement")
               .select(F.col("date").cast(DateType()).alias("d"))
               .dropna())

mm = src_dates.agg(F.min("d").alias("min_d"), F.max("d").alias("max_d")).first()

# If no dates exist yet, make a tiny default window (last 365 days)
if mm is None or mm.min_d is None or mm.max_d is None:
    end   = F.current_date()
    start = F.date_add(end, -365)
    date_seq_df = spark.range(1).select(F.sequence(start, end).alias("dseq"))
else:
    start = F.lit(mm.min_d)
    end   = F.lit(mm.max_d)
    date_seq_df = spark.range(1).select(F.sequence(start, end).alias("dseq"))

# 2) Explode sequence → one row per day
df = date_seq_df.select(F.explode(F.col("dseq")).alias("date"))

# 3) Derive attributes
dim_date = (df
  .withColumn("date_key", F.date_format("date","yyyyMMdd").cast(IntegerType()))
  .withColumn("year",       F.year("date"))
  .withColumn("month",      F.month("date"))
  .withColumn("day",        F.dayofmonth("date"))
  .withColumn("month_name", F.date_format("date","MMM"))
  .select("date_key","date","year","month","day","month_name")
)

write_tbl(dim_date, "gold_dim_date")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# #### Facts
# 
# Helper lookups

# CELL ********************

dim_country_lu  = spark.table(f"{DB}.gold_dim_country").select("country_key","iso3","country_name_std")
dim_material_lu = spark.table(f"{DB}.gold_dim_material").select("material_key","material_name_std")
dim_stage_lu    = spark.table(f"{DB}.gold_dim_stage").select("stage_key","stage_code")
dim_ind_lu      = spark.table(f"{DB}.gold_dim_indicator").select("indicator_key","source_system","abbrev","indicator_code","variable_name")
dim_date_lu     = spark.table(f"{DB}.gold_dim_date").select("date_key","date")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# gold.fact_epi_score (wide → long)

# CELL ********************

epi_res = spark.table(f"{DB}.silver_epi2024results")

id_cols = {"code","iso","country"}
metric_cols = [c for c in epi_res.columns if c not in id_cols]
if not metric_cols:
    raise ValueError("No metric columns found in silver_epi2024results.")

epi_long = (
    epi_res.select(
        F.col("iso"),
        F.map_from_arrays(
            F.array([F.lit(c) for c in metric_cols]),
            F.array([F.col(c).cast("double") for c in metric_cols])
        ).alias("kv")
    )
    .select("iso", F.explode("kv").alias("abbrev","score"))
    .filter(F.col("score").isNotNull())
)

fact_epi_score = (
  epi_long
    .join(dim_country_lu, on=epi_long.iso == dim_country_lu.iso3, how="left")
    .join(dim_ind_lu.filter(F.col("source_system")=="EPI").select("indicator_key","abbrev"), on="abbrev", how="left")
    .withColumn("year", F.lit(2024).cast(IntegerType()))
    .select(F.col("country_key"), F.col("indicator_key"), "year", F.col("score"))
)

write_tbl(fact_epi_score, "fact_epi_score")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# oem_lh.fact_supply_share

# CELL ********************

sup = spark.table(f"{DB}.silver_globalsupplyshares").select(
    F.initcap(F.trim("material")).alias("material"),
    F.col("stage"),
    F.col("country"),
    F.regexp_replace("share", "[<%]", "").cast("double").alias("share_pct"),
    F.col("t").cast("double").alias("intensity_t")
)

fact_supply_share = (sup
  .join(dim_material_lu, on=F.col("material")==dim_material_lu.material_name_std, how="left")
  .join(dim_country_lu,  on=F.col("country")==dim_country_lu.country_name_std,   how="left")
  .join(dim_stage_lu,    on=F.col("stage")==dim_stage_lu.stage_code,             how="left")
  .withColumn("year", F.lit(2023).cast(IntegerType()))
  .select("material_key","stage_key","country_key","year","share_pct","intensity_t"))

write_tbl(fact_supply_share, "fact_supply_share")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# oem_lh.fact_procurement

# CELL ********************

from pyspark.sql import functions as F

# Lookup (as before)
dim_country_lu  = spark.table(f"{DB}.gold_dim_country").select("country_key","iso3","country_name_std")
dim_material_lu = spark.table(f"{DB}.gold_dim_material").select("material_key","material_name_std")
dim_stage_lu    = spark.table(f"{DB}.gold_dim_stage").select("stage_key","stage_code")
dim_ind_lu      = spark.table(f"{DB}.gold_dim_indicator").select("indicator_key","source_system","abbrev","indicator_code","variable_name")
dim_date_lu     = spark.table(f"{DB}.gold_dim_date").select("date_key","date")

# Source
proc = spark.table(f"{DB}.silver_procurement")

# Unit normalization (extend as needed)
unit_norm = F.create_map(*[
    F.lit("kg"),F.lit(1.0),
    F.lit("g"), F.lit(0.001),
    F.lit("t"), F.lit(1000.0),
    F.lit("tonne"),F.lit(1000.0)
])

# Alias frames to avoid attribute confusion
p = (proc
     .withColumn("txn_date", F.col("date").cast("date"))
     .withColumn("material_name_std", F.initcap(F.trim("materialname")))
    ).alias("p")

d = dim_date_lu.alias("d")
c = dim_country_lu.alias("c")
m = dim_material_lu.alias("m")

# Build fact
fact_procurement = (
    p.join(d, F.col("p.txn_date") == F.col("d.date"), "left")
     .withColumn("quantity_base",
                 F.col("p.quantity") * unit_norm.getItem(F.lower(F.col("p.unit"))))
     .withColumn("spend_eur",
                 F.col("quantity_base") * F.col("p.unitpriceeur"))
     .join(m, F.col("p.material_name_std") == F.col("m.material_name_std"), "left")
     .join(c.select(F.col("country_key").alias("supplier_hq_country_key"),
                    F.col("country_name_std").alias("hq_name")),
           F.col("p.headquarterscountry") == F.col("hq_name"), "left")
     .join(c.select(F.col("country_key").alias("production_country_key"),
                    F.col("country_name_std").alias("prod_name")),
           F.col("p.productioncountry") == F.col("prod_name"), "left")
     .select(
         F.col("d.date_key"),
         F.col("m.material_key"),
         F.col("supplier_hq_country_key"),
         F.col("production_country_key"),
         F.col("quantity_base"),
         F.col("p.unitpriceeur").alias("unitprice_eur"),
         F.col("spend_eur")
     )
)

write_tbl(fact_procurement, "fact_procurement")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
