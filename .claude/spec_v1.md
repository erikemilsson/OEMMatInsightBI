---
version: 1
status: active
created: 2025-11-14
updated: 2026-07-20
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
> -   Context documentation (`.claude/context/`)
>
> -   Reference files (`.claude/reference/`)
>
> -   Standards and conventions (`.claude/context/standards/`)

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

-   Connection strings: Managed via Fabric dataflow connections

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

-   Fabric Dataflow: `bronze_azureSQLdb2table.Dataflow`

-   Frequency: Manual — pipeline triggered on demand

-   Incremental vs Full Load: Parameters exist (`p_full_load`, `p_from_date`); incremental logic implementation is task-006

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

**Ingestion Method:** `EPI_file2table.Dataflow`

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

-   Bronze table: `bronze_epi2024results`

-   Silver table: `silver_epi2024results`

**Update Frequency:** Annual (EPI releases yearly)

**File Location:** Manual CSV file upload. (Task created to investigate automating ingestion).

**File Format:** CSV (inferred from dataflow type)

#### 3. World Governance Indicators (WGI) - External Data

**Source:** World Bank WGI, via the World Bank API

**Ingestion Method:** `bronze_ingest_wgi.Notebook` (PySpark, API-based). Supersedes the retired `WGI_file2table.Dataflow` CSV lineage.

**Content:** Country-level governance quality metrics across 6 governance dimensions

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

-   **Six** indicators are ingested, not five. Coverage rules must test against six.

-   *(The pipeline currently selects only identity columns — `country_iso3`, `country_name`, `indicator_name` — discarding `Year`/`Value`. Corrected by task-031; made mandatory by DEC-001.)*

**Update Frequency:** Annual (World Bank releases Q3-Q4)

#### 4. Supply Shares (EU CRM Data) - External Data

**Source:** EU Critical Raw Materials supply chain data

**Two complementary tables from the same EU CRM study — NOT duplicates.** Both are required inputs to the Supply Risk model (see § Business Logic & Calculations → Supply Risk):

| | Global supply | EU sourcing |
|---|---|---|
| Bronze | `bronze_GlobalSupplyShares` | `bronze_EUSupplyShares` |
| Silver | `silver_globalsupplyshares` | `silver_eusupplyshares` — **planned (task-038), not yet built** |
| Measures | where a material is produced worldwide | where the EU actually sources it from |

**Current-state caveat:** the EU table is orphaned at the silver boundary — `bronze-to-silver.Notebook` reads only the Global table, so `bronze_EUSupplyShares` has no silver consumer today. Wiring EU sourcing into silver is DEC-001 Option B work, tracked in task-038.

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

**Notebook:** `bronze-to-silver.Notebook`

**Purpose:** Standardize raw data from multiple sources

**Specific Cleaning Logic:**

**1. EPI Data (`bronze_epi2024results` → `silver_epi2024results`):**

-   Drop all columns ending with `.old`

-   Remove `.new` suffix from column names

-   Cast `code` column to INTEGER

-   Select only: code, iso, country, EPI columns

-   Write to: `silver_epi2024results`

**2. Global Supply Shares (`bronze_GlobalSupplyShares` → `silver_globalsupplyshares`):**

-   Convert column headers to lowercase

-   Replace spaces with underscores

-   Drop `t` column (unused)

-   Write to: `silver_globalsupplyshares`

**3. World Governance Indicators (`bronze_WGI` → `silver_wgi`):**

-   Source: World Bank API via `bronze_ingest_wgi.Notebook` — long format, one row per country per indicator per year

-   Standardize `Country Code` → `country_iso3` (UPPER, trimmed); trim `Country Name` and `Series Name`

-   **Must preserve `Year` and `Value`** — the governance scores are the `WGIᶜ` input to the Supply Risk model (§ Business Logic & Calculations). *Currently dropped by the pipeline; corrected by task-031.*

-   Coverage rules test against **six** indicators (not five)

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

-   `bronze_GlobalSupplyShares`

-   `bronze_EUSupplyShares`

-   `bronze_WGI`

-   `bronze_procurement_transactional`

-   `bronze_supplier_ref`

