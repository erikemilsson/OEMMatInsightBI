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

# PARAMETERS CELL ********************

# Pipeline parameters — overridden by the orchestrator pipeline when invoked.
#
# ALL of them must live in THIS ONE CELL. Fabric permits exactly one parameters cell
# per notebook and injects the runtime override directly beneath it, so any parameter
# assigned in a different cell is never overridden — it silently keeps its default.
# EPI_YEAR was briefly given its own parameters cell for task-042 crit 1; because that
# is a move rather than an addition, it took the marker off p_full_load/p_from_date and
# pinned gold to an incremental load no matter what the pipeline passed (invisible on a
# p_full_load=false run, wrong on a full one). Hence the consolidation.
#
# Every derivation that reads these — EPI_SILVER_TBL below, _is_full_load and
# _watermark_date further down — lives in a LATER cell, which is what makes the
# injection ordering correct.
p_full_load = "false"
p_from_date = "1900-01-01"
EPI_YEAR = 2024
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

# MARKDOWN ********************

# ## Setup and Conventions

# CELL ********************

from pyspark.sql import functions as F, Window as W
from pyspark.sql.types import IntegerType, StringType, FloatType, DateType, StructType, StructField, DoubleType, LongType, TimestampType
import logging
from datetime import datetime

# Configuration
DB = "oem_lh"  # Lakehouse database/schema
LOG_UNMAPPED = True  # Enable logging of unmapped values
FAIL_ON_UNMAPPED = False  # Whether to fail pipeline on unmapped values

# task-012_3 — V-Order: write Parquet/Delta columnar files in V-Order so DirectLake
# scans are faster for Power BI. Fabric-specific (no effect outside Fabric); adds write
# cost but improves read perf on the gold tables the semantic model binds to. Set once
# at session start so every .write.format("delta") in this notebook inherits it.
# DEPLOY NOTE (acceptance criterion 2 — Erik's step in Fabric): after deploying this
# notebook, run `OPTIMIZE <table>` once on every existing gold table to compact and
# re-encode already-written files in V-Order. New writes pick V-Order up automatically;
# OPTIMIZE back-fills legacy files. The per-merge OPTIMIZE in merge_tbl and the
# incremental fact_procurement write only compact rows they touch — they do NOT
# re-encode the whole table.
spark.conf.set("spark.sql.parquet.vorder.enabled", "true")

# EPI vintage: EPI_YEAR now lives in the dedicated parameter cell at the top of this
# notebook (task-042 crit 1) so the pipeline can single-source it; this derivation reads
# it AFTER Fabric's injected override, so it tracks the passed vintage. Keep in sync with
# bronze_ingest_epi.Notebook, which derives bronze_epi{year}results the same way.
EPI_SILVER_TBL = f"silver_epi{EPI_YEAR}results"

# Initialize logging
logger = spark._jvm.org.apache.log4j.LogManager.getLogger("SilverToGold")

# Create database if not exists
spark.sql(f"CREATE DATABASE IF NOT EXISTS {DB}")
spark.sql(f"USE {DB}")

def stable_key(cols):
    """Generate deterministic 32-bit surrogate key over business keys"""
    return (F.abs(F.xxhash64(*[F.coalesce(F.col(c).cast("string"), F.lit("∅")) for c in cols]))).cast("bigint")

def write_tbl(df, tbl_name):
    """Write DataFrame to Delta table with overwrite"""
    (df.write
       .format("delta")
       .mode("overwrite")
       .option("overwriteSchema","true")
       .saveAsTable(f"{DB}.{tbl_name}"))
    print(f"✓ Written {df.count():,} records to {DB}.{tbl_name}")

def merge_tbl(df, tbl_name, merge_condition):
    """Delta MERGE for incremental loads"""
    from delta.tables import DeltaTable
    target = DeltaTable.forName(spark, f"{DB}.{tbl_name}")
    (target.alias("target")
     .merge(df.alias("source"), merge_condition)
     .whenMatchedUpdateAll()
     .whenNotMatchedInsertAll()
     .execute())
    # OPTIMIZE after merge
    spark.sql(f"OPTIMIZE {DB}.{tbl_name}")
    print(f"✓ Merged records into {DB}.{tbl_name}")

def check_unmapped(df, join_col, name, fail=False):
    """Check for unmapped values after a join.

    Callsite history: task-028 deleted the duplicate fact_supply_share build that was
    this function's only caller (the surviving build reports the same three dimensions in
    more detail), leaving it definition-only for a time. task-038_3 gave it a live callsite
    again — the WGIᶜ join coverage check, in the fact_supply_share cell — so it is no
    longer retained-for-parity-only.

    This definition is also the production half of the parity contract asserted by
    tests/test_data_quality.py::test_check_unmapped_*_parity against
    src/transformations/data_quality.py — do not delete it without updating both.
    """
    unmapped = df.filter(F.col(join_col).isNull())
    count = unmapped.count()
    if count > 0:
        print(f"⚠️  Found {count:,} unmapped records for {name}")
        if LOG_UNMAPPED:
            unmapped.select(join_col).distinct().show(20, truncate=False)
        if fail and FAIL_ON_UNMAPPED:
            raise ValueError(f"Pipeline failed: {count} unmapped {name} records")
    return count

def unmapped_gap(condition, unmapped_type, gap_dimension, value_col):
    """
    Build ONE audit-row candidate for ONE failed dimension (task-027).

    Why this exists: the unmapped-audit tables used to store every original value on
    every unmapped row (material AND hq_country AND prod_country, unconditionally), so
    nothing downstream could tell WHICH join actually failed. The gap registry guessed
    with COALESCE(original_material, original_hq_country, original_prod_country) and got
    it wrong for every country gap — the registry filled with rows like
    gap_type='country' / gap_natural_key='Copper'. Each failed dimension now emits its
    own audit row carrying only its own value, so no consumer has to infer anything.

    Returns a struct when `condition` is true (that dimension failed to join) and NULL
    otherwise, so a source row explodes into 0..N audit rows — one per failed dimension.

      unmapped_type   the fine-grained slot that failed:
                      material | hq_country | prod_country   (procurement)
                      material | country | stage             (supply share)
      gap_dimension   the dimension the value belongs to: material | country | stage.
                      hq_country and prod_country both roll up to 'country' because the
                      remediation is identical (one country alias fixes both) and
                      data_quality_architecture.md keys gold_gap_registry.gap_type on the
                      coarse dimension.
      value_col       the source value that failed to join — and ONLY that value.

    All branches build an identically-named struct so F.array() over several candidates
    type-checks.
    """
    return F.when(
        condition,
        F.struct(
            F.lit(unmapped_type).alias("unmapped_type"),
            F.lit(gap_dimension).alias("gap_dimension"),
            value_col.cast("string").alias("unmapped_value"),
        ),
    )

