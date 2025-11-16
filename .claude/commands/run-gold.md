# Run Gold Layer Transformation

Execute the silver-to-gold business logic transformations to create dimensional model.

## What This Command Does

This command runs the `silver-to-gold2.Notebook` which creates the star schema:
- 3 fact tables (procurement, supply_share, epi_score)
- 5 dimension tables (country, date, indicator, material, stage)
- Alias resolution for country and material names
- Surrogate key generation (xxhash64)
- Data quality scoring and confidence tracking
- Unmapped value handling with audit tables

**Input:** Silver tables
**Output:** Gold fact and dimension tables (business-ready data model)

## Prerequisites

- Silver layer tables populated (run `/run-silver` first)
- Lakehouse `oem_lh` accessible with write permissions
- Sufficient compute for complex transformations (~10-15 minutes runtime)

## Steps

### Option 1: Run via Fabric Pipeline

1. Navigate to Fabric workspace
2. Open pipeline: `orchestrator_pipeline_bronze_to_gold`
3. Run full pipeline (gold is stage 3, runs after silver)
4. Monitor "silver-to-gold" notebook activity

### Option 2: Run Notebook Directly (Recommended for development)

1. Navigate to Fabric workspace
2. Open notebook: `silver-to-gold2`
3. Review configuration cell (top of notebook):
   ```python
   DB = "oem_lh"
   FAIL_ON_UNMAPPED = False  # Uses placeholder dimensions instead
   LOG_UNMAPPED = True       # Creates audit tables
   ```
4. Click "Run all" button
5. Monitor execution (takes ~10-15 minutes)
6. Check outputs in lakehouse

## Outputs Created

### Dimension Tables

**gold_dim_country:**
- ~180-200 countries from EPI + WB + 8 manually added
- 6 placeholder countries (Unknown - Africa/Asia/Europe/Americas/Oceania/Global)
- Attributes: iso3, iso_numeric, wb_code, country_name_std, region, is_placeholder
- Key: country_key (BIGINT - xxhash64 of iso3)

**gold_dim_date:**
- One row per day from min to max procurement date
- Attributes: year, month, day, month_name, quarter, day_of_week, week_of_year
- Key: date_key (INTEGER - yyyyMMdd format)

**gold_dim_indicator:**
- EPI indicators (~30-40) + WGI indicators (~6)
- Attributes: source_system, abbrev, variable_name, indicator_code, weight, description
- Key: indicator_key (BIGINT - xxhash64)

**gold_dim_material:**
- Unique materials from procurement + supply shares
- 13 commodity groups (Battery metals, Base metals, Precious metals, etc.)
- Attributes: material_name_std, commodity_group, unit_base, is_placeholder
- Key: material_key (BIGINT - xxhash64 of material_name_std)

**gold_dim_stage:**
- 2 rows: Extraction (E), Processing (P)
- Key: stage_key (BIGINT - xxhash64 of stage_code)

### Fact Tables

**fact_procurement:**
- One row per procurement transaction
- Measures: quantity_base (kg), unitprice_eur, spend_eur, data_quality_score
- Dimension keys: date_key, material_key, supplier_hq_country_key, production_country_key
- Quality categorization: High/Medium/Low/Unmapped

**fact_supply_share:**
- One row per material × stage × country × year
- Measures: share_pct (0-100), data_quality_score
- Dimension keys: material_key, stage_key, country_key, year (2023)
- Unmapped flags: has_unmapped_material, has_unmapped_country

**fact_epi_score:**
- One row per country × indicator × year (pivoted from wide format)
- Measures: score (indicator value)
- Dimension keys: country_key, indicator_key, year (2024)

### Supporting Tables

**Lookup Tables:**
- gold_dim_country_lookup - 100+ country aliases with confidence scores
- gold_dim_material_lookup - Material aliases with confidence scores

**Audit Tables:**
- gold_unmapped_procurement_audit - Unmapped procurement values
- gold_unmapped_supply_audit - Unmapped supply share values with impact assessment
- gold_data_quality_metrics - Summary quality statistics
- gold_country_coverage_matrix - Country presence across sources

**Helper Views:**
- v_fact_procurement_high_confidence - Quality >= 0.9
- v_fact_procurement_all - With dimension names joined
- v_fact_supply_share_high_confidence - Quality >= 0.9, no unknowns
- v_fact_supply_share_complete - All data with quality flags
- v_supply_concentration_risk - Risk analysis by material/stage

## Validation

After gold transformation completes:

```python
# Check gold table row counts
gold_tables = {
    # Dimensions
    "gold_dim_country": (180, 210),     # ~186 real + 6 placeholders
    "gold_dim_date": (365, 3650),       # 1-10 years of dates
    "gold_dim_indicator": (30, 50),     # EPI + WGI indicators
    "gold_dim_material": (50, 200),     # Unique materials
    "gold_dim_stage": (2, 2),           # Exactly 2
    # Facts
    "fact_procurement": (100000, 300000),
    "fact_supply_share": (5000, 15000),
    "fact_epi_score": (3000, 10000)     # Countries × Indicators
}

for table, (min_rows, max_rows) in gold_tables.items():
    count = spark.table(f"oem_lh.{table}").count()
    status = "✓" if min_rows <= count <= max_rows else "✗"
    print(f"{status} {table}: {count:,} rows (expected {min_rows:,}-{max_rows:,})")
```

**Data Quality Checks:**
```python
# Check for unmapped procurement records
unmapped_procurement = spark.table("oem_lh.gold_unmapped_procurement_audit").count()
print(f"Unmapped procurement records: {unmapped_procurement}")

# Check data quality distribution
quality_dist = spark.sql("""
    SELECT quality_category, COUNT(*) as count,
           ROUND(AVG(data_quality_score), 3) as avg_score
    FROM oem_lh.fact_procurement
    GROUP BY quality_category
    ORDER BY avg_score DESC
""")
quality_dist.show()

# Expected:
# High (0.9-1.0): Majority of records
# Medium (0.7-0.89): Some records
# Low (0.5-0.69): Few records
# Unmapped (0.0): Minimal records (assigned to Unknown placeholders)
```

## Troubleshooting

**Notebook Times Out (>12 hours):**
- Check data volume in silver tables
- Review Spark configuration (increase executor memory)
- Consider incremental load approach

**High Unmapped Counts:**
- Review `gold_unmapped_procurement_audit` table
- Check for new country/material names needing aliases
- Add aliases to lookup tables and re-run

**Surrogate Key Collisions:**
- Verify xxhash64 function works correctly
- Check for null values in key generation columns
- Review `stable_key()` function implementation

**Fact Table Empty or Low Row Count:**
- Check silver table counts (ensure input data exists)
- Review filtering logic (e.g., year 2020 filter for WGI)
- Verify joins not filtering out too much data

## Next Steps

After gold transformation succeeds:
1. Run `/check-quality` to review data quality metrics
2. Run `/view-unmapped` to see unmapped values
3. Proceed to warehouse sync (automatic in pipeline)
4. Refresh semantic model and check Power BI report

## Related Files

- `/fabric/silver-to-gold2.Notebook/`
- `/.claude/context/architecture/medallion_architecture.md`
- `/.claude/reference/schemas/gold_tables.md`
- `/.claude/reference/transformations/alias_mappings.md`
- `/.claude/tasks/01_enhance_data_quality_visibility.md`
