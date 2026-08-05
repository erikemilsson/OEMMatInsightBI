---
version: 1
status: active
created: 2025-11-14
updated: 2026-08-05
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
> -   Context documentation (`.claude/support/documents/`)
>
> -   Reference files (`.claude/support/reference/`)
>
> -   Standards and conventions (`.claude/support/documents/standards/`)

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

**Secondary Purpose:** This project also serves as hands-on preparation for a data engineering consultant role (Rejlers). Beyond demonstrating a working BI solution, it exercises production patterns commonly encountered at client sites: incremental Delta MERGE loading, SQL warehouse stored procedures alongside PySpark notebooks, pipeline error handling with retry logic, and CI/CD deployment via GitHub Actions. The hybrid Lakehouse + Warehouse approach reflects standard Fabric practice.

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

-   **Warehouse:** `oem_wh` (SQL-queryable layer for BI)

-   **Semantic Model:** `OEMInsightBI_v2` (Power BI data model; old `semantic_model_oeminsightbi` archived in `fabric/archive/`)

-   **Report:** Power BI report connected to semantic model

**Development Environment:**

-   Python 3.12 (local virtual environment: `.venv`)

-   PySpark (Fabric notebooks)

-   Power Query M (Dataflows)

-   SQL (Azure SQL, Fabric Warehouse)

**Version Control:**

-   Git repository structure exists in `/fabric` folder

-   Each Fabric artifact has `.platform` metadata

-   Git integration with Fabric workspace via single-developer direct commits to main

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

-   `dbo.Procurement` → `bronze_procurement_transactional`

-   Purchase orders, suppliers, materials, dates, amounts

-   `dbo.SupplierInfo` → `bronze_supplier_ref`

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

**Schema scripts** (in `/azure` folder — tracked):

-   `procurement.sql` - Procurement table schema/data

-   `supplier_info.sql` - Supplier reference schema/data

**Key Columns:**

**`dbo.Procurement` table:**

-   `Date` (DATE) - Transaction date, used for date dimension join

-   `MaterialName` (NVARCHAR(100)) - Material identifier for material dimension

-   `SupplierName` (NVARCHAR(200)) - Supplier identifier, join key to supplier_ref

-   `Region` (NVARCHAR(100)) - Supplier region

-   `Quantity` (DECIMAL(18,2)) - Purchase quantity

-   `Unit` (NVARCHAR(50)) - Unit of measure (kg, t, g, etc.)

-   `UnitPriceEUR` (DECIMAL(18,2)) - Price per unit in EUR

-   **Primary key:** None defined (transactional data)

**`dbo.SupplierInfo` table:**

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

**Single-vintage caveat.** The naming is parameterized at both ends but **hardcoded in the middle**: `bronze_to_silver.Notebook` names `bronze_epi2024results` and `silver_epi2024results` literally (lines 74, 108). Changing the vintage at either end therefore breaks the chain rather than moving it. A second hardcoded reference sits in `data_quality_checks.Notebook`'s `BLOCKING_CHECKS` as `("schema_validation", "oem_lh.silver_epi2024results")` — and a stale entry there does **not** error, it silently demotes that check to advisory. Only the 2024 vintage is supported today; **task-042** carries the parameterization.

**Update Frequency:** Annual (EPI releases yearly)

**File Location:** Manual CSV file upload. (Task created to investigate automating ingestion).

**File Format:** CSV (inferred from dataflow type)

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

-   *(The pipeline currently selects only identity columns — `country_iso3`, `country_name`, `indicator_name` — discarding `Year`/`Value`. Corrected by task-031; made mandatory by DEC-001.)*

**Update Frequency:** Annual (World Bank releases Q3-Q4)

#### 4. Supply Shares (EU CRM Data) - External Data

**Source:** EU Critical Raw Materials supply chain data

**Two complementary tables from the same EU CRM study — NOT duplicates.** Both are required inputs to the Supply Risk model (see § Business Logic & Calculations → Supply Risk):

| | Global supply | EU sourcing |
|---|---|---|
| Bronze | `bronze_global_supply_shares` | `bronze_eu_supply_shares` |
| Silver | `silver_globalsupplyshares` | `silver_eusupplyshares` — **planned (task-038), not yet built** |
| Measures | where a material is produced worldwide | where the EU actually sources it from |

**Current-state caveat:** the EU table is orphaned at the silver boundary — `bronze_to_silver.Notebook` reads only the Global table, so `bronze_eu_supply_shares` has no silver consumer today. Wiring EU sourcing into silver is DEC-001 Option B work, tracked in task-038.

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

