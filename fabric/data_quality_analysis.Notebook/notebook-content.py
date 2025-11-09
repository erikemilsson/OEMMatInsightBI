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
# META       "default_lakehouse_workspace_id": "99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9"
# META     }
# META   }
# META }

# MARKDOWN ********************

# # Data Quality Analysis Dashboard
# 
# **Purpose:** Comprehensive data quality monitoring and alias resolution analysis
# 
# This notebook surfaces all data quality metrics, unmapped values, and match confidence scores
# to provide transparency into the quality and assumptions of the data pipeline.
# 
# **Last Updated:** Generated automatically on pipeline run

# CELL ********************

from pyspark.sql import functions as F, Window as W
from pyspark.sql.types import *
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime

# Configuration
DB = "oem_lh"
spark.sql(f"USE {DB}")

print(f"{'='*70}")
print(f"DATA QUALITY ANALYSIS DASHBOARD")
print(f"{'='*70}")
print(f"Analysis Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Database: {DB}")
print(f"{'='*70}\n")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 1. Executive Summary - Overall Data Quality

# CELL ********************

# Load quality metrics
fact_proc = spark.table(f"{DB}.fact_procurement")
fact_supply = spark.table(f"{DB}.fact_supply_share")

# Calculate summary statistics
total_proc_records = fact_proc.count()
high_quality_proc = fact_proc.filter(F.col("quality_category") == "High").count()
proc_quality_pct = (high_quality_proc / total_proc_records * 100) if total_proc_records > 0 else 0

total_supply_records = fact_supply.count()
high_quality_supply = fact_supply.filter(F.col("quality_category") == "High").count()
supply_quality_pct = (high_quality_supply / total_supply_records * 100) if total_supply_records > 0 else 0

avg_proc_score = fact_proc.agg(F.avg("data_quality_score")).first()[0]
avg_supply_score = fact_supply.agg(F.avg("data_quality_score")).first()[0]

print(f"\n{'='*70}")
print("EXECUTIVE SUMMARY - DATA QUALITY METRICS")
print(f"{'='*70}\n")

print("Fact Procurement:")
print(f"  Total Records: {total_proc_records:,}")
print(f"  High Quality Records: {high_quality_proc:,} ({proc_quality_pct:.1f}%)")
print(f"  Average Quality Score: {avg_proc_score:.3f}")

print(f"\nFact Supply Share:")
print(f"  Total Records: {total_supply_records:,}")
print(f"  High Quality Records: {high_quality_supply:,} ({supply_quality_pct:.1f}%)")
print(f"  Average Quality Score: {avg_supply_score:.3f}")

# Overall assessment
overall_quality = (proc_quality_pct + supply_quality_pct) / 2
print(f"\n{'='*70}")
print(f"OVERALL QUALITY RATING: {overall_quality:.1f}% High Quality Records")

if overall_quality >= 90:
    assessment = "✅ EXCELLENT - Very high data quality"
elif overall_quality >= 75:
    assessment = "✓ GOOD - Acceptable quality with minor issues"
elif overall_quality >= 60:
    assessment = "⚠️  FAIR - Some quality issues need attention"
else:
    assessment = "❌ NEEDS IMPROVEMENT - Significant quality issues"

print(f"Assessment: {assessment}")
print(f"{'='*70}\n")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 2. Quality Distribution by Category

# CELL ********************

print(f"\n{'='*70}")
print("QUALITY DISTRIBUTION - FACT PROCUREMENT")
print(f"{'='*70}\n")

proc_quality_dist = (
    fact_proc
    .groupBy("quality_category")
    .agg(
        F.count("*").alias("record_count"),
        F.sum("spend_eur").alias("total_spend_eur")
    )
    .withColumn("pct_of_records",
                F.col("record_count") / F.lit(total_proc_records) * 100)
    .orderBy(F.desc("record_count"))
)

proc_quality_dist.show(truncate=False)

# Detailed quality score distribution
print(f"\n{'='*70}")
print("QUALITY SCORE DISTRIBUTION (PROCUREMENT)")
print(f"{'='*70}\n")

