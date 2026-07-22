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

# # Sample Quality Data Population (Task 017)
# 
# **Purpose:** Insert backdated sample data into quality observability tables to demonstrate trending before organic data accumulates.
# 
# **Tables populated:**
# - `gold_quality_history` - 25 rows showing metrics across 5 simulated pipeline runs
# - `gold_gap_registry` - 12 rows showing gap lifecycle (new, persisting, resolved)
# 
# **Story:** Quality improved from 85% coverage (Jan 1) to 100% (Jan 20) through systematic gap resolution.
# 
# **Note:** Sample data is marked with `[SAMPLE]` prefix in resolution_notes for gap_registry.
# Run this notebook ONCE to seed historical data for demo purposes.

# CELL ********************

# =============================================================================
# CONFIGURATION
# =============================================================================

DB = "oem_lh"

# Check if sample data already exists
existing_sample_count = spark.sql(f"""
    SELECT COUNT(*) as cnt
    FROM {DB}.gold_gap_registry
    WHERE resolution_notes LIKE '[SAMPLE]%'
""").first().cnt

if existing_sample_count > 0:
    print(f"WARNING: Found {existing_sample_count} existing sample records in gap_registry.")
    print("This notebook should only run ONCE. Skipping to avoid duplicates.")
    print("To re-run, first delete sample data with:")
    print(f"  DELETE FROM {DB}.gold_gap_registry WHERE resolution_notes LIKE '[SAMPLE]%'")
    print(f"  DELETE FROM {DB}.gold_quality_history WHERE refresh_timestamp < '2026-01-15'")
    dbutils.notebook.exit("Sample data already exists - skipped")

print("No existing sample data found. Proceeding with insertion...")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 1. Sample Quality History Data
# 
# Shows quality improvement over 5 simulated pipeline runs:
# 
# | Run | Date | Coverage | Match Rate | Unmapped | Story |
# |-----|------|----------|------------|----------|-------|
# | 1 | Jan 1 | 85% | 92% | 15 | Initial baseline |
# | 2 | Jan 5 | 88% | 93% | 12 | Added 3 country aliases |
# | 3 | Jan 10 | 92% | 95% | 8 | Material cleanup |
# | 4 | Jan 15 | 96% | 97% | 4 | Major sprint |
# | 5 | Jan 18 | 99% | 99% | 2 | Near complete |

# CELL ********************

from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, BooleanType, TimestampType
from datetime import datetime, timedelta

# =============================================================================
# QUALITY HISTORY SAMPLE DATA
# =============================================================================

