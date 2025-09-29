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
from pyspark.sql.types import IntegerType, StringType, FloatType, DateType, StructType, StructField
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

# ## Mapping Tables for Data Standardization

# CELL ********************

# Country name standardization mappings
country_aliases = spark.createDataFrame([
    # Common variations
    ("USA", "United States of America"),
    ("US", "United States of America"),
    ("U.S.", "United States of America"),
    ("U.S.A.", "United States of America"),
    ("United States", "United States of America"),
    ("UK", "United Kingdom"),
    ("GB", "United Kingdom"),
    ("Great Britain", "United Kingdom"),
    ("England", "United Kingdom"),
    ("Czech Republic", "Czechia"),
    ("Slovak Republic", "Slovakia"),
    ("DR Congo", "Democratic Republic of the Congo"),
    ("DRC", "Democratic Republic of the Congo"),
    ("DRC (HQ in South Africa)", "Democratic Republic of the Congo"),
    ("Congo, Dem. Rep.", "Democratic Republic of the Congo"),
    ("UAE", "United Arab Emirates"),
    ("South Korea", "Korea, Rep."),
    ("Republic of Korea", "Korea, Rep."),
    ("North Korea", "Korea, Dem. People's Rep."),
    ("Korea, South", "South Korea"),
    ("Korea, North", "North Korea"),
    ("Russia", "Russian Federation"),
    ("Vietnam", "Viet Nam"),
    ("Laos", "Lao PDR"),
    ("Bolivia", "Bolivia, Plurinational State of"),
    ("Venezuela", "Venezuela, Bolivarian Republic of"),
    ("Tanzania", "Tanzania, United Republic of"),
    ("Moldova", "Moldova, Republic of"),
    ("Macedonia", "North Macedonia"),
    ("Burma", "Myanmar"),
    ("Holland", "Netherlands"),
    ("Ivory Coast", "Côte d'Ivoire"),
    ("Cape Verde", "Cabo Verde"),
    ("Türkiye", "Turkey"),
    ("T�rkiye", "Turkey"),
    ("Turkyie", "Turkey"),
    ("Tï¿½rkiye", "Turkey"),
    ("Korea, South", "Korea, Rep."),
    ("Korea, North", "Korea, Dem. People's Rep."),
    ("Congo, D.R.", "Democratic Republic of the Congo"),
    ("Brasilia", "Brazil"),
    ("Hong Kong", "China"),
    ("French Guiana", "France"),
    ("Kosovo", "Kosovo"),
    ("San Marino", "San Marino"),
    ("Libya", "Libya"),
    ("Syria", "Syrian Arab Republic"),
    ("Yemen", "Yemen, Rep."),
    ("Yemen", "Yemen, Rep."),
    ("Syria", "Syrian Arab Republic"),
    ("Libya", "Libya"),
    ("Kosovo", "Kosovo"),
    ("San Marino", "San Marino"),
    ("Czechia", "Czech Republic"),
    ("Congo", "Congo, Rep."),
    ("Congo, D.R.", "Congo, Dem. Rep."),
    ("Nauru", "Nauru"),
    ("Korea, South", "South Korea"),
    ("Korea, North", "North Korea"),
    ("Congo, D.R.", "Dem. Rep. Congo"),
    ("DRC", "Dem. Rep. Congo"),
    ("DR Congo", "Dem. Rep. Congo"),
    ("DRC (HQ in South Africa)", "Dem. Rep. Congo"),
    ("Congo", "Republic of Congo"),
    ("Czechia", "Czech Republic"),
    # Add more as discovered
], ["alias", "standard_name"])

# Material name standardization mappings
material_aliases = spark.createDataFrame([
    # Case variations
    ("STEEL (High-Tensile)", "Steel (High-Tensile)"),
    ("steel (high-tensile)", "Steel (High-Tensile)"),
    ("Steel (high tensile)", "Steel (High-Tensile)"),
    # Spelling variations
    ("Aluminum", "Aluminium"),
    ("Rare Earths (NDPR)", "Rare Earths (Ndpr)"),
    ("Rare Earth (Ndpr)", "Rare Earths (Ndpr)"),
    # Unit variations in names
    ("Copper (kg)", "Copper"),
    ("Lithium (t)", "Lithium"),
    # Common abbreviations
    ("Electronics (Controllers, Sensors)", "Electronics (controllers, Sensors)"),
    ("Electronic Components", "Electronics (controllers, Sensors)"),
    ("Plastic (ABS)", "Plastic (Abs)"),
    ("Tires (Rubber Compound)", "Tires (rubber Compound)"),
    # Add more as discovered
], ["alias", "standard_material"])

