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
# Pipeline run identifier — used by bronze_load_metadata for gold coordination
# (task-029). The pipeline sets this to @pipeline().RunId; when empty (manual
# notebook run, local test) the watermark functions skip the exclude-current-run
# filter and fall back to the latest SUCCESS row regardless of execution_id.
p_execution_id = ""

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.functions import col, expr, regexp_replace, substring
from pyspark.sql.types import (IntegerType,StringType,DoubleType,StructType,StructField,
                               DateType,TimestampType,LongType)
from delta.tables import DeltaTable
from datetime import datetime, timedelta, date

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## High-water mark tracking (task-029)
# `bronze_load_metadata` records one row per pipeline run per tracked source table.
# `get_last_load_date` reads the last SUCCESSful run's max date; `update_load_metadata`
# appends a SUCCESS or FAILED row. The effective watermark for this run is resolved
# once (here) and used by both the silver read below and — via the same mechanism —
# the gold read in silver-to-gold2. See `.claude/support/documents/incremental_load_strategy.md § 4-5`.

# CELL ********************

# --- bronze_load_metadata schema (single source of truth; mirrored in src/transformations/watermark.py) ---
METADATA_SCHEMA = StructType([
    StructField("source_table", StringType(), False),       # e.g. "bronze_procurement_transactional"
    StructField("last_load_date", DateType(), False),        # max date loaded (watermark)
    StructField("load_timestamp", TimestampType(), False),    # when this row was written
    StructField("rows_loaded", LongType(), True),            # row count in this load (NULL on FAILED)
    StructField("load_status", StringType(), False),         # SUCCESS | FAILED | IN_PROGRESS
    StructField("execution_id", StringType(), True),          # pipeline run id (gold coordination)
])

DEFAULT_WATERMARK = "1900-01-01"
DEFAULT_SOURCE_TABLE = "bronze_procurement_transactional"
METADATA_TABLE_FQN = "oem_lh.bronze_load_metadata"


def resolve_effective_watermark(p_full_load, p_from_date, last_load_date):
    """Resolve the effective watermark for this run as a "YYYY-MM-DD" string.

    Precedence (criterion 3):
      1. p_full_load == "true"          -> "1900-01-01"  (full load; load from epoch)
      2. p_from_date != "1900-01-01"    -> p_from_date   (explicit manual override)
      3. last_load_date is not None     -> strftime(last_load_date)
      4. otherwise                      -> "1900-01-01"  (no prior SUCCESS row)

    The "1900-01-01" value of p_from_date is the "not explicitly set" sentinel:
    p_full_load=true is the explicit "load from epoch" path, so a caller that
    wants a full refresh sets p_full_load rather than relying on the default.
    """
    if (p_full_load or "").strip().lower() == "true":
        return DEFAULT_WATERMARK
    override = (p_from_date or "").strip()
    if override and override != DEFAULT_WATERMARK:
        return override
    if last_load_date is not None:
        return last_load_date.strftime("%Y-%m-%d")
    return DEFAULT_WATERMARK


def metadata_row(source_table, last_load_date, rows_loaded, status,
                 execution_id=None, now=None):
    """Build ONE metadata row tuple matching METADATA_SCHEMA, for append."""
    ts = now if now is not None else datetime.now()
    if isinstance(last_load_date, str):
        last_load_date = datetime.strptime(last_load_date, "%Y-%m-%d").date()
    elif isinstance(last_load_date, datetime):
        last_load_date = last_load_date.date()
    return (source_table, last_load_date, ts, rows_loaded, status, execution_id)


def get_last_load_date(metadata_df, source_table, exclude_execution_id=None):
    """Return the last SUCCESSful load's last_load_date for source_table, or None.

    exclude_execution_id: if non-empty, rows with this execution_id are excluded.
        silver-to-gold2 passes the current run's execution_id so it reads the
        PREVIOUS run's watermark (bronze-to-silver has already written its
        SUCCESS row by the time gold starts), keeping both layers on the same
        effective watermark for a given run.
    """
    q = (metadata_df
         .filter(F.col("source_table") == source_table)
         .filter(F.col("load_status") == "SUCCESS"))
    if exclude_execution_id:
        q = q.filter(F.col("execution_id") != F.lit(exclude_execution_id))
    row = (q.orderBy(F.col("load_timestamp").desc())
            .limit(1)
            .select("last_load_date")
            .collect())
    if not row:
        return None
    ld = row[0]["last_load_date"]
    if ld is None:
        return None
    if isinstance(ld, datetime):
        return ld.date()
    return ld