# Define 5 simulated pipeline runs with progressive improvement
# NOTE: coverage_rate, match_rate, high_quality_pct use WHOLE PERCENTAGES (85 = 85%)
#       to match the format used by the real populate_quality_history() function
sample_runs = [
    # (timestamp, layer, entity, metric_name, metric_value, threshold, breach_flag)

    # --- Run 1: Jan 1, 2026 - Initial baseline (85% coverage) ---
    ("2026-01-01 08:00:00", "Gold", "fact_procurement", "coverage_rate", 85.0, 95.0, True),
    ("2026-01-01 08:00:00", "Gold", "fact_procurement", "match_rate", 92.0, 95.0, True),
    ("2026-01-01 08:00:00", "Gold", "fact_procurement", "unmapped_count", 15.0, 5.0, True),
    ("2026-01-01 08:00:00", "Gold", "fact_procurement", "high_quality_pct", 78.0, 80.0, True),
    ("2026-01-01 08:00:00", "Gold", "gold_dim_country", "active_countries", 45.0, None, False),

    # --- Run 2: Jan 5, 2026 - Added country aliases (88% coverage) ---
    ("2026-01-05 09:30:00", "Gold", "fact_procurement", "coverage_rate", 88.0, 95.0, True),
    ("2026-01-05 09:30:00", "Gold", "fact_procurement", "match_rate", 93.0, 95.0, True),
    ("2026-01-05 09:30:00", "Gold", "fact_procurement", "unmapped_count", 12.0, 5.0, True),
    ("2026-01-05 09:30:00", "Gold", "fact_procurement", "high_quality_pct", 82.0, 80.0, False),
    ("2026-01-05 09:30:00", "Gold", "gold_dim_country", "active_countries", 48.0, None, False),

    # --- Run 3: Jan 10, 2026 - Material cleanup (92% coverage) ---
    ("2026-01-10 10:15:00", "Gold", "fact_procurement", "coverage_rate", 92.0, 95.0, True),
    ("2026-01-10 10:15:00", "Gold", "fact_procurement", "match_rate", 95.0, 95.0, False),
    ("2026-01-10 10:15:00", "Gold", "fact_procurement", "unmapped_count", 8.0, 5.0, True),
    ("2026-01-10 10:15:00", "Gold", "fact_procurement", "high_quality_pct", 87.0, 80.0, False),
    ("2026-01-10 10:15:00", "Gold", "gold_dim_material", "active_materials", 125.0, None, False),

    # --- Run 4: Jan 15, 2026 - Major cleanup sprint (96% coverage) ---
    ("2026-01-15 11:00:00", "Gold", "fact_procurement", "coverage_rate", 96.0, 95.0, False),
    ("2026-01-15 11:00:00", "Gold", "fact_procurement", "match_rate", 97.0, 95.0, False),
    ("2026-01-15 11:00:00", "Gold", "fact_procurement", "unmapped_count", 4.0, 5.0, False),
    ("2026-01-15 11:00:00", "Gold", "fact_procurement", "high_quality_pct", 92.0, 80.0, False),
    ("2026-01-15 11:00:00", "Gold", "gold_dim_country", "active_countries", 52.0, None, False),

    # --- Run 5: Jan 18, 2026 - Near complete (99% coverage) ---
    ("2026-01-18 14:30:00", "Gold", "fact_procurement", "coverage_rate", 99.0, 95.0, False),
    ("2026-01-18 14:30:00", "Gold", "fact_procurement", "match_rate", 99.0, 95.0, False),
    ("2026-01-18 14:30:00", "Gold", "fact_procurement", "unmapped_count", 2.0, 5.0, False),
    ("2026-01-18 14:30:00", "Gold", "fact_procurement", "high_quality_pct", 96.0, 80.0, False),
    ("2026-01-18 14:30:00", "Gold", "gold_dim_material", "active_materials", 132.0, None, False),
]

# Create DataFrame
history_schema = StructType([
    StructField("refresh_timestamp", StringType(), False),
    StructField("layer", StringType(), False),
    StructField("entity", StringType(), False),
    StructField("metric_name", StringType(), False),
    StructField("metric_value", DoubleType(), False),
    StructField("threshold", DoubleType(), True),
    StructField("breach_flag", BooleanType(), False),
])

history_df = spark.createDataFrame(sample_runs, history_schema)

# Convert timestamp string to timestamp type
history_df = history_df.withColumn(
    "refresh_timestamp",
    F.to_timestamp("refresh_timestamp", "yyyy-MM-dd HH:mm:ss")
)

# Insert into table
history_df.write.format("delta").mode("append").saveAsTable(f"{DB}.gold_quality_history")

print(f"Inserted {history_df.count()} sample rows into gold_quality_history")
print("\nSample data preview:")
history_df.orderBy("refresh_timestamp", "entity", "metric_name").show(10, truncate=False)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 2. Sample Gap Registry Data
# 
# Shows gap lifecycle with different statuses:
# 
# | Gap | Type | First Seen | Status | Story |
# |-----|------|------------|--------|-------|
# | Singpaore | country | Jan 1 | Resolved Jan 15 | Typo fixed with alias |
# | Chnia | country | Jan 1 | Resolved Jan 5 | Typo fixed quickly |
# | Deutchland | country | Jan 1 | Resolved Jan 10 | German spelling |
# | VNM-X | country | Jan 5 | Open | Needs investigation |
# | Unknown Material X | material | Jan 5 | Open | High impact |
# | PLASTIC_RAW_001 | material | Jan 1 | Resolved Jan 15 | Added to master |
# | steel-ss304 | material | Jan 1 | Resolved Jan 5 | Normalized naming |
# | COPPER_GRADE_A | material | Jan 10 | Open | New, being addressed |
# | Taivan | country | Jan 10 | Resolved Jan 18 | Typo fixed |
# | Phillipines | country | Jan 1 | Open | Long-standing |
# | aluminium-6061 | material | Jan 5 | Resolved Jan 15 | US/UK spelling |
# | BRASS_ALLOY_X | material | Jan 15 | Open | Very new |

# CELL ********************

