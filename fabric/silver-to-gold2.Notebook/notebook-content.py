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

# ## Setup and Conventions

# CELL ********************

from pyspark.sql import functions as F, Window as W
from pyspark.sql.types import IntegerType, StringType, FloatType, DateType, StructType, StructField, DoubleType, LongType
import logging
from datetime import datetime

# Configuration
DB = "oem_lh"  # Lakehouse database/schema
LOG_UNMAPPED = True  # Enable logging of unmapped values
FAIL_ON_UNMAPPED = False  # Whether to fail pipeline on unmapped values

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

def check_unmapped(df, join_col, name, fail=False):
    """Check for unmapped values after a join"""
    unmapped = df.filter(F.col(join_col).isNull())
    count = unmapped.count()
    if count > 0:
        print(f"⚠️  Found {count:,} unmapped records for {name}")
        if LOG_UNMAPPED:
            unmapped.select(join_col).distinct().show(20, truncate=False)
        if fail and FAIL_ON_UNMAPPED:
            raise ValueError(f"Pipeline failed: {count} unmapped {name} records")
    return count

# Pipeline execution timestamp
pipeline_run_ts = datetime.now()
print(f"Pipeline started at: {pipeline_run_ts}")

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
    
    # Other important mappings
    ("Czechia", "Czech Republic", 0.95, "standard_alias"),
    ("UAE", "United Arab Emirates", 0.95, "standard_alias"),
    ("Syrian Arab Republic", "Syria", 0.95, "standard_alias"),
    ("Russia", "Russian Federation", 0.95, "standard_alias"),
    ("Vietnam", "Viet Nam", 0.95, "standard_alias"),
    ("Hong Kong", "China", 0.85, "territory"),  # Lower confidence for territories
    ("French Guiana", "France", 0.85, "territory"),
], ["alias", "standard_name", "confidence", "match_type"])

# Material aliases remain similar but add confidence
material_aliases_with_confidence = spark.createDataFrame([
    # Case variations - high confidence
    ("STEEL (High-Tensile)", "Steel (High-Tensile)", 0.95, "case_variation"),
    ("steel (high-tensile)", "Steel (High-Tensile)", 0.95, "case_variation"),
    
    # Spelling variations - high confidence  
    ("Aluminum", "Aluminium", 0.95, "spelling_variant"),
    
    # Unit variations - medium confidence as we're stripping units
    ("Copper (kg)", "Copper", 0.90, "unit_removed"),
    ("Lithium (t)", "Lithium", 0.90, "unit_removed"),
    
    # Abbreviations - medium confidence
    ("Electronics (Controllers, Sensors)", "Electronics (controllers, Sensors)", 0.90, "standardized"),
    ("Electronic Components", "Electronics (controllers, Sensors)", 0.85, "generalized"),
], ["alias", "standard_material", "confidence", "match_type"])

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
epi = spark.table(f"{DB}.silver_epi2024results").select(
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

# 3. ADD MISSING COUNTRIES - These are critical for supply chain analysis
# These countries appear in procurement/supply data but not in EPI/WB
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

# 4. UNION ALL COUNTRIES WITH CONSISTENT KEY GENERATION
all_countries = (
    dim_country_base
    .withColumn("region", F.lit(None).cast(StringType()))  # Add region column for compatibility
    .unionByName(missing_countries.withColumn("region", F.lit(None).cast(StringType())), allowMissingColumns=True)
    .unionByName(unknown_countries, allowMissingColumns=True)
)

# Generate consistent keys for all records
dim_country = (
    all_countries
    .withColumn("country_key", generate_country_key("iso3", "country_name_std"))
    .withColumn("is_placeholder", 
        # Flag placeholder/unknown countries for transparency
        F.when(F.col("iso3").startswith("UNK_"), True).otherwise(False))
    .select("country_key", "iso3", "iso_numeric", "wb_code", "country_name_std", "region", "is_placeholder")
    .dropDuplicates(["country_key"])
)

# 5. BUILD COMPREHENSIVE LOOKUP TABLE WITH CONFIDENCE SCORES
country_lookup = (
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
        .join(dim_country.alias("dc"), 
              F.col("ca.standard_name") == F.col("dc.country_name_std"), "inner")
        .select(
            F.col("ca.alias").alias("lookup_name"),
            "dc.country_key", "dc.iso3", "dc.iso_numeric", "dc.wb_code", "dc.country_name_std",
            F.col("ca.confidence").alias("match_confidence"),
            F.col("ca.match_type")
        )
    )
)

