# Check Data Quality

Review data quality metrics, match confidence scores, and unmapped values.

## What This Command Does

This command helps you assess data quality across the pipeline by checking:
- Match confidence scores for country and material aliases
- Unmapped values in procurement and supply share data
- Data quality distribution (High/Medium/Low/Unmapped)
- Coverage matrix (which countries appear in which sources)

## Prerequisites

- Gold layer tables populated (run `/run-gold` or `/run-full-pipeline` first)
- Audit tables created (automatic in gold transformation)

## Quick Quality Check

```python
from pyspark.sql import SparkSession

# 1. Check data quality distribution in fact_procurement
print("=== Fact Procurement Quality Distribution ===")
spark.sql("""
    SELECT
        quality_category,
        COUNT(*) as record_count,
        ROUND(AVG(data_quality_score), 3) as avg_score,
        ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) as percentage
    FROM oem_lh.fact_procurement
    GROUP BY quality_category
    ORDER BY avg_score DESC
""").show()

# Expected output:
# +------------------+--------------+-----------+------------+
# | quality_category | record_count | avg_score | percentage |
# +------------------+--------------+-----------+------------+
# | High             |      85,000  |   0.975   |    85.0    |
# | Medium           |      12,000  |   0.825   |    12.0    |
# | Low              |       2,500  |   0.650   |     2.5    |
# | Unmapped         |         500  |   0.000   |     0.5    |
# +------------------+--------------+-----------+------------+

# 2. Check unmapped procurement records
print("\n=== Unmapped Procurement Values ===")
unmapped_proc = spark.table("oem_lh.gold_unmapped_procurement_audit")
print(f"Total unmapped records: {unmapped_proc.count()}")

if unmapped_proc.count() > 0:
    print("\nTop 10 unmapped values by frequency:")
    spark.sql("""
        SELECT
            unmapped_value,
            unmapped_field,
            COUNT(*) as frequency,
            ROUND(SUM(spend_eur), 2) as total_spend_impact
        FROM oem_lh.gold_unmapped_procurement_audit
        GROUP BY unmapped_value, unmapped_field
        ORDER BY frequency DESC
        LIMIT 10
    """).show(truncate=False)

# 3. Check unmapped supply share records
print("\n=== Unmapped Supply Share Values ===")
unmapped_supply = spark.table("oem_lh.gold_unmapped_supply_audit")
print(f"Total unmapped records: {unmapped_supply.count()}")

if unmapped_supply.count() > 0:
    print("\nTop 10 unmapped values by impact:")
    spark.sql("""
        SELECT
            unmapped_material,
            unmapped_country,
            share_pct,
            unmapped_impact_score
        FROM oem_lh.gold_unmapped_supply_audit
        ORDER BY unmapped_impact_score DESC
        LIMIT 10
    """).show(truncate=False)

# 4. Check country coverage matrix
print("\n=== Country Coverage Matrix ===")
spark.sql("""
    SELECT
        in_procurement,
        in_epi,
        in_wgi,
        in_supply_shares,
        COUNT(*) as country_count
    FROM oem_lh.gold_country_coverage_matrix
    GROUP BY in_procurement, in_epi, in_wgi, in_supply_shares
    ORDER BY country_count DESC
""").show()

# 5. Summary statistics
print("\n=== Overall Data Quality Summary ===")
total_records = spark.table("oem_lh.fact_procurement").count()
high_quality = spark.table("oem_lh.fact_procurement").filter("data_quality_score >= 0.9").count()
unmapped = spark.table("oem_lh.gold_unmapped_procurement_audit").count()

print(f"Total procurement records: {total_records:,}")
print(f"High quality (≥0.9): {high_quality:,} ({100*high_quality/total_records:.1f}%)")
print(f"Unmapped: {unmapped:,} ({100*unmapped/total_records:.1f}%)")
print(f"\nData Quality Score: {100*high_quality/total_records:.1f}/100")
```

## Detailed Quality Analysis

### 1. Alias Resolution Analysis

Check how well country and material aliases are resolving:

```python
# Country alias match rates
print("=== Country Alias Statistics ===")
spark.sql("""
    SELECT
        CASE
            WHEN confidence >= 1.0 THEN 'Exact Match (1.0)'
            WHEN confidence >= 0.95 THEN 'Standard Alias (0.95-0.99)'
            WHEN confidence >= 0.85 THEN 'Territory Mapping (0.85-0.94)'
            WHEN confidence >= 0.80 THEN 'Encoding Variant (0.80-0.84)'
            ELSE 'Low Confidence (<0.80)'
        END as match_tier,
        COUNT(*) as alias_count,
        ROUND(AVG(confidence), 3) as avg_confidence
    FROM oem_lh.gold_dim_country_lookup
    GROUP BY match_tier
    ORDER BY avg_confidence DESC
""").show(truncate=False)

# Material alias match rates
print("\n=== Material Alias Statistics ===")
spark.sql("""
    SELECT
        CASE
            WHEN confidence >= 0.95 THEN 'High Confidence (≥0.95)'
            WHEN confidence >= 0.90 THEN 'Medium Confidence (0.90-0.94)'
            ELSE 'Low Confidence (<0.90)'
        END as match_tier,
        COUNT(*) as alias_count,
        ROUND(AVG(confidence), 3) as avg_confidence
    FROM oem_lh.gold_dim_material_lookup
    GROUP BY match_tier
    ORDER BY avg_confidence DESC
""").show(truncate=False)
```

