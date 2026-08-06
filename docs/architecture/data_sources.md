# Data Sources - OEMMatInsightBI

## Overview

This project integrates data from 4 primary sources: 1 transactional database + 3 external datasets.

## 1. Azure SQL Database (Transactional System)

**Server:** `procurement-supplier.database.windows.net`
**Database:** `procurement-supplier-db`
**Authentication:** Fabric connection `oem_azuresql_procurement` (service principal, shared with security group `Fabric-SPN-Access`). The retired `bronze_azureSQLdb2table` dataflow bound this credential inside its own definition; the Copy activities that replaced it (task-048) bind it at the workspace connection level instead.

### Tables

**dbo.Procurement** → `bronze_procurement_transactional`
- **Purpose:** Purchase order transactions
- **Grain:** One row per material purchase
- **Key Columns:**
  - `Date` (DATE) - Transaction date
  - `MaterialName` (NVARCHAR(100)) - Material identifier
  - `SupplierName` (NVARCHAR(200)) - Supplier identifier
  - `Region` (NVARCHAR(100)) - Supplier region
  - `Quantity` (DECIMAL(18,2)) - Purchase quantity
  - `Unit` (NVARCHAR(50)) - Unit of measure (kg, t, g, etc.)
  - `UnitPriceEUR` (DECIMAL(18,2)) - Price per unit in EUR

**dbo.SupplierInfo** → `bronze_supplier_ref`
- **Purpose:** Supplier master data
- **Grain:** One row per supplier
- **Key Columns:**
  - `SupplierName` (NVARCHAR(200)) - Join key from Procurement
  - `HeadquartersCountry` (NVARCHAR(100)) - HQ location
  - `ProductionCountry` (NVARCHAR(100)) - Production location
  - `Region` (NVARCHAR(100)) - Geographic region

**Ingestion:** Copy activities `bronze_copy_procurement_transactional` and
`bronze_copy_supplier_ref`, via Fabric connection `oem_azuresql_procurement`.
(Was `bronze_azureSQLdb2table.Dataflow` / activity `bronze_procurement` — retired 2026-07-31.)
**Note:** bronze holds the source's RAW day/year-transposed dates; the correction runs in
`bronze_to_silver`. Read silver for usable dates.
**Frequency:** (TBD - currently manual/on-demand)
**Load Type:** Full refresh at bronze. **Incremental starts at silver** — `silver_procurement`
and `fact_procurement` load via delete-insert over a 7-day look-back window driven by
`p_full_load` / `p_from_date`. See `incremental_load_strategy.md § 3`.

**Setup Scripts:** (in `/azure` folder)
- `user_creation.sql` - Database user setup
- `grant_permissions.sql` - Access control
- `procurement.sql` - Procurement table schema/data
- `supplier_info.sql` - Supplier reference schema/data

## 2. Environmental Performance Index (EPI)

**Source:** Yale Center for Environmental Law & Policy
**Format:** CSV downloaded over HTTPS (no manual upload)
**Year:** Whatever `p_epi_year` names — `"2024"` today
**URL:** `https://epi.yale.edu/downloads/epi{p_epi_year}results.csv`
**License:** CC BY-NC-SA 4.0 (non-commercial use only)

### Content

**Purpose:** Country-level environmental performance scores
**Grain:** One row per country
**Countries:** ~180-200 countries covered

**Key Fields:**
- `code` (INTEGER) - Numeric country code
- `iso` (STRING) - ISO3 country code (e.g., "USA", "CHN", "SWE")
- `country` (STRING) - Country name
- `EPI` (DOUBLE) - Overall EPI score
- ~30+ indicator columns (air quality, biodiversity, climate change, etc.)