write_tbl(country_aliases, "mapping_country_aliases")
write_tbl(material_aliases, "mapping_material_aliases")

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

## Fixed Country Dimension Logic

# 1. CONSISTENT KEY GENERATION STRATEGY
def generate_country_key(iso3_col, name_col):
    """Generate consistent country keys using ISO3 when available, fallback to name"""
    return F.when(F.col(iso3_col).isNotNull(), 
                  stable_key([iso3_col])
                 ).otherwise(stable_key([name_col]))

# 2. BUILD BASE DIMENSION WITH PROPER SCHEMA
# Load base country data with consistent schema
epi = spark.table(f"{DB}.silver_epi2024results").select(
    F.col("iso").alias("iso3"),
    F.col("code").cast(IntegerType()).alias("iso_numeric"),
    F.col("country").alias("country_name_epi")
).filter(F.col("iso3").isNotNull()).dropDuplicates(["iso3"])

wb = spark.table(f"{DB}.silver_wb").select(
    F.col("country_code").alias("wb_code"),
    F.col("country_name").alias("country_name_wb")
).filter(F.col("wb_code").isNotNull()).dropDuplicates(["wb_code"])

# Build primary dimension from EPI and WB data
dim_country_base = (
    epi.alias("e")
    .join(wb.alias("w"), F.upper(F.col("e.iso3")) == F.upper(F.col("w.wb_code")), "left")
    .select(
        F.coalesce(F.col("e.country_name_epi"), F.col("w.country_name_wb")).alias("country_name_std"),
        F.col("e.iso3"),
        F.col("e.iso_numeric"),
        F.col("w.wb_code")
    )
    .dropDuplicates(["iso3"])
)

# 3. ADD MISSING COUNTRIES WITH PROPER SCHEMA ALIGNMENT
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

# 4. UNION ALL COUNTRIES WITH CONSISTENT KEY GENERATION
all_countries = dim_country_base.unionByName(missing_countries, allowMissingColumns=True)

# Generate consistent keys for all records
dim_country = (
    all_countries
    .withColumn("country_key", generate_country_key("iso3", "country_name_std"))
    .select("country_key", "iso3", "iso_numeric", "wb_code", "country_name_std")
    .dropDuplicates(["country_key"])  # Ensure unique keys
)

# 5. CLEAN UP CONFLICTING ALIASES
country_aliases_clean = spark.createDataFrame([
    # US variations
    ("USA", "United States of America"),
    ("US", "United States of America"),
    ("U.S.", "United States of America"),
    ("U.S.A.", "United States of America"),
    ("United States", "United States of America"),
    
    # UK variations
    ("UK", "United Kingdom"),
    ("GB", "United Kingdom"),
    ("Great Britain", "United Kingdom"),
    ("England", "United Kingdom"),
    
    # Congo variations - FIXED to map to actual dimension names
    ("DR Congo", "Dem. Rep. Congo"),
    ("DRC", "Dem. Rep. Congo"),
    ("DRC (HQ in South Africa)", "Dem. Rep. Congo"),
    ("Congo, Dem. Rep.", "Dem. Rep. Congo"),
    ("Congo, D.R.", "Dem. Rep. Congo"),
    ("Democratic Republic of the Congo", "Dem. Rep. Congo"),
    ("Congo", "Republic of Congo"),
    
    # Korea variations - FIXED to map to actual dimension names
    ("Korea, South", "South Korea"),
    ("Republic of Korea", "South Korea"),
    ("Korea, Rep.", "South Korea"),
    ("Korea, North", "North Korea"),
    ("Korea, Dem. People's Rep.", "North Korea"),
    
    # Turkey variations (including encoding issues)
    ("Türkiye", "Turkey"),
    ("TÃ¼rkiye", "Turkey"),
    ("TÃ¯Â¿Â½rkiye", "Turkey"),
    ("Turkyie", "Turkey"),
    ("Tï¿½rkiye", "Turkey"),
    
    # Czech variations - FIXED
    ("Czechia", "Czech Republic"),
    ("Slovak Republic", "Slovakia"),
    
    # Middle East - FIXED to use actual names in dimension
    ("UAE", "United Arab Emirates"),
    ("Syrian Arab Republic", "Syria"),
    
    # Other mappings
    ("Vietnam", "Viet Nam"),
    ("Laos", "Lao PDR"),
    ("Burma", "Myanmar"),
    ("Bolivia", "Bolivia, Plurinational State of"),
    ("Venezuela", "Venezuela, Bolivarian Republic of"),
    ("Brasilia", "Brazil"),
    ("Tanzania", "Tanzania, United Republic of"),
    ("Ivory Coast", "Côte d'Ivoire"),
    ("Cape Verde", "Cabo Verde"),
    ("Holland", "Netherlands"),
    ("Moldova", "Moldova, Republic of"),
    ("Macedonia", "North Macedonia"),
    ("Russia", "Russian Federation"),
    ("Hong Kong", "China"),
    ("French Guiana", "France"),
], ["alias", "standard_name"])

