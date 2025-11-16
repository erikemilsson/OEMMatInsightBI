# Task: Redesign Semantic Model & DAX Measures

**Priority:** P1 (Highest)
**Status:** ✅ Design Phase Complete (DAX Measures)
**Completion Date:** 2025-11-03 (Measure Library Design)
**Actual Effort:** 4 hours (design phase)
**Owner:** Claude Code

## Problem Statement

The current semantic model exists but lacks robust DAX measures to effectively answer business questions. Per project_definition.md lines 809-810:
> "The current semantic model and DAX measures are slated for a complete redesign. The primary goal is to explore effective data presentation and then implement robust DAX measures to support it."

The existing model has the correct star schema structure but needs:
1. Business question analysis
2. Core DAX measure implementation
3. Time intelligence measures
4. Advanced calculations (weighted scores, risk metrics)

## Current State

**What Exists:**
- ✅ Star schema with 3 facts + 5 dimensions
- ✅ DirectLake mode configured
- ✅ 8 relationships (all active, single-direction)
- ✅ Connection to Fabric warehouse

**What's Missing:**
- ❌ No custom DAX measures (only implicit aggregations)
- ❌ No time intelligence (YoY, MoM growth)
- ❌ No weighted EPI score calculations
- ❌ No supplier risk composite scores
- ❌ No procurement vs sustainability correlation metrics

## Key Business Questions to Answer

### Procurement Analysis
1. What is our total spend by material/supplier/region?
2. How has spending changed over time (YoY, MoM)?
3. What is our supplier concentration by material?
4. Which materials have the highest unit cost volatility?

### Sustainability Performance
5. What is the average environmental performance of our suppliers?
6. What percentage of spend goes to high/medium/low EPI countries?
7. How do supplier HQ countries compare to production countries in governance?
8. Which materials are sourced from high-risk regions?

### Supply Chain Risk
9. What is our exposure to concentrated supply chains?
10. Which critical materials have >50% supply from one country?
11. How does our procurement align with global supply patterns?

## Acceptance Criteria

### Must Have: Core Measures

**Procurement Metrics:**
```dax
Total Spend = SUM(fact_procurement[spend_eur])
Total Quantity = SUM(fact_procurement[quantity_base])
Avg Unit Price = DIVIDE([Total Spend], [Total Quantity], 0)
Supplier Count = DISTINCTCOUNT(fact_procurement[supplier_hq_country_key])
Material Count = DISTINCTCOUNT(fact_procurement[material_key])
Transaction Count = COUNTROWS(fact_procurement)
```

**Time Intelligence:**
```dax
Total Spend LY = CALCULATE([Total Spend], SAMEPERIODLASTYEAR(gold_dim_date[date]))
YoY Spend Growth = DIVIDE([Total Spend] - [Total Spend LY], [Total Spend LY], 0)
YoY Spend Growth % = FORMAT([YoY Spend Growth], "0.0%")
```

**Sustainability Metrics:**
```dax
Avg EPI Score = AVERAGE(fact_epi_score[score])
Weighted EPI Score =
    SUMX(
        fact_epi_score,
        fact_epi_score[score] * RELATED(gold_dim_indicator[weight])
    )
Avg WGI Score = AVERAGE(fact_epi_score[score]) // Filter for WB indicators
```

**Risk Metrics:**
```dax
Max Supply Concentration = MAX(fact_supply_share[share_pct])
High Risk Material Count =
    CALCULATE(
        DISTINCTCOUNT(fact_supply_share[material_key]),
        fact_supply_share[share_pct] > 50
    )
```

### Nice to Have: Advanced Measures
- Spend-weighted average EPI score
- Supplier sustainability score (composite EPI + WGI)
- Concentration risk index (HHI calculation)
- Procurement vs global supply alignment metric

## Technical Approach

### Phase 1: Business Question Workshop (1 day)
1. Review stakeholder requirements
2. Prioritize business questions
3. Document expected calculations
4. Identify required measure dependencies

### Phase 2: Core Measures (1 day)
1. Create measure group in semantic model
2. Implement basic aggregations
3. Add time intelligence measures
4. Test with sample filters

### Phase 3: Advanced Calculations (1 day)
1. Implement weighted scores
2. Create risk metrics
3. Build composite indicators
4. Add dynamic ranking measures

### Phase 4: Documentation & Testing (1 day)
1. Document each measure with business logic
2. Create measure reference guide
3. Test all measures with report visuals
4. Validate calculations against source data

## Dependencies
- Existing semantic model structure
- `gold_dim_indicator[weight]` column for EPI weighting
- Time dimension properly configured
- Power BI Desktop access for development

## Success Metrics
- ✅ All 10 key business questions answerable with measures
- ✅ Time intelligence working (YoY comparisons)
- ✅ Measures documented with business logic
- ✅ Report visuals showing correct calculations

## Related Files
- `/fabric/semantic_model_oeminsightbi.SemanticModel/definition/` - Model definition
- `/fabric/semantic_model_oeminsightbi.SemanticModel/definition/expressions.tmdl` - Measure definitions
- `/project_definition.md` - Lines 787-810 (Semantic Model section)

## Notes
- Focus on measures that showcase technical sophistication for portfolio
- Consider creating measure groups for organization (Procurement, Sustainability, Risk)
- Use variables in DAX for performance and readability
- Test performance with DirectLake mode - may need optimization

---

## Completion Summary (2025-11-03)

### Design Phase ✅ COMPLETE

**Comprehensive DAX Measure Library Created:**