**Output Tables:** (in silver lakehouse)

-   `silver_epi2024results`

-   `silver_globalsupplyshares`

-   `silver_wgi`

-   `silver_procurement`

**Data Quality Rules Applied:**

-   Null filtering on key fields (iso3 for countries, scores for metrics)

-   Type casting with validation (integers, doubles)

-   Score range validation (0-100 for WB indicators)

-   Duplicate removal on natural keys

### Silver → Gold: Business Logic & Aggregations

**Notebook:** `silver-to-gold2.Notebook`

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
    -   **Grain:** One row per material × stage × country × year
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
    -   **Audit Tables:** `gold_unmapped_supply_audit`
    -   **Views:**
        -   `v_fact_supply_share_high_confidence` (quality \>= 0.9, no unknowns)
        -   `v_fact_supply_share_complete` (all data with quality flags and warnings)
        -   `v_supply_concentration_risk` (risk analysis by material/stage)
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
        -   Primary: EPI (`silver_epi2024results`) only — *the World Bank ESG source was removed; `silver-to-gold2.Notebook:244` builds the primary dimension from EPI data alone*
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
        -   `parent_indicator` (BIGINT) - Parent indicator key (currently NULL)
    -   **Source:**
        -   EPI: `silver_epi2024variables2024-12-11` table
        -   WB: **none currently** — `silver-to-gold2.Notebook:883` builds an *empty* WB-indicator DataFrame for schema compatibility, so no WB-sourced indicator rows exist. WGI reaches gold as country **coverage flags**, not as indicator rows.
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
| 1 | `bronzecopy_EUSupplyShares` | Copy (HTTP → Lakehouse) | `bronze_EUSupplyShares` | 3 |
| 2 | `bronzecopy_GlobalSupplyShares` | Copy (HTTP → Lakehouse) | `bronze_GlobalSupplyShares` | 3 |
| 3 | `bronze_WGI` | RefreshDataflow | `bronze_WGI` | 2 |
| 4 | `bronze_procurement` | RefreshDataflow | `bronze_procurement_transactional`, `bronze_supplier_ref` | 3 |
| 5 | `bronze_EPI` | RefreshDataflow | `bronze_epi2024results` and related tables | 2 |

**Stage 2: Silver Transformation (Sequential)**

6.  `bronze-to-silver data cleaning` (Notebook Activity)
    -   Depends on: **all 5** bronze activities (Succeeded)

    -   Notebook: `bronze-to-silver.Notebook`

    -   Output: Silver tables (`silver_epi2024results`, `silver_globalsupplyshares`, `silver_wgi`, `silver_procurement`)

    -   Timeout: 12 hours

    -   Retry: 2 attempts

**Stage 3: Gold Transformation (Sequential)**

7.  `silver-to-gold` (Notebook Activity)
    -   Depends on: bronze-to-silver data cleaning (Succeeded)

    -   Notebook: `silver-to-gold2.Notebook` — Output: Gold fact and dimension tables

    -   Timeout: 12 hours

    -   Retry: 2 attempts

**Stage 4: Data Quality (Sequential)**

8.  `data_quality_checks` (Notebook Activity)
    -   Depends on: silver-to-gold (Succeeded)

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

**Error Handling:** Activity-level retry (1-3 attempts depending on activity, 30-second intervals) with Upon-Failure paths to shared error logging. Canonical description: § Open Questions & Decisions Needed → Technical Decisions #5. *(Supersedes the earlier "fail-fast, 0 retries" description — stale since task-011 shipped retry logic.)*

**Notifications:** NoNotification configured on dataflow refreshes

**Dependencies:**

-   Stage 1 activities run in parallel (no dependencies)

-   Stage 2 waits for all 5 Stage 1 activities to succeed

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

-   `fact_supply_share` - Global supply concentration by material/stage/country

