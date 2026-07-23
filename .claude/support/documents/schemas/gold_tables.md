# Gold Layer Table Schemas

## Fact Tables

### fact_procurement
Grain: One row per procurement transaction
```
date_key                    INTEGER (yyyyMMdd; 19000101 = UNKNOWN DATE, never NULL)
material_key                BIGINT (xxhash64)
supplier_hq_country_key     BIGINT (xxhash64)
production_country_key      BIGINT (xxhash64)
quantity_base               DOUBLE, NULLABLE (kg; NULL for non-mass units, e.g. pcs)
unitprice_eur               DOUBLE (per the row's source Unit — EUR/kg, EUR/piece)
spend_eur                   DOUBLE (quantity_original × unitprice_eur; per_row_unit)
data_quality_score          DOUBLE (0-1 scale)
quality_category            STRING (High/Medium/Low/Unmapped)
source_row_id               BIGINT (traces back to the silver transaction)
```

**`date_key` is never NULL** (task-030). A transaction whose source date is NULL or
fails the cast is routed to the explicit **UNKNOWN-DATE member `19000101`** in
`gold_dim_date` rather than left unjoined. A NULL key matches no dimension row, so in
DirectLake those rows would vanish from every date-filtered visual while still counting
in unfiltered totals — cards and time-series would not reconcile. It would also break
the BLOCKING referential-integrity check (`fact_procurement.date_key →
gold_dim_date`), which counts NULL as an orphan at 0% tolerance.

**`quantity_base` is nullable** (task-030) — NULL whenever the row's unit is outside
the four-entry mass map (e.g. `pcs`, which has no kg equivalent). **`spend_eur` is
computed for every row** as `quantity × unitprice` (per_row_unit, task-030 AC3), so a
`pcs` row has NULL `quantity_base` but a real `spend_eur`. Anything summing
`quantity_base` must expect NULLs; the no-mass rows are named in
`gold_unmapped_unit_audit`. See `calculations.md § Spend EUR`.

### fact_supply_share
Grain: One row per material × stage × country × year
```
material_key                BIGINT
stage_key                   BIGINT
country_key                 BIGINT
year                        INTEGER (2023)
share_pct                   DOUBLE (0-100)
data_quality_score          DOUBLE
quality_category            STRING
has_unmapped_material       BOOLEAN
has_unmapped_country        BOOLEAN
unmapped_impact_score       DOUBLE
```

### fact_epi_score
Grain: One row per country × indicator × year
```
country_key                 BIGINT
indicator_key               BIGINT
year                        INTEGER (2024)
score                       DOUBLE
```

## Dimension Tables

### gold_dim_country
Grain: One row per country
```
country_key                 BIGINT (PK)
iso3                        STRING
iso_numeric                 INTEGER
wb_code                     STRING
country_name_std            STRING
region                      STRING
is_placeholder              BOOLEAN
```

### gold_dim_date
Grain: One row per day, **plus exactly one UNKNOWN-DATE member**
```
date_key                    INTEGER (PK, yyyyMMdd)
date                        DATE
year                        INTEGER
month                       INTEGER
day                         INTEGER
month_name                  STRING
quarter                     INTEGER
day_of_week                 INTEGER
week_of_year                INTEGER
```

**UNKNOWN-DATE member:** `date_key = 19000101` / `date = 1900-01-01`, carrying the same
derived attributes as any real day (built by the same `date_attributes()` helper, so it
cannot drift out of schema agreement). It is the target for transactions with no usable
date — see `fact_procurement` above. `19000101` rather than `-1` because every other
`date_key` is `yyyyMMdd` and downstream SQL/DAX may parse it back to a date.

> **If `gold_dim_date` is ever marked as a Power BI date table**, exclude this member
> from the marked table rather than deleting it from the dimension — it breaks date
> contiguity (1900, then a jump to the real range). It is not marked as a date table
> today (no `dataCategory: Time` in the TMDL).

### gold_dim_material
Grain: One row per material
```
material_key                BIGINT (PK)
material_name_std           STRING
commodity_group             STRING (13 categories)
unit_base                   STRING ("kg")
is_placeholder              BOOLEAN
```

### gold_dim_indicator
Grain: One row per EPI/WGI indicator
```
indicator_key               BIGINT (PK)
source_system               STRING ("EPI" or "WB")
type                        STRING
abbrev                      STRING
variable_name               STRING
policyobjective             STRING
issuecategory               STRING
indicator_code              STRING
weight                      FLOAT
description                 STRING
parent_indicator            BIGINT (nullable)
```

### gold_dim_stage
Grain: One row per production stage
```
stage_key                   BIGINT (PK)
stage_code                  STRING ("E" or "P")
stage_name                  STRING ("Extraction" or "Processing")
```

## Audit & Observability Tables

`gold_tables.md` previously documented only facts and dimensions, so the audit and
observability tables the gold notebook writes had no schema home. They are listed here
for inventory completeness; **`data_quality_architecture.md` remains the detailed
reference** for how they are populated and consumed.

### gold_unmapped_unit_audit
Grain: One row per unrecognized unit (per load window)
```
unmapped_unit               STRING (lower/trimmed source unit outside the conversion map)
row_count                   BIGINT
quantity_original_sum       DOUBLE (unconverted — the kg equivalent is unknown)
detected_timestamp          TIMESTAMP
```
Added by task-030. Deliberately its **own** table rather than rows in
`gold_unmapped_procurement_audit`: that table is consumed wholesale by
`populate_gap_registry`, which would turn a unit into a `gap_type='unit'` registry entry
and inflate the "unmapped records" dashboard metric. An unrecognized unit is a
*conversion-map* gap, not a *dimension-alias* gap. Empty when the source only uses
kg/g/mg/t.

### Other gold tables written by `silver-to-gold2`

| Table | Grain / purpose |
|---|---|
| `gold_unmapped_procurement_audit` | One row per unmapped value occurrence (see `data_quality_architecture.md § [2]`) |
| `gold_unmapped_supply_audit` | Same, for the supply-share fact |
| `gold_data_gaps` | One row per country × country_role — EPI/WGI coverage flags |
| `gold_data_gaps_summary` | Coverage rollup for KPI cards |
| `gold_country_coverage_matrix` | Country presence across all source datasets |
| `gold_data_quality_metrics` / `gold_data_quality_dashboard` | Quality metric rollups |
| `gold_dim_country_lookup` / `gold_dim_material_lookup` | Alias-aware join surfaces |
| `mapping_country_aliases_confidence` / `mapping_material_aliases_confidence` | Alias tables with confidence scores |

> `gold_quality_history` and `gold_gap_registry` are written by
> `data_quality_checks.Notebook`, not by `silver-to-gold2` — see
> `data_quality_architecture.md`.
