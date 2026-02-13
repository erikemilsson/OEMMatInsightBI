# Business Rules - OEMMatInsightBI

## Overview

This document defines the business logic, calculations, and rules applied in the OEMMatInsightBI project.

## Supplier Concentration Risk

### Definition
Percentage of global supply of a material from a single country at a specific production stage (extraction or processing).

### Calculation
```
Concentration % = (Supply from Country X / Total Global Supply) × 100
```

### Risk Thresholds

| Threshold | Risk Level | Description |
|-----------|-----------|-------------|
| >50% | **Critical** | Over half of global supply from one country - severe risk |
| 30-50% | **High** | Significant concentration - high vulnerability |
| 20-30% | **Medium** | Moderate concentration - manageable risk |
| <20% | **Low** | Diversified supply - minimal concentration risk |

### Implementation
- Calculated in `v_supply_concentration_risk` view
- Applied to fact_supply_share table
- Used in supply chain risk dashboard

## Environmental Score Aggregation

### EPI Indicator Weighting
Each EPI indicator has a weight (0-1) that reflects its importance in the overall EPI score.

```
Weighted EPI Score = Σ (Indicator Score × Indicator Weight) / Σ (Indicator Weights)
```

### Data Source
- Weights stored in: `gold_dim_indicator.weight` column
- Source: EPI methodology documentation
- Updated annually with new EPI release

### Current Implementation
- Individual indicators stored in `fact_epi_score`
- Weighted aggregation performed in DAX measures (Task 02)
- Overall EPI score available in `silver_epi2024results.EPI` column

## Material Categorization

### Commodity Groups (13 Categories)

1. **Battery metals:** Lithium, Graphite, Nickel, Cobalt, Natural Graphite
2. **Base metals:** Copper, Aluminum/Aluminium, Zinc, Tin, Iron Ore, Lead, Magnesium
3. **Precious metals:** Gold, Silver, Platinum, Palladium, Rhodium, Iridium, Ruthenium
4. **Rare earth elements:** Neodymium, Praseodymium, Cerium, Lanthanum, Yttrium, Rare Earths (Ndpr), Erbium, Thulium, Holmium, Lutetium, Samarium
5. **Specialty metals:** Tungsten, Molybdenum, Titanium, Titanium Metal, Tantalum, Vanadium, Silicon Metal, Niobium, Arsenic, Selenium, Germanium, Hafnium, Rhenium, Zirconium, Bismuth
6. **Industrial minerals:** Limestone, Silica Sand, Kaolin, Strontium, Feldspar, Gypsum
7. **Chemicals:** Phosphorus, Phosphorous, Phosphate Rock, Potash, Sulphur
8. **Energy materials:** Coking Coal
9. **Organic materials:** Natural Rubber, Natural Teak Wood
10. **Manufactured products:** Electronics (controllers, Sensors), Plastic (Abs), Tires (rubber Compound), Steel (High-Tensile)
11. **Specialty gases:** Helium, Neon
12. **Other/Unknown:** Unclassified materials
13. **Placeholder:** Unknown Material (for unmapped values)

### Mapping Logic
- Hardcoded in `silver-to-gold2.Notebook`
- Dictionary: `grp_map = {"Lithium": "Battery metals", ...}`
- Case-insensitive matching
- Unknown materials → "Other/Unknown" group

## Unit Normalization

### Base Unit
All quantities normalized to **kilograms (kg)** for consistency.

### Conversion Factors

| Unit | Symbol | Conversion to kg |
|------|--------|------------------|
| Kilogram | kg | 1.0 |
| Gram | g | 0.001 |
| Milligram | mg | 0.000001 |
| Tonne (Metric Ton) | t | 1000.0 |

### Formula
```
quantity_base (kg) = quantity × conversion_factor
```

### Implementation
```python
unit_map = {
    "kg": 1.0,
    "g": 0.001,
    "mg": 0.000001,
    "t": 1000.0
}
```

Applied in `fact_procurement.quantity_base` calculation.

## Spend Calculation

### Formula
```
spend_eur = quantity_base (kg) × unitprice_eur (EUR/kg)
```

### Business Rules
- Spend is always in EUR (no currency conversion in current implementation)
- Negative spend is invalid (flagged in data quality checks)
- Zero spend is valid (free samples, donated materials)
- NULL spend indicates missing unit price (flagged for review)

### Implementation
- Calculated in `fact_procurement.spend_eur` column
- Used as primary measure for procurement analysis
- Aggregated in DAX: `Total Spend = SUM(fact_procurement[spend_eur])`

## Data Quality Scoring

### Confidence Tiers

