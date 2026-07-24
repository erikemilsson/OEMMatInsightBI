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
# This notebook does the following:
# - cleans headers,
# - trims entries,
# - type casts,
# - light normalization (no business joins).
# Supports incremental loading for procurement data via p_full_load / p_from_date parameters.


# PARAMETERS CELL ********************

# Pipeline parameters — overridden by Fabric pipeline at runtime
p_full_load = "false"
p_from_date = "1900-01-01"
# EPI vintage — single-sources the epi{year}results table names below (task-042).
# Matches bronze_ingest_epi.Notebook's p_epi_year default; keep in sync with the
# pipeline so bronze and silver never diverge on the vintage.
p_epi_year = "2024"

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
df = spark.sql(f"SELECT * FROM oem_lh.bronze_epi{p_epi_year}results")

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

df_selected.write.format("delta").mode("overwrite").saveAsTable(f'silver_epi{p_epi_year}results')

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
# Supports incremental loading when p_full_load is "false". Uses a date-partition
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

# -----------------------------------------------------------------------------
# task-031 — silver_wgi MUST preserve Year and Value
# -----------------------------------------------------------------------------
# spec_v1 § Data Transformations #3 makes preservation mandatory: the governance
# scores are the WGIᶜ weight in DEC-001's supply-risk formula
# (HHI_WGI,t = Σ_c (Sᶜ)² · WGIᶜ · tᶜ), so task-038 cannot be built until the values
# survive into silver. The previous projection kept three identity columns only,
# which both discarded every score AND left ~28 identical rows per country-indicator
# (one per ingested year, values dropped) — duplication that looked like a grain bug
# but was really the time series with its payload removed.
#
# REQUIRED BRONZE SHAPE: the long-format table written by bronze_ingest_wgi.Notebook
# from the World Bank API — one row per country per indicator per year, carrying
# `Indicator Code`, `Year` and `Value`.
#
# WHY THIS FAILS LOUDLY INSTEAD OF FALLING BACK: the retired WGI_file2table.Dataflow
# produces a different and quietly INCOMPATIBLE table — four columns (`Country Name`,
# `Country Code`, `Series Name`, `Percentile Rank 2023`) holding 2023 PERCENTILE RANKS
# (0–100), with ": Percentile Rank" stripped from the series name, versus the API's
# ESTIMATES (−2.5…+2.5). Accepting it would land a differently-scaled quantity in
# `value` under the same column name, and WGIᶜ would silently mean something else —
# the same class of invisible unit error task-030 removed from the spend calculation.
# A hard stop with an actionable message is the cheaper failure.
REQUIRED_WGI_COLUMNS = ["Indicator Code", "Year", "Value"]
# Case-insensitive because Spark's own column resolution is: a bronze writer that
# emitted "year" instead of "Year" would resolve fine in the select below, so raising
# on it here would be a spurious failure rather than a caught defect.
_wgi_columns_present = {c.lower() for c in df_wgi.columns}
missing_wgi_columns = [c for c in REQUIRED_WGI_COLUMNS
                       if c.lower() not in _wgi_columns_present]
if missing_wgi_columns:
    raise RuntimeError(
        f"bronze_WGI is missing {missing_wgi_columns}.\n"
        f"  Columns present: {df_wgi.columns}\n"
        "  CAUSE: bronze_WGI is still being written by the retired WGI_file2table.Dataflow "
        "(Excel, 2023 percentile ranks, ~5 indicators) rather than by "
        "bronze_ingest_wgi.Notebook (World Bank API, long format, 6 indicators, estimates).\n"
        "  WHY NOT FALL BACK: silver_wgi must preserve Year/Value "
        "(spec_v1 § Data Transformations #3, DEC-001) — the identity-only projection this "
        "notebook used to emit is exactly the defect task-031 removed, and the dataflow's "
        "percentile ranks are not interchangeable with the API's estimates.\n"
        "  FIX: complete task-035 — replace the 'bronze_WGI' RefreshDataflow activity in "
        "orchestrator_pipeline_bronze_to_gold with a TridentNotebook activity calling "
        "bronze_ingest_wgi. Running bronze_ingest_wgi by hand unblocks a single run, but "
        "the next pipeline run overwrites bronze_WGI from the dataflow again."
    )