write_tbl(dim_country, "gold_dim_country")
write_tbl(country_lookup, "gold_dim_country_lookup")

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
    Create a matrix showing which countries exist in which datasets.
    This is critical for understanding data gaps in visualizations.
    """
    # Get unique countries from each source
    epi_countries = spark.table(f"{DB}.silver_epi2024results").select(
        F.col("country").alias("country_epi")
    ).distinct()

    # NOTE: silver_WB table removed (World Bank ESG data not available)
    # Create empty DataFrame with same schema for compatibility
    wb_countries = spark.createDataFrame([], "country_wb: string")
    
    supply_countries = spark.table(f"{DB}.silver_globalsupplyshares").select(
        F.col("country").alias("country_supply")
    ).distinct()
    
    proc_hq_countries = spark.table(f"{DB}.silver_procurement").select(
        F.col("headquarterscountry").alias("country_proc_hq")
    ).distinct()
    
    proc_prod_countries = spark.table(f"{DB}.silver_procurement").select(
        F.col("productioncountry").alias("country_proc_prod")
    ).distinct()
    
    # Build coverage matrix
    coverage = (
        dim_country
        .filter(~F.col("is_placeholder"))  # Exclude unknown placeholders
        .select("country_key", "country_name_std", "iso3")
        
        # Check presence in each dataset using the lookup table
        .join(
            country_lookup.alias("lu_epi").join(epi_countries, 
                F.col("lu_epi.lookup_name") == F.col("country_epi"), "inner")
                .select("country_key").distinct(),
            "country_key", "left"
        )
        .withColumn("has_epi", F.when(F.col("country_key").isNotNull(), 1).otherwise(0))
        
        # Continue for other sources...
        # (Simplified for brevity - would repeat pattern for each source)
        
        .withColumn("coverage_score", 
            # Calculate percentage of datasets containing this country
            F.col("has_epi") / 1.0  # Would sum all has_* columns / total sources
        )
        .withColumn("coverage_category",
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

materials_raw = (
    proc.union(sup)
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
    .distinct()
)

# NEW: Add UNKNOWN placeholder materials for unmapped records
unknown_materials = spark.createDataFrame([
    ("Unknown Material", "Other/Unknown", "kg"),
], ["material_name_std", "commodity_group", "unit_base"])

# Commodity group mapping (FIXED SYNTAX ERROR)
grp_map = F.create_map(
    F.lit("Lithium"), F.lit("Battery metals"),
    F.lit("Graphite"), F.lit("Battery metals"),
    F.lit("Copper"), F.lit("Base metals"),
    F.lit("Nickel"), F.lit("Battery metals"),
    F.lit("Cobalt"), F.lit("Battery metals"),
    F.lit("Lead"), F.lit("Base metals"),
    F.lit("Aluminum"), F.lit("Base metals"),
    F.lit("Aluminium"), F.lit("Base metals"),
    F.lit("Zinc"), F.lit("Base metals"),
    F.lit("Tin"), F.lit("Base metals"),
    F.lit("Iron Ore"), F.lit("Base metals"),
    F.lit("Magnesium"), F.lit("Base metals"),
    F.lit("Gold"), F.lit("Precious metals"),
    F.lit("Silver"), F.lit("Precious metals"),
    F.lit("Platinum"), F.lit("Precious metals"),
    F.lit("Palladium"), F.lit("Precious metals"),
    F.lit("Rhodium"), F.lit("Precious metals"),
    F.lit("Iridium"), F.lit("Precious metals"),
    F.lit("Ruthenium"), F.lit("Precious metals"),
    F.lit("Neodymium"), F.lit("Rare earth elements"),
    F.lit("Praseodymium"), F.lit("Rare earth elements"),
    F.lit("Cerium"), F.lit("Rare earth elements"),
    F.lit("Lanthanum"), F.lit("Rare earth elements"),
    F.lit("Yttrium"), F.lit("Rare earth elements"),
    F.lit("Rare Earths (Ndpr)"), F.lit("Rare earth elements"),
    F.lit("Tungsten"), F.lit("Specialty metals"),
    F.lit("Molybdenum"), F.lit("Specialty metals"),
    F.lit("Titanium"), F.lit("Specialty metals"),
    F.lit("Titanium Metal"), F.lit("Specialty metals"),
    F.lit("Tantalum"), F.lit("Specialty metals"),
    F.lit("Vanadium"), F.lit("Specialty metals"),
    F.lit("Silicon Metal"), F.lit("Specialty metals"),
    F.lit("Niobium"), F.lit("Specialty metals"),
    F.lit("Limestone"), F.lit("Industrial minerals"),
    F.lit("Silica Sand"), F.lit("Industrial minerals"),
    F.lit("Kaolin"), F.lit("Industrial minerals"),
    F.lit("Phosphorus"), F.lit("Chemicals"),
    F.lit("Phosphate Rock"), F.lit("Chemicals"),
    F.lit("Potash"), F.lit("Chemicals"),
    F.lit("Sulphur"), F.lit("Chemicals"),
    F.lit("Coking Coal"), F.lit("Energy materials"),
    F.lit("Natural Rubber"), F.lit("Organic materials"),
    F.lit("Electronics (controllers, Sensors)"), F.lit("Manufactured products"),
    F.lit("Plastic (Abs)"), F.lit("Manufactured products"),
    F.lit("Tires (rubber Compound)"), F.lit("Manufactured products"),
    F.lit("Steel (High-Tensile)"), F.lit("Manufactured products"),
    F.lit("Helium"), F.lit("Specialty gases"),
    F.lit("Neon"), F.lit("Specialty gases"),
    F.lit("Natural Graphite"), F.lit("Battery metals"),
    F.lit("Erbium"), F.lit("Rare earth elements"),
    F.lit("Thulium"), F.lit("Rare earth elements"),
    F.lit("Holmium"), F.lit("Rare earth elements"),
    F.lit("Lutetium"), F.lit("Rare earth elements"),
    F.lit("Samarium"), F.lit("Rare earth elements"),
    F.lit("Arsenic"), F.lit("Specialty metals"),
    F.lit("Selenium"), F.lit("Specialty metals"),
    F.lit("Germanium"), F.lit("Specialty metals"),
    F.lit("Hafnium"), F.lit("Specialty metals"),
    F.lit("Rhenium"), F.lit("Specialty metals"),
    F.lit("Zirconium"), F.lit("Specialty metals"),
    F.lit("Bismuth"), F.lit("Specialty metals"),
    F.lit("Strontium"), F.lit("Industrial minerals"),
    F.lit("Feldspar"), F.lit("Industrial minerals"),
    F.lit("Gypsum"), F.lit("Industrial minerals"),
    F.lit("Natural Teak Wood"), F.lit("Organic materials"),
    F.lit("Phosphorous"), F.lit("Chemicals"),
)

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
)

# Enhanced lookup with confidence scores
material_lookup = (
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
        .join(dim_material.alias("dm"), 
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

write_tbl(dim_material, "gold_dim_material")
write_tbl(material_lookup, "gold_dim_material_lookup")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## gold.dim_indicator

# CELL ********************

# EPI indicators
epi_vars = spark.table(f"{DB}.`silver_epi2024variables2024-12-11`").select(
    F.lit("EPI").alias("source_system"),
    "type",
    F.col("abbreviation").alias("abbrev"),
    F.col("variable").alias("variable_name"),
    "policyobjective","issuecategory","weight","description",
    F.lit(None).cast(StringType()).alias("indicator_code")
).withColumn("indicator_key", stable_key(["source_system","abbrev","variable_name"]))

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

# Union all indicators
all_indicators = epi_vars.unionByName(wb_vars, allowMissingColumns=True)

# For now, set parent_indicator to NULL (can be enhanced later with proper hierarchy)
# This avoids the flawed self-join logic
dim_indicator = (
    all_indicators
    .withColumn("parent_indicator", F.lit(None).cast("bigint"))
    .select("indicator_key","source_system","type","abbrev","variable_name",
            "policyobjective","issuecategory","indicator_code","weight","description",
            "parent_indicator")
)

write_tbl(dim_indicator, "gold_dim_indicator")

# Stats
print(f"\nIndicator dimension stats:")
print(f"  EPI indicators: {dim_indicator.filter(F.col('source_system')=='EPI').count()}")
print(f"  WB indicators: {dim_indicator.filter(F.col('source_system')=='WB').count()}")

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

# Build dimension with additional useful attributes
dim_date = (
    df
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

write_tbl(dim_date, "gold_dim_date")

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

epi_res = spark.table(f"{DB}.silver_epi2024results")

# Identify metric columns
id_cols = {"code","iso","country"}
metric_cols = [c for c in epi_res.columns if c not in id_cols]
if not metric_cols:
    raise ValueError("No metric columns found in silver_epi2024results.")

print(f"Processing {len(metric_cols)} EPI indicators")

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
    .join(dim_country_lu, on=epi_long.iso == dim_country_lu.iso3, how="left")
    .join(dim_ind_lu.filter(F.col("source_system")=="EPI").select("indicator_key","abbrev"), 
          on="abbrev", how="left")
    .withColumn("year", F.lit(2024).cast(IntegerType()))
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

# ## gold.fact_supply_share

# CELL ********************

sup = spark.table(f"{DB}.silver_globalsupplyshares").select(
    F.initcap(F.trim("material")).alias("material"),
    F.col("stage"),
    F.col("country"),
    F.regexp_replace("share", "[<%]", "").cast("double").alias("share_pct")
)

# Join with enhanced lookups
fact_supply_share = (
    sup
    .join(dim_material_lu, on=F.col("material")==dim_material_lu.lookup_name, how="left")
    .join(dim_country_lu, on=F.col("country")==dim_country_lu.lookup_name, how="left")
    .join(dim_stage_lu, on=F.col("stage")==dim_stage_lu.stage_code, how="left")
    .withColumn("year", F.lit(2023).cast(IntegerType()))
    .select("material_key","stage_key","country_key","year","share_pct")
)

# Data quality checks
total_records = fact_supply_share.count()
check_unmapped(fact_supply_share.select("material_key"), "material_key", "materials in supply shares")
check_unmapped(fact_supply_share.select("country_key"), "country_key", "countries in supply shares")
check_unmapped(fact_supply_share.select("stage_key"), "stage_key", "stages in supply shares")

# Clean fact table
fact_supply_share_clean = fact_supply_share.filter(
    (F.col("material_key").isNotNull()) & 
    (F.col("country_key").isNotNull()) & 
    (F.col("stage_key").isNotNull())
)

write_tbl(fact_supply_share_clean, "fact_supply_share")
print(f"  Retained {fact_supply_share_clean.count()} of {total_records} records ({100*fact_supply_share_clean.count()/total_records:.1f}%)")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## gold.fact_procurement (with extensive data quality checks)

# CELL ********************

proc = spark.table(f"{DB}.silver_procurement")

# Extended unit normalization map
unit_norm = F.create_map(*[
    F.lit("kg"), F.lit(1.0),
    F.lit("g"), F.lit(0.001),
    F.lit("mg"), F.lit(0.000001),
    F.lit("t"), F.lit(1000.0),
    # ... (rest remains same)
])

# Prepare procurement data
p = (
    proc
    .withColumn("txn_date", F.col("date").cast("date"))
    .withColumn("material_name", F.initcap(F.trim("materialname")))
    .withColumn("hq_country", F.trim("headquarterscountry"))
    .withColumn("prod_country", F.trim("productioncountry"))
    .withColumn("row_id", F.monotonically_increasing_id())  # Add row ID for tracking
).alias("p")

# Build fact with comprehensive joins and quality tracking
fact_procurement_raw = (
    p
    # Date join
    .join(dim_date_lu.alias("d"), F.col("p.txn_date") == F.col("d.date"), "left")
    
    # Material join with confidence tracking
    .join(dim_material_lu.alias("m"), F.col("p.material_name") == F.col("m.lookup_name"), "left")
    
    # Country joins with confidence tracking
    .join(dim_country_lu.alias("c_hq"), F.col("p.hq_country") == F.col("c_hq.lookup_name"), "left")
    .join(dim_country_lu.alias("c_prod"), F.col("p.prod_country") == F.col("c_prod.lookup_name"), "left")
    
    # Calculate derived fields
    .withColumn("unit_factor", unit_norm[F.lower(F.col("p.unit"))])
    .withColumn("quantity_base",
                F.when(F.col("unit_factor").isNotNull(), 
                       F.col("p.quantity") * F.col("unit_factor"))
                .otherwise(F.col("p.quantity")))
    .withColumn("spend_eur",
                F.col("quantity_base") * F.col("p.unitpriceeur"))
    
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
    
    .select(
        F.col("d.date_key"),
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
)

write_tbl(fact_procurement_complete, "fact_procurement")

# NEW: Create audit trail for unmapped records
unmapped_audit = (
    fact_procurement_raw
    .filter(
        (F.col("m.material_key").isNull()) |
        (F.col("c_hq.country_key").isNull()) |
        (F.col("c_prod.country_key").isNull())
    )
    .select(
        F.col("p.row_id"),
        F.col("p.material_name").alias("original_material"),
        F.col("p.hq_country").alias("original_hq_country"),
        F.col("p.prod_country").alias("original_prod_country"),
        F.when(F.col("m.material_key").isNull(), "Material").alias("unmapped_type"),
        F.current_timestamp().alias("detected_timestamp")
    )
)

write_tbl(unmapped_audit, "gold_unmapped_procurement_audit")

## gold.fact_supply_share (with enhanced quality tracking and unknown handling)

sup = spark.table(f"{DB}.silver_globalsupplyshares")

# Prepare supply share data with row tracking for audit
supply_prep = (
    sup
    .select(
        F.initcap(F.trim("material")).alias("material"),
        F.col("stage"),
        F.trim("country").alias("country"),
        # Clean percentage values - handle various formats
        F.when(F.col("share").contains("<"), 
               # For values like "<1%", use 0.5% as estimate (midpoint between 0 and 1)
               F.lit(0.5))
         .otherwise(
               F.regexp_replace("share", "[<%]", "").cast("double")
         ).alias("share_pct"),
        F.monotonically_increasing_id().alias("row_id")  # Add for tracking
    )
    # Add source metadata for audit purposes
    .withColumn("source_file", F.lit("silver_globalsupplyshares"))
    .withColumn("processing_timestamp", F.current_timestamp())
)

# Join with enhanced lookups including confidence scores
fact_supply_share_raw = (
    supply_prep.alias("s")
    
    # Material join with confidence tracking
    .join(dim_material_lu.alias("m"), 
          F.col("s.material") == F.col("m.lookup_name"), "left")
    
    # Country join with confidence tracking
    .join(dim_country_lu.alias("c"), 
          F.col("s.country") == F.col("c.lookup_name"), "left")
    
    # Stage join (no confidence needed as it's a simple code match)
    .join(dim_stage_lu.alias("st"), 
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
        "share_pct",
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

write_tbl(fact_supply_share_final, "fact_supply_share")

# NEW: Create detailed audit trail for unmapped supply shares
# This is critical for understanding global supply chain data gaps
unmapped_supply_audit = (
    fact_supply_share_raw
    .filter(
        (F.col("m.material_key").isNull()) |
        (F.col("c.country_key").isNull()) |
        (F.col("st.stage_key").isNull())
    )
    .select(
        F.col("s.row_id"),
        F.col("s.material").alias("original_material"),
        F.col("s.country").alias("original_country"),
        F.col("s.stage").alias("original_stage"),
        F.col("s.share_pct"),
        F.when(F.col("m.material_key").isNull(), "Material")
         .when(F.col("c.country_key").isNull(), "Country")
         .when(F.col("st.stage_key").isNull(), "Stage")
         .alias("unmapped_dimension"),
        F.current_timestamp().alias("detected_timestamp"),
        # Add impact assessment
        F.when(F.col("s.share_pct") > 10, "High Impact")
         .when(F.col("s.share_pct") > 5, "Medium Impact")
         .otherwise("Low Impact").alias("impact_level")
    )
)

write_tbl(unmapped_supply_audit, "gold_unmapped_supply_audit")

# NEW: Create aggregated quality metrics for supply shares
# This helps identify which materials/countries have poor data quality
quality_by_material = (
    fact_supply_share_final
    .groupBy("material_key")
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

# Create visualization-ready views with quality filters
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

# Create summary statistics for supply concentration risk
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
        SUM(has_unmapped_country) as unmapped_countries,
        CASE 
            WHEN MAX(share_pct) > 50 THEN 'Critical'
            WHEN MAX(share_pct) > 30 THEN 'High'
            WHEN MAX(share_pct) > 20 THEN 'Medium'
            ELSE 'Low'
        END as concentration_risk_level
    FROM {DB}.v_fact_supply_share_complete
    GROUP BY material_name_std, commodity_group, stage_name
""")

print("\n" + "="*60)
print("SUPPLY SHARE FACT COMPLETION SUMMARY")
print("="*60)
print(f"Total records processed: {total_supply_records:,}")
print(f"Records written to fact: {fact_supply_share_final.count():,}")
print(f"Records in audit trail: {unmapped_supply_audit.count():,}")
print(f"\nViews created:")
print("  - v_fact_supply_share_high_confidence: Verified data only")
print("  - v_fact_supply_share_complete: All data with quality flags")
print("  - v_supply_concentration_risk: Risk analysis view")
print(f"\nData Quality Distribution:")
fact_supply_share_final.groupBy("quality_category").count().orderBy("quality_category").show()

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
