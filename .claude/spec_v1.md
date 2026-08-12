---
version: 1
status: active
created: 2025-11-14
updated: 2026-08-12
---

# OEMMatInsightBI - Project Definition for Claude Code

> **Purpose:** This file serves as the single source of truth for generating Claude Code environment files (`.claude/` structure) for the OEMMatInsightBI project.
>
> **Instructions for Claude Code:** Read this entire file to understand the project, then generate:
>
> -   Task management structure (`.claude/tasks/`)
>
> -   Command definitions (`.claude/commands/`)
>
> -   Context documentation (`docs/`)
>
> -   Reference files (`.claude/support/reference/`)
>
> -   Standards and conventions (`docs/standards/`)

------------------------------------------------------------------------

## Project Overview

### Business Context

**Project Name:** OEMMatInsightBI (OEM Material Insight Business Intelligence)

**Domain:** Supply Chain Sustainability Analytics

**Business Problem:** OEM manufacturers need visibility into their supply chain's environmental and governance performance to:

-   Assess supplier sustainability credentials (Environmental Performance Index - EPI)

-   Evaluate governance quality of supplier countries (World Governance Indicators - WGI)

-   Analyze material sourcing patterns and supplier concentration risks

-   Track procurement spending against sustainability metrics

-   Comply with ESG reporting requirements

-   Make data-driven sourcing decisions

**Secondary Purpose:** This project also serves as hands-on preparation for a data engineering consultant role (Rejlers). Beyond demonstrating a working BI solution, it exercises production patterns commonly encountered at client sites: incremental Delta MERGE loading, a blocking data-quality gate backed by observability tables, pipeline error handling with retry logic, and CI/CD deployment via GitHub Actions. Storage and serving are **Lakehouse-only** — the semantic model reads gold Delta tables through DirectLake, with no warehouse in the path.

**Stakeholders:**

-   Procurement teams (primary users)

-   Sustainability/ESG reporting teams

-   Supply chain risk management

-   Executive leadership (dashboard consumers)

**Success Metrics:**

-   Complete visibility into supplier environmental performance

-   Ability to identify high-risk sourcing regions

-   Automated ESG reporting from procurement data

-   Power BI dashboards accessible to stakeholders

------------------------------------------------------------------------

## Technical Architecture

### Platform Stack

**Primary Platform:** Microsoft Fabric

-   **Lakehouse:** `oem_lh` (data storage, bronze/silver/gold layers)

-   **SQL analytics endpoint:** `oem_lh`'s auto-created, read-only T-SQL surface. Some Fabric APIs report it with item type `Warehouse`; it is not a standalone warehouse and is not in the DirectLake path. **Retired (2026-08-10)** — the standalone `oem_wh` Warehouse was removed; nothing ever read it. See `.claude/support/retired/oem-wh-warehouse/manifest.json`.

-   **Semantic Model:** `OEMInsightBI` (Power BI data model; renamed from `OEMInsightBI_v2` on 2026-08-10 to drop the version suffix. The superseded `semantic_model_oeminsightbi` was removed from `fabric/archive/` on 2026-08-01 by workspace-sync commit `d128664` and survives only in git history at `d128664~1`)

-   **Report:** Power BI report connected to semantic model

**Development Environment:**

-   Python 3.12 (local virtual environment: `.venv`)

-   PySpark (Fabric notebooks)

-   Power Query M (Dataflows)

-   SQL (Azure SQL, Fabric Warehouse)

**Version Control:**

-   Git repository structure exists in `/fabric` folder

-   Each Fabric artifact has `.platform` metadata

-   Single developer, direct commits to main. The repo is the source of truth; `fabric-cicd` publishes it to the workspace on every push (§ Development Workflow). Fabric's own Git integration was disconnected 2026-08-05 and is no longer a sync path.

**Azure Services:**

-   Azure SQL Database (transactional source system)

-   **Server:** procurement-supplier.database.windows.net

-   **Database:** procurement-supplier-db

-   Authentication method: SQL authentication (see `secure/user_creation.sql` — `secure/` is gitignored; credentials kept locally per project convention)

-   Connection strings: Managed via Fabric connections (`oem_azuresql_procurement`), shared with the `Fabric-SPN-Access` security group so SPN-driven deploys can use them

------------------------------------------------------------------------

## Data Architecture

### Medallion Architecture Implementation

```         
Bronze Layer (Raw Ingestion)
    ↓
Silver Layer (Cleaned & Validated)
    ↓
Gold Layer (Business Logic & Aggregations)
    ↓
Semantic Model (Star Schema)
    ↓
Power BI Reports
```

### Data Sources

#### 1. Azure SQL Database (Transactional System)

**Tables Ingested:**

-   `dbo.procurement_transactional` → `bronze_procurement_transactional`

-   Purchase orders, suppliers, materials, dates, amounts

-   `dbo.supplier_ref` → `bronze_supplier_ref`

-   Supplier master data (names, locations, metadata)

**Ingestion Method:**

**Retired (2026-07-31)** — the dataflow below was replaced by Copy activities; see `.claude/support/retired/bronze-azuresqldb2table-dataflow/manifest.json`.

-   ~~Fabric Dataflow: `bronze_azureSQLdb2table.Dataflow`~~ — retired. Ingestion is now two Copy activities in the orchestrator pipeline (`bronze_copy_procurement_transactional`, `bronze_copy_supplier_ref`) reading `dbo.procurement_transactional` and `dbo.supplier_ref` via the Fabric connection `oem_azuresql_procurement`.

-   Frequency: Manual — pipeline triggered on demand

-   Incremental vs Full Load: Parameters exist (`p_full_load`, `p_from_date`); **bronze is a full load.** `p_from_date` never reached the retired dataflow and does not reach the Copy activities; it drives a 7-day look-back in `bronze_to_silver` against corrected dates. Incrementality lives in silver, not bronze.

**Setup Scripts:**

**Credential scripts** (in `/secure` folder — gitignored; credentials kept locally):

-   `user_creation.sql` - Database user setup

-   `grant_permissions.sql` - Access control

**Schema + seed scripts** (in `/azure` folder — tracked):

-   `procurement.sql` - DDL for `dbo.procurement_transactional` (step 1 of 2)

-   `procurement_seed.sql` - the 132 transaction rows as a literal `INSERT` (step 2 of 2)

-   `supplier_info.sql` - DDL for `dbo.supplier_ref` (step 1 of 2)

-   `supplier_info_seed.sql` - the 11 supplier reference rows as a literal `INSERT` (step 2 of 2)

Together these rebuild the Azure SQL source from the repo alone (task-064). Run the DDL before its seed; each seed opens with a `DELETE` so a repeat run is idempotent and closes with a row-count `THROW` guard. **The DDL scripts create `dbo.procurement_transactional` and `dbo.supplier_ref`** — the names the Copy activities actually read. They previously created `dbo.Procurement` / `dbo.SupplierInfo`, names no live artifact has ever read (the retired dataflow read the `_transactional` / `_ref` names too), so the DDL described an object the pipeline could never ingest. **The `DROP` in each DDL now targets the live table** — see DEC-015.

**Key Columns:**

**`dbo.procurement_transactional` table:**

-   `Date` (DATE) - Transaction date, used for date dimension join

-   `MaterialName` (NVARCHAR(100)) - Material identifier for material dimension

-   `SupplierName` (NVARCHAR(200)) - Supplier identifier, join key to supplier_ref

-   `Region` (NVARCHAR(100)) - Supplier region

-   `Quantity` (DECIMAL(18,2)) - Purchase quantity

-   `Unit` (NVARCHAR(50)) - Unit of measure (kg, t, g, etc.)

-   `UnitPriceEUR` (DECIMAL(18,2)) - Price per unit in EUR

-   **Primary key:** None defined (transactional data)

**`dbo.supplier_ref` table:**

-   `SupplierName` (NVARCHAR(200)) - Supplier identifier, join key from procurement

-   `HeadquartersCountry` (NVARCHAR(100)) - Supplier HQ location for country analysis

-   `ProductionCountry` (NVARCHAR(100)) - Production location for supply chain analysis

-   `Region` (NVARCHAR(100))

-   Geographic region

-   **Primary key:** None defined

#### 2. Environmental Performance Index (EPI) - External Data

**Source:** EPI dataset (file-based ingestion)

**Ingestion Method:** `bronze_ingest_epi.Notebook` (PySpark, automated HTTP download from `epi.yale.edu` with retry; year-parameterised per task-028). Supersedes the retired `EPI_file2table.Dataflow` CSV lineage.

**Content:** Country-level environmental performance scores across multiple indicators

**Grain:** One row per country with \~30+ indicator columns (wide format)

**Year Covered:** 2024

**Key Fields:**

-   `code` (INTEGER) - Numeric country code

-   `iso` (STRING) - ISO3 country code (e.g., "USA", "CHN", "SWE")

-   `country` (STRING) - Country name

-   `EPI` (DOUBLE)

-   Overall EPI score - \~30+ indicator columns (e.g., air quality, biodiversity, climate change scores)

**Transformation Notes:**

-   Data stored in bronze as wide format (one row per country)

-   Pivoted to long format in silver-to-gold transformation (one row per country per indicator)

**Table naming — vintage-derived:**

-   Convention: `bronze_epi{year}results` / `silver_epi{year}results` (plus `silver_epi{year}variables`)

-   Bronze table: `bronze_epi2024results` — derived by `bronze_ingest_epi.Notebook` from its `p_epi_year` parameter (default `"2024"`)

-   Silver table: `silver_epi2024results` — consumed by `silver_to_gold.Notebook` via `EPI_YEAR` (default `2024`)

**Vintage is single-sourced end to end** (task-042, closed 2026-07-26). Every EPI table name in the chain derives from a vintage parameter rather than a literal, so changing the vintage **re-points** the chain rather than breaking it:

-   `bronze_ingest_epi.Notebook` — `p_epi_year` parameter cell
-   `bronze_to_silver.Notebook` — `p_epi_year = "2024"` in its parameters cell; reads `f"…bronze_epi{p_epi_year}results"` and writes `f'silver_epi{p_epi_year}results'`. **Zero literal occurrences** of `bronze_epi2024results` / `silver_epi2024results`
-   `silver_to_gold.Notebook` and `data_quality_checks.Notebook` — `EPI_YEAR` declared once in a parameter cell; all EPI table names, **including the `BLOCKING_CHECKS` entry** `("schema_validation", f"oem_lh.silver_epi{EPI_YEAR}results")`, are f-strings over it
-   The pipeline passes one `p_epi_year` to every EPI notebook (§ Orchestration)

*Verified 2026-08-06. This paragraph previously described the pre-task-042 state — that `bronze_to_silver` hardcoded both names "literally (lines 74, 108)", that changing the vintage "breaks the chain", and that task-042 still "carries the parameterization". All four claims were stale: task-042 is exactly the task that fixed them, and it closed 11 days before this correction. Retaining the caveat that matters: a **stale `BLOCKING_CHECKS` table name does not error — it silently demotes that check to advisory**, which is why the entry is derived rather than written out (see § Data Quality & Validation).*

**Update Frequency:** Annual (EPI releases yearly)

**File Location:** Downloaded over HTTPS from `epi.yale.edu` by `bronze_ingest_epi.Notebook` (task-028; year-parameterised via `p_epi_year`). Manual upload to Lakehouse `Files/` was the pre-task-035 mechanism.

**File Format:** CSV

#### 3. World Governance Indicators (WGI) - External Data

**Source:** World Bank WGI, via the World Bank API

**Ingestion Method:** `bronze_ingest_wgi.Notebook` (PySpark, API-based). Supersedes the retired `WGI_file2table.Dataflow` CSV lineage.

**Content:** Country-level governance quality metrics across 6 WGI dimensions

**Grain:** Long format — one row per country per indicator per year

**Years Covered:** 1996-2023 as ingested. The Supply Risk model consumes the **latest year available per country**.