def update_load_metadata(source_table, last_load_date, rows_loaded, status,
                          execution_id=None, now=None):
    """Append one metadata row to bronze_load_metadata (creates the table on first call)."""
    row = metadata_row(source_table, last_load_date, rows_loaded, status,
                       execution_id=execution_id, now=now)
    df = spark.createDataFrame([row], schema=METADATA_SCHEMA)
    try:
        spark.sql(f"CREATE TABLE IF NOT EXISTS {METADATA_TABLE_FQN} "
                  f"USING DELTA AS SELECT * FROM df")
    except Exception:
        # Table already exists (normal case after first run); the append below
        # will re-raise if the table genuinely cannot be written.
        pass
    df.write.format("delta").mode("append").saveAsTable(METADATA_TABLE_FQN)


# --- Resolve the effective watermark for THIS run ---
# Auto-retrieve the last SUCCESSful load's watermark (excludes the current run's
# execution_id so gold — which runs after us — reads the same previous-run
# watermark rather than the row we are about to write).
_metadata_df = spark.table(METADATA_TABLE_FQN) if spark.catalog.tableExists(METADATA_TABLE_FQN) else None
_last_load_date = get_last_load_date(_metadata_df, DEFAULT_SOURCE_TABLE) if _metadata_df is not None else None
effective_from_date = resolve_effective_watermark(p_full_load, p_from_date, _last_load_date)
print(f"[watermark] p_full_load={p_full_load!r} p_from_date={p_from_date!r} "
      f"last_SUCCESS={_last_load_date} execution_id={p_execution_id!r} "
      f"-> effective_from_date={effective_from_date!r}")

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

# overwriteSchema: bronze_epi{year}results is now produced by bronze_ingest_epi
# (pandas -> spark), which types the score columns as double. The retired
# EPI_file2table dataflow had landed them as text, so the pre-existing
# silver_epi{year}results carries EPI as string and a plain mode("overwrite")
# fails with DELTA_FAILED_TO_MERGE_FIELDS. This is a full-snapshot replace, so
# replacing the schema is correct — same reason silver_wgi carries it below.
df_selected.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(f'silver_epi{p_epi_year}results')

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
# `t` is the EU CRM trade parameter (0.8 EU-sourced, 1.0 baseline non-EU, >1 under
# export restrictions) and is a load-bearing input to the Supply Risk model — it is
# carried through to silver rather than dropped (task-038_1; see spec_v1
# § Data Architecture -> Supply Shares). It was previously dropped here on the basis
# of stale documentation calling it "unknown field"; DEC-001 identified it.
df_newheaders = df.toDF(*new_columns)

# `share` deliberately stays a raw string ('45%', '<1%') at this layer. The censored-share
# convention ('<1%' -> 0.5) is applied once, in silver-to-gold2's fact_supply_share build,
# which is the single source of truth for it (task-028). Do not fork it into silver.

display(df_newheaders)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# overwriteSchema: task-038_1 stops dropping `t`, so this write goes from 4 columns to 5
# against a silver_globalsupplyshares that already exists in the lakehouse with the old
# 4-column shape. Delta enforces schema on overwrite, so a plain mode("overwrite") fails
# with DELTA_FAILED_TO_MERGE_FIELDS. This is a full-snapshot replace, so replacing the
# schema is correct — same reason silver_epi{year}results and silver_wgi carry it, the
# latter for the identical case of restoring previously-dropped columns (task-031/035).
df_newheaders.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable('silver_globalsupplyshares')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## EUSupplyShares: bronze --> silver
# The EU CRM study ships two complementary tables: GlobalSupplyShares (where a material is
# produced worldwide) and EUSupplyShares (where the EU actually sources it from). Both are
# required inputs to the Supply Risk model. Until task-038_1 the EU table was landed in
# bronze on every run but had no silver consumer.
# This block applies the SAME rules as the Global block above — header normalisation and
# nothing else — so both silver tables carry an identical column contract and the gold union
# in task-038_2 needs no per-source special-casing.

# CELL ********************

df_eu = spark.sql("SELECT * FROM oem_lh.`bronze_EUSupplyShares`")

# rename column headers — identical rule to the Global table above
new_columns_eu = [c.lower().replace(' ', '_') for c in df_eu.columns]
df_eu_newheaders = df_eu.toDF(*new_columns_eu)