-   **Must preserve `Year` and `Value`** — the governance scores are the `WGIᶜ` input to the Supply Risk model (§ Business Logic & Calculations). *Currently dropped by the pipeline; corrected by task-031.*

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

-   `silver_eusupplyshares` *(planned — task-038; see § Data Architecture → Supply Shares)*

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
        -   WB: **none currently** — `silver_to_gold.Notebook:883` builds an *empty* WB-indicator DataFrame for schema compatibility, so no WB-sourced indicator rows exist. WGI reaches gold as country **coverage flags**, not as indicator rows.
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

**Planned — not yet orchestrated:** warehouse sync (gold → `oem_wh`). No pipeline activity exists for this today. The warehouse itself is real — see § Infrastructure & Deployment (SQL endpoint, views, `usp_merge_fact_procurement`); only the automated sync is outstanding.

**Pipeline Parameters:**

-   `procurement_array` (Array)

-   Configuration for procurement source-to-sink mappings

-   `p_full_load` (Boolean)

-   Flag for full vs incremental load (default: false)

-   `p_from_date` (String)

-   Start date for incremental load (default: "1900-01-01")

**Schedule:** Not configured. The pipeline is run manually.

**Error Handling:** Activity-level retry (1–3 retries depending on activity; retry intervals 30–300s depending on activity — see Technical Decisions #5 for per-activity values) plus a single terminal handler activity (`pipeline_error_handler`) that runs on every outcome and logs each activity to `gold_pipeline_execution_log`, **re-raising only when an activity's final attempt FAILED** (an activity retried into success is reported as recovered, not a run failure) to keep a genuinely failing run red. Canonical description: § Open Questions & Decisions Needed → Technical Decisions #5 (DEC-004, amended 2026-07-27). *(Supersedes the earlier "fail-fast, 0 retries" description — stale since task-011 shipped retry logic — and the "Upon-Failure paths" wording — stale since the 2026-07-27 amendment moved the handler onto every outcome — and the "re-raising on any FAILED" wording — stale since task-051 shipped final-attempt semantics, 2026-08-03, under which a retried-into-success activity is recovered, not a run failure.)*

**Notifications:** No on-demand-firing sink configured. `notifyOption` remains `NoNotification`; the notification criterion (task-041 criterion 5) is deferred with reason until task-010 (scheduling) lands. See Technical Decisions #5.

**Dependencies:**

-   Stage 1 activities run in parallel (no dependencies)

-   Stage 2 waits for all 6 Stage 1 activities to succeed

-   Stage 3 waits for Stage 2 to succeed

-   Stage 4 waits for Stage 3 to succeed

------------------------------------------------------------------------

## Semantic Model & Reporting

### Semantic Model: `OEMInsightBI_v2`

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

-   40+ DAX measures are implemented and documented in `.claude/support/documents/dax_measure_library.md`.

-   Representative measures:

    -   Total Spend = SUM(fact_procurement\[spend_eur\])

    -   Total Quantity = SUM(fact_procurement\[quantity_base\])

    -   Supplier Count = DISTINCTCOUNT(fact_procurement\[supplier_hq_country_key\])

    -   Avg EPI Score = AVERAGE(fact_epi_score\[score\])

    -   Supply Concentration Index = MAX(fact_supply_share\[share_pct\]) filtered to `supply_mix = 'global'`

    -   Supply Risk (Global) = governance- & trade-weighted HHI, global supply mix

    -   Supply Risk (EU Sourcing) = the same index over the EU sourcing mix

    -   Supply Risk Contrast = DIVIDE(\[Supply Risk (EU Sourcing)\], \[Supply Risk (Global)\]) — blank when the global index is 0

    -   YoY Growth = \[Calculate current vs previous year\]

**Date Table Configuration:**

-   Date dimension connected to: fact_procurement\[date_key\] only

-   fact_epi_score uses year = 2024 (no date relationship)

-   fact_supply_share uses year = 2023 (no date relationship)

-   Time intelligence requires relationship to fact_procurement

### Power BI Report: `report2.Report`

The report was redesigned and rebuilt from scratch after the semantic model was finalized (task-003, task-013, task-014, task-016). The earlier report was discarded.

**RLS (Row-Level Security):** Designed (6 roles, see `.claude/support/documents/rls_security_strategy.md`). Portfolio demonstration only.

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

-   [x] 40+ DAX measures (documented in `.claude/support/documents/dax_measure_library.md`)

-   [x] Data quality observability tables added to semantic model

-   [x] Cross-table relationship fixes for visuals

**Security:**

-   [x] Row-Level Security designed (6 roles — see `rls_security_strategy.md`)

**Testing:**

-   [x] Unit tests for transformation logic (235 tests, `tests/`), including the notebook↔`src/` parity contract (task-032)

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

-   [ ] Incremental load — implementation done (006_1a/1b/1c/2); end-to-end testing in Fabric remains (task-006_3)
-   [ ] Pipeline scheduling (task-010)
-   [ ] Performance retest — optimizations applied (012_3, 012_4); before/after measurement remains (task-012_5)
-   [ ] External-data ingestion — automated in code; end-to-end runtime verification remains (task-036)

**Documentation:**

-   [ ] Report page descriptions and visual inventory
-   [ ] Data lineage diagrams

### Known Issues/Technical Debt 🔴

**Permanent data limitation — WGI governance coverage.** The World Bank publishes no WGI for non-member states; Taiwan (TWN) has none and never will. This is not an aliasing defect and cannot be resolved by mapping. Affected rows carry `incomplete_wgi_coverage`; supply risk for Taiwan-supplied materials is **understated by construction**. NULL must never coerce to 0 (0 is a legitimate index value meaning diffuse supply).

**Accepted coupling — `fabric-cicd` private API.** See § Infrastructure & Deployment → CI/CD Deployment → Known Limitations.

No other open issues. Previously identified gap (data quality visibility) addressed via quality observability tables in tasks 018/019.

------------------------------------------------------------------------

## Development Workflow

### Current Git Integration

**Repository Structure:**

```         
/fabric
  ├── [Artifact].Dataflow/
  ├── [Artifact].Notebook/
  ├── [Artifact].DataPipeline/
  ├── [Artifact].SemanticModel/
  └── [Artifact].Report/
```

**Git Status:** Repository synced with Fabric workspace via Git integration. Single developer, direct commits to main. CI/CD deployment pipeline planned (Phase 4) to formalize this with `fabric-cicd` + GitHub Actions.

**Desired Workflow with Claude Code:**

1.  **Morning (Claude Code):**
    -   Pull latest from Git
    -   Sync Fabric state (read any exported metadata)
    -   Review tasks
    -   Develop locally (notebooks, SQL, configs)
    -   Push changes to feature branch
2.  **Afternoon (Fabric UI):**
    -   Pull feature branch in Fabric
    -   Test notebooks with real data
    -   Run data quality checks
    -   Export schemas/data quality reports
    -   Commit results back to Git
3.  **Evening (Claude Code):**
    -   Pull latest (includes data quality reports)
    -   Sync state, review issues
    -   Create tasks for any problems
    -   Plan next day

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

**Retired (2026-07-31)** — the example below no longer exists. The convention itself still stands for `EPI_file2table` / `WGI_file2table`, which remain as items.

-   `[layer]_[source]_[method]2table.Dataflow`

-   Examples: ~~`bronze_azureSQLdb2table`~~ (retired), `EPI_file2table`, `WGI_file2table`

**Pipelines:**

-   `[purpose]_pipeline_[scope].DataPipeline`

-   Example: `orchestrator_pipeline_bronze_to_gold`

**Consistency Issues:**

-   Table naming mixes bronze\_/silver\_/gold_dim\_ prefixes

-   Notebooks use both hyphens and underscores as separators

-   Some artifact names use camelCase (copyjob1), others use underscores

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

*All 12 of these are implemented in `data_quality_checks.Notebook` — 9 from task-007, plus 3 from task-020 (bronze date-range validation, silver data-type consistency, silver completeness).*

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

-   DQ framework: 12 check functions across bronze/silver/gold in `data_quality_checks.Notebook` (9 from task-007, 3 from task-020); results persisted to gold_quality_history

-   Observability tables: gold_quality_history, gold_gap_registry, gold_low_confidence_audit (task-018)

### Pipeline Blocking Gate

Quality checks are not purely advisory. `data_quality_checks.Notebook` is the pipeline's terminal activity, and it **halts the pipeline** when any check in a fixed blocking set fails.

-   **Trigger:** `status == "fail"` for any check in `BLOCKING_CHECKS` — currently **13 entries**: schema validation on the core bronze tables plus `silver_epi2024results`, required-field completeness and duplicate detection on `bronze_procurement_transactional`, referential integrity at 0% tolerance on all three gold facts, lookup-name uniqueness on both lookup dimensions, and grain uniqueness on `fact_supply_share` / `fact_epi_score`.

-   **Mechanism:** a single `DataQualityException` raised **after** results are persisted, so a blocked run still leaves a full audit trail.

-   **Verdict rows:** the gate writes `entity = 'gate'` rows to `gold_quality_history` — `dq_gate_raised`, `dq_gate_blocking_failures`, and `dq_gate_blocking_evaluated` (which guards against a stale `BLOCKING_CHECKS` entry silently demoting a check to advisory). The gate outcome is therefore answerable from the table alone, without reading notebook source (DEC-003).

-   **Not the same as `breach_flag`.** `breach_flag` is a *score* threshold (`< 70.0`) and is advisory only. The two diverge routinely: a grain-uniqueness failure on 2 rows out of 2,561 scores ~99.9 — far above the breach threshold — yet halts the pipeline. **A run can record 0 breaches and still be a blocked run.** Asserting "the gate passed" from `breach_flag` reads the wrong field.

Membership of `BLOCKING_CHECKS` is a deliberate choice per check, not a severity level. New checks default to advisory; promoting one is an explicit decision (see `data_quality_framework.md § 6`).

### Expected Data Profiles

Synthetic dataset — exact counts depend on Azure SQL seed scripts in `/azure/`.

**Procurement Transactions:** ~500 records, key fields: date, materialname, suppliername, quantity, unitpriceeur

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
-   Retired artifacts under `fabric/archive/` excluded from publish via folder regex

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

-   Designed and documented (see `.claude/support/documents/rls_security_strategy.md`). 6 roles defined. Implementation is a portfolio demonstration — not enforced in a production sense.

**Access Control:** Single-developer portfolio project — no access control configuration needed.

------------------------------------------------------------------------

## Performance Optimization

### Current Performance Status

**Pipeline Runtime:** Not benchmarked — manual pipeline runs at portfolio scale. No production load or SLA requirements.

**Optimization Opportunities:**

-   [x] ~~Partitioning strategy implementation~~ — **not applicable**, see § Open Questions & Decisions Needed → Technical Decisions 2. Task-012_2 was retired on this basis (2026-07-29).

-   [ ] Predicate pushdown in notebooks (some already implemented with filters)

-   [x] Incremental load activation — **built** (task-024, date-partition delete-insert; task-029, `bronze_load_metadata` high-water-mark). See § Open Questions & Decisions Needed → Technical Decisions 1.

-   [ ] Caching strategies *(task-012_3)*

-   [x] ~~Index creation in warehouse~~ — **not applicable** (platform limitation), see DEC-012. Task-012_4 was retired on this basis (2026-08-03).

-   [ ] DirectLake optimization (V-Order columnar format) *(task-012_3)*

------------------------------------------------------------------------

## Testing Strategy

### Current Testing Status

**Unit Tests:** 235 tests for transformation logic in `tests/` (as of 2026-08-03; originally 33 from task-008, since extended by task-020/027/032 and the Phase 2–4 work), including the notebook↔`src/` parity contract (task-032). **Integration Tests:** None yet. **Data Validation Tests:** Quality checks in gold layer + observability tables.

**Testing Approach:**

-   [x] Unit tests for transformation functions (stable_key, clean_and_rename, etc.) — task-008

-   [x] CI pipeline: GitHub Actions matrix testing (Python 3.10–3.12)

-   [ ] Schema validation tests

-   [ ] Data quality tests (expand current checks)

-   [ ] Pipeline integration tests

-   [ ] Semantic model validation (relationship integrity)

-   [ ] Regression tests for alias mappings

**Test Data:** Synthetic data generated via SQL scripts in `/azure/`. Local unit tests use PySpark test fixtures in `tests/`.

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

See `.claude/support/documents/dax_measure_library.md` for the full measure library (40+ measures). Key measures:

-   Total Spend = SUM(fact_procurement\[spend_eur\])

-   Total Quantity = SUM(fact_procurement\[quantity_base\])

-   Avg Unit Price = DIVIDE(\[Total Spend\], \[Total Quantity\])

-   Supplier Count = DISTINCTCOUNT(fact_procurement\[supplier_hq_country_key\])

-   Material Count = DISTINCTCOUNT(fact_procurement\[material_key\])

-   Avg EPI Score = AVERAGE(fact_epi_score\[score\])

-   Supply Concentration = MAX(fact_supply_share\[share_pct\]) filtered to `supply_mix = 'global'` *(secondary lens)*

-   Supply Risk (Global) = governance- & trade-weighted HHI over the global supply mix

-   Supply Risk (EU Sourcing) = the same index over the EU sourcing mix

-   Supply Risk Contrast = DIVIDE(\[Supply Risk (EU Sourcing)\], \[Supply Risk (Global)\]) — EU-specific exposure; blank when the global index is 0

-   YoY Spend Growth = \[Calculate vs previous year\]

-   Spend by Commodity Group = \[Sum spend joined to material dimension\]

-   High Risk Sourcing % = \[Procurement from countries with low EPI/WGI scores\]

------------------------------------------------------------------------

## Dependencies & External Systems

### Upstream Dependencies

**Azure SQL Database:**

-   **Server:** procurement-supplier.database.windows.net

-   **Database:** procurement-supplier-db

-   **Tables:** dbo.Procurement, dbo.SupplierInfo

-   Connection string/endpoint: Managed via the Fabric connection `oem_azuresql_procurement` (credential in Fabric's connection store, never in a tracked file)

-   Refresh schedule: Manual — pipeline triggered on demand

**EPI Dataset:**

-   Source: Yale EPI (https://epi.yale.edu/), file-based dataflow ingestion

-   Update schedule: Annual (typically Q2-Q3 each year)

-   File location: Manual CSV upload to Fabric Lakehouse Files

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

-   Report ID: `report2.Report` (in `/fabric` folder; old `report.Report` archived in `fabric/archive/`)

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
    -   **Incremental key:** `Date` field from `dbo.Procurement` (transaction date)
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
    -   **Notification (criterion 5, deferred 2026-07-27 with reason):** no on-demand-firing sink exists until task-010 (scheduling) lands; `notifyOption='MailOnFailure'` would now cover only 1/8 activities after the EPI/WGI repoint. Revisit at task-010. The pipeline's failure signal is `gold_pipeline_execution_log` plus the run reporting Failed via the handler's re-raise.

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
| Phase 1 | Core Data Model & Reports | **Complete (10/10)** | Gold tables populated, semantic model connected, Power BI report built |
| Phase 2 | Automation & Quality | Active (36/38) — task-006_3, task-036 remain (both Fabric-run verification) | Incremental load works for fact_procurement, data quality checks run in pipeline, external data ingestion scripted |
| Phase 3 | Operations & Performance | Active (13/15) — task-010 (scheduling, On Hold) + task-012_5 (perf retest) | Error handling with Try-Catch in pipeline, pipeline scheduling configured, basic performance review done |
| Phase 4 | CI/CD Deployment | **Complete (7/7)** — task-043…046 shipped; task-048/049 folded in | GitHub Actions workflow deploys Fabric artifacts on merge to main via `fabric-cicd` |

### Phase 4 — CI/CD Deployment

**Goal:** Automated deployment pipeline — the one production-readiness pattern not covered by the companion NordGrid project.

**Deliverables:**

1. **GitHub Actions workflow** using `fabric-cicd` library (owner: both — Claude writes workflow, Erik configures Service Principal + GitHub secrets)
   - `parameter.yml` for environment-specific configuration (lakehouse IDs, connection strings)
   - Service Principal authentication (human task: Azure AD app registration)
   - Deployment triggered on merge to main

2. **SQL Warehouse Analytics Layer** — already implemented (4 views + 2 stored procedures in `oem_wh`). No additional work needed.

### Remaining Work

Four tasks remain, all gated on Fabric-UI execution by the project owner. They are not sequential — they collapse into a single Fabric session:

**Prerequisites (must precede the measured runs):** `OPTIMIZE` on gold tables (task-012_3 AC2); ~~deploy `fabric/sql/warehouse_indexes.sql` (task-012_4 AC5)~~ — retired DEC-012 (file is now a finding document, not deployable DDL). Running the retest before OPTIMIZE invalidates the comparison.

1. **task-036** — external-data e2e: satisfied by any complete pipeline run (EPI/WGI ingest identically in both parameter modes).
2. **task-006_3** — incremental load: one full-load run (`p_full_load=true`, which must log FULL LOAD — the runtime proof for task-039's parameters cell) plus one incremental run, then the duplicate check.
3. **task-012_5** — performance retest: three incremental warm-cache runs, matching the task-012_1 baseline methodology.
4. **task-010** — scheduling: configure the daily 06:00 run; the first scheduled execution supplies its own evidence.

Descoped: task-034 (Data Gaps report page — optional surface; the underlying table and measures shipped under task-001). Closed won't-do: task-047 (see § CI/CD Deployment → Known Limitations).

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

(After join with SupplierInfo:)
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