# 6. BUILD COMPREHENSIVE LOOKUP TABLE
country_lookup = (
    # First, add all standard country names as self-lookups
    dim_country
    .select(
        F.col("country_name_std").alias("lookup_name"),
        "country_key", "iso3", "iso_numeric", "wb_code", "country_name_std"
    )
    # Then add aliases that successfully map to existing countries
    .unionByName(
        country_aliases_clean.alias("ca")
        .join(dim_country.alias("dc"), 
              F.col("ca.standard_name") == F.col("dc.country_name_std"), "inner")
        .select(
            F.col("ca.alias").alias("lookup_name"),
            "dc.country_key", "dc.iso3", "dc.iso_numeric", "dc.wb_code", "dc.country_name_std"
        )
    )
)

# 7. WRITE TABLES
write_tbl(dim_country, "gold_dim_country")
write_tbl(country_lookup, "gold_dim_country_lookup")

# 8. COMPREHENSIVE VALIDATION AND DEBUGGING
print(f"\n{'='*60}")
print("COUNTRY DIMENSION VALIDATION REPORT")
print(f"{'='*60}")

print(f"\nDimension Statistics:")
print(f"  Base countries from EPI/WB: {dim_country_base.count()}")
print(f"  Added missing countries: {missing_countries.count()}")
print(f"  Total countries in dimension: {dim_country.count()}")
print(f"  Total lookup entries (with aliases): {country_lookup.count()}")

# Validate that all manually added countries are present
print(f"\nValidating Missing Countries in Final Dimension:")
missing_country_names = ["North Korea", "Yemen", "Syria", "Libya", "Turkey", "Kosovo", "San Marino", "Nauru"]

for country in missing_country_names:
    exists = dim_country.filter(F.col("country_name_std") == country).count() > 0
    print(f"  {'✓' if exists else '✗'} '{country}' {'found' if exists else 'MISSING!'}")

# Validate alias mappings
print(f"\nValidating Alias Mappings:")
test_aliases = ["Yemen", "Korea, North", "Turkyie", "Kosovo", "DRC (HQ in South Africa)", "Korea, South"]

for alias in test_aliases:
    mapping = country_lookup.filter(F.col("lookup_name") == alias)
    if mapping.count() > 0:
        mapped_to = mapping.first()["country_name_std"]
        print(f"  ✓ '{alias}' → '{mapped_to}'")
    else:
        print(f"  ✗ '{alias}' NOT MAPPED!")

# Check for duplicate country keys
duplicate_keys = (
    dim_country
    .groupBy("country_key")
    .count()
    .filter(F.col("count") > 1)
    .count()
)

if duplicate_keys > 0:
    print(f"\n⚠️  WARNING: {duplicate_keys} duplicate country keys found!")
    (dim_country
     .groupBy("country_key")
     .count()
     .filter(F.col("count") > 1)
     .show())
else:
    print(f"\n✓ No duplicate country keys found")