**Ingestion:** `bronze_ingest_epi.Notebook` (PySpark; pipeline activity `bronze_EPI`).
Supersedes the retired `EPI_file2table.Dataflow` manual-upload lineage.
**Frequency:** Annual (Yale typically publishes in June)
**Load Type:** Full replacement (annual snapshot, `mode("overwrite")`)
**Current Table:** `bronze_epi{p_epi_year}results` — e.g. `bronze_epi2024results`

The download URL and the target table name are derived from the **same** `p_epi_year`
parameter, so each vintage lands in its own table. Decoupling them was a real bug: the URL
was parameterised while the table name was hardcoded, so a 2025 run would have written
2025 numbers into `bronze_epi2024results`. A non-4-digit `p_epi_year` raises, and a 404
raises with the year echoed back.

**Transformation:**
- Bronze: Wide format (one row per country, 30+ columns)
- Silver: Cleaned (drop .old columns, cast types) → `silver_epi{year}results`
- Gold: Pivoted to long format (one row per country × indicator) → `fact_epi_score`

**Update Schedule:** Pass the new year as `p_epi_year` when the release lands
**Automation:** ✅ Automated (notebook in the pipeline)

## 3. World Governance Indicators (WGI)

**Source:** World Bank
**Format:** JSON over HTTPS — **World Bank API v2**, paginated
**Year:** All years in the requested range (no year filter is applied)
**URL:** `https://api.worldbank.org/v2/country/all/indicator/{code}`

### Content

**Purpose:** Country-level governance quality metrics
**Grain:** One row per country × indicator × year (**long format as delivered**)
**Countries:** ~200+ countries
**Indicators:** 6 governance dimensions, all `*.EST` estimate series — `CC.EST`, `GE.EST`,
`PV.EST`, `RL.EST`, `RQ.EST`, `VA.EST`

**Key Fields:**
- `Country Name` (STRING) - Full country name
- `Country Code` (STRING) - ISO3 country code
- `Series Name` (STRING) - Name of governance indicator, e.g. "Control of Corruption: Estimate"
- `Indicator Code` (STRING) - Coded identifier, e.g. `CC.EST`
- `Year` (STRING) - Observation year; cast to INT in silver
- `Value` (DOUBLE) - Governance **estimate**, roughly −2.5 … +2.5

**Ingestion:** `bronze_ingest_wgi.Notebook` (PySpark; pipeline activity `bronze_wgi`).
Supersedes the retired `WGI_file2table.Dataflow` CSV lineage.
**Frequency:** Annual (typically Q3-Q4)
**Load Type:** Full replacement (`mode("overwrite")` — WGI is a full snapshot refresh)
**Current Table:** `bronze_wgi`

The World Bank re-coded WGI in the API: the classic `CC.EST` / `GE.EST` / … codes were
archived to source 57 and now return "indicator not found"; the live estimate series are
`GOV_WGI_*.EST` under source 3. The notebook **fetches with the new codes but stores the
classic short code and series name**, so the `Indicator Code` / `Series Name` contract is
unchanged for every downstream layer.

**Transformation:**
- Bronze: Long format already — nothing is unpivoted
- Silver: Standardize ISO3, cast `Year`/`Value`, drop null-valued observations,
  deduplicate to grain (country_iso3 × indicator_code × year) → `silver_wgi`
- Gold: Feeds the governance-coverage flags in `gold_data_gaps` (a country counts as
  governance-covered only when all **six** indicators are present)

> ⚠️ **Retired lineage.** `bronze_WB_ESGCSV` and `bronze_WB_ESGSeries` — the wide extract
> with `y_2000 … y_2023` year columns plus a separate `Topic` metadata table, filtered to
> 2020, written to `silver_WB` — no longer exist. The retired dataflow emitted 2023
> **percentile ranks (0-100)**, which are not interchangeable with the API's estimates, so
> `bronze_to_silver` **hard-fails** if `bronze_wgi` is missing `Indicator Code` / `Year` /
> `Value` rather than silently falling back.

**Automation:** ✅ Automated (notebook in the pipeline)