# Contract check: the gold union in task-038_2 assumes these two silver tables are
# column-compatible. Assert it here, at the boundary where a mismatch is cheap to see,
# rather than letting it surface as a confusing union error one layer downstream.
global_cols = set(df_newheaders.columns)
eu_cols = set(df_eu_newheaders.columns)
if global_cols != eu_cols:
    only_global = sorted(global_cols - eu_cols)
    only_eu = sorted(eu_cols - global_cols)
    raise ValueError(
        "silver supply-share column contract mismatch — task-038_2's union will not work.\n"
        f"  only in silver_globalsupplyshares: {only_global}\n"
        f"  only in silver_eusupplyshares:     {only_eu}\n"
        "Reconcile the two bronze sources (or widen the contract deliberately) before building gold."
    )

display(df_eu_newheaders)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# overwriteSchema for consistency with the other full-snapshot silver writes in this
# notebook. silver_eusupplyshares is new so there is no pre-existing schema to conflict
# with on the first run, but carrying the option keeps the table's shape free to follow
# bronze on later runs rather than failing the pipeline.
df_eu_newheaders.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable('silver_eusupplyshares')

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
# task-048: bronze now lands the source's RAW transaction date (the retired
# `bronze_azureSQLdb2table` dataflow used to correct it during ingestion; its Copy-activity
# replacement cannot transform). `correct_procurement_date` below undoes the source's
# day/year transposition, and runs BEFORE the look-back window.

# CELL ********************

# --- Source date correction (task-048; mirrored in src/transformations/procurement_dates.py) ---
# `dbo.procurement_transactional` stores each transaction date with its DAY and YEAR
# components transposed: the calendar year sits in the day position and the day-of-month
# sits in the year position as an offset from 2000. Raw `2015-01-24` means `2024-01-15`.
#
# This used to be fixed during ingestion by the `bronze_azureSQLdb2table` Dataflow Gen2,
# which built  CorrectedDate = #date(Day([Date])+2000, Month([Date]), Year([Date])-2000),
# dropped `Date` and renamed `CorrectedDate` to `Date`. That dataflow is retired: an SPN
# cannot refresh a Dataflow Gen2 and every fabric-cicd publish strips its credentials. Its
# replacement is a Copy activity, and a Copy activity cannot transform — so the correction
# moves here. Bronze now holds the source's raw (malformed) `Date`; silver corrects it,
# which also keeps bronze byte-faithful to the source (better medallion practice than
# folding the fix into the Copy activity's source query).
#
# NULL semantics: Power Query's #date() raised on an out-of-range component; Spark's
# make_date returns NULL instead when spark.sql.ansi.enabled=false (Fabric's default).
# A malformed row that would once have failed the whole dataflow refresh now lands as a
# NULL date and is visible to the data-quality checks.
DATE_SWAP_EPOCH = 2000


def correct_procurement_date(df, column="Date"):
    """Undo the source system's day/year transposition on a procurement date column.

    Replaces `column` in place (preserving position, matching the retired mashup's
    add/drop/rename sequence) with make_date(day+2000, month, year-2000). Rows whose
    corrected components are not a real calendar date — and rows with a NULL raw date —
    yield NULL rather than raising.

    `to_date` is applied first so this is indifferent to whether the Copy activity landed
    bronze `Date` as a date or as a string; both produce identical output.
    """
    raw = F.to_date(F.col(column))
    return df.withColumn(
        column,
        F.make_date(
            F.dayofmonth(raw) + F.lit(DATE_SWAP_EPOCH),
            F.month(raw),
            F.year(raw) - F.lit(DATE_SWAP_EPOCH),
        ),
    )

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Read bronze procurement data — apply date filter for incremental loads.
# task-029: the window now keys off `effective_from_date` (auto-retrieved from
# bronze_load_metadata when the pipeline default "1900-01-01" is passed), not
# the raw p_from_date widget value. A p_full_load=true run still reads all bronze.
is_full_load = p_full_load.strip().lower() == "true"

