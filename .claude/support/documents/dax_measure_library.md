# DAX Measure Library Design - OEMMatInsightBI

**Status:** Design Complete
**Last Updated:** 2025-11-03
**Owner:** Claude Code

## Executive Summary

This document defines the comprehensive DAX measure library for the OEMMatInsightBI semantic model. Based on Task 09 findings, the current model has **no custom DAX measures** - only implicit column aggregations. This design creates a production-ready measure library organized into logical groups to answer 10+ key business questions about procurement spend, sustainability performance, and supply chain risk.

**Key Decisions:**
- ✅ **Measure Groups:** 5 logical groups (Procurement, Time Intelligence, Sustainability, Risk, Advanced)
- ✅ **Core Measures:** 30+ measures covering procurement basics, YoY comparisons, EPI/WGI scoring
- ✅ **Advanced Calculations:** HHI concentration index, spend-weighted scores, composite indicators
- ✅ **What-If Parameters:** Scenario analysis for threshold testing
- ✅ **Performance Patterns:** Variables, DIVIDE for safe division, filter optimization

**Expected Benefits:**
- **Business Value:** Answer all stakeholder questions about ESG impact and procurement decisions
- **Performance:** DirectLake mode with optimized DAX patterns
- **Portfolio Quality:** Demonstrates advanced DAX skills (time intelligence, weighted calculations, statistical metrics)

---

## 1. Semantic Model Structure Overview

### Star Schema Summary

**Fact Tables (3):**
- `fact_procurement` - Procurement transactions (spend, quantity, dates)
- `fact_epi_score` - Environmental Performance Index scores by country/year/indicator
- `fact_supply_share` - Global supply chain shares by material/country/stage

**Dimension Tables (5):**
- `gold_dim_date` - Date dimension (date, year, month, quarter)
- `gold_dim_country` - Countries (country_key, country_name, iso3, region)
- `gold_dim_material` - Materials (material_key, material_name, commodity_group)
- `gold_dim_indicator` - ESG indicators (indicator_code, indicator_name, weight)
- `gold_dim_stage` - Supply chain stages (stage_name: Extraction, Processing, Manufacturing)

### Relationships (8 Active)

```
fact_procurement
  ├─ gold_dim_date (date_key → date_key)
  ├─ gold_dim_country (supplier_hq_country_key → country_key)
  └─ gold_dim_material (material_key → material_key)

fact_epi_score
  ├─ gold_dim_country (country_key → country_key)
  └─ gold_dim_indicator (indicator_key → indicator_key)

fact_supply_share
  ├─ gold_dim_country (country_key → country_key)
  ├─ gold_dim_material (material_key → material_key)
  └─ gold_dim_stage (stage_key → stage_key)
```

---

## 2. Measure Organization Strategy

### Measure Tables (Display Folders)

Create a dedicated `_Measures` table for organization:

**Measure Table Structure:**
```
_Measures (hidden table)
  ├─ 📊 Procurement
  │   ├─ Total Spend
  │   ├─ Total Quantity
  │   ├─ Transaction Count
  │   └─ ...
  ├─ 📅 Time Intelligence
  │   ├─ Total Spend LY
  │   ├─ YoY Spend Growth
  │   └─ ...
  ├─ 🌍 Sustainability
  │   ├─ Avg EPI Score
  │   ├─ Weighted EPI Score
  │   └─ ...
  ├─ ⚠️ Risk
  │   ├─ Supply Risk (Global)
  │   ├─ Supply Concentration Index
  │   └─ ...
  └─ 🔬 Advanced
      ├─ Spend-Weighted EPI
      ├─ Composite Risk Score
      └─ ...
```

**Benefits:**
- Clear measure organization for report authors
- Easy navigation in field list
- Professional semantic model structure
- Simplified measure discovery

### Naming Conventions

**Format:** `[Measure Name] [Unit/Context]`

**Examples:**
- ✅ Good: `Total Spend EUR`, `YoY Spend Growth %`, `Avg EPI Score`
- ❌ Bad: `Spend`, `Growth`, `Score`

**Suffixes:**
- `EUR` - Currency amounts
- `%` - Percentages
- `LY` - Last Year
- `YTD` - Year to Date
- `Avg` - Average
- `Count` - Count distinct

---

## 3. Core Procurement Measures

### 3.1 Basic Aggregations

**Total Spend EUR**
```dax
Total Spend EUR = SUM(fact_procurement[spend_eur])
```
**Business Logic:** Total procurement spend in EUR across all transactions.

---

**Total Quantity (Base Units)**
```dax
Total Quantity = SUM(fact_procurement[quantity_base])
```
**Business Logic:** Total quantity in base units (kg for all materials, normalized during transformation).

---

**Transaction Count**
```dax
Transaction Count = COUNTROWS(fact_procurement)
```
**Business Logic:** Number of procurement transactions.

---

**Average Unit Price EUR**
```dax
Avg Unit Price EUR =
VAR TotalSpend = [Total Spend EUR]
VAR TotalQty = [Total Quantity]
RETURN
    DIVIDE(TotalSpend, TotalQty, 0)
```
**Business Logic:** Average price per base unit (EUR/kg). Uses DIVIDE for safe division (returns 0 if qty = 0).