# Standardize columns: snake_case names, UPPER ISO3, typed year/value.
df_wgi_typed = df_wgi.select(
    F.upper(F.trim(F.col("`Country Code`"))).alias("country_iso3"),
    F.trim(F.col("`Country Name`")).alias("country_name"),
    F.trim(F.col("`Series Name`")).alias("indicator_name"),
    F.trim(F.col("`Indicator Code`")).alias("indicator_code"),
    F.col("`Year`").cast(IntegerType()).alias("year"),
    F.col("`Value`").cast(DoubleType()).alias("value")
).filter(
    (F.col("country_iso3").isNotNull()) &
    (F.col("indicator_name").isNotNull()) &
    (F.col("year").isNotNull()) &
    # A NULL Value is how the World Bank API says "no observation for this
    # country/indicator/year" — it returns a row for every year in the requested
    # range regardless. Those rows are not governance scores, so they do not belong
    # in a cleaned layer: keeping them would leave empty rows for the years WGI was
    # never published (it was biennial 1996–2000) and force every downstream
    # "latest score" query to re-filter. Coverage is measured on real observations.
    (F.col("value").isNotNull())
)

# Grain: one row per (country_iso3, indicator_name, year) — the contract task-031
# declares. Deduplication is keyed on `indicator_code` because that is the source's
# real identifier, and de-duplicating on the NAME could silently discard a genuine
# observation if two codes ever shared a name (data loss beats a grain violation only
# in the wrong direction — the medallion rule here is no silent data loss).
# Making the dedupe structural rather than assumed also means a re-ingest that appends
# instead of overwriting cannot fan out the gold join.
#
# CAVEAT: dropDuplicates picks an arbitrary survivor. That is safe only because
# bronze_ingest_wgi writes with mode("overwrite"), so the same (country, code, year)
# cannot carry two DIFFERENT values in one snapshot. There is no load-timestamp column
# to order by, so a latest-wins rule is not expressible here — if bronze ever becomes
# append-mode, this needs a real dedupe key, not just a tiebreak.
df_wgi_clean = df_wgi_typed.dropDuplicates(["country_iso3", "indicator_code", "year"])

# The declared grain uses indicator_name while the dedupe uses indicator_code. Those
# are equivalent only while the name↔code mapping is 1:1 — true of WGI's six
# dimensions, but asserted rather than assumed, because a collision would leave
# silver_wgi silently non-unique at its stated grain AND make the gold coverage rule
# (which counts DISTINCT indicator_name) undercount that country's indicators.
_name_code_pairs = df_wgi_clean.select("indicator_name", "indicator_code").distinct()
_pair_total, _name_total = (
    _name_code_pairs.count(),
    _name_code_pairs.select("indicator_name").distinct().count(),
)
if _pair_total != _name_total:
    raise RuntimeError(
        f"WGI indicator_name -> indicator_code is not 1:1 ({_pair_total} distinct pairs "
        f"for {_name_total} distinct names). silver_wgi's declared grain "
        "(country_iso3, indicator_name, year) is therefore not unique, and "
        "silver-to-gold2's COUNT(DISTINCT indicator_name) coverage rule would undercount. "
        "Either the World Bank renamed an indicator mid-series or two codes collided — "
        "reconcile before loading."
    )

# Per-run visibility into what actually reached silver — the analogue of the
# unit-domain report in silver-to-gold2. Without it, a partial API fetch (an indicator
# that 404s, a truncated year range) is invisible until the gold coverage flag
# quietly drops every country.
print("--- silver_wgi: governance indicators preserved ---")
(
    df_wgi_clean
    .groupBy("indicator_code", "indicator_name")
    .agg(
        F.countDistinct("country_iso3").alias("countries"),
        F.min("year").alias("first_year"),
        F.max("year").alias("last_year"),
        # NOT aliased `count`: pyspark Row subclasses tuple, so row.count would
        # return the bound tuple method rather than the value.
        F.count(F.lit(1)).alias("observations")
    )
    .orderBy("indicator_code")
).show(truncate=False)

# The gold coverage rule in silver-to-gold2 requires all SIX indicators per country.
# If fewer than six ever reach silver, that rule cannot be satisfied by ANY country
# and the Data Gaps page would report zero WGI coverage — worth a warning here, at
# the layer that can explain why, rather than a mystery zero two notebooks later.
EXPECTED_WGI_INDICATORS = 6
observed_wgi_indicators = df_wgi_clean.select("indicator_code").distinct().count()
if observed_wgi_indicators != EXPECTED_WGI_INDICATORS:
    print(f"⚠️  WARNING: silver_wgi carries {observed_wgi_indicators} distinct indicators, "
          f"expected {EXPECTED_WGI_INDICATORS}. gold_data_gaps requires all "
          f"{EXPECTED_WGI_INDICATORS} for a country to count as governance-covered, so "
          f"WGI coverage will read 0. Check the bronze_ingest_wgi fetch log.")

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