**Key Fields:**

-   `Country Name` (STRING) - Full country name

-   `Country Code` (STRING) - ISO3 country code

-   `Series Name` (STRING) - Name of governance indicator

-   `Indicator Code` (STRING) - Coded indicator identifier

-   `Year` (INT) - Observation year

-   `Value` (DOUBLE) - Governance score for that country/indicator/year

**Silver contract:**

-   `silver_wgi` **must preserve `Year` and `Value`.** They are the `WGIᶜ` input to the Supply Risk model; without them the governance weight cannot be computed downstream.

-   **Six** WGI dimensions are ingested, not five. Coverage rules must test against six.

-   *(Historical note: the pipeline once selected only identity columns — `country_iso3`, `country_name`, `indicator_name` — discarding `Year`/`Value`. **Corrected by task-031, closed 2026-07-23**; `bronze_to_silver` now hard-requires `Indicator Code`/`Year`/`Value` and fails rather than falling back. Made mandatory by DEC-001.)*

**Update Frequency:** Annual (World Bank releases Q3-Q4)

#### 4. Supply Shares (EU CRM Data) - External Data

**Source:** EU Critical Raw Materials supply chain data

**Two complementary tables from the same EU CRM study — NOT duplicates.** Both are required inputs to the Supply Risk model (see § Business Logic & Calculations → Supply Risk):

| | Global supply | EU sourcing |
|---|---|---|
| Bronze | `bronze_global_supply_shares` | `bronze_eu_supply_shares` |
| Silver | `silver_globalsupplyshares` | `silver_eusupplyshares` |
| Measures | where a material is produced worldwide | where the EU actually sources it from |

**Both halves of DEC-001 Option B are live.** `bronze_to_silver.Notebook` reads `bronze_eu_supply_shares` and writes `silver_eusupplyshares`; `fact_supply_share` carries **903 rows at `supply_mix = 'eu_sourcing'`** alongside 2,560 global rows (3,463 total), with trade-weighting `t` spanning 0.80–1.50. Built under task-038, closed 2026-08-05. *(Measured against the live Delta log 2026-08-06.)*

**Ingestion Method:** One copy activity per table. Each activity's source connection must point at its own CSV — conflating them produced the duplicated-load defect tracked as FR-004 / task-022.

**Content:** Material supply concentration by country and production stage

**Grain:** One row per material per stage per country

**Key Fields:**

-   `Material` (STRING) - Material name

-   `Stage` (STRING) - Production stage code ("E" = Extraction, "P" = Processing)

-   `Country` (STRING) - Supplier country name

-   `Share` (STRING) - Supply share percentage (e.g., "45%", "\<1%")

-   `t` (DOUBLE) - **Trade parameter** from the EU CRM methodology: `0.8` for EU-sourced, `1.0` baseline non-EU, `>1` where export restrictions apply. **Load-bearing input to the Supply Risk model — must be preserved through silver into `fact_supply_share`.** (Previously documented here as "Unknown field (dropped in transformation)" and dropped by the pipeline on that basis; identified via DEC-001.)

**Transformation Notes:**

-   Share values cleaned: percentage signs removed, "\<1%" converted to 0.5%

-   Column headers lowercased and spaces replaced with underscores

-   `t` carried through unchanged (see Key Fields)

-   Year assigned: 2023 (in gold transformation)

**Update Frequency:** Tracks EU CRM study releases (irregular)

**File Location:** GitHub repository CSV file (HTTP source)

**File Format:** CSV with comma delimiter

------------------------------------------------------------------------

## Data Transformations

### Bronze → Silver: Data Cleaning

**Notebook:** `bronze_to_silver.Notebook`

**Purpose:** Standardize raw data from multiple sources

**Specific Cleaning Logic:**

**1. EPI Data (`bronze_epi2024results` → `silver_epi2024results`):**

-   Drop all columns ending with `.old`

-   Remove `.new` suffix from column names

-   Cast `code` column to INTEGER

-   Select identity columns (code, iso, country) plus all 30+ EPI sub-indicator score columns (AIR, BIO, CLI, ECO, …, and the overall EPI composite), each cast to DOUBLE — preserving the full wide indicator set so silver_to_gold can unpivot it into `fact_epi_score` at country × indicator × year grain (task-054)

-   Write to: `silver_epi2024results`

**2. Global Supply Shares (`bronze_global_supply_shares` → `silver_globalsupplyshares`):**

-   Convert column headers to lowercase

-   Replace spaces with underscores

-   Drop `t` column (unused)

-   Write to: `silver_globalsupplyshares`

**3. World Governance Indicators (`bronze_wgi` → `silver_wgi`):**

-   Source: World Bank API via `bronze_ingest_wgi.Notebook` — long format, one row per country per indicator per year

-   Standardize `Country Code` → `country_iso3` (UPPER, trimmed); trim `Country Name` and `Series Name`

-   **Must preserve `Year` and `Value`** — the governance scores are the `WGIᶜ` input to the Supply Risk model (§ Business Logic & Calculations). *Satisfied since task-031 (closed 2026-07-23): both columns are now hard-required at read time, so a source missing them fails loudly instead of silently dropping them.*

-   Coverage rules test against **six** WGI dimensions (not five)

-   Write to: `silver_wgi`

*(Supersedes the retired `bronze_WB_ESGCSV` + `bronze_WB_ESGSeries` → `silver_WB` CSV/dataflow lineage — no live artifact produces those tables.)*

**4. Procurement Data (`bronze_procurement_transactional` + `bronze_supplier_ref` → `silver_procurement`):**

-   Left join procurement_transactional with supplier_ref on SupplierName

-   Convert column headers to lowercase with underscores

-   Drop duplicate columns: region, suppliername (from supplier_ref)

-   Result includes: date, materialname, quantity, unit, unitpriceeur, headquarterscountry, productioncountry

-   Write to: `silver_procurement`

**Input Tables:** (in bronze lakehouse)

-   `bronze_epi2024results`

-   `bronze_global_supply_shares`

-   `bronze_eu_supply_shares`

-   `bronze_wgi`

-   `bronze_procurement_transactional`

-   `bronze_supplier_ref`

**Output Tables:** (in silver lakehouse)

-   `silver_epi2024results`

-   `silver_globalsupplyshares`

-   `silver_eusupplyshares` *(live — built by task-038, closed 2026-08-05; 903 `eu_sourcing` rows reach `fact_supply_share`. See § Data Architecture → Supply Shares.)*

-   `silver_wgi`

-   `silver_procurement`

**Data Quality Rules Applied:**

-   Null filtering on key fields (iso3 for countries, scores for metrics)

-   Type casting with validation (integers, doubles)

-   Score range validation — EPI scores 0-100. **Not applied to WGI:** the World Bank API serves *estimates* (approx. −2.5…+2.5), not the retired `WGI_file2table.Dataflow` extract's 0-100 percentile ranks. No range rule is enforced on `silver_wgi`.

-   Duplicate removal on natural keys

### Silver → Gold: Business Logic & Aggregations

**Notebook:** `silver_to_gold.Notebook`

**Purpose:** Create business-ready fact and dimension tables with:

-   Surrogate key generation (deterministic xxhash64)

-   Alias resolution for country/material names

-   Data quality tracking and confidence scoring

-   Unmapped value handling with placeholder dimensions

**Configuration:**

-   Database: `oem_lh`

-   Fail on unmapped: FALSE (uses placeholder dimensions)

-   Log unmapped: TRUE (creates audit tables)

**Output: Fact Tables**

1.  **`fact_procurement`**
    -   **Grain:** One row per procurement transaction
    -   **Measures:**
        -   `quantity_base` (DOUBLE) - Quantity normalized to kg
        -   `unitprice_eur` (DOUBLE) - Unit price in EUR
        -   `spend_eur` (DOUBLE) - Total spend (quantity_base × unitprice_eur)
        -   `data_quality_score` (DOUBLE) - Average match confidence (0-1)
        -   `quality_category` (STRING) - High/Medium/Low/Unmapped
    -   **Foreign Keys:**
        -   `date_key` (INT) → gold_dim_date
        -   `material_key` (BIGINT) → gold_dim_material
        -   `supplier_hq_country_key` (BIGINT) → gold_dim_country
        -   `production_country_key` (BIGINT) → gold_dim_country
    -   **Business Logic:**
        -   Unit normalization: kg=1.0, g=0.001, t=1000.0, mg=0.000001
        -   Spend calculation: quantity_base × unitprice_eur
        -   Data quality scoring: average of material, HQ country, production country match confidences
        -   Unmapped values assigned to "Unknown
        -   Global" placeholder country/material
        -   Source row tracking for audit trail
    -   **Audit Tables:** `gold_unmapped_procurement_audit`
    -   **Views:** `v_fact_procurement_high_confidence` (quality \>= 0.9), `v_fact_procurement_all` (with dimension names)
2.  **`fact_supply_share`**
    -   **Grain:** One row per material × stage × country × year × supply_mix
    -   **Attributes:**
        -   `supply_mix` (STRING) - `'global'` \| `'eu_sourcing'`. Discriminates the two complementary EU CRM tables (§ Data Architecture → Supply Shares). Rows are unioned from `silver_globalsupplyshares` and `silver_eusupplyshares`, with `supply_mix` stamped at read time.
        -   `t` (DOUBLE) - Trade parameter carried unchanged from silver; the `tᶜ` input to the Supply Risk model.
    -   **Measures:**
        -   `share_pct` (DOUBLE) - Supply percentage (0-100)
        -   `data_quality_score` (DOUBLE) - Average match confidence (0-1)
        -   `quality_category` (STRING) - High/Medium/Low/Unmapped
        -   `has_unmapped_material` (BOOLEAN) - Material not resolved flag
        -   `has_unmapped_country` (BOOLEAN) - Country not resolved flag
        -   `unmapped_impact_score` (DOUBLE) - Share % if unmapped (for prioritization)
    -   **Foreign Keys:**
        -   `material_key` (BIGINT) → gold_dim_material
        -   `stage_key` (BIGINT) → gold_dim_stage
        -   `country_key` (BIGINT) → gold_dim_country
        -   `year` (INT) - Fixed value: 2023
    -   **Business Logic:**
        -   Share cleaning: "\<1%" converted to 0.5%, "%" symbol removed
        -   Quality scoring: average of material, country, stage match confidences
        -   Unmapped materials/countries assigned to "Unknown" placeholders
        -   Stage must be valid (E or P) - records with invalid stage dropped
        -   Impact scoring: unmapped records weighted by share percentage
        -   The two `supply_mix` values are **never summed together** — every consumer either filters to one mix or pivots on it. They are complementary measures from the same EU CRM study, not partitions of one population.
    -   **Audit Tables:** `gold_unmapped_supply_audit`
    -   **Views:**
        -   `v_fact_supply_share_high_confidence` (quality \>= 0.9, no unknowns)
        -   `v_fact_supply_share_complete` (all data with quality flags and warnings)
        -   `v_supply_concentration_risk` (risk analysis by material/stage; filters `supply_mix = 'global'`, preserving its pre-DEC-001 meaning)
3.  **`fact_epi_score`**
    -   **Grain:** One row per country × indicator × year
    -   **Measures:**
        -   `score` (DOUBLE) - EPI indicator score value
    -   **Foreign Keys:**
        -   `country_key` (BIGINT) → gold_dim_country
        -   `indicator_key` (BIGINT) → gold_dim_indicator
        -   `year` (INT) - Fixed value: 2024
    -   **Business Logic:**
        -   Pivot EPI wide format (30+ indicator columns) to long format
        -   Map country via ISO3 code
        -   Map indicator via abbreviation
        -   Records with NULL country_key or indicator_key are dropped
    -   **Data Quality:** Unmapped countries/indicators logged but not included in fact

**Output: Dimension Tables**