# Show any unmapped aliases
unmapped_aliases = (
    country_aliases_clean.alias("ca")
    .join(dim_country.alias("dc"), 
          F.col("ca.standard_name") == F.col("dc.country_name_std"), "left")
    .filter(F.col("dc.country_name_std").isNull())
)

unmapped_count = unmapped_aliases.count()
if unmapped_count > 0:
    print(f"\n⚠️  WARNING: {unmapped_count} aliases point to non-existent countries:")
    unmapped_aliases.select("alias", "standard_name").show(truncate=False)
else:
    print(f"\n✓ All aliases map to existing countries")

print(f"\n{'='*60}")
print("Country dimension fix completed!")
print(f"{'='*60}")

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

# Apply alias resolution
materials = (
    materials_raw
    .join(material_aliases, materials_raw.material == material_aliases["alias"], "left")
    .withColumn("material_name_std", 
                F.coalesce(F.col("standard_material"), F.col("material")))
    .select("material_name_std")
    .distinct()
)

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
    .select("material_key","material_name_std","commodity_group","unit_base")
)

# Create extended lookup with aliases - include all needed columns
material_lookup = (
    dim_material
    .select(
        F.col("material_name_std").alias("lookup_name"), 
        "material_key",  # This is already correct in your code
        "material_name_std", 
        "commodity_group"
    )
    .unionByName(
        material_aliases.alias("ma")
        .join(dim_material.alias("dm"), 
              F.col("ma.standard_material") == F.col("dm.material_name_std"), "inner")
        .select(
            F.col("ma.alias").alias("lookup_name"), 
            "dm.material_key", 
            "dm.material_name_std", 
            "dm.commodity_group"
        )
    )
)

write_tbl(dim_material, "gold_dim_material")
write_tbl(material_lookup, "gold_dim_material_lookup")

# Data quality check for unmapped commodity groups
unmapped_materials = dim_material.filter(F.col("commodity_group").isNull())
if unmapped_materials.count() > 0:
    print(f"\n⚠️  WARNING: {unmapped_materials.count()} materials without commodity group:")
    unmapped_materials.select("material_name_std").show(20, truncate=False)
    if FAIL_ON_UNMAPPED:
        raise ValueError("Found materials without commodity groups")

print(f"\nMaterial dimension stats:")
print(f"  Unique materials: {dim_material.count()}")
print(f"  With commodity groups: {dim_material.filter(F.col('commodity_group').isNotNull()).count()}")
print(f"  Lookup entries: {material_lookup.count()}")

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

