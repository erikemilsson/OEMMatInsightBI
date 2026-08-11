# Bronze Layer Table Schemas

## bronze_procurement_transactional
Source: Azure SQL dbo.procurement_transactional
Grain: One row per material purchase
```
Date                        DATE
MaterialName                STRING (NVARCHAR(100))
SupplierName                STRING (NVARCHAR(200))
Region                      STRING (NVARCHAR(100))
Quantity                    DECIMAL(18,2)
Unit                        STRING (NVARCHAR(50))   -- observed domain: kg, pcs
UnitPriceEUR                DECIMAL(18,2)           -- per the row's Unit (EUR/kg, EUR/piece)
```

**`UnitPriceEUR` is per the row's `Unit`, not per kilogram** (confirmed against the
live source 2026-07-23, task-030 AC3). The observed `Unit` domain is `kg` (108 rows)
and `pcs` (24 rows — electronic control units, tyres); a `pcs` price can only be per
piece. Gold computes `spend_eur = Quantity × UnitPriceEUR` accordingly, and
`quantity_base` (kg) is NULL for non-mass units like `pcs`. See `calculations.md §
Spend EUR`.

## bronze_supplier_ref
Source: Azure SQL dbo.supplier_ref
Grain: One row per supplier
```
SupplierName                STRING (NVARCHAR(200))
HeadquartersCountry         STRING (NVARCHAR(100))
ProductionCountry           STRING (NVARCHAR(100))
Region                      STRING (NVARCHAR(100))
```

## bronze_epi{year}results
Source: EPI CSV, downloaded by `bronze_ingest_epi.Notebook`
Grain: One row per country (wide format)
```
code                        INTEGER
iso                         STRING (ISO3)
country                     STRING
EPI                         DOUBLE
[30+ indicator columns]     DOUBLE (e.g., AIR, BIO, CLI, etc.)
```

The table name carries the vintage — `bronze_epi2024results` for `p_epi_year = "2024"`.
The year comes from the pipeline parameter `p_epi_year`, so a new vintage lands in its own
table rather than overwriting the previous one.

## bronze_wgi
Source: **World Bank API v2** (`https://api.worldbank.org/v2`), ingested by
`bronze_ingest_wgi.Notebook` (pipeline activity `bronze_wgi`)
Grain: One row per country × indicator × year (**long format**)
```
Country Name                STRING
Country Code                STRING (ISO3)
Series Name                 STRING  -- e.g. "Control of Corruption: Estimate"
Indicator Code              STRING  -- e.g. "CC.EST"
Year                        STRING  -- cast to INT in silver
Value                       DOUBLE  -- governance ESTIMATE, roughly -2.5 … +2.5
```

**Six indicators**, all `*.EST` estimate series: `CC.EST`, `GE.EST`, `PV.EST`, `RL.EST`,
`RQ.EST`, `VA.EST`. The notebook fetches the World Bank's current API codes
(`GOV_WGI_*.EST`, source 3) but **stores the classic short code and series name**, so the
`Indicator Code` / `Series Name` contract is stable for every downstream layer even though
the API re-coded the series.

Write mode is `overwrite` with `overwriteSchema` — WGI is a full snapshot refresh.

> **Retired lineage.** `bronze_WB_ESGCSV` and `bronze_WB_ESGSeries` — the wide Excel/CSV
> extract with `y_2000 … y_2023` year columns and a separate metadata table, produced by
> `WGI_file2table.Dataflow` — are **retired and no longer exist**. That dataflow emitted a
> different and incompatible shape: four columns (`Country Name`, `Country Code`,
> `Series Name`, `Percentile Rank 2023`) holding 2023 **percentile ranks (0–100)**, not
> estimates. `bronze_to_silver` therefore **hard-fails** with an actionable message if
> `bronze_wgi` is missing `Indicator Code` / `Year` / `Value`, rather than falling back —
> a percentile rank landing in `value` under the same column name would silently change
> what `WGIᶜ` means in the DEC-001 supply-risk formula.

## bronze_global_supply_shares
Source: EU CRM CSV over HTTP — Copy activity `bronzecopy_GlobalSupplyShares`
Grain: One row per material × stage × country
```
Material                    STRING
Stage                       STRING ("E" or "P")
Country                     STRING
Share                       STRING (percentage with % symbol)
t                           STRING (the EU CRM trade parameter; RETAINED through silver
                            since task-038_1 — load-bearing input to the Supply Risk
                            model per DEC-001. It was dropped until 2026-07-29 on the
                            basis of this line, which used to read "dropped in silver".)
```

## bronze_eu_supply_shares
Source: EU CRM CSV over HTTP — Copy activity `bronzecopy_EUSupplyShares`
Grain: One row per material × stage × country (EU-scope companion to the global file)

**Consumed since task-038_1 (2026-07-29):** `bronze_to_silver` builds `silver_eusupplyshares`
from this table, applying the same header normalisation the global table gets and retaining
`t`. The notebook asserts that both silver tables carry the same column set, so this table's
schema is pinned to the global one:

```
Material                    STRING
Stage                       STRING ("E" or "P")
Country                     STRING
Share                       STRING (percentage with % symbol)
t                           STRING (trade parameter; ~0.8 for EU-sourced)
```

If the live table diverges from this shape, the bronze_to_silver run fails fast with a
"silver supply-share column contract mismatch" error naming the differing columns.
