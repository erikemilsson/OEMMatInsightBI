# Power BI Measure Guide - OEMMatInsightBI

**Created:** 2025-11-17
**Purpose:** Guide for using existing measures and planning additional measures

---

## Part 1: Schema Overview

### Available Tables & Key Columns

**Fact Tables:**
- `fact_procurement`
  - `spend_eur` (numeric) - Procurement spend
  - `quantity_base` (numeric) - Quantity in base units
  - `unitprice_eur` (numeric) - Unit price
  - Keys: `date_key`, `material_key`, `supplier_hq_country_key`, `production_country_key`

- `fact_epi_score`
  - `score` (numeric) - EPI score value
  - `year` (integer) - Score year
  - Keys: `country_key`, `indicator_key`

- `fact_supply_share`
  - `share_pct` (STRING!) - Supply share percentage (needs conversion)
  - `intensity_t` (STRING!) - Intensity in tonnes (needs conversion)
  - `year` (integer) - Supply year
  - Keys: `material_key`, `country_key`, `stage_key`

**Dimension Tables:**
- `gold_dim_date` - Date dimension with `date`, `year`, `month`, `day`, `month_name`
- `gold_dim_country` - Country info with `country_name_std`, `iso3`, `wb_code`
- `gold_dim_material` - Material info with `material_name_std`, `commodity_group`
- `gold_dim_indicator` - Indicator info with `source_system` (e.g., "EPI", "WGI")
- `gold_dim_stage` - Supply chain stages

**⚠️ Critical Issue:** `share_pct` and `intensity_t` are stored as STRINGS. You must convert them in DAX using `VALUE()`.

---

## Part 2: 8 Existing Measures - Usage Guide

### Procurement Measures (2)

#### 1. **Total Spend EUR**
```dax
Total Spend EUR = SUM(fact_procurement[spend_eur])
```
**Use For:**
- KPI cards showing total spend
- Charts comparing spend by country, material, or time
- Trend lines over time

**Visual Ideas:**
- Card visual for executive summary
- Column chart: Spend by Material
- Line chart: Spend over time (by month/year)

#### 2. **YoY Spend Growth %**
```dax
YoY Spend Growth % =
    VAR CurrentPeriod = [Total Spend EUR]
    VAR PriorPeriod = CALCULATE([Total Spend EUR], SAMEPERIODLASTYEAR(gold_dim_date[date]))
    RETURN
        DIVIDE(CurrentPeriod - PriorPeriod, PriorPeriod, 0)
```
**Use For:**
- Year-over-year comparison cards
- Trend indicators showing growth direction
- Conditional formatting (green = positive, red = negative)

**Visual Ideas:**
- KPI card with trend indicator
- Line chart showing growth % over multiple years
- Table showing spend by category with YoY growth column

---

### Sustainability Measures (3)

#### 3. **Avg EPI Score**
```dax
Avg EPI Score =
    CALCULATE(
        AVERAGE(fact_epi_score[score]),
        gold_dim_indicator[source_system] = "EPI"
    )
```
**Use For:**
- Average environmental score across countries in current context
- Benchmarking country performance

**Visual Ideas:**
- Card showing average EPI score for supplier countries
- Map visual colored by EPI score
- Bar chart: Countries ranked by EPI score

#### 4. **Spend-Weighted EPI Score**
```dax
Spend-Weighted EPI Score =
    SUMX(
        SUMMARIZE(fact_procurement, fact_procurement[supplier_hq_country_key]),
        VAR CountrySpend = CALCULATE([Total Spend EUR])
        VAR CountryEPI =
            CALCULATE(
                [Avg EPI Score],
                FILTER(
                    fact_epi_score,
                    fact_epi_score[country_key] = fact_procurement[supplier_hq_country_key]
                )
            )
        RETURN
            CountrySpend * CountryEPI
    ) / [Total Spend EUR]
```
**Use For:**
- Portfolio-level sustainability metric
- Understanding true environmental exposure based on spend concentration