# WB indicators
wb_vars = (
    spark.table(f"{DB}.silver_wb")
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
    "lookup_name", "country_key", "iso3", "country_name_std"
)
dim_material_lu = spark.table(f"{DB}.gold_dim_material_lookup").select(
    "lookup_name", "material_key", "material_name_std", "commodity_group"
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

# Source data
proc = spark.table(f"{DB}.silver_procurement")

# Extended unit normalization map
unit_norm = F.create_map(*[
    F.lit("kg"), F.lit(1.0),
    F.lit("g"), F.lit(0.001),
    F.lit("mg"), F.lit(0.000001),
    F.lit("t"), F.lit(1000.0),
    F.lit("tonne"), F.lit(1000.0),
    F.lit("mt"), F.lit(1000.0),  # metric ton
    F.lit("lb"), F.lit(0.453592),  # pounds to kg
    F.lit("lbs"), F.lit(0.453592),
    F.lit("oz"), F.lit(0.0283495),  # ounces to kg
    F.lit("ton"), F.lit(907.185),  # US ton to kg
    F.lit("pcs"), F.lit(1.0),  # Pieces - keep as count, no weight conversion
    F.lit("pieces"), F.lit(1.0),  # Alternative spelling
    F.lit("unit"), F.lit(1.0),
    F.lit("units"), F.lit(1.0),
])

# Prepare procurement data
p = (
    proc
    .withColumn("txn_date", F.col("date").cast("date"))
    .withColumn("material_name", F.initcap(F.trim("materialname")))
    .withColumn("hq_country", F.trim("headquarterscountry"))
    .withColumn("prod_country", F.trim("productioncountry"))
).alias("p")

# Alias dimension lookups
d = dim_date_lu.alias("d")
m = dim_material_lu.alias("m")
c_hq = dim_country_lu.alias("c_hq")
c_prod = dim_country_lu.alias("c_prod")

# Build fact with comprehensive joins
fact_procurement_raw = (
    p
    # Date join
    .join(d, F.col("p.txn_date") == F.col("d.date"), "left")
    
    # Material join with alias resolution
    .join(m, F.col("p.material_name") == F.col("m.lookup_name"), "left")
    
    # Country joins with alias resolution
    .join(c_hq, F.col("p.hq_country") == F.col("c_hq.lookup_name"), "left")
    .join(c_prod, F.col("p.prod_country") == F.col("c_prod.lookup_name"), "left")
    
    # Calculate derived fields
    .withColumn("unit_factor", unit_norm[F.lower(F.col("p.unit"))])
    .withColumn("quantity_base",
                F.when(F.col("unit_factor").isNotNull(), 
                       F.col("p.quantity") * F.col("unit_factor"))
                .otherwise(F.col("p.quantity")))  # Keep original if unit unknown
    .withColumn("spend_eur",
                F.col("quantity_base") * F.col("p.unitpriceeur"))
    
    # Select final columns (keeping original column names as requested)
    .select(
        F.col("d.date_key"),
        F.col("m.material_key"),
        F.col("c_hq.country_key").alias("supplier_hq_country_key"),
        F.col("c_prod.country_key").alias("production_country_key"),
        F.col("quantity_base"),
        F.col("p.unitpriceeur").alias("unitprice_eur"),
        F.col("spend_eur"),
        # Keep original values for debugging
        F.col("p.materialname").alias("_orig_material"),
        F.col("p.headquarterscountry").alias("_orig_hq_country"),
        F.col("p.productioncountry").alias("_orig_prod_country"),
        F.col("p.unit").alias("_orig_unit"),
        F.col("unit_factor").alias("_unit_factor")
    )
)

# Comprehensive data quality report
print("\n" + "="*60)
print("PROCUREMENT DATA QUALITY REPORT")
print("="*60)

total = fact_procurement_raw.count()
print(f"\nTotal procurement records: {total:,}")

# Check each foreign key
missing_dates = fact_procurement_raw.filter(F.col("date_key").isNull()).count()
missing_materials = fact_procurement_raw.filter(F.col("material_key").isNull()).count()
missing_hq = fact_procurement_raw.filter(F.col("supplier_hq_country_key").isNull()).count()
missing_prod = fact_procurement_raw.filter(F.col("production_country_key").isNull()).count()
missing_units = fact_procurement_raw.filter(F.col("_unit_factor").isNull()).count()

print(f"\nUnmapped values:")
print(f"  Missing dates: {missing_dates:,} ({100*missing_dates/total:.1f}%)")
print(f"  Missing materials: {missing_materials:,} ({100*missing_materials/total:.1f}%)")
print(f"  Missing HQ countries: {missing_hq:,} ({100*missing_hq/total:.1f}%)")
print(f"  Missing prod countries: {missing_prod:,} ({100*missing_prod/total:.1f}%)")
print(f"  Unknown units: {missing_units:,} ({100*missing_units/total:.1f}%)")

# Show samples of unmapped values for investigation
if missing_materials > 0:
    print("\nUnmapped materials (top 10):")
    (
        fact_procurement_raw
        .filter(F.col("material_key").isNull())
        .groupBy("_orig_material")
        .count()
        .orderBy(F.desc("count"))
        .show(10, truncate=False)
    )

if missing_hq > 0:
    print("\nUnmapped HQ countries (top 10):")
    (
        fact_procurement_raw
        .filter(F.col("supplier_hq_country_key").isNull())
        .groupBy("_orig_hq_country")
        .count()
        .orderBy(F.desc("count"))
        .show(10, truncate=False)
    )

if missing_units > 0:
    print("\nUnknown units:")
    (
        fact_procurement_raw
        .filter(F.col("_unit_factor").isNull())
        .groupBy("_orig_unit")
        .count()
        .orderBy(F.desc("count"))
        .show(10, truncate=False)
    )

# Create clean fact table (remove debug columns)
fact_procurement = fact_procurement_raw.select(
    "date_key", "material_key", "supplier_hq_country_key", 
    "production_country_key", "quantity_base", "unitprice_eur", "spend_eur"
)

# Decision: keep all records or only complete ones?
if FAIL_ON_UNMAPPED and (missing_materials + missing_hq + missing_prod) > total * 0.1:
    raise ValueError(f"More than 10% of records have unmapped values. Review mappings.")

write_tbl(fact_procurement, "fact_procurement")

# Summary statistics
print("\n" + "="*60)
print("PROCUREMENT FACT SUMMARY")
print("="*60)
stats = fact_procurement.agg(
    F.count("*").alias("records"),
    F.sum("spend_eur").alias("total_spend"),
    F.avg("unitprice_eur").alias("avg_price"),
    F.countDistinct("material_key").alias("unique_materials"),
    F.countDistinct("supplier_hq_country_key").alias("unique_suppliers"),
    F.countDistinct("production_country_key").alias("unique_production")
).first()

print(f"Records: {stats.records:,}")
print(f"Total spend: €{stats.total_spend:,.2f}")
print(f"Avg unit price: €{stats.avg_price:.2f}")
print(f"Unique materials: {stats.unique_materials}")
print(f"Unique supplier countries: {stats.unique_suppliers}")
print(f"Unique production countries: {stats.unique_production}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Pipeline Summary and Data Quality Report

# CELL ********************

print("\n" + "="*70)
print("SILVER-TO-GOLD PIPELINE EXECUTION SUMMARY")
print("="*70)

# Record counts for all tables
tables = [
    ("gold_dim_country", "Country Dimension"),
    ("gold_dim_material", "Material Dimension"),
    ("gold_dim_indicator", "Indicator Dimension"),
    ("gold_dim_stage", "Stage Dimension"),
    ("gold_dim_date", "Date Dimension"),
    ("fact_epi_score", "EPI Score Facts"),
    ("fact_supply_share", "Supply Share Facts"),
    ("fact_procurement", "Procurement Facts")
]

print("\nTable Record Counts:")
print("-" * 40)
for table_name, display_name in tables:
    try:
        count = spark.table(f"{DB}.{table_name}").count()
        print(f"{display_name:.<30} {count:>8,}")
    except Exception as e:
        print(f"{display_name:.<30} ERROR: {e}")

# Create data quality summary table
quality_summary = spark.createDataFrame([
    ("Pipeline Run", str(pipeline_run_ts), "INFO"),
    ("Database", DB, "INFO"),
    ("Unmapped Materials", str(missing_materials), "WARNING" if missing_materials > 0 else "OK"),
    ("Unmapped Countries", str(missing_hq + missing_prod), "WARNING" if (missing_hq + missing_prod) > 0 else "OK"),
    ("Unknown Units", str(missing_units), "WARNING" if missing_units > 0 else "OK")
], ["metric", "value", "status"])

write_tbl(quality_summary, "pipeline_quality_summary")

print("\n" + "="*70)
print("Pipeline completed successfully!")
print("Review 'pipeline_quality_summary' table for detailed metrics")
print("="*70)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

def log_data_quality_issue(issue_type, table_name, count, details):
    return spark.createDataFrame(
        [(pipeline_run_ts, issue_type, table_name, count, details)],
        ["run_timestamp", "issue_type", "table_name", "record_count", "details"]
    )

# Collect all issues
dq_issues = [
    log_data_quality_issue("Unmapped Material", "dim_material", 50, "Missing commodity groups"),
    log_data_quality_issue("Unmapped Country", "fact_supply_share", 3410, "NULL country keys"),
    log_data_quality_issue("Unmapped Country", "fact_procurement", 12, "DRC (HQ in South Africa)")
]

# Union and write
quality_log = dq_issues[0]
for issue in dq_issues[1:]:
    quality_log = quality_log.union(issue)
    
write_tbl(quality_log, "data_quality_log")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

existing_countries = spark.table(f"{DB}.gold_dim_country").select("country_name_std").distinct()

# Check for specific problem countries
for country_pattern in ["Korea", "Yemen", "Congo", "Syria", "Libya", "Turkey", "Czech"]:
    matches = existing_countries.filter(F.col("country_name_std").contains(country_pattern))
    print(f"\nCountries containing '{country_pattern}':")
    matches.show(truncate=False)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