-   `gold_supply_risk` - Governance- & trade-weighted supply risk by material/stage (`hhi_global`, `hhi_eu_sourcing`, contrast). Yearly grain, no date relationship (consistent with `fact_supply_share`). See § Business Logic & Calculations → Supply Risk.

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

    -   Supply Concentration Index = MAX(fact_supply_share\[share_pct\])

    -   Supply Risk (Global) = governance- & trade-weighted HHI, global supply mix

    -   Supply Risk (EU Sourcing) = the same index over the EU sourcing mix

    -   Supply Risk Contrast = EU-sourcing vs global (EU-specific exposure)

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

-   [x] Azure SQL dataflow (`bronze_azureSQLdb2table.Dataflow`)

-   [x] EPI file ingestion (`EPI_file2table.Dataflow`)

-   [x] WGI file ingestion (`WGI_file2table.Dataflow`)

-   [x] HTTP copy job for EU supply shares (`bronzecopy_EUSupplyShares`)

-   [x] Automated external data ingestion scripting (task-005)

**Silver Layer:**

-   [x] Cleaning notebook (`bronze-to-silver.Notebook`)

-   [x] Column standardization (lowercase, underscore separation)

-   [x] Data type conversions

-   [x] Unpivoting and reshaping

**Gold Layer:**

-   [x] Business logic notebook (`silver-to-gold2.Notebook`)

-   [x] 3 fact tables created (procurement, supply_share, epi_score)

-   [x] 5 dimension tables created (country, date, indicator, material, stage)

-   [x] Surrogate key generation (xxhash64)

-   [x] Alias resolution for countries and materials

-   [x] Data quality scoring and confidence tracking

-   [x] Unmapped value handling with placeholders

-   [x] Audit trail tables for unmapped records

-   [x] Helper views for high-confidence data filtering

-   [x] Data quality observability tables (gold_quality_history, gold_gap_registry, gold_low_confidence_audit)

**Semantic Model:**

-   [x] Star schema defined

-   [x] DirectLake mode configured

-   [x] 8 relationships configured (all active, single-direction)

-   [x] Connection to Fabric warehouse established

-   [x] 40+ DAX measures (documented in `.claude/support/documents/dax_measure_library.md`)

-   [x] Data quality observability tables added to semantic model

-   [x] Cross-table relationship fixes for visuals

**Security:**

-   [x] Row-Level Security designed (6 roles — see `rls_security_strategy.md`)

**Testing:**

-   [x] Unit tests for transformation logic (33 tests, `tests/`)

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

### What's Incomplete/Needs Work ⚠️

**Remaining Technical Work** (mapped to tasks):

-   [ ] Incremental load — implementation done (006_1a/1b/1c/2); end-to-end testing in Fabric remains (task-006_3)
-   [ ] Pipeline scheduling (task-010)
-   [ ] Performance optimization (task-012, broken into 012_1–012_5)
-   [ ] CI/CD deployment via `fabric-cicd` (Phase 4)

**Documentation:**

-   [ ] Report page descriptions and visual inventory
-   [ ] Data lineage diagrams

### Known Issues/Technical Debt 🔴

No open issues. Previously identified gap (data quality visibility) addressed via quality observability tables in tasks 018/019.

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

-   `[purpose]_[source]to[target].Notebook`

    -   Examples: `bronze-to-silver.Notebook`, `silver-to-gold2.Notebook`

    -   Inconsistency: Uses both underscores and hyphens

**Dataflows:**

-   `[layer]_[source]_[method]2table.Dataflow`

-   Examples: `bronze_azureSQLdb2table`, `EPI_file2table`, `WGI_file2table`

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

-   [x] Score range validation (0-100 for WB indicators)

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

### Expected Data Profiles

Synthetic dataset — exact counts depend on Azure SQL seed scripts in `/azure/`.

**Procurement Transactions:** ~500 records, key fields: date, materialname, suppliername, quantity, unitpriceeur

**EPI Scores:** ~180-200 countries, ~30-40 indicators (wide format in bronze), year 2024, score range 0-100

**WGI Indicators:** ~200+ countries, 6 governance dimensions, year 2020, score range 0-100

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

**Warehouse ID:** b1cb7506-8d2d-4e4a-97cc-2b580da8eda0 (from expressions.tmdl)

**Purpose:** SQL-queryable analytics layer with business-logic transformations. Combines mirrored gold tables from the Lakehouse with native SQL views and stored procedures.

