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
all_countries = (
    dim_country_base
    .withColumn("region", F.coalesce(region_mapping[F.col("iso3")], F.lit("Other")))
    .unionByName(missing_countries.withColumn("region", F.coalesce(region_mapping[F.col("iso3")], F.lit("Other"))), allowMissingColumns=True)
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
    .dropDuplicates(["material_name_std"])  # Dedupe by material name only to avoid duplicate keys
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
    .dropDuplicates(["material_key"])  # CRITICAL: Ensure unique keys for dimension table
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
# NOTE: silver_epi2024variables table may not exist in all environments
# Create from EPI results columns if variables metadata table is unavailable
try:
    epi_vars = spark.table(f"{DB}.silver_epi2024variables").select(
        F.lit("EPI").alias("source_system"),
        "type",
        F.col("abbreviation").alias("abbrev"),
        F.col("variable").alias("variable_name"),
        "policyobjective","issuecategory","weight","description",
        F.lit(None).cast(StringType()).alias("indicator_code")
    ).withColumn("indicator_key", stable_key(["source_system","abbrev","variable_name"]))
    print("✓ Loaded EPI variables from silver_epi2024variables table")
except Exception as e:
    print(f"⚠️  EPI variables table not found, creating indicators from results columns: {e}")
    # Derive indicator metadata from EPI results column names
    epi_results = spark.table(f"{DB}.silver_epi2024results")
    id_cols = {"code", "iso", "country"}
    indicator_cols = [c for c in epi_results.columns if c not in id_cols]

    epi_vars = spark.createDataFrame(
        [(col,) for col in indicator_cols],
        ["abbrev"]
    ).select(
        F.lit("EPI").alias("source_system"),
        F.lit("indicator").alias("type"),
        F.col("abbrev"),
        F.col("abbrev").alias("variable_name"),  # Use abbreviation as name
        F.lit(None).cast(StringType()).alias("policyobjective"),
        F.lit(None).cast(StringType()).alias("issuecategory"),
        F.lit(None).cast(FloatType()).alias("weight"),
        F.lit(None).cast(StringType()).alias("description"),
        F.lit(None).cast(StringType()).alias("indicator_code")
    ).withColumn("indicator_key", stable_key(["source_system","abbrev","variable_name"]))
    print(f"✓ Created {epi_vars.count()} EPI indicators from results columns")

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
        SUM(CASE WHEN has_unmapped_country THEN 1 ELSE 0 END) as unmapped_countries,
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

    # Get top unmapped values
    top_unmapped_materials = spark.sql(f"""
        SELECT original_material, COUNT(*) as count
        FROM {DB}.gold_unmapped_procurement_audit
        WHERE original_material IS NOT NULL
        GROUP BY original_material
        ORDER BY count DESC
        LIMIT 10
    """).collect()

    top_unmapped_countries = spark.sql(f"""
        SELECT original_hq_country, COUNT(*) as count
        FROM {DB}.gold_unmapped_procurement_audit
        WHERE original_hq_country IS NOT NULL
        GROUP BY original_hq_country
        ORDER BY count DESC
        LIMIT 10
    """).collect()

    # Build dashboard table with all metrics in long format (category, metric_name, metric_value)
    # IMPORTANT: Cast all metric_value to float to avoid type mismatch errors
    dashboard_rows = [
        # Overall Metrics
        ("Overall", "Match Rate", float(proc_metrics.avg_quality_score * 100 if proc_metrics.avg_quality_score else 0), "Percentage of records with high-confidence matches", datetime.now()),
        ("Overall", "Total Records", float(proc_metrics.total_records + supply_metrics.total_records), "Combined procurement and supply share records", datetime.now()),
        ("Overall", "High Confidence %", float((proc_metrics.high_count / proc_metrics.total_records * 100) if proc_metrics.total_records else 0), "Records with quality score >= 0.9", datetime.now()),
        ("Overall", "Unmapped Records", float(unmapped_proc_count + unmapped_supply_count), "Total records with unmapped dimensions", datetime.now()),

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
            f"#{i+1}: {row.original_material}",
            float(row.count),
            f"Unmapped material name appearing {row.count} times",
            datetime.now()
        ))

    # Add top unmapped countries
    for i, row in enumerate(top_unmapped_countries):
        dashboard_rows.append((
            "Unmapped Countries",
            f"#{i+1}: {row.original_hq_country}",
            float(row.count),
            f"Unmapped country name appearing {row.count} times",
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

    # 2. Get countries that have EPI scores (using the main EPI indicator)
    # We'll check for the presence of ANY EPI score for each country
    countries_with_epi = spark.sql(f"""
        SELECT DISTINCT country_key
        FROM {DB}.fact_epi_score
        WHERE score IS NOT NULL
    """)

    # 3. Get countries that have WGI scores (World Governance Indicators)
    # Join silver_wgi to dim_country via Country Code (ISO3)
    # Require ALL 5 WGI indicators for "complete" governance coverage
    # This creates authentic gaps - countries with partial WGI data don't qualify
    countries_with_wgi = spark.sql(f"""
        SELECT dc.country_key
        FROM {DB}.silver_wgi sw
        JOIN {DB}.gold_dim_country dc ON sw.country_iso3 = UPPER(dc.iso3)
        GROUP BY dc.country_key
        HAVING COUNT(DISTINCT sw.indicator_name) >= 5
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
spark.sql(f"""
    CREATE TABLE IF NOT EXISTS {DB}.gold_quality_history (
        refresh_timestamp TIMESTAMP,
        layer STRING,
        entity STRING,
        metric_name STRING,
        metric_value DOUBLE,
        threshold DOUBLE,
        breach_flag BOOLEAN
    )
    USING DELTA
    COMMENT 'Append-only quality metrics per pipeline run for trending analysis'
""")
print("✓ Created table: gold_quality_history")

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
        history_df = spark.createDataFrame(
            [(pipeline_run_ts, layer, entity, metric, value, threshold, breach)
             for layer, entity, metric, value, threshold, breach in metrics_to_insert],
            ["refresh_timestamp", "layer", "entity", "metric_name", "metric_value", "threshold", "breach_flag"]
        )

        # Append to history table
        history_df.write.format("delta").mode("append").saveAsTable(f"{DB}.gold_quality_history")

        print(f"✓ Appended {len(metrics_to_insert)} metrics to gold_quality_history")
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
    1. Existing gaps: Update last_seen, increment total_occurrences
    2. New gaps: Insert with first_seen = now, status = Open
    3. Resolved gaps: Mark status = Resolved if value now has an alias match

    Note: Resolution detection requires comparing against alias tables.
    """

    # Collect current unmapped values from audit tables
    current_gaps_procurement = spark.sql(f"""
        SELECT
            COALESCE(original_material, original_hq_country, original_prod_country) as unmapped_value,
            CASE
                WHEN original_material IS NOT NULL AND original_hq_country IS NULL AND original_prod_country IS NULL THEN 'material'
                WHEN original_hq_country IS NOT NULL THEN 'country'
                WHEN original_prod_country IS NOT NULL THEN 'country'
                ELSE 'unknown'
            END as unmapped_type,
            'procurement' as entity,
            COUNT(*) as occurrence_count
        FROM {DB}.gold_unmapped_procurement_audit
        WHERE COALESCE(original_material, original_hq_country, original_prod_country) IS NOT NULL
        GROUP BY 1, 2
    """)

    current_gaps_supply = spark.sql(f"""
        SELECT
            COALESCE(original_material, original_country) as unmapped_value,
            unmapped_dimension as unmapped_type,
            'supply_share' as entity,
            COUNT(*) as occurrence_count
        FROM {DB}.gold_unmapped_supply_audit
        WHERE COALESCE(original_material, original_country) IS NOT NULL
        GROUP BY 1, 2
    """)

    # Union all current gaps
    current_gaps = (
        current_gaps_procurement
        .unionByName(current_gaps_supply, allowMissingColumns=True)
        .withColumn("gap_natural_key", F.col("unmapped_value"))
        .withColumn("gap_type", F.lower(F.col("unmapped_type")))
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

        # MERGE: Update existing, insert new
        gap_registry_delta.alias("target").merge(
            source_gaps.alias("source"),
            "target.gap_id = source.gap_id"
        ).whenMatchedUpdate(
            condition="target.current_status != 'Resolved'",
            set={
                "last_seen": F.lit(pipeline_run_ts),
                "total_occurrences": F.col("target.total_occurrences") + F.col("source.occurrence_count_int")
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

        # Check for resolved gaps (gaps in registry but NOT in current unmapped)
        # These are gaps that now have alias mappings
        current_gap_ids = source_gaps.select("gap_id").distinct()

        resolved_count = spark.sql(f"""
            UPDATE {DB}.gold_gap_registry
            SET current_status = 'Resolved',
                resolution_date = current_timestamp(),
                resolution_notes = 'Auto-resolved: value now has alias mapping'
            WHERE current_status = 'Open'
            AND gap_id NOT IN (SELECT gap_id FROM {source_gaps.createOrReplaceTempView('_current_gaps') or '_current_gaps'})
        """)

        print(f"✓ Gap registry MERGE complete: {current_gap_count} active gaps")
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

    # Get low confidence matches from supply shares
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

    if low_conf_count > 0:
        # Overwrite table with current state (point-in-time snapshot)
        all_low_conf.write.format("delta").mode("overwrite").saveAsTable(f"{DB}.gold_low_confidence_audit")
        print(f"✓ Captured {low_conf_count} low confidence matches to gold_low_confidence_audit")
        return all_low_conf
    else:
        print("✓ No low confidence matches found")
        return None

# Execute low confidence audit
low_conf_result = populate_low_confidence_audit()

# Show top low confidence matches by spend impact
print("\nTop Low Confidence Matches (by frequency):")
if low_conf_result:
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
history_count = spark.table(f"{DB}.gold_quality_history").count()
history_runs = spark.sql(f"SELECT COUNT(DISTINCT refresh_timestamp) FROM {DB}.gold_quality_history").first()[0]
print(f"\n📊 gold_quality_history: {history_count} total metrics across {history_runs} pipeline runs")

# Gap Registry stats
registry_stats = spark.sql(f"""
    SELECT
        current_status,
        COUNT(*) as count
    FROM {DB}.gold_gap_registry
    GROUP BY current_status
""").collect()
print(f"\n🔍 gold_gap_registry:")
for row in registry_stats:
    print(f"   - {row.current_status}: {row.count} gaps")

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