# Pipeline execution timestamp
pipeline_run_ts = datetime.now()
print(f"Pipeline started at: {pipeline_run_ts}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## High-water mark tracking (task-029)
# `silver-to-gold2` consumes the SAME effective watermark that `bronze-to-silver`
# resolved for this run, via the same `bronze_load_metadata` mechanism — ONE
# watermark value per run, consumed by both layers (criterion 4). Gold runs AFTER
# silver in the pipeline, so bronze-to-silver has already written its SUCCESS row
# by the time we start; we exclude the current run's execution_id to read the
# PREVIOUS run's watermark (the one silver used for its look-back window).

# CELL ********************

# --- bronze_load_metadata schema (mirrored from src/transformations/watermark.py) ---
METADATA_SCHEMA = StructType([
    StructField("source_table", StringType(), False),
    StructField("last_load_date", DateType(), False),
    StructField("load_timestamp", TimestampType(), False),
    StructField("rows_loaded", LongType(), True),
    StructField("load_status", StringType(), False),
    StructField("execution_id", StringType(), True),
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

    exclude_execution_id: when non-empty, rows with this execution_id are excluded
        so gold reads the PREVIOUS run's watermark (bronze-to-silver has already
        written its SUCCESS row by the time gold starts).
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


# --- Resolve the effective watermark for THIS gold run ---
# Same precedence as bronze-to-silver; the exclude_execution_id filter means we
# read the PREVIOUS run's watermark (the one silver used), not the row silver
# just wrote for this run — so both layers window on the same value per run.
_metadata_df = (spark.table(METADATA_TABLE_FQN)
                if spark.catalog.tableExists(METADATA_TABLE_FQN) else None)
_last_load_date = (get_last_load_date(_metadata_df, DEFAULT_SOURCE_TABLE,
                                       exclude_execution_id=p_execution_id)
                   if _metadata_df is not None else None)
effective_from_date = resolve_effective_watermark(p_full_load, p_from_date, _last_load_date)
print(f"[watermark] gold — p_full_load={p_full_load!r} p_from_date={p_from_date!r} "
      f"last_SUCCESS(excluding this run)={_last_load_date} execution_id={p_execution_id!r} "
      f"-> effective_from_date={effective_from_date!r}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Initialize tracking lists for data quality

# CELL ********************

# These lists will collect all mapping issues for comprehensive reporting
mapping_issues = []
coverage_stats = []

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Mapping Tables for Data Standardization

# CELL ********************

# Adding confidence scores helps users understand data quality in visualizations
country_aliases_with_confidence = spark.createDataFrame([
    # Tier 1: Exact standard names (100% confidence)
    ("United States of America", "United States of America", 1.00, "exact_match"),
    ("United Kingdom", "United Kingdom", 1.00, "exact_match"),
    
    # Tier 2: Standard aliases and abbreviations (95% confidence) 
    ("USA", "United States of America", 0.95, "standard_alias"),
    ("US", "United States of America", 0.95, "standard_alias"),
    ("U.S.", "United States of America", 0.95, "standard_alias"),
    ("U.S.A.", "United States of America", 0.95, "standard_alias"),
    ("United States", "United States of America", 0.95, "standard_alias"),
    ("UK", "United Kingdom", 0.95, "standard_alias"),
    ("GB", "United Kingdom", 0.95, "standard_alias"),
    ("Great Britain", "United Kingdom", 0.95, "standard_alias"),
    ("England", "United Kingdom", 0.90, "partial_country"),  # Lower confidence as it's part of UK
    
    # Congo variations - CRITICAL: Multiple distinct countries involved
    ("DR Congo", "Dem. Rep. Congo", 0.95, "standard_alias"),
    ("DRC", "Dem. Rep. Congo", 0.95, "standard_alias"),
    ("DRC (HQ in South Africa)", "Dem. Rep. Congo", 0.85, "with_notation"),  # Lower confidence due to HQ notation
    ("Congo, Dem. Rep.", "Dem. Rep. Congo", 0.95, "standard_alias"),
    ("Congo, D.R.", "Dem. Rep. Congo", 0.95, "standard_alias"),
    ("Democratic Republic of the Congo", "Dem. Rep. Congo", 0.95, "standard_alias"),
    ("Congo", "Republic of Congo", 0.90, "ambiguous"),  # Lower confidence due to ambiguity
    
    # Korea variations - CRITICAL: These are different countries
    ("Korea, South", "South Korea", 0.95, "standard_alias"),
    ("Republic of Korea", "South Korea", 0.95, "standard_alias"),
    ("Korea, Rep.", "South Korea", 0.95, "standard_alias"),
    ("Korea, North", "North Korea", 0.95, "standard_alias"),
    ("Korea, Dem. People's Rep.", "North Korea", 0.95, "standard_alias"),
    
    # Turkey variations with encoding issues
    ("Türkiye", "Turkey", 0.90, "encoding_variant"),
    ("TÃ¼rkiye", "Turkey", 0.80, "corrupted_encoding"),  # Lower confidence for corrupted text
    ("TÃƒÂ¼rkiye", "Turkey", 0.80, "corrupted_encoding"),
    ("TÃƒÂ¯Â¿Â½rkiye", "Turkey", 0.80, "corrupted_encoding"),
    ("Turkyie", "Turkey", 0.85, "typo"),
    ("TÃ¯Â¿Â½rkiye", "Turkey", 0.80, "corrupted_encoding"),
    
    # Supply-shares source gaps (task-025, measured 2026-07-22 against the Global CSV).
    # EPI 2024 names CPV "Cabo Verde" and BRA "Brazil", so those are the standard
    # names dim_country carries and the ones these aliases must resolve to.
    ("Cape Verde", "Cabo Verde", 0.95, "standard_alias"),
    # 'Brasilia' is Brazil's CAPITAL CITY, not a country — a source-data error in
    # fact_GlobalSupplyShares&t.csv. Mapped deliberately at low confidence with an
    # honest match_type so it stays visible in the audit rather than being laundered
    # into a clean country mapping.
    ("Brasilia", "Brazil", 0.60, "source_error"),

    # Other important mappings
    ("Czechia", "Czech Republic", 0.95, "standard_alias"),
    ("UAE", "United Arab Emirates", 0.95, "standard_alias"),
    ("Syrian Arab Republic", "Syria", 0.95, "standard_alias"),
    # Direction corrected 2026-07-22 (task-025 crit 3): EPI 2024 names RUS "Russia",
    # so "Russia" is the standard name carried by gold_dim_country and resolves via
    # self-lookup. The alias previously pointed Russia -> "Russian Federation", a name
    # no dim row carries, so the inner join dropped it (orphaned alias) AND the World
    # Bank's standard spelling "Russian Federation" had no route to the dim.
    ("Russian Federation", "Russia", 0.95, "standard_alias"),
    ("Vietnam", "Viet Nam", 0.95, "standard_alias"),
    ("Hong Kong", "China", 0.85, "territory"),  # Lower confidence for territories
    ("French Guiana", "France", 0.85, "territory"),
], ["alias", "standard_name", "confidence", "match_type"])

# Material aliases remain similar but add confidence.
#
# REACHABILITY CONTRACT (task-028): every LHS below must satisfy initcap(lhs) == lhs.
# Source material names are initcap'd BEFORE this join (see materials_raw below) and
# before every fact join, and Spark's initcap lowercases everything after the first
# letter of each whitespace-delimited word ("High-Tensile" -> "High-tensile",
# "(ABS)" -> "(abs)"). An LHS that is not its own initcap can never be matched by any
# input, so it is dead weight that looks like a live mapping. Enforced by the assertion
# next to grp_map below and by tests/test_material_mapping.py — add rows only after
# checking them against that guard.
#
# Removed 2026-07-23 as provably unreachable (all three had initcap(lhs) != lhs, and
# all three were redundant anyway — initcap already collapses the source spelling onto
# the target): "STEEL (High-Tensile)" / "steel (high-tensile)" -> "Steel (high-tensile)"
# and "Electronics (Controllers, Sensors)" -> "Electronics (controllers, Sensors)".
# Case-only variants NEVER need an alias row here; initcap handles them for free.
MATERIAL_ALIASES = [
    # Spelling variations - high confidence
    ("Aluminum", "Aluminium", 0.95, "spelling_variant"),
    # Unifies the two spellings that both reached dim_material as distinct materials
    # (task-028 / alias_mappings.md § Spelling Variants). Direction follows the doc and
    # the Aluminum precedent: the non-US spelling is canonical, so only "Phosphorous"
    # enters dim_material and "Phosphorus" resolves to the same material_key.
    ("Phosphorus", "Phosphorous", 0.95, "spelling_variant"),

    # Unit variations - medium confidence as we're stripping units
    ("Copper (kg)", "Copper", 0.90, "unit_removed"),
    ("Lithium (t)", "Lithium", 0.90, "unit_removed"),

    # Abbreviations - medium confidence
    ("Electronic Components", "Electronics (controllers, Sensors)", 0.85, "generalized"),
]

material_aliases_with_confidence = spark.createDataFrame(
    MATERIAL_ALIASES, ["alias", "standard_material", "confidence", "match_type"]
)

write_tbl(country_aliases_with_confidence, "mapping_country_aliases_confidence")
write_tbl(material_aliases_with_confidence, "mapping_material_aliases_confidence")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# # Dimensions
# 
# ## gold.dim_country (with alias resolution)

# CELL ********************

# Fixed Country Dimension Logic with Enhanced Data Quality Tracking

# 1. CONSISTENT KEY GENERATION STRATEGY
def generate_country_key(iso3_col, name_col):
    """Generate consistent country keys using ISO3 when available, fallback to name"""
    return F.when(F.col(iso3_col).isNotNull(), 
                  stable_key([iso3_col])
                 ).otherwise(stable_key([name_col]))

# 2. BUILD BASE DIMENSION WITH PROPER SCHEMA
epi = spark.table(f"{DB}.{EPI_SILVER_TBL}").select(
    F.col("iso").alias("iso3"),
    F.col("code").cast(IntegerType()).alias("iso_numeric"),
    F.col("country").alias("country_name_epi")
).filter(F.col("iso3").isNotNull()).dropDuplicates(["iso3"])

# NOTE: silver_WB table removed (World Bank ESG data not available)
# Build primary dimension from EPI data only
dim_country_base = (
    epi
    .select(
        F.col("country_name_epi").alias("country_name_std"),
        F.col("iso3"),
        F.col("iso_numeric"),
        F.col("iso3").alias("wb_code")  # Use iso3 as wb_code fallback
    )
    .dropDuplicates(["iso3"])
)

# 3. ADD CURATED COUNTRIES with canonical standard names.
# These rows carry the country_name_std spelling that the alias table
# (country_aliases_with_confidence) resolves to. NOTE: contrary to a prior
# comment ("not in EPI/WB"), some of these DO appear in EPI — e.g. EPI 2024
# names TUR "Türkiye", which the aliases at lines 175-180 map back to "Turkey".
# Because country_key = f(iso3), a curated row and an EPI row for the same iso3
# collide on country_key; the precedence-ranked dedupe below makes the curated
# (canonical) name win so those aliases never get orphaned. Entries with no EPI
# match (e.g. Kosovo) are simply the only row for their iso3.
missing_countries = spark.createDataFrame([
    ("North Korea", "PRK", 408, "PRK"),
    ("Yemen", "YEM", 887, "YEM"), 
    ("Syria", "SYR", 760, "SYR"),
    ("Libya", "LBY", 434, "LBY"),
    ("Turkey", "TUR", 792, "TUR"),
    ("Kosovo", "XKX", None, None),
    ("San Marino", "SMR", 674, "SMR"),
    ("Nauru", "NRU", 520, "NRU"),
], ["country_name_std", "iso3", "iso_numeric", "wb_code"])

# NEW: Add UNKNOWN placeholder countries for unmapped records
# This ensures we don't lose data in aggregations
# NOTE: Must provide explicit schema because all iso_numeric/wb_code values are None
unknown_countries_schema = StructType([
    StructField("country_name_std", StringType(), True),
    StructField("iso3", StringType(), True),
    StructField("iso_numeric", IntegerType(), True),
    StructField("wb_code", StringType(), True),
    StructField("region", StringType(), True)
])
unknown_countries = spark.createDataFrame([
    ("Unknown - Africa", "UNK_AFR", None, None, "Africa"),
    ("Unknown - Asia", "UNK_ASIA", None, None, "Asia"),
    ("Unknown - Europe", "UNK_EUR", None, None, "Europe"),
    ("Unknown - Americas", "UNK_AMER", None, None, "Americas"),
    ("Unknown - Oceania", "UNK_OCE", None, None, "Oceania"),
    ("Unknown - Global", "UNK_GLOB", None, None, None),
], unknown_countries_schema)

# 4. REGION MAPPING FOR RLS (Row-Level Security)
# Maps ISO3 codes to geographic regions for regional manager filtering
region_mapping = F.create_map(
    # Americas
    F.lit("USA"), F.lit("Americas"),
    F.lit("CAN"), F.lit("Americas"),
    F.lit("MEX"), F.lit("Americas"),
    F.lit("BRA"), F.lit("Americas"),
    F.lit("ARG"), F.lit("Americas"),
    F.lit("CHL"), F.lit("Americas"),
    F.lit("COL"), F.lit("Americas"),
    F.lit("PER"), F.lit("Americas"),
    F.lit("VEN"), F.lit("Americas"),
    F.lit("ECU"), F.lit("Americas"),
    F.lit("BOL"), F.lit("Americas"),
    F.lit("URY"), F.lit("Americas"),
    F.lit("PRY"), F.lit("Americas"),
    F.lit("GUY"), F.lit("Americas"),
    F.lit("SUR"), F.lit("Americas"),
    F.lit("PAN"), F.lit("Americas"),
    F.lit("CRI"), F.lit("Americas"),
    F.lit("GTM"), F.lit("Americas"),
    F.lit("HND"), F.lit("Americas"),
    F.lit("NIC"), F.lit("Americas"),
    F.lit("SLV"), F.lit("Americas"),
    F.lit("CUB"), F.lit("Americas"),
    F.lit("DOM"), F.lit("Americas"),
    F.lit("HTI"), F.lit("Americas"),
    F.lit("JAM"), F.lit("Americas"),
    F.lit("TTO"), F.lit("Americas"),
    # Europe
    F.lit("DEU"), F.lit("Europe"),
    F.lit("FRA"), F.lit("Europe"),
    F.lit("GBR"), F.lit("Europe"),
    F.lit("ITA"), F.lit("Europe"),
    F.lit("ESP"), F.lit("Europe"),
    F.lit("NLD"), F.lit("Europe"),
    F.lit("BEL"), F.lit("Europe"),
    F.lit("CHE"), F.lit("Europe"),
    F.lit("AUT"), F.lit("Europe"),
    F.lit("POL"), F.lit("Europe"),
    F.lit("SWE"), F.lit("Europe"),
    F.lit("NOR"), F.lit("Europe"),
    F.lit("FIN"), F.lit("Europe"),
    F.lit("DNK"), F.lit("Europe"),
    F.lit("IRL"), F.lit("Europe"),
    F.lit("PRT"), F.lit("Europe"),
    F.lit("GRC"), F.lit("Europe"),
    F.lit("CZE"), F.lit("Europe"),
    F.lit("ROU"), F.lit("Europe"),
    F.lit("HUN"), F.lit("Europe"),
    F.lit("UKR"), F.lit("Europe"),
    F.lit("SVK"), F.lit("Europe"),
    F.lit("BGR"), F.lit("Europe"),
    F.lit("HRV"), F.lit("Europe"),
    F.lit("SVN"), F.lit("Europe"),
    F.lit("LTU"), F.lit("Europe"),
    F.lit("LVA"), F.lit("Europe"),
    F.lit("EST"), F.lit("Europe"),
    F.lit("LUX"), F.lit("Europe"),
    F.lit("SRB"), F.lit("Europe"),
    F.lit("BIH"), F.lit("Europe"),
    F.lit("ALB"), F.lit("Europe"),
    F.lit("MKD"), F.lit("Europe"),
    F.lit("MNE"), F.lit("Europe"),
    F.lit("ISL"), F.lit("Europe"),
    F.lit("MLT"), F.lit("Europe"),
    F.lit("CYP"), F.lit("Europe"),
    F.lit("RUS"), F.lit("Europe"),
    F.lit("BLR"), F.lit("Europe"),
    F.lit("MDA"), F.lit("Europe"),
    # Asia-Pacific
    F.lit("CHN"), F.lit("Asia-Pacific"),
    F.lit("JPN"), F.lit("Asia-Pacific"),
    F.lit("KOR"), F.lit("Asia-Pacific"),
    F.lit("AUS"), F.lit("Asia-Pacific"),
    F.lit("IND"), F.lit("Asia-Pacific"),
    F.lit("IDN"), F.lit("Asia-Pacific"),
    F.lit("THA"), F.lit("Asia-Pacific"),
    F.lit("VNM"), F.lit("Asia-Pacific"),
    F.lit("MYS"), F.lit("Asia-Pacific"),
    F.lit("SGP"), F.lit("Asia-Pacific"),
    F.lit("PHL"), F.lit("Asia-Pacific"),
    F.lit("NZL"), F.lit("Asia-Pacific"),
    F.lit("PAK"), F.lit("Asia-Pacific"),
    F.lit("BGD"), F.lit("Asia-Pacific"),
    F.lit("MMR"), F.lit("Asia-Pacific"),
    F.lit("KHM"), F.lit("Asia-Pacific"),
    F.lit("LAO"), F.lit("Asia-Pacific"),
    F.lit("LKA"), F.lit("Asia-Pacific"),
    F.lit("NPL"), F.lit("Asia-Pacific"),
    F.lit("MNG"), F.lit("Asia-Pacific"),
    F.lit("PRK"), F.lit("Asia-Pacific"),
    F.lit("TWN"), F.lit("Asia-Pacific"),
    F.lit("HKG"), F.lit("Asia-Pacific"),
    F.lit("MAC"), F.lit("Asia-Pacific"),
    F.lit("BRN"), F.lit("Asia-Pacific"),
    F.lit("TLS"), F.lit("Asia-Pacific"),
    F.lit("PNG"), F.lit("Asia-Pacific"),
    F.lit("FJI"), F.lit("Asia-Pacific"),
    # Africa
    F.lit("ZAF"), F.lit("Africa"),
    F.lit("EGY"), F.lit("Africa"),
    F.lit("NGA"), F.lit("Africa"),
    F.lit("MAR"), F.lit("Africa"),
    F.lit("KEN"), F.lit("Africa"),
    F.lit("GHA"), F.lit("Africa"),
    F.lit("COD"), F.lit("Africa"),
    F.lit("ZMB"), F.lit("Africa"),
    F.lit("TZA"), F.lit("Africa"),
    F.lit("ETH"), F.lit("Africa"),
    F.lit("UGA"), F.lit("Africa"),
    F.lit("DZA"), F.lit("Africa"),
    F.lit("TUN"), F.lit("Africa"),
    F.lit("LBY"), F.lit("Africa"),
    F.lit("SDN"), F.lit("Africa"),
    F.lit("AGO"), F.lit("Africa"),
    F.lit("MOZ"), F.lit("Africa"),
    F.lit("ZWE"), F.lit("Africa"),
    F.lit("BWA"), F.lit("Africa"),
    F.lit("NAM"), F.lit("Africa"),
    F.lit("SEN"), F.lit("Africa"),
    F.lit("CIV"), F.lit("Africa"),
    F.lit("CMR"), F.lit("Africa"),
    F.lit("MLI"), F.lit("Africa"),
    F.lit("BFA"), F.lit("Africa"),
    F.lit("NER"), F.lit("Africa"),
    F.lit("TCD"), F.lit("Africa"),
    F.lit("COG"), F.lit("Africa"),
    F.lit("GAB"), F.lit("Africa"),
    F.lit("GNQ"), F.lit("Africa"),
    F.lit("RWA"), F.lit("Africa"),
    F.lit("BDI"), F.lit("Africa"),
    F.lit("MWI"), F.lit("Africa"),
    F.lit("MDG"), F.lit("Africa"),
    F.lit("MUS"), F.lit("Africa"),
    # Middle East
    F.lit("SAU"), F.lit("Middle East"),
    F.lit("ARE"), F.lit("Middle East"),
    F.lit("ISR"), F.lit("Middle East"),
    F.lit("TUR"), F.lit("Middle East"),
    F.lit("IRN"), F.lit("Middle East"),
    F.lit("QAT"), F.lit("Middle East"),
    F.lit("KWT"), F.lit("Middle East"),
    F.lit("BHR"), F.lit("Middle East"),
    F.lit("OMN"), F.lit("Middle East"),
    F.lit("JOR"), F.lit("Middle East"),
    F.lit("LBN"), F.lit("Middle East"),
    F.lit("SYR"), F.lit("Middle East"),
    F.lit("IRQ"), F.lit("Middle East"),
    F.lit("YEM"), F.lit("Middle East"),
    F.lit("AFG"), F.lit("Middle East"),
    F.lit("KAZ"), F.lit("Middle East"),
    F.lit("UZB"), F.lit("Middle East"),
    F.lit("TKM"), F.lit("Middle East"),
    F.lit("AZE"), F.lit("Middle East"),
    F.lit("GEO"), F.lit("Middle East"),
    F.lit("ARM"), F.lit("Middle East"),
)

# 5. UNION ALL COUNTRIES WITH CONSISTENT KEY GENERATION AND REGION ASSIGNMENT
# source_precedence drives the deterministic duplicate-iso3 resolution below:
#   1 = curated missing_countries (canonical names the alias table targets) — WINS
#   2 = EPI-sourced rows (source spelling, e.g. 'Türkiye' for TUR)
#   3 = Unknown placeholders (distinct UNK_* iso3, never collide)
all_countries = (
    dim_country_base
    .withColumn("region", F.coalesce(region_mapping[F.col("iso3")], F.lit("Other")))
    .withColumn("source_precedence", F.lit(2))
    .unionByName(
        missing_countries
        .withColumn("region", F.coalesce(region_mapping[F.col("iso3")], F.lit("Other")))
        .withColumn("source_precedence", F.lit(1)),
        allowMissingColumns=True)
    .unionByName(
        unknown_countries.withColumn("source_precedence", F.lit(3)),
        allowMissingColumns=True)
)

# Generate consistent keys for all records
# DETERMINISTIC DUPLICATE-ISO3 RESOLUTION (task-025):
# country_key = f(iso3) only, so a curated row and an EPI row for the same iso3
# (e.g. Turkey: curated 'Turkey' vs EPI 'Türkiye') hash to the SAME country_key.
# The old dropDuplicates(['country_key']) kept an ARBITRARY row per key —
# nondeterministic country naming that could silently orphan every alias whose
# standard_name is the curated spelling (the alias table targets 'Turkey', not
# 'Türkiye'), sending procurement 'Turkey' rows to Unknown - Global on some runs
# but not others. DECISION: curated missing_countries names win over EPI source
# names (source_precedence 1 < 2). That is the naming the alias table resolves to,
# so it maximises alias closure; the country_name_std tie-break makes the ordering
# total and reproducible run-to-run. Note country_key is identical across the
# colliding rows, so fact_epi_score (joined on iso3) is unaffected — only the
# display name / iso_numeric / wb_code change.
_dedupe_win = W.partitionBy("country_key").orderBy(
    F.col("source_precedence").asc(), F.col("country_name_std").asc()
)
dim_country = (
    all_countries
    .withColumn("country_key", generate_country_key("iso3", "country_name_std"))
    .withColumn("is_placeholder",
        # Flag placeholder/unknown countries for transparency
        F.when(F.col("iso3").startswith("UNK_"), True).otherwise(False))
    .withColumn("_dedupe_rn", F.row_number().over(_dedupe_win))
    .filter(F.col("_dedupe_rn") == 1)
    .select("country_key", "iso3", "iso_numeric", "wb_code", "country_name_std", "region", "is_placeholder")
).cache()  # task-012_3: reused across lookup build, coverage matrix, WGI weight mapping

# 5. BUILD COMPREHENSIVE LOOKUP TABLE WITH CONFIDENCE SCORES
_country_lookup_raw = (
    # First, add all standard country names as self-lookups with 100% confidence
    dim_country
    .select(
        F.col("country_name_std").alias("lookup_name"),
        "country_key", "iso3", "iso_numeric", "wb_code", "country_name_std",
        F.lit(1.0).alias("match_confidence"),
        F.lit("exact").alias("match_type")
    )
    # Then add aliases with their confidence scores
    .unionByName(
        country_aliases_with_confidence.alias("ca")
        .join(F.broadcast(dim_country.alias("dc")),  # task-012_3: small dim, broadcast
              F.col("ca.standard_name") == F.col("dc.country_name_std"), "inner")
        .select(
            F.col("ca.alias").alias("lookup_name"),
            "dc.country_key", "dc.iso3", "dc.iso_numeric", "dc.wb_code", "dc.country_name_std",
            F.col("ca.confidence").alias("match_confidence"),
            F.col("ca.match_type")
        )
    )
)

# DEDUPE ON lookup_name (task-023): a country whose standard name also appears
# verbatim in the alias seed (Tier-1 rows 'United States of America' and
# 'United Kingdom' at ~L144-145) yields TWO rows sharing one lookup_name — the
# self-lookup plus the redundant Tier-1 alias. fact_procurement / fact_supply_share
# join on lookup_name, so each collision doubles the joined fact row and inflates
# SUM(fact_procurement[spend_eur]). Keep exactly one row per lookup_name, chosen
# deterministically (NOT an arbitrary dropDuplicates):
#   1) highest match_confidence   (self-lookups are always 1.0 = the maximum)
#   2) prefer the exact self-lookup over an equal-confidence alias (match_type=='exact')
#   3) country_key as a final, run-to-run-stable total-order tiebreak
_country_lu_win = W.partitionBy("lookup_name").orderBy(
    F.col("match_confidence").desc(),
    F.when(F.col("match_type") == "exact", 0).otherwise(1).asc(),
    F.col("country_key").asc()
)
country_lookup = (
    _country_lookup_raw
    .withColumn("_lu_rn", F.row_number().over(_country_lu_win))
    .filter(F.col("_lu_rn") == 1)
    .drop("_lu_rn")
).cache()  # task-012_3: reused in uniqueness guard + write_tbl

write_tbl(dim_country, "gold_dim_country")
write_tbl(country_lookup, "gold_dim_country_lookup")

# GUARD (task-023): lookup_name MUST be unique — a duplicate fans out every fact
# row that joins on it. Fail the notebook loudly rather than silently doubling spend.
_dup_country = country_lookup.groupBy("lookup_name").count().filter(F.col("count") > 1)
_dup_country_n = _dup_country.count()
assert _dup_country_n == 0, (
    f"gold_dim_country_lookup has {_dup_country_n} duplicate lookup_name value(s): "
    f"{[r['lookup_name'] for r in _dup_country.limit(10).collect()]}"
)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# NEW: Create country coverage matrix for transparency
# This shows which countries appear in which source systems
def create_country_coverage_matrix():
    """
    Which countries exist in which source datasets — one row per real (non-placeholder)
    dim_country row, one has_* flag per source, and a coverage score over ALL sources.

    Rewritten by task-028. The previous version shipped a coverage_category derived from
    EPI alone (its own comment said "Simplified for brevity"), and the EPI probe was
    broken besides: it left-joined on country_key and then tested `country_key IS NOT
    NULL`, but country_key comes from the LEFT side of that join, so it is never null —
    has_epi was hardcoded 1, coverage_score 1.0 and every country landed in
    "High Coverage". The presence flag now comes from the joined-in side, so a miss
    really reads 0.

    Sources are matched through country_lookup (alias-aware), so a source spelling like
    "Türkiye" or "USA" counts as presence for the country it resolves to.

    NOTE: the retired World Bank ESG source (silver_WB) is deliberately absent rather
    than joined as an always-empty frame — including it would drag every country's score
    down by a fixed 1/N for a source that no longer exists.
    """
    # (flag column, distinct country values from that source)
    sources = [
        ("has_epi", spark.table(f"{DB}.{EPI_SILVER_TBL}")
            .select(F.col("country").alias("src_country"))),
        # task-038_2 decided to leave this GLOBAL-ONLY. has_supply is a flag on a different
        # gold table (gold_country_coverage_matrix) whose published meaning is "this country
        # appears as a worldwide producer". Adding silver_eusupplyshares would flip existing
        # countries from 0 to 1 and raise their coverage_score with no acceptance criterion
        # covering the change. Broadening it is a deliberate follow-up, not a side effect.
        ("has_supply", spark.table(f"{DB}.silver_globalsupplyshares")
            .select(F.col("country").alias("src_country"))),
        ("has_proc_hq", spark.table(f"{DB}.silver_procurement")
            .select(F.col("headquarterscountry").alias("src_country"))),
        ("has_proc_prod", spark.table(f"{DB}.silver_procurement")
            .select(F.col("productioncountry").alias("src_country"))),
    ]

    coverage = (
        dim_country
        .filter(~F.col("is_placeholder"))  # Exclude unknown placeholders
        .select("country_key", "country_name_std", "iso3")
    )

    for flag, src in sources:
        present = (
            country_lookup.select("lookup_name", "country_key")
            .join(src.dropna().distinct(),
                  F.col("lookup_name") == F.col("src_country"), "inner")
            .select("country_key").distinct()
            .withColumn(flag, F.lit(1))
        )
        coverage = (
            coverage
            .join(present, "country_key", "left")
            .withColumn(flag, F.coalesce(F.col(flag), F.lit(0)))
        )

    flags = [f for f, _ in sources]
    n_sources = len(flags)

    coverage = (
        coverage
        .withColumn("sources_present", sum([F.col(f) for f in flags[1:]], F.col(flags[0])))
        .withColumn("total_sources", F.lit(n_sources))
        .withColumn("coverage_score", F.col("sources_present") / F.lit(float(n_sources)))
        .withColumn("coverage_category",
            # With 4 sources: 4/4 High, 2-3/4 Medium, 0-1/4 Low.
            F.when(F.col("coverage_score") >= 0.8, "High Coverage")
             .when(F.col("coverage_score") >= 0.5, "Medium Coverage")
             .otherwise("Low Coverage")
        )
    )

    write_tbl(coverage, "gold_country_coverage_matrix")
    return coverage

coverage_matrix = create_country_coverage_matrix()

# Validation report
print(f"\n{'='*60}")
print("COUNTRY DIMENSION VALIDATION REPORT")
print(f"{'='*60}")

total_countries = dim_country.filter(~F.col("is_placeholder")).count()
placeholder_countries = dim_country.filter(F.col("is_placeholder")).count()
lookup_entries = country_lookup.count()

print(f"\nDimension Statistics:")
print(f"  Real countries: {total_countries}")
print(f"  Placeholder countries: {placeholder_countries}")
print(f"  Total lookup entries: {lookup_entries}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## gold.dim_material (with alias resolution and commodity groups)

# CELL ********************

# Gather all unique materials from sources
proc = spark.table(f"{DB}.silver_procurement").select(
    F.initcap(F.trim("materialname")).alias("material")
)
sup = spark.table(f"{DB}.silver_globalsupplyshares").select(
    F.initcap(F.trim("material")).alias("material")
)
# task-038_2: silver_eusupplyshares now also feeds fact_supply_share, so its materials MUST
# be gathered here too. Without this, any material that appears only in the EU sourcing
# table would find no dim row, land on the 'Unknown Material' placeholder, and be reported
# as an unmapped-material quality failure — a false signal manufactured by the union rather
# than a real gap in the data. Additive to gold_dim_material: it can only add material rows,
# never change an existing one (the dim is keyed on the standardised name).
sup_eu = spark.table(f"{DB}.silver_eusupplyshares").select(
    F.initcap(F.trim("material")).alias("material")
)

materials_raw = (
    proc.union(sup).union(sup_eu)
    .dropna()
    .dropDuplicates()
)

# Apply alias resolution with confidence tracking
materials = (
    materials_raw
    .join(material_aliases_with_confidence, 
          materials_raw.material == material_aliases_with_confidence["alias"], "left")
    .withColumn("material_name_std", 
                F.coalesce(F.col("standard_material"), F.col("material")))
    .withColumn("match_confidence",
                F.coalesce(F.col("confidence"), F.lit(1.0)))  # Original names get 100% confidence
    .withColumn("match_type",
                F.coalesce(F.col("match_type"), F.lit("original")))
    .select("material_name_std", "match_confidence", "match_type")
    .dropDuplicates(["material_name_std"])  # Dedupe by material name only to avoid duplicate keys
)

# NEW: Add UNKNOWN placeholder materials for unmapped records
unknown_materials = spark.createDataFrame([
    ("Unknown Material", "Other/Unknown", "kg"),
], ["material_name_std", "commodity_group", "unit_base"])

# Commodity group mapping.
#
# REACHABILITY CONTRACT (task-028): this map is probed with material_name_std, which is
# initcap'd upstream, so every key must satisfy initcap(key) == key. A key that is not
# its own initcap can never match and silently falls through to "Other/Unknown" — the
# defect that hid "Steel (High-Tensile)", "Plastic (ABS)" and "Rare Earths (NdPr)"
# behind Other/Unknown until 2026-07-22. Kept honest by the assertion below (fails the
# run) and by tests/test_material_mapping.py (fails CI). Held as a plain dict rather
# than inline F.lit() pairs precisely so both guards can enumerate the keys.
COMMODITY_GROUPS = {
    "Lithium": "Battery metals",
    "Graphite": "Battery metals",
    "Copper": "Base metals",
    "Nickel": "Battery metals",
    "Cobalt": "Battery metals",
    "Lead": "Base metals",
    "Aluminum": "Base metals",
    "Aluminium": "Base metals",
    "Zinc": "Base metals",
    "Tin": "Base metals",
    "Iron Ore": "Base metals",
    "Magnesium": "Base metals",
    "Gold": "Precious metals",
    "Silver": "Precious metals",
    "Platinum": "Precious metals",
    "Palladium": "Precious metals",
    "Rhodium": "Precious metals",
    "Iridium": "Precious metals",
    "Ruthenium": "Precious metals",
    "Neodymium": "Rare earth elements",
    "Praseodymium": "Rare earth elements",
    "Cerium": "Rare earth elements",
    "Lanthanum": "Rare earth elements",
    "Yttrium": "Rare earth elements",
    # Written in initcap form ("(ndpr)", not "(NdPr)") — see the contract above.
    "Rare Earths (ndpr)": "Rare earth elements",
    "Tungsten": "Specialty metals",
    "Molybdenum": "Specialty metals",
    "Titanium": "Specialty metals",
    "Titanium Metal": "Specialty metals",
    "Tantalum": "Specialty metals",
    "Vanadium": "Specialty metals",
    "Silicon Metal": "Specialty metals",
    "Niobium": "Specialty metals",
    "Limestone": "Industrial minerals",
    "Silica Sand": "Industrial minerals",
    "Kaolin": "Industrial minerals",
    # Both spellings stay mapped even though the "Phosphorus" -> "Phosphorous" alias
    # means only the latter reaches dim_material — they agree on the group, so the
    # retained key is harmless insurance if that alias is ever removed.
    "Phosphorus": "Chemicals",
    "Phosphorous": "Chemicals",
    "Phosphate Rock": "Chemicals",
    "Potash": "Chemicals",
    "Sulphur": "Chemicals",
    "Coking Coal": "Energy materials",
    "Natural Rubber": "Organic materials",
    "Electronics (controllers, Sensors)": "Manufactured products",
    "Plastic (abs)": "Manufactured products",
    "Tires (rubber Compound)": "Manufactured products",
    "Steel (high-tensile)": "Manufactured products",
    "Helium": "Specialty gases",
    "Neon": "Specialty gases",
    "Natural Graphite": "Battery metals",
    "Erbium": "Rare earth elements",
    "Thulium": "Rare earth elements",
    "Holmium": "Rare earth elements",
    "Lutetium": "Rare earth elements",
    "Samarium": "Rare earth elements",
    "Arsenic": "Specialty metals",
    "Selenium": "Specialty metals",
    "Germanium": "Specialty metals",
    "Hafnium": "Specialty metals",
    "Rhenium": "Specialty metals",
    "Zirconium": "Specialty metals",
    "Bismuth": "Specialty metals",
    "Strontium": "Industrial minerals",
    "Feldspar": "Industrial minerals",
    "Gypsum": "Industrial minerals",
    "Natural Teak Wood": "Organic materials",
}

grp_map = F.create_map([F.lit(x) for kv in COMMODITY_GROUPS.items() for x in kv])

# GUARD (task-028): fail the run — loudly, at build time — if any commodity-group key or
# material-alias LHS is unreachable from initcap-normalized input. Both tables are matched
# against values that have already been through F.initcap(F.trim(...)), so a key that is
# not its own initcap is dead: materials fall through to "Other/Unknown" and aliases never
# fire, both silently. One Spark round-trip over ~70 short strings; the mirror of this
# assertion lives in tests/test_material_mapping.py so the contract is also enforced
# outside Fabric.
_reach_probe = sorted(set(COMMODITY_GROUPS) | {a[0] for a in MATERIAL_ALIASES})
_unreachable = [
    r["v"] for r in (
        spark.createDataFrame([(v,) for v in _reach_probe], ["v"])
        .filter(F.initcap(F.col("v")) != F.col("v"))
        .collect()
    )
]
assert not _unreachable, (
    f"{len(_unreachable)} commodity-group key(s)/material alias(es) are unreachable — "
    f"initcap() rewrites them, so nothing can ever match: {_unreachable}. "
    f"Rewrite each in its own initcap form (e.g. 'Plastic (ABS)' -> 'Plastic (abs)')."
)
print(f"✓ Material mapping reachability: {len(_reach_probe)} keys/aliases, 0 unreachable")

dim_material = (
    materials
    .withColumn("commodity_group",
                F.coalesce(grp_map[F.col("material_name_std")], F.lit("Other/Unknown")))
    .withColumn("unit_base", F.lit("kg"))
    .withColumn("material_key", stable_key(["material_name_std"]))
    .withColumn("is_placeholder", F.lit(False))
    .select("material_key","material_name_std","commodity_group","unit_base","is_placeholder")
    # Add unknown placeholder
    .unionByName(
        unknown_materials
        .withColumn("material_key", stable_key(["material_name_std"]))
        .withColumn("is_placeholder", F.lit(True))
    )
    .dropDuplicates(["material_key"])  # CRITICAL: Ensure unique keys for dimension table
).cache()  # task-012_3: reused across lookup build, quality_by_material join

# Enhanced lookup with confidence scores
_material_lookup_raw = (
    dim_material
    .select(
        F.col("material_name_std").alias("lookup_name"),
        "material_key",
        "material_name_std",
        "commodity_group",
        F.lit(1.0).alias("match_confidence"),
        F.lit("exact").alias("match_type")
    )
    .unionByName(
        material_aliases_with_confidence.alias("ma")
        .join(F.broadcast(dim_material.alias("dm")),  # task-012_3: small dim, broadcast
              F.col("ma.standard_material") == F.col("dm.material_name_std"), "inner")
        .select(
            F.col("ma.alias").alias("lookup_name"),
            "dm.material_key",
            "dm.material_name_std",
            "dm.commodity_group",
            F.col("ma.confidence").alias("match_confidence"),
            F.col("ma.match_type")
        )
    )
)

# DEDUPE ON lookup_name (task-023): structurally identical self-mapping hazard as
# the country lookup. No current material alias equals a standard material name, so
# this is future-proofing — a later alias whose text matches a standard name would
# otherwise reintroduce the fan-out. Same deterministic rule: exact / highest-
# confidence row wins (see the country-lookup dedupe above for the ordering rationale).
_material_lu_win = W.partitionBy("lookup_name").orderBy(
    F.col("match_confidence").desc(),
    F.when(F.col("match_type") == "exact", 0).otherwise(1).asc(),
    F.col("material_key").asc()
)
material_lookup = (
    _material_lookup_raw
    .withColumn("_lu_rn", F.row_number().over(_material_lu_win))
    .filter(F.col("_lu_rn") == 1)
    .drop("_lu_rn")
).cache()  # task-012_3: reused in uniqueness guard + write_tbl

write_tbl(dim_material, "gold_dim_material")
write_tbl(material_lookup, "gold_dim_material_lookup")

# GUARD (task-023): lookup_name MUST be unique — see the country-lookup guard above.
_dup_material = material_lookup.groupBy("lookup_name").count().filter(F.col("count") > 1)
_dup_material_n = _dup_material.count()
assert _dup_material_n == 0, (
    f"gold_dim_material_lookup has {_dup_material_n} duplicate lookup_name value(s): "
    f"{[r['lookup_name'] for r in _dup_material.limit(10).collect()]}"
)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## silver.epi{EPI_YEAR}variables (built from bronze weights)
# # task-056: the primary `gold_dim_indicator` path selects from
# `silver_epi{EPI_YEAR}variables`, but that table was never built — `bronze_ingest_epi`
# previously downloaded only the results CSV, so `silver-to-gold2` fell back to a
# NULL-weight fallback that hardcoded `weight=F.lit(None)` and flattened `type` to
# 'indicator' for all rows. This cell builds the silver variables table from the
# ingested `bronze_epi{EPI_YEAR}weights` table (AC1) so the primary path runs against
# real data.
# # Load-bearing mapping: `weight` ← `EPI Percent` (the ABSOLUTE contribution to the EPI
# composite), NOT the relative `Weight` column. The source CSV stores `EPI Percent` as
# a STRING like "3.00%" / "25.00%" (pd.read_csv keeps it StringType at bronze), so the
# silver build must (a) strip the "%" suffix before casting to float and (b) NULL the
# weight for non-leaf rows explicitly via F.when(Type=='Indicator', ...).otherwise(NULL).
# The real Yale CSV has NON-NULL `EPI Percent` on all 11 IssueCategory rows (BDH=25.00%,
# ECS=5.00%, ...) — aggregates are NOT excluded by NULL source data. They are excluded
# from `Weighted EPI Score` by (i) the explicit `.otherwise(NULL)` weight mapping here
# AND (ii) the measure's `type='Indicator'` filter (fact_epi_score.tmdl, task-056 AC3
# harden). Belt-and-suspenders: the NULL weight drops aggregates from SUMX numerator and
# SUM(weight) denominator; the type filter drops them from the filter context entirely.
# The relative `Weight` column is preserved as `weight_relative` for traceability but is
# NOT consumed downstream.

# CELL ********************

_bronze_weights_tbl = f"bronze_epi{EPI_YEAR}weights"

_epi_weights_src = (
    spark.table(f"{DB}.{_bronze_weights_tbl}")
    .select(
        F.col("Type").alias("type"),
        F.col("Abbreviation").alias("abbreviation"),
        F.col("Variable").alias("variable"),
        F.col("PolicyObjective").alias("policyobjective"),
        F.col("IssueCategory").alias("issuecategory"),
        F.col("NextLevel").alias("nextlevel"),
        F.col("Weight").cast(FloatType()).alias("weight_relative"),
        # `epi_percent` (renamed from Yale's "EPI Percent" at bronze write for Delta
        # column-name safety — Delta rejects spaces) is the absolute leaf-indicator
        # contribution to the EPI composite. Source stores it as a STRING ("3.00%");
        # strip the "%" suffix then cast to float. Only leaf indicators (Type=Indicator)
        # carry a weight; EPI composite, PolicyObjective, and IssueCategory rows get
        # NULL explicitly — the real CSV has non-null epi_percent on IC rows
        # (BDH=25.00%, etc.), so the NULL must be imposed by this mapping, not assumed
        # from the source. The measure's `type='Indicator'` filter (fact_epi_score.tmdl)
        # is the belt; this NULL-IC-weight is the suspenders.
        F.when(
            F.col("Type") == "Indicator",
            F.regexp_replace(F.col("epi_percent"), "%", "").cast(FloatType())
        ).otherwise(F.lit(None).cast(FloatType())).alias("weight"),
        # Use the human-readable `Variable` name as description (the results-derived
        # fallback previously used abbreviation as name; Variable carries full labels).
        F.col("Variable").alias("description"),
    )
)

# Persist as the silver variables table the primary path selects from.
write_tbl(_epi_weights_src, f"silver_epi{EPI_YEAR}variables")
print(f"✓ Built silver_epi{EPI_YEAR}variables from {_bronze_weights_tbl}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## gold.dim_indicator

# CELL ********************

# EPI indicators
# task-056: the primary path now runs against the silver variables table built above from
# the ingested bronze weights. `nextlevel` is carried through so `parent_indicator` can be
# resolved via a self-join (NextLevel is the parent's abbreviation). The old NULL-
# hardcoding fallback is retired — if the silver table is genuinely absent we now warn
# loudly and produce an EMPTY EPI df (visible breakage: zero EPI indicators) rather than
# 73 rows with NULL weight (silent breakage: Weighted EPI Score renders BLANK).
try:
    epi_vars = spark.table(f"{DB}.silver_epi{EPI_YEAR}variables").select(
        F.lit("EPI").alias("source_system"),
        "type",
        F.col("abbreviation").alias("abbrev"),
        F.col("variable").alias("variable_name"),
        "policyobjective","issuecategory","weight","description",
        "nextlevel",
        F.lit(None).cast(StringType()).alias("indicator_code")
    ).withColumn("indicator_key", stable_key(["source_system","abbrev","variable_name"]))
    print(f"✓ Loaded EPI variables from silver_epi{EPI_YEAR}variables table")
except Exception as e:
    # Loud fallback: the silver build cell above should always produce this table in a
    # normal pipeline run. If we land here, the bronze weights table was missing or the
    # silver build failed — do NOT paper over with fake NULL weights (the pre-task-056
    # behaviour); emit an empty EPI df so the gap is visible in gold_dim_indicator.
    print(
        f"⚠️  silver_epi{EPI_YEAR}variables not found — NOT falling back to NULL weights. "
        f"EPI indicators will be EMPTY. Root cause: {e}"
    )
    epi_vars = spark.createDataFrame(
        [],
        StructType([
            StructField("source_system", StringType(), True),
            StructField("type", StringType(), True),
            StructField("abbrev", StringType(), True),
            StructField("variable_name", StringType(), True),
            StructField("policyobjective", StringType(), True),
            StructField("issuecategory", StringType(), True),
            StructField("weight", FloatType(), True),
            StructField("description", StringType(), True),
            StructField("nextlevel", StringType(), True),
            StructField("indicator_code", StringType(), True),
            StructField("indicator_key", LongType(), True),
        ])
    )

# WB indicators - NOTE: silver_WB table removed (World Bank ESG data not available)
# Create empty WB indicators DataFrame with same schema for compatibility
wb_vars = spark.createDataFrame(
    [],
    StructType([
        StructField("source_system", StringType(), True),
        StructField("type", StringType(), True),
        StructField("abbrev", StringType(), True),
        StructField("variable_name", StringType(), True),
        StructField("policyobjective", StringType(), True),
        StructField("issuecategory", StringType(), True),
        StructField("weight", FloatType(), True),
        StructField("description", StringType(), True),
        StructField("indicator_code", StringType(), True),
        StructField("parent_label", StringType(), True),
        StructField("indicator_key", LongType(), True)
    ])
)

# Union all indicators. `nextlevel` (EPI only) and `parent_label` (WB only) are carried
# through via allowMissingColumns; both are dropped after the parent_indicator self-join.
all_indicators = epi_vars.unionByName(wb_vars, allowMissingColumns=True)

# task-056: resolve parent_indicator from NextLevel via self-join.
# NextLevel is the parent's abbreviation (e.g., Indicator MKP → NextLevel=BDH → parent is
# the IssueCategory BDH). The EPI composite row's NextLevel is NULL/empty → parent_indicator
# stays NULL (root). WB indicators have no NextLevel → parent_indicator NULL. Only EPI
# indicators with a non-null, matching NextLevel get a parent_indicator.
_parent_lookup = all_indicators.select(
    F.col("abbrev").alias("_parent_abbrev"),
    F.col("indicator_key").alias("_parent_key")
)

dim_indicator = (
    all_indicators.alias("a")
    .join(
        _parent_lookup.alias("p"),
        (F.col("a.nextlevel").isNotNull())
        & (F.length(F.trim(F.col("a.nextlevel"))) > 0)
        & (F.col("a.nextlevel") == F.col("p._parent_abbrev")),
        "left"
    )
    .withColumn("parent_indicator", F.col("p._parent_key"))
    .select(
        F.col("a.indicator_key"),
        F.col("a.source_system"),
        F.col("a.type"),
        F.col("a.abbrev"),
        F.col("a.variable_name"),
        F.col("a.policyobjective"),
        F.col("a.issuecategory"),
        F.col("a.indicator_code"),
        F.col("a.weight"),
        F.col("a.description"),
        F.col("parent_indicator"),
    )
)

write_tbl(dim_indicator, "gold_dim_indicator")

# Stats
print(f"\nIndicator dimension stats:")
print(f"  EPI indicators: {dim_indicator.filter(F.col('source_system')=='EPI').count()}")
print(f"  WB indicators: {dim_indicator.filter(F.col('source_system')=='WB').count()}")
print(f"  EPI indicators with non-null parent_indicator: "
      f"{dim_indicator.filter((F.col('source_system')=='EPI') & (F.col('parent_indicator').isNotNull())).count()}")
print(f"  EPI leaf indicators (type=Indicator) with non-null weight: "
      f"{dim_indicator.filter((F.col('source_system')=='EPI') & (F.col('type')=='Indicator') & (F.col('weight').isNotNull())).count()}")
print(f"  Distinct EPI type values: "
      f"{[r['type'] for r in dim_indicator.filter(F.col('source_system')=='EPI').select('type').distinct().collect()]}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## gold.dim_stage

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

# ## gold.dim_date

# CELL ********************

from pyspark.sql import functions as F
from pyspark.sql.types import IntegerType, DateType

# Get min/max date from procurement (with better null handling)
try:
    src_dates = (
        spark.table(f"{DB}.silver_procurement")
        .select(F.col("date").cast(DateType()).alias("d"))
        .filter(F.col("d").isNotNull())
    )
    
    if src_dates.count() > 0:
        mm = src_dates.agg(F.min("d").alias("min_d"), F.max("d").alias("max_d")).first()
        start = F.lit(mm.min_d)
        end = F.lit(mm.max_d)
        print(f"Date range from procurement: {mm.min_d} to {mm.max_d}")
    else:
        raise Exception("No valid dates in procurement")
        
except Exception as e:
    print(f"Using default date range due to: {e}")
    end = F.current_date()
    start = F.date_add(end, -365)

# Generate date sequence
date_seq_df = spark.range(1).select(F.sequence(start, end).alias("dseq"))
df = date_seq_df.select(F.explode(F.col("dseq")).alias("date"))


def date_attributes(date_df):
    """Derive every dim_date attribute from a single `date` column.

    Factored out (task-030) so the real calendar sequence and the UNKNOWN-DATE
    member below are built by the SAME expressions — the sentinel row can never
    drift out of schema or attribute agreement with the rest of the dimension.
    """
    return (
        date_df
        .withColumn("date_key", F.date_format("date","yyyyMMdd").cast(IntegerType()))
        .withColumn("year", F.year("date"))
        .withColumn("month", F.month("date"))
        .withColumn("day", F.dayofmonth("date"))
        .withColumn("month_name", F.date_format("date","MMM"))
        .withColumn("quarter", F.quarter("date"))  # Added quarter
        .withColumn("day_of_week", F.dayofweek("date"))  # Added day of week
        .withColumn("week_of_year", F.weekofyear("date"))  # Added week of year
        .select("date_key","date","year","month","day","month_name","quarter","day_of_week","week_of_year")
    )


# -----------------------------------------------------------------------------
# task-030 (AC1) — EXPLICIT UNKNOWN-DATE MEMBER, not a NULL date_key
# -----------------------------------------------------------------------------
# DECISION: transactions whose source date is NULL or fails the date cast are kept
# in fact_procurement and pointed at a sentinel dim_date member (19000101 /
# 1900-01-01) instead of carrying a NULL date_key. The alternative considered was
# quarantining them out of the fact into the unmapped audit.
#
# Why the unknown member wins here:
#   1. It is the SAME philosophy this notebook already applies to the other two
#      dimensions — an unmapped material becomes 'Unknown Material' and an unmapped
#      country becomes 'Unknown - Global' (see the fact_procurement cell). One
#      mental model for every dimension miss beats a per-dimension special case.
#   2. No data loss: the transaction's spend stays in the fact, so the unfiltered
#      grand total is the true total. Quarantining would make gold spend silently
#      UNDERSTATE actual spend — the same class of invisible divergence this task
#      exists to remove, just pointed the other way.
#   3. A NULL date_key matches no dim_date row, so in DirectLake the row vanishes
#      from every date-related visual while still counting in unfiltered cards.
#      A real member is selectable in a slicer: the undated spend is visible and
#      explainable instead of missing.
#   4. The BLOCKING referential-integrity check owned by task-026
#      (fact_procurement.date_key -> gold_dim_date, 0% tolerance) uses a LEFT ANTI
#      join, which counts a NULL key as an orphan. Any NULL date_key would halt the
#      pipeline. Routing to a member that genuinely exists in the dimension keeps
#      that gate green for a reason, rather than by luck.
#
# 19000101 (not -1) because every other date_key in this model is yyyyMMdd, and
# downstream SQL/DAX may parse it back to a date. The sentinel keeps that invariant.
#
# NOTE for whoever marks gold_dim_date as a Power BI date table: this member breaks
# date contiguity (1900 then a jump to the real range). gold_dim_date is not marked
# as a date table today (no dataCategory: Time in the TMDL). If it ever is, exclude
# the sentinel from the marked table rather than deleting it from the dimension.
UNKNOWN_DATE_KEY = 19000101
UNKNOWN_DATE = "1900-01-01"

dim_date_calendar = date_attributes(df).filter(F.col("date_key") != F.lit(UNKNOWN_DATE_KEY))
dim_date_unknown = date_attributes(
    spark.range(1).select(F.lit(UNKNOWN_DATE).cast(DateType()).alias("date"))
)

# Build dimension with additional useful attributes
dim_date = dim_date_calendar.unionByName(dim_date_unknown)

write_tbl(dim_date, "gold_dim_date")
print(f"  ↳ includes the UNKNOWN-DATE member date_key={UNKNOWN_DATE_KEY} "
      f"({UNKNOWN_DATE}) — fact rows with no usable transaction date point here")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# # Facts
# 
# ## Load lookup tables with enhanced mappings

# CELL ********************

# Use extended lookup tables for better matching
dim_country_lu = spark.table(f"{DB}.gold_dim_country_lookup").select(
    "lookup_name", "country_key", "iso3", "country_name_std", "match_confidence", "match_type"
)
# fact_epi_score joins on iso3 (EPI has one score per country), so it needs a
# ONE-row-per-iso3 map — NOT dim_country_lu, which holds one row PER ALIAS per iso3
# and would fan out each EPI score 2-7x for alias-rich countries (US/UK/Turkey/
# Congo/Koreas), breaking the 'one row per country x indicator x year' grain. task-023.
dim_country_iso3_map = spark.table(f"{DB}.gold_dim_country").select(
    "iso3", "country_key"
).dropDuplicates(["iso3"])
dim_material_lu = spark.table(f"{DB}.gold_dim_material_lookup").select(
    "lookup_name", "material_key", "material_name_std", "commodity_group", "match_confidence", "match_type"
)
dim_stage_lu = spark.table(f"{DB}.gold_dim_stage").select("stage_key","stage_code")
dim_ind_lu = spark.table(f"{DB}.gold_dim_indicator").select(
    "indicator_key","source_system","abbrev","indicator_code","variable_name"
)
dim_date_lu = spark.table(f"{DB}.gold_dim_date").select("date_key","date")

print("Lookup tables loaded successfully")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## gold.fact_epi_score

# CELL ********************

epi_res = spark.table(f"{DB}.{EPI_SILVER_TBL}")

# Identify metric columns
id_cols = {"code","iso","country"}
metric_cols = [c for c in epi_res.columns if c not in id_cols]
if not metric_cols:
    raise ValueError(f"No metric columns found in {EPI_SILVER_TBL}.")

print(f"Processing {len(metric_cols)} EPI indicators")

# task-054 (FB-001): bronze-to-silver now preserves all 30+ EPI sub-indicator columns
# into silver_epi{year}results (previously it dropped everything except the overall
# EPI composite, so this unpivot had only one column to work with and fact_epi_score
# landed 180 rows of overall-EPI-only against a spec / gold_tables.md / DAX library /
# TMDL that all specify grain = country × indicator × year). With the 30+ columns
# now reaching silver, this unpivot produces ~180 countries × ~30+ indicators.
#
# Overall EPI composite handling (AC2): the `EPI` column — the overall composite
# score — is INCLUDED as one indicator row (abbrev="EPI") alongside the 30+
# sub-indicators. It is NOT excluded. This preserves the pre-task-054 per-country
# overall-EPI row that the live report visuals consume (Avg EPI Score / Countries
# with EPI Data, both filtered to abbrev="EPI" in the TMDL so the sub-indicator
# rows do not pollute the per-country average), AND makes the sub-indicators
# available to the Weighted EPI Score measure. The composite is its own row, not
# a derived aggregate over the sub-indicators — consistent with how the EPI
# source ships it (one column among many) and with gold_dim_indicator, which
# carries the EPI composite as one indicator with its own weight.
#
# Pivot to long format
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

# Join with dimensions
fact_epi_score = (
    epi_long
    # task-023: join the deduped iso3 -> country_key map (one row per iso3), NOT the
    # per-alias dim_country_lu, so EPI scores are not duplicated once per country alias.
    # task-012_3: broadcast the dim lookups (dim_country, dim_indicator) — both are
    # small (one row per iso3 / per EPI indicator) and the fact side is the large frame.
    .join(F.broadcast(dim_country_iso3_map),
          on=epi_long.iso == dim_country_iso3_map.iso3, how="left")
    .join(F.broadcast(dim_ind_lu.filter(F.col("source_system")=="EPI")
                          .select("indicator_key","abbrev")),
          on="abbrev", how="left")
    # task-028: stamped from EPI_YEAR, the same constant that picks EPI_SILVER_TBL above,
    # so the vintage label can never drift from the vintage actually read. The old
    # hardcoded F.lit(2024) would have labelled a 2025 pull as 2024.
    .withColumn("year", F.lit(EPI_YEAR).cast(IntegerType()))
    .select(F.col("country_key"), F.col("indicator_key"), "year", F.col("score"))
)

# Data quality check
unmapped_countries = fact_epi_score.filter(F.col("country_key").isNull()).count()
unmapped_indicators = fact_epi_score.filter(F.col("indicator_key").isNull()).count()

if unmapped_countries > 0:
    print(f"⚠️  WARNING: {unmapped_countries} records with unmapped countries")
if unmapped_indicators > 0:
    print(f"⚠️  WARNING: {unmapped_indicators} records with unmapped indicators")

# Filter out records with NULL keys
fact_epi_score_clean = fact_epi_score.filter(
    (F.col("country_key").isNotNull()) & 
    (F.col("indicator_key").isNotNull())
)

write_tbl(fact_epi_score_clean, "fact_epi_score")
print(f"  Dropped {fact_epi_score.count() - fact_epi_score_clean.count()} records with NULL keys")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## gold.fact_supply_share — now built once, further down (see the fact_procurement cell)
# REMOVED by task-028: this cell used to build a first, simpler `fact_supply_share` and
# write it to the same table the enhanced build (in the fact_procurement cell below,
# `## gold.fact_supply_share (with enhanced quality tracking and unknown handling)`)
# overwrites minutes later. Every row it produced was discarded, and the two builds
# disagreed on '<1%' (this one parsed it to 1.0 via regexp_replace; the survivor uses the
# 0.5 midpoint), so the dead write also made the notebook look like it had two answers to
# the same question. Its only surviving side effects were console prints — the three
# check_unmapped() calls (fail=False, so print-only) are superseded by the richer
# "SUPPLY SHARE DATA QUALITY ANALYSIS" block in the surviving build, which reports the
# same three dimensions with counts, percentages and top offenders. Deleting it also
# closes the DirectLake window in which readers could see the intermediate table.


# MARKDOWN ********************

# ## gold.fact_procurement (with extensive data quality checks)

# CELL ********************

# Read silver for the fact. In incremental mode, mirror bronze-to-silver's 7-day look-back
# window (see bronze-to-silver notebook-content.py ~L179-186) so we only rebuild the changed
# window; in full-load mode (or first load) read the whole silver table.
# task-029: the window now keys off `effective_from_date` (auto-retrieved from
# bronze_load_metadata, excluding the current run's execution_id so gold uses the
# SAME effective watermark silver used). Both layers consume ONE mechanism — no
# second watermark source.
_is_full_load = p_full_load.strip().lower() == "true"
_fact_exists = spark.catalog.tableExists(f"{DB}.fact_procurement")

if _is_full_load or not _fact_exists:
    proc = spark.table(f"{DB}.silver_procurement")
else:
    from datetime import timedelta
    _watermark_date = datetime.strptime(effective_from_date, "%Y-%m-%d")
    _lookback_str = (_watermark_date - timedelta(days=7)).strftime("%Y-%m-%d")
    proc = (spark.table(f"{DB}.silver_procurement")
            .filter(F.col("date").cast("date") >= F.lit(_lookback_str)))
    print(f"fact_procurement: INCREMENTAL — silver window from {_lookback_str} "
          f"(7-day look-back from effective_from_date={effective_from_date})")

# -----------------------------------------------------------------------------
# Unit normalization (task-030 AC2)
# -----------------------------------------------------------------------------
# ONE python dict is the source of truth: it builds the Spark map used by the fact
# AND drives the unit-domain report printed below, so the two can never disagree.
# The four factors are the ones documented in calculations.md § "Quantity Base".
# (The old trailing comment "... (rest remains same)" implied a truncated map; it
# did not — these four ARE the whole map, which is exactly why the fallback below
# mattered so much.)
#
# MIRRORED CHECK: data_quality_checks.Notebook carries the advisory
# business_rule_validation rule "Unit In Conversion Domain" on silver_procurement
# with this same domain. Fabric notebooks cannot import from each other, so the
# list is duplicated by necessity — change both together.
UNIT_CONVERSION_FACTORS = {
    "kg": 1.0,
    "g": 0.001,
    "mg": 0.000001,
    "t": 1000.0,
}
unit_norm = F.create_map(*[
    lit for unit, factor in UNIT_CONVERSION_FACTORS.items()
    for lit in (F.lit(unit), F.lit(factor))
])

# Lookup key for the map. TRIM matters: without it a source value of " kg" misses
# the map and a miss yields a NULL quantity_base — so whitespace alone would silently
# strip the kg mass off a perfectly good mass row (spend survives under per_row_unit,
# but the row would wrongly land in the no-mass audit).
unit_key = F.lower(F.trim(F.col("p.unit")))

# -----------------------------------------------------------------------------
# task-030 (AC3) — unitprice_eur basis. CONFIRMED per_row_unit (2026-07-23).
# -----------------------------------------------------------------------------
# CONFIRMED against the live source (oem_lh.bronze_procurement_transactional): the
# unit domain is {kg (108 rows), pcs (24 rows)} — no mass units other than kg. `pcs`
# (electronic control units, tyres) can only be priced PER PIECE, so unitprice_eur is
# per the row's own Unit, not per kilogram. The kg rows are consistent with this (for
# a kg row per-kg == per-row-unit).
#
# WHY THIS MATTERED: under the old "per_kg" formula spend = quantity_base * price, and
# quantity_base is NULL for any non-mass unit (task-030 AC2), so EVERY pcs row's spend
# collapsed to NULL — €1.74M of real procurement (the largest category) silently gone.
# per_row_unit computes spend = quantity_original * price for every row, which is the
# honest line total: correct for kg (EUR/kg × kg) AND for pcs (EUR/pc × pcs), and it
# leaves the kg rows' spend unchanged. quantity_base stays NULL for pcs — correct, a
# piece has no kg mass — but that no longer poisons spend.
#
# This also reconciles populate_low_confidence_audit, which already computes
# spend_impact as raw quantity * unitpriceeur (i.e. per_row_unit).
UNITPRICE_BASIS = "per_row_unit"

if UNITPRICE_BASIS == "per_row_unit":
    # Price is EUR per the row's own Unit: multiply the ORIGINAL quantity. No conversion
    # on the price side (converting both sides would double-count), and — crucially —
    # spend does NOT depend on quantity_base, so a non-mass unit (pcs) still gets a real
    # spend even though its quantity_base is NULL.
    spend_eur_expr = F.col("p.quantity") * F.col("p.unitpriceeur")
elif UNITPRICE_BASIS == "per_kg":
    # Retained for completeness. Price is EUR per kilogram: multiply the kg-normalized
    # quantity. DO NOT use with the current data — it NULLs out every pcs row's spend,
    # because quantity_base is NULL for units outside {kg,g,mg,t}.
    spend_eur_expr = F.col("quantity_base") * F.col("p.unitpriceeur")
else:
    raise ValueError(
        f"UNITPRICE_BASIS must be 'per_kg' or 'per_row_unit', got {UNITPRICE_BASIS!r}"
    )

# Prepare procurement data
p = (
    proc
    .withColumn("txn_date", F.col("date").cast("date"))
    .withColumn("material_name", F.initcap(F.trim("materialname")))
    .withColumn("hq_country", F.trim("headquarterscountry"))
    .withColumn("prod_country", F.trim("productioncountry"))
    .withColumn("row_id", F.monotonically_increasing_id())  # Add row ID for tracking
).alias("p")

# -----------------------------------------------------------------------------
# task-030 (AC2) — OBSERVED UNIT DOMAIN + no-mass-conversion audit
# -----------------------------------------------------------------------------
# Printed every run so the actual unit vocabulary of the source is visible instead
# of assumed. Computed off `p` (the rows actually being loaded) BEFORE the dimension
# joins, so the counts are per source transaction and cannot be skewed by a join.
#
# NOTE (task-030 AC3, per_row_unit): a unit outside {kg,g,mg,t} means "no kg mass
# equivalent", so quantity_base is NULL — but under per_row_unit spend_eur is STILL
# computed (quantity × unitprice). So an unrecognized unit withholds MASS, not SPEND.
# The live source's non-mass unit is `pcs` (electronic control units, tyres): those
# rows have a real spend and a NULL quantity_base, which is exactly right.
p_units = (
    p
    .select(unit_key.alias("unit_key"))
    .groupBy("unit_key")
    # NOT aliased `count`: pyspark Row subclasses tuple, so row.count would return
    # the bound tuple method and float(row.count) raises TypeError.
    .agg(F.count(F.lit(1)).alias("row_count"))
    .orderBy(F.desc("row_count"))
    .collect()
)
print("\n--- Unit domain observed in silver_procurement (this load window) ---")
for u in p_units:
    known = u.unit_key in UNIT_CONVERSION_FACTORS
    label = "mass unit — quantity_base in kg" if known \
        else "non-mass unit — quantity_base NULL (spend still computed)"
    print(f"  {str(u.unit_key):>12} : {u.row_count:>8,} rows   [{label}]")

# Durable audit of every unit outside the conversion map. A console print dies with
# the notebook page; this table is queryable after the fact and is what /view-unmapped
# style investigation needs. Deliberately its OWN table rather than a row in
# gold_unmapped_procurement_audit: that table is consumed wholesale by
# populate_gap_registry, which would turn a unit into a gap_type='unit' registry
# entry and inflate the "unmapped records" dashboard metric. A missing mass factor is
# a conversion-map gap, not a dimension-alias gap.
unit_audit = (
    p
    .withColumn("unit_key", unit_key)
    .withColumn("unit_factor", unit_norm[F.col("unit_key")])
    .filter(F.col("unit_factor").isNull())
    .groupBy(F.col("unit_key").alias("unmapped_unit"))
    .agg(
        F.count(F.lit(1)).alias("row_count"),
        F.sum(F.col("quantity").cast("double")).alias("quantity_original_sum"),
    )
    .withColumn("detected_timestamp", F.current_timestamp())
)
write_tbl(unit_audit, "gold_unmapped_unit_audit")

no_mass_rows = sum(u.row_count for u in p_units
                   if u.unit_key not in UNIT_CONVERSION_FACTORS)
if no_mass_rows > 0:
    print(f"ℹ️  NOTE: {no_mass_rows:,} rows carry a non-mass unit outside "
          f"{sorted(UNIT_CONVERSION_FACTORS)} (e.g. pcs). Their quantity_base is NULL "
          f"(no kg equivalent) but spend_eur IS computed as quantity × unitprice "
          f"under per_row_unit (see {DB}.gold_unmapped_unit_audit). Only add a unit to "
          f"UNIT_CONVERSION_FACTORS if it is a MASS unit with a real kg factor — do NOT "
          f"map pcs to a mass, that would fabricate a weight.")

# Build fact with comprehensive joins and quality tracking
fact_procurement_raw = (
    p
    # Date join — dim_date_lu is NOT broadcast: it carries years of daily rows and may
    # exceed the broadcast threshold; the dimension joins below are the small ones.
    .join(dim_date_lu.alias("d"), F.col("p.txn_date") == F.col("d.date"), "left")

    # task-012_3: broadcast the small dimension lookups (dim_material, dim_country).
    # Material join with confidence tracking
    .join(F.broadcast(dim_material_lu.alias("m")), F.col("p.material_name") == F.col("m.lookup_name"), "left")

    # Country joins with confidence tracking
    .join(F.broadcast(dim_country_lu.alias("c_hq")), F.col("p.hq_country") == F.col("c_hq.lookup_name"), "left")
    .join(F.broadcast(dim_country_lu.alias("c_prod")), F.col("p.prod_country") == F.col("c_prod.lookup_name"), "left")
    
    # Calculate derived fields
    .withColumn("unit_factor", unit_norm[unit_key])
    # task-030 (AC2): the fallback used to be .otherwise(F.col("p.quantity")) — a row
    # denominated in 'lb' or 'tonne' kept its RAW magnitude while being labelled kg,
    # so quantity_base and spend_eur were quietly wrong by whatever the real factor
    # was (x1000 for a tonne). NULL is the honest answer: we do not know the kg
    # equivalent. It is a known-unknown that SUM() skips and the audit table above
    # names, instead of an unknown-unknown baked into the number.
    .withColumn("quantity_base",
                F.when(F.col("unit_factor").isNotNull(),
                       (F.col("p.quantity") * F.col("unit_factor")).cast("double"))
                .otherwise(F.lit(None).cast("double")))
    # Basis chosen at the top of this cell (task-030 AC3, pending source confirmation).
    .withColumn("spend_eur", spend_eur_expr)
    
    # NEW: Add data quality indicators
    .withColumn("data_quality_score",
        # Calculate overall quality score (0-1) based on match confidences
        (F.coalesce(F.col("m.match_confidence"), F.lit(0)) +
         F.coalesce(F.col("c_hq.match_confidence"), F.lit(0)) +
         F.coalesce(F.col("c_prod.match_confidence"), F.lit(0))) / 3.0
    )
    .withColumn("quality_category",
        F.when(F.col("data_quality_score") >= 0.9, "High")
         .when(F.col("data_quality_score") >= 0.7, "Medium")
         .when(F.col("data_quality_score") >= 0.5, "Low")
         .otherwise("Unmapped")
    )
)

# NEW: For unmapped records, assign to UNKNOWN dimensions
# This ensures no data loss while maintaining transparency
fact_procurement_complete = (
    fact_procurement_raw
    .withColumn("material_key_final",
        F.when(F.col("m.material_key").isNull(), 
               spark.sql("SELECT material_key FROM gold_dim_material WHERE material_name_std = 'Unknown Material'").first()[0])
         .otherwise(F.col("m.material_key"))
    )
    .withColumn("supplier_hq_country_key_final",
        F.when(F.col("c_hq.country_key").isNull(),
               spark.sql("SELECT country_key FROM gold_dim_country WHERE country_name_std = 'Unknown - Global'").first()[0])
         .otherwise(F.col("c_hq.country_key"))
    )
    .withColumn("production_country_key_final",
        F.when(F.col("c_prod.country_key").isNull(),
               spark.sql("SELECT country_key FROM gold_dim_country WHERE country_name_std = 'Unknown - Global'").first()[0])
         .otherwise(F.col("c_prod.country_key"))
    )
    
    # task-030 (AC1): route a failed date join to the explicit UNKNOWN-DATE member
    # instead of leaving date_key NULL — same placeholder philosophy as the three
    # dimension keys above. See the dim_date cell for the full rationale.
    .withColumn("date_key_final",
        F.coalesce(F.col("d.date_key"), F.lit(UNKNOWN_DATE_KEY).cast(IntegerType()))
    )

    .select(
        F.col("date_key_final").alias("date_key"),
        F.col("material_key_final").alias("material_key"),
        F.col("supplier_hq_country_key_final").alias("supplier_hq_country_key"),
        F.col("production_country_key_final").alias("production_country_key"),
        F.col("quantity_base"),
        F.col("p.unitpriceeur").alias("unitprice_eur"),
        F.col("spend_eur"),
        F.col("data_quality_score"),
        F.col("quality_category"),
        # Keep original values for audit
        F.col("p.row_id").alias("source_row_id")
    )
).cache()  # task-012_3: reused in write/delete-insert, window_min_date, count

# task-030 (AC1): how many transactions had no usable date this run. Printed rather
# than silently absorbed — the whole point of the unknown member is that undated
# spend stays countable.
undated_rows = fact_procurement_raw.filter(F.col("d.date_key").isNull()).count()
if undated_rows > 0:
    print(f"⚠️  WARNING: {undated_rows:,} transactions have no usable date "
          f"(NULL or uncastable) — routed to dim_date member {UNKNOWN_DATE_KEY}. "
          f"They are included in unfiltered totals and selectable in a date slicer, "
          f"but cannot be attributed to a real period.")
else:
    print(f"✓ fact_procurement: every transaction resolved to a real date "
          f"(0 rows on the {UNKNOWN_DATE_KEY} unknown-date member)")

# Write fact_procurement — full overwrite (full load / first load) or transaction-grain
# delete-insert over the incremental window.
# task-024 decision (2026-07-14): keep one-row-per-transaction grain and ABANDON the natural-key
# MERGE. The old merge key (date_key, material_key, supplier_hq_country_key, production_country_key)
# is coarser than the transaction grain, so legitimate same-day transactions collapsed onto one key:
# same-batch dups threw Delta's "multiple source rows matched" (crash) and cross-run dups were
# silently overwritten by whenMatchedUpdateAll (data loss). Delete-insert is lossless (NO dedupe —
# every transaction is preserved) and idempotent: re-running deletes the same date_key window and
# re-inserts the same rows. gold_tables.md grain "one row per transaction" is UNCHANGED.
if _is_full_load or not _fact_exists:
    write_tbl(fact_procurement_complete, "fact_procurement")
else:
    from delta.tables import DeltaTable
    # Delete-insert boundary = the minimum date_key actually present in the windowed fact. Because
    # the window read pulled every silver row with date >= look-back, every silver row with
    # date_key >= this minimum is in the window; deleting target rows with date_key >= min and
    # re-inserting the window is therefore lossless AND idempotent. (Rows with a NULL date are
    # excluded by the incremental window filter above, so they never accumulate here.)
    #
    # task-030: the UNKNOWN-DATE member is EXCLUDED from the boundary computation. Undated rows
    # now carry date_key=19000101, which is below every real date_key — if one ever reached this
    # frame the boundary would collapse to 19000101 and the delete would wipe the ENTIRE fact
    # table before re-inserting only the window. Today the incremental filter (date >= look-back)
    # already drops undated rows before the join, so this is belt-and-braces; it stays correct if
    # that filter is ever changed. Undated rows written by a full load sit below the boundary and
    # are therefore preserved, not deleted, by subsequent incremental runs.
    window_min_date_key = (
        fact_procurement_complete
        .filter(F.col("date_key") != F.lit(UNKNOWN_DATE_KEY))
        .agg(F.min("date_key")).first()[0]
    )
    if window_min_date_key is None:
        print("fact_procurement: incremental window is empty — nothing to delete-insert")
    else:
        target = DeltaTable.forName(spark, f"{DB}.fact_procurement")
        target.delete(F.col("date_key") >= F.lit(window_min_date_key))
        (fact_procurement_complete.write
            .format("delta")
            .mode("append")
            .saveAsTable(f"{DB}.fact_procurement"))
        spark.sql(f"OPTIMIZE {DB}.fact_procurement")
        print(f"✓ fact_procurement: delete-insert complete for date_key >= {window_min_date_key} "
              f"({fact_procurement_complete.count():,} rows re-inserted)")

# Audit trail for unmapped records — ONE ROW PER (source row x failed dimension).
#
# task-027: this table used to be one row per unmapped source row carrying
# original_material + original_hq_country + original_prod_country regardless of which
# join failed, plus an unmapped_type that was only ever 'Material' or NULL. That shape
# made "which dimension is the gap?" unanswerable, and every downstream consumer that
# tried to answer it (gap registry, DQ dashboard, quality views) got it wrong.
#
# New shape:
#   row_id | unmapped_type | gap_dimension | unmapped_value | spend_eur | detected_timestamp
# A row whose material AND production country both failed now produces two rows, each
# naming exactly one failing value. A fully-mapped source row produces none, so the old
# outer .filter() is no longer needed — the explode below drops non-failing dimensions.
#
# spend_eur carries the transaction's spend onto each gap row so a gap can be ranked by
# money at risk: SUM(spend_eur) per unmapped_value is the "spend_impact" that
# data_quality_architecture.md § [2] already claims this table has, and the shape
# /view-unmapped queries. "frequency" stays an aggregate (COUNT(*)) rather than a stored
# column — this table is per-occurrence, not pre-aggregated.
#
# unmapped_value is left NULL when the SOURCE value itself is NULL (a genuinely empty
# country on the transaction). Those rows stay in the audit as evidence, but the gap
# registry skips them: a NULL has no natural key to alias.
unmapped_audit = (
    fact_procurement_raw
    .select(
        F.col("p.row_id").alias("row_id"),
        F.col("spend_eur"),
        F.array(
            unmapped_gap(F.col("m.material_key").isNull(),
                         "material", "material", F.col("p.material_name")),
            unmapped_gap(F.col("c_hq.country_key").isNull(),
                         "hq_country", "country", F.col("p.hq_country")),
            unmapped_gap(F.col("c_prod.country_key").isNull(),
                         "prod_country", "country", F.col("p.prod_country")),
        ).alias("gap_candidates"),
    )
    .select("row_id", "spend_eur", F.explode("gap_candidates").alias("gap"))
    .filter(F.col("gap").isNotNull())
    .select(
        "row_id",
        F.col("gap.unmapped_type").alias("unmapped_type"),
        F.col("gap.gap_dimension").alias("gap_dimension"),
        F.col("gap.unmapped_value").alias("unmapped_value"),
        "spend_eur",
        F.current_timestamp().alias("detected_timestamp"),
    )
)

write_tbl(unmapped_audit, "gold_unmapped_procurement_audit")

## gold.fact_supply_share (with enhanced quality tracking and unknown handling)

# task-038_2 / DEC-001 Option B: the fact is the UNION of the two complementary EU CRM
# supply tables, discriminated by `supply_mix`:
#   'global'      — silver_globalsupplyshares: where a material is produced worldwide
#   'eu_sourcing' — silver_eusupplyshares:     where the EU actually sources it from
# They are NOT partitions of one population. spec_v1 § Data Architecture -> Gold Layer
# item 2: "The two supply_mix values are never summed together" — every consumer either
# filters to one mix or pivots on it. The grain therefore gains supply_mix:
# material x stage x country x year x supply_mix.
#
# The union happens HERE, at read time, before any cleaning. That way the '<1%' -> 0.5
# convention, the dimension joins, the quality scoring and the territory rollup below are
# each expressed exactly once and apply identically to both mixes — no per-source special
# casing, and task-028's single-source-of-truth rule for censored shares survives intact.
#
# unionByName is deliberately STRICT (no allowMissingColumns): bronze-to-silver already
# asserts the two silver tables share a column contract, so a divergence here is a real
# upstream defect and should fail loudly rather than be papered over with NULLs.
SUPPLY_SOURCES = [
    ("global", "silver_globalsupplyshares"),
    ("eu_sourcing", "silver_eusupplyshares"),
]

sup = None
for _mix_name, _mix_tbl in SUPPLY_SOURCES:
    _mix_df = (
        spark.table(f"{DB}.{_mix_tbl}")
        .withColumn("supply_mix", F.lit(_mix_name))
        .withColumn("source_file", F.lit(_mix_tbl))
    )
    sup = _mix_df if sup is None else sup.unionByName(_mix_df)

# `t` arrives from silver as a STRING on BOTH tables (verified against the live lakehouse
# and documented in schemas/bronze_tables.md); spec_v1 item 2 calls it DOUBLE, which is the
# target shape of the gold column, not the shape silver delivers. It is cast explicitly
# below. Fabric runs with spark.sql.ansi.enabled=false, so a non-numeric value casts to
# NULL instead of raising — this counter is what stops that from passing silently. It is
# observability, not suppression: a non-zero count is a real upstream data defect.
_t_cast_lost = sup.filter(F.col("t").isNotNull() & F.col("t").cast("double").isNull()).count()
if _t_cast_lost > 0:
    print(f"\n⚠️  WARNING: {_t_cast_lost} supply-share row(s) carry a non-numeric `t` that "
          f"cast to NULL. Their trade weighting is undefined and DEC-001's HHI_WGI,t will "
          f"skip them — investigate the source before trusting the supply-risk output.")

# Prepare supply share data with row tracking for audit
supply_prep = (
    sup
    .select(
        F.initcap(F.trim("material")).alias("material"),
        F.col("stage"),
        F.trim("country").alias("country"),
        # Clean percentage values - handle various formats.
        # '<1%' -> 0.5, the midpoint of the (0, 1) interval the source is asserting.
        # SINGLE SOURCE OF TRUTH for censored shares (task-028): the earlier duplicate
        # fact_supply_share build parsed '<1%' to 1.0 by stripping the '<' and was
        # deleted, so this is now the only place the convention is expressed. It matches
        # spec_v1 § Data Sources / Supply Shares ("'<1%' converted to 0.5%"). Any change
        # here changes every downstream supply-share measure — do not fork it.
        # task-038_2: this now runs over the unioned rows, so both mixes are cleaned by
        # this one expression.
        F.when(F.col("share").contains("<"), F.lit(0.5))
         .otherwise(
               F.regexp_replace("share", "[<%]", "").cast("double")
         ).alias("share_pct"),
        F.col("t").cast("double").alias("t"),
        F.col("supply_mix"),
        # Source metadata for audit purposes, stamped per-source at read time above
        F.col("source_file"),
        F.monotonically_increasing_id().alias("row_id")  # Add for tracking
    )
    .withColumn("processing_timestamp", F.current_timestamp())
)

# Join with enhanced lookups including confidence scores
fact_supply_share_raw = (
    supply_prep.alias("s")

    # task-012_3: broadcast the small dimension lookups (dim_material, dim_country,
    # dim_stage — 2 rows). The fact side is the unioned supply-share frame.
    # Material join with confidence tracking
    .join(F.broadcast(dim_material_lu.alias("m")),
          F.col("s.material") == F.col("m.lookup_name"), "left")

    # Country join with confidence tracking
    .join(F.broadcast(dim_country_lu.alias("c")),
          F.col("s.country") == F.col("c.lookup_name"), "left")

    # Stage join (no confidence needed as it's a simple code match)
    .join(F.broadcast(dim_stage_lu.alias("st")),
          F.col("s.stage") == F.col("st.stage_code"), "left")
    
    # Add year (assuming 2023 for supply share data)
    .withColumn("year", F.lit(2023).cast(IntegerType()))
    
    # NEW: Calculate data quality score based on match confidences
    .withColumn("data_quality_score",
        # Average confidence of material and country matches
        # Stage is binary (matched or not) so we add 1 or 0
        (F.coalesce(F.col("m.match_confidence"), F.lit(0)) +
         F.coalesce(F.col("c.match_confidence"), F.lit(0)) +
         F.when(F.col("st.stage_key").isNotNull(), 1.0).otherwise(0.0)) / 3.0
    )
    
    # NEW: Categorize quality for easy filtering in visualizations
    .withColumn("quality_category",
        F.when(F.col("data_quality_score") >= 0.9, "High")
         .when(F.col("data_quality_score") >= 0.7, "Medium")
         .when(F.col("data_quality_score") >= 0.5, "Low")
         .otherwise("Unmapped")
    )
    
    # NEW: Add match type details for transparency
    .withColumn("material_match_type", F.col("m.match_type"))
    .withColumn("country_match_type", F.col("c.match_type"))
)

# Comprehensive data quality analysis before handling unmapped
print("\n" + "="*60)
print("SUPPLY SHARE DATA QUALITY ANALYSIS")
print("="*60)

total_supply_records = fact_supply_share_raw.count()
print(f"\nTotal supply share records: {total_supply_records:,}")

# Analyze unmapped records by dimension
unmapped_materials = fact_supply_share_raw.filter(F.col("m.material_key").isNull())
unmapped_countries = fact_supply_share_raw.filter(F.col("c.country_key").isNull())
unmapped_stages = fact_supply_share_raw.filter(F.col("st.stage_key").isNull())

print(f"\nUnmapped records by dimension:")
print(f"  Materials: {unmapped_materials.count():,} ({100*unmapped_materials.count()/total_supply_records:.1f}%)")
print(f"  Countries: {unmapped_countries.count():,} ({100*unmapped_countries.count()/total_supply_records:.1f}%)")
print(f"  Stages: {unmapped_stages.count():,} ({100*unmapped_stages.count()/total_supply_records:.1f}%)")

# Show top unmapped values for investigation
if unmapped_materials.count() > 0:
    print("\nTop unmapped materials:")
    (unmapped_materials
     .groupBy("s.material")
     .agg(F.count("*").alias("count"), 
          F.sum("s.share_pct").alias("total_share_pct"))
     .orderBy(F.desc("count"))
     .show(10, truncate=False))

if unmapped_countries.count() > 0:
    print("\nTop unmapped countries (critical for geographic analysis):")
    (unmapped_countries
     .groupBy("s.country", "s.stage")
     .agg(F.count("*").alias("count"),
          F.sum("s.share_pct").alias("total_share_pct"),
          F.collect_set("s.material").alias("materials_affected"))
     .orderBy(F.desc("total_share_pct"))
     .show(20, truncate=False))

# NEW: Get placeholder keys for unmapped records
# Cache these lookups for efficiency
unknown_material_key = spark.sql("""
    SELECT material_key FROM gold_dim_material 
    WHERE material_name_std = 'Unknown Material'
""").first()[0]

unknown_country_key = spark.sql("""
    SELECT country_key FROM gold_dim_country 
    WHERE country_name_std = 'Unknown - Global'
""").first()[0]

# Handle unmapped records by assigning to UNKNOWN dimensions
# CRITICAL: This preserves all supply share data for accurate totals
fact_supply_share_complete = (
    fact_supply_share_raw
    
    # Replace NULL keys with UNKNOWN placeholders
    .withColumn("material_key_final",
        F.when(F.col("m.material_key").isNull(), unknown_material_key)
         .otherwise(F.col("m.material_key"))
    )
    .withColumn("country_key_final",
        F.when(F.col("c.country_key").isNull(), unknown_country_key)
         .otherwise(F.col("c.country_key"))
    )
    
    # For stages, we can't have unknowns as there are only E and P
    # Records with unmapped stages should be investigated
    .withColumn("stage_key_final", F.col("st.stage_key"))
    
    # Track whether this record used placeholders
    .withColumn("has_unmapped_material", 
        F.when(F.col("m.material_key").isNull(), True).otherwise(False))
    .withColumn("has_unmapped_country",
        F.when(F.col("c.country_key").isNull(), True).otherwise(False))
    
    # Calculate impact of unmapped records
    .withColumn("unmapped_impact_score",
        # Higher shares that are unmapped are more problematic
        F.when((F.col("has_unmapped_material") | F.col("has_unmapped_country")), 
               F.col("s.share_pct")).otherwise(0)
    )
    
    .select(
        F.col("material_key_final").alias("material_key"),
        F.col("stage_key_final").alias("stage_key"),
        F.col("country_key_final").alias("country_key"),
        "year",
        # task-038_2: supply_mix is part of the grain, t is the DEC-001 tᶜ input
        F.col("s.supply_mix").alias("supply_mix"),
        "share_pct",
        F.col("s.t").alias("t"),
        "data_quality_score",
        "quality_category",
        "has_unmapped_material",
        "has_unmapped_country",
        "unmapped_impact_score",
        F.col("s.row_id").alias("source_row_id")
    )
)

# Filter out records with NULL stage_key (these are data errors)
fact_supply_share_final = fact_supply_share_complete.filter(
    F.col("stage_key").isNotNull()
)

dropped_stage_records = fact_supply_share_complete.filter(
    F.col("stage_key").isNull()
).count()

if dropped_stage_records > 0:
    print(f"\n⚠️  WARNING: Dropped {dropped_stage_records} records with invalid stage codes")

# TERRITORY-ROLLUP AGGREGATION (task-023, decided 2026-07-22).
# A territory alias deliberately maps several source countries onto one dim country —
# ("Hong Kong","China",0.85,"territory") at ~:188 is the live case: the source lists
# Antimony/P for both China (51.8%) and Hong Kong (0.3%), so both rows land on the
# grain (Antimony, P, China, 2023). That is intended behaviour, but it is structurally
# incompatible with grain_uniqueness@fact_supply_share, which asserts one row per
# (material_key, stage_key, country_key, year) at 0% tolerance.
#
# Resolution: SUM the shares. If a territory is treated as part of its parent for this
# analysis, its supply IS the parent's supply — so China/Antimony/P becomes 52.1%.
# Without this the shares were already double-counted in any SUM; the rows were simply
# not collapsed, which fanned out every downstream join on the grain.
#
# Rows with no collision pass through a groupBy unchanged, so this is a no-op for the
# ~2560 single-row grains.
#
# Non-key column semantics, chosen deliberately:
#   data_quality_score  MIN  — a merged row is only as trustworthy as its weakest
#                              constituent; the 0.85 territory alias correctly drags it down
#   quality_category    the category belonging to that MIN score (struct-min keeps them paired)
#   has_unmapped_*      MAX  — boolean OR (True > False in Spark ordering)
#   unmapped_impact_score SUM — it is a share-scaled impact, so it adds like share_pct
#   source_row_id       MIN  — deterministic representative; the per-row audit trail is
#                              built separately from fact_supply_share_raw, so nothing is lost
#
# task-038_2 — supply_mix JOINS THE GROUPING KEY. The two mixes are complementary
# measurements, never partitions of one population, so a global row and an eu_sourcing row
# on the same (material, stage, country, year) must NOT be merged. Omitting supply_mix here
# would SUM their shares together and silently corrupt both.
#
# task-038_2 — HOW `t` COMBINES (resolved 2026-07-30; the methodology question the
# task-024/028 note below used to defer to DEC-001). DEC-001 fixes the formula
# HHI_WGI,t = Σ_c (Sᶜ)²·WGIᶜ·tᶜ but is silent on rollup aggregation.
#   RULE: SHARE-WEIGHTED MEAN — t_merged = Σ(shareᵢ·tᵢ) / Σ(shareᵢ)
#   Live case: Antimony/P China 51.8% t=1.1 + Hong Kong 0.3% t=1.0 -> China 52.1% t=1.0994.
#   WHY: t is a per-flow multiplier, so a merged flow's effective t is the share-weighted
#   average of its constituents. It is the only rule that preserves the trade-weighted
#   supply quantity Σ(S·t) exactly across the rollup (57.28 before and after), and it is an
#   exact no-op on the ~2560 non-colliding grains — matching how every other aggregation
#   here behaves on a single-row group.
#   REJECTED: MAX (overstates, 57.31); dominant-constituent (discards the minor row, and is
#   unstable at near-equal shares); MIN (understates by ~9% — MIN is right for
#   data_quality_score because that is a trust score, but t is a risk multiplier).
_pre_rollup_rows = fact_supply_share_final.count()

# CRITERION-5 BASELINE (task-038_2). The expectation MUST come from outside the frame it
# checks. An earlier version of this derived it from fact_supply_share_final itself, which
# made the assertion a tautology — both sides moved in lockstep and it was mathematically
# incapable of failing (caught in verification). The real baseline is the fact table as it
# exists in the lakehouse BEFORE this run overwrites it:
#   - table predates task-038_2 (no supply_mix column) -> its TOTAL count is the old
#     global-only row count, which is exactly what criterion 5 wants to compare against
#   - table already migrated -> compare against its 'global' slice
#   - table absent (first ever run) -> no baseline exists; report and skip
# Read before write_tbl() below, or the overwrite destroys the thing being compared.
_baseline_global_rows = None
_baseline_source = "unavailable (fact_supply_share not present — first run)"
if spark.catalog.tableExists(f"{DB}.fact_supply_share"):
    _prev_fact = spark.table(f"{DB}.fact_supply_share")
    if "supply_mix" in _prev_fact.columns:
        _baseline_global_rows = _prev_fact.filter(F.col("supply_mix") == "global").count()
        _baseline_source = "previous run's global slice"
    else:
        _baseline_global_rows = _prev_fact.count()
        _baseline_source = "pre-task global-only table (total row count)"

fact_supply_share_final = (
    fact_supply_share_final
    .groupBy("material_key", "stage_key", "country_key", "year", "supply_mix")
    .agg(
        F.sum("share_pct").alias("share_pct"),
        # Share-weighted mean of t. Rows with a NULL t are excluded from BOTH the numerator
        # and the denominator, so a missing t cannot bias the mean downward; if every
        # constituent t is NULL the result is NULL — nothing is invented.
        F.sum(F.when(F.col("t").isNotNull(), F.col("share_pct") * F.col("t"))).alias("_t_num"),
        F.sum(F.when(F.col("t").isNotNull(), F.col("share_pct"))).alias("_t_den"),
        F.avg("t").alias("_t_unweighted"),
        F.min(F.struct("data_quality_score", "quality_category")).alias("_worst"),
        F.max("has_unmapped_material").alias("has_unmapped_material"),
        F.max("has_unmapped_country").alias("has_unmapped_country"),
        F.sum("unmapped_impact_score").alias("unmapped_impact_score"),
        F.min("source_row_id").alias("source_row_id"),
    )
    .select(
        "material_key", "stage_key", "country_key", "year", "supply_mix", "share_pct",
        # Zero-denominator guard: an all-zero (or all-NULL) share group makes the weighted
        # mean undefined, so fall back to the unweighted mean — which is still an exact
        # no-op on a single-row grain, the case that actually occurs.
        F.when(F.col("_t_den") > 0, F.col("_t_num") / F.col("_t_den"))
         .otherwise(F.col("_t_unweighted")).alias("t"),
        F.col("_worst.data_quality_score").alias("data_quality_score"),
        F.col("_worst.quality_category").alias("quality_category"),
        "has_unmapped_material", "has_unmapped_country",
        "unmapped_impact_score", "source_row_id",
    )
).cache()  # task-012_3: reused 8+ times (grain guard, mix counts, WGI join, supply risk, write, quality metrics)

_post_rollup_rows = fact_supply_share_final.count()
if _pre_rollup_rows != _post_rollup_rows:
    print(f"  Territory rollup: merged {_pre_rollup_rows - _post_rollup_rows} row(s) "
          f"into their parent country ({_pre_rollup_rows} -> {_post_rollup_rows})")

# GUARD: the grain must now be unique, or grain_uniqueness will fail the pipeline
# downstream with a far less informative message than this assert. task-038_2 added
# supply_mix — it must match grain_checks@data_quality_checks, which declares the same
# five-column key list.
_dup_grain = (fact_supply_share_final
              .groupBy("material_key", "stage_key", "country_key", "year", "supply_mix")
              .count().filter(F.col("count") > 1))
_dup_grain_n = _dup_grain.count()
assert _dup_grain_n == 0, (
    f"fact_supply_share still has {_dup_grain_n} duplicate grain(s) after the territory "
    f"rollup: {[r.asDict() for r in _dup_grain.limit(5).collect()]}"
)

# ADDITIVITY CHECK (task-038_2, acceptance criterion 5). The EU rows must be ADDITIVE — a
# second, complementary population landing alongside the existing one — not a re-partition
# that moves rows out of the global mix. Two assertions:
#   1. every row carries one of the two known discriminator values (catches a NULL or a
#      stray mix introduced by a future source), and
#   2. the global-mix row count still equals what the global-only build produced.
# The count alias is deliberately `n`, not `count`: pyspark Row subclasses tuple, so a
# column named `count` shadows tuple.count and breaks attribute access.
_mix_counts = {
    r["supply_mix"]: r["n"]
    for r in fact_supply_share_final.groupBy("supply_mix")
                                    .agg(F.count(F.lit(1)).alias("n")).collect()
}
_global_rows = _mix_counts.get("global", 0)
_eu_rows = _mix_counts.get("eu_sourcing", 0)

print(f"\nfact_supply_share rows by supply_mix: global={_global_rows:,}  "
      f"eu_sourcing={_eu_rows:,}  total={_global_rows + _eu_rows:,}")

# STRUCTURAL INVARIANT — hard assert. Locally testable, and true on every future run.
assert set(_mix_counts.keys()) <= {"global", "eu_sourcing"}, (
    f"fact_supply_share carries unexpected supply_mix value(s): "
    f"{sorted(k for k in _mix_counts if k not in ('global', 'eu_sourcing'))}. "
    f"spec_v1 § Data Architecture -> Gold Layer item 2 defines exactly two."
)

# ADDITIVITY vs the EXTERNAL baseline captured above (criterion 5). Deliberately a REPORT,
# not an assert: criterion 5 is a one-time migration check ("unchanged from before this
# task"), whereas a hard assert here would fail every future legitimate source refresh —
# the annual EU CRM vintage changes the global row count on purpose. A divergence on the
# FIRST post-task run means the EU rows displaced or merged into the global population and
# the task must be reopened; a divergence later is expected whenever the source changes.
if _baseline_global_rows is None:
    print(f"  [criterion 5] no baseline — {_baseline_source}. "
          f"Compare global={_global_rows:,} against the ~2,561 lineage figure by hand.")
elif _global_rows == _baseline_global_rows:
    print(f"  [criterion 5] PASS — global mix unchanged at {_global_rows:,} rows "
          f"vs baseline from {_baseline_source}. EU rows are additive ({_eu_rows:,} added).")
else:
    print(f"  [criterion 5] ⚠️  DIVERGENCE — global mix is {_global_rows:,} rows but the "
          f"baseline ({_baseline_source}) held {_baseline_global_rows:,}. On the first run "
          f"after task-038_2 this means the EU rows displaced or merged into the global "
          f"population — reopen the task. On a later run, confirm the supply-share source "
          f"genuinely changed before accepting it.")

# =============================================================================
# GOVERNANCE WEIGHT WGIᶜ (task-038_3)
# spec_v1 § Business Logic & Calculations -> Supply Risk (DEC-001 Option B)
# =============================================================================
#   HHI_WGI,t = Σ_c (Sᶜ)² · WGIᶜ · tᶜ
#   WGIᶜ = clamp( (2.5 − mean₆(WGI estimates for c, latest year available)) / 5 , 0, 1 )
#
# This block owns WGIᶜ only — the per-country weight and its join onto the fact.
# The HHI aggregation (gold_supply_risk, contrast_ratio, is_bottleneck) is task-038_4.
#
# MIRRORED IN src/transformations/supply_risk.py (DEC-002). tests/test_supply_risk.py
# loads THESE FunctionDefs out of this file and pins them against the src/ versions —
# editing one side without the other fails CI by design.
#
# THE FIXED BOUNDS ARE THE WHOLE POINT. estimate_min/estimate_max default to the
# theoretical −2.5..+2.5 of the World Bank estimate scale and are NEVER F.min/F.max over
# the loaded set. Spec: "Rescaling uses the fixed theoretical bounds ... not the observed
# min/max of the loaded set. This is a reproducibility requirement: with observed bounds,
# adding a country or a new WGI vintage silently re-ranks every material." They live as
# function DEFAULTS rather than module constants so the values travel inside the
# FunctionDef — the parity harness compiles these nodes in a fresh namespace, so a
# constant read from the enclosing scope would be supplied by the test and a drifted
# notebook value would go undetected.
#
# THE INVERSION IS MANDATORY. Raw WGI is higher = better governance; WGIᶜ must be
# 1 = worst. An un-inverted index still computes and still looks plausible while ranking
# every material backwards, so the direction is pinned by test, not by reading.


def wgi_weight_expr(mean_estimate, estimate_min=-2.5, estimate_max=2.5):
    """clamp((estimate_max − mean₆) / (estimate_max − estimate_min), 0, 1).

    NULL HANDLING IS NOT COSMETIC: F.greatest / F.least IGNORE nulls and return the
    greatest/least NON-NULL argument, so a bare least(greatest(raw, 0), 1) maps a NULL
    mean to 0.0 — "perfect governance" for a country with no data. The F.when(isNotNull)
    wrapper (no .otherwise, so the else branch is NULL) keeps unknown countries unknown.
    """
    mean_col = F.col(mean_estimate) if isinstance(mean_estimate, str) else mean_estimate
    span = estimate_max - estimate_min  # 5.0 for the spec'd bounds
    raw = (F.lit(estimate_max) - mean_col) / F.lit(span)
    clamped = F.least(F.greatest(raw, F.lit(0.0)), F.lit(1.0))
    return F.when(mean_col.isNotNull(), clamped)


def compute_wgi_weight(silver_wgi, required_dimensions=6,
                       estimate_min=-2.5, estimate_max=2.5):
    """WGIᶜ per country from the long-format silver_wgi (task-031/task-035 shape).

    COMPLETENESS RULE (acceptance criterion 4) — the mean is over ALL SIX dimensions,
    never a partial mean. `wgi_year` is the LATEST year in which the country carries the
    full set of `required_dimensions` distinct indicators; a country whose most recent
    year is incomplete falls back to its most recent COMPLETE year rather than averaging
    whatever subset that year happens to hold. A country with no complete year in any
    vintage gets wgi_year / wgi_mean_estimate / wgi_weight = NULL and is reported as a
    coverage gap — NOT given an averaged-over-four-dimensions number that would be
    indistinguishable from a real one downstream.

    `wgi_dimensions_available` is diagnostic: the count at wgi_year when a complete year
    exists, else the best count the country reaches in ANY single year, so "5 of 6" is
    distinguishable from "absent from WGI entirely".

    DELIBERATE DIVERGENCE FROM create_data_gaps_table's COVERAGE FLAG (defined further
    down this notebook, at the `WGI_REQUIRED_INDICATORS = 6` rule — searched by name
    rather than line number, which shifts on every edit). See DEC-009.
    That flag counts a country as governance-covered on
    COUNT(DISTINCT indicator_name) >= WGI_REQUIRED_INDICATORS across ALL years — it is
    vintage-agnostic by design because it answers "do we hold governance data for this
    country at all?". WGIᶜ needs the six dimensions in ONE year, because a mean mixing
    2019's rule-of-law with 2023's voice-and-accountability is not a measurement of any
    year. The two rules therefore differ on purpose: a country with six dimensions spread
    across years counts as covered there and as a gap here. That divergence is documented
    rather than resolved by weakening either rule, and the coverage flag is deliberately
    NOT modified by task-038_3 (the note at its definition anticipated exactly this).
    """
    observed = (
        silver_wgi
        # Silver already drops NULL-valued rows; defensive so this is correct standalone.
        .filter(F.col("value").isNotNull())
        # No-op today (silver dedupes on (country_iso3, indicator_code, year) and asserts
        # name<->code is 1:1). Present so F.avg is provably a mean over DISTINCT
        # dimensions rather than over rows — an undetected fan-out would otherwise
        # silently re-weight one dimension.
        .dropDuplicates(["country_iso3", "indicator_name", "year"])
        .groupBy("country_iso3", "year")
        .agg(
            F.countDistinct("indicator_name").alias("dimensions_available"),
            F.avg("value").alias("mean_estimate"),
        )
    )

    # Latest COMPLETE year per country in one pass. F.max over a struct orders
    # lexicographically by its first field (year) and ignores NULLs, so the F.when
    # yields the newest year that reached the required dimension count, or NULL when the
    # country never does. `year` is unique within a country group here, so the remaining
    # struct fields never act as tie-breaks — they ride along to avoid a self-join.
    latest_complete = F.max(
        F.when(
            F.col("dimensions_available") >= F.lit(required_dimensions),
            F.struct(
                F.col("year").alias("year"),
                F.col("dimensions_available").alias("dimensions_available"),
                F.col("mean_estimate").alias("mean_estimate"),
            ),
        )
    ).alias("_latest")

    return (
        observed
        .groupBy("country_iso3")
        .agg(latest_complete, F.max("dimensions_available").alias("_best_dimensions"))
        .select(
            F.col("country_iso3"),
            F.col("_latest.year").alias("wgi_year"),
            F.coalesce(
                F.col("_latest.dimensions_available"), F.col("_best_dimensions")
            ).alias("wgi_dimensions_available"),
            F.col("_latest.mean_estimate").alias("wgi_mean_estimate"),
            wgi_weight_expr(
                F.col("_latest.mean_estimate"), estimate_min, estimate_max
            ).alias("wgi_weight"),
        )
    )


def map_wgi_weight_to_country_key(wgi_weight, dim_country):
    """Re-key the per-ISO3 weight onto country_key, the fact tables' country grain.

    The predicate mirrors the WGI coverage rule's join below (sw.country_iso3 =
    UPPER(dc.iso3)) so the two cannot drift. silver_wgi.country_iso3 is already
    UPPER+TRIM'd at silver, so only the dimension side needs normalising.

    INNER on purpose: a WGI country with no gold_dim_country row has no fact rows either.
    The gap that matters — a dim country with no WGI weight — is created by the LEFT join
    in attach_wgi_weight and measured there. Uniqueness on country_key is asserted at the
    call site rather than forced here, so a violation can name the offending keys.
    """
    return (
        wgi_weight.alias("w")
        .join(
            F.broadcast(dim_country.alias("dc")),  # task-012_3: small dim, broadcast
            F.col("w.country_iso3") == F.upper(F.col("dc.iso3")),
            "inner",
        )
        .select(
            F.col("dc.country_key").alias("country_key"),
            F.col("w.wgi_year").alias("wgi_year"),
            F.col("w.wgi_weight").alias("wgi_weight"),
        )
    )


def attach_wgi_weight(fact_df, wgi_by_country_key):
    """LEFT-join the governance weight onto a fact keyed by country_key.

    LEFT, never INNER: a country with no usable WGI vintage keeps its supply rows and
    surfaces as a measured coverage gap (wgi_weight IS NULL, counted by check_unmapped).
    Dropping it would silently shrink the supply base the HHI is computed over and make a
    material look LESS concentrated than it is.

    Original column order is preserved and the new columns appended — a join on a column
    name list would otherwise promote country_key to position 0.
    """
    original_columns = fact_df.columns
    # task-012_3: wgi_by_country_key is one row per country — broadcast.
    joined = fact_df.join(F.broadcast(wgi_by_country_key), "country_key", "left")
    return joined.select(*original_columns, "wgi_year", "wgi_weight")


# --- PRECONDITION: silver_wgi must carry the estimates -----------------------------
# The long-format silver_wgi (country_iso3, indicator_name, year, value) is the shape
# task-031 declared and task-035 put into the pipeline; both are Finished, so this branch
# is dead in the deployed pipeline and exists only for a gold run against a stale table.
# HARD STOP rather than a NULL-filled fallback: an all-NULL WGIᶜ would let task-038_4
# publish a supply-risk model that computes, looks plausible and means nothing — the same
# class of invisible error the spec's inversion warning is about. Mirrors bronze-to-silver's
# treatment of the identical incompatibility.
_wgi_src_cols = {c.lower() for c in spark.table(f"{DB}.silver_wgi").columns}
_wgi_missing = [c for c in ("country_iso3", "indicator_name", "year", "value")
                if c not in _wgi_src_cols]
if _wgi_missing:
    raise RuntimeError(
        f"silver_wgi is missing {_wgi_missing} — cannot compute WGIᶜ.\n"
        f"  Columns present: {sorted(_wgi_src_cols)}\n"
        "  CAUSE: silver_wgi is still the retired 3-column identity shape, i.e. "
        "bronze-to-silver has not re-run since task-031/task-035.\n"
        "  FIX: run bronze-to-silver (or the full pipeline) so silver_wgi is rebuilt from "
        "the long-format bronze_wgi written by bronze_ingest_wgi."
    )

wgi_weight_by_iso3 = compute_wgi_weight(spark.table(f"{DB}.silver_wgi"))
wgi_weight_by_country_key = map_wgi_weight_to_country_key(
    wgi_weight_by_iso3, spark.table(f"{DB}.gold_dim_country")
)

# GUARD: one weight per country_key, or the LEFT join fans out every supply row for that
# country and every downstream SUM(share_pct) doubles. country_key is a function of iso3
# alone and gold_dim_country is deduped on country_key, so this should be structurally
# impossible — assert it anyway, because the failure is silent and the fix is upstream.
_dup_wgi = (wgi_weight_by_country_key
            .groupBy("country_key")
            .agg(F.count(F.lit(1)).alias("n"))
            .filter(F.col("n") > 1))
_dup_wgi_n = _dup_wgi.count()
assert _dup_wgi_n == 0, (
    f"WGI weight is not unique on country_key ({_dup_wgi_n} duplicate key(s)): "
    f"{[r.asDict() for r in _dup_wgi.limit(5).collect()]}. Joining it onto "
    f"fact_supply_share would fan out the fact — fix gold_dim_country's iso3 uniqueness."
)

# Row count is captured BEFORE the join, off the pre-join frame, so the assert below
# compares two genuinely different frames and is able to fail (a fan-out changes only the
# post-join side). Same discipline as the criterion-5 baseline above.
_pre_wgi_rows = fact_supply_share_final.count()
fact_supply_share_final = attach_wgi_weight(fact_supply_share_final, wgi_weight_by_country_key)
_post_wgi_rows = fact_supply_share_final.count()
assert _pre_wgi_rows == _post_wgi_rows, (
    f"WGI join changed fact_supply_share row count: {_pre_wgi_rows:,} -> "
    f"{_post_wgi_rows:,}. A LEFT join must be row-preserving; a change means the weight "
    f"frame is not unique on country_key."
)

# --- COVERAGE (acceptance criterion 5) --------------------------------------------
# Measured and surfaced through the EXISTING check_unmapped mechanism, not a bespoke
# path and not a silent drop. check_unmapped counts rows whose joined column is NULL —
# here that is exactly "supply rows with no usable WGI vintage".
wgi_unmapped_rows = check_unmapped(fact_supply_share_final, "wgi_weight",
                                   "WGI governance weight")

# check_unmapped's own log prints the distinct values of the checked column, which for a
# null-check is just [null]. The breakdown below is what makes the number actionable —
# it names the countries and splits the fixable gaps from the unfixable ones. Placeholder
# countries (iso3 UNK_*) can never carry a WGI weight by construction, so counting them
# against coverage would set a floor no alias work could ever clear.
if wgi_unmapped_rows > 0:
    _wgi_gap_detail = (
        fact_supply_share_final
        .filter(F.col("wgi_weight").isNull())
        .join(spark.table(f"{DB}.gold_dim_country")
                   .select("country_key", "iso3", "country_name_std", "is_placeholder"),
              "country_key", "left")
        .groupBy("iso3", "country_name_std", "is_placeholder")
        .agg(F.count(F.lit(1)).alias("n"),          # NOT `count`: Row subclasses tuple
             F.sum("share_pct").alias("total_share_pct"))
        .orderBy(F.desc("total_share_pct"))
    )
    _placeholder_rows = (fact_supply_share_final
                         .filter(F.col("wgi_weight").isNull())
                         .join(spark.table(f"{DB}.gold_dim_country")
                                    .select("country_key", "is_placeholder"),
                               "country_key", "left")
                         .filter(F.coalesce(F.col("is_placeholder"), F.lit(False)))
                         .count())
    print(f"\n  WGI coverage gap: {wgi_unmapped_rows:,} of {_post_wgi_rows:,} supply rows "
          f"have no governance weight "
          f"({_placeholder_rows:,} on placeholder countries — not remediable by aliasing; "
          f"{wgi_unmapped_rows - _placeholder_rows:,} on real countries).")
    print("  Countries with no usable WGI vintage (by supply share at risk):")
    _wgi_gap_detail.show(20, truncate=False)
else:
    print(f"\n  WGI coverage: all {_post_wgi_rows:,} supply rows carry a governance weight.")

# Vintage provenance — the spec's reproducibility requirement is about the WEIGHTS being
# stable, so which vintage each country landed on is worth stating once per run.
print("\n  WGIᶜ vintages in use (countries per latest complete year):")
(wgi_weight_by_iso3
 .groupBy("wgi_year")
 .agg(F.count(F.lit(1)).alias("countries"),
      F.min("wgi_weight").alias("min_weight"),
      F.max("wgi_weight").alias("max_weight"))
 .orderBy(F.col("wgi_year").desc_nulls_last())
 ).show(truncate=False)

write_tbl(fact_supply_share_final, "fact_supply_share")

# Detailed audit trail for unmapped supply shares — ONE ROW PER (source row x failed
# dimension), matching gold_unmapped_procurement_audit.
#
# task-027: the old chained when/when/when recorded only the FIRST failing dimension, so
# a row whose material AND country both failed was logged as a material gap and the
# country gap was invisible. It also stored original_material/original_country/
# original_stage unconditionally, which is what let the gap registry's COALESCE pick a
# material name and label it a country gap.
#
# unmapped_dimension is renamed to unmapped_type so both audit tables expose the same
# contract (unmapped_type + gap_dimension + unmapped_value); share_pct and impact_level
# are kept because gap prioritisation for supply is share-weighted.
#
# task-038_2: this audit stays MIX-INCLUSIVE and gains a supply_mix column. It is a
# per-source-row gap worklist, not an aggregate — an unmapped material or country in the EU
# sourcing table is a genuine gap that now affects real fact rows, so suppressing it would
# hide work rather than protect a number. Nothing here sums across mixes, so including both
# cannot double-count; supply_mix simply tells the remediator which source the gap came from.
unmapped_supply_audit = (
    fact_supply_share_raw
    .select(
        F.col("s.row_id").alias("row_id"),
        F.col("s.supply_mix").alias("supply_mix"),
        F.col("s.share_pct").alias("share_pct"),
        F.array(
            unmapped_gap(F.col("m.material_key").isNull(),
                         "material", "material", F.col("s.material")),
            unmapped_gap(F.col("c.country_key").isNull(),
                         "country", "country", F.col("s.country")),
            unmapped_gap(F.col("st.stage_key").isNull(),
                         "stage", "stage", F.col("s.stage")),
        ).alias("gap_candidates"),
    )
    .select("row_id", "supply_mix", "share_pct", F.explode("gap_candidates").alias("gap"))
    .filter(F.col("gap").isNotNull())
    .select(
        "row_id",
        "supply_mix",
        F.col("gap.unmapped_type").alias("unmapped_type"),
        F.col("gap.gap_dimension").alias("gap_dimension"),
        F.col("gap.unmapped_value").alias("unmapped_value"),
        "share_pct",
        # Impact assessment (unchanged thresholds)
        F.when(F.col("share_pct") > 10, "High Impact")
         .when(F.col("share_pct") > 5, "Medium Impact")
         .otherwise("Low Impact").alias("impact_level"),
        F.current_timestamp().alias("detected_timestamp"),
    )
)

write_tbl(unmapped_supply_audit, "gold_unmapped_supply_audit")

# NEW: Create aggregated quality metrics for supply shares
# This helps identify which materials/countries have poor data quality
# task-038_2: grouped BY supply_mix, not across it. total_share_pct is a SUM of share_pct,
# and spec_v1 item 2 forbids summing the two mixes together — a material's global shares sum
# to ~100 and its EU sourcing shares sum to ~100, so a blended total would read ~200 and mean
# nothing. Reporting them side by side is DEC-001 Option B's stated presentation.
quality_by_material = (
    fact_supply_share_final
    .groupBy("material_key", "supply_mix")
    .agg(
        F.count("*").alias("record_count"),
        F.avg("data_quality_score").alias("avg_quality_score"),
        F.sum(F.when(F.col("has_unmapped_country"), 1).otherwise(0)).alias("unmapped_country_count"),
        F.sum("share_pct").alias("total_share_pct")
    )
    .join(dim_material.select("material_key", "material_name_std"), "material_key")
    .orderBy(F.desc("unmapped_country_count"))
)

print("\n" + "="*60)
print("SUPPLY SHARE QUALITY BY MATERIAL")
print("="*60)
quality_by_material.show(20, truncate=False)

# Create visualization-ready views with quality filters.
#
# task-038_2 MIGRATION — per-view decision on whether each consumer stays global-only or
# becomes mix-aware. The dividing line is AGGREGATION: a view that only filters/decorates
# rows cannot double-count, so it stays mix-inclusive and simply exposes supply_mix for the
# consumer to pivot on. A view that AGGREGATES over the fact would blend the two mixes and
# silently change its own pre-DEC-001 meaning, so it is pinned to the global mix.
#   v_fact_supply_share_high_confidence  MIX-INCLUSIVE — pure quality filter, no aggregation
#   v_fact_supply_share_complete         MIX-INCLUSIVE — pure decoration, no aggregation
#   v_supply_concentration_risk          GLOBAL-ONLY   — aggregates (MAX/COUNT/SUM/AVG)
# Both mix-inclusive views select fs.*, so supply_mix and t flow through automatically and
# every downstream consumer can filter or pivot on the discriminator.
spark.sql(f"""
    CREATE OR REPLACE VIEW {DB}.v_fact_supply_share_high_confidence AS
    SELECT 
        fs.*,
        dm.material_name_std,
        dm.commodity_group,
        dc.country_name_std,
        dc.iso3,
        dc.region,
        ds.stage_name
    FROM {DB}.fact_supply_share fs
    JOIN {DB}.gold_dim_material dm ON fs.material_key = dm.material_key
    JOIN {DB}.gold_dim_country dc ON fs.country_key = dc.country_key
    JOIN {DB}.gold_dim_stage ds ON fs.stage_key = ds.stage_key
    WHERE fs.data_quality_score >= 0.9
    AND NOT fs.has_unmapped_material
    AND NOT fs.has_unmapped_country
""")

spark.sql(f"""
    CREATE OR REPLACE VIEW {DB}.v_fact_supply_share_complete AS
    SELECT 
        fs.*,
        dm.material_name_std,
        dm.commodity_group,
        dm.is_placeholder as material_is_unknown,
        dc.country_name_std,
        dc.iso3,
        dc.region,
        dc.is_placeholder as country_is_unknown,
        ds.stage_name,
        -- Add warning flag for visualizations
        CASE 
            WHEN fs.has_unmapped_material OR fs.has_unmapped_country THEN 'Contains Unknown Values'
            WHEN fs.data_quality_score < 0.7 THEN 'Low Confidence Match'
            ELSE 'Verified'
        END as data_warning
    FROM {DB}.fact_supply_share fs
    JOIN {DB}.gold_dim_material dm ON fs.material_key = dm.material_key
    JOIN {DB}.gold_dim_country dc ON fs.country_key = dc.country_key
    JOIN {DB}.gold_dim_stage ds ON fs.stage_key = ds.stage_key
""")

# Create summary statistics for supply concentration risk.
#
# task-038_2 MIGRATION (acceptance criterion 3) — THE supply_mix = 'global' FILTER IS
# LOAD-BEARING. This view existed before DEC-001 and meant "concentration of WORLDWIDE
# PRODUCTION per material/stage". Every aggregate below would silently change meaning the
# moment EU rows landed in the fact:
#   MAX(share_pct)              -> would take the max across BOTH mixes, so an EU sourcing
#                                  share could set the concentration_risk_level of a
#                                  material whose global production is well diversified
#   COUNT(DISTINCT country_key) -> would union the global producer set with the EU supplier
#                                  set, inflating the apparent supplier count
#   SUM(... share_pct > 30)     -> counts rows, so it would roughly double
#   AVG(data_quality_score)     -> would be diluted by the other mix
# spec_v1 § Data Architecture -> Gold Layer item 2 pins this view to the global mix for
# exactly that reason. The EU-sourcing counterpart is a separate deliverable (DEC-001
# Option B reports the two side by side); it must NOT be produced by relaxing this filter.
spark.sql(f"""
    CREATE OR REPLACE VIEW {DB}.v_supply_concentration_risk AS
    SELECT
        material_name_std,
        commodity_group,
        stage_name,
        MAX(share_pct) as max_country_share,
        COUNT(DISTINCT country_key) as supplier_country_count,
        SUM(CASE WHEN share_pct > 30 THEN 1 ELSE 0 END) as high_concentration_countries,
        AVG(data_quality_score) as avg_data_quality,
        SUM(CASE WHEN has_unmapped_country THEN 1 ELSE 0 END) as unmapped_countries,
        CASE 
            WHEN MAX(share_pct) > 50 THEN 'Critical'
            WHEN MAX(share_pct) > 30 THEN 'High'
            WHEN MAX(share_pct) > 20 THEN 'Medium'
            ELSE 'Low'
        END as concentration_risk_level
    FROM {DB}.v_fact_supply_share_complete
    WHERE supply_mix = 'global'
    GROUP BY material_name_std, commodity_group, stage_name
""")

print("\n" + "="*60)
print("SUPPLY SHARE FACT COMPLETION SUMMARY")
print("="*60)
print(f"Total records processed: {total_supply_records:,}")
print(f"Records written to fact: {fact_supply_share_final.count():,}")
print(f"Records in audit trail: {unmapped_supply_audit.count():,}")
print(f"\nViews created:")
print("  - v_fact_supply_share_high_confidence: Verified data only (both supply mixes)")
print("  - v_fact_supply_share_complete: All data with quality flags (both supply mixes)")
print("  - v_supply_concentration_risk: Risk analysis view (global mix only — task-038_2)")
print(f"\nData Quality Distribution (by supply mix — never blended):")
(fact_supply_share_final
 .groupBy("supply_mix", "quality_category").count()
 .orderBy("supply_mix", "quality_category").show())

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# # gold_supply_risk — governance- & trade-weighted HHI (task-038_4)
# spec_v1 § Business Logic & Calculations -> Supply Risk (DEC-001 Option B)
# Grain: one row per material × stage × year. Both stages (E/P) retained and the
# bottleneck FLAGGED rather than collapsed, so the extraction-vs-processing
# comparison stays available to the report while the headline figure needs no
# DAX ranking pattern.

# CELL ********************

# =============================================================================
# HHI aggregation — gold_supply_risk (task-038_4)
#   HHI_WGI,t = Σ_c (Sᶜ)² · WGIᶜ · tᶜ
#
# This block owns the AGGREGATION half of the supply-risk model — the per-mix
# HHI, the contrast_ratio, the bottleneck flag and the WGI-coverage flag. The
# per-country weight WGIᶜ is task-038_3 (the cell directly above); this consumes
# it from fact_supply_share and never recomputes it.
#
# MIRRORED IN src/transformations/supply_risk.py (DEC-002). tests/test_supply_risk.py
# loads THESE FunctionDefs out of this file and pins them against the src/
# versions — editing one side without the other fails CI by design.
#
# THE SHARE FRACTION IS THE WHOLE POINT. share_pct is stored 0-100 on
# fact_supply_share; squaring the 0-100 scale silently inflates the index by 10^4
# and produces a plausible-looking but wrong number. The division by 100 in
# supply_risk_contribution is pinned by a parity test.
#
# THE GRAIN IS material × stage × year (spec § Data Architecture →
# gold_supply_risk, § Business Logic & Calculations → Supply Risk).
#
# NULL RULES (each pinned by a test):
#   1. NULL wgi_weight rows are EXCLUDED from the Σ_c sum — never coerced to 0.
#      0.0 is a legitimate weight meaning *best governance*, so coercing NULL
#      to 0 would read as a perfectly-governed country and silently re-rank
#      every material. F.greatest/F.least IGNORE nulls and would swallow them
#      the way task-038_3 found; the .filter(wgi_weight.isNotNull()) guard is
#      explicit.
#   2. Placeholder countries (gold_dim_country.is_placeholder = TRUE, e.g.
#      UNK_GLOB) are excluded from the country-level HHI sum regardless of
#      their weight — a placeholder is a bucket, not a country. The weight is
#      NULL by construction but the guard is defensive.
#   3. EU coverage gap (global rows exist, no eu_sourcing rows) →
#      hhi_eu_sourcing = NULL, contrast_ratio = NULL — never 0.
#   4. hhi_global = 0 → contrast_ratio = NULL, never 0.
#
# THE TAIWAN / NULL-WGI TRADEOFF (DEC-009 + user decision, task-038_4). A country
# can have wgi_weight = NULL — TWN (World Bank publishes no WGI for Taiwan, ever;
# ~14 rows / ~19.4 share-points on the live fact) and UNK_GLOB (placeholder).
# Erik's decision: EXCLUDE + FLAG COVERAGE. Rows with NULL wgi_weight are dropped
# from the Σ_c sum, so the HHI is computed over the governance-known subset only.
# This UNDERSTATES risk for Taiwan-heavy materials — it is an accepted, visible
# tradeoff, not a bug. The incomplete_wgi_coverage column makes the gap visible
# rather than silent.


def supply_risk_contribution(share_pct, wgi_weight, t):
    """The per-country contribution (Sᶜ)² · WGIᶜ · tᶜ as a Spark Column.

    Sᶜ = share_pct / 100 — the FRACTION, not the 0-100 percentage. share_pct is
    stored 0-100 on fact_supply_share, so squaring the wrong scale silently
    inflates the index by 10^4 and produces a plausible-looking but wrong number;
    a parity test pins the division by 100 explicitly. `t` is the DEC-001 trade
    parameter (0.8 EU, 1.0 baseline non-EU, >1 export-restricted) and is nullable
    on the fact — a NULL t yields a NULL contribution, which F.sum skips, so a
    row with no trade parameter is excluded from the sum rather than zeroed.

    Accepts column names (str) or Column expressions for all three arguments.
    """
    def _col(x):
        return F.col(x) if isinstance(x, str) else x

    share_frac = _col(share_pct) / F.lit(100.0)
    return (share_frac * share_frac) * _col(wgi_weight) * _col(t)


def compute_gold_supply_risk(fact_supply_share, dim_country):
    """Build the gold_supply_risk table content from fact_supply_share.

    Spec: § Business Logic & Calculations → Supply Risk (DEC-001 Option B) +
    § Data Architecture → gold_supply_risk. Grain: one row per
    (material_key, stage_key, year). Both stages (E/P) retained; the bottleneck
    is FLAGGED (is_bottleneck) rather than collapsed.

    Output columns:
      hhi_global              Σ_c (Sᶜ)²·WGIᶜ·tᶜ over supply_mix='global'
      hhi_eu_sourcing         same over supply_mix='eu_sourcing'; NULL when the
                              material × stage × year has no EU sourcing rows
                              (the EU coverage gap — never 0)
      contrast_ratio          hhi_eu_sourcing / hhi_global; NULL when
                              hhi_global is 0 or NULL, or when hhi_eu_sourcing
                              is NULL (never 0 — 0 is a legitimate "perfectly
                              diffuse" index value, not "no EU data")
      is_bottleneck           BOOLEAN — the stage with the HIGHER hhi_global per
                              material × year. Driven by hhi_global ONLY (not
                              hhi_eu_sourcing, not max of the two) so it stays
                              defined when EU coverage is missing. Strict: a tie
                              flags neither stage. NULL hhi_global never wins.
      incomplete_wgi_coverage BOOLEAN — TRUE when any supplier row for this
                              material × stage × year was excluded due to NULL
                              wgi_weight (TWN; or a placeholder bucket). The HHI
                              is then computed over the governance-known subset
                              only, which UNDERSTATES risk for Taiwan-heavy
                              materials — an accepted, visible tradeoff, not a
                              bug. The flag makes the gap visible rather than
                              silent.

    Implemented without a Window so the parity harness (which compiles only these
    FunctionDefs in a namespace holding `F` alone) needs no extra imports.
    """
    # Bring is_placeholder onto the fact — it is not carried on fact_supply_share,
    # only on gold_dim_country. LEFT so a fact row whose country_key is missing
    # from the dim keeps its supply row and is excluded by the wgi_weight filter
    # rather than dropped here.
    fs = fact_supply_share.join(
        F.broadcast(dim_country.select("country_key", "is_placeholder")),  # task-012_3
        "country_key", "left",
    )

    contribution = supply_risk_contribution("share_pct", "wgi_weight", "t")

    # HHI per (material × stage × year × supply_mix), summed over the
    # governance-known, non-placeholder subset only. NULL wgi_weight rows are
    # excluded, NOT zeroed (rule 1). Placeholders excluded by rule 2.
    per_mix = (
        fs
        .filter(F.col("wgi_weight").isNotNull())
        .filter(~F.coalesce(F.col("is_placeholder"), F.lit(False)))
        .groupBy("material_key", "stage_key", "year", "supply_mix")
        .agg(F.sum(contribution).alias("hhi"))
    )

    hhi_global = (
        per_mix.filter(F.col("supply_mix") == "global")
        .select("material_key", "stage_key", "year", F.col("hhi").alias("hhi_global"))
    )
    hhi_eu = (
        per_mix.filter(F.col("supply_mix") == "eu_sourcing")
        .select("material_key", "stage_key", "year", F.col("hhi").alias("hhi_eu_sourcing"))
    )

    # The grain is every (material × stage × year) appearing in EITHER mix. A
    # material present in global but absent from eu_sourcing (the EU coverage
    # gap) still gets a row, with hhi_eu_sourcing = NULL (rule 3). The reverse
    # is symmetric. Starting from `fs` (pre-filter) rather than `per_mix`
    # (post-filter) means a key whose only rows were all-NULL-wgi still appears,
    # with both HHIs NULL and incomplete_wgi_coverage = TRUE.
    grain_keys = (
        fs.select("material_key", "stage_key", "year").distinct()
    )

    result = (
        grain_keys
        .join(hhi_global, ["material_key", "stage_key", "year"], "left")
        .join(hhi_eu, ["material_key", "stage_key", "year"], "left")
    )

    # contrast_ratio (rules 3 + 4): NULL when hhi_global is NULL or 0, or when
    # hhi_eu_sourcing is NULL. The F.when guard is what keeps 0/0 from returning a
    # sentinel; in ANSI-off mode 0/0 is NULL anyway, but the explicit guard is
    # readable and survives an ANSI-on regression.
    result = result.withColumn(
        "contrast_ratio",
        F.when(
            (F.col("hhi_global").isNotNull())
            & (F.col("hhi_global") != F.lit(0.0))
            & (F.col("hhi_eu_sourcing").isNotNull()),
            F.col("hhi_eu_sourcing") / F.col("hhi_global"),
        ),
    )

    # incomplete_wgi_coverage (rule 1 visibility): TRUE when any supplier row for
    # this material × stage × year was excluded due to NULL wgi_weight. Computed
    # across BOTH mixes — wgi_weight is a country property, not a mix property.
    # A placeholder bucket (UNK_GLOB) also carries NULL wgi_weight and is flagged
    # here; that is correct — the index for that key IS computed over an
    # incomplete governance subset.
    excluded = (
        fs
        .filter(F.col("wgi_weight").isNull())
        .groupBy("material_key", "stage_key", "year")
        .agg(F.count(F.lit(1)).alias("_n_excluded"))
    )
    result = (
        result
        .join(excluded, ["material_key", "stage_key", "year"], "left")
        .withColumn(
            "incomplete_wgi_coverage",
            F.col("_n_excluded").isNotNull() & (F.col("_n_excluded") > 0),
        )
        .drop("_n_excluded")
    )

    # is_bottleneck: the stage with the HIGHER hhi_global per material × year.
    # Driven by hhi_global ONLY (spec: "not by hhi_eu_sourcing or the max of the
    # two") so it stays defined when EU coverage is missing. Strict comparison —
    # a tie flags NEITHER stage; NULL hhi_global never wins.
    maxes = (
        result
        .filter(F.col("hhi_global").isNotNull())
        .groupBy("material_key", "year")
        .agg(F.max("hhi_global").alias("_max_hhi"))
    )
    at_max = (
        result
        .filter(F.col("hhi_global").isNotNull())
        .join(maxes, ["material_key", "year"], "inner")
        .filter(F.col("hhi_global") == F.col("_max_hhi"))
        .groupBy("material_key", "year")
        .agg(F.count(F.lit(1)).alias("_n_at_max"))
    )
    result = (
        result
        .join(maxes, ["material_key", "year"], "left")
        .join(at_max, ["material_key", "year"], "left")
        .withColumn(
            "is_bottleneck",
            (F.col("hhi_global").isNotNull())
            & (F.col("hhi_global") == F.col("_max_hhi"))
            & (F.col("_n_at_max") == F.lit(1)),
        )
        .drop("_max_hhi", "_n_at_max")
    )

    return result.select(
        "material_key", "stage_key", "year",
        "hhi_global", "hhi_eu_sourcing", "contrast_ratio",
        "is_bottleneck", "incomplete_wgi_coverage",
    )


gold_supply_risk = compute_gold_supply_risk(
    fact_supply_share_final, spark.table(f"{DB}.gold_dim_country")
)

# GRAIN GUARD (acceptance criterion 1): one row per (material_key, stage_key,
# year) — enforced, fails loudly. A duplicate here means either fact_supply_share
# carries a grain collision (the territory rollup upstream should have collapsed
# it) or compute_gold_supply_risk dropped supply_mix from the grouping key.
_dup_supply_risk = (gold_supply_risk
                    .groupBy("material_key", "stage_key", "year")
                    .agg(F.count(F.lit(1)).alias("n"))
                    .filter(F.col("n") > 1))
_dup_supply_risk_n = _dup_supply_risk.count()
assert _dup_supply_risk_n == 0, (
    f"gold_supply_risk grain is not unique on (material_key, stage_key, year) — "
    f"{_dup_supply_risk_n} duplicate grain(s): "
    f"{[r.asDict() for r in _dup_supply_risk.limit(5).collect()]}. Either "
    f"fact_supply_share has a grain collision the territory rollup missed, or "
    f"compute_gold_supply_risk dropped supply_mix from the HHI grouping key."
)

# COVERAGE SUMMARY — make the Taiwan/placeholder exclusion visible per run, not
# just per row. The incomplete_wgi_coverage flag is the durable surface; this
# print is the operational view so a degraded run is obvious in the notebook log.
_coverage_summary = (
    gold_supply_risk
    .groupBy("incomplete_wgi_coverage")
    .agg(F.count(F.lit(1)).alias("rows"))
)
print("\n" + "="*60)
print("gold_supply_risk — WGI coverage summary")
print("="*60)
(_coverage_summary.orderBy(F.col("incomplete_wgi_coverage").desc()).show())

_bottleneck_n = gold_supply_risk.filter(F.col("is_bottleneck")).count()
_total_rows = gold_supply_risk.count()
_eu_gap_n = gold_supply_risk.filter(F.col("hhi_eu_sourcing").isNull()).count()
print(f"gold_supply_risk: {_total_rows:,} rows ({_bottleneck_n:,} flagged bottleneck, "
      f"{_eu_gap_n:,} with EU coverage gap / hhi_eu_sourcing NULL)")

write_tbl(gold_supply_risk, "gold_supply_risk")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# # Data quality dashboard table

# CELL ********************

def create_quality_dashboard():
    """
    Create a summary table for BI tools to show data quality metrics.
    This enables transparency in dashboards and reports.
    """
    quality_metrics = spark.sql(f"""
        SELECT 
            'fact_procurement' as fact_table,
            COUNT(*) as total_records,
            SUM(CASE WHEN quality_category = 'High' THEN 1 ELSE 0 END) as high_quality_records,
            SUM(CASE WHEN quality_category = 'Medium' THEN 1 ELSE 0 END) as medium_quality_records,
            SUM(CASE WHEN quality_category = 'Low' THEN 1 ELSE 0 END) as low_quality_records,
            SUM(CASE WHEN quality_category = 'Unmapped' THEN 1 ELSE 0 END) as unmapped_records,
            AVG(data_quality_score) as avg_quality_score,
            CURRENT_TIMESTAMP() as calculation_timestamp
        FROM {DB}.fact_procurement
    """)
    
    write_tbl(quality_metrics, "gold_data_quality_metrics")
    return quality_metrics

quality_dashboard = create_quality_dashboard()

## NEW: Create visualization-ready views with quality filters
# These views allow analysts to choose their data quality threshold
spark.sql(f"""
    CREATE OR REPLACE VIEW {DB}.v_fact_procurement_high_confidence AS
    SELECT * FROM {DB}.fact_procurement
    WHERE data_quality_score >= 0.9
""")

spark.sql(f"""
    CREATE OR REPLACE VIEW {DB}.v_fact_procurement_all AS
    SELECT 
        fp.*,
        dc_hq.country_name_std as supplier_country_name,
        dc_hq.is_placeholder as supplier_is_unknown,
        dc_prod.country_name_std as production_country_name,
        dc_prod.is_placeholder as production_is_unknown,
        dm.material_name_std,
        dm.commodity_group,
        dm.is_placeholder as material_is_unknown
    FROM {DB}.fact_procurement fp
    LEFT JOIN {DB}.gold_dim_country dc_hq ON fp.supplier_hq_country_key = dc_hq.country_key
    LEFT JOIN {DB}.gold_dim_country dc_prod ON fp.production_country_key = dc_prod.country_key
    LEFT JOIN {DB}.gold_dim_material dm ON fp.material_key = dm.material_key
""")

print("\n" + "="*70)
print("ENHANCED PIPELINE EXECUTION SUMMARY")
print("="*70)
print("\nViews created for visualization:")
print("  - v_fact_procurement_high_confidence: Only high quality matches")
print("  - v_fact_procurement_all: All data with quality indicators")
print("\nQuality tracking tables:")
print("  - gold_data_quality_metrics: Summary metrics for dashboards")
print("  - gold_unmapped_procurement_audit: Detailed unmapped records")
print("  - gold_country_coverage_matrix: Country presence across sources")
print("\nVisualization guidance:")
print("  - Use quality_category field to show confidence in charts")
print("  - Filter on is_placeholder=False to exclude unknowns")
print("  - Include data_quality_score as tooltip for transparency")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# # Comprehensive Data Quality Dashboard Table (Task 001)

# CELL ********************

def create_dq_dashboard():
    """
    Create a comprehensive data quality dashboard table optimized for Power BI.
    This table provides all key metrics needed for a Data Quality page in the report.
    """

    # Get procurement metrics
    proc_metrics = spark.sql(f"""
        SELECT
            COUNT(*) as total_records,
            AVG(data_quality_score) as avg_quality_score,
            SUM(CASE WHEN quality_category = 'High' THEN 1 ELSE 0 END) as high_count,
            SUM(CASE WHEN quality_category = 'Medium' THEN 1 ELSE 0 END) as medium_count,
            SUM(CASE WHEN quality_category = 'Low' THEN 1 ELSE 0 END) as low_count,
            SUM(CASE WHEN quality_category = 'Unmapped' THEN 1 ELSE 0 END) as unmapped_count,
            SUM(spend_eur) as total_spend
        FROM {DB}.fact_procurement
    """).first()

    # Get supply share metrics
    supply_metrics = spark.sql(f"""
        SELECT
            COUNT(*) as total_records,
            AVG(data_quality_score) as avg_quality_score,
            SUM(CASE WHEN quality_category = 'High' THEN 1 ELSE 0 END) as high_count,
            SUM(CASE WHEN quality_category = 'Medium' THEN 1 ELSE 0 END) as medium_count,
            SUM(CASE WHEN quality_category = 'Low' THEN 1 ELSE 0 END) as low_count,
            SUM(CASE WHEN quality_category = 'Unmapped' THEN 1 ELSE 0 END) as unmapped_count
        FROM {DB}.fact_supply_share
    """).first()

    # Get unmapped audit counts
    unmapped_proc_count = spark.table(f"{DB}.gold_unmapped_procurement_audit").count()
    unmapped_supply_count = spark.table(f"{DB}.gold_unmapped_supply_audit").count()

    # Get top unmapped values.
    # task-027: the audit table now carries one row per failed dimension, so "top unmapped
    # materials" is a filter on unmapped_type instead of a scan of a material column that
    # was populated even when the material matched fine and the country was the real gap.
    # The country query filters on gap_dimension so hq_country and prod_country misses are
    # counted together — the same alias fixes both.
    # The count alias is deliberately NOT `count`: pyspark Row inherits tuple.count, so
    # `row.count` returns the bound tuple method (float(row.count) raises TypeError) —
    # the old alias only escaped that because this audit table happened to be empty.
    top_unmapped_materials = spark.sql(f"""
        SELECT unmapped_value, COUNT(*) as occurrence_count
        FROM {DB}.gold_unmapped_procurement_audit
        WHERE unmapped_type = 'material' AND unmapped_value IS NOT NULL
        GROUP BY unmapped_value
        ORDER BY occurrence_count DESC
        LIMIT 10
    """).collect()

    top_unmapped_countries = spark.sql(f"""
        SELECT unmapped_value, COUNT(*) as occurrence_count
        FROM {DB}.gold_unmapped_procurement_audit
        WHERE gap_dimension = 'country' AND unmapped_value IS NOT NULL
        GROUP BY unmapped_value
        ORDER BY occurrence_count DESC
        LIMIT 10
    """).collect()

    # Build dashboard table with all metrics in long format (category, metric_name, metric_value)
    # IMPORTANT: Cast all metric_value to float to avoid type mismatch errors
    dashboard_rows = [
        # Overall Metrics
        ("Overall", "Match Rate", float(proc_metrics.avg_quality_score * 100 if proc_metrics.avg_quality_score else 0), "Percentage of records with high-confidence matches", datetime.now()),
        ("Overall", "Total Records", float(proc_metrics.total_records + supply_metrics.total_records), "Combined procurement and supply share records", datetime.now()),
        ("Overall", "High Confidence %", float((proc_metrics.high_count / proc_metrics.total_records * 100) if proc_metrics.total_records else 0), "Records with quality score >= 0.9", datetime.now()),
        # task-027: the audit tables are now one row per (source row x failed dimension), so
        # this counts unmapped dimension instances — a transaction that failed on both
        # material and production country contributes 2. metric_name is left unchanged
        # because Power BI visuals filter on it; only the description is corrected.
        ("Overall", "Unmapped Records", float(unmapped_proc_count + unmapped_supply_count), "Total unmapped dimension instances (one per source row x failed dimension)", datetime.now()),

        # Procurement Metrics
        ("Procurement", "Total Records", float(proc_metrics.total_records), "Number of procurement transactions", datetime.now()),
        ("Procurement", "Match Rate", float(proc_metrics.avg_quality_score * 100 if proc_metrics.avg_quality_score else 0), "Average quality score for procurement", datetime.now()),
        ("Procurement", "High Confidence Count", float(proc_metrics.high_count), "Records with High quality category", datetime.now()),
        ("Procurement", "Medium Confidence Count", float(proc_metrics.medium_count), "Records with Medium quality category", datetime.now()),
        ("Procurement", "Low Confidence Count", float(proc_metrics.low_count), "Records with Low quality category", datetime.now()),
        ("Procurement", "Unmapped Count", float(proc_metrics.unmapped_count), "Records with Unmapped quality category", datetime.now()),
        ("Procurement", "Total Spend EUR", float(proc_metrics.total_spend if proc_metrics.total_spend else 0), "Total procurement spend in EUR", datetime.now()),

        # Supply Share Metrics
        ("Supply", "Total Records", float(supply_metrics.total_records), "Number of supply share records", datetime.now()),
        ("Supply", "Match Rate", float(supply_metrics.avg_quality_score * 100 if supply_metrics.avg_quality_score else 0), "Average quality score for supply shares", datetime.now()),
        ("Supply", "High Confidence Count", float(supply_metrics.high_count), "Records with High quality category", datetime.now()),
        ("Supply", "Medium Confidence Count", float(supply_metrics.medium_count), "Records with Medium quality category", datetime.now()),
        ("Supply", "Low Confidence Count", float(supply_metrics.low_count), "Records with Low quality category", datetime.now()),
        ("Supply", "Unmapped Count", float(supply_metrics.unmapped_count), "Records with Unmapped quality category", datetime.now()),
    ]

    # Add top unmapped materials
    for i, row in enumerate(top_unmapped_materials):
        dashboard_rows.append((
            "Unmapped Materials",
            f"#{i+1}: {row.unmapped_value}",
            float(row.occurrence_count),
            f"Unmapped material name appearing {row.occurrence_count} times",
            datetime.now()
        ))

    # Add top unmapped countries
    for i, row in enumerate(top_unmapped_countries):
        dashboard_rows.append((
            "Unmapped Countries",
            f"#{i+1}: {row.unmapped_value}",
            float(row.occurrence_count),
            f"Unmapped country name appearing {row.occurrence_count} times",
            datetime.now()
        ))

    # Create DataFrame
    dq_dashboard = spark.createDataFrame(
        dashboard_rows,
        ["category", "metric_name", "metric_value", "description", "metric_date"]
    )

    write_tbl(dq_dashboard, "gold_data_quality_dashboard")
    return dq_dashboard

# Execute dashboard creation
dq_dashboard = create_dq_dashboard()

print("\n" + "="*70)
print("DATA QUALITY DASHBOARD TABLE CREATED")
print("="*70)
print(f"\nTable: {DB}.gold_data_quality_dashboard")
print(f"Records: {dq_dashboard.count()}")
print("\nMetric Categories:")
dq_dashboard.groupBy("category").count().orderBy("category").show()

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# # Data Gaps Visibility Table
# This table shows which countries/materials in procurement are MISSING indicator data (EPI scores).
# Purpose: Enable actionable insights like "Contact suppliers in these countries for sustainability data"

# CELL ********************

# task-031: how many distinct WGI indicators a country needs before it counts as
# governance-covered. Six is the full set fetched by bronze_ingest_wgi
# (WGI_INDICATORS: CC.EST, GE.EST, PV.EST, RL.EST, RQ.EST, VA.EST) and the number
# spec_v1 § Data Transformations #3 requires coverage rules to test against.
# bronze-to-silver warns at load time if fewer than six ever reach silver_wgi, which
# is the failure mode that would drive this flag to zero for every country.
WGI_REQUIRED_INDICATORS = 6


def create_data_gaps_table():
    """
    Create a comprehensive data gaps table showing:
    1. Countries in procurement that have NO EPI scores
    2. Countries in procurement that have NO WGI scores
    3. Coverage percentages for actionable reporting
    4. Spend impact of missing data

    This enables the Data Gaps page in Power BI to show:
    - "X of Y supplier countries have full indicator coverage (EPI + WGI)"
    - "€Z spend is with suppliers in countries without sustainability/governance data"
    """

    # 1. Get distinct countries from procurement (both supplier HQ and production)
    procurement_countries = spark.sql(f"""
        SELECT DISTINCT supplier_hq_country_key as country_key, 'Supplier HQ' as country_role
        FROM {DB}.fact_procurement
        WHERE supplier_hq_country_key IS NOT NULL
        UNION
        SELECT DISTINCT production_country_key as country_key, 'Production' as country_role
        FROM {DB}.fact_procurement
        WHERE production_country_key IS NOT NULL
    """)

    # 2. Countries with an overall EPI composite score (abbrev='EPI'). Post-task-054
    #    the fact table carries 30+ sub-indicator rows per country, so filtering only
    #    on score IS NOT NULL would count a country with any non-null sub-indicator.
    #    Joining gold_dim_indicator on indicator_key and restricting to abbrev='EPI'
    #    keeps this aligned to the TMDL 'Countries with EPI Data' measure
    #    (DISTINCTCOUNT(country_key) filtered to gold_dim_indicator[abbrev]="EPI").
    countries_with_epi = spark.sql(f"""
        SELECT DISTINCT f.country_key
        FROM {DB}.fact_epi_score f
        JOIN {DB}.gold_dim_indicator d ON f.indicator_key = d.indicator_key
        WHERE d.abbrev = 'EPI' AND f.score IS NOT NULL
    """)

    # 3. Get countries that have WGI scores (World Governance Indicators)
    # Join silver_wgi to dim_country via Country Code (ISO3)
    # Require ALL SIX WGI indicators for "complete" governance coverage
    # This creates authentic gaps - countries with partial WGI data don't qualify
    #
    # task-031: the threshold was ">= 5" under a comment reading "ALL 5 WGI
    # indicators" — a relic of the retired 5-indicator Excel extract.
    # bronze_ingest_wgi fetches SIX (WGI_INDICATORS: CC/GE/PV/RL/RQ/VA) and spec_v1
    # § Data Transformations #3 states coverage rules test against six, so at ">= 5"
    # a country missing an entire governance dimension still counted as fully
    # covered — the flag was structurally unable to report the gap it exists to find.
    #
    # UNAFFECTED BY THE GRAIN CHANGE: task-031 also widened silver_wgi from one row
    # per country-indicator to one row per country-indicator-YEAR. COUNT(DISTINCT
    # indicator_name) collapses that year expansion, so the flag still depends only
    # on how many distinct indicators a country has, not how many years each spans.
    #
    # `value IS NOT NULL` mirrors the EPI check above: a country whose indicators are
    # all empty is not governance-covered. bronze-to-silver drops null-valued rows, so
    # once the API-shaped silver_wgi is in place this filters nothing.
    #
    # MIGRATION GUARD (task-031/task-035 coupling): the API-shaped silver_wgi carrying
    # `value` only exists after bronze-to-silver re-runs against a long-format bronze_wgi
    # — which is blocked until task-035 repoints the pipeline at bronze_ingest_wgi. Until
    # then the live silver_wgi is the retired 3-column shape (country_iso3, country_name,
    # indicator_name) with NO `value` column, and referencing sw.value hard-fails the
    # whole gold notebook here (AnalysisException UNRESOLVED_COLUMN). So the value filter
    # is applied ONLY when the column is present. Post-migration: filter applies, task-031
    # intent preserved. Pre-migration: it is skipped, gold completes, and WGI coverage
    # simply reflects the distinct-indicator count of whatever is in silver_wgi today
    # (which self-corrects once the real values land). Coverage semantics for the target
    # (post-migration) state are unchanged.
    #
    # NOTE — RESOLVED by task-038_3, see DEC-009 § "Deliberate divergence from the Data
    # Gaps coverage rule". This is a COVERAGE flag, deliberately vintage-agnostic: six
    # indicators in ANY year qualify, because it answers "do we hold governance data for
    # this country at all?". WGIᶜ deliberately uses a DIFFERENT rule — the latest year
    # carrying all six dimensions — because a mean mixing 2019's rule-of-law with 2023's
    # voice-and-accountability is not a measurement of any year.
    #
    # The two rules are divergent BY DECISION, not by accident. Do NOT "reconcile" them by
    # weakening either one; this rule stays as-is deliberately.
    _wgi_cols = [c.lower() for c in spark.table(f"{DB}.silver_wgi").columns]
    _wgi_value_filter = "WHERE sw.value IS NOT NULL" if "value" in _wgi_cols else ""
    if not _wgi_value_filter:
        print("  ⚠️  silver_wgi has no `value` column (pre-task-035 schema) — WGI "
              "coverage computed on indicator presence only; re-run after task-035 for "
              "value-filtered coverage.")
    countries_with_wgi = spark.sql(f"""
        SELECT dc.country_key
        FROM {DB}.silver_wgi sw
        JOIN {DB}.gold_dim_country dc ON sw.country_iso3 = UPPER(dc.iso3)
        {_wgi_value_filter}
        GROUP BY dc.country_key
        HAVING COUNT(DISTINCT sw.indicator_name) >= {WGI_REQUIRED_INDICATORS}
    """)

    # 4. Join to find gaps (both EPI and WGI)
    gaps_detail = (
        procurement_countries
        .join(
            spark.table(f"{DB}.gold_dim_country").select(
                "country_key", "country_name_std", "iso3", "region", "is_placeholder"
            ),
            "country_key",
            "left"
        )
        .join(
            countries_with_epi.withColumn("has_epi_score", F.lit(True)),
            "country_key",
            "left"
        )
        .join(
            countries_with_wgi.withColumn("has_wgi_score", F.lit(True)),
            "country_key",
            "left"
        )
        .withColumn("has_epi_score", F.coalesce(F.col("has_epi_score"), F.lit(False)))
        .withColumn("has_wgi_score", F.coalesce(F.col("has_wgi_score"), F.lit(False)))
        .filter(~F.coalesce(F.col("is_placeholder"), F.lit(False)))  # Exclude placeholder countries
    )

    # 5. Calculate spend impact for countries without indicator data
    spend_by_country = spark.sql(f"""
        SELECT
            supplier_hq_country_key as country_key,
            SUM(spend_eur) as total_spend_eur,
            COUNT(*) as transaction_count
        FROM {DB}.fact_procurement
        GROUP BY supplier_hq_country_key
    """)

    # 6. Create the final data gaps table
    data_gaps = (
        gaps_detail
        .join(spend_by_country, "country_key", "left")
        .select(
            "country_key",
            "country_name_std",
            "iso3",
            "region",
            "country_role",
            "has_epi_score",
            "has_wgi_score",
            F.coalesce("total_spend_eur", F.lit(0.0)).alias("spend_eur"),
            F.coalesce("transaction_count", F.lit(0)).alias("transaction_count"),
            F.when(F.col("has_epi_score") & F.col("has_wgi_score"), "Full Coverage")
             .when(F.col("has_epi_score"), "EPI Only")
             .when(F.col("has_wgi_score"), "WGI Only")
             .otherwise("No Coverage").alias("data_status"),
            F.current_timestamp().alias("calculated_at")
        )
        .dropDuplicates(["country_key", "country_role"])
    )

    write_tbl(data_gaps, "gold_data_gaps")

    # 7. Create summary statistics table for KPI cards
    total_countries = data_gaps.select("country_key").distinct().count()

    # EPI coverage stats
    countries_with_epi_count = data_gaps.filter(F.col("has_epi_score")).select("country_key").distinct().count()
    countries_without_epi_count = data_gaps.filter(~F.col("has_epi_score")).select("country_key").distinct().count()

    # WGI coverage stats
    countries_with_wgi_count = data_gaps.filter(F.col("has_wgi_score")).select("country_key").distinct().count()
    countries_without_wgi_count = data_gaps.filter(~F.col("has_wgi_score")).select("country_key").distinct().count()

    # Combined coverage stats
    full_coverage_count = data_gaps.filter(F.col("has_epi_score") & F.col("has_wgi_score")).select("country_key").distinct().count()
    partial_coverage_count = data_gaps.filter(
        (F.col("has_epi_score") & ~F.col("has_wgi_score")) |
        (~F.col("has_epi_score") & F.col("has_wgi_score"))
    ).select("country_key").distinct().count()
    no_coverage_count = data_gaps.filter(~F.col("has_epi_score") & ~F.col("has_wgi_score")).select("country_key").distinct().count()

    # Spend calculations
    spend_full_coverage = data_gaps.filter(F.col("has_epi_score") & F.col("has_wgi_score")).agg(F.sum("spend_eur")).first()[0] or 0
    spend_with_epi = data_gaps.filter(F.col("has_epi_score")).agg(F.sum("spend_eur")).first()[0] or 0
    spend_with_wgi = data_gaps.filter(F.col("has_wgi_score")).agg(F.sum("spend_eur")).first()[0] or 0
    total_spend = data_gaps.agg(F.sum("spend_eur")).first()[0] or 0

    # Coverage percentages
    epi_coverage_pct = (countries_with_epi_count / total_countries * 100) if total_countries > 0 else 0
    wgi_coverage_pct = (countries_with_wgi_count / total_countries * 100) if total_countries > 0 else 0
    full_coverage_pct = (full_coverage_count / total_countries * 100) if total_countries > 0 else 0
    spend_full_coverage_pct = (spend_full_coverage / total_spend * 100) if total_spend > 0 else 0

    # Create summary table
    summary_rows = [
        # EPI Coverage
        ("EPI Coverage", "Countries with EPI Data", float(countries_with_epi_count), f"{countries_with_epi_count} of {total_countries} supplier countries"),
        ("EPI Coverage", "Countries without EPI Data", float(countries_without_epi_count), f"Missing EPI sustainability indicators"),
        ("EPI Coverage", "EPI Country Coverage %", float(epi_coverage_pct), f"Percentage of procurement countries with EPI data"),
        # WGI Coverage
        ("WGI Coverage", "Countries with WGI Data", float(countries_with_wgi_count), f"{countries_with_wgi_count} of {total_countries} supplier countries"),
        ("WGI Coverage", "Countries without WGI Data", float(countries_without_wgi_count), f"Missing WGI governance indicators"),
        ("WGI Coverage", "WGI Country Coverage %", float(wgi_coverage_pct), f"Percentage of procurement countries with WGI data"),
        # Combined Coverage
        ("Combined Coverage", "Full Coverage (EPI + WGI)", float(full_coverage_count), f"Countries with both EPI and WGI data"),
        ("Combined Coverage", "Partial Coverage", float(partial_coverage_count), f"Countries with either EPI or WGI (not both)"),
        ("Combined Coverage", "No Coverage", float(no_coverage_count), f"Countries missing both EPI and WGI data"),
        ("Combined Coverage", "Full Coverage %", float(full_coverage_pct), f"Percentage with complete indicator coverage"),
        # Spend Impact
        ("Spend Impact", "Spend with Full Coverage (EUR)", float(spend_full_coverage), f"Procurement spend with complete indicator data"),
        ("Spend Impact", "Spend with EPI Data (EUR)", float(spend_with_epi), f"Procurement spend where EPI data exists"),
        ("Spend Impact", "Spend with WGI Data (EUR)", float(spend_with_wgi), f"Procurement spend where WGI data exists"),
        ("Spend Impact", "Full Coverage Spend %", float(spend_full_coverage_pct), f"Percentage of spend with complete coverage"),
        # Summary
        ("Summary", "Total Procurement Countries", float(total_countries), f"Distinct countries in procurement data"),
        ("Summary", "Total Procurement Spend (EUR)", float(total_spend), f"Total procurement spend across all countries"),
    ]

    data_gaps_summary = spark.createDataFrame(
        summary_rows,
        ["category", "metric_name", "metric_value", "description"]
    ).withColumn("calculated_at", F.current_timestamp())

    write_tbl(data_gaps_summary, "gold_data_gaps_summary")

    return data_gaps, data_gaps_summary

# Execute data gaps table creation
data_gaps, data_gaps_summary = create_data_gaps_table()

print("\n" + "="*70)
print("DATA GAPS VISIBILITY TABLE CREATED (Task 001)")
print("="*70)

print("\n📊 EPI COVERAGE:")
data_gaps_summary.filter(F.col("category") == "EPI Coverage").show(truncate=False)

print("\n🏛️ WGI COVERAGE:")
data_gaps_summary.filter(F.col("category") == "WGI Coverage").show(truncate=False)

print("\n📈 COMBINED COVERAGE:")
data_gaps_summary.filter(F.col("category") == "Combined Coverage").show(truncate=False)

print("\n💰 SPEND IMPACT:")
data_gaps_summary.filter(F.col("category") == "Spend Impact").show(truncate=False)

print("\n🔍 COUNTRIES BY COVERAGE STATUS:")
(data_gaps
 .select("country_key", "country_name_std", "iso3", "region", "data_status", "has_epi_score", "has_wgi_score", "spend_eur")
 .dropDuplicates(["country_key"])
 .orderBy(F.desc("spend_eur"))
 .show(20, truncate=False))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# # Quality Observability Tables (Task 018)
# Three tables for tracking data quality over time:
# 1. **gold_quality_history** - Append-only metrics per pipeline run (trending)
# 2. **gold_gap_registry** - SCD tracking of unmapped values with lifecycle management
# 3. **gold_low_confidence_audit** - Fuzzy matches below 0.95 confidence for review

# CELL ********************

# =============================================================================
# QUALITY OBSERVABILITY INFRASTRUCTURE
# =============================================================================
# These tables enable:
# - Trending quality metrics over time ("coverage improved from 85% to 100%")
# - Gap lifecycle tracking ("this gap has been open for 3 months")
# - Surfacing fuzzy matches for manual review
# =============================================================================

from delta.tables import DeltaTable

# -----------------------------------------------------------------------------
# 1. CREATE TABLE: gold_quality_history (append-only)
# -----------------------------------------------------------------------------
# Schema matches data_quality_architecture.md
#
# task-040 widened the original 7-column schema by two:
#   status   - the per-check verdict ("pass" / "fail" / "warning") produced by
#              data_quality_checks.log_check_result. This is the field the DQ gate
#              actually reads. "n/a" on rows that are not a single check result
#              (this notebook's coverage/match metrics, aggregate scores).
#   producer - which notebook appended the row. BOTH this notebook and
#              data_quality_checks append to this table on every pipeline run;
#              without a marker their rows are indistinguishable and any
#              DISTINCT refresh_timestamp count over the whole table double-counts.
#
# breach_flag is unchanged and is NOT the gate: it is a threshold flag on the
# metric (for DQ check rows, score < 70). A blocking check can fail the gate while
# scoring 99.9 and never breaching. See data_quality_framework.md
# "Score severity vs. the blocking gate".
spark.sql(f"""
    CREATE TABLE IF NOT EXISTS {DB}.gold_quality_history (
        refresh_timestamp TIMESTAMP,
        layer STRING,
        entity STRING,
        metric_name STRING,
        metric_value DOUBLE,
        threshold DOUBLE,
        breach_flag BOOLEAN,
        status STRING,
        producer STRING
    )
    USING DELTA
    COMMENT 'Append-only quality metrics per pipeline run for trending analysis'
""")
print("✓ Created table: gold_quality_history")

# -----------------------------------------------------------------------------
# 1b. SCHEMA EVOLUTION for a gold_quality_history that predates task-040
# -----------------------------------------------------------------------------
# The table is append-only and already holds history, so it is widened in place
# with an explicit ALTER TABLE rather than recreated or silently mergeSchema'd.
# Rows written before task-040 keep NULL in both new columns and are deliberately
# NOT backfilled: their gate outcome was never recorded and cannot be
# reconstructed. NULL therefore means "pre-task-040 row"; "n/a" means "post-change
# row that is not a per-check result".
#
# ADD COLUMNS appends the new columns at the end, so the writers below can keep
# emitting columns in table order — name- and position-based resolution agree.
#
# An equivalent helper lives in data_quality_checks (that notebook writes to this
# table too and can be run standalone). Keep the two in sync.
# Phase 5 (2026-08-05): this was "silver-to-gold2" and named a notebook that no longer
# exists after the rename. Commit 0fe8763 swept the docs to 'silver_to_gold' but missed
# this literal, so docs and live data disagreed until now. Rows written before the fix
# were retagged in place by a one-off UPDATE — unlike the pre-task-040 NULLs above, this
# value is a provenance label, not a lost measurement, so it is safe to rewrite and the
# distinct-run count at the bottom of this notebook stays contiguous across the rename.
QUALITY_HISTORY_PRODUCER = "silver_to_gold"
QUALITY_HISTORY_ADDED_COLUMNS = [("status", "STRING"), ("producer", "STRING")]


def ensure_quality_history_columns():
    """Idempotently add the task-040 columns to gold_quality_history."""
    if not spark.catalog.tableExists(f"{DB}.gold_quality_history"):
        return  # the first write creates the table with the full 9-column schema
    existing = set(spark.table(f"{DB}.gold_quality_history").columns)
    for col_name, col_type in QUALITY_HISTORY_ADDED_COLUMNS:
        if col_name not in existing:
            spark.sql(
                f"ALTER TABLE {DB}.gold_quality_history ADD COLUMNS ({col_name} {col_type})"
            )
            print(f"  ↑ gold_quality_history: added column {col_name} {col_type} "
                  f"(pre-existing rows keep NULL)")


ensure_quality_history_columns()

# -----------------------------------------------------------------------------
# 2. CREATE TABLE: gold_gap_registry (SCD with MERGE)
# -----------------------------------------------------------------------------
spark.sql(f"""
    CREATE TABLE IF NOT EXISTS {DB}.gold_gap_registry (
        gap_id BIGINT,
        gap_natural_key STRING,
        entity STRING,
        gap_type STRING,
        first_seen TIMESTAMP,
        last_seen TIMESTAMP,
        total_occurrences INT,
        current_status STRING,
        estimated_impact DOUBLE,
        resolution_date TIMESTAMP,
        resolution_notes STRING
    )
    USING DELTA
    COMMENT 'SCD tracking of unmapped values with lifecycle management'
""")
print("✓ Created table: gold_gap_registry")

# -----------------------------------------------------------------------------
# 3. CREATE TABLE: gold_low_confidence_audit
# -----------------------------------------------------------------------------
spark.sql(f"""
    CREATE TABLE IF NOT EXISTS {DB}.gold_low_confidence_audit (
        source_value STRING,
        matched_to STRING,
        confidence DOUBLE,
        entity STRING,
        match_type STRING,
        frequency INT,
        spend_impact DOUBLE,
        last_seen TIMESTAMP
    )
    USING DELTA
    COMMENT 'Fuzzy matches with confidence < 0.95 for manual review'
""")
print("✓ Created table: gold_low_confidence_audit")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Populate Quality History (Append)
# Captures metrics from the current pipeline run

# CELL ********************

def populate_quality_history():
    """
    Append quality metrics from the current pipeline run.
    This builds up historical data for trend analysis.
    """

    # Collect metrics from current run
    metrics_to_insert = []

    # --- Procurement Metrics ---
    proc_stats = spark.sql(f"""
        SELECT
            COUNT(*) as total_records,
            AVG(data_quality_score) as avg_quality_score,
            SUM(CASE WHEN quality_category = 'High' THEN 1 ELSE 0 END) as high_count,
            SUM(CASE WHEN quality_category = 'Unmapped' THEN 1 ELSE 0 END) as unmapped_count,
            SUM(spend_eur) as total_spend
        FROM {DB}.fact_procurement
    """).first()

    if proc_stats.total_records and proc_stats.total_records > 0:
        # Coverage rate (High quality as % of total)
        coverage_rate = (proc_stats.high_count / proc_stats.total_records) * 100
        metrics_to_insert.append(("Gold", "fact_procurement", "coverage_rate", float(coverage_rate), 90.0, coverage_rate < 90.0))

        # Match rate (avg quality score)
        match_rate = (proc_stats.avg_quality_score or 0) * 100
        metrics_to_insert.append(("Gold", "fact_procurement", "match_rate", float(match_rate), 85.0, match_rate < 85.0))

        # Unmapped count
        unmapped_count = float(proc_stats.unmapped_count or 0)
        metrics_to_insert.append(("Gold", "fact_procurement", "unmapped_count", unmapped_count, 10.0, unmapped_count > 10.0))

        # Total records
        metrics_to_insert.append(("Gold", "fact_procurement", "total_records", float(proc_stats.total_records), None, False))

    # --- Supply Share Metrics ---
    supply_stats = spark.sql(f"""
        SELECT
            COUNT(*) as total_records,
            AVG(data_quality_score) as avg_quality_score,
            SUM(CASE WHEN quality_category = 'High' THEN 1 ELSE 0 END) as high_count,
            SUM(CASE WHEN has_unmapped_country OR has_unmapped_material THEN 1 ELSE 0 END) as unmapped_count
        FROM {DB}.fact_supply_share
    """).first()

    if supply_stats.total_records and supply_stats.total_records > 0:
        coverage_rate = (supply_stats.high_count / supply_stats.total_records) * 100
        metrics_to_insert.append(("Gold", "fact_supply_share", "coverage_rate", float(coverage_rate), 90.0, coverage_rate < 90.0))

        match_rate = (supply_stats.avg_quality_score or 0) * 100
        metrics_to_insert.append(("Gold", "fact_supply_share", "match_rate", float(match_rate), 85.0, match_rate < 85.0))

        unmapped_count = float(supply_stats.unmapped_count or 0)
        metrics_to_insert.append(("Gold", "fact_supply_share", "unmapped_count", unmapped_count, 50.0, unmapped_count > 50.0))

    # --- Data Gaps Coverage ---
    gaps_stats = spark.sql(f"""
        SELECT
            COUNT(DISTINCT country_key) as total_countries,
            SUM(CASE WHEN has_epi_score AND has_wgi_score THEN 1 ELSE 0 END) as full_coverage_count,
            SUM(spend_eur) as total_spend
        FROM {DB}.gold_data_gaps
    """).first()

    if gaps_stats.total_countries and gaps_stats.total_countries > 0:
        external_coverage = (gaps_stats.full_coverage_count / gaps_stats.total_countries) * 100
        metrics_to_insert.append(("Gold", "gold_data_gaps", "external_coverage_rate", float(external_coverage), 80.0, external_coverage < 80.0))

    # --- Dimension Health ---
    dim_country_count = spark.table(f"{DB}.gold_dim_country").filter(~F.col("is_placeholder")).count()
    metrics_to_insert.append(("Gold", "gold_dim_country", "active_countries", float(dim_country_count), None, False))

    dim_material_count = spark.table(f"{DB}.gold_dim_material").filter(~F.col("is_placeholder")).count()
    metrics_to_insert.append(("Gold", "gold_dim_material", "active_materials", float(dim_material_count), None, False))

    # Create DataFrame and append
    if metrics_to_insert:
        # task-040: this notebook does not run the DQ check library and has no notion
        # of blocking checks, so it has no per-check verdict to record -> status is
        # "n/a" for every row it writes. `producer` is what makes these rows
        # distinguishable from the ones data_quality_checks appends to the same table
        # in the same pipeline run.
        ensure_quality_history_columns()
        history_df = spark.createDataFrame(
            [(pipeline_run_ts, layer, entity, metric, value, threshold, breach,
              "n/a", QUALITY_HISTORY_PRODUCER)
             for layer, entity, metric, value, threshold, breach in metrics_to_insert],
            ["refresh_timestamp", "layer", "entity", "metric_name", "metric_value", "threshold", "breach_flag",
             "status", "producer"]
        )

        # Append to history table
        history_df.write.format("delta").mode("append").saveAsTable(f"{DB}.gold_quality_history")

        print(f"✓ Appended {len(metrics_to_insert)} metrics to gold_quality_history "
              f"(producer='{QUALITY_HISTORY_PRODUCER}')")
        return history_df

    return None

# Execute quality history population
quality_history_df = populate_quality_history()

# Show what was captured
print("\nQuality metrics captured this run:")
if quality_history_df:
    quality_history_df.show(truncate=False)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Populate Gap Registry (MERGE)
# Uses SCD pattern to track gap lifecycle: new gaps inserted, existing gaps updated

# CELL ********************

def populate_gap_registry():
    """
    MERGE pattern for gap lifecycle tracking:
    1. Existing open gaps: refresh last_seen and total_occurrences
    2. New gaps: Insert with first_seen = now, status = Open
    3. Reopened gaps: a gap the registry had marked Resolved that is unmapped again
       goes back to Open, carrying a note about the reopen (task-027)
    4. Absent gaps: marked Resolved — they are no longer in the unmapped snapshot

    Reads the failed dimension straight off the audit rows: since task-027 both audit
    tables emit one row per (source row x failed dimension) with unmapped_value (the
    value that actually failed to join) and gap_dimension (material | country | stage),
    there is nothing left to infer. The old
    COALESCE(original_material, original_hq_country, original_prod_country) + CASE
    inference is DELETED — it could not tell which join failed and labelled nearly
    every gap gap_type='country' with a material name as the natural key.
    """

    # Collect current unmapped values from the audit tables.
    # gap_dimension (not unmapped_type) becomes gap_type: hq_country and prod_country
    # misses of the same country are ONE gap because one country alias fixes both, and
    # data_quality_architecture.md § Gap Registry keys gap_type on the coarse dimension.
    # Rows whose unmapped_value is NULL are real gaps but have no natural key to alias,
    # so they stay in the audit tables and out of the registry.
    current_gaps_procurement = spark.sql(f"""
        SELECT
            unmapped_value,
            gap_dimension,
            'procurement' as entity,
            COUNT(*) as occurrence_count
        FROM {DB}.gold_unmapped_procurement_audit
        WHERE unmapped_value IS NOT NULL
        GROUP BY 1, 2
    """)

    current_gaps_supply = spark.sql(f"""
        SELECT
            unmapped_value,
            gap_dimension,
            'supply_share' as entity,
            COUNT(*) as occurrence_count
        FROM {DB}.gold_unmapped_supply_audit
        WHERE unmapped_value IS NOT NULL
        GROUP BY 1, 2
    """)

    # Union all current gaps (identical schemas — no allowMissingColumns, so a future
    # schema drift between the two audit tables fails loudly instead of silently nulling)
    current_gaps = (
        current_gaps_procurement
        .unionByName(current_gaps_supply)
        .withColumn("gap_natural_key", F.col("unmapped_value"))
        .withColumn("gap_type", F.col("gap_dimension"))
    )

    current_gap_count = current_gaps.count()

    if current_gap_count == 0:
        print("✓ No unmapped values found - gap registry unchanged")
        return None

    # Check if gap_registry has data
    existing_count = spark.table(f"{DB}.gold_gap_registry").count()

    if existing_count == 0:
        # First run: Insert all as new gaps
        new_gaps = (
            current_gaps
            .withColumn("gap_id", stable_key(["gap_natural_key", "entity", "gap_type"]))
            .withColumn("first_seen", F.lit(pipeline_run_ts))
            .withColumn("last_seen", F.lit(pipeline_run_ts))
            .withColumn("total_occurrences", F.col("occurrence_count").cast("int"))
            .withColumn("current_status", F.lit("Open"))
            .withColumn("estimated_impact", F.lit(None).cast("double"))
            .withColumn("resolution_date", F.lit(None).cast("timestamp"))
            .withColumn("resolution_notes", F.lit(None).cast("string"))
            .select(
                "gap_id", "gap_natural_key", "entity", "gap_type",
                "first_seen", "last_seen", "total_occurrences", "current_status",
                "estimated_impact", "resolution_date", "resolution_notes"
            )
        )

        new_gaps.write.format("delta").mode("append").saveAsTable(f"{DB}.gold_gap_registry")
        print(f"✓ Initialized gap_registry with {current_gap_count} gaps")
        return new_gaps

    else:
        # Subsequent runs: MERGE logic
        # Prepare source data with computed gap_id
        source_gaps = (
            current_gaps
            .withColumn("gap_id", stable_key(["gap_natural_key", "entity", "gap_type"]))
            .withColumn("occurrence_count_int", F.col("occurrence_count").cast("int"))
        )

        # Get Delta table reference
        gap_registry_delta = DeltaTable.forName(spark, f"{DB}.gold_gap_registry")

        source_gaps.createOrReplaceTempView('_current_gaps')

        # Count the gaps this run is about to REOPEN, before the MERGE changes them.
        reopened_count = spark.sql(f"""
            SELECT COUNT(*)
            FROM {DB}.gold_gap_registry r
            JOIN _current_gaps c ON r.gap_id = c.gap_id
            WHERE r.current_status = 'Resolved'
        """).first()[0]

        # --------------------------------------------------------------------------
        # task-027 — total_occurrences semantics: SET-TO-CURRENT, not increment.
        #
        # total_occurrences is "how many source rows exhibit this gap in the most recent
        # run's unmapped snapshot". It is NOT a lifetime cumulative counter.
        #
        # Why: gold_unmapped_procurement_audit / gold_unmapped_supply_audit are FULL
        # SNAPSHOTS — write_tbl overwrites them from all silver data on every run. The old
        #   total_occurrences = target.total_occurrences + source.occurrence_count
        # therefore added the SAME rows again on every run: ten runs over a value occurring
        # ten times reported 100. That measured occurrences x runs, and it also broke the
        # medallion doc's idempotency claim (re-running the pipeline on unchanged data
        # changed gold data).
        #
        # Set-to-current is the only honest reading of a snapshot source, and it is
        # idempotent: two consecutive runs on unchanged data leave the number identical.
        # Gap AGE is already tracked losslessly by first_seen/last_seen, which is what the
        # doc's business questions ("open for 3 months") actually need.
        #
        # data_quality_architecture.md § Gap Registry still calls total_occurrences a
        # "cumulative count" — that description needs correcting (flagged for task-033).
        #
        # CAVEAT (task-029): once a real incremental watermark lands, the procurement audit
        # becomes a snapshot of the WINDOW rather than of all data, and these counts become
        # per-window. Today p_from_date defaults to 1900-01-01, so window == full table.
        # --------------------------------------------------------------------------
        # MERGE: reopen resolved gaps, refresh open ones, insert new ones.
        # Clause order matters — Delta applies the first MATCHED clause whose condition
        # holds, so the reopen branch must come before the plain refresh branch.
        gap_registry_delta.alias("target").merge(
            source_gaps.alias("source"),
            "target.gap_id = source.gap_id"
        ).whenMatchedUpdate(
            # REOPEN (task-027): this gap was marked Resolved but the value is unmapped
            # again. Without this branch the row was matched, skipped by the
            # "!= 'Resolved'" condition, and the regression stayed invisible forever.
            # It goes back to 'Open' rather than to a new 'Reopened' status so it stays
            # inside the documented status set (Open / In Progress / Resolved / Excluded)
            # and keeps flowing through every existing current_status = 'Open' consumer,
            # including the absence sweep below. The reopen is recorded in
            # resolution_notes, and resolution_date is cleared because it no longer holds.
            condition="target.current_status = 'Resolved'",
            set={
                "last_seen": F.lit(pipeline_run_ts),
                "total_occurrences": F.col("source.occurrence_count_int"),
                "current_status": F.lit("Open"),
                "resolution_date": F.lit(None).cast("timestamp"),
                "resolution_notes": F.concat(
                    F.lit(f"Reopened {pipeline_run_ts:%Y-%m-%d %H:%M:%S}: value is unmapped "
                          f"again. Previous resolution: "),
                    F.substring(
                        F.coalesce(F.col("target.resolution_notes"), F.lit("(none recorded)")),
                        1, 180
                    ),
                ),
            }
        ).whenMatchedUpdate(
            # Still Open / In Progress / Excluded — refresh the sighting. current_status is
            # deliberately left alone so a deliberate 'Excluded' is not flipped back.
            condition="target.current_status != 'Resolved'",
            set={
                "last_seen": F.lit(pipeline_run_ts),
                "total_occurrences": F.col("source.occurrence_count_int")
            }
        ).whenNotMatchedInsert(
            values={
                "gap_id": "source.gap_id",
                "gap_natural_key": "source.gap_natural_key",
                "entity": "source.entity",
                "gap_type": "source.gap_type",
                "first_seen": F.lit(pipeline_run_ts),
                "last_seen": F.lit(pipeline_run_ts),
                "total_occurrences": "source.occurrence_count_int",
                "current_status": F.lit("Open"),
                "estimated_impact": F.lit(None).cast("double"),
                "resolution_date": F.lit(None).cast("timestamp"),
                "resolution_notes": F.lit(None).cast("string")
            }
        ).execute()

        # Check for resolved gaps (gaps in registry but NOT in current unmapped).
        # Using LEFT JOIN instead of subquery (Delta Lake doesn't support subqueries in UPDATE)
        #
        # task-027: sample rows seeded by sample_quality_data.Notebook are excluded. They are
        # marked with a '[SAMPLE]' prefix in resolution_notes (that notebook's own convention,
        # and how it cleans itself up) and describe a demo lifecycle that no real run can
        # confirm — without this filter the first real run silently auto-resolved every
        # seeded 'Open' gap and destroyed the demo story. Note: Spark SQL LIKE has no
        # character-class syntax, so '[SAMPLE]%' matches the literal prefix.
        resolved_gaps = spark.sql(f"""
            SELECT r.gap_id
            FROM {DB}.gold_gap_registry r
            LEFT JOIN _current_gaps c ON r.gap_id = c.gap_id
            WHERE r.current_status = 'Open'
              AND c.gap_id IS NULL
              AND COALESCE(r.resolution_notes, '') NOT LIKE '[SAMPLE]%'
        """)

        resolved_gaps.createOrReplaceTempView('_resolved_gaps')

        # Materialise the count BEFORE the MERGE — resolved_gaps is a lazy query over
        # gold_gap_registry filtered on current_status = 'Open', so re-counting it after
        # the MERGE would always return 0.
        auto_resolved_count = resolved_gaps.count()

        # Update resolved gaps using MERGE.
        # task-027: the note states what was actually observed (the value is no longer in
        # the unmapped snapshot). The old text claimed "value now has alias mapping", which
        # this sweep never verified — absence can equally mean the source row disappeared.
        spark.sql(f"""
            MERGE INTO {DB}.gold_gap_registry AS target
            USING _resolved_gaps AS resolved
            ON target.gap_id = resolved.gap_id
            WHEN MATCHED THEN UPDATE SET
                current_status = 'Resolved',
                resolution_date = current_timestamp(),
                resolution_notes = 'Auto-resolved: value no longer appears in the unmapped snapshot'
        """)

        print(f"✓ Gap registry MERGE complete: {current_gap_count} active gaps "
              f"({reopened_count} reopened, {auto_resolved_count} auto-resolved)")
        return source_gaps

# Execute gap registry population
gap_registry_result = populate_gap_registry()

# Show gap registry summary
print("\nGap Registry Summary:")
spark.sql(f"""
    SELECT
        current_status,
        gap_type,
        COUNT(*) as count,
        MIN(first_seen) as oldest_gap,
        MAX(last_seen) as newest_update,
        SUM(total_occurrences) as total_occurrences
    FROM {DB}.gold_gap_registry
    GROUP BY current_status, gap_type
    ORDER BY current_status, gap_type
""").show(truncate=False)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Populate Low Confidence Audit
# Captures matches with confidence < 0.95 for manual review

# CELL ********************

def populate_low_confidence_audit():
    """
    Capture fuzzy matches that succeeded but have confidence < 0.95.
    These are "good enough" matches that should be surfaced for verification.

    Example: "Singpaore" → "Singapore" at 0.85 confidence
    """

    # Get low confidence matches from fact_procurement
    # We need to go back to the raw join to get confidence scores
    low_conf_procurement = spark.sql(f"""
        WITH procurement_with_confidence AS (
            SELECT
                p.materialname as source_value,
                m.material_name_std as matched_to,
                m.match_confidence as confidence,
                'procurement' as entity,
                'material' as match_type,
                COUNT(*) as frequency,
                SUM(p.quantity * p.unitpriceeur) as spend_impact
            FROM {DB}.silver_procurement p
            LEFT JOIN {DB}.gold_dim_material_lookup m
                ON INITCAP(TRIM(p.materialname)) = m.lookup_name
            WHERE m.match_confidence IS NOT NULL
              AND m.match_confidence < 0.95
              AND m.match_confidence > 0  -- Exclude exact matches that somehow got 0
            GROUP BY p.materialname, m.material_name_std, m.match_confidence

            UNION ALL

            SELECT
                p.headquarterscountry as source_value,
                c.country_name_std as matched_to,
                c.match_confidence as confidence,
                'procurement' as entity,
                'hq_country' as match_type,
                COUNT(*) as frequency,
                SUM(p.quantity * p.unitpriceeur) as spend_impact
            FROM {DB}.silver_procurement p
            LEFT JOIN {DB}.gold_dim_country_lookup c
                ON TRIM(p.headquarterscountry) = c.lookup_name
            WHERE c.match_confidence IS NOT NULL
              AND c.match_confidence < 0.95
              AND c.match_confidence > 0
            GROUP BY p.headquarterscountry, c.country_name_std, c.match_confidence

            UNION ALL

            SELECT
                p.productioncountry as source_value,
                c.country_name_std as matched_to,
                c.match_confidence as confidence,
                'procurement' as entity,
                'prod_country' as match_type,
                COUNT(*) as frequency,
                SUM(p.quantity * p.unitpriceeur) as spend_impact
            FROM {DB}.silver_procurement p
            LEFT JOIN {DB}.gold_dim_country_lookup c
                ON TRIM(p.productioncountry) = c.lookup_name
            WHERE c.match_confidence IS NOT NULL
              AND c.match_confidence < 0.95
              AND c.match_confidence > 0
            GROUP BY p.productioncountry, c.country_name_std, c.match_confidence
        )
        SELECT * FROM procurement_with_confidence
        WHERE source_value IS NOT NULL
    """)

    # Get low confidence matches from supply shares.
    #
    # task-038_2 decided to leave this GLOBAL-ONLY. gold_low_confidence_audit groups on
    # (source_value, matched_to, confidence) with no mix discriminator in its contract, so
    # unioning silver_eusupplyshares in would ADD its occurrences to the `frequency` of rows
    # that already exist — silently changing published numbers rather than adding new ones.
    # Widening it needs a supply_mix column on the audit table first; tracked as follow-up.
    low_conf_supply = spark.sql(f"""
        SELECT
            s.material as source_value,
            m.material_name_std as matched_to,
            m.match_confidence as confidence,
            'supply_share' as entity,
            'material' as match_type,
            COUNT(*) as frequency,
            CAST(NULL as DOUBLE) as spend_impact
        FROM {DB}.silver_globalsupplyshares s
        LEFT JOIN {DB}.gold_dim_material_lookup m
            ON INITCAP(TRIM(s.material)) = m.lookup_name
        WHERE m.match_confidence IS NOT NULL
          AND m.match_confidence < 0.95
          AND m.match_confidence > 0
        GROUP BY s.material, m.material_name_std, m.match_confidence

        UNION ALL

        SELECT
            s.country as source_value,
            c.country_name_std as matched_to,
            c.match_confidence as confidence,
            'supply_share' as entity,
            'country' as match_type,
            COUNT(*) as frequency,
            CAST(NULL as DOUBLE) as spend_impact
        FROM {DB}.silver_globalsupplyshares s
        LEFT JOIN {DB}.gold_dim_country_lookup c
            ON TRIM(s.country) = c.lookup_name
        WHERE c.match_confidence IS NOT NULL
          AND c.match_confidence < 0.95
          AND c.match_confidence > 0
        GROUP BY s.country, c.country_name_std, c.match_confidence
    """)

    # Combine all low confidence matches
    all_low_conf = (
        low_conf_procurement
        .unionByName(low_conf_supply, allowMissingColumns=True)
        .withColumn("last_seen", F.lit(pipeline_run_ts))
        .select(
            "source_value", "matched_to", "confidence", "entity",
            "match_type", "frequency", "spend_impact", "last_seen"
        )
    )

    low_conf_count = all_low_conf.count()

    # Overwrite table with current state (point-in-time snapshot).
    # Use overwriteSchema to handle any column type changes.
    #
    # task-027: the write is UNCONDITIONAL. It used to sit inside `if low_conf_count > 0`,
    # so a run that found nothing left the previous run's rows in place — and because this
    # table is in the DirectLake semantic model, a fully-remediated pipeline kept reporting
    # fuzzy matches that no longer existed, with no way to tell the snapshot was stale.
    # An empty DataFrame still carries the full schema, so overwriting with it truncates
    # the table to zero rows without dropping or retyping any column.
    all_low_conf.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{DB}.gold_low_confidence_audit")

    if low_conf_count > 0:
        print(f"✓ Captured {low_conf_count} low confidence matches to gold_low_confidence_audit")
    else:
        print("✓ No low confidence matches found — gold_low_confidence_audit truncated to 0 rows")

    return all_low_conf

# Execute low confidence audit
low_conf_result = populate_low_confidence_audit()

# Show top low confidence matches by spend impact
# (populate_low_confidence_audit now always returns a DataFrame — possibly empty — because
# the snapshot write is unconditional; `is not None` keeps the intent explicit.)
print("\nTop Low Confidence Matches (by frequency):")
if low_conf_result is not None:
    low_conf_result.orderBy(F.desc("frequency")).show(15, truncate=False)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Quality Observability Summary

# CELL ********************

# Print final summary of observability tables
print("\n" + "="*70)
print("QUALITY OBSERVABILITY TABLES - PIPELINE RUN COMPLETE")
print("="*70)

print(f"\nPipeline Run Timestamp: {pipeline_run_ts}")

# Quality History stats
# task-040: every pipeline run writes TWO distinct refresh_timestamps to this table —
# one from this notebook, one from data_quality_checks (each stamps its own
# datetime.now()). COUNT(DISTINCT refresh_timestamp) over the whole table therefore
# reported roughly twice the real number of runs. Count this notebook's own
# timestamps instead: it appends exactly once per pipeline run.
history_count = spark.table(f"{DB}.gold_quality_history").count()
history_runs = spark.sql(f"""
    SELECT COUNT(DISTINCT refresh_timestamp)
    FROM {DB}.gold_quality_history
    WHERE producer = '{QUALITY_HISTORY_PRODUCER}'
""").first()[0]
legacy_timestamps = spark.sql(f"""
    SELECT COUNT(DISTINCT refresh_timestamp)
    FROM {DB}.gold_quality_history
    WHERE producer IS NULL
""").first()[0]
print(f"\n📊 gold_quality_history: {history_count} total metrics across {history_runs} pipeline runs")
if legacy_timestamps:
    print(f"   (+{legacy_timestamps} unattributed pre-task-040 timestamps, excluded from the run count "
          f"because they mix both writers and cannot be attributed)")
print("   Rows by producer:")
spark.sql(f"""
    SELECT COALESCE(producer, '(pre-task-040, unmarked)') AS producer,
           COUNT(DISTINCT refresh_timestamp)              AS distinct_timestamps,
           COUNT(*)                                       AS metric_rows
    FROM {DB}.gold_quality_history
    GROUP BY COALESCE(producer, '(pre-task-040, unmarked)')
    ORDER BY producer
""").show(truncate=False)

# Gap Registry stats
# NOTE: the alias is gap_count, not count — pyspark Row inherits tuple.count, so
# `row.count` returns the bound tuple method and this line printed
# "<built-in method count ...> gaps" instead of a number.
registry_stats = spark.sql(f"""
    SELECT
        current_status,
        COUNT(*) as gap_count
    FROM {DB}.gold_gap_registry
    GROUP BY current_status
""").collect()
print(f"\n🔍 gold_gap_registry:")
for row in registry_stats:
    print(f"   - {row.current_status}: {row.gap_count} gaps")

# Low Confidence Audit stats
low_conf_count = spark.table(f"{DB}.gold_low_confidence_audit").count()
print(f"\n⚠️  gold_low_confidence_audit: {low_conf_count} fuzzy matches for review")

# Actionable insights
print("\n" + "-"*70)
print("ACTIONABLE INSIGHTS")
print("-"*70)

# Show oldest open gaps
print("\n🚨 Oldest Open Gaps (prioritize for alias mapping):")
spark.sql(f"""
    SELECT
        gap_natural_key,
        entity,
        gap_type,
        first_seen,
        total_occurrences,
        DATEDIFF(current_date(), first_seen) as days_open
    FROM {DB}.gold_gap_registry
    WHERE current_status = 'Open'
    ORDER BY first_seen ASC
    LIMIT 10
""").show(truncate=False)

# Show highest impact low confidence matches
print("\n💰 Highest Impact Low Confidence Matches (verify mappings):")
spark.sql(f"""
    SELECT
        source_value,
        matched_to,
        confidence,
        entity,
        match_type,
        frequency,
        spend_impact
    FROM {DB}.gold_low_confidence_audit
    WHERE spend_impact IS NOT NULL
    ORDER BY spend_impact DESC
    LIMIT 10
""").show(truncate=False)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