## 4. EU Critical Raw Materials - Supply Shares (Global + EU sourcing)

**Source:** EU Commission Critical Raw Materials data (GitHub)
**Format:** CSV file
**Year:** 2023
**URL:** (HTTP endpoint from GitHub repository)

### Content

**Purpose:** Material supply concentration by country and stage
**Grain:** One row per material × stage × country
**Materials:** ~80+ critical raw materials
**Stages:** E (Extraction), P (Processing)

**Key Fields:**
- `Material` (STRING) - Material name
- `Stage` (STRING) - Production stage ("E" or "P")
- `Country` (STRING) - Supplier country
- `Share` (STRING) - Supply percentage (e.g., "45%", "<1%")
- `t` (DOUBLE) - Trade parameter from the EU CRM methodology: `0.8` EU-sourced, `1.0`
  baseline non-EU, `>1` where export restrictions apply. **Load-bearing input to the Supply
  Risk model — preserved through silver into `fact_supply_share`** (DEC-001, task-038_1).

**Ingestion:** **two** Copy activities, one per scope — they are separate sources, not one:

| Copy activity | Target table | Consumed downstream? |
|---|---|---|
| `bronze_copy_global_supply_shares` | `bronze_global_supply_shares` | ✅ Yes — `bronze_to_silver` builds `silver_globalsupplyshares` from it |
| `bronze_copy_eu_supply_shares` | `bronze_eu_supply_shares` | ✅ Yes — `bronze_to_silver` builds `silver_eusupplyshares` from it (task-038_1, 2026-07-29) |

**Frequency:** (TBD - currently on-demand)
**Load Type:** Full replacement (`OverwriteSchema` table action)

**Transformation** (both files — the EU table is treated identically to the global one so the
two silver tables carry the same column contract and the gold union needs no special-casing):
- Bronze: String share values with % symbols; a `t` column carrying the source's trade
  parameter
- Silver: Clean headers only. `t` is **retained** — it is the EU CRM trade parameter and a
  load-bearing input to the Supply Risk model (DEC-001). It was dropped here until
  task-038_1 on the basis of stale documentation calling it an unused field.
- Gold: Convert "<1%" to 0.5%, cast to numeric, assign year=2023. The censored-share
  convention lives **only** in `silver_to_gold`'s `fact_supply_share` build (task-028) —
  `share` stays a raw string through silver; do not fork the conversion upstream.

**Automation:** ✅ Already automated (HTTP source in pipeline)

## Data Integration Architecture

### Source → Bronze
```
Azure SQL ──────────────> bronze_procurement_transactional      (copy activity)
                          bronze_supplier_ref

Yale EPI HTTPS ────────> bronze_epi{year}results                (notebook)

World Bank API v2 ─────> bronze_wgi                             (notebook)

EU CRM HTTP ───────────> bronze_global_supply_shares              (copy activity)
                          bronze_eu_supply_shares                  (copy activity)
```

### Update Frequencies

| Source | Frequency | Last Update | Next Update |
|--------|-----------|-------------|-------------|
| Azure SQL | Daily (planned) | Manual | Implement scheduling |
| EPI | Annual | 2024 vintage (`p_epi_year`) | Pass the new year when Yale publishes |
| WGI | Annual | Full series from the API each run | Automatic — no vintage to bump |
| EU CRM | Annual | 2023 | Unknown |

## Data Quality by Source

### Azure SQL
- **Reliability:** High (synthetic/sample data, controlled)
- **Completeness:** High (~100% of required fields populated)
- **Consistency:** High (enforced by database schema)
- **Issues:** None identified

### EPI
- **Reliability:** High (authoritative source from Yale)
- **Completeness:** Medium (~180 countries, missing some small nations)
- **Consistency:** High (standardized methodology)
- **Issues:** Schema changes between years (handle with .old/.new columns)