# =============================================================================
# GAP REGISTRY SAMPLE DATA
# =============================================================================

# Get next gap_id (after any existing real data)
max_gap_id_result = spark.sql(f"SELECT COALESCE(MAX(gap_id), 0) as max_id FROM {DB}.gold_gap_registry").first()
next_gap_id = max_gap_id_result.max_id + 1000  # Start sample IDs at +1000 to avoid collision

# Sample gaps with lifecycle story
# (gap_id, gap_natural_key, entity, gap_type, first_seen, last_seen, total_occurrences, current_status, estimated_impact, resolution_date, resolution_notes)
sample_gaps = [
    # --- Resolved Gaps (success stories) ---
    (next_gap_id + 1, "Singpaore", "procurement", "country",
     "2026-01-01 08:00:00", "2026-01-15 11:00:00", 47, "Resolved", 12500.0,
     "2026-01-15 11:00:00", "[SAMPLE] Typo fixed: added alias mapping to Singapore"),

    (next_gap_id + 2, "Chnia", "procurement", "country",
     "2026-01-01 08:00:00", "2026-01-05 09:30:00", 23, "Resolved", 8200.0,
     "2026-01-05 09:30:00", "[SAMPLE] Typo fixed: added alias mapping to China"),

    (next_gap_id + 3, "Deutchland", "procurement", "country",
     "2026-01-01 08:00:00", "2026-01-10 10:15:00", 15, "Resolved", 5100.0,
     "2026-01-10 10:15:00", "[SAMPLE] German spelling: added alias mapping to Germany"),

    (next_gap_id + 4, "PLASTIC_RAW_001", "procurement", "material",
     "2026-01-01 08:00:00", "2026-01-15 11:00:00", 34, "Resolved", 15200.0,
     "2026-01-15 11:00:00", "[SAMPLE] Added to material master data"),

    (next_gap_id + 5, "steel-ss304", "procurement", "material",
     "2026-01-01 08:00:00", "2026-01-05 09:30:00", 28, "Resolved", 9800.0,
     "2026-01-05 09:30:00", "[SAMPLE] Normalized naming convention: mapped to SS304 Stainless Steel"),

    (next_gap_id + 6, "Taivan", "procurement", "country",
     "2026-01-10 10:15:00", "2026-01-18 14:30:00", 8, "Resolved", 2100.0,
     "2026-01-18 14:30:00", "[SAMPLE] Typo fixed: added alias mapping to Taiwan"),

    (next_gap_id + 7, "aluminium-6061", "procurement", "material",
     "2026-01-05 09:30:00", "2026-01-15 11:00:00", 19, "Resolved", 7300.0,
     "2026-01-15 11:00:00", "[SAMPLE] UK spelling normalized: mapped to Aluminum 6061"),

    # --- Open Gaps (still need attention) ---
    (next_gap_id + 8, "VNM-X", "procurement", "country",
     "2026-01-05 09:30:00", "2026-01-18 14:30:00", 89, "Open", 22000.0,
     None, "[SAMPLE] Needs investigation - unclear country code"),

    (next_gap_id + 9, "Unknown Material X", "procurement", "material",
     "2026-01-05 09:30:00", "2026-01-18 14:30:00", 156, "Open", 45000.0,
     None, "[SAMPLE] High impact - priority for resolution"),

    (next_gap_id + 10, "COPPER_GRADE_A", "procurement", "material",
     "2026-01-10 10:15:00", "2026-01-18 14:30:00", 12, "Open", 3200.0,
     None, "[SAMPLE] New gap - being addressed"),

    (next_gap_id + 11, "Phillipines", "procurement", "country",
     "2026-01-01 08:00:00", "2026-01-18 14:30:00", 67, "Open", 18500.0,
     None, "[SAMPLE] Long-standing typo - needs alias mapping to Philippines"),

    (next_gap_id + 12, "BRASS_ALLOY_X", "procurement", "material",
     "2026-01-15 11:00:00", "2026-01-18 14:30:00", 5, "Open", 1800.0,
     None, "[SAMPLE] Very new gap - just appeared"),
]

