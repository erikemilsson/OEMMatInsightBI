# Data Quality Dashboard Guide

## Overview

The **Data Quality Analysis Notebook** (`fabric/data_quality_analysis.Notebook`) provides comprehensive visibility into the quality and assumptions of your data pipeline, specifically focusing on alias resolution and match confidence.

## What It Shows

### 1. Executive Summary
- Overall quality rating (% of high-quality records)
- Total records vs high-quality records for each fact table
- Average quality scores
- Assessment (Excellent / Good / Fair / Needs Improvement)

### 2. Quality Distribution
- Breakdown by category: High / Medium / Low / Unmapped
- Quality score bands (0.95-1.00, 0.90-0.95, etc.)
- Distribution for both `fact_procurement` and `fact_supply_share`

### 3. Unmapped Values Analysis
- **Critical for identifying data gaps**
- Lists all values that couldn't be matched to dimension tables
- Shows business impact (e.g., high supply share % that's unmapped)
- Prioritized by impact level (High / Medium / Low)

### 4. Alias Resolution Statistics
- Total aliases defined for countries and materials
- Match type distribution (exact_match, standard_alias, encoding_variant, etc.)
- Confidence score distribution
- Countries/materials with most aliases

### 5. Country Coverage Matrix
- Which countries appear in which datasets (EPI, World Bank, Supply Share, Procurement)
- **Critical gap analysis:** Countries used in procurement but lacking ESG scores
- Enables informed decisions about data completeness

### 6. Match Confidence Analysis
- How procurement data matched to dimensions
- Distribution of match types actually used in your data
- Helps identify if low-confidence aliases are being used frequently

### 7. Actionable Recommendations
- Prioritized list of data quality improvements
- Impact assessment for each recommendation
- Specific actions to take (e.g., "Add aliases for X countries")

### 8. Quality Summary Report
- One-page summary of all key metrics
- Tracks improvement opportunities
- Export-friendly format for documentation

## How to Use

### Running the Notebook

1. **In Microsoft Fabric:**
   - Navigate to your workspace
   - Open `data_quality_analysis.Notebook`
   - Click "Run All" to execute the full analysis
   - Review each section's output

2. **As Part of Pipeline:**
   - Add the notebook to your `orchestrator_pipeline_bronze_to_gold` pipeline
   - Run it after the `silver-to-gold` transformation
   - Creates audit trail of data quality over time

3. **Ad-Hoc Analysis:**
   - Run anytime to check current data quality
   - Before making changes to alias mappings
   - After adding new data sources

### Interpreting Results

**Quality Score Thresholds:**
- **≥ 0.90:** High confidence - exact or standard aliases
- **0.70-0.90:** Medium confidence - fuzzy matches, encoding variants
- **0.50-0.70:** Low confidence - weak matches, may need review
- **< 0.50:** Unmapped - no match found, uses "Unknown" placeholder

**Priority Flags:**
- **HIGH:** Significant impact on data accuracy or >5% of records affected
- **MEDIUM:** Moderate impact, should address but not urgent
- **LOW:** Minor issues, address when convenient

### Acting on Recommendations

#### To Add Country Aliases:
1. Open `fabric/silver-to-gold2.Notebook/notebook-content.py`
2. Find `country_aliases_with_confidence` DataFrame creation (around line 106)
3. Add new row:
   ```python
   ("New Alias", "Standard Country Name", 0.95, "standard_alias"),
   ```
4. Re-run the pipeline

#### To Add Material Aliases:
1. Same notebook, find `material_aliases_with_confidence` (around line 157)
2. Add new row:
   ```python
   ("New Material Alias", "Standard Material", 0.95, "spelling_variant"),
   ```
3. Re-run the pipeline

#### To Add Missing Countries:
1. Find `missing_countries` DataFrame (around line 228)
2. Add country with ISO3 code:
   ```python
   ("Country Name", "ISO3", iso_numeric, "wb_code"),
   ```

## Understanding Quality Categories

### High (≥ 0.90)
- **Exact matches** to dimension tables
- **Standard aliases** (USA → United States of America)
- **Reliable data** for analysis and reporting
- Safe to use without caveats

### Medium (0.70-0.90)
- **Fuzzy matches** with reasonable confidence
- **Encoding variants** (Türkiye → Turkey)
- **Territory mappings** (Hong Kong → China)
- Generally acceptable but note assumptions in reports

### Low (0.50-0.70)
- **Weak matches** that may need verification
- **Corrupted encodings** with pattern-based fixes
- Use with caution, consider flagging in visualizations

### Unmapped (< 0.50)
- **No match found** in dimension tables
- Assigned to "Unknown" placeholders
- **No data loss** but limited analytical value
- **Priority for improvement**

## Key Tables Created by Pipeline

### Audit Tables
- `gold_unmapped_procurement_audit` - Tracks unmapped procurement records
- `gold_unmapped_supply_audit` - Tracks unmapped supply share records with impact
- `gold_data_quality_metrics` - Summary metrics for dashboards

### Alias Mapping Tables
- `mapping_country_aliases_confidence` - All country aliases with scores
- `mapping_material_aliases_confidence` - All material aliases with scores

### Lookup Tables
- `gold_dim_country_lookup` - Country dimension + all aliases
- `gold_dim_material_lookup` - Material dimension + all aliases
- `gold_country_coverage_matrix` - Country presence across datasets

### Quality Views
- `v_fact_procurement_high_confidence` - Only high-quality records
- `v_fact_procurement_all` - All records with quality indicators
- `v_fact_supply_share_high_confidence` - Verified supply data
- `v_fact_supply_share_complete` - All supply data with warnings
- `v_supply_concentration_risk` - Supply risk with quality metrics

## Using Quality Data in Power BI

### Approach 1: Filter to High Quality Only
```dax
High Quality Procurement =
CALCULATE(
    [Total Spend],
    fact_procurement[quality_category] = "High"
)
```

### Approach 2: Show Quality as Tooltip
Add `data_quality_score` and `quality_category` to visual tooltips to give users transparency.

### Approach 3: Conditional Formatting
Use `quality_category` to color-code visuals:
- High = Green
- Medium = Yellow
- Low = Orange
- Unmapped = Red

### Approach 4: Create Quality Dashboard Page
Add a dedicated report page showing:
- Quality KPIs (% High Quality, Avg Score)
- Quality distribution charts
- Top unmapped values tables
- Trend over time (if historical data available)

## Best Practices

1. **Run Before Major Changes**
   - Before adding new data sources
   - After updating alias mappings
   - When data quality issues are suspected

2. **Review Regularly**
   - Monthly quality checks
   - After pipeline failures
   - When new countries/materials appear

3. **Document Decisions**
   - When adding low-confidence aliases, document why
   - Track improvements to quality score over time
   - Note any business rules applied

4. **Communicate Transparently**
   - Include quality caveats in reports
   - Show confidence scores to stakeholders
   - Highlight data gaps in presentations

## Troubleshooting

### "No unmapped records but quality score is low"
- Check confidence scores of matches being used
- Review medium-confidence aliases (0.70-0.90 range)
- Consider upgrading confidence if matches are verified

### "High unmapped count but low impact"
- Common for rare materials or small transactions
- Prioritize by business impact, not just count
- Focus on high `unmapped_impact_score` values

### "Countries in procurement but no ESG scores"
- Expected for some countries (North Korea, Yemen, etc.)
- Either add manual ESG data or flag in visualizations
- Document data availability limitations

## Next Steps

After reviewing the data quality dashboard:

1. **Address high-priority gaps** identified in recommendations
2. **Add aliases** for frequently unmapped values
3. **Create Power BI quality page** to track improvements
4. **Schedule regular reviews** (monthly or after data updates)
5. **Document data lineage** and quality assumptions

## Contact

For questions about data quality metrics or alias resolution, refer to:
- `src/transformations/data_quality.py` - Quality check functions
- `src/transformations/key_generation.py` - Surrogate key logic
- `fabric/silver-to-gold2.Notebook` - Main transformation logic