---

### 3.2 Count Measures

**Supplier Count**
```dax
Supplier Count = DISTINCTCOUNT(fact_procurement[supplier_hq_country_key])
```
**Business Logic:** Number of unique supplier HQ countries.

---

**Material Count**
```dax
Material Count = DISTINCTCOUNT(fact_procurement[material_key])
```
**Business Logic:** Number of distinct materials procured.

---

**Active Procurement Days**
```dax
Active Procurement Days = DISTINCTCOUNT(fact_procurement[date_key])
```
**Business Logic:** Number of days with at least one transaction.

---

### 3.3 Filtering & Context Measures

**Has Procurement?**
```dax
Has Procurement = NOT ISEMPTY(fact_procurement)
```
**Business Logic:** Returns TRUE if there are procurement transactions in current filter context. Useful for conditional formatting.

---

**Procurement Days from Last**
```dax
Days from Last Procurement =
VAR LastProcurementDate = MAX(fact_procurement[date_key])
VAR TodayDateKey = FORMAT(TODAY(), "YYYYMMDD")
RETURN
    DATEDIFF(
        DATE(LEFT(LastProcurementDate, 4), MID(LastProcurementDate, 5, 2), RIGHT(LastProcurementDate, 2)),
        TODAY(),
        DAY
    )
```
**Business Logic:** Number of days since last procurement transaction. Useful for data freshness monitoring.

---

## 4. Time Intelligence Measures

### 4.1 Prior Period Comparisons

**Total Spend LY (Last Year)**
```dax
Total Spend LY =
CALCULATE(
    [Total Spend EUR],
    SAMEPERIODLASTYEAR(gold_dim_date[date])
)
```
**Business Logic:** Total spend for the same period last year.

---

**Total Spend MTD (Month to Date)**
```dax
Total Spend MTD =
CALCULATE(
    [Total Spend EUR],
    DATESMTD(gold_dim_date[date])
)
```

---

**Total Spend YTD (Year to Date)**
```dax
Total Spend YTD =
CALCULATE(
    [Total Spend EUR],
    DATESYTD(gold_dim_date[date])
)
```

---

**Total Spend LYTD (Last Year to Date)**
```dax
Total Spend LYTD =
CALCULATE(
    [Total Spend YTD],
    SAMEPERIODLASTYEAR(gold_dim_date[date])
)
```

---

### 4.2 Growth Measures

**YoY Spend Growth EUR**
```dax
YoY Spend Growth EUR =
VAR CurrentPeriod = [Total Spend EUR]
VAR PriorPeriod = [Total Spend LY]
RETURN
    CurrentPeriod - PriorPeriod
```
**Business Logic:** Absolute change in spend vs last year.

---

**YoY Spend Growth %**
```dax
YoY Spend Growth % =
VAR CurrentPeriod = [Total Spend EUR]
VAR PriorPeriod = [Total Spend LY]
RETURN
    DIVIDE(CurrentPeriod - PriorPeriod, PriorPeriod, 0)
```
**Format:** Percentage with 1 decimal (e.g., 15.3%)

---

**YoY Spend Growth % (Formatted)**
```dax
YoY Spend Growth % Formatted =
FORMAT([YoY Spend Growth %], "+0.0%;-0.0%;0.0%")
```
**Business Logic:** Formatted string with +/- prefix for easier reading.

---

**MoM Spend Growth %**
```dax
MoM Spend Growth % =
VAR CurrentMonth = [Total Spend EUR]
VAR PriorMonth = CALCULATE([Total Spend EUR], DATEADD(gold_dim_date[date], -1, MONTH))
RETURN
    DIVIDE(CurrentMonth - PriorMonth, PriorMonth, 0)
```

---

### 4.3 Moving Averages

**3-Month Moving Avg Spend**
```dax
3M Moving Avg Spend =
VAR Last3Months =
    DATESINPERIOD(
        gold_dim_date[date],
        MAX(gold_dim_date[date]),
        -3,
        MONTH
    )
RETURN
    CALCULATE(
        AVERAGEX(
            VALUES(gold_dim_date[year_month]),
            [Total Spend EUR]
        ),
        Last3Months
    )
```
**Business Logic:** Average monthly spend over last 3 months. Smooths volatility.

---

## 5. Sustainability Measures

### 5.1 EPI Score Measures

**Avg EPI Score**
```dax
Avg EPI Score =
CALCULATE(
    AVERAGE(fact_epi_score[score]),
    gold_dim_indicator[abbrev] = "EPI"
)
```
**Business Logic:** Simple average of EPI scores for supplier countries. Range: 0-100 (higher = better environmental performance).

---