# Create DataFrame
gap_schema = StructType([
    StructField("gap_id", StringType(), False),  # Will convert to BIGINT
    StructField("gap_natural_key", StringType(), False),
    StructField("entity", StringType(), False),
    StructField("gap_type", StringType(), False),
    StructField("first_seen", StringType(), False),
    StructField("last_seen", StringType(), False),
    StructField("total_occurrences", StringType(), False),  # Will convert to INT
    StructField("current_status", StringType(), False),
    StructField("estimated_impact", DoubleType(), True),
    StructField("resolution_date", StringType(), True),
    StructField("resolution_notes", StringType(), True),
])

# Convert tuples to proper format
gap_data = [
    (str(g[0]), g[1], g[2], g[3], g[4], g[5], str(g[6]), g[7], g[8], g[9], g[10])
    for g in sample_gaps
]

gap_df = spark.createDataFrame(gap_data, gap_schema)

# Convert types
gap_df = gap_df \
    .withColumn("gap_id", F.col("gap_id").cast("bigint")) \
    .withColumn("total_occurrences", F.col("total_occurrences").cast("int")) \
    .withColumn("first_seen", F.to_timestamp("first_seen", "yyyy-MM-dd HH:mm:ss")) \
    .withColumn("last_seen", F.to_timestamp("last_seen", "yyyy-MM-dd HH:mm:ss")) \
    .withColumn("resolution_date", F.to_timestamp("resolution_date", "yyyy-MM-dd HH:mm:ss"))

# Insert into table
gap_df.write.format("delta").mode("append").saveAsTable(f"{DB}.gold_gap_registry")

print(f"Inserted {gap_df.count()} sample rows into gold_gap_registry")
print("\nSample gap registry preview:")
gap_df.orderBy("first_seen", "gap_natural_key").show(truncate=False)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 3. Verify Sample Data

# CELL ********************

# =============================================================================
# VERIFICATION
# =============================================================================

print("=" * 60)
print("SAMPLE DATA VERIFICATION")
print("=" * 60)

# Quality History summary
print("\n--- gold_quality_history ---")
spark.sql(f"""
    SELECT
        DATE(refresh_timestamp) as run_date,
        COUNT(*) as metrics_count,
        ROUND(AVG(CASE WHEN metric_name = 'coverage_rate' THEN metric_value END), 2) as coverage_rate,
        ROUND(AVG(CASE WHEN metric_name = 'match_rate' THEN metric_value END), 2) as match_rate,
        SUM(CASE WHEN breach_flag = true THEN 1 ELSE 0 END) as breaches
    FROM {DB}.gold_quality_history
    WHERE refresh_timestamp < '2026-01-19'  -- Sample data only
    GROUP BY DATE(refresh_timestamp)
    ORDER BY run_date
""").show(truncate=False)

# Gap Registry summary
print("\n--- gold_gap_registry ---")
spark.sql(f"""
    SELECT
        current_status,
        gap_type,
        COUNT(*) as count,
        ROUND(SUM(estimated_impact), 0) as total_impact_eur,
        ROUND(AVG(total_occurrences), 0) as avg_occurrences
    FROM {DB}.gold_gap_registry
    WHERE resolution_notes LIKE '[SAMPLE]%'
    GROUP BY current_status, gap_type
    ORDER BY current_status, gap_type
""").show(truncate=False)

# Timeline view
print("\n--- Gap Resolution Timeline ---")
spark.sql(f"""
    SELECT
        gap_natural_key,
        gap_type,
        DATE(first_seen) as first_seen,
        DATE(resolution_date) as resolved,
        DATEDIFF(COALESCE(resolution_date, current_timestamp()), first_seen) as days_open,
        current_status,
        total_occurrences,
        ROUND(estimated_impact, 0) as impact_eur
    FROM {DB}.gold_gap_registry
    WHERE resolution_notes LIKE '[SAMPLE]%'
    ORDER BY first_seen, gap_natural_key
""").show(truncate=False)

print("\n" + "=" * 60)
print("SAMPLE DATA INSERTION COMPLETE")
print("=" * 60)
print("\nYou can now build trend charts in Power BI using this data.")
print("Sample data is marked with [SAMPLE] prefix in resolution_notes.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Cleanup (Optional)
# 
# Run this cell only if you need to remove sample data:
# 
# ```sql
# -- Remove sample gap registry entries
# DELETE FROM oem_lh.gold_gap_registry WHERE resolution_notes LIKE '[SAMPLE]%';
# 
# -- Remove sample quality history (by date range)
# DELETE FROM oem_lh.gold_quality_history WHERE refresh_timestamp < '2026-01-19';
# ```
