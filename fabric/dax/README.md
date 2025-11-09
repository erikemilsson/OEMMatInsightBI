# DAX Measures

This folder contains DAX measure libraries for Power BI semantic models.

## Contents

### `quality_measures.dax`
Comprehensive collection of 50+ DAX measures for data quality monitoring and reporting.

**Measure Categories:**

1. **Core Quality Metrics** - Total records, average scores, overall quality
2. **Quality Category Breakdowns** - High/Medium/Low/Unmapped record counts
3. **Quality Percentages** - Percentage calculations for dashboards
4. **Business Impact Metrics** - Spend by quality, supply share by quality
5. **Quality Assessment** - Rating indicators and color helpers
6. **Dimension-Specific Metrics** - Material and country quality analysis
7. **Trend Analysis** - Quality improvement over time
8. **KPI Targets** - Target vs actual comparisons
9. **Drill-Through Helpers** - Context measures for detail pages
10. **Conditional Formatting** - Color bands and visual helpers

**Usage:**
1. Open your Power BI semantic model
2. Copy measures from this file
3. Paste into a measures table (create `_Measures` table if needed)
4. Organize into folders as indicated in comments
5. Use in visuals on the Data Quality dashboard page

**Prerequisites:**
- Fact tables must have `data_quality_score` and `quality_category` columns
- For supply share: also requires `has_unmapped_material` and `has_unmapped_country` columns

**See Also:**
- Documentation: `docs/data_quality_guide.md`
- SQL Views: `fabric/create_quality_views.sql`
- Analysis Notebook: `fabric/data_quality_analysis.Notebook/`