### 2. Identify Data Quality Issues

```python
# Find procurement records with low quality scores
print("=== Low Quality Procurement Records (Score < 0.7) ===")
spark.sql("""
    SELECT
        p.date_key,
        m.material_name_std,
        c1.country_name_std as hq_country,
        c2.country_name_std as production_country,
        p.data_quality_score,
        p.quality_category,
        p.spend_eur
    FROM oem_lh.fact_procurement p
    LEFT JOIN oem_lh.gold_dim_material m ON p.material_key = m.material_key
    LEFT JOIN oem_lh.gold_dim_country c1 ON p.supplier_hq_country_key = c1.country_key
    LEFT JOIN oem_lh.gold_dim_country c2 ON p.production_country_key = c2.country_key
    WHERE p.data_quality_score < 0.7
    ORDER BY p.spend_eur DESC
    LIMIT 20
""").show(truncate=False)

# Find materials with high unmapped rates
print("\n=== Materials with High Unmapped Rates ===")
spark.sql("""
    SELECT
        material_key,
        COUNT(*) as total_records,
        SUM(CASE WHEN has_unmapped_material THEN 1 ELSE 0 END) as unmapped_records,
        ROUND(100.0 * SUM(CASE WHEN has_unmapped_material THEN 1 ELSE 0 END) / COUNT(*), 2) as unmapped_pct
    FROM oem_lh.fact_supply_share
    GROUP BY material_key
    HAVING unmapped_pct > 10
    ORDER BY unmapped_pct DESC
""").show(truncate=False)
```

### 3. Review Data Completeness

```python
# Check for missing dimension attributes
print("=== Dimension Table Completeness ===")

# Country dimension
null_counts_country = spark.sql("""
    SELECT
        SUM(CASE WHEN iso3 IS NULL THEN 1 ELSE 0 END) as null_iso3,
        SUM(CASE WHEN country_name_std IS NULL THEN 1 ELSE 0 END) as null_name,
        SUM(CASE WHEN is_placeholder THEN 1 ELSE 0 END) as placeholder_count,
        COUNT(*) as total_countries
    FROM oem_lh.gold_dim_country
""")
print("Country Dimension:")
null_counts_country.show()

# Material dimension
null_counts_material = spark.sql("""
    SELECT
        SUM(CASE WHEN commodity_group IS NULL THEN 1 ELSE 0 END) as null_commodity_group,
        SUM(CASE WHEN is_placeholder THEN 1 ELSE 0 END) as placeholder_count,
        COUNT(*) as total_materials
    FROM oem_lh.gold_dim_material
""")
print("\nMaterial Dimension:")
null_counts_material.show()
```

## Quality Score Interpretation

**Data Quality Score Range:**
- **0.90-1.00 (High):** Excellent match confidence, exact or standard aliases used
- **0.70-0.89 (Medium):** Good match, but uses territory mappings or encoding variants
- **0.50-0.69 (Low):** Uncertain match, review recommended
- **0.00 (Unmapped):** No match found, assigned to "Unknown" placeholder

**Quality Category Distribution (Target):**
- High: >85% of records
- Medium: 10-15% of records
- Low: <5% of records
- Unmapped: <1% of records

## Actionable Insights

**If High Unmapped Count:**
1. Review `gold_unmapped_procurement_audit` table
2. Identify frequently unmapped values
3. Add new aliases to lookup tables:
   - Update `gold_dim_country_lookup` for country aliases
   - Update `gold_dim_material_lookup` for material aliases
4. Re-run gold transformation: `/run-gold`

**If Low Quality Scores:**
1. Review confidence scoring thresholds in `silver-to-gold2.Notebook`
2. Consider adjusting alias matching rules
3. Add more alias variants to lookup tables

**If Data Completeness Issues:**
1. Check bronze/silver data sources for null values
2. Review data ingestion and cleaning logic
3. Add data quality checks to prevent nulls

## Next Steps

- If quality is satisfactory: Proceed with report development
- If unmapped values found: Add aliases and re-run gold transformation
- If quality is low: Review Task 01 (Enhance Data Quality Visibility)
- For automated monitoring: Implement Task 07 (Add Data Quality Checks)

## Related Files

- `/.claude/tasks/01_enhance_data_quality_visibility.md`
- `/.claude/tasks/07_add_data_quality_checks.md`
- `/fabric/silver-to-gold2.Notebook/` - Quality scoring logic
- `/.claude/support/documents/transformations/alias_mappings.md`