proc_score_bands = fact_proc.select(
    F.when(F.col("data_quality_score") >= 0.95, "0.95-1.00 (Excellent)")
     .when(F.col("data_quality_score") >= 0.90, "0.90-0.95 (Very Good)")
     .when(F.col("data_quality_score") >= 0.80, "0.80-0.90 (Good)")
     .when(F.col("data_quality_score") >= 0.70, "0.70-0.80 (Fair)")
     .when(F.col("data_quality_score") >= 0.50, "0.50-0.70 (Low)")
     .otherwise("< 0.50 (Poor)").alias("score_band")
).groupBy("score_band").count().orderBy(F.desc("count"))

proc_score_bands.show(truncate=False)

# Supply share quality distribution
print(f"\n{'='*70}")
print("QUALITY DISTRIBUTION - FACT SUPPLY SHARE")
print(f"{'='*70}\n")

supply_quality_dist = (
    fact_supply
    .groupBy("quality_category")
    .agg(
        F.count("*").alias("record_count"),
        F.sum("share_pct").alias("total_share_pct")
    )
    .withColumn("pct_of_records",
                F.col("record_count") / F.lit(total_supply_records) * 100)
    .orderBy(F.desc("record_count"))
)

supply_quality_dist.show(truncate=False)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 3. Unmapped Values Analysis - Critical Issues

# CELL ********************

print(f"\n{'='*70}")
print("UNMAPPED VALUES - PROCUREMENT DATA")
print(f"{'='*70}\n")

# Load audit tables
unmapped_proc = spark.table(f"{DB}.gold_unmapped_procurement_audit")

total_unmapped_proc = unmapped_proc.count()
print(f"Total Unmapped Procurement Records: {total_unmapped_proc:,}")

if total_unmapped_proc > 0:
    print("\nTop Unmapped Materials:")
    (unmapped_proc
     .filter(F.col("unmapped_type") == "Material")
     .groupBy("original_material")
     .count()
     .orderBy(F.desc("count"))
     .limit(15)
     .show(truncate=False))

    print("\nTop Unmapped HQ Countries:")
    (unmapped_proc
     .filter(F.col("original_hq_country").isNotNull())
     .groupBy("original_hq_country")
     .count()
     .orderBy(F.desc("count"))
     .limit(15)
     .show(truncate=False))

    print("\nTop Unmapped Production Countries:")
    (unmapped_proc
     .filter(F.col("original_prod_country").isNotNull())
     .groupBy("original_prod_country")
     .count()
     .orderBy(F.desc("count"))
     .limit(15)
     .show(truncate=False))
else:
    print("✅ No unmapped procurement records found!")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

print(f"\n{'='*70}")
print("UNMAPPED VALUES - SUPPLY SHARE DATA (WITH IMPACT ANALYSIS)")
print(f"{'='*70}\n")

unmapped_supply = spark.table(f"{DB}.gold_unmapped_supply_audit")

total_unmapped_supply = unmapped_supply.count()
print(f"Total Unmapped Supply Share Records: {total_unmapped_supply:,}")

if total_unmapped_supply > 0:
    print("\n⚠️  CRITICAL: Unmapped Materials by Impact")
    print("(Higher share % = more critical to resolve)\n")
    (unmapped_supply
     .filter(F.col("unmapped_dimension") == "Material")
     .groupBy("original_material", "impact_level")
     .agg(
         F.count("*").alias("record_count"),
         F.sum("share_pct").alias("total_share_pct"),
         F.max("share_pct").alias("max_share_pct")
     )
     .orderBy(F.desc("total_share_pct"))
     .limit(20)
     .show(truncate=False))

    print("\n⚠️  CRITICAL: Unmapped Countries by Impact")
    print("(Countries with high supply share that need mapping)\n")
    (unmapped_supply
     .filter(F.col("unmapped_dimension") == "Country")
     .groupBy("original_country", "original_stage", "impact_level")
     .agg(
         F.count("*").alias("record_count"),
         F.sum("share_pct").alias("total_share_pct"),
         F.max("share_pct").alias("max_share_pct")
     )
     .orderBy(F.desc("total_share_pct"))
     .limit(20)
     .show(truncate=False))

    # Impact summary
    print("\nImpact Level Distribution:")
    (unmapped_supply
     .groupBy("impact_level", "unmapped_dimension")
     .count()
     .orderBy("unmapped_dimension", F.desc("count"))
     .show(truncate=False))
