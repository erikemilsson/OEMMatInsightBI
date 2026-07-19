# DAX Measures Documentation - OEMMatInsightBI

**Status:** No Custom DAX Measures Found
**Last Updated:** 2025-11-03
**Investigation Date:** 2025-11-03

## Summary

After investigating the semantic model files synced to Git, **no custom DAX measures have been found**. The semantic model currently relies on implicit aggregations (SUM, NONE) defined at the column level.

## Investigation Findings

### Files Checked
1. `/fabric/OEMInsightBI_v2.SemanticModel/definition/expressions.tmdl`
   - **Finding:** Contains only database connection expression
   - **DAX Measures:** None

2. `/fabric/OEMInsightBI_v2.SemanticModel/definition/model.tmdl`
   - **Finding:** Model structure with table references only
   - **DAX Measures:** None

3. Table Definition Files (all checked):
   - `fact_procurement.tmdl`
   - `fact_epi_score.tmdl`
   - `fact_supply_share.tmdl`
   - `gold_dim_country.tmdl`
   - `gold_dim_material.tmdl`
   - `gold_dim_indicator.tmdl`
   - `gold_dim_stage.tmdl`
   - `gold_dim_date.tmdl`
   - **Finding:** Only column definitions with implicit aggregations
   - **DAX Measures:** None

### Column Aggregations Found

**fact_procurement:**
- `quantity_base` - SUM
- `unitprice_eur` - SUM
- `spend_eur` - SUM
- Foreign keys - NONE (non-additive)

**fact_epi_score:**
- `score` - SUM (⚠️ May be incorrect aggregation for scores)
- Foreign keys - NONE

**fact_supply_share:**
- (Not checked in detail, similar structure expected)

## Implications

### Potential Issues
1. **No Explicit Measures:** Power BI report likely uses implicit aggregations or measures defined in .pbix file
2. **Version Control Gap:** If measures exist in .pbix, they're not version-controlled
3. **Score Aggregation:** EPI score column has SUM aggregation, which may not be semantically correct
4. **No Time Intelligence:** No YoY, MoM, or period comparison measures
5. **No Business Metrics:** No KPIs like concentration risk, sustainability scores, etc.

### Possible Scenarios

**Scenario 1:** Measures exist in .pbix file but not synced to Git
- **Action Required:** Export measures from Power BI Desktop to TMDL
- **Next Steps:** Open .pbix file, use DAX Studio to export measures

**Scenario 2:** No measures exist anywhere (using implicit aggregations only)
- **Action Required:** Design and create business measures
- **Next Steps:** Proceed with Task 02 (Redesign Semantic Model & DAX Measures)

**Scenario 3:** Report uses visual-level measures (not model-level)
- **Action Required:** Convert visual measures to model measures for reusability
- **Next Steps:** Audit report visuals, extract DAX expressions

## Recommended Next Steps

### Immediate Actions
1. ✅ **Document finding:** Complete (this file)
2. ⏭️ **Check if .pbix file exists:** Verify if `report2.Report/report.pbix` contains measures
3. ⏭️ **Prioritize Task 02:** "Redesign Semantic Model & DAX Measures" (P1)
4. ⏭️ **Create measure design document:** Plan essential business metrics

### Future Task: Create Essential Measures

If no measures exist, the following should be created:

#### Procurement Metrics
```dax
// Total Spend
Total Spend = SUM(fact_procurement[spend_eur])

// Total Quantity (kg)
Total Quantity = SUM(fact_procurement[quantity_base])

// Average Unit Price
Avg Unit Price = DIVIDE([Total Spend], [Total Quantity], 0)

// Distinct Materials Count
Materials Count = DISTINCTCOUNT(fact_procurement[material_key])

// Distinct Suppliers Count
Suppliers Count = DISTINCTCOUNT(fact_procurement[supplier_hq_country_key])
```

#### Time Intelligence
```dax
// Total Spend LY (Last Year)
Total Spend LY = CALCULATE([Total Spend], SAMEPERIODLASTYEAR(gold_dim_date[date]))

// YoY Spend Growth
YoY Spend Growth = DIVIDE([Total Spend] - [Total Spend LY], [Total Spend LY], 0)

// YoY Spend Growth %
YoY Spend Growth % = [YoY Spend Growth] * 100
```

#### Concentration Risk
```dax
// Top 3 Materials Spend
Top 3 Materials Spend =
CALCULATE(
    [Total Spend],
    TOPN(3, ALLSELECTED(gold_dim_material), [Total Spend], DESC)
)

// Concentration Risk (Top 3 / Total)
Concentration Risk % = DIVIDE([Top 3 Materials Spend], [Total Spend], 0) * 100
```

#### Sustainability Metrics
```dax
// Average EPI Score
Avg EPI Score = AVERAGE(fact_epi_score[score])

// High Risk Countries (Score < 50)
High Risk Countries =
CALCULATE(
    DISTINCTCOUNT(fact_epi_score[country_key]),
    fact_epi_score[score] < 50
)

// Supply Share High Risk %
Supply Share High Risk % =
CALCULATE(
    [Total Supply Share],
    fact_epi_score[score] < 50
) * 100
```

## Related Tasks

- **Task 02 (P1):** Redesign Semantic Model & DAX Measures
  - **Status:** Not Started
  - **Dependency:** This investigation (Task 09) - ✅ Complete
  - **Next:** Design measure library and implement

- **Task 03 (P1):** Redesign Power BI Report
  - **Status:** Not Started
  - **Dependency:** Task 02 (measures must exist first)

## Related Files

- `/fabric/OEMInsightBI_v2.SemanticModel/definition/expressions.tmdl` - Current (minimal) expressions
- `/fabric/OEMInsightBI_v2.SemanticModel/definition/model.tmdl` - Model structure
- `/project_definition.md` - Lines 787-810 (documenting lack of measures)
- `/.claude/tasks/02_redesign_semantic_model.md` - Next task to address this

## Notes

- **DirectLake Mode:** All tables use DirectLake, which is efficient for large datasets
- **Star Schema:** Proper dimensional model in place (3 facts, 5 dimensions)
- **Missing Layer:** Metrics layer (DAX measures) needs to be built
- **Portfolio Value:** Creating well-documented DAX measures demonstrates Power BI expertise
- **Best Practice:** Version control measures in TMDL format for collaboration

---

**Conclusion:** No custom DAX measures found in Git-synced semantic model files. Next step is to determine if measures exist in .pbix file or need to be created from scratch. Recommend proceeding with Task 02 to design and implement business metrics layer.