### WGI
- **Reliability:** High (World Bank official data)
- **Completeness:** High (~200 countries)
- **Consistency:** Medium (methodology changes over time)
- **Issues:** The API returns a row for every year in the requested range whether or not
  an observation exists, so null-valued rows must be dropped in silver (WGI was biennial
  1996–2000). The World Bank also re-coded the indicator series, which the ingest notebook
  absorbs. **No range validation is applied** — values are estimates (≈ −2.5 … +2.5), not
  the retired extract's 0-100 percentile ranks.

### EU CRM
- **Reliability:** High (EU Commission official data)
- **Completeness:** Medium (focused on critical materials only)
- **Consistency:** Medium (country name variations)
- **Issues:** Special value handling ("<1%")

## Troubleshooting Data Sources

### Azure SQL Connection Failed
- Check firewall rules (allow Fabric IP addresses)
- Verify the Fabric connection `oem_azuresql_procurement` is bound (Manage connections and
  gateways → Connections) — procurement ingestion is via the Copy activities
  `bronze_copy_procurement_transactional` and `bronze_copy_supplier_ref` (task-048 retired
  the `bronze_azureSQLdb2table` dataflow; the dataflow workspace item is deleted)
- Test the connection from its context menu in Manage connections and gateways

### EPI download fails
- A 404 means Yale has no file for that `p_epi_year`, or changed the URL pattern — the
  notebook raises with the attempted URL echoed back
- Other HTTP errors retry 3× before failing
- Check `p_epi_year` is a 4-digit year (a malformed value raises before any download)

### WGI fetch returns no data / fewer than 6 indicators
- `bronze_ingest_wgi` raises outright if zero records come back — check network access to
  `api.worldbank.org` from the Fabric capacity
- `bronze_to_silver` warns when `silver_wgi` carries fewer than 6 distinct indicators;
  the gold coverage rule requires all six, so WGI coverage reads 0 when one is missing.
  Check the ingest fetch log for an indicator that 404'd (the World Bank archives series
  periodically — see the code-mapping note in § 3)

### `bronze_to_silver` fails with "bronze_wgi is missing ['Indicator Code', 'Year', 'Value']"
- **Obsolete since task-035 (2026-07-26):** `bronze_wgi` is now written by the
  `bronze_ingest_wgi` TridentNotebook activity, not by the retired `WGI_file2table.Dataflow`,
  so the pipeline can no longer overwrite bronze from the dataflow. The error can still
  surface if someone re-points the activity at the dataflow manually, or runs the dataflow
  by hand and then the pipeline in the same session — in that case the fix is to ensure
  the `bronze_wgi` activity in `orchestrator_pipeline_bronze_to_gold` points at
  `bronze_ingest_wgi.Notebook` (the shipped state).

### EU CRM HTTP Error
- Check GitHub URL is accessible
- Verify no rate limiting
- Check repository structure hasn't changed

### Schema Drift
- Compare current schema to expected (use `/validate-schema`)
- Update transformation notebooks if needed
- Document changes in this file

## Related Files

- `/azure/` - Azure SQL setup scripts
- SQL ingestion — Copy activities in the orchestrator pipeline (the
  `bronze_azureSQLdb2table.Dataflow` directory was removed 2026-07-31)
- `/fabric/bronze_ingest_epi.Notebook/` - EPI ingestion (live)
- `/fabric/bronze_ingest_wgi.Notebook/` - WGI ingestion (live)
- `/fabric/orchestrator_pipeline_bronze_to_gold.DataPipeline/` - Orchestration + the two supply-share copy activities
- `/docs/schemas/bronze_tables.md` - Bronze table schemas
- `/project_definition.md` - Lines 126-319 (Data Sources section)

**Retired** (artifacts still on disk, no longer in the pipeline):
- `/fabric/EPI_file2table.Dataflow/` — superseded by `bronze_ingest_epi.Notebook`
- `/fabric/WGI_file2table.Dataflow/` — superseded by `bronze_ingest_wgi.Notebook`
