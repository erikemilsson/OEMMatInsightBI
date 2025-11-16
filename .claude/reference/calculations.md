# Key Calculations Reference

## Procurement Calculations

### Spend EUR
```
spend_eur = quantity_base (kg) × unitprice_eur (EUR/kg)
```

### Quantity Base (Unit Normalization)
```
quantity_base = quantity × conversion_factor

conversion_factors = {
    "kg": 1.0,
    "g": 0.001,
    "mg": 0.000001,
    "t": 1000.0
}
```

### Data Quality Score
```
data_quality_score = (material_confidence + hq_country_confidence + prod_country_confidence) / 3
```

### Quality Category
```
IF data_quality_score >= 0.90 THEN "High"
ELSE IF data_quality_score >= 0.70 THEN "Medium"
ELSE IF data_quality_score >= 0.50 THEN "Low"
ELSE "Unmapped"
```

## Supply Concentration Calculations

### Supply Share Percentage
```
share_pct = Clean(<source_share_string>)

Clean rules:
- Remove "%" symbol
- Convert "<1%" to 0.5 (midpoint estimate)
- Cast to DOUBLE
```

### Unmapped Impact Score
```
unmapped_impact_score = share_pct (if value is unmapped, else 0)
```

## Sustainability Metrics (Planned - Task 02)

### Weighted EPI Score
```dax
Weighted EPI Score = 
SUMX(
    fact_epi_score,
    fact_epi_score[score] * RELATED(gold_dim_indicator[weight])
) / SUMX(fact_epi_score, RELATED(gold_dim_indicator[weight]))
```

### Spend by EPI Category
```dax
High EPI Spend = 
CALCULATE(
    [Total Spend],
    FILTER(gold_dim_country, gold_dim_country[avg_epi_score] >= 70)
)
```

## Risk Calculations

### Concentration Risk Level
```
IF max_share_pct > 50 THEN "Critical"
ELSE IF max_share_pct > 30 THEN "High"
ELSE IF max_share_pct > 20 THEN "Medium"
ELSE "Low"
```

## Date Calculations

### Date Key Generation
```
date_key = YEAR × 10000 + MONTH × 100 + DAY

Example: 2024-01-15 → 20240115
```

### Fiscal Periods (Not implemented - calendar year only)
```
quarter = CEILING(month / 3.0)
```

## Surrogate Key Generation

### xxhash64 Function
```python
from pyspark.sql.functions import xxhash64, concat_ws

surrogate_key = xxhash64(concat_ws("||", col1, col2, ...))
```

Example:
```
country_key = xxhash64("USA") = -8844688327304771973
material_key = xxhash64("Lithium") = 1234567890123456789
```