1.  **`gold_dim_country`**
    -   **Surrogate Key:** `country_key` (BIGINT) - xxhash64 of iso3 or country_name_std
    -   **Attributes:**
        -   `iso3` (STRING) - ISO 3166-1 alpha-3 code
        -   `iso_numeric` (INTEGER) - ISO 3166-1 numeric code
        -   `wb_code` (STRING) - World Bank country code
        -   `country_name_std` (STRING) - Standardized country name
        -   `region` (STRING) - Geographic region (for placeholder countries)
        -   `is_placeholder` (BOOLEAN) - Flag for unknown/unmapped countries
    -   **Source:**
        -   Primary: EPI (`silver_epi2024results`) only — *the World Bank ESG source was removed; `silver_to_gold.Notebook:244` builds the primary dimension from EPI data alone*
        -   Augmented with: 8 manually added countries (North Korea, Yemen, Syria, Libya, Turkey, Kosovo, San Marino, Nauru)
        -   Placeholders: 6 unknown regions (Unknown - Africa/Asia/Europe/Americas/Oceania/Global)
    -   **SCD Type:** Type 1 (overwrite)
    -   **Lookup Table:** `gold_dim_country_lookup` with 100+ alias mappings and confidence scores
        -   Tier 1: Exact matches (1.0 confidence)
        -   Tier 2: Standard aliases (0.95 confidence, e.g., USA, UK, GB)
        -   Encoding variants (0.80-0.90, e.g., Türkiye variations)
        -   Territory mappings (0.85, e.g., Hong Kong → China)
    -   **Coverage Matrix:** `gold_country_coverage_matrix` tracks country presence across data sources
2.  **`gold_dim_date`**
    -   **Surrogate Key:** `date_key` (INTEGER) - yyyyMMdd format
    -   **Grain:** One row per day
    -   **Attributes:**
        -   `date` (DATE) - Calendar date
        -   `year` (INTEGER)
        -   `month` (INTEGER)
        -   `day` (INTEGER)
        -   `month_name` (STRING) - Abbreviated month (Jan, Feb, etc.)
        -   `quarter` (INTEGER) - Calendar quarter (1-4)
        -   `day_of_week` (INTEGER) - Day of week (1=Sunday, 7=Saturday)
        -   `week_of_year` (INTEGER) - ISO week number
    -   **Date Range:** Dynamically determined from procurement data (min to max date), fallback to current_date - 365 days
    -   **Fiscal Calendar:** Not implemented (calendar year only)
3.  **`gold_dim_indicator`**
    -   **Surrogate Key:** `indicator_key` (BIGINT) - xxhash64 of source_system + indicator identifiers
    -   **Purpose:** EPI and WGI indicator metadata
    -   **Attributes:**
        -   `source_system` (STRING) - "EPI" *(the "WB" value is not currently produced — see Source below)*
        -   `type` (STRING) - EPI indicator type
        -   `abbrev` (STRING) - EPI indicator abbreviation
        -   `variable_name` (STRING) - Full indicator name
        -   `policyobjective` (STRING) - EPI policy objective
        -   `issuecategory` (STRING) - EPI issue category
        -   `indicator_code` (STRING) - World Bank indicator code
        -   `weight` (FLOAT) - EPI indicator weight
        -   `description` (STRING) - Indicator description
        -   `parent_indicator` (BIGINT) - Parent indicator key, resolved from EPI `NextLevel` via a self-join on the parent indicator's abbreviation (NULL for the EPI composite root and for WB indicators; populated for EPI indicators with a non-empty `NextLevel`). *(Prior "(currently NULL)" wording stale since task-056 shipped the NextLevel self-join.)*
    -   **Source:**
        -   EPI: `silver_epi{EPI_YEAR}variables` — built by `silver_to_gold` from bronze EPI weights (Yale `epi2024weights.csv`, ingested by `bronze_ingest_epi`); `NextLevel` is carried through so `parent_indicator` can be resolved. If the silver table is absent, an empty EPI indicator DataFrame is emitted (the gap is visible in `gold_dim_indicator`) — no NULL-weight fallback. *(Prior "`silver_epi2024variables2024-12-11`" wording stale since task-056 built `silver_epi{EPI_YEAR}variables` from bronze weights; the pre-task-056 "no silver_epi2024variables table / weights always NULL" gap is closed.)*
        -   WB: **none currently** — `silver_to_gold.Notebook` builds an *empty* WB-indicator DataFrame (`wb_vars`, ~line 1236) for schema compatibility, so no WB-sourced indicator rows exist. WGI reaches gold as country **coverage flags**, not as indicator rows.
4.  **`gold_dim_material`**
    -   **Surrogate Key:** `material_key` (BIGINT) - xxhash64 of material_name_std
    -   **Attributes:**
        -   `material_name_std` (STRING) - Standardized material name (InitCap format)
        -   `commodity_group` (STRING) - Material category (13 groups)
        -   `unit_base` (STRING) - Base unit of measure (kg)
        -   `is_placeholder` (BOOLEAN) - Flag for "Unknown Material"
    -   **Source:** Union of unique materials from silver_procurement and silver_globalsupplyshares
    -   **SCD Type:** Type 1 (overwrite)
    -   **Commodity Groups:** (13 categories)
        -   Battery metals (Lithium, Graphite, Nickel, Cobalt, Natural Graphite)
        -   Base metals (Copper, Aluminum/Aluminium, Zinc, Tin, Iron Ore, Lead, Magnesium)
        -   Precious metals (Gold, Silver, Platinum, Palladium, Rhodium, Iridium, Ruthenium)
        -   Rare earth elements (Neodymium, Praseodymium, Cerium, Lanthanum, Yttrium, Rare Earths (Ndpr), Erbium, Thulium, Holmium, Lutetium, Samarium)
        -   Specialty metals (Tungsten, Molybdenum, Titanium, Titanium Metal, Tantalum, Vanadium, Silicon Metal, Niobium, Arsenic, Selenium, Germanium, Hafnium, Rhenium, Zirconium, Bismuth)
        -   Industrial minerals (Limestone, Silica Sand, Kaolin, Strontium, Feldspar, Gypsum)
        -   Chemicals (Phosphorus, Phosphorous, Phosphate Rock, Potash, Sulphur)
        -   Energy materials (Coking Coal)
        -   Organic materials (Natural Rubber, Natural Teak Wood)
        -   Manufactured products (Electronics (controllers, Sensors), Plastic (Abs), Tires (rubber Compound), Steel (High-Tensile))
        -   Specialty gases (Helium, Neon)
        -   Other/Unknown (unclassified materials)
    -   **Lookup Table:** `gold_dim_material_lookup` with alias resolution and confidence scores
        -   Case variations (0.95 confidence)
        -   Spelling variants (0.95, e.g., Aluminum → Aluminium)
        -   Unit removal (0.90, e.g., "Copper (kg)" → "Copper")
5.  **`gold_dim_stage`**
    -   **Surrogate Key:** `stage_key` (BIGINT) - xxhash64 of stage_code
    -   **Purpose:** Supply chain production stage
    -   **Attributes:**
        -   `stage_code` (STRING) - "E" or "P"
        -   `stage_name` (STRING) - "Extraction" or "Processing"
    -   **Source:** Hardcoded dimension (2 rows)

**Data Quality & Audit Tables:** - `gold_unmapped_procurement_audit` - Procurement records with unmapped dimensions - `gold_unmapped_supply_audit` - Supply share records with unmapped dimensions (includes impact assessment) - `gold_data_quality_metrics` - Summary dashboard table with quality statistics - `gold_country_coverage_matrix` - Country presence across source systems - `mapping_country_aliases_confidence` - Country alias resolution rules - `mapping_material_aliases_confidence` - Material alias resolution rules

**Key Functions:** - `stable_key(cols)` - Generate deterministic 64-bit surrogate key via xxhash64 - `write_tbl(df, name)` - Write DataFrame to Delta table with overwrite - `check_unmapped(df, col, name)` - Log unmapped values for data quality monitoring

------------------------------------------------------------------------

## Orchestration

### Pipeline: `orchestrator_pipeline_bronze_to_gold.DataPipeline`

**Purpose:** End-to-end orchestration from ingestion to gold layer

**Pipeline Structure:**

**Stage 1: Bronze Ingestion (Parallel Execution)** — all activities timeout 12 hours

| # | Activity | Type | Sink / Output | Retry |
|---|----------|------|---------------|-------|
| 1 | `bronze_copy_eu_supply_shares` | Copy (HTTP → Lakehouse) | `bronze_eu_supply_shares` | 3 |
| 2 | `bronze_copy_global_supply_shares` | Copy (HTTP → Lakehouse) | `bronze_global_supply_shares` | 3 |
| 3 | `bronze_wgi` | Notebook | `bronze_wgi` | 2 |
| 4 | `bronze_copy_procurement_transactional` | Copy (Azure SQL → Lakehouse) | `bronze_procurement_transactional` | 3 |
| 5 | `bronze_copy_supplier_ref` | Copy (Azure SQL → Lakehouse) | `bronze_supplier_ref` | 3 |
| 6 | `bronze_epi` | Notebook | `bronze_epi2024results` and related tables | 2 |

**Retired (2026-07-31)** — row 4 was previously `bronze_procurement` / RefreshDataflow / `bronze_azureSQLdb2table`, producing both tables in one activity. It was replaced because a service principal cannot refresh a Dataflow Gen2 (`SPNBasedRefreshNotAllowed`) and every `fabric-cicd` publish strips its credentials. **No RefreshDataflow activities remain; the pipeline is SPN-safe end to end.** See `.claude/support/retired/bronze-azuresqldb2table-dataflow/manifest.json`.

Bronze now holds the source's raw day/year-transposed dates — a Copy activity cannot transform, so the correction moved to `bronze_to_silver`. Read silver, not bronze, for usable dates.

**Stage 2: Silver Transformation (Sequential)**

7.  `bronze_to_silver_cleaning` (Notebook Activity)
    -   Depends on: **all 6** bronze activities (Succeeded)

    -   Notebook: `bronze_to_silver.Notebook`

    -   Output: Silver tables (`silver_epi2024results`, `silver_globalsupplyshares`, `silver_wgi`, `silver_procurement`)

    -   Timeout: 12 hours

    -   Retry: 2 attempts

**Stage 3: Gold Transformation (Sequential)**

8.  `silver_to_gold` (Notebook Activity)
    -   Depends on: bronze_to_silver_cleaning (Succeeded)

    -   Notebook: `silver_to_gold.Notebook` — Output: Gold fact and dimension tables

    -   Timeout: 12 hours

    -   Retry: 2 attempts

**Stage 4: Data Quality (Sequential)**

9.  `data_quality_checks` (Notebook Activity)
    -   Depends on: silver_to_gold (Succeeded)

    -   Notebook: `data_quality_checks.Notebook`

    -   Purpose: Runs the bronze/silver/gold check suite. Blocking failures raise `DataQualityException`, failing the activity and halting the pipeline.

    -   Timeout: 12 hours

    -   Retry: 1 attempt

**Not orchestrated — and there is no warehouse.** No gold → warehouse sync activity exists. **Retired (2026-08-10)** — `oem_wh` was removed because nothing read it. A live catalogue query on that date returned 8 tables, **zero views and zero stored procedures**, so the "SQL endpoint, views, `usp_merge_fact_procurement`" this line previously pointed to never existed. A SQL interface over gold would now need both a new warehouse and a sync activity. See `.claude/support/retired/oem-wh-warehouse/manifest.json`.

**Pipeline Parameters:**

-   `procurement_array` (Array)

-   Configuration for procurement source-to-sink mappings

-   `p_full_load` (Boolean)

-   Flag for full vs incremental load (default: false)

-   `p_from_date` (String)

-   Start date for incremental load (default: "1900-01-01")

-   `p_epi_year` (String)