else:
    print("✅ No unmapped supply share records found!")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 4. Alias Resolution Statistics

# CELL ********************

print(f"\n{'='*70}")
print("ALIAS RESOLUTION STATISTICS - COUNTRIES")
print(f"{'='*70}\n")

country_aliases = spark.table(f"{DB}.mapping_country_aliases_confidence")
dim_country = spark.table(f"{DB}.gold_dim_country")

total_countries = dim_country.filter(~F.col("is_placeholder")).count()
total_country_aliases = country_aliases.count()
unique_standards = country_aliases.select("standard_name").distinct().count()

print(f"Total Real Countries: {total_countries:,}")
print(f"Total Country Aliases Defined: {total_country_aliases:,}")
print(f"Unique Standard Names: {unique_standards:,}")
print(f"Average Aliases per Country: {total_country_aliases/unique_standards:.1f}")

print("\nAlias Match Type Distribution:")
(country_aliases
 .groupBy("match_type")
 .agg(
     F.count("*").alias("alias_count"),
     F.avg("confidence").alias("avg_confidence"),
     F.min("confidence").alias("min_confidence"),
     F.max("confidence").alias("max_confidence")
 )
 .orderBy(F.desc("alias_count"))
 .show(truncate=False))

print("\nConfidence Score Distribution:")
(country_aliases
 .select(
     F.when(F.col("confidence") >= 0.95, "0.95-1.00 (Excellent)")
      .when(F.col("confidence") >= 0.90, "0.90-0.95 (Very Good)")
      .when(F.col("confidence") >= 0.85, "0.85-0.90 (Good)")
      .when(F.col("confidence") >= 0.80, "0.80-0.85 (Fair)")
      .otherwise("< 0.80 (Low)").alias("confidence_band")
 )
 .groupBy("confidence_band")
 .count()
 .orderBy(F.desc("count"))
 .show(truncate=False))

print("\nTop 20 Countries by Number of Aliases:")
(country_aliases
 .groupBy("standard_name")
 .count()
 .orderBy(F.desc("count"))
 .limit(20)
 .show(truncate=False))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

print(f"\n{'='*70}")
print("ALIAS RESOLUTION STATISTICS - MATERIALS")
print(f"{'='*70}\n")

material_aliases = spark.table(f"{DB}.mapping_material_aliases_confidence")
dim_material = spark.table(f"{DB}.gold_dim_material")

total_materials = dim_material.filter(~F.col("is_placeholder")).count()
total_material_aliases = material_aliases.count()
unique_material_standards = material_aliases.select("standard_material").distinct().count()

print(f"Total Real Materials: {total_materials:,}")
print(f"Total Material Aliases Defined: {total_material_aliases:,}")
print(f"Unique Standard Materials: {unique_material_standards:,}")
print(f"Average Aliases per Material: {total_material_aliases/unique_material_standards:.1f}")

print("\nAlias Match Type Distribution:")
(material_aliases
 .groupBy("match_type")
 .agg(
     F.count("*").alias("alias_count"),
     F.avg("confidence").alias("avg_confidence")
 )
 .orderBy(F.desc("alias_count"))
 .show(truncate=False))

print("\nMaterials with Most Aliases:")
(material_aliases
 .groupBy("standard_material")
 .count()
 .orderBy(F.desc("count"))
 .show(truncate=False))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 5. Country Coverage Matrix Analysis

# CELL ********************

print(f"\n{'='*70}")
print("COUNTRY COVERAGE MATRIX - Data Source Analysis")
print(f"{'='*70}\n")

# Load silver tables to check coverage
epi_countries = (spark.table(f"{DB}.silver_epi2024results")
                .select(F.col("country").alias("country_name"))
                .distinct())

