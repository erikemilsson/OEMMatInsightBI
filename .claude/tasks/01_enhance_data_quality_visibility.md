# Task: Enhance Data Quality & Matching Visibility

**Priority:** P1 (Highest)
**Status:** Not Started
**Estimated Effort:** 2-3 days
**Owner:** TBD

## Problem Statement

The project currently implements sophisticated alias resolution for country and material names with confidence scoring (0-1 scale), but there's no centralized way to:
- View unmapped values across datasets
- Assess match confidence and quality assumptions
- Understand the impact of mapping decisions on final results
- Identify which mappings need manual review

This makes it difficult to assess confidence in the final dataset and creates portfolio presentation challenges.

## Current State

**What Exists:**
- ✅ Alias resolution tables: `gold_dim_country_lookup`, `gold_dim_material_lookup`
- ✅ Confidence scoring: Tier 1 (1.0), Tier 2 (0.95), encoding variants (0.80-0.90)
- ✅ Audit tables: `gold_unmapped_procurement_audit`, `gold_unmapped_supply_audit`
- ✅ Quality categorization: High/Medium/Low/Unmapped
- ✅ Coverage matrix: `gold_country_coverage_matrix`
- ✅ Helper views: `v_fact_procurement_high_confidence`, `v_fact_supply_share_high_confidence`

**What's Missing:**
- ❌ No centralized DQ dashboard or report
- ❌ No visualization of match rates by source
- ❌ No trend analysis of data quality over time
- ❌ No prioritized list of mappings to review

## Acceptance Criteria

### Must Have:
1. **Data Quality Notebook** (`/fabric/notebooks/data_quality_report.Notebook`)
   - Query all audit tables and generate summary statistics
   - Calculate match rates by source system (Azure SQL, EPI, WGI, EU CRM)
   - Identify top 10 unmapped countries and materials by impact (spend, share %)
   - Export results to new table: `gold_data_quality_dashboard`

2. **Power BI DQ Page** (in existing report or new dedicated report)
   - Overall quality scorecard (match rates, unmapped counts)
   - Confidence distribution chart (High/Medium/Low/Unmapped)
   - Unmapped values table with impact assessment
   - Trend analysis (if historical DQ data available)

3. **Documentation**
   - Update `/fabric/Readme.md` with instructions to run DQ notebook
   - Add DQ page to report navigation

### Nice to Have:
- Automated DQ report generation (daily/weekly schedule)
- Email alerts for unmapped values exceeding threshold
- Interactive drill-through from DQ page to audit tables

## Technical Approach

### Step 1: Create Data Quality Notebook
```python
# Read audit tables
unmapped_procurement = spark.read.table("oem_lh.gold_unmapped_procurement_audit")
unmapped_supply = spark.read.table("oem_lh.gold_unmapped_supply_audit")

# Calculate summary statistics
quality_summary = {
    "procurement_total": procurement_fact.count(),
    "procurement_unmapped": unmapped_procurement.count(),
    "procurement_match_rate": ...,
    "top_unmapped_countries": ...,
    "top_unmapped_materials": ...
}

# Write to dashboard table
write_tbl(summary_df, "gold_data_quality_dashboard")
```

### Step 2: Add to Pipeline
- Insert new notebook activity after `silver-to-gold` step
- Runs in parallel with warehouse sync (non-blocking)

### Step 3: Create Power BI Visuals
- Card visuals: Match rates, total unmapped
- Bar chart: Unmapped values by source system
- Table: Top unmapped values with impact scores

## Dependencies
- Existing audit tables and views
- Access to `silver-to-gold2.Notebook` transformation logic
- Power BI report edit permissions

## Success Metrics
- ✅ DQ dashboard accessible in Power BI
- ✅ Unmapped values visible with impact assessment
- ✅ Match rates calculated for all sources
- ✅ Portfolio presentation-ready DQ documentation

## Related Files
- `/fabric/silver-to-gold2.Notebook/` - Existing transformation logic
- `/fabric/report.Report/` - Power BI report to extend
- `/project_definition.md` - Lines 972-973 (Known Issues section)

## Notes
- This task directly addresses the main technical debt identified in project_definition.md
- Focus on clarity and portfolio value - this will be a showcase feature
- Consider using Fabric's built-in data profiling features if available