-   EPI vintage, default `"2024"`. **Load-bearing:** every EPI table-name contract derives from it (`bronze_epi{YEAR}results`, `silver_epi{YEAR}variables`, …), so changing it re-points the whole EPI chain. Single-sourced to the parameter cells of the EPI notebooks.

-   `p_execution_id` (String)

-   Correlation id for one pipeline run, default null. Written to `bronze_load_metadata` and `gold_pipeline_execution_log` so a watermark row can be traced back to the run that wrote it.

*All five verified against the live `getDefinition` payload 2026-08-06 (10 activities, 5 parameters).*

**Schedule:** **Active since 2026-08-05** — daily at **06:00 Europe/Stockholm**, schedule id `17288b67-a36f-4db8-88fe-cfa4ce1dba61`, enabled, no end date in practice (2099-01-01). Configured via Fabric's job scheduler, which is **not** part of the pipeline's item definition — it survives `fabric-cicd` publishes and is not represented in `pipeline-content.json`. Runs use the pipeline defaults (`p_full_load = false`, incremental). Verified end to end on 2026-08-05: a test firing **against a temporary 22:20 test time** started at `20:20:00.63Z` — the exact specified minute — ran 21.9 minutes, and completed as the first `invokeType=Scheduled` invocation in 58 runs. The schedule was then reset to 06:00. **That first morning firing has now been observed** (2026-08-06): run `df0cc54f-b3e4-46c9-bdd3-6b19efdf7381`, `invokeType=Scheduled`, started `04:00:01.24Z` = 06:00:01 Europe/Stockholm, Completed in 22.6 min, taking the Scheduled count 1 → 2. The 06:00 recurrence is therefore proven by observation, not only by mechanism. On-demand runs remain available and are unaffected. Runbook: `docs/guides/pipeline_schedule.md`.