**Weighted EPI Score**
```dax
Weighted EPI Score =
VAR EpiSubIndicators =
    FILTER(
        gold_dim_indicator,
        gold_dim_indicator[source_system] = "EPI"
            && gold_dim_indicator[abbrev] <> "EPI"
            && gold_dim_indicator[type] = "Indicator"
    )
VAR WeightedScores =
    CALCULATE(
        SUMX(
            fact_epi_score,
            fact_epi_score[score] * RELATED(gold_dim_indicator[weight])
        ),
        EpiSubIndicators
    )
VAR TotalWeights =
    CALCULATE(SUM(gold_dim_indicator[weight]), EpiSubIndicators)
RETURN
    DIVIDE(WeightedScores, TotalWeights, 0)
```
**Business Logic:** EPI sub-indicator scores weighted by indicator importance (e.g., climate change 40%, biodiversity 10%). The overall EPI composite (`abbrev = "EPI"`) is excluded — it is itself a weighted aggregate of these sub-indicators, so including it would double-count. WGI indicators (`source_system = "WB"`) are excluded so the numerator and denominator stay on the same source family. EPI data is single-year (2024), so the country × indicator × year grain does not inflate the weight sum. **task-056 (2026-08-04):** the `type = "Indicator"` filter is now explicit — `gold_dim_indicator.weight` is sourced from the Yale `epi2024weights.csv` `EPI Percent` column, which is populated for leaf indicators (Type=Indicator) and NULL for aggregates (EPI composite, PolicyObjective, IssueCategory). Aggregates drop out via `RELATED(weight)=NULL` anyway, but the explicit `type` filter is safer than relying on NULL-weight exclusion. The `abbrev <> "EPI"` filter (task-055's double-count fix) is retained.

---

**Spend-Weighted EPI Score**
```dax
Spend-Weighted EPI Score =
SUMX(
    SUMMARIZE(
        fact_procurement,
        fact_procurement[supplier_hq_country_key]
    ),
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
**Business Logic:** EPI score weighted by spend per country. Shows actual environmental impact of procurement decisions.

---

### 5.2 WGI (Governance) Measures

**Avg WGI Score (All Indicators)**
```dax
Avg WGI Score =
CALCULATE(
    AVERAGE(fact_epi_score[score]),
    gold_dim_indicator[source_system] = "WB"
)
```
**Business Logic:** Average World Bank governance score. Range: -2.5 to +2.5 (higher = better governance).

---

**Governance Score - Control of Corruption**
```dax
WGI - Control of Corruption =
CALCULATE(
    AVERAGE(fact_epi_score[score]),
    gold_dim_indicator[indicator_code] = "CC.EST"
)
```

---

**Governance Score - Rule of Law**
```dax
WGI - Rule of Law =
CALCULATE(
    AVERAGE(fact_epi_score[score]),
    gold_dim_indicator[indicator_code] = "RL.EST"
)
```

---

**Spend-Weighted WGI Score**
```dax
Spend-Weighted WGI Score =
SUMX(
    SUMMARIZE(fact_procurement, fact_procurement[supplier_hq_country_key]),
    VAR CountrySpend = CALCULATE([Total Spend EUR])
    VAR CountryWGI = CALCULATE([Avg WGI Score])
    RETURN CountrySpend * CountryWGI
) / [Total Spend EUR]
```

---

### 5.3 Sustainability Categorization

**% Spend - High EPI Countries**
```dax
% Spend - High EPI (>60) =
VAR HighEPISpend =
    CALCULATE(
        [Total Spend EUR],
        fact_epi_score[score] >= 60,
        gold_dim_indicator[abbrev] = "EPI"
    )
RETURN
    DIVIDE(HighEPISpend, [Total Spend EUR], 0)
```
**Format:** Percentage

---

**% Spend - Medium EPI Countries**
```dax
% Spend - Medium EPI (40-60) =
VAR MediumEPISpend =
    CALCULATE(
        [Total Spend EUR],
        fact_epi_score[score] >= 40,
        fact_epi_score[score] < 60,
        gold_dim_indicator[abbrev] = "EPI"
    )
RETURN
    DIVIDE(MediumEPISpend, [Total Spend EUR], 0)
```

---

**% Spend - Low EPI Countries**
```dax
% Spend - Low EPI (<40) =
VAR LowEPISpend =
    CALCULATE(
        [Total Spend EUR],
        fact_epi_score[score] < 40,
        gold_dim_indicator[abbrev] = "EPI"
    )
RETURN
    DIVIDE(LowEPISpend, [Total Spend EUR], 0)
```

---

## 6. Supply Chain Risk Measures

### 6.1 Supply Risk (Primary) & Supply Concentration (Secondary Lens)

Per **DEC-001 Option B** and § Business Logic → Supply Risk. The primary supply-chain risk measure is a governance- & trade-weighted Herfindahl index (HHI), computed per stage (Extraction/Processing) with the bottleneck stage flagged. A simpler single-country concentration view is retained alongside as a secondary lens.

**Scope boundary (DEC-001):** the SR measures are **gross** supply risk — no import-reliance blend of the two indices into a single SR (Option C), and no recycling (`EoL_RIR`) or substitution (`SI_SR`) filters (Option D). They are not official EU CRM SR values; the report must label them as gross.

#### Supply Risk (Global)

```dax
Supply Risk (Global) =
MAX ( gold_supply_risk[hhi_global] )
```

**Business Logic:** Governance- & trade-weighted HHI over the global production mix (`supply_mix = 'global'`), precomputed in `gold_supply_risk` at grain one row per material × stage × year (DEC-001 Option B; formula `HHI_WGI,t = Σ_c (Sᶜ)² · WGIᶜ · tᶜ`). Reads the precomputed `hhi_global` column.

**Aggregation choice — `MAX`:** the grain is unique on (material × stage × year), so `SUM`, `MAX`, and `AVERAGE` all collapse to the same value at the grain. `MAX` is chosen to match the precedent set by the existing `Supply Concentration Index` measure on `fact_supply_share` (which also uses `MAX` on a single-row-per-grain column) and to make the "return the single row's value" intent explicit; `SUM` would silently double-count across stages/years when the filter context is coarser than the grain, and the report is expected to filter to `is_bottleneck = TRUE` for the headline figure rather than rely on the measure's default aggregation.

#### Supply Risk (EU Sourcing)

```dax
Supply Risk (EU Sourcing) =
MAX ( gold_supply_risk[hhi_eu_sourcing] )
```

**Business Logic:** The same index over the EU sourcing mix (`supply_mix = 'eu_sourcing'`), precomputed in `gold_supply_risk`. Returns `BLANK` when the EU coverage gap leaves `hhi_eu_sourcing = NULL` (a material × stage with global supply data but no EU sourcing rows) — **never 0**, which would misread as "no EU concentration risk" (0 is a legitimate index value meaning perfectly diffuse supply; `MAX` of a `NULL` column yields `BLANK`).

#### Supply Risk Contrast

```dax
Supply Risk Contrast =
DIVIDE ( [Supply Risk (EU Sourcing)], [Supply Risk (Global)] )
```

**Business Logic:** EU-specific exposure relative to global concentration. `1.4` = EU sourcing is 40% more concentrated than the world. `DIVIDE` returns `BLANK` on divide-by-zero by default, so the contrast is **blank when the global index is 0** (a perfectly diffuse global supply) — matching the `NULL`-not-0 rule on `gold_supply_risk.contrast_ratio` (precomputed as `NULL` when `hhi_global` is 0 or when `hhi_eu_sourcing` is `NULL`). Also blank when `[Supply Risk (EU Sourcing)]` is `BLANK` (EU coverage gap), since `DIVIDE` propagates `BLANK` operands to `BLANK`.

#### WGI vintage & aggregation rule

The `WGIᶜ` governance risk weight in `0..1` (1 = worst governance) is derived as the rescaled **inverse** of the mean of all six WGI dimensions for the latest year available per country:

```
WGIᶜ = clamp( (2.5 − mean₆(WGI estimates for c, latest year available)) / 5 , 0, 1 )
```

- **Mean of six** — all six WGI dimensions (Voice & Accountability, Political Stability, Government Effectiveness, Regulatory Quality, Rule of Law, Control of Corruption) are averaged per country.
- **Latest year per country with all six** — the vintage is the most recent year for which the country has all six estimates; a partial vintage is not substituted forward.
- **Fixed-bound clamp** — rescaling uses the **fixed theoretical bounds of the World Bank estimate scale (−2.5..+2.5), not the observed min/max of the loaded set.** This is a reproducibility requirement: with observed bounds, adding a country or a new WGI vintage silently re-ranks every material, and the before/after comparison the model is validated against would not be stable between runs. The clamp handles the rare country whose mean estimate falls outside ±2.5.
- **Inversion is mandatory** — raw WGI runs ≈ −2.5..+2.5 with *higher = better* governance. Used unmodified as a multiplier it would *reward* poorly-governed sourcing — the index would still compute and still look plausible, but every risk ranking would be backwards. The spec requires the inverted, rescaled form.

#### Supply Concentration (Secondary Lens — Retained)

```dax
Supply Concentration Index =
CALCULATE (
    MAX ( fact_supply_share[share_pct] ),
    fact_supply_share[supply_mix] = "global"
)
```

**Business Logic:** Percentage of global supply from a single country (the `MAX` share per material/stage). Retained alongside the weighted model as a simple, intuitive concentration view; the report presents the two side by side. **Filtered to `supply_mix = 'global'`** per spec § Semantic Model and § Business Logic — without this filter the measure silently double-counts once EU sourcing rows land in `fact_supply_share` (task-038_2 unioned the two mixes with a `supply_mix` discriminator; the same migration was applied to `v_supply_concentration_risk` in that task). Thresholds (per § Business Logic → Supplier Concentration Risk): Critical >50%, High >30%, Medium >20%, Low ≤20%.

---

### 6.2 Procurement vs Global Supply Alignment

**Procurement Alignment Score**
```dax
Procurement Alignment Score =
SUMX(
    SUMMARIZE(
        fact_procurement,
        fact_procurement[material_key],
        fact_procurement[supplier_hq_country_key]
    ),
    VAR MaterialKey = fact_procurement[material_key]
    VAR CountryKey = fact_procurement[supplier_hq_country_key]
    VAR ProcurementShare =
        DIVIDE(
            CALCULATE([Total Spend EUR]),
            CALCULATE([Total Spend EUR], ALL(fact_procurement[supplier_hq_country_key]))
        )
    VAR GlobalSupplyShare =
        CALCULATE(
            MAX(fact_supply_share[share_pct]) / 100,
            fact_supply_share[material_key] = MaterialKey,
            fact_supply_share[country_key] = CountryKey
        )
    RETURN
        ABS(ProcurementShare - GlobalSupplyShare)
)
```
**Business Logic:** Measures how closely procurement follows global supply patterns. Lower score = better alignment. Range: 0-1.

---

### 6.3 Composite Risk Score

**Composite Risk Score**
```dax
Composite Risk Score =
VAR ConcentrationRisk = [Supply Risk (Global)]
VAR SustainabilityRisk = 1 - ([Spend-Weighted EPI Score] / 100)
VAR GovernanceRisk = ([Spend-Weighted WGI Score] + 2.5) / 5  // Normalize -2.5 to +2.5 → 0 to 1
RETURN
    (ConcentrationRisk * 0.4) +
    (SustainabilityRisk * 0.3) +
    (GovernanceRisk * 0.3)
```
**Business Logic:** Weighted composite of three risk dimensions. Range: 0-1 (higher = more risk).
- Concentration Risk: 40% weight
- Sustainability Risk: 30% weight
- Governance Risk: 30% weight

---

## 7. Advanced Measures

### 7.1 Ranking & Top N

**Material Rank by Spend**
```dax
Material Rank by Spend =
RANKX(
    ALL(gold_dim_material[material_name]),
    [Total Spend EUR],
    ,
    DESC,
    DENSE
)
```
**Business Logic:** Rank materials by total spend. 1 = highest spend material.

---

**Top 10 Material Spend %**
```dax
Top 10 Material Spend % =
VAR Top10Spend =
    CALCULATE(
        [Total Spend EUR],
        TOPN(10, ALL(gold_dim_material[material_name]), [Total Spend EUR], DESC)
    )
RETURN
    DIVIDE(Top10Spend, CALCULATE([Total Spend EUR], ALL(gold_dim_material)), 0)
```
**Business Logic:** Percentage of spend on top 10 materials. Indicates spend concentration.

---

### 7.2 Statistical Measures

**Unit Price Volatility (StdDev)**
```dax
Unit Price Volatility =
STDEV.P(fact_procurement[unitprice_eur])
```
**Business Logic:** Standard deviation of unit prices. Higher value = more price volatility.

---

**Coefficient of Variation - Unit Price**
```dax
CV - Unit Price =
VAR StdDev = [Unit Price Volatility]
VAR Mean = [Avg Unit Price EUR]
RETURN
    DIVIDE(StdDev, Mean, 0)
```
**Business Logic:** Normalized volatility measure (volatility / mean). Allows comparison across materials.

---

### 7.3 Pareto Analysis

**Cumulative Spend %**
```dax
Cumulative Spend % =
VAR CurrentMaterialSpend = [Total Spend EUR]
VAR MaterialsUpToCurrent =
    FILTER(
        ALL(gold_dim_material[material_name]),
        [Total Spend EUR] >= CurrentMaterialSpend
    )
VAR CumulativeSpend =
    CALCULATE(
        [Total Spend EUR],
        MaterialsUpToCurrent
    )
RETURN
    DIVIDE(CumulativeSpend, CALCULATE([Total Spend EUR], ALL(gold_dim_material)), 0)
```
**Business Logic:** Cumulative percentage of spend when materials sorted by spend descending. Used for Pareto (80/20) analysis.

---

**Is Top 80% Spend?**
```dax
Is Top 80% Spend =
IF([Cumulative Spend %] <= 0.8, "Top 80%", "Remaining 20%")
```

---

## 8. What-If Parameters

### 8.1 EPI Threshold Parameter

**Create Parameter:**
```dax
// In Power BI Desktop: Modeling > New Parameter
EPI Threshold = GENERATESERIES(0, 100, 5)  // 0, 5, 10, ..., 95, 100
```

**Use in Measure:**
```dax
% Spend Above EPI Threshold =
VAR ThresholdValue = SELECTEDVALUE('EPI Threshold'[EPI Threshold], 50)
VAR AboveThresholdSpend =
    CALCULATE(
        [Total Spend EUR],
        fact_epi_score[score] >= ThresholdValue
    )
RETURN
    DIVIDE(AboveThresholdSpend, [Total Spend EUR], 0)
```

---

### 8.2 Risk Tolerance Parameter

**Create Parameter:**
```dax
Risk Tolerance = {"Low (Conservative)", "Medium (Balanced)", "High (Aggressive)"}
```

**Use in Measure:**
```dax
Risk Assessment =
VAR RiskLevel = SELECTEDVALUE('Risk Tolerance'[Value], "Medium (Balanced)")
VAR CompositeRisk = [Composite Risk Score]
VAR Threshold =
    SWITCH(
        RiskLevel,
        "Low (Conservative)", 0.3,
        "Medium (Balanced)", 0.5,
        "High (Aggressive)", 0.7,
        0.5
    )
RETURN
    IF(CompositeRisk <= Threshold, "Acceptable", "Review Required")
```

---

## 9. Calculation Groups (Advanced)

### Time Intelligence Calculation Group

**Create Calculation Group:** `Time Intelligence`

**Calculation Items:**

**Current Period**
```dax
SELECTEDMEASURE()
```

**Last Year**
```dax
CALCULATE(SELECTEDMEASURE(), SAMEPERIODLASTYEAR(gold_dim_date[date]))
```

**YoY Growth %**
```dax
VAR CurrentValue = SELECTEDMEASURE()
VAR PriorValue = CALCULATE(SELECTEDMEASURE(), SAMEPERIODLASTYEAR(gold_dim_date[date]))
RETURN DIVIDE(CurrentValue - PriorValue, PriorValue, 0)
```

**YTD**
```dax
CALCULATE(SELECTEDMEASURE(), DATESYTD(gold_dim_date[date]))
```

**Usage:** Apply to any base measure (e.g., Total Spend EUR) to get time intelligence variants automatically.

---

## 10. Performance Optimization Patterns

### 10.1 Use Variables for Readability

**Bad:**
```dax
YoY Growth % = DIVIDE([Total Spend EUR] - CALCULATE([Total Spend EUR], SAMEPERIODLASTYEAR(gold_dim_date[date])), CALCULATE([Total Spend EUR], SAMEPERIODLASTYEAR(gold_dim_date[date])), 0)
```

**Good:**
```dax
YoY Growth % =
VAR CurrentPeriod = [Total Spend EUR]
VAR PriorPeriod = [Total Spend LY]
RETURN
    DIVIDE(CurrentPeriod - PriorPeriod, PriorPeriod, 0)
```

---

### 10.2 Avoid Expensive Row Context Operations

**Bad (Slow):**
```dax
// Row-by-row iteration
Total Spend Slow =
SUMX(
    fact_procurement,
    fact_procurement[quantity_base] * fact_procurement[unitprice_eur]
)
```

**Good (Fast):**
```dax
// Use pre-calculated column
Total Spend Fast = SUM(fact_procurement[spend_eur])
```

**Recommendation:** Calculate `spend_eur` in data transformation layer, not in DAX.

---

### 10.3 Filter Context Optimization

**Bad:**
```dax
// Multiple CALCULATE calls
High EPI Spend =
    CALCULATE(
        CALCULATE(
            [Total Spend EUR],
            fact_epi_score[score] >= 60
        ),
        gold_dim_indicator[abbrev] = "EPI"
    )
```

**Good:**
```dax
// Single CALCULATE with multiple filters
High EPI Spend =
    CALCULATE(
        [Total Spend EUR],
        fact_epi_score[score] >= 60,
        gold_dim_indicator[abbrev] = "EPI"
    )
```

---

### 10.4 Use DIVIDE Instead of Division Operator

**Bad:**
```dax
Avg Price = [Total Spend EUR] / [Total Quantity]
// Returns error if Total Quantity = 0
```

**Good:**
```dax
Avg Price = DIVIDE([Total Spend EUR], [Total Quantity], 0)
// Returns 0 if Total Quantity = 0
```

---

## 11. Measure Documentation Template

For each measure, document in measure description:

```
[Measure Name]

Business Logic:
- What does this measure calculate?
- How is it used in decision-making?

Calculation:
- High-level formula description
- Dependencies on other measures

Filter Context:
- Default filters applied
- Important slicer interactions

Format:
- Currency, Percentage, Integer, etc.
- Decimal places

Example Values:
- Typical range (e.g., 0-100 for percentages)

Owner: [Name]
Last Updated: [Date]
```

**Example:**
```
Spend-Weighted EPI Score

Business Logic:
Calculates the average Environmental Performance Index score weighted by procurement spend per country. This shows the actual environmental impact of procurement decisions, giving more weight to countries where we spend more.

Calculation:
For each supplier country, multiply total spend by average EPI score. Sum across all countries and divide by total spend. Result is weighted average EPI score.

Filter Context:
Respects all slicers (date, material, region). Filters only to EPI indicators (excludes WGI).

Format:
Decimal number, 1 decimal place (e.g., 58.3)

Example Values:
Range: 0-100 (higher = better environmental performance)
Typical: 45-65

Owner: Data Engineering Team
Last Updated: 2025-11-03
```

---

## 12. Testing Strategy

### Unit Tests for Measures

**Test 1: Basic Aggregation Accuracy**
```
Test: Total Spend EUR = SUM of spend_eur column
Data: Filter to single material (e.g., Lithium)
Expected: Measure value matches Excel SUM of source data
```

**Test 2: Time Intelligence Correctness**
```
Test: YoY Spend Growth % calculation
Data: 2023 = 1,000 EUR, 2024 = 1,200 EUR
Expected: YoY Growth = 20% (200/1,000)
```

**Test 3: Weighted Calculations**
```
Test: Spend-Weighted EPI Score
Data:
  - Country A: 1,000 EUR spend, EPI = 60
  - Country B: 500 EUR spend, EPI = 90
Expected: (1000*60 + 500*90) / 1500 = 70
```

**Test 4: Division by Zero Handling**
```
Test: Avg Unit Price EUR with zero quantity
Data: Filter to date with no transactions
Expected: 0 (not error)
```

**Test 5: Filter Context**
```
Test: % Spend - High EPI Countries
Data: Total spend = 10,000 EUR, High EPI spend = 6,000 EUR
Expected: 60% (0.6)
```

### Integration Tests with Visuals

**Visual 1: Matrix - Material x Time**
```
Rows: Material Name
Columns: Year
Values: Total Spend EUR, YoY Spend Growth %

Validation:
- YoY Growth % shows BLANK for first year (no prior year)
- Growth % calculated correctly for each material/year
- Totals row shows overall YoY growth
```

**Visual 2: Scatter Chart - Spend vs Risk**
```
X-Axis: Total Spend EUR
Y-Axis: Composite Risk Score
Legend: Commodity Group

Validation:
- Each material plotted correctly
- Risk score in range 0-1
- Tooltips show all related measures
```

**Visual 3: Waterfall - Spend Breakdown**
```
Category: Material (Top 10) + Others
Values: Total Spend EUR

Validation:
- Top 10 materials sorted by spend descending
- "Others" category = sum of remaining materials
- Total matches overall Total Spend EUR
```

---

## 13. Implementation Checklist

### Phase 1: Setup (0.5 days)
- [ ] Open semantic model in Power BI Desktop
- [ ] Create `_Measures` table (hidden, no columns)
- [ ] Create display folders: Procurement, Time Intelligence, Sustainability, Risk, Advanced
- [ ] Test DirectLake connection to warehouse

### Phase 2: Core Measures (1 day)
- [ ] **Procurement (10 measures):**
  - [ ] Total Spend EUR
  - [ ] Total Quantity
  - [ ] Transaction Count
  - [ ] Avg Unit Price EUR
  - [ ] Supplier Count
  - [ ] Material Count
  - [ ] Active Procurement Days
  - [ ] Has Procurement
  - [ ] Days from Last Procurement
  - [ ] Avg Unit Price EUR
- [ ] Test each measure with sample filters
- [ ] Document measure descriptions

### Phase 3: Time Intelligence (1 day)
- [ ] **Prior Period Measures (4):**
  - [ ] Total Spend LY
  - [ ] Total Spend MTD
  - [ ] Total Spend YTD
  - [ ] Total Spend LYTD
- [ ] **Growth Measures (4):**
  - [ ] YoY Spend Growth EUR
  - [ ] YoY Spend Growth %
  - [ ] YoY Spend Growth % Formatted
  - [ ] MoM Spend Growth %
- [ ] **Moving Averages (1):**
  - [ ] 3M Moving Avg Spend
- [ ] Test with date slicers (year, quarter, month)
- [ ] Validate edge cases (first year, no data)

### Phase 4: Sustainability Measures (1 day)
- [ ] **EPI Measures (4):**
  - [ ] Avg EPI Score
  - [ ] Weighted EPI Score
  - [ ] Spend-Weighted EPI Score
  - [ ] % Spend - High/Medium/Low EPI
- [ ] **WGI Measures (4):**
  - [ ] Avg WGI Score
  - [ ] WGI - Control of Corruption
  - [ ] WGI - Rule of Law
  - [ ] Spend-Weighted WGI Score
- [ ] Test with country filters
- [ ] Validate score ranges (EPI: 0-100, WGI: -2.5 to +2.5)

### Phase 5: Risk Measures (0.5 days)
- [ ] **Supply Risk (3):**
  - [ ] Supply Risk (Global)
  - [ ] Supply Risk (EU Sourcing)
  - [ ] Supply Risk Contrast
- [ ] **Supply Concentration (1):**
  - [ ] Supply Concentration Index (filtered to supply_mix = "global")
- [ ] **Advanced Risk (2):**
  - [ ] Procurement Alignment Score
  - [ ] Composite Risk Score
- [ ] Test with material filters
- [ ] Validate Supply Risk Contrast blanks when global index is 0

### Phase 6: Advanced Measures (0.5 days)
- [ ] **Ranking (2):**
  - [ ] Material Rank by Spend
  - [ ] Top 10 Material Spend %
- [ ] **Statistical (2):**
  - [ ] Unit Price Volatility
  - [ ] CV - Unit Price
- [ ] **Pareto (2):**
  - [ ] Cumulative Spend %
  - [ ] Is Top 80% Spend
- [ ] Test sorting and filtering behavior

### Phase 7: What-If Parameters (0.5 days)
- [ ] Create EPI Threshold parameter (0-100, step 5)
- [ ] Create Risk Tolerance parameter (3 values)
- [ ] Create measures using parameters
- [ ] Test parameter interactions with visuals

### Phase 8: Documentation & Testing (0.5 days)
- [ ] Add descriptions to all measures
- [ ] Create measure reference document
- [ ] Run unit tests (5 tests above)
- [ ] Run integration tests with visuals
- [ ] Performance test with large dataset
- [ ] Publish to Fabric workspace

---

## 14. Performance Benchmarks

**Expected Performance (DirectLake Mode):**

| Visual Type | Measure Count | Expected Response Time | Notes |
|-------------|---------------|------------------------|-------|
| **Matrix** | 3-5 measures | <500ms | Procurement measures only |
| **Line Chart** | 2 time series | <300ms | Total Spend EUR + LY |
| **Scatter Plot** | 3 measures | <1s | Spend vs Risk vs EPI |
| **Table (Top 100)** | 10 measures | <1s | All measure types |
| **Card** | 1 KPI | <100ms | Single aggregation |

**Optimization Triggers:**
- If matrix with 10+ measures takes >2s: Review DAX for row context operations
- If scatter plot takes >3s: Consider aggregation table for materials
- If page load >5s: Review visual count and interactions

---

## 15. Business Questions Answered

### Procurement Analysis
1. ✅ **What is our total spend by material/supplier/region?**
   - Use: `Total Spend EUR` with material/country/region slicers

2. ✅ **How has spending changed over time (YoY, MoM)?**
   - Use: `YoY Spend Growth %`, `MoM Spend Growth %`

3. ✅ **What is our supplier concentration by material?**
   - Use: `Supplier Count`, `Top 10 Material Spend %`

4. ✅ **Which materials have the highest unit cost volatility?**
   - Use: `Unit Price Volatility`, `CV - Unit Price`

### Sustainability Performance
5. ✅ **What is the average environmental performance of our suppliers?**
   - Use: `Avg EPI Score`, `Spend-Weighted EPI Score`

6. ✅ **What percentage of spend goes to high/medium/low EPI countries?**
   - Use: `% Spend - High EPI`, `% Spend - Medium EPI`, `% Spend - Low EPI`

7. ✅ **How do supplier HQ countries compare to production countries in governance?**
   - Use: `Avg WGI Score` with country dimension filters

8. ✅ **Which materials are sourced from high-risk regions?**
   - Use: `Composite Risk Score` filtered by material

### Supply Chain Risk
9. ✅ **What is our exposure to concentrated supply chains?**
   - Use: `Supply Risk (Global)`, `Supply Risk Contrast`

10. ✅ **Which critical materials have >50% supply from one country?**
    - Use: `Supply Concentration Index`, `Supply Risk (Global)`

11. ✅ **How does our procurement align with global supply patterns?**
    - Use: `Procurement Alignment Score`

---

## 16. Future Enhancements

### Predictive Measures (Power BI Premium)
```dax
Forecasted Spend (6M) =
FORECAST(
    [Total Spend EUR],
    6,  // Forecast 6 months ahead
    MONTH,
    gold_dim_date[date]
)
```

### Anomaly Detection
```dax
Is Spend Anomaly =
VAR CurrentSpend = [Total Spend EUR]
VAR AvgSpend = [3M Moving Avg Spend]
VAR StdDev = STDEV.P([Total Spend EUR])
VAR ZScore = DIVIDE(CurrentSpend - AvgSpend, StdDev, 0)
RETURN
    IF(ABS(ZScore) > 2, "Anomaly", "Normal")
```

### Custom Hierarchies
- Date: Year > Quarter > Month > Week > Day
- Geography: Region > Country > Supplier
- Material: Commodity Group > Material Type > Material

---

## 17. References

### DAX Best Practices
- **SQLBI DAX Guide:** https://dax.guide/
- **SQLBI Best Practices:** https://www.sqlbi.com/articles/best-practices-using-summarize-and-addcolumns/
- **Time Intelligence Patterns:** https://www.sqlbi.com/articles/time-intelligence-in-power-bi-desktop/

### Performance Optimization
- **DAX Optimization:** https://www.sqlbi.com/articles/optimizing-dax-expressions-involving-aggregations/
- **DirectLake Performance:** https://learn.microsoft.com/fabric/get-started/direct-lake-overview

---

**Document Status:** Design complete and ready for implementation
**Implementation Effort:** 5 days (setup to final testing)
**Next Task:** Task 04 (RLS Security Strategy Design)

---

## Summary: 30+ DAX Measures by Category

**Procurement (10):** Total Spend EUR, Total Quantity, Transaction Count, Avg Unit Price EUR, Supplier Count, Material Count, Active Procurement Days, Has Procurement, Days from Last Procurement

**Time Intelligence (9):** Total Spend LY/MTD/YTD/LYTD, YoY Growth EUR/%, MoM Growth %, 3M Moving Avg

**Sustainability (8):** Avg EPI Score, Weighted EPI Score, Spend-Weighted EPI, % Spend by EPI Category, Avg WGI Score, WGI indicators, Spend-Weighted WGI

**Risk (6):** Supply Risk (Global), Supply Risk (EU Sourcing), Supply Risk Contrast, Supply Concentration Index, Procurement Alignment, Composite Risk Score

**Advanced (6):** Material Rank, Top 10 %, Unit Price Volatility, CV, Cumulative Spend %, Is Top 80%

**Total: 40+ measures** covering all business questions with professional DAX patterns.
