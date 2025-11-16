# View Unmapped Values

Display detailed information about unmapped countries and materials in the data.

## What This Command Does

This command provides a comprehensive view of values that couldn't be matched to standard dimensions during the gold layer transformation, including:
- Unmapped procurement values (suppliers, materials, countries)
- Unmapped supply share values (materials, countries)
- Impact assessment (spend, supply percentage affected)
- Recommendations for adding new aliases

## Prerequisites

- Gold layer transformation completed
- Audit tables created: `gold_unmapped_procurement_audit`, `gold_unmapped_supply_audit`

## View Unmapped Procurement Values

```python
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, count, sum as _sum, round as _round

# Load unmapped procurement audit table
unmapped_proc = spark.table("oem_lh.gold_unmapped_procurement_audit")

print("=" * 80)
print("UNMAPPED PROCUREMENT VALUES REPORT")
print("=" * 80)

total_unmapped = unmapped_proc.count()
print(f"\nTotal unmapped records: {total_unmapped:,}\n")

if total_unmapped == 0:
    print("✓ No unmapped values found! All procurement data successfully matched.")
else:
    # Group by unmapped field type
    print("\n--- Unmapped Values by Field ---")
    unmapped_proc.groupBy("unmapped_field").agg(
        count("*").alias("record_count"),
        _round(_sum("spend_eur"), 2).alias("total_spend_eur")
    ).orderBy(col("record_count").desc()).show(truncate=False)

    # Top unmapped supplier countries by frequency
    print("\n--- Top 20 Unmapped Supplier HQ Countries ---")
    spark.sql("""
        SELECT
            unmapped_value as country_name,
            COUNT(*) as frequency,
            ROUND(SUM(spend_eur), 2) as total_spend_eur,
            ROUND(AVG(spend_eur), 2) as avg_spend_eur
        FROM oem_lh.gold_unmapped_procurement_audit
        WHERE unmapped_field = 'supplier_hq_country'
        GROUP BY unmapped_value
        ORDER BY frequency DESC
        LIMIT 20
    """).show(truncate=False)

    # Top unmapped production countries
    print("\n--- Top 20 Unmapped Production Countries ---")
    spark.sql("""
        SELECT
            unmapped_value as country_name,
            COUNT(*) as frequency,
            ROUND(SUM(spend_eur), 2) as total_spend_eur
        FROM oem_lh.gold_unmapped_procurement_audit
        WHERE unmapped_field = 'production_country'
        GROUP BY unmapped_value
        ORDER BY frequency DESC
        LIMIT 20
    """).show(truncate=False)

    # Top unmapped materials
    print("\n--- Top 20 Unmapped Materials ---")
    spark.sql("""
        SELECT
            unmapped_value as material_name,
            COUNT(*) as frequency,
            ROUND(SUM(spend_eur), 2) as total_spend_eur,
            ROUND(AVG(spend_eur), 2) as avg_spend_eur
        FROM oem_lh.gold_unmapped_procurement_audit
        WHERE unmapped_field = 'material'
        GROUP BY unmapped_value
        ORDER BY frequency DESC
        LIMIT 20
    """).show(truncate=False)

    # Impact analysis
    total_spend = spark.table("oem_lh.fact_procurement").agg(_sum("spend_eur")).collect()[0][0]
    unmapped_spend = unmapped_proc.agg(_sum("spend_eur")).collect()[0][0] if unmapped_spend else 0

    print(f"\n--- Impact Analysis ---")
    print(f"Total procurement spend: €{total_spend:,.2f}")
    print(f"Unmapped spend: €{unmapped_spend:,.2f}")
    print(f"Unmapped percentage: {100*unmapped_spend/total_spend:.2f}%")
```

## View Unmapped Supply Share Values