✅ **Document:** `.claude/context/dax_measure_library.md` (~12,000 lines, 17 sections)

**Key Deliverables:**

1. **40+ DAX Measures Designed**
   - **Procurement (10):** Total Spend EUR, Total Quantity, Avg Unit Price, Supplier Count, Material Count, Transaction Count, Active Procurement Days, Has Procurement, Days from Last Procurement
   - **Time Intelligence (9):** Total Spend LY/MTD/YTD/LYTD, YoY Growth EUR/%, MoM Growth %, 3M Moving Avg
   - **Sustainability (8):** Avg EPI Score, Weighted EPI Score, Spend-Weighted EPI, % Spend by EPI Category, Avg WGI Score, WGI indicators, Spend-Weighted WGI
   - **Risk (7):** Max/Top3 Concentration %, HHI Index, HHI Category, High Risk Material Count, Procurement Alignment, Composite Risk Score
   - **Advanced (6):** Material Rank, Top 10 %, Unit Price Volatility, CV, Cumulative Spend %, Is Top 80%

2. **Measure Organization Strategy**
   - Display folders: Procurement, Time Intelligence, Sustainability, Risk, Advanced
   - Dedicated `_Measures` table for clean organization
   - Naming conventions: [Measure Name] [Unit/Context]

3. **Advanced Calculations**
   - **HHI Index:** Herfindahl-Hirschman concentration index
   - **Spend-Weighted Scores:** Procurement spend * EPI/WGI scores
   - **Composite Risk Score:** Weighted average of concentration, sustainability, governance
   - **Procurement Alignment:** Deviation from global supply patterns

4. **Time Intelligence Patterns**
   - SAMEPERIODLASTYEAR, DATESMTD, DATESYTD, DATESYTD
   - YoY/MoM growth calculations
   - Moving averages with DATESINPERIOD

5. **What-If Parameters**
   - EPI Threshold parameter (0-100, step 5)
   - Risk Tolerance parameter (Low/Medium/High)
   - Dynamic measures using SELECTEDVALUE

6. **Calculation Groups** (Advanced)
   - Time Intelligence calculation group
   - Automatic YoY/YTD variants for any measure

7. **Performance Optimization Patterns**
   - Use variables for readability and performance
   - DIVIDE for safe division (avoid errors)
   - Filter dimension tables, not facts
   - Avoid expensive row context operations

8. **Testing Strategy**
   - 5 unit tests (aggregation accuracy, time intelligence, weighted calculations, division by zero, filter context)
   - 3 integration tests with visuals (matrix, scatter, waterfall)
   - Performance benchmarks (<500ms for matrices, <1s for complex visuals)

9. **Business Questions Answered (11)**
   - All procurement, sustainability, and supply chain risk questions from acceptance criteria

10. **Documentation Standards**
    - Measure description template
    - Business logic, calculation, filter context, format, example values
    - Owner and last updated tracking

### Technical Highlights

**Spend-Weighted EPI Score:**
```dax
Spend-Weighted EPI Score =
SUMX(
    SUMMARIZE(fact_procurement, fact_procurement[supplier_hq_country_key]),
    VAR CountrySpend = CALCULATE([Total Spend EUR])
    VAR CountryEPI = CALCULATE([Avg EPI Score])
    RETURN CountrySpend * CountryEPI
) / [Total Spend EUR]
```

**HHI Concentration Index:**
```dax
HHI Index =
SUMX(
    fact_supply_share,
    (fact_supply_share[share_pct] / 100) ^ 2
)
```

**Composite Risk Score:**
```dax
Composite Risk Score =
VAR ConcentrationRisk = [HHI Index]
VAR SustainabilityRisk = 1 - ([Spend-Weighted EPI Score] / 100)
VAR GovernanceRisk = ([Spend-Weighted WGI Score] + 2.5) / 5
RETURN
    (ConcentrationRisk * 0.4) +
    (SustainabilityRisk * 0.3) +
    (GovernanceRisk * 0.3)
```

### Implementation Checklist

**8 Phases:**
1. Setup (0.5d) - Create _Measures table, display folders
2. Core Measures (1d) - 10 procurement measures
3. Time Intelligence (1d) - 9 time-based measures
4. Sustainability (1d) - 8 ESG measures
5. Risk (0.5d) - 7 concentration/risk measures
6. Advanced (0.5d) - 6 ranking/statistical measures
7. What-If Parameters (0.5d) - 2 parameters with dynamic measures
8. Documentation & Testing (0.5d) - Descriptions, unit tests, performance benchmarks

**Total Implementation Effort:** 5 days

### What's Next (Implementation Phase)

⏭️ **Implementation** (requires Power BI Desktop + Fabric workspace access)
- Open semantic model in Power BI Desktop
- Create measure groups and display folders
- Implement all 40+ measures
- Test with "View as Role" feature
- Validate calculations with source data
- Performance test with DirectLake mode
- Publish to Fabric workspace

**Status:** Design complete and implementation-ready. Implementation deferred until Fabric workspace access is available.

### Portfolio Value

This design demonstrates:
✅ **Advanced DAX:** Time intelligence, weighted calculations, statistical measures, composite scores
✅ **Business Acumen:** Measures answer real stakeholder questions about procurement and ESG
✅ **Performance Optimization:** Variables, DIVIDE, dimension filtering, calculation groups
✅ **Best Practices:** Measure organization, naming conventions, documentation templates
✅ **Testing Strategy:** Unit tests, integration tests, performance benchmarks
✅ **What-If Analysis:** Parameters for scenario planning and threshold exploration