| Tier | Confidence Score | Description | Example |
|------|------------------|-------------|---------|
| Tier 1 | 1.00 | Exact match or ISO standard | "USA" → USA (ISO3) |
| Tier 2 | 0.95 | Standard alias | "United States" → USA |
| Tier 3 | 0.90 | Common variant | "Aluminum" → "Aluminium" |
| Tier 4 | 0.85 | Territory mapping | "Hong Kong" → China |
| Tier 5 | 0.80 | Encoding variant | "Türkiye" → Turkey |

### Overall Quality Score
```
data_quality_score = (material_confidence + hq_country_confidence + production_country_confidence) / 3
```

### Quality Categories

| Score Range | Category | Action |
|-------------|----------|--------|
| 0.90-1.00 | High | No action needed |
| 0.70-0.89 | Medium | Review if high-value transaction |
| 0.50-0.69 | Low | Prioritize for alias addition |
| 0.00 | Unmapped | Immediate attention required |

### Implementation
- Confidence tracked in lookup tables: `gold_dim_country_lookup`, `gold_dim_material_lookup`
- Quality score in `fact_procurement.data_quality_score`
- Category in `fact_procurement.quality_category`

## Unmapped Value Handling

### Philosophy
**Never lose data.** If a value cannot be matched to standard dimensions, assign to placeholder dimension and log for review.

### Placeholder Dimensions

**Country Placeholders:**
- Unknown - Africa
- Unknown - Asia
- Unknown - Europe
- Unknown - Americas
- Unknown - Oceania
- Unknown - Global (fallback)

**Material Placeholder:**
- Unknown Material

### Audit Trail
- Unmapped procurement: `gold_unmapped_procurement_audit`
- Unmapped supply: `gold_unmapped_supply_audit`
- Includes: original value, affected spend/share, source row reference

## Date Logic

### Grain
- **Procurement:** Daily (each transaction has a specific date)
- **EPI:** Yearly (annual snapshot, year=2024)
- **WGI:** Yearly (filtered to year=2020)
- **Supply Shares:** Yearly (year=2023)

### Date Dimension
- Range: Dynamically determined from min/max procurement date
- Fallback: current_date - 365 days if no procurement data
- Format: `date_key = yyyyMMdd` (e.g., 20240115 for Jan 15, 2024)

### Fiscal vs Calendar Year
- **Current:** Calendar year only (Jan 1 - Dec 31)
- **Future:** Fiscal year support (see Task 02)

### Time Intelligence
- Year-over-Year (YoY): Compare to same period last year
- Month-over-Month (MoM): Compare to previous month
- Quarter: Calendar quarters (Q1=Jan-Mar, Q2=Apr-Jun, Q3=Jul-Sep, Q4=Oct-Dec)

## Supply Share Cleaning

### Special Value Handling
- **"<1%"**: Converted to 0.5% (midpoint estimate)
- **"%" symbol**: Removed during cleaning
- **NULL/Empty**: Excluded from analysis

### Year Assignment
- All supply share data assigned year = 2023
- Reflects data collection time period
- Updated annually when new EU CRM data released

## Data Lineage

### Bronze → Silver → Gold
```
Source → Bronze (Raw) → Silver (Cleaned) → Gold (Business Logic)
```

### Transformation Checkpoints
1. **Bronze:** Raw data as-is from source
2. **Silver:** Cleaned, validated, standardized column names
3. **Gold:** Business logic applied, dimensions created, surrogate keys generated

### Data Volume Expectations
- **Bronze → Silver:** Same row count (no filtering)
- **Silver → Gold:** May differ (pivoting, aggregation, unmapped filtering)

## Edge Cases

### NULL Handling
- **Required fields:** Reject record, log to audit table
- **Optional fields:** Allow NULL, handle in reports
- **Foreign keys:** Assign to placeholder dimension if unmapped

### Zero Values
- **Quantity = 0:** Invalid - log as data quality issue
- **Price = 0:** Valid - represents free/donated materials
- **Spend = 0:** Valid if price or quantity is zero

### Duplicate Records
- **Bronze/Silver:** Keep duplicates (may be legitimate)
- **Gold:** Deduplicate on natural key before creating fact

## Business Rules Validation

### Automated Checks (Task 07)
- Negative prices → Flag as ERROR
- Negative quantities → Flag as ERROR
- NULL in required fields → Flag as ERROR
- Quality score <0.5 → Flag as WARNING
- Unmapped values → Log to audit table

### Manual Reviews
- Outlier prices (>3 std deviations) → Review quarterly
- New unmapped values → Review monthly
- Concentration risk >50% → Review immediately

## Change Management

### Updating Business Rules
1. Document proposed change in this file
2. Update transformation notebook logic
3. Add unit tests for new rule
4. Re-run pipeline with test data
5. Validate results before production deployment

### Version Control
- All rule changes tracked in Git
- Commit message must reference rule change
- Update project_definition.md if significant change