# task-048: correct the transposed source date FIRST, then window. The ordering is
# load-bearing — everything downstream is expressed in CORRECTED-date space:
#   * the watermark: bronze_load_metadata.last_load_date is written from
#     silver_df.agg(F.max("date")), a corrected date. Filtering raw bronze dates
#     against a corrected-space watermark compares two different calendars.
#   * the delete-insert boundary: `window_min_date` below is the window's minimum
#     date. A window selected on raw dates with a boundary computed on corrected
#     ones would DELETE a range the append does not restore — silent data loss.
# This is the SILVER look-back, and it is now the ONLY one. There is no bronze-side
# incremental filter: both replacing Copy activities are plain full-table copies with
# no source query, so do not go looking for one. The retired mashup did contain a
# `WHERE Date >= '<lookback>'` pushdown via Value.NativeQuery, but it sat behind
# `if p_from_date = "1900-01-01" then <full table> else <native query>`, and the
# pipeline never passed p_from_date to the RefreshDataflow activity — so that branch
# was unreachable and bronze always full-loaded. The Copy activities therefore
# reproduce actual pre-migration runtime behaviour exactly; nothing was lost.
# See spec_v1.md § Data Architecture (Incremental vs Full Load) and
# .claude/support/documents/architecture/orchestration.md § p_from_date.
df1_all = correct_procurement_date(
    spark.sql("SELECT * FROM oem_lh.bronze_procurement_transactional")
)

if is_full_load:
    df1 = df1_all
    print("Procurement: FULL LOAD — reading all bronze records")
else:
    # Apply 7-day look-back window for late-arriving data
    watermark_date = datetime.strptime(effective_from_date, "%Y-%m-%d")
    lookback_date = watermark_date - timedelta(days=7)
    lookback_str = lookback_date.strftime("%Y-%m-%d")
    df1 = df1_all.filter(F.col("Date") >= F.to_date(F.lit(lookback_str)))
    print(f"Procurement: INCREMENTAL LOAD — reading records from {lookback_str} "
          f"(7-day look-back from effective_from_date={effective_from_date})")

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
#
# task-029: wrap the write in try/except and append a bronze_load_metadata row — SUCCESS with the
# new max date loaded (advances the watermark) or FAILED with the effective_from_date that was
# attempted (does NOT advance — next run re-reads from the same watermark). The FAILED row's
# last_load_date records "what we tried to load from", not a new max.
try:
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
            # window's min date, not effective_from_date: deleting only >= effective_from_date would
            # leave the [look-back, effective_from_date) rows un-deleted and then re-append them,
            # duplicating that range.)
            window_min_date = silver_df.agg(F.min("date")).first()[0]
            if window_min_date is None:
                print("Procurement: incremental window is empty — nothing to delete-insert")
            else:
                target_table = DeltaTable.forName(spark, "oem_lh.silver_procurement")
                target_table.delete(F.col("date") >= F.lit(window_min_date))
                silver_df.write.format("delta").mode("append").saveAsTable("silver_procurement")
                print(f"Procurement: delete-insert complete for date >= {window_min_date} "
                      f"({silver_df.count():,} rows re-inserted)")

    # SUCCESS — advance the watermark to the max date actually loaded this run.
    # On a full load the watermark advances to the overall max; on an incremental
    # load it advances to the window's max (the newest transaction seen).
    # If the window was empty (no rows loaded), skip the SUCCESS row — the watermark
    # stays at the previous value, which is correct (no new data was loaded).
    _max_date_loaded = silver_df.agg(F.max("date")).first()[0]
    _rows_loaded = silver_df.count()
    if _max_date_loaded is not None:
        update_load_metadata(DEFAULT_SOURCE_TABLE, _max_date_loaded, _rows_loaded,
                              status="SUCCESS", execution_id=p_execution_id)
        print(f"[watermark] SUCCESS row written — source={DEFAULT_SOURCE_TABLE} "
              f"last_load_date={_max_date_loaded} rows={_rows_loaded} execution_id={p_execution_id!r}")
    else:
        print(f"[watermark] no SUCCESS row written — window was empty (0 rows loaded); "
              f"watermark stays at previous value. execution_id={p_execution_id!r}")
except Exception as _load_err:
    # FAILED — record the watermark that was attempted (does NOT advance) and re-raise
    # so the pipeline error handler also logs the failure to gold_pipeline_execution_log.
    update_load_metadata(DEFAULT_SOURCE_TABLE, effective_from_date, 0,
                          status="FAILED", execution_id=p_execution_id)
    print(f"[watermark] FAILED row written — attempted_from={effective_from_date} "
          f"execution_id={p_execution_id!r} error={_load_err!r}")
    raise

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

# task-035: silver_wgi migrates from the retired 3-col identity shape to the task-031
# long format (adds indicator_code / year / value), so the overwrite must replace the
# schema too. overwriteSchema is safe here — silver_wgi is a full-snapshot rebuild each run.
df_wgi_clean.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("silver_wgi")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
