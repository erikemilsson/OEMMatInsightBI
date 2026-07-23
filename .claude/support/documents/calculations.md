# Key Calculations Reference

## Procurement Calculations

### Spend EUR
```
spend_eur = quantity_base (kg) × unitprice_eur (EUR/kg)
```

> ⚠️ **The "EUR/kg" basis is an ASSUMPTION, not a verified fact.** Bronze carries a
> per-row `Unit`, so the source price may be per that unit rather than per kilogram —
> in which case spend for a tonne-denominated row is inflated ×1000 today. The
> notebook exposes a `UNITPRICE_BASIS` switch (`"per_kg"` | `"per_row_unit"`) with
> both branches wired and tested; confirming the answer against the Azure SQL source
> is a one-token edit. Until it is confirmed, treat spend on non-kg rows as
> provisional. Tracked as task-030 AC3.
>
> If the answer turns out to be `per_row_unit`, `spend_eur = quantity (original) ×
> unitprice_eur` with **no** conversion on the price side, and
> `populate_low_confidence_audit`'s `spend_impact` must be aligned to the same basis.

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

**Units outside this map yield `NULL`, not a passthrough** (task-030). A row whose
unit is `lb`, `tonne`, or anything else not listed gets `quantity_base = NULL` **and**
`spend_eur = NULL`. Both columns are therefore nullable.

This replaced a fallback of `.otherwise(quantity)`, which kept the row's *raw
magnitude* while labelling it kg — so a tonne row understated by ×1000 and nothing
anywhere reported it. `NULL` is the honest answer: we do not know the kg equivalent.
`SUM()` skips it, and the affected rows are named in **`gold_unmapped_unit_audit`**
(unit, row count, original quantity total), with the full observed unit domain printed
on every gold run.

The lookup is `lower(trim(unit))` — under NULL-on-miss semantics, stray whitespace
alone would otherwise drop a good row out of spend.

> The same four-unit domain is mirrored as an **advisory** DQ rule ("Unit In
> Conversion Domain") on `silver_procurement` in `data_quality_checks.Notebook`. It is
> deliberately *not* in `BLOCKING_CHECKS` — see `data_quality_framework.md § 6`.
> Fabric notebooks cannot import from each other, so the list is duplicated by
> necessity: **change both together.**

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