wb_countries = (spark.table(f"{DB}.silver_wb")
               .select(F.col("country_name"))
               .distinct())

supply_countries = (spark.table(f"{DB}.silver_globalsupplyshares")
                   .select(F.trim("country").alias("country_name"))
                   .distinct())

proc_hq = (spark.table(f"{DB}.silver_procurement")
          .select(F.trim("headquarterscountry").alias("country_name"))
          .distinct())

proc_prod = (spark.table(f"{DB}.silver_procurement")
            .select(F.trim("productioncountry").alias("country_name"))
            .distinct())

print(f"Countries in EPI Dataset: {epi_countries.count():,}")
print(f"Countries in World Bank Dataset: {wb_countries.count():,}")
print(f"Countries in Supply Share Data: {supply_countries.count():,}")
print(f"Countries in Procurement (HQ): {proc_hq.count():,}")
print(f"Countries in Procurement (Production): {proc_prod.count():,}")

# Find countries in procurement but not in ESG datasets
print(f"\n{'='*70}")
print("COVERAGE GAPS - Countries in Procurement but Missing ESG Data")
print(f"{'='*70}\n")

all_proc_countries = proc_hq.union(proc_prod).distinct()
epi_wb_countries = epi_countries.union(wb_countries).distinct()

# Use country lookup to find mapped countries
country_lookup = spark.table(f"{DB}.gold_dim_country_lookup")

proc_with_lookup = (
    all_proc_countries
    .join(country_lookup,
          all_proc_countries.country_name == country_lookup.lookup_name,
          "left")
)

# Check which ones don't have ESG data
proc_no_esg = (
    proc_with_lookup
    .join(epi_wb_countries,
          proc_with_lookup.country_name_std == epi_wb_countries.country_name,
          "left_anti")
    .select("country_name", "country_name_std", "match_confidence")
    .distinct()
)

gap_count = proc_no_esg.count()
print(f"Countries Used in Procurement without ESG Coverage: {gap_count}")

if gap_count > 0:
    print("\n⚠️  These countries appear in procurement but lack ESG scores:")
    proc_no_esg.orderBy("country_name").show(50, truncate=False)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 6. Match Confidence Analysis by Dimension

# CELL ********************

print(f"\n{'='*70}")
print("MATCH CONFIDENCE ANALYSIS - FACT PROCUREMENT")
print(f"{'='*70}\n")

# This requires joining back to lookup tables to get individual confidence scores
# Since we only store the average in the fact, we need to reconstruct

proc_detail = spark.table(f"{DB}.silver_procurement")
country_lookup = spark.table(f"{DB}.gold_dim_country_lookup")
material_lookup = spark.table(f"{DB}.gold_dim_material_lookup")

# Material confidence distribution
material_match_stats = (
    proc_detail
    .select(F.initcap(F.trim("materialname")).alias("material"))
    .join(material_lookup,
          F.col("material") == material_lookup.lookup_name,
          "left")
    .groupBy("match_type")
    .agg(
        F.count("*").alias("usage_count"),
        F.avg("match_confidence").alias("avg_confidence")
    )
    .orderBy(F.desc("usage_count"))
)

print("\nMaterial Match Statistics (by usage in procurement):")
material_match_stats.show(truncate=False)

# Country confidence distribution
hq_country_match_stats = (
    proc_detail
    .select(F.trim("headquarterscountry").alias("country"))
    .join(country_lookup,
          F.col("country") == country_lookup.lookup_name,
          "left")
    .groupBy("match_type")
    .agg(
        F.count("*").alias("usage_count"),
        F.avg("match_confidence").alias("avg_confidence")
    )
    .orderBy(F.desc("usage_count"))
)

print("\nHQ Country Match Statistics (by usage in procurement):")
hq_country_match_stats.show(truncate=False)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 7. Actionable Recommendations

# CELL ********************

print(f"\n{'='*70}")
print("DATA QUALITY IMPROVEMENT RECOMMENDATIONS")
print(f"{'='*70}\n")

recommendations = []