**Visual Ideas:**
- KPI card: "Portfolio EPI Score" (weighted by spend)
- Comparison card: Avg EPI vs Spend-Weighted EPI (shows if you're spending more in high/low EPI countries)

#### 5. **% Spend - High EPI (>60)**
```dax
% Spend - High EPI (>60) =
    VAR HighEPISpend =
        CALCULATE(
            [Total Spend EUR],
            FILTER(
                fact_epi_score,
                fact_epi_score[score] >= 60 &&
                RELATED(gold_dim_indicator[source_system]) = "EPI"
            )
        )
    RETURN
        DIVIDE(HighEPISpend, [Total Spend EUR], 0)
```
**Use For:**
- Compliance/target tracking (e.g., "80% of spend in countries with EPI > 60")
- Sustainability dashboard

**Visual Ideas:**
- Gauge visual showing % of spend in high-EPI countries
- Donut chart: Spend split by EPI threshold (<60 vs >=60)

---

### Risk Measures (3)

#### 6. **Max Supply Concentration %**
```dax
Max Supply Concentration % =
    VAR MaxShare = MAXX(fact_supply_share, VALUE(fact_supply_share[share_pct]))
    RETURN
        DIVIDE(MaxShare, 100, 0)
```
**Use For:**
- Identifying highest single-country dependency for a material
- Risk dashboards

**Visual Ideas:**
- Card: "Highest Country Risk: 87%"
- Table: Material | Country | Max Concentration %

#### 7. **HHI Index**
```dax
HHI Index =
    SUMX(
        fact_supply_share,
        POWER(DIVIDE(VALUE(fact_supply_share[share_pct]), 100, 0), 2)
    )
```
**Use For:**
- Measuring supply chain concentration risk (0-1 scale, higher = more concentrated)
- Benchmarking against industry standards (HHI > 0.25 = highly concentrated)

**Visual Ideas:**
- Card with conditional formatting (>0.25 = red)
- Scatter plot: HHI Index vs Total Spend (identify high-spend, high-risk materials)

#### 8. **High Risk Material Count**
```dax
High Risk Material Count =
    CALCULATE(
        DISTINCTCOUNT(fact_supply_share[material_key]),
        VALUE(fact_supply_share[share_pct]) > 50
    )
```
**Use For:**
- Counting materials where one country supplies >50%
- Executive summary: "12 materials at high risk"

**Visual Ideas:**
- KPI card: "Materials at Risk"
- Table: List of high-risk materials with Max Concentration %

---

## Part 3: Recommended Additional Measures

### Priority 1: Essential Missing Measures (6)

These measures are needed for the most common visuals:

#### A. **Total Quantity**
```dax
Total Quantity = SUM(fact_procurement[quantity_base])
```
**Why:** Basic aggregation for volume analysis

#### B. **Transaction Count**
```dax
Transaction Count = COUNTROWS(fact_procurement)
```
**Why:** Operational metric for procurement activity

#### C. **Distinct Supplier Countries**
```dax
Supplier Countries Count = DISTINCTCOUNT(fact_procurement[supplier_hq_country_key])
```
**Why:** Measure supply chain diversification

#### D. **Distinct Materials**
```dax
Materials Count = DISTINCTCOUNT(fact_procurement[material_key])
```
**Why:** Measure portfolio breadth

#### E. **Avg Spend per Transaction**
```dax
Avg Spend per Transaction =
    DIVIDE([Total Spend EUR], [Transaction Count], 0)
```
**Why:** Understand transaction patterns

#### F. **Latest EPI Score by Country** (calculated column alternative)
```dax
Latest EPI Score =
    VAR LatestYear = MAXX(fact_epi_score, fact_epi_score[year])
    RETURN
        CALCULATE(
            AVERAGE(fact_epi_score[score]),
            fact_epi_score[year] = LatestYear,
            gold_dim_indicator[source_system] = "EPI"
        )
```
**Why:** Show most recent EPI scores (not historical averages)

---

### Priority 2: Advanced Portfolio Measures (4)

#### G. **Spend Exposure at Risk** (Composite Metric)
```dax
Spend Exposure at Risk =
    SUMX(
        SUMMARIZE(
            fact_procurement,
            fact_procurement[supplier_hq_country_key],
            fact_procurement[material_key]
        ),
        VAR MaterialSpend = CALCULATE([Total Spend EUR])
        VAR SupplyConcentration =
            CALCULATE(
                MAX(VALUE(fact_supply_share[share_pct])),
                USERELATIONSHIP(fact_supply_share[country_key], fact_procurement[supplier_hq_country_key])
            ) / 100
        VAR EpiScore = CALCULATE([Avg EPI Score])
        VAR RiskFactor = SupplyConcentration * (1 - DIVIDE(EpiScore, 100, 0))
        RETURN
            MaterialSpend * RiskFactor
    )
```
**Why:** Combines spend, concentration, and EPI into single risk metric

#### H. **Portfolio Diversification Score**
```dax
Diversification Score =
    VAR HHI = [HHI Index]
    RETURN
        1 - HHI  // Scale: 0 = concentrated, 1 = perfectly diversified
```
**Why:** Easier to interpret than HHI (higher = better)

#### I. **Top 3 Countries Spend %**
```dax
Top 3 Countries Spend % =
    VAR Top3Spend =
        CALCULATE(
            [Total Spend EUR],
            TOPN(
                3,
                ALLSELECTED(gold_dim_country),
                [Total Spend EUR],
                DESC
            )
        )
    RETURN
        DIVIDE(Top3Spend, CALCULATE([Total Spend EUR], ALLSELECTED(gold_dim_country)), 0)
```
**Why:** Quick concentration metric for executive summary

#### J. **Material Risk Index** (uses latest supply & EPI data)
```dax
Material Risk Index =
    VAR LatestSupplyYear = MAXX(fact_supply_share, fact_supply_share[year])
    VAR LatestEPIYear = MAXX(fact_epi_score, fact_epi_score[year])
    RETURN
        SUMX(
            SUMMARIZE(
                fact_supply_share,
                fact_supply_share[material_key],
                fact_supply_share[country_key]
            ),
            VAR SupplyShare = CALCULATE(
                VALUE(fact_supply_share[share_pct]) / 100,
                fact_supply_share[year] = LatestSupplyYear
            )
            VAR EPIScore = CALCULATE(
                [Avg EPI Score],
                fact_epi_score[year] = LatestEPIYear
            )
            VAR RiskScore = SupplyShare * (1 - DIVIDE(EPIScore, 100, 0))
            RETURN RiskScore
        )
```
**Why:** Material-level risk metric combining supply concentration and environmental risk

---

## Part 4: Visual Recommendations by Page

### Page 1: Executive Dashboard

**KPIs (4 cards across top):**
1. Total Spend EUR
2. YoY Spend Growth %
3. Supplier Countries Count (NEW)
4. Materials Count (NEW)

**Charts:**
1. Line chart: Total Spend EUR by Month (trend)
2. Column chart: Total Spend EUR by Material (top 10)
3. Map: Total Spend EUR by Supplier Country (colored by EPI score)
4. Donut chart: Spend by Commodity Group

---

### Page 2: Risk & Sustainability Analysis

**KPIs (3 cards):**
1. Spend-Weighted EPI Score
2. % Spend - High EPI (>60)
3. High Risk Material Count

**Charts:**
1. Scatter plot: HHI Index vs Total Spend EUR by Material
2. Table: Material | Max Supply Concentration % | Latest EPI Score | Spend Exposure at Risk
3. Column chart: Spend Exposure at Risk by Material (sorted DESC)
4. Bar chart: Top 10 Countries by Total Spend EUR (colored by EPI)

**Slicer:**
- Year (for fact_supply_share / fact_epi_score filtering)

---

## Part 5: Implementation Steps

### Step 1: Add Priority 1 Measures (6 measures)
These are simple and essential:
- Total Quantity
- Transaction Count
- Supplier Countries Count
- Materials Count
- Avg Spend per Transaction
- Latest EPI Score

### Step 2: Add Priority 2 Measures (4 measures)
More complex but high-impact:
- Spend Exposure at Risk
- Diversification Score
- Top 3 Countries Spend %
- Material Risk Index

### Step 3: Create Visuals in Power BI Desktop
1. Connect to semantic model
2. Build Page 1 (Executive Dashboard)
3. Build Page 2 (Risk & Sustainability)
4. Apply theme and formatting

### Step 4: Test & Validate
- Check that all measures calculate correctly
- Verify relationships are working (e.g., slicers filter visuals)
- Test with different year selections

### Step 5: Export for Portfolio
- High-res screenshots (1920x1080)
- PDF export
- Save .pbix file

---

## Part 6: Troubleshooting

### Common Issues

**Issue 1: "Missing_References" error**
- **Cause:** Report references measures/tables that don't exist
- **Fix:** Delete broken visuals or update references to existing measures

**Issue 2: Blank measures for supply/EPI data**
- **Cause:** Year filters preventing calculation
- **Fix:** Add year slicer or modify measure to use CALCULATE with ALL/ALLSELECTED

**Issue 3: HHI Index not calculating**
- **Cause:** share_pct is a string
- **Fix:** Use VALUE() function to convert (already in existing measure)

**Issue 4: Avg EPI Score same as Spend-Weighted EPI Score**
- **Cause:** Relationship filter not working correctly
- **Fix:** Check relationships between fact_procurement, fact_epi_score, and gold_dim_country

---

## Summary

**Currently Available:** 8 measures (2 procurement, 3 sustainability, 3 risk)

**Recommended to Add:** 10 measures (6 essential + 4 advanced)

**Total After:** 18 portfolio-ready measures

This will give you a complete measure library for professional Power BI reports showcasing:
- ✅ Basic aggregations
- ✅ Time intelligence (YoY)
- ✅ Weighted calculations
- ✅ Risk metrics (HHI, concentration)
- ✅ Composite indicators
- ✅ Context-aware calculations (latest year)

**Next:** Review this guide, then I'll add the 10 recommended measures to `_Measures.tmdl`.