```python
# Load unmapped supply share audit table
unmapped_supply = spark.table("oem_lh.gold_unmapped_supply_audit")

print("\n" + "=" * 80)
print("UNMAPPED SUPPLY SHARE VALUES REPORT")
print("=" * 80)

total_unmapped_supply = unmapped_supply.count()
print(f"\nTotal unmapped records: {total_unmapped_supply:,}\n")

if total_unmapped_supply == 0:
    print("✓ No unmapped values found! All supply share data successfully matched.")
else:
    # Top unmapped materials by impact
    print("\n--- Top 20 Unmapped Materials (by Supply Share Impact) ---")
    spark.sql("""
        SELECT
            unmapped_material,
            COUNT(*) as frequency,
            ROUND(AVG(share_pct), 2) as avg_share_pct,
            ROUND(MAX(share_pct), 2) as max_share_pct,
            ROUND(AVG(unmapped_impact_score), 2) as avg_impact_score
        FROM oem_lh.gold_unmapped_supply_audit
        WHERE unmapped_material IS NOT NULL
        GROUP BY unmapped_material
        ORDER BY avg_impact_score DESC
        LIMIT 20
    """).show(truncate=False)

    # Top unmapped countries
    print("\n--- Top 20 Unmapped Countries (by Supply Share Impact) ---")
    spark.sql("""
        SELECT
            unmapped_country,
            COUNT(*) as frequency,
            ROUND(AVG(share_pct), 2) as avg_share_pct,
            ROUND(MAX(share_pct), 2) as max_share_pct,
            ROUND(AVG(unmapped_impact_score), 2) as avg_impact_score
        FROM oem_lh.gold_unmapped_supply_audit
        WHERE unmapped_country IS NOT NULL
        GROUP BY unmapped_country
        ORDER BY avg_impact_score DESC
        LIMIT 20
    """).show(truncate=False)

    # High-impact unmapped records (share > 10%)
    print("\n--- High-Impact Unmapped Records (Share > 10%) ---")
    spark.sql("""
        SELECT
            material,
            stage,
            unmapped_material,
            unmapped_country,
            share_pct,
            unmapped_impact_score
        FROM oem_lh.gold_unmapped_supply_audit
        WHERE share_pct > 10.0
        ORDER BY share_pct DESC
    """).show(truncate=False)
```

## Generate Alias Recommendations

This section provides suggestions for adding new aliases to lookup tables:

```python
print("\n" + "=" * 80)
print("ALIAS RECOMMENDATIONS")
print("=" * 80)

# Country alias recommendations
print("\n--- Recommended Country Aliases to Add ---")
print("Add these to gold_dim_country_lookup table:\n")

unmapped_countries = spark.sql("""
    SELECT DISTINCT
        unmapped_value as alias_to_add,
        COUNT(*) OVER (PARTITION BY unmapped_value) as frequency
    FROM oem_lh.gold_unmapped_procurement_audit
    WHERE unmapped_field IN ('supplier_hq_country', 'production_country')
""").orderBy(col("frequency").desc()).limit(10).collect()

if unmapped_countries:
    for row in unmapped_countries:
        print(f"  - '{row.alias_to_add}' → [match to standard country name] (frequency: {row.frequency})")
else:
    print("  ✓ No country aliases needed!")

# Material alias recommendations
print("\n--- Recommended Material Aliases to Add ---")
print("Add these to gold_dim_material_lookup table:\n")

unmapped_materials = spark.sql("""
    SELECT DISTINCT
        unmapped_value as alias_to_add,
        COUNT(*) OVER (PARTITION BY unmapped_value) as frequency
    FROM oem_lh.gold_unmapped_procurement_audit
    WHERE unmapped_field = 'material'
""").orderBy(col("frequency").desc()).limit(10).collect()

if unmapped_materials:
    for row in unmapped_materials:
        print(f"  - '{row.alias_to_add}' → [match to standard material name] (frequency: {row.frequency})")
else:
    print("  ✓ No material aliases needed!")
```

## Export Unmapped Values for Review

Save unmapped values to CSV for manual review and alias creation:

```python
# Export unmapped procurement values
unmapped_proc_export = spark.sql("""
    SELECT
        unmapped_value,
        unmapped_field,
        COUNT(*) as frequency,
        ROUND(SUM(spend_eur), 2) as total_spend_eur,
        ROUND(AVG(spend_eur), 2) as avg_spend_eur,
        '' as suggested_match,
        0.95 as suggested_confidence
    FROM oem_lh.gold_unmapped_procurement_audit
    GROUP BY unmapped_value, unmapped_field
    ORDER BY frequency DESC
""")

# Save to Files section of lakehouse
unmapped_proc_export.coalesce(1).write \
    .mode("overwrite") \
    .option("header", "true") \
    .csv("Files/unmapped_values/procurement")

print("\n✓ Unmapped procurement values exported to:")
print("  Files/unmapped_values/procurement/")

# Export unmapped supply share values
unmapped_supply_export = spark.sql("""
    SELECT
        unmapped_material,
        unmapped_country,
        stage,
        ROUND(AVG(share_pct), 2) as avg_share_pct,
        COUNT(*) as frequency,
        '' as suggested_material_match,
        '' as suggested_country_match
    FROM oem_lh.gold_unmapped_supply_audit
    GROUP BY unmapped_material, unmapped_country, stage
    ORDER BY avg_share_pct DESC
""")

unmapped_supply_export.coalesce(1).write \
    .mode("overwrite") \
    .option("header", "true") \
    .csv("Files/unmapped_values/supply_share")

print("✓ Unmapped supply share values exported to:")
print("  Files/unmapped_values/supply_share/")
```

## How to Add New Aliases

After identifying unmapped values, add them to lookup tables:

### Option 1: Update Lookup Tables Directly (via Notebook)

```python
# Example: Add new country alias
from pyspark.sql.functions import lit

new_country_alias = spark.createDataFrame([
    ("Türkiye", "Turkey", 0.95),  # Encoding variant
    ("USA", "United States of America", 1.0),  # Standard alias
    ("UK", "United Kingdom", 1.0)
], ["alias", "country_name_std", "confidence"])

# Append to lookup table
new_country_alias.write \
    .mode("append") \
    .saveAsTable("oem_lh.gold_dim_country_lookup")

print("✓ New country aliases added!")
```

### Option 2: Update in silver-to-gold2 Notebook

Modify the alias mapping dictionaries in `silver-to-gold2.Notebook`:

```python
# Add to country alias mapping
country_aliases = {
    # Existing aliases...
    "Türkiye": ("Turkey", 0.95),
    "USA": ("United States of America", 1.0),
    "UK": ("United Kingdom", 1.0)
}

# Add to material alias mapping
material_aliases = {
    # Existing aliases...
    "Aluminum": ("Aluminium", 0.95),
    "Copper (kg)": ("Copper", 0.90)
}
```

After adding aliases, re-run gold transformation: `/run-gold`

## Interpretation Guide

**Unmapped Frequency:**
- **High (>100 records):** Critical - should be added immediately
- **Medium (10-100 records):** Important - add when convenient
- **Low (<10 records):** Minor - can defer or leave unmapped

**Impact Score (for supply shares):**
- **High (>10%):** Significant supply chain gap - prioritize
- **Medium (1-10%):** Moderate impact - address if material is critical
- **Low (<1%):** Minimal impact - can defer

**Confidence Scores for New Aliases:**
- **1.0:** Exact match or ISO standard
- **0.95:** Standard alias (e.g., USA → United States)
- **0.90:** Common variant (e.g., unit suffixes)
- **0.85:** Territory mapping (e.g., Hong Kong → China)
- **0.80:** Encoding variant (e.g., Türkiye → Turkey)

## Next Steps

1. Review unmapped values and impact
2. Research correct matches (use Wikipedia, ISO country codes)
3. Add aliases to lookup tables or notebook
4. Re-run gold transformation: `/run-gold`
5. Re-check quality: `/check-quality`
6. Repeat until unmapped rate <1%

## Related Files

- `/fabric/silver-to-gold2.Notebook/` - Contains alias mapping logic
- `/.claude/reference/transformations/alias_mappings.md` - Alias documentation
- `/.claude/tasks/01_enhance_data_quality_visibility.md`
- `/.claude/commands/check-quality.md`