# Check unmapped values
if total_unmapped_proc > 0:
    unmapped_pct = (total_unmapped_proc / total_proc_records * 100)
    recommendations.append({
        "priority": "HIGH" if unmapped_pct > 5 else "MEDIUM",
        "issue": f"{total_unmapped_proc:,} unmapped procurement records ({unmapped_pct:.1f}%)",
        "action": "Add aliases for unmapped materials and countries to alias mapping tables",
        "impact": f"Could improve quality score by up to {unmapped_pct:.1f}%"
    })

if total_unmapped_supply > 0:
    # Check high-impact unmapped supply shares
    high_impact_unmapped = (unmapped_supply
                           .filter(F.col("impact_level") == "High Impact")
                           .count())
    if high_impact_unmapped > 0:
        recommendations.append({
            "priority": "HIGH",
            "issue": f"{high_impact_unmapped:,} high-impact unmapped supply share records",
            "action": "Prioritize mapping countries/materials with >10% supply share",
            "impact": "Critical for accurate supply concentration analysis"
        })

# Check low confidence matches
low_conf_proc = fact_proc.filter(F.col("data_quality_score") < 0.80).count()
if low_conf_proc > 0:
    low_conf_pct = (low_conf_proc / total_proc_records * 100)
    recommendations.append({
        "priority": "MEDIUM",
        "issue": f"{low_conf_proc:,} procurement records with confidence < 0.80",
        "action": "Review and improve aliases with confidence scores 0.70-0.80",
        "impact": f"Affects {low_conf_pct:.1f}% of procurement data"
    })

# Check coverage gaps
if gap_count > 0:
    recommendations.append({
        "priority": "MEDIUM",
        "issue": f"{gap_count} countries used in procurement lack ESG scores",
        "action": "Either add ESG data for these countries or flag in visualizations",
        "impact": "Enables complete sustainability analysis of supply chain"
    })

# Display recommendations
if recommendations:
    print(f"Found {len(recommendations)} data quality improvement opportunities:\n")
    for i, rec in enumerate(recommendations, 1):
        print(f"{i}. [{rec['priority']}] {rec['issue']}")
        print(f"   Action: {rec['action']}")
        print(f"   Impact: {rec['impact']}\n")
else:
    print("✅ No critical data quality issues found!")
    print("Data quality is excellent across all dimensions.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 8. Quality Summary Report

# CELL ********************

print(f"\n{'='*70}")
print("DATA QUALITY SUMMARY REPORT")
print(f"{'='*70}\n")

print("OVERALL METRICS:")
print(f"  • Total Procurement Records: {total_proc_records:,}")
print(f"  • Total Supply Share Records: {total_supply_records:,}")
print(f"  • Average Procurement Quality Score: {avg_proc_score:.3f}")
print(f"  • Average Supply Share Quality Score: {avg_supply_score:.3f}")
print(f"  • High Quality Record %: {overall_quality:.1f}%")

print(f"\nALIAS COVERAGE:")
print(f"  • Country Aliases: {total_country_aliases:,}")
print(f"  • Material Aliases: {total_material_aliases:,}")
print(f"  • Countries in Dimension: {total_countries:,}")
print(f"  • Materials in Dimension: {total_materials:,}")

print(f"\nDATA GAPS:")
print(f"  • Unmapped Procurement Records: {total_unmapped_proc:,}")
print(f"  • Unmapped Supply Records: {total_unmapped_supply:,}")
print(f"  • Countries Missing ESG Data: {gap_count}")

print(f"\nRECOMMENDATIONS:")
print(f"  • Total Improvement Opportunities: {len(recommendations)}")
high_priority = sum(1 for r in recommendations if r['priority'] == 'HIGH')
print(f"  • High Priority Items: {high_priority}")

print(f"\n{'='*70}")
print(f"Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'='*70}\n")

print("✓ Data Quality Analysis Complete")
print("\nNext Steps:")
print("  1. Review unmapped values and add aliases as needed")
print("  2. Focus on high-impact supply share gaps first")
print("  3. Consider flagging low-confidence records in visualizations")
print("  4. Monitor quality trends after pipeline improvements")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
