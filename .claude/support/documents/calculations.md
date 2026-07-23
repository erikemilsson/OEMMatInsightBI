# Key Calculations Reference

## Procurement Calculations

### Spend EUR
```
spend_eur = quantity_original × unitprice_eur      (per_row_unit basis)
```

`unitprice_eur` is **per the row's own `Unit`** — EUR/kg for a `kg` row, EUR/piece for
a `pcs` row. Confirmed against the live source 2026-07-23 (task-030 AC3): the unit
domain is `{kg, pcs}`, and `pcs` (electronic control units, tyres) can only be priced
per piece. So spend is the plain line total `quantity × unitprice`, and it does **not**
go through the kg normalization.

> **This is deliberately independent of `quantity_base`.** A non-mass unit like `pcs`
> has `quantity_base = NULL` (no kg equivalent) but a perfectly real `spend_eur`. The
> earlier `per_kg` formula `spend = quantity_base × unitprice` tied the two together and
> collapsed every `pcs` row's spend to NULL — €1.74M of real procurement (the largest
> category) silently lost. `per_row_unit` fixes that while leaving `kg` rows unchanged
> (for a `kg` row, `quantity_original == quantity_base`).
>
> `populate_low_confidence_audit`'s `spend_impact` already uses this same
> `quantity × unitprice` form, so the two are now consistent.
>
> The notebook keeps a `UNITPRICE_BASIS` switch (`"per_row_unit"` | `"per_kg"`); it is
> set to `per_row_unit`. Do not switch to `per_kg` with the current data — it re-breaks
> `pcs` spend.

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

**Units outside this map yield `quantity_base = NULL`, not a passthrough** (task-030).
A row whose unit is `pcs`, `lb`, or anything else not listed has no kg mass, so
`quantity_base` is NULL. `quantity_base` is therefore nullable. **`spend_eur` is not
affected** — it is `quantity × unitprice` regardless of unit (see Spend EUR above).

This replaced a fallback of `.otherwise(quantity)`, which kept the row's *raw
magnitude* while labelling it kg — so a piece count or a tonne would masquerade as kg
mass and nothing reported it. `NULL` is the honest answer for the mass: we do not know
the kg equivalent of a piece. `SUM(quantity_base)` skips it, and the affected rows are
named in **`gold_unmapped_unit_audit`** (unit, row count, original quantity total), with
the full observed unit domain printed on every gold run.

The lookup is `lower(trim(unit))` — stray whitespace would otherwise strip the kg mass
off a genuine mass row (spend survives, but the row would wrongly land in the no-mass
audit).

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
