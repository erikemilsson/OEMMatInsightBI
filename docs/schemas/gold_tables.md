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
Grain: One row per material × stage × country × year × **supply_mix**
```
material_key                BIGINT
stage_key                   BIGINT
country_key                 BIGINT
year                        INTEGER (2023)
supply_mix                  STRING ('global' | 'eu_sourcing')
share_pct                   DOUBLE (0-100)
t                           DOUBLE (nullable)
data_quality_score          DOUBLE
quality_category            STRING
has_unmapped_material       BOOLEAN
has_unmapped_country        BOOLEAN
unmapped_impact_score       DOUBLE
source_row_id               BIGINT
wgi_year                    INTEGER (nullable)
wgi_weight                  DOUBLE (nullable, 0-1)
```

**`supply_mix` is part of the grain** (task-038_2). The two mixes are complementary
measurements, never partitions of one population — a `global` row and an `eu_sourcing`
row on the same (material, stage, country, year) are both real and must not be summed
together. `grain_checks@data_quality_checks` declares the same five-column key.

**`t` is the DEC-001 trade parameter** `tᶜ` (0.8 EU, 1.0 baseline non-EU, >1
export-restricted). Nullable: NULL where the source carries no trade parameter. On a
territory rollup it combines as a **share-weighted mean**, which preserves Σ(S·t)
exactly across the merge.

**`wgi_weight` is the DEC-001 governance weight** `WGIᶜ` (task-038_3), in `0..1` where
**1 = worst governance** — the rescaled *inverse* of the mean of all six WGI dimensions,
clamped against the FIXED −2.5..+2.5 theoretical bounds of the World Bank estimate scale
(never the observed min/max of the loaded set; see `calculations.md` / spec_v1 § Business
Logic & Calculations → Supply Risk). `wgi_year` records which vintage each country landed
on — the latest year in which that country carries all six dimensions.

**Both WGI columns are nullable, and NULL means "no usable governance vintage", not
zero.** A country with fewer than six dimensions in every year, or absent from
`silver_wgi` entirely (including the `Unknown - Global` placeholder), keeps its supply
rows with `wgi_weight IS NULL`. The gap is measured by `check_unmapped` at build time
rather than dropped. Anything multiplying by `wgi_weight` must decide explicitly how to
treat NULL — 0.0 is a legitimate weight meaning *best governance*, so coercing NULL to 0
would read as a perfectly-governed country.

### fact_epi_score
Grain: One row per country × indicator × year
```
country_key                 BIGINT
indicator_key               BIGINT
year                        INTEGER (2024)
score                       DOUBLE
```

## Derived / Calculated Tables

### gold_supply_risk
Grain: One row per material × stage × year
```
material_key                BIGINT
stage_key                   BIGINT
year                        INTEGER
hhi_global                  DOUBLE (nullable; Σ_c (Sᶜ)²·WGIᶜ·tᶜ over supply_mix='global')
hhi_eu_sourcing             DOUBLE (nullable; same over supply_mix='eu_sourcing'; NULL when the key has no EU sourcing rows — the EU coverage gap, never 0)
contrast_ratio              DOUBLE (nullable; hhi_eu_sourcing / hhi_global; NULL when hhi_global is 0 or NULL, or when hhi_eu_sourcing is NULL — never 0)
is_bottleneck               BOOLEAN (the stage with the HIGHER hhi_global per material × year; strict — a tie flags neither stage; NULL hhi_global never wins)
incomplete_wgi_coverage      BOOLEAN (TRUE when any supplier row for this key was excluded due to NULL wgi_weight)
```

Built by `compute_gold_supply_risk` in `silver-to-gold2.Notebook` (task-038_4),
mirrored in `src/transformations/supply_risk.py` (DEC-002). Consumes
`fact_supply_share` (with its `wgi_weight` and `t` columns) and joins
`gold_dim_country` for `is_placeholder`.

**Shares are fractions, not percentages.** `Sᶜ = share_pct / 100` — `share_pct`
is stored 0-100 on `fact_supply_share`, and squaring the 0-100 scale silently
inflates the index by 10^4. A parity test pins the division by 100.

**NULL handling (DEC-009 + user decision, task-038_4):**

- Rows with `wgi_weight IS NULL` are **excluded** from the Σ_c sum — never
  coerced to 0 (0.0 is a legitimate weight meaning *best governance*; coercing
  NULL to 0 would read as a perfectly-governed country and silently re-rank every
  material). The HHI is computed over the governance-known subset only, which
  **understates risk for Taiwan-heavy materials** (TWN — World Bank publishes no
  WGI for Taiwan, ever). This is an accepted, visible tradeoff, not a bug.
- Placeholder countries (`gold_dim_country.is_placeholder = TRUE`, e.g.
  `UNK_GLOB`) are excluded from the country-level HHI sum regardless of their
  weight — a placeholder is a bucket, not a country.
- `incomplete_wgi_coverage` makes the NULL-wgi exclusion **visible per row**
  rather than silent. A material × stage × year flagged TRUE has an HHI computed
  over a partial governance subset.
- EU coverage gap (global rows exist, no eu_sourcing rows) →
  `hhi_eu_sourcing = NULL` and `contrast_ratio = NULL` — **never 0**, which
  would misread as "no EU concentration risk" (0 is a legitimate index value
  meaning perfectly diffuse supply).
- `hhi_global = 0` → `contrast_ratio = NULL`, never 0.

**`is_bottleneck` is driven by `hhi_global` ONLY** (not `hhi_eu_sourcing`, not
the max of the two), so it stays defined when EU coverage is missing. The
methodology reports SR at the bottleneck stage (E/P); gold retains both stages
and flags the bottleneck rather than collapsing to one row, so the
extraction-vs-processing comparison stays available to the report.

See `spec_v1 § Business Logic & Calculations → Supply Risk` (DEC-001 Option B)
for the formula and the scope boundary (gross supply risk — no import-reliance
blend, no recycling/substitution filters; the "gross" labelling is the report
job, not this table).

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
| `gold_data_gaps` | One row per country — EPI/WGI coverage flags, role carried as `is_supplier_hq` / `is_production` attributes (task-074) |
| `gold_data_gaps_summary` | Coverage rollup for KPI cards |
| `gold_country_coverage_matrix` | Country presence across all source datasets |
| `gold_data_quality_metrics` / `gold_data_quality_dashboard` | Quality metric rollups |
| `gold_dim_country_lookup` / `gold_dim_material_lookup` | Alias-aware join surfaces (see `transformations/alias_mappings.md`) |
| `mapping_country_aliases_confidence` / `mapping_material_aliases_confidence` | Alias tables with confidence scores |
| `gold_low_confidence_audit` | One row per fuzzy match below 0.95 confidence, pre-aggregated with `frequency` + `spend_impact`. Point-in-time snapshot, truncated to 0 rows when clean |
| `gold_quality_history` | Append-only quality metrics per run |
| `gold_gap_registry` | One row per distinct unmapped value, with lifecycle fields |

> **Who writes the observability tables.** `silver-to-gold2` creates *and* populates all
> three (`populate_quality_history()`, `populate_gap_registry()`,
> `populate_low_confidence_audit()`). `data_quality_checks.Notebook` **also** appends
> per-check rows to `gold_quality_history` — that is why the table carries a `producer`
> column — but it does **not** write `gold_gap_registry`. (An earlier version of this note
> had the ownership backwards.) See `data_quality_architecture.md` for the full schemas.