**Error Handling:** Activity-level retry (1–3 retries depending on activity; retry intervals 30–300s depending on activity — see Technical Decisions #5 for per-activity values) plus a single terminal handler activity (`pipeline_error_handler`) that runs on every outcome and logs each activity to `gold_pipeline_execution_log`, **re-raising only when an activity's final attempt FAILED** (an activity retried into success is reported as recovered, not a run failure) to keep a genuinely failing run red. Canonical description: § Open Questions & Decisions Needed → Technical Decisions #5 (DEC-004, amended 2026-07-27). *(Supersedes the earlier "fail-fast, 0 retries" description — stale since task-011 shipped retry logic — and the "Upon-Failure paths" wording — stale since the 2026-07-27 amendment moved the handler onto every outcome — and the "re-raising on any FAILED" wording — stale since task-051 shipped final-attempt semantics, 2026-08-03, under which a retried-into-success activity is recovered, not a run failure.)*

**Notifications:** No email sink configured, and none is planned — **push notification was descoped 2026-08-05** (task-010, superseding the 2026-07-27 deferral of task-041 criterion 5). The pipeline's failure signal is `gold_pipeline_execution_log` plus the run reporting Failed via the handler's re-raise; that is *detection*, and it is unchanged. What was dropped is *push*. Two reasons: the tenant cannot deliver it (the Schedule pane's Failure-notifications field rejects addresses outside the organization, and the only tenant principal is a `.onmicrosoft.com` account with no Exchange mailbox — configuring it would satisfy the criterion while alerting into a void), and this is a single-operator project with no on-call, SLA, or downstream consumers. No `notifyOption` key exists anywhere in the pipeline definition. Upgrade paths, if push is ever wanted, are recorded in `docs/guides/pipeline_schedule.md § Failure Notifications`. Resolves the criterion DEC-004 parked here. See Technical Decisions #5.

**Dependencies:**

-   Stage 1 activities run in parallel (no dependencies)

-   Stage 2 waits for all 6 Stage 1 activities to succeed

-   Stage 3 waits for Stage 2 to succeed

-   Stage 4 waits for Stage 3 to succeed

------------------------------------------------------------------------

## Semantic Model & Reporting

### Semantic Model: `OEMInsightBI`

**Model Type:** Star Schema in **DirectLake** mode

-   DirectLake provides direct query to Delta tables in Fabric Lakehouse

-   No data import required - queries run directly on parquet files

-   Automatic refresh when lakehouse tables update

**Fact Tables:**

-   `fact_epi_score` - Environmental performance scores by country/indicator/year

-   `fact_procurement` - Procurement transactions with spend and quantity

-   `fact_supply_share` - Supply concentration by material/stage/country for **both** the global production mix and the EU sourcing mix (`supply_mix` discriminator)

**Derived / Calculated Tables:**

-   `gold_supply_risk` - derived from `fact_supply_share`; governance- & trade-weighted supply risk. **Grain: one row per material × stage × year.** Columns: `hhi_global`, `hhi_eu_sourcing`, `contrast_ratio`, `is_bottleneck`. Yearly grain, no date relationship (consistent with `fact_supply_share`). See § Business Logic & Calculations → Supply Risk.

**Dimension Tables:**

-   `gold_dim_country` - Country master with ISO codes and regions

-   `gold_dim_date` - Date dimension with calendar attributes

-   `gold_dim_indicator` - EPI and WGI indicator metadata

-   `gold_dim_material` - Material master with commodity groups

-   `gold_dim_stage` - Production stage (Extraction/Processing)

**Relationships:**

All relationships are **many-to-one** with **single direction** filtering (dimension filters fact).

1.  **Date Relationships:**
    -   `gold_dim_date[date_key]` (one) → `fact_procurement[date_key]` (many)
    -   Cardinality: 1:\*
    -   Filter direction: Single (date filters procurement)
    -   Note: fact_epi_score and fact_supply_share use year column, not date_key
2.  **Country Relationships:**
    -   `gold_dim_country[country_key]` (one) → `fact_procurement[production_country_key]` (many)
    -   `gold_dim_country[country_key]` (one) → `fact_epi_score[country_key]` (many)
    -   `gold_dim_country[country_key]` (one) → `fact_supply_share[country_key]` (many)
    -   Cardinality: 1:\* for all
    -   Filter direction: Single (country filters all facts)
    -   Note: fact_procurement has TWO country relationships (HQ and production)
3.  **Material Relationships:**
    -   `gold_dim_material[material_key]` (one) → `fact_procurement[material_key]` (many)
    -   `gold_dim_material[material_key]` (one) → `fact_supply_share[material_key]` (many)
    -   Cardinality: 1:\*
    -   Filter direction: Single (material filters facts)
4.  **Indicator Relationship:**
    -   `gold_dim_indicator[indicator_key]` (one) → `fact_epi_score[indicator_key]` (many)
    -   Cardinality: 1:\*
    -   Filter direction: Single (indicator filters scores)
5.  **Stage Relationship:**
    -   `gold_dim_stage[stage_key]` (one) → `fact_supply_share[stage_key]` (many)
    -   Cardinality: 1:\*
    -   Filter direction: Single (stage filters supply shares)

**Active Relationships:** All relationships are active (no inactive relationships defined)

**Role-Playing Dimensions:**

-   gold_dim_country plays two roles in fact_procurement (supplier HQ and production country)

**Key Measures/Calculations:**

-   The semantic model redesign and DAX measure implementation are complete (task-002, task-009).

-   40+ DAX measures are implemented and documented in `docs/dax_measure_library.md`.

-   Representative measures:

    -   Total Spend EUR = SUM(fact_procurement\[spend_eur\])

    -   Supplier Countries Count = DISTINCTCOUNT(fact_procurement\[supplier_hq_country_key\])

    -   Avg EPI Score = AVERAGE(fact_epi_score\[score\])

    -   Supply Concentration Index = MAX(fact_supply_share\[share_pct\]) filtered to `supply_mix = 'global'`

    -   Supply Risk (Global) = governance- & trade-weighted HHI, global supply mix

    -   Supply Risk (EU Sourcing) = the same index over the EU sourcing mix

    -   Supply Risk Contrast = DIVIDE(\[Supply Risk (EU Sourcing)\], \[Supply Risk (Global)\]) — blank when the global index is 0

*Names above match a live enumeration of the semantic model (45 measures, 2026-08-06). Two measures previously listed here — `Total Quantity` and `YoY Growth` — **do not exist in the model** and were removed rather than left as phantom references. `quantity_base` is NULL for non-mass units (see § Data Quality → Persistent advisory failures), so a naive `Total Quantity` would silently under-report; a year-over-year measure was never built.*

**Date Table Configuration:**

-   Date dimension connected to: fact_procurement\[date_key\] only

-   fact_epi_score uses year = 2024 (no date relationship)

-   fact_supply_share uses year = 2023 (no date relationship)

-   Time intelligence requires relationship to fact_procurement

### Power BI Report: `oem_report.Report`

The report was redesigned and rebuilt from scratch after the semantic model was finalized (task-003, task-013, task-014, task-016). The earlier report was discarded.

**RLS (Row-Level Security):** Designed (6 roles, see `docs/rls_security_strategy.md`). Portfolio demonstration only.

**Theme:** CY24SU10.json (Fabric default theme)

*Page/visual inventory remains to be documented — tracked under § Current State Assessment → Documentation.*

------------------------------------------------------------------------

## Current State Assessment

### What's Implemented ✅

**Bronze Layer:**

-   [x] Azure SQL ingestion — **Retired (2026-07-31)**: was `bronze_azureSQLdb2table.Dataflow`, now Copy activities `bronze_copy_procurement_transactional` + `bronze_copy_supplier_ref`. See `.claude/support/retired/bronze-azuresqldb2table-dataflow/manifest.json`.

-   [x] EPI ingestion (`bronze_ingest_epi.Notebook` — automated HTTP download from epi.yale.edu with retry; year-parameterised per task-028)

-   [x] WGI ingestion (`bronze_ingest_wgi.Notebook`, World Bank API)

-   [x] HTTP copy job for EU supply shares (`bronze_copy_eu_supply_shares`)

-   [x] Automated external data ingestion scripting (task-005)

**Silver Layer:**

-   [x] Cleaning notebook (`bronze_to_silver.Notebook`)

-   [x] Column standardization (lowercase, underscore separation)

-   [x] Data type conversions

-   [x] Unpivoting and reshaping

**Gold Layer:**

-   [x] Business logic notebook (`silver_to_gold.Notebook`)

-   [x] 3 fact tables created (procurement, supply_share, epi_score)

-   [x] 5 dimension tables created (country, date, indicator, material, stage)

-   [x] Surrogate key generation (xxhash64)

-   [x] Alias resolution for countries and materials

-   [x] Data quality scoring and confidence tracking

-   [x] Unmapped value handling with placeholders

-   [x] Audit trail tables for unmapped records

-   [x] Helper views for high-confidence data filtering

-   [x] Data quality observability tables (gold_quality_history, gold_gap_registry, gold_low_confidence_audit)

-   [x] `gold_supply_risk` — governance- & trade-weighted dual HHI, global vs EU-sourcing, with bottleneck flagging (task-038)

**Semantic Model:**

-   [x] Star schema defined

-   [x] DirectLake mode configured

-   [x] 8 relationships configured (all active, single-direction)

-   [x] Connection to Fabric lakehouse (`oem_lh`) established

-   [x] 40+ DAX measures (documented in `docs/dax_measure_library.md`)

-   [x] Data quality observability tables added to semantic model

-   [x] Cross-table relationship fixes for visuals

**Security:**

-   [x] Row-Level Security designed (6 roles — see `rls_security_strategy.md`)

**Testing:**

-   [x] Unit tests for transformation logic (**282 tests** as of 2026-08-06, `tests/`), including the notebook↔`src/` parity contract (task-032)

-   [x] CI pipeline: GitHub Actions with matrix testing (Python 3.10-3.12)

**Orchestration:**

-   [x] Pipeline created (`orchestrator_pipeline_bronze_to_gold.DataPipeline`)

-   [x] 4-stage sequential execution (bronze → silver → gold → data quality)

-   [x] Parallel bronze ingestion

-   [x] Dependency management configured

-   [x] Error handling & retry logic — Try-Catch pattern, activity-level retry (task-011)

**Reporting:**

-   [x] Power BI report created

-   [x] Theme applied (CY24SU10)

**Deployment:**

-   [x] Automated Fabric deployment on merge to main (`fabric-cicd` + GitHub Actions, Service Principal auth, dry-run mode)

### What's Incomplete/Needs Work ⚠️

**Remaining Technical Work** (mapped to tasks):

-   [x] Incremental load — end-to-end tested in Fabric (task-006_3, closed 2026-08-04)
-   [x] Pipeline scheduling — daily 06:00 Europe/Stockholm, live and observed firing (task-010, closed 2026-08-05)
-   [x] Performance retest — three warm-cache runs against the baseline; honest null result (task-012_5, closed 2026-08-03)
-   [x] External-data ingestion — end-to-end runtime verified (task-036, closed 2026-08-04)

**Documentation:**

-   [ ] Report page descriptions and visual inventory
-   [ ] Data lineage diagrams

### Known Issues/Technical Debt 🔴

**Permanent data limitation — WGI governance coverage.** The World Bank publishes no WGI for non-member states; Taiwan (TWN) has none and never will. This is not an aliasing defect and cannot be resolved by mapping. Affected rows carry `incomplete_wgi_coverage`; supply risk for Taiwan-supplied materials is **understated by construction**. NULL must never coerce to 0 (0 is a legitimate index value meaning diffuse supply).

**Accepted coupling — `fabric-cicd` private API.** See § Infrastructure & Deployment → CI/CD Deployment → Known Limitations.

No other open issues. Previously identified gap (data quality visibility) addressed via quality observability tables in tasks 018/019.

------------------------------------------------------------------------

## Development Workflow

### Source Control & Publishing

**Repository Structure:**

```         
/fabric
  ├── [Artifact].Dataflow/
  ├── [Artifact].Notebook/
  ├── [Artifact].DataPipeline/
  ├── [Artifact].SemanticModel/
  └── [Artifact].Report/
```

**Publish path:** The repo is the single source of truth. Pushing to `main` triggers `.github/workflows/deploy-fabric.yml`, which publishes `fabric/` to the workspace via `fabric-cicd`. Single developer, direct commits to main. DEC-007 established this as dry-run by default behind a staged gate; task-046 validated the live path and the default was flipped to real publish on 2026-08-01.

**Fabric Git integration: disconnected (2026-08-05).** The workspace was previously *also* connected to this repo through Fabric's built-in Git integration, giving two independent publish paths. `fabric-cicd` writes items through the REST API, and those writes never register in Git integration's sync state — so it drifted on every deploy, and its *Update from Git* action failed permanently with a "reserved name" collision. Reconnecting would not have fixed it: a fresh connection re-initializes clean, then goes stale again on the next push. To capture something authored in the Fabric UI (a dataflow mashup edit, item metadata), reconnect, sync **workspace → git**, commit, then disconnect again.

**Working Split with Claude Code:**

1.  **Author locally (Claude Code):** notebooks, SQL, TMDL, configs, and tests in the repo. Run the pytest suite against the transformation logic before committing.
2.  **Publish:** commit and push to `main`. The GitHub Action publishes `fabric/` to the workspace via `fabric-cicd`.
3.  **Run and observe (Fabric UI):** trigger the orchestrator pipeline, watch the run, and read the quality tables (`gold_quality_history`, `gold_gap_registry`). Measure after the **run**, not after the deploy — a green publish says nothing about runtime behavior.
4.  **Feed findings back (Claude Code):** file what the run surfaced as tasks, fix in the repo, push again.

Fabric UI edits are not a sync path — anything changed there is overwritten by the next publish unless it is first captured back into the repo (see § Source Control & Publishing).

### Naming Conventions

**Lakehouse Tables:**

-   `[layer].[entity_name]`

    -   Examples: `bronze_procurement_transactional`, `silver_procurement`, `gold_dim_country`

    -   Note: Some tables use underscore prefix (bronze\_), others use layer as prefix

**Notebooks:**

-   `[source]_to_[target].Notebook` for layer transitions; `[layer]_[verb]_[entity].Notebook` for ingestion

    -   Examples: `bronze_to_silver.Notebook`, `silver_to_gold.Notebook`, `bronze_ingest_wgi.Notebook`

    -   Reconciled to snake_case in Phase 5 (2026-08-04/05); the prior hyphen/underscore mix and the `2` version stamp are retired

**Dataflows:**

**Retired (2026-08-10)** — **no Dataflow Gen2 items remain.** `bronze_azureSQLdb2table` was retired 2026-07-31; `EPI_file2table` and `WGI_file2table` followed on 2026-08-10. The convention is retained for reference only. See `.claude/support/retired/epi-wgi-file2table-dataflows/manifest.json`.

-   `[layer]_[source]_[method]2table.Dataflow`

-   Examples (all retired): ~~`bronze_azureSQLdb2table`~~, ~~`EPI_file2table`~~, ~~`WGI_file2table`~~

**Pipelines:**

-   `[purpose]_pipeline_[scope].DataPipeline`

-   Example: `orchestrator_pipeline_bronze_to_gold`

**Consistency notes** *(measured 2026-08-10: **13 live workspace items**, 39 lakehouse tables)*:

-   Gold-layer tables use two prefix families: `fact_*` (3 tables) carries no `gold_` prefix while the other 20 gold-layer tables do. Deliberate, but worth knowing when globbing by prefix.

-   `silver_eusupplyshares` and `silver_globalsupplyshares` are concatenated rather than snake_case — **open** (Phase 5 Batch C, undecided). Any fix must use the underscore-**adding** form: the metastore lowercases identifiers, so a case-only rename is a silent no-op and `DROP TABLE` on the old casing destroys the live table. Four further tables read as concatenated but are **deliberate and must not be "fixed"** — `bronze_epi2024results`, `bronze_epi2024weights`, `silver_epi2024results`, `silver_epi2024variables` embed the EPI vintage because their names derive from the `p_epi_year` contract (§ Orchestration); renaming them breaks the parameterised chain.

-   `mapping_*` (2 tables) sits outside the medallion prefixes by design.

-   `sample_quality_data` does not participate in the pipeline. Renamed from `sample-quality-data` on 2026-08-10 — it was the last hyphenated notebook name. (`Notebook_1`, previously listed here, was deleted the same day.)

-   **Artifact rename targets are closed (2026-08-10).** `OEMInsightBI_v2` → `OEMInsightBI` and `report2` → `oem_report`, matching what `docs/standards/naming_standards.md` prescribes (a semantic model and a co-named report reading as one brand). Each was done live-rename-first, then repo lockstep; item IDs are unchanged by a rename, so the report→model binding was never disturbed. **One naming family remains open** — the concatenated silver tables above (Phase 5 Batch C, undecided).

-   Remaining non-snake_case names: `OEMInsightBI` and `oem_report` deliberately follow Fabric's PascalCase / project-prefixed display-name convention rather than snake_case (`naming_standards.md § Semantic Model & Report Naming`) — settled, and as of 2026-08-10 the `_v2` / `2` suffixes that were the open part are gone. All notebooks are snake_case. The Fabric-generated `StagingLakehouseForDataflows_*` / `StagingWarehouseForDataflows_*` (dataflow staging) and `Report Usage Metrics Model` / `Report Usage Metrics Report` names previously listed here were all deleted 2026-08-10, as were `EPI_file2table` / `WGI_file2table`. **`copyjob1` does not exist** in the workspace — 13 items enumerated 2026-08-10.

-   **Terminology carve-out — "DQ gate" is deliberate:** spec *prose* canonicalizes on "data quality" over the abbreviation "DQ" (FB-005, promoted 2026-05-17; re-swept 2026-08-10). **"DQ gate" is the single retained exception** — a coined term for the `BLOCKING_CHECKS` failure gate, used in § Technical Decisions and § Remaining Work, where the expanded "data quality gate" reads as needless length. After the 2026-08-10 sweep, and outside this bullet, those are the **only** two standalone occurrences of "DQ" in this spec — `grep -c '\bDQ\b' .claude/spec_v1.md` returns **3**, counting this bullet. A fourth is drift, not this carve-out.

------------------------------------------------------------------------

## Data Quality & Validation

### Data Quality Checks Implemented ✅

**Gold Layer Implementation:**

-   [x] Match confidence scoring (0-1 scale based on alias resolution)

-   [x] Quality categorization (High/Medium/Low/Unmapped)

-   [x] Unmapped value detection and logging

-   [x] Audit trail tables (gold_unmapped_procurement_audit, gold_unmapped_supply_audit)

-   [x] Impact assessment for unmapped supply shares

-   [x] Placeholder dimension assignment for unmapped values (no data loss)

-   [x] Coverage matrix for country presence across sources

**Silver Layer Implementation:**

-   [x] Score range validation (EPI 0-100) — *not applied to WGI; see § Data Transformations*

-   [x] Null filtering on key fields

-   [x] Duplicate removal

### Data Quality Checks Needed

*All **14** are implemented in `data_quality_checks.Notebook` — 9 from task-007, 3 from task-020 (bronze date-range validation, silver data-type consistency, silver completeness), and **2 from task-026: `lookup_name_uniqueness` (gold lookup dims) and `grain_uniqueness` (gold facts)**. Split: Bronze 5 / Silver 5 / Gold 4. The task-026 pair was previously omitted from this list even though **both are in `BLOCKING_CHECKS` and therefore halt the pipeline** — so the spec understated its own halt conditions (FR-060, corrected 2026-08-06). Count verified three ways: 14 `# CHECK N:` headers, 14 distinct `check_name` literals reaching `log_check_result`, 14 `CHECK_TO_DIMENSION` keys.*

**Bronze Layer Checks:**

-   [x] Row count validation (expected vs actual)

-   [x] Schema drift detection

-   [x] Null checks on required fields

-   [x] Duplicate detection (primary keys)

-   [x] Date range validation (no future dates, etc.)

**Silver Layer Checks:**

-   [x] Referential integrity (orphaned records)

-   [x] Business rule validation

-   [x] Data type consistency

-   [x] Outlier detection (amounts, quantities)

-   [x] Completeness checks

**Gold Layer Checks:**

-   [x] Aggregate totals reconciliation

-   [x] Historical trend validation (no sudden spikes/drops without explanation)

**Current Data Quality Implementation:**

-   Unmapped values: Logged to audit tables, assigned to placeholder dimensions

-   Failures: Logged with check_unmapped() function

-   Results: Stored in gold_data_quality_metrics table

-   Visualization: quality_category field available in facts for filtering

-   Data quality framework: **14** check functions across bronze/silver/gold in `data_quality_checks.Notebook` *(as of 2026-08-10; 9 from task-007, 3 from task-020, 2 from task-026)*; results persisted to gold_quality_history. **Three checks record a non-`pass` row on every run by design** — measured, explained and accepted in `docs/data_quality_framework.md § 7`; none is in `BLOCKING_CHECKS`, so the gate correctly never raises on them

-   Observability tables: gold_quality_history, gold_gap_registry, gold_low_confidence_audit (task-018)

### Pipeline Blocking Gate

Quality checks are not purely advisory. `data_quality_checks.Notebook` is the pipeline's terminal activity, and it **halts the pipeline** when any check in a fixed blocking set fails.

-   **Trigger:** `status == "fail"` for any check in `BLOCKING_CHECKS` *(13 entries as of 2026-08-10)*: schema validation on the core bronze tables plus `silver_epi2024results`, required-field completeness and duplicate detection on `bronze_procurement_transactional`, referential integrity at 0% tolerance on all three gold facts, lookup-name uniqueness on both lookup dimensions, and grain uniqueness on `fact_supply_share` / `fact_epi_score`.

-   **Mechanism:** a single `DataQualityException` raised **after** results are persisted, so a blocked run still leaves a full audit trail.

-   **Verdict rows:** the gate writes `entity = 'gate'` rows to `gold_quality_history` — `dq_gate_raised`, `dq_gate_blocking_failures`, and `dq_gate_blocking_evaluated` (which guards against a stale `BLOCKING_CHECKS` entry silently demoting a check to advisory). The gate outcome is therefore answerable from the table alone, without reading notebook source (DEC-003).

-   **Not the same as `breach_flag`.** `breach_flag` is a *score* threshold (`< 70.0`) and is advisory only. The two diverge routinely: a grain-uniqueness failure on 2 rows out of 2,561 scores ~99.9 — far above the breach threshold — yet halts the pipeline. **A run can record 0 breaches and still be a blocked run.** Asserting "the gate passed" from `breach_flag` reads the wrong field.

Membership of `BLOCKING_CHECKS` is a deliberate choice per check, not a severity level. New checks default to advisory; promoting one is an explicit decision (see `data_quality_framework.md § 6`).

### Expected Data Profiles

Synthetic dataset, **reproducible from the repo** since task-064. `/azure/` holds a `CREATE TABLE` script and a matching literal-`INSERT` seed script per table (`procurement.sql` + `procurement_seed.sql`, `supplier_info.sql` + `supplier_info_seed.sql`), so a fresh clone can rebuild both Azure SQL tables with no hand-seeding and no out-of-band file. The seed rows were exported from the lakehouse bronze copy of each table (Delta versions 101 and 99, 2026-08-11) rather than from Azure SQL directly, so no laptop firewall rule was reopened. Counts below are measured against the live lakehouse (2026-08-06) and match the committed seed.

**Procurement Transactions:** **132 records** (measured), key fields: date, materialname, suppliername, quantity, unitpriceeur. Bronze holds the source's raw day/year-transposed dates; silver corrects them to calendar 2024.

**EPI Scores:** ~180-200 countries, ~30-40 indicators (wide format in bronze), year 2024, score range 0-100

**WGI Indicators:** ~200+ countries, 6 WGI dimensions, years 1996-2023 (annual from 2002; biennial before), estimate scale approx. −2.5…+2.5. Grain in silver: one row per country per indicator per year.

**Supply Shares:**

-   Materials covered: 80+ critical raw materials

-   Countries covered: Global (major producers)

-   Stages: 2 (Extraction, Processing)

-   Share range: 0-100% (with "\<1%" special handling)

-   Year: 2023 (assigned in gold layer)

------------------------------------------------------------------------

## Infrastructure & Deployment

### Fabric Workspace Configuration

**Workspace Name:** OEMMatInsightBI

**Workspace ID:** 99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9 (from notebook metadata)

**Capacity:** Trial-20240714... (F64 SKU with 64 Capacity Units)

**Region:** Sweden Central

**Environment:** Personal Development / Portfolio Project

### Lakehouse Configuration

**Lakehouse Name:** `oem_lh` **Lakehouse ID:** 488fb9f8-e635-4683-90c4-ba4fee9dfadb (from notebook metadata) **Storage Structure:**

```         
/Files
  ├── /config (if used)
  ├── /schema_exports (for Claude Code sync)
  ├── /dq_reports (for Claude Code sync)
  └── /scripts

/Tables
  ├── /bronze (bronze_* tables)
  ├── /silver (silver_* tables)
  └── /gold (gold_dim_*, fact_*, mapping_*, v_* views)
```

**Partitioning Strategy:** Not applicable at portfolio scale — default Fabric behavior. **Optimization Settings:** Default V-Order (Fabric default for warehouse tables). **Format:** Delta Lake (confirmed from write operations)

### Warehouse Configuration

**Retired (2026-08-10)** — `oem_wh` was removed from the repo and the workspace. See `.claude/support/retired/oem-wh-warehouse/manifest.json`.

> ⚠️ **The "SQL Business Logic Objects" listed below never existed.** A live `sys.objects` query on 2026-08-10 returned 8 tables and **zero views, zero stored procedures**; all 8 tables had `modify_date == create_date == 2026-01-16`. The four `v_*` views and two `usp_*` procedures were specified and never built. Three of the `v_*` names do exist — as Spark-catalog views created inside `silver_to_gold.Notebook` over the lakehouse, invisible to any SQL endpoint (established independently by task-038_2). The section is retained as historical record, not as a description of shipped work.

**Warehouse Name:** `oem_wh`

**Warehouse ID:** b1cb7506-8d2d-4e4a-97cc-2b580da8eda0 (from `fabric/oem_wh.Warehouse/.platform`)

**Purpose:** SQL-queryable analytics layer with business-logic transformations. Combines mirrored gold tables from the Lakehouse with native SQL views and stored procedures.

**Tables/Views:**

-   Mirrors gold layer tables via Lakehouse-to-Warehouse sync (Copy Job)

-   Schema: dbo (default schema)

-   The semantic model does not query this warehouse — its DirectLake mode reads the `oem_lh` lakehouse's Delta/parquet tables directly (see § Semantic Model & Reporting)

**SQL Business Logic Objects (in `oem_wh`):**

The warehouse hosts SQL views and stored procedures that complement PySpark notebook transformations. This hybrid approach follows standard Fabric practice — notebooks handle complex ETL in the Lakehouse, SQL handles structured analytics and business rules in the Warehouse.

**Views:**
-   `dbo.v_procurement_summary` — Procurement spend aggregated by material, country, and time period with dimension attributes joined
-   `dbo.v_supply_concentration_risk` — Supply concentration risk analysis by material and stage, with risk tier classification (Critical/High/Medium/Low)
-   `dbo.v_supplier_sustainability_scorecard` — Combines procurement spend with EPI and WGI scores per supplier country for ESG reporting
-   `dbo.v_data_quality_overview` — Cross-table data quality summary (match rates, unmapped counts, confidence distributions)

**Stored Procedures:**
-   `dbo.usp_merge_fact_procurement` — Incremental MERGE for fact_procurement using watermark-based change detection. Demonstrates the Delta MERGE pattern in T-SQL as an alternative to PySpark.
-   `dbo.usp_refresh_quality_metrics` — Refreshes aggregated data quality metrics from audit tables

**Connection:**

-   Endpoint: 2BINPJYTVAEEVEF26XKMILPX4E-NXGOJGODN2TUTLWZW2NQJKL2VE.datawarehouse.fabric.microsoft.com

-   Database ID: b1cb7506-8d2d-4e4a-97cc-2b580da8eda0

### CI/CD Deployment

**Status: Implemented (Phase 4, 2026-08-01).** `.github/workflows/deploy-fabric.yml` and `fabric/parameter.yml` are live; `.github/workflows/test.yml` runs the test matrix.

**Approach:** Git-based deployment using Microsoft's `fabric-cicd` Python library + GitHub Actions (Microsoft CI/CD Option 2 — trunk-based with build environments).

**Why this approach:** `fabric-cicd` is the de facto standard for code-first Fabric deployment, maintained by Microsoft (MIT-licensed). It handles notebooks, pipelines, semantic models, environments, and lakehouses. Combined with GitHub Actions, it provides automated deployment on merge to main.

**Deployment Pipeline:**

-   **Trigger:** Push to `main` branch (after PR merge)
-   **Tool:** `fabric-cicd` library (`pip install fabric-cicd`)
-   **Authentication:** Service Principal with Fabric workspace contributor role
-   **Parameterization:** `parameter.yml` for environment-specific config (lakehouse IDs, connection strings)
-   **Key functions:** `publish_all_items()`, `unpublish_all_orphan_items()`

**GitHub Actions Workflow:** `.github/workflows/deploy-fabric.yml`

-   Install `fabric-cicd`
-   Authenticate via Service Principal (client ID, client secret, tenant ID stored as GitHub secrets)
-   Run `publish_all_items()` targeting the Fabric workspace
-   Environment-specific find-and-replace via `parameter.yml`

**Scope of deployment:** Metadata only — notebooks, pipelines, semantic model definitions, warehouse DDL. Data is never deployed; data population happens via the orchestrator pipeline.

**Additional capabilities beyond the original plan:**
-   Dry-run mode reporting the deployment plan without publishing
-   `fabric/archive/` excluded from publish via folder regex (`folder_exclude_regex = r"^/archive$"`, `.github/workflows/deploy-fabric.yml`) — the guard is retained deliberately, though the directory is currently empty

**Known Limitations:**
-   Notebook-to-Lakehouse bindings don't auto-update across environments — `parameter.yml` handles this
-   Lakehouse table data, shortcuts, and views are not deployed (metadata only)
-   **Dry-run mode couples to private `fabric-cicd` API.** Verified against 1.2.0 (2026-08-02): the library exposes no public dry-run or resolve-only entry point, so enumeration calls `_refresh_repository_items` / `_refresh_deployed_items`. Documented at the call site with an upgrade trigger; degrades to a warning rather than a hard failure if renamed. Tracked as task-047, closed won't-do — the criterion was gated on a library release that may never ship.

**Credentials:** Service Principal setup is a human task (Azure AD app registration, Fabric workspace permissions). Secrets stored in GitHub repository settings, never committed to code.

### Security & Access

**Authentication:**

-   Azure SQL: SQL authentication (see `secure/user_creation.sql`, `secure/grant_permissions.sql` — kept locally; `secure/` is gitignored)

-   Lakehouse: Workspace identity

-   Semantic Model: Workspace connection (from expressions.tmdl)

**Row-Level Security (RLS):**

-   Designed and documented (see `docs/rls_security_strategy.md`). 6 roles defined. Implementation is a portfolio demonstration — not enforced in a production sense.

**Access Control:** Single-developer portfolio project — no access control configuration needed.

------------------------------------------------------------------------

## Performance Optimization

### Current Performance Status

**Pipeline Runtime: Benchmarked** — 6 measured runs across two FINAL documents: `docs/performance_baseline.md` (3 runs, 2026-08-02) and `docs/performance_optimized.md` (3 runs, 2026-08-03), both at `p_full_load=false` on a warm cache. The headline is an honest **null result**: the primary target (`silver_to_gold`, ~58–60% of wall clock) came back **+6%, inside noise**, with one confirmed regression (`data_quality_checks`, +43%) and a functional total of +18%. Nothing measurably improved, which is a valid result for a pipeline that was already fast. No production load or SLA requirements; the >30% improvement target was retired 2026-07-29.

*Activity names in both documents predate the Phase 5 snake_case rename — see `performance_baseline.md § Activity names predate the Phase 5 rename` for the old→new mapping.*

**Optimization Opportunities:**

-   [x] ~~Partitioning strategy implementation~~ — **not applicable**, see § Open Questions & Decisions Needed → Technical Decisions 2. Task-012_2 was retired on this basis (2026-07-29).

-   [ ] Predicate pushdown in notebooks (some already implemented with filters)

-   [x] Incremental load activation — **built** (task-024, date-partition delete-insert; task-029, `bronze_load_metadata` high-water-mark). See § Open Questions & Decisions Needed → Technical Decisions 1.

-   [x] Caching strategies — **built** (task-012_3, closed 2026-08-02; `.cache()` on multi-action DataFrames, broadcast hints on small dim joins)

-   [x] ~~Index creation in warehouse~~ — **not applicable** (platform limitation), see DEC-012. Task-012_4 was retired on this basis (2026-08-03).

-   [x] DirectLake optimization (V-Order columnar format) — **built** (task-012_3, closed 2026-08-02; scoped to gold writes per DEC-011)

------------------------------------------------------------------------

## Testing Strategy

### Current Testing Status

**Unit Tests:** **300 tests** for transformation logic in `tests/` (as of 2026-08-11; originally 33 from task-008, since extended by task-020/027/032, the Phase 2–4 work, task-060's claim-scoped documentation guard, and task-063's country-alias regression coverage), including the notebook↔`src/` parity contract (task-032). **Integration Tests:** None yet. **Data Validation Tests:** Quality checks in gold layer + observability tables.

**Testing Approach:** *(counts in this section are measured against the suite at the date given on the Unit Tests line above)*

-   [x] Unit tests for transformation functions (stable_key, clean_and_rename, etc.) — task-008

-   [x] CI pipeline: GitHub Actions matrix testing (Python 3.10–3.12)

-   [ ] Schema validation tests

-   [x] Data quality tests (expand current checks) — `tests/test_data_quality.py` collects **45 tests** over the data quality functions, and the check suite itself was expanded twice (9 → 12 → 14; see § Data Quality & Validation)

-   [ ] Pipeline integration tests — none yet; the pipeline is exercised end to end by real runs, not by a test harness

-   [ ] Semantic model validation (relationship integrity)

-   [x] Regression tests for alias mappings — `tests/test_material_mapping.py` covers `MATERIAL_ALIASES` (7 tests, including that known-dead materials now resolve and that alias targets exist in the commodity map) and `tests/test_country_mapping.py` covers `country_aliases_with_confidence` (18 tests — the direction rule that keeps an alias target from orphaning against `gold_dim_country`, the confidence banding pinned to `alias_mappings.md`'s `match_type` taxonomy and the 0.95 `gold_low_confidence_audit` threshold, the Congo / Korea / Türkiye groups that must be edited as a set, resolution of the spellings that historically failed, and that an unmapped country lands in the audit under its own spelling rather than silently defaulting). Both seeds are read live from the notebook via `ast`, so editing a seed is what makes the guard fail — task-063

**Test Data:** Synthetic. **`/azure/` contains DDL plus a committed seed per table** (two `CREATE TABLE` scripts and two literal-`INSERT` scripts totalling 132 procurement rows and 11 supplier rows), so the Azure SQL rows are reproducible from the repo (task-064). Local unit tests use PySpark test fixtures in `tests/`.

------------------------------------------------------------------------

## Business Logic & Calculations

### Key Business Rules

**Supply Risk (primary measure — DEC-001 Option B):**

Governance- and trade-weighted Herfindahl index, computed **per stage** (E/P) with the bottleneck stage flagged (see Bottleneck handling below):

```
HHI_WGI,t = Σ_c (Sᶜ)² · WGIᶜ · tᶜ
```

Per country `c`:

-   `Sᶜ` — supply share (fraction)

-   `tᶜ` — trade parameter from source data (0.8 EU, 1.0 baseline non-EU, \>1 export-restricted)

-   `WGIᶜ` — governance risk weight in `0..1` where **1 = worst governance**, derived as the rescaled **inverse** of the mean of all six WGI dimensions for the latest year available per country:

```
WGIᶜ = clamp( (2.5 − mean₆(WGI estimates for c, latest year available)) / 5 , 0, 1 )
```

Rescaling uses the **fixed theoretical bounds of the World Bank estimate scale (−2.5..+2.5), not the observed min/max of the loaded set.** This is a reproducibility requirement: with observed bounds, adding a country or a new WGI vintage silently re-ranks every material, and the before/after comparison the model is validated against would not be stable between runs. The clamp handles the rare country whose mean estimate falls outside ±2.5.

**The inversion is mandatory.** Raw WGI runs ≈ −2.5..+2.5 with *higher = better* governance. Used unmodified as a multiplier it would *reward* poorly-governed sourcing — the index would still compute and still look plausible, but every risk ranking would be backwards. The spec requires the inverted, rescaled form.

Computed over two supply mixes and exposed in `gold_supply_risk` (**grain: one row per material × stage × year**):

-   `hhi_global` — global production mix (`supply_mix = 'global'`)

-   `hhi_eu_sourcing` — EU sourcing mix (`supply_mix = 'eu_sourcing'`)

-   `contrast_ratio` = `hhi_eu_sourcing / hhi_global` — EU sourcing concentration relative to global (`1.4` = EU sourcing is 40% more concentrated than the world). **NULL when `hhi_global` = 0.**

-   `is_bottleneck` (BOOLEAN) — marks the stage with the higher `hhi_global` per material × year

**Bottleneck handling.** The methodology reports SR at the bottleneck stage (E/P). Gold retains **both** stages and flags the bottleneck rather than collapsing to one row, so the extraction-vs-processing comparison stays available to the report while the headline figure needs no DAX ranking pattern. The flag is driven by `hhi_global`, not by `hhi_eu_sourcing` or the max of the two, so it stays defined when EU coverage is missing.

**EU coverage gaps.** A material × stage with global supply data but no EU sourcing rows yields `hhi_eu_sourcing = NULL` and `contrast_ratio = NULL` — **never 0**, which would misread as "no EU concentration risk" (0 is a legitimate index value meaning perfectly diffuse supply). Coverage is measured and surfaced via the existing `check_unmapped` mechanism (§ Data Quality & Validation), not silently dropped.

**Scope boundary (DEC-001):** no import-reliance blend of the two indices into a single SR (Option C); no recycling (`EoL_RIR`) or substitution (`SI_SR`) filters (Option D). These figures are therefore **gross** supply risk and **must be labelled as such in the report** — they are not official EU CRM SR values.

**Supplier Concentration Risk (secondary lens — retained):**

-   Definition: Percentage of global supply from single country

-   Calculation: MAX(share_pct) per material/stage

-   Threshold for "high risk":

    -   Critical: \>50% from single country

    -   High: \>30%

    -   Medium: \>20%

    -   Low: ≤20%

-   Source: Implemented in v_supply_concentration_risk view, filtered to `supply_mix = 'global'`

-   Retained alongside the weighted model as a simple, intuitive concentration view; the report presents the two side by side.

**Environmental Score Aggregation:**

-   Individual indicators stored separately in fact_epi_score (no composite scoring)

-   Weighting approach: EPI provides weights per indicator (stored in gold_dim_indicator.weight)

**Supply Share Calculation:**

-   Formula: Pre-calculated percentages from source data (EU CRM)

-   Time period: Annual snapshot (2023)

-   Special handling: "\<1%" converted to 0.5% (midpoint estimate)

**Material Categorization:**

-   Categories: 13 commodity groups (see gold_dim_material section)

-   Hierarchy: Single-level (no sub-categories)

-   Mapping: Hardcoded in silver_to_gold.Notebook grp_map dictionary

**Unit Normalization:**

-   Base unit: kg (kilograms)

-   Conversion factors:

    -   kg = 1.0

    -   g = 0.001

    -   mg = 0.000001

    -   t (tonne) = 1000.0

-   Applied in: fact_procurement (quantity_base calculation)

**Date Logic:**

-   Calendar year only (no fiscal year). Reporting periods: Daily grain available in gold_dim_date with quarter/month aggregations

### DAX Measures (High-Level)

See `docs/dax_measure_library.md` for the full measure library. **45 measures live in the model** (enumerated 2026-08-06); names below are that enumeration. Key measures:

-   Total Spend EUR = SUM(fact_procurement\[spend_eur\])

-   Total Spend by Country = spend rolled to supplier HQ country

-   Supplier Countries Count = DISTINCTCOUNT(fact_procurement\[supplier_hq_country_key\])

-   Materials Count = DISTINCTCOUNT(fact_procurement\[material_key\])

-   Transaction Count = row count of fact_procurement

-   Avg EPI Score = AVERAGE(fact_epi_score\[score\])

-   Weighted EPI Score = `AVERAGEX`-wrapped weight-weighted EPI across sub-indicators. **Reads 0–100 at every grain, including the grand total** (44.14 world-wide across 180 countries, 58.59 filtered to `region = "Europe"`), since task-061 wrapped the per-country weighted average in `AVERAGEX(VALUES(gold_dim_country[country_key]), …)` so the denominator scales with country cardinality rather than summing the 58 fixed weights once. A single-country context is bit-for-bit unchanged (max delta 0.0 across all 194 country keys). Slice by country or a country attribute; a value repeating identically down a non-country axis signals that the axis does not filter `fact_epi_score`. Canonical definition: `docs/dax_measure_library.md § 2.2`.

-   Supply Concentration Index = MAX(fact_supply_share\[share_pct\]) filtered to `supply_mix = 'global'` *(secondary lens)*

-   Supply Risk (Global) = governance- & trade-weighted HHI over the global supply mix

-   Supply Risk (EU Sourcing) = the same index over the EU sourcing mix

-   Supply Risk Contrast = DIVIDE(\[Supply Risk (EU Sourcing)\], \[Supply Risk (Global)\]) — EU-specific exposure; blank when the global index is 0

**Named here previously but NOT in the model** — removed rather than left as phantom references (verified against the 45-measure enumeration, 2026-08-06): `Total Spend` (actual name is `Total Spend EUR`), `Supplier Count` (actual name is `Supplier Countries Count`), `Total Quantity`, `Avg Unit Price`, `YoY Spend Growth`, `Spend by Commodity Group`, `High Risk Sourcing %`. No year-over-year measure of any name exists. A `Total Quantity` would need care rather than a plain SUM: `quantity_base` is NULL for non-mass units (24 of 132 procurement rows are `pcs`), so a naive sum silently under-reports — see § Data Quality and `docs/data_quality_framework.md § 7.2`.

------------------------------------------------------------------------

## Dependencies & External Systems

### Upstream Dependencies

**Azure SQL Database:**

-   **Server:** procurement-supplier.database.windows.net

-   **Database:** procurement-supplier-db

-   **Tables:** dbo.procurement_transactional, dbo.supplier_ref

-   Connection string/endpoint: Managed via the Fabric connection `oem_azuresql_procurement` (credential in Fabric's connection store, never in a tracked file)

-   Refresh schedule: Manual — pipeline triggered on demand

**EPI Dataset:**

-   Source: Yale EPI (https://epi.yale.edu/), automated HTTPS download

-   Update schedule: Annual (typically Q2-Q3 each year)

-   File location: n/a — fetched at runtime by `bronze_ingest_epi.Notebook`, not pre-staged

-   Ingestion: `bronze_ingest_epi.Notebook` — automated HTTP download, no manual upload

-   Current year: 2024

**WGI Dataset:**

-   Source: World Bank (WGI = World Governance Indicators)

-   Update schedule: Annual (typically Q3-Q4)

-   File location: N/A — `bronze_ingest_wgi.Notebook` pulls directly from the World Bank API

-   Ingestion: `bronze_ingest_wgi.Notebook` (World Bank API, automated)

-   Current year: 2020 (filtered in transformation)

**EU CRM Supply Shares:**

-   Source: GitHub repository CSV file (HTTP endpoint)

-   Update schedule: Tracks EU CRM study releases (irregular)

-   Connection type: HTTP REST endpoint

-   Current year: 2023 (assigned in gold layer)

### Downstream Consumers

**Power BI Report:**

-   Report ID: `oem_report.Report` (in `/fabric` folder; renamed from `report2.Report` on 2026-08-10. The superseded `report.Report` was removed from `fabric/archive/` on 2026-08-01 by workspace-sync commit `d128664` and survives only in git history at `d128664~1`)

-   Portfolio demonstration — no external consumers

-   Refresh schedule: Automatic with DirectLake (on lakehouse update)

-   Published via Fabric workspace (DirectLake mode)

**Semantic Model**

-   Connected applications: Power BI reports via DirectLake

-   Query mode: DirectLake (direct parquet file access)

-   Refresh: Automatic (no explicit refresh needed with DirectLake)

**Other Systems:** None — no downstream consumers beyond Power BI.

------------------------------------------------------------------------

## Open Questions & Decisions Needed

### Technical Decisions

1.  **Incremental vs Full Load:**
    -   **DECISION:** Incremental load for `fact_procurement` (the only table with ongoing transactional data). External data tables (EPI, WGI, Supply Shares) remain full-load on their annual refresh cycle.
    -   **Pattern (BUILT — task-024, 2026-07-14):** transaction-grain **date-partition delete-insert** over a 7-day look-back window, with the window driven by the `p_from_date` pipeline parameter. Deliberately *not* a natural-key MERGE: two same-day purchases of the same material from the same supplier are legitimate distinct transactions, and a natural-key merge either crashed on multiple source matches or silently collapsed them.
    -   **Incremental key:** `Date` field from `dbo.procurement_transactional` (transaction date)
    -   **High-water mark (BUILT — task-029, 2026-07-28):** the `bronze_load_metadata` table and its parameter flow are implemented notebook-side and verified end to end in Fabric. Gold coordination uses `exclude_execution_id` per DEC-006.
    -   **Separate artifact:** `usp_merge_fact_procurement` (T-SQL MERGE) remains as a skill demonstration of the Delta MERGE pattern in T-SQL — it is **not** the live load path.
    -   **Why:** `mode("overwrite")` erases the Delta log and forces a full DirectLake semantic model reload. Delete-insert preserves the VertiPaq column store while keeping transaction grain.
    -   **Post-load maintenance:** Run `OPTIMIZE` on gold tables after each incremental load. V-Order enabled by default in Warehouse.
2.  **Partitioning Strategy:**
    -   **DECISION:** Not applicable at portfolio scale — default Fabric behavior sufficient. No custom partitioning needed.
3.  **SCD Implementation:**
    -   Which dimensions need history tracking?
    -   Type 1 vs Type 2?
    -   **DECISION:** Currently all Type 1 (overwrite)
    -   **Recommendation:** Consider Type 2 for gold_dim_country, gold_dim_material if names/attributes change
4.  **Data Retention:**
    -   **DECISION:** Not applicable — portfolio project with no retention policy needed. All layers kept indefinitely.
5.  **Error Handling:**
    -   **DECISION (DEC-004, 2026-07-23, amended 2026-07-27):** Activity-level retry plus a single pipeline-level error-handler activity on the terminal node, logging every activity's outcome to `gold_pipeline_execution_log`.
    -   **Pattern:** Each activity keeps its retry count (1–3 retries, i.e. 2–4 total attempts) and interval (30–300s: 30s for bronze_wgi/bronze_epi, 120s for bronze_to_silver_cleaning/silver_to_gold/data_quality_checks, 300s for the four Copy activities). One handler activity (`pipeline_error_handler`) depends on the terminal activity `data_quality_checks` via `['Succeeded','Failed','Skipped']` — so it runs on every outcome — and reads per-activity results via POST `queryactivityruns` (not `@activity('X').Error`, which has no `error` field on Skipped activities). It writes one log row **per attempt** (Succeeded rows included), then collapses those per-attempt rows to one final terminal outcome per activity (ranking `activityRunStart`, since `queryactivityruns` always returns `retryAttempt` as null) and **re-raises `RuntimeError` only when an activity's final attempt FAILED** — so an activity retried into success is reported as recovered (logged, not a run failure) while a genuinely failed activity keeps the run red. Non-notebook activities (Copy) are covered because the handler reads the run's activity-run records directly, not via in-notebook `try/except`.
    -   **Why:** Fabric has no pipeline-level retry — only activity-level. A handler on `['Failed','Skipped']` only (the original 2-activity shape) never fires on a clean run and so cannot log successes; running on every outcome and re-raising when an activity's final attempt fails (a retried-into-success activity is recovered, not a run failure) gives both coverage and the red-on-failure guard in one activity. The re-raise is the Try-Catch-trap defence: a bare on-failure branch that succeeds makes the whole run report Success and would silently undo the DQ gate.
    -   **Notification (criterion 5 — resolved 2026-08-05 as DESCOPED, superseding the 2026-07-27 deferral):** email push is not configured and will not be. The Schedule pane's native Failure-notifications field refuses addresses outside the organization, and the tenant's only principal is a `.onmicrosoft.com` account without an Exchange mailbox, so a configured alert would fire into a void — false confidence, worse than none. The pipeline's failure signal remains `gold_pipeline_execution_log` plus the run reporting Failed via the handler's re-raise. *Correcting the prior text: the pipeline carries **no** `notifyOption` key at all (verified 2026-08-05 — zero occurrences across all 10 activities: 6 TridentNotebook + 4 Copy). The earlier "`MailOnFailure` would cover only 1/8 activities" was wrong on both the mechanism and the count.*

### Business Decisions

1.  **EPI Indicator Selection:**
    -   **DECISION:** All indicators included in fact_epi_score. No custom weighting or filtering — the full EPI dataset is available for Power BI exploration. Users can filter by policy objective or issue category in the report.
2.  **Supplier Risk Thresholds:**
    -   **DECISION:** Concentration risk thresholds implemented (Critical >50%, High >30%, Medium >20%, Low ≤20%), retained as a secondary lens.
    -   **DECISION (DEC-001, 2026-07-19 — supersedes the previous deferral):** Governance-weighted supply risk is **in scope**. The earlier "ESG risk scoring (composite EPI + WGI) deferred — out of scope for current phases" no longer holds: DEC-001 Option B brings WGI into the supply-risk model as a weight on the Herfindahl index. See § Business Logic & Calculations → Supply Risk. **EPI remains outside the risk model** — it stays a separate environmental measure; only WGI is incorporated.
3.  **Reporting Granularity:**
    -   Daily, weekly, monthly aggregates?
    -   **DECISION:** Daily grain in fact_procurement, yearly grain in fact_epi_score and fact_supply_share
    -   **Current:** gold_dim_date provides daily grain with month/quarter/week attributes
4.  **Material Hierarchy:**
    -   **DECISION:** Single-level hierarchy (13 commodity groups). Sub-categories not needed — sufficient analytical granularity for the portfolio use case.
5.  **Fiscal Calendar:**
    -   **DECISION:** Calendar year only. No fiscal year logic — the synthetic procurement data doesn't model a specific organization's fiscal calendar.

------------------------------------------------------------------------

## Next Steps & Priorities

### Phase Structure

| Phase | Focus | Status | Acceptance Criteria |
|-------|-------|--------|-------------------|
| Phase 1 | Core Data Model & Reports | **Complete (9/9)** — task-034 absorbed | Gold tables populated, semantic model connected, Power BI report built |
| Phase 2 | Automation & Quality | **Complete (45/45)** — closed 2026-08-05; gate 2→3 approved | Incremental load works for fact_procurement, data quality checks run in pipeline, external data ingestion scripted |
| Phase 3 | Operations & Performance | **Complete (14/14)** — task-012_5 closed 2026-08-03, task-010 closed 2026-08-05; task-012_4 absorbed | Error handling with Try-Catch in pipeline, pipeline scheduling configured, basic performance review done |
| Phase 4 | CI/CD Deployment | **Complete (6/6)** — task-043…046 shipped; task-048/049 folded in; task-047 closed won't-do | GitHub Actions workflow deploys Fabric artifacts on merge to main via `fabric-cicd` |

### Phase 4 — CI/CD Deployment

**Goal:** Automated deployment pipeline — the one production-readiness pattern not covered by the companion NordGrid project.

**Deliverables:**

1. **GitHub Actions workflow** using `fabric-cicd` library (owner: both — Claude writes workflow, Erik configures Service Principal + GitHub secrets)
   - `parameter.yml` for environment-specific configuration (lakehouse IDs, connection strings)
   - Service Principal authentication (human task: Azure AD app registration)
   - Deployment triggered on merge to main

2. ~~**SQL Warehouse Analytics Layer** — already implemented (4 views + 2 stored procedures in `oem_wh`).~~ — **Retired (2026-08-10).** Never implemented: the objects were specified but never built, and the warehouse itself was removed. The shipped analytics surface is the gold layer plus 45 DAX measures over DirectLake.

### Remaining Work

**All Phase 1–4 build scope is closed.** Phase 5 is the accuracy-of-the-record fix queue that phase-level verification produced; the dashboard is the authority for current task counts and statuses. The four Fabric-UI-gated tasks previously listed here resolved as: **task-036** and **task-006_3** on 2026-08-04 (full-load + incremental runs, duplicate check clean); **task-012_5** on 2026-08-03 (three warm-cache runs against the task-012_1 baseline, after the `OPTIMIZE` prerequisite); **task-010** on 2026-08-05 (daily 06:00 schedule live and verified firing).

Descoped: task-034 (Data Gaps report page — optional surface; the underlying table and measures shipped under task-001). Closed won't-do: task-047 (see § CI/CD Deployment → Known Limitations). Retired: task-012_4's warehouse-index deployment (DEC-012 — `fabric/sql/warehouse_indexes.sql` is a finding document, not deployable DDL).

**Verification and hygiene status (no build scope remains):**

1. **Phase-level verification has run and PASSED.** `.claude/verification-result.json` is the authority for its result, fingerprint and date (DEC-022, template-tier — `.claude/rules/spec-workflow.md`) — this section deliberately does not restate them, because recording a result in the spec changes the spec fingerprint and thereby invalidates the very result being recorded. The first phase-level run was 2026-08-05, the first in the project's history. It was validated on live evidence (live DAX over the gold tables, repo-vs-workspace pipeline definition byte-identical, DQ gate rows, green deploys, the test suite) and produced fix tasks 057–061, **every one of them accuracy-of-the-record rather than correctness-of-the-build** — the build was sound; the spec's description of it is what needed work. This section is part of that correction.
2. **Open friction:** tracked in `.claude/support/friction.jsonl`, which is the authority for what is open. The dominant mechanism is FR-052's class — a false status assertion baked into a pinned section fingerprint, invisible to fingerprint-based drift detection because the stale text is *inside* the hash rather than differing from it. That class is why this section points at authorities instead of restating them.
3. **First 06:00 scheduled firing — CONFIRMED 2026-08-06.** Run `df0cc54f-b3e4-46c9-bdd3-6b19efdf7381`, `invokeType=Scheduled`, started `04:00:01.24Z` = 06:00:01 Europe/Stockholm, Completed in 22.6 min; Scheduled count 1 → 2. This was the schedule's last link resting on mechanism rather than observation, and it now rests on observation. See § Orchestration → Schedule.

------------------------------------------------------------------------

## Appendix: Sample Data Patterns

### Sample Procurement Record

**From azure/procurement.sql schema:**

```         
Date: 2024-01-15
MaterialName: "Lithium"
SupplierName: "Acme Mining Corp"
Region: "Americas"
Quantity: 1000.00
Unit: "kg"
UnitPriceEUR: 45.50

(After join with dbo.supplier_ref:)
HeadquartersCountry: "United States of America"
ProductionCountry: "Chile"
```

### Sample EPI Record

**From silver_epi2024results (wide format):**

```         
code: 840
iso: "USA"
country: "United States of America"
EPI: 51.2
[30+ indicator columns with scores]

(After pivot to fact_epi_score:)
country_key: <hash>
indicator_key: <hash>
year: 2024
score: 51.2
```

### Sample WB Record (retired lineage — see § Data Transformations)

**From silver_WB (retired — no live artifact produces this table):**

```         
country_code: "USA"
country_name: "United States"
indicator_code: "GE.EST"
indicator_name: "Government Effectiveness: Estimate"
topic: "Economic Policy"
score: 85.3
(year 2020 filtered)
```

### Sample Supply Share Record

**From silver_globalsupplyshares:**

```         
material: "Lithium"
stage: "E"
country: "Chile"
share: "45%"

(After transformation to fact_supply_share:)
material_key: <hash for "Lithium">
stage_key: <hash for "E">
country_key: <hash for "Chile">
year: 2023
share_pct: 45.0
```

------------------------------------------------------------------------

## Contact & Ownership

**Project Owner:** Personal Portfolio Project\
**Technical Lead:** Personal Portfolio Project\
**Business Analyst:** Personal Portfolio Project\
**Stakeholders:** (Emulated) Procurement teams, Sustainability/ESG teams