**Tables/Views:**

-   Mirrors gold layer tables via Lakehouse-to-Warehouse sync (Copy Job)

-   Schema: dbo (default schema)

-   DirectLake queries these tables directly from parquet files

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

**Approach:** Git-based deployment using Microsoft's `fabric-cicd` Python library + GitHub Actions (Microsoft CI/CD Option 2 — trunk-based with build environments).

**Why this approach:** `fabric-cicd` is the de facto standard for code-first Fabric deployment, maintained by Microsoft (MIT-licensed). It handles notebooks, pipelines, semantic models, environments, and lakehouses. Combined with GitHub Actions, it provides automated deployment on merge to main.

**Deployment Pipeline:**

-   **Trigger:** Push to `main` branch (after PR merge)
-   **Tool:** `fabric-cicd` library (`pip install fabric-cicd`)
-   **Authentication:** Service Principal with Fabric workspace contributor role
-   **Parameterization:** `parameter.yml` for environment-specific config (lakehouse IDs, connection strings)
-   **Key functions:** `publish_all_items()`, `unpublish_all_orphan_items()`

**GitHub Actions Workflow:** `.github/workflows/fabric-deploy.yml`

-   Install `fabric-cicd`
-   Authenticate via Service Principal (client ID, client secret, tenant ID stored as GitHub secrets)
-   Run `publish_all_items()` targeting the Fabric workspace
-   Environment-specific find-and-replace via `parameter.yml`

**Scope of deployment:** Metadata only — notebooks, pipelines, semantic model definitions, warehouse DDL. Data is never deployed; data population happens via the orchestrator pipeline.

**Known Limitations:**
-   Notebook-to-Lakehouse bindings don't auto-update across environments — `parameter.yml` handles this
-   Lakehouse table data, shortcuts, and views are not deployed (metadata only)
-   `fabric-cicd` is pre-1.0 (v0.3.x) but production-used across the community

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

-   [ ] Partitioning strategy implementation

-   [ ] Predicate pushdown in notebooks (some already implemented with filters)

-   [ ] Incremental load activation (parameters exist, logic not implemented)

-   [ ] Caching strategies

-   [ ] Index creation in warehouse

-   [ ] DirectLake optimization (V-Order columnar format)

------------------------------------------------------------------------

## Testing Strategy

### Current Testing Status

**Unit Tests:** 33 tests for transformation logic in `tests/` (task-008). **Integration Tests:** None yet. **Data Validation Tests:** Quality checks in gold layer + observability tables.

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

Governance- and trade-weighted Herfindahl index, computed at the bottleneck stage (E/P):

```
HHI_WGI,t = Σ_c (Sᶜ)² · WGIᶜ · tᶜ
```

Per country `c`:

-   `Sᶜ` — supply share (fraction)

-   `tᶜ` — trade parameter from source data (0.8 EU, 1.0 baseline non-EU, \>1 export-restricted)

-   `WGIᶜ` — governance risk weight in `0..1` where **1 = worst governance**, derived as the rescaled **inverse** of the mean of all six WGI dimensions for the latest year available per country

**The inversion is mandatory.** Raw WGI runs ≈ −2.5..+2.5 with *higher = better* governance. Used unmodified as a multiplier it would *reward* poorly-governed sourcing — the index would still compute and still look plausible, but every risk ranking would be backwards. The spec requires the inverted, rescaled form.

Computed over two supply mixes and exposed in `gold_supply_risk`:

-   `hhi_global` — global production mix

-   `hhi_eu_sourcing` — EU sourcing mix

-   contrast between the two — the EU-specific exposure signal

**Scope boundary (DEC-001):** no import-reliance blend of the two indices into a single SR (Option C); no recycling (`EoL_RIR`) or substitution (`SI_SR`) filters (Option D). These figures are therefore **gross** supply risk and **must be labelled as such in the report** — they are not official EU CRM SR values.

**Supplier Concentration Risk (secondary lens — retained):**

-   Definition: Percentage of global supply from single country

-   Calculation: MAX(share_pct) per material/stage

-   Threshold for "high risk":

    -   Critical: \>50% from single country

    -   High: \>30%

    -   Medium: \>20%

    -   Low: ≤20%

-   Source: Implemented in v_supply_concentration_risk view

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

-   Mapping: Hardcoded in silver-to-gold2.Notebook grp_map dictionary

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

-   Supply Concentration = MAX(fact_supply_share\[share_pct\]) *(secondary lens)*

-   Supply Risk (Global) = governance- & trade-weighted HHI over the global supply mix

-   Supply Risk (EU Sourcing) = the same index over the EU sourcing mix

-   Supply Risk Contrast = EU-sourcing index vs global index (EU-specific exposure)

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

-   Connection string/endpoint: Managed via Fabric dataflow connection

-   Refresh schedule: Manual — pipeline triggered on demand

**EPI Dataset:**

-   Source: Yale EPI (https://epi.yale.edu/), file-based dataflow ingestion

-   Update schedule: Annual (typically Q2-Q3 each year)

-   File location: Manual CSV upload to Fabric Lakehouse Files

-   Ingestion: Automated via dataflow after manual file upload

-   Current year: 2024

**WGI Dataset:**

-   Source: World Bank (WGI = World Governance Indicators)

-   Update schedule: Annual (typically Q3-Q4)

-   File location: Manual CSV upload to Fabric Lakehouse Files

-   Ingestion: Automated via dataflow after manual file upload

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
    -   **Planned (task-029):** the `bronze_load_metadata` high-water-mark table and its parameter flow are documented but **not implemented**. Task-029 will implement or formally descope it.
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
    -   **DECISION:** Activity-level retry with Try-Catch pattern and error logging.
    -   **Pattern:** Each activity gets retry count (3) and interval (30s). Upon Failure paths route to a shared error-logging activity (writes to `pipeline_execution_log` table). Critical failures use the Fail activity with custom error codes. Non-critical failures (e.g., EPI refresh fails) allow the pipeline to continue via Try-Catch, logging the failure for review.
    -   **Why:** Fabric has no pipeline-level retry — only activity-level. The Try-Catch pattern (Upon Failure path only) allows the pipeline to succeed even when non-critical activities fail, which is important for a multi-source pipeline where one external source being unavailable shouldn't block everything.
    -   **Notification:** Pipeline failure alerts via Fabric monitoring (no custom notification system needed for a single-developer project).

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
| Phase 1 | Core Data Model & Reports | Complete (9/9) | Gold tables populated, semantic model connected, Power BI report built |
| Phase 2 | Automation & Quality | Active (10/11) — only task-006_3 (incremental-load testing in Fabric) remains | Incremental load works for fact_procurement, data quality checks run in pipeline, external data ingestion scripted |
| Phase 3 | Operations & Performance | Active (1/7) — task-011 done; task-010 (scheduling) + task-012_1–012_5 (performance) pending | Error handling with Try-Catch in pipeline, pipeline scheduling configured, basic performance review done |
| Phase 4 | CI/CD Deployment | Planned | GitHub Actions workflow deploys Fabric artifacts on merge to main via `fabric-cicd` |

### Phase 4 — CI/CD Deployment

**Goal:** Automated deployment pipeline — the one production-readiness pattern not covered by the companion NordGrid project.

**Deliverables:**

1. **GitHub Actions workflow** using `fabric-cicd` library (owner: both — Claude writes workflow, Erik configures Service Principal + GitHub secrets)
   - `parameter.yml` for environment-specific configuration (lakehouse IDs, connection strings)
   - Service Principal authentication (human task: Azure AD app registration)
   - Deployment triggered on merge to main

2. **SQL Warehouse Analytics Layer** — already implemented (4 views + 2 stored procedures in `oem_wh`). No additional work needed.

### Priority Order

Complete in sequence:
1. Phase 2 remaining: task-006_3 (test incremental load in Fabric) — the last Phase 2 item
2. Phase 3: task-010 (scheduling) + task-012_1–012_5 (performance) — task-011 (error handling) is done
3. Phase 4 — CI/CD builds on the completed pipeline

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

### Sample WGI Record

**From silver_WB:**

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