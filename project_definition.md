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

-   **Semantic Model:** `semantic_model_oeminsightbi` (Power BI data model)

-   **Report:** Power BI report connected to semantic model

**Development Environment:**

-   Python 3.12 (local virtual environment: `.venv`)

-   PySpark (Fabric notebooks)

-   Power Query M (Dataflows)

-   SQL (Azure SQL, Fabric Warehouse)

**Version Control:**

-   Git repository structure exists in `/fabric` folder

-   Each Fabric artifact has `.platform` metadata

-   Git integration with Fabric workspace (status: **NEEDS DOCUMENTATION**)

**Azure Services:**

-   Azure SQL Database (transactional source system)

-   **Server:** procurement-supplier.database.windows.net

-   **Database:** procurement-supplier-db

-   Authentication method: **NEEDS DOCUMENTATION**

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

-   Frequency: **NEEDS DOCUMENTATION**

-   Incremental vs Full Load: **NEEDS DOCUMENTATION** (Pipeline has parameters `p_full_load` and `p_from_date` suggesting incremental capability)

**Setup Scripts:** (in `/azure` folder)

-   `user_creation.sql` - Database user setup

-   `grant_permissions.sql` - Access control

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

**Source:** World Bank WGI dataset (file-based)

**Ingestion Method:** `WGI_file2table.Dataflow`

**Content:** Country-level governance quality metrics across 6 governance dimensions

**Grain:** One row per country per indicator with year columns (wide format)

**Year Covered:** 2020 (filtered in transformation)

**Key Fields:**

-   `Country Name` (STRING) - Full country name

-   `Country Code` (STRING) - ISO country code

-   `Indicator Name` (STRING) - Name of governance indicator

-   `Indicator Code` (STRING) - Coded indicator identifier

-   `Topic` (STRING) - Governance dimension/category (from ESGSeries metadata join)

-   `y_[YEAR]` columns (DOUBLE) - Score values by year

-   `Score` (DOUBLE) - Unpivoted score value (after transformation)

**Transformation Notes:**

-   Year columns unpivoted in bronze-to-silver transformation

-   Filtered for year 2020 only

-   Scores filtered to 0-100 range

-   Joined with `bronze_WB_ESGSeries` for topic/category metadata

-   Bronze tables: `bronze_WB_ESGCSV`, `bronze_WB_ESGSeries`

-   Silver table: `silver_WB`

**Update Frequency:** Annual (World Bank releases Q3-Q4)

**File Location:** **NEEDS DOCUMENTATION**

**File Format:** Manual CSV file upload. (Task created to investigate automating ingestion).

#### 4. Global Supply Shares (EU CRM Data) - External Data

**Source:** EU Critical Raw Materials supply chain data

**Ingestion Method:** Copy activity in pipeline (`bronzecopy_EUSupplyShares`)

**Content:** Material supply concentration by country and production stage

**Grain:** One row per material per stage per country

**Key Fields:**

-   `Material` (STRING) - Material name

-   `Stage` (STRING) - Production stage code ("E" = Extraction, "P" = Processing)

-   `Country` (STRING) - Supplier country name

-   `Share` (STRING) - Supply share percentage (e.g., "45%", "\<1%")

-   `t` (STRING) - Unknown field (dropped in transformation)

**Transformation Notes:**

-   Share values cleaned: percentage signs removed, "\<1%" converted to 0.5%

-   Column headers lowercased and spaces replaced with underscores

-   Bronze table: `bronze_GlobalSupplyShares`

-   Silver table: `silver_globalsupplyshares`

-   Year assigned: 2023 (in gold transformation)

**Update Frequency:** **NEEDS DOCUMENTATION**

**File Location:** GitHub repository CSV file (HTTP source)

**File Format:** CSV with comma delimiter

------------------------------------------------------------------------

## Data Transformations

### Bronze → Silver: Data Cleaning

**Notebook:** `clean_columnsAndHeaders.Notebook`

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

**3. World Bank ESG/WGI Data (`bronze_WB_ESGCSV` + `bronze_WB_ESGSeries` → `silver_WB`):**

-   Unpivot year columns (y_2000, y_2001, etc.) to long format

-   Remove `y_` prefix from year values

-   Filter for year 2020 only

-   Join with ESGSeries table to add Topic metadata

-   Cast score to DOUBLE type

-   Filter scores to 0-100 range

-   Drop year column (year 2020 is implicit)

-   Convert column headers to lowercase with underscores

-   Write to: `silver_WB`

**4. Procurement Data (`bronze_procurement_transactional` + `bronze_supplier_ref` → `silver_procurement`):**

-   Left join procurement_transactional with supplier_ref on SupplierName

-   Convert column headers to lowercase with underscores

-   Drop duplicate columns: region, suppliername (from supplier_ref)

-   Result includes: date, materialname, quantity, unit, unitpriceeur, headquarterscountry, productioncountry

-   Write to: `silver_procurement`

**Input Tables:** (in bronze lakehouse)

-   `bronze_epi2024results`

-   `bronze_GlobalSupplyShares`

-   `bronze_WB_ESGCSV`

-   `bronze_WB_ESGSeries`

-   `bronze_procurement_transactional`

-   `bronze_supplier_ref`

**Output Tables:** (in silver lakehouse)

-   `silver_epi2024results`

-   `silver_globalsupplyshares`

-   `silver_WB`

-   `silver_procurement`

**Data Quality Rules Applied:**

-   Null filtering on key fields (iso3 for countries, scores for metrics)

-   Type casting with validation (integers, doubles)

-   Score range validation (0-100 for WB indicators)

-   Duplicate removal on natural keys

**Known Issues/Technical Debt:**

-   **NEEDS DOCUMENTATION** (requires operational knowledge)

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
        -   Primary: EPI (silver_epi2024results) + World Bank (silver_wb)
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
        -   `source_system` (STRING) - "EPI" or "WB"
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
        -   WB: `silver_wb` table (distinct indicator_code, indicator_name, topic)
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

**Known Issues/Technical Debt:** - **NEEDS DOCUMENTATION** (requires operational feedback)

------------------------------------------------------------------------

## Orchestration

### Pipeline: `orchestrator_pipeline_bronze_to_gold.DataPipeline`

**Purpose:** End-to-end orchestration from ingestion to gold layer

**Pipeline Structure:**

**Stage 1: Bronze Ingestion (Parallel Execution)**

1.  `bronzecopy_EUSupplyShares` (Copy Activity)
    -   Type: Copy from HTTP source to Lakehouse

    -   Source: EU CRM GitHub repository CSV

    -   Sink: `bronze_EUSupplyShares` table in oem_lh

    -   Timeout: 12 hours

    -   Retry: 0 attempts

<!-- -->

2.  `bronze_WGI` (RefreshDataflow Activity)
    -   Type: Dataflow refresh
    -   Dataflow: `WGI_file2table.Dataflow`
    -   Output: WGI bronze tables
    -   Timeout: 12 hours
    -   Retry: 0 attempts
3.  `bronze_procurement` (RefreshDataflow Activity)
    -   Type: Dataflow refresh
    -   Dataflow: `bronze_azureSQLdb2table.Dataflow`
    -   Output: `bronze_procurement_transactional`, `bronze_supplier_ref`
    -   Timeout: 12 hours
    -   Retry: 0 attempts
4.  `bronze_EPI` (RefreshDataflow Activity)
    -   Type: Dataflow refresh
    -   Dataflow: `EPI_file2table.Dataflow`
    -   Output: `bronze_epi2024results` and related tables
    -   Timeout: 12 hours
    -   Retry: 0 attempts

**Stage 2: Silver Transformation (Sequential)**

5.  `bronze-to-silver data cleaning` (Notebook Activity)
    -   Depends on: All 4 bronze activities (Succeeded)

    -   Notebook: `clean_columnsAndHeaders.Notebook`

    -   Output: Silver tables (silver_epi2024results, silver_globalsupplyshares, silver_WB, silver_procurement)

    -   Timeout: 12 hours

    -   Retry: 0 attempts

**Stage 3: Gold Transformation (Sequential)**

6.  `silver-to-gold` (Notebook Activity)
    -   Depends on: bronze-to-silver data cleaning (Succeeded)

    -   Notebook: `silver-to-gold2.Notebook` - Output: Gold fact and dimension tables

    -   Timeout: 12 hours

    -   Retry: 0 attempts

**Stage 4: Warehouse Sync (Sequential)**

7.  `Copy job1` (InvokeCopyJob Activity)
    -   Depends on: silver-to-gold (Succeeded)

    -   Purpose: Sync gold tables to warehouse

    -   Output: Tables in `oem_wh` warehouse

    -   Timeout: 12 hours

    -   Retry: 0 attempts

**Pipeline Parameters:**

-   `procurement_array` (Array)

-   Configuration for procurement source-to-sink mappings

-   `p_full_load` (Boolean)

-   Flag for full vs incremental load (default: false)

-   `p_from_date` (String)

-   Start date for incremental load (default: "1900-01-01")

**Schedule:** Not configured. The pipeline is run manually.

**Error Handling:** Fail-fast approach (0 retries, 30-second intervals)

**Notifications:** NoNotification configured on dataflow refreshes

**Retry Logic:** None (0 retries on all activities)

**Dependencies:**

-   Stage 1 activities run in parallel (no dependencies)

-   Stage 2 waits for all Stage 1 activities to succeed

-   Stage 3 waits for Stage 2 to succeed

-   Stage 4 waits for Stage 3 to succeed

**Known Issues:** - **NEEDS DOCUMENTATION** (requires operational monitoring data)

------------------------------------------------------------------------

## Semantic Model & Reporting

### Semantic Model: `semantic_model_oeminsightbi`

**Model Type:** Star Schema in **DirectLake** mode

-   DirectLake provides direct query to Delta tables in Fabric Lakehouse

-   No data import required - queries run directly on parquet files

-   Automatic refresh when lakehouse tables update

**Fact Tables:**

-   `fact_epi_score` - Environmental performance scores by country/indicator/year

-   `fact_procurement` - Procurement transactions with spend and quantity

-   `fact_supply_share` - Global supply concentration by material/stage/country

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

**Key Measures/Calculations:** (in `expressions.tmdl`)

-   **NOTE:** No custom DAX measures found in current semantic model files

-   Only database connection expression exists

-   Measures likely defined in Power BI Desktop file (.pbix) not synced to git

-   **Expected measures based on business requirements:**

    -   Total Spend = SUM(fact_procurement\[spend_eur\])

    -   Total Quantity = SUM(fact_procurement\[quantity_base\])

    -   Supplier Count = DISTINCTCOUNT(fact_procurement\[supplier_hq_country_key\])

    -   Avg EPI Score = AVERAGE(fact_epi_score\[score\])

    -   Supply Concentration Index = MAX(fact_supply_share\[share_pct\])

    -   YoY Growth = \[Calculate current vs previous year\]

    -   **NOTE:** The current semantic model and DAX measures are slated for a complete redesign. The primary goal is to explore effective data presentation and then implement robust DAX measures to support it. A task has been created for this exploration and implementation.

**Date Table Configuration:**

-   Date dimension connected to: fact_procurement\[date_key\] only

-   fact_epi_score uses year = 2024 (no date relationship)

-   fact_supply_share uses year = 2023 (no date relationship)

-   Time intelligence requires relationship to fact_procurement

### Power BI Report: `report.Report`

**Report Pages:** **NEEDS REDESIGN**

**Key Visuals:** **NEEDS REDESIGN**

**Filters/Slicers:** **NEEDS REDESIGN**

**Drill-through Pages:** **NEEDS DOCUMENTATION**

**RLS (Row-Level Security):** **NEEDS DOCUMENTATION**

**Theme:** CY24SU10.json (Fabric default theme)

**NOTE:** The existing report will be discarded. A new set of visualizations and pages will be designed from scratch after the semantic model is finalized.

------------------------------------------------------------------------

## Current State Assessment

### What's Implemented ✅

**Bronze Layer:**

-   [x] Azure SQL dataflow (`bronze_azureSQLdb2table.Dataflow`)

-   [x] EPI file ingestion (`EPI_file2table.Dataflow`)

-   [x] WGI file ingestion (`WGI_file2table.Dataflow`)

-   [x] HTTP copy job for EU supply shares (`bronzecopy_EUSupplyShares`)

**Silver Layer:**

-   [x] Cleaning notebook (`clean_columnsAndHeaders.Notebook`)

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

**Semantic Model:**

-   [x] Star schema defined

-   [x] DirectLake mode configured

-   [x] 8 relationships configured (all active, single-direction)

-   [x] Connection to Fabric warehouse established

**Orchestration:**

-   [x] Pipeline created (`orchestrator_pipeline_bronze_to_gold.DataPipeline`)

-   [x] 4-stage sequential execution (bronze → silver → gold → warehouse)

-   [x] Parallel bronze ingestion

-   [x] Dependency management configured

**Reporting:**

-   [x] Power BI report created

-   [x] Theme applied (CY24SU10)

### What's Incomplete/Needs Work ⚠️

**Documentation Gaps:**

-   [ ] DAX measure formulas (not in git-synced files)
-   [ ] Report page descriptions and visual inventory
-   [ ] Business logic documentation (business rules, thresholds)
-   [ ] Data lineage diagrams
-   [ ] Error handling procedures
-   [ ] Git workflow documentation

**Technical Gaps:**

-   [ ] Incremental load implementation (parameters exist but logic not used)

-   [ ] Schema validation in notebooks

-   [ ] Performance optimization (partitioning, indexing)

-   [ ] Unit tests for transformation logic

-   [ ] Integration tests for pipeline

-   [ ] Automated data quality monitoring

-   [ ] Alerting/notification configuration

-   [ ] **Semantic Model & DAX Logic:** The current model needs to be redesigned to better answer business questions. New DAX measures need to be created from scratch.

-   [ ] **Reporting & Visualization:** The Power BI report needs to be completely redesigned with a focus on clear, insightful visuals.

-   [ ] **Automated Ingestion:** The ingestion of external data (EPI, WGI, EU Supply Shares) is currently a manual CSV upload process. This needs investigation to automate or connect directly to sources.

-   [ ] **Security Implementation:** Row-Level Security (RLS) needs to be designed conceptually and then implemented technically to showcase security best practices.

**Process Gaps:**

-   [ ] Pipeline scheduling configuration

-   [ ] Change management process

-   [ ] Deployment procedure (dev → prod)

-   [ ] Monitoring/alerting setup

-   [ ] Backup/recovery procedures

-   [ ] Access control documentation

### Known Issues/Technical Debt 🔴

**NEEDS DOCUMENTATION:**

-   Any data quality issues in sources?

-   Performance bottlenecks?

-   Incomplete transformations?

-   Workarounds or hacks in code?

-   Deprecated approaches that need refactoring?

-   **Data Quality Visibility:** There is no centralized way to view the quality of the data, specifically the match rates and assumptions made during alias resolution (e.g., country and material name mapping). This makes it difficult to assess confidence in the final dataset and needs to be addressed for the project portfolio.

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

**Git Status:** **NEEDS DOCUMENTATION**

**Git Status:** The project is managed by a single developer. A formal branching strategy (e.g., GitFlow) is not currently implemented. Work is typically committed directly to the main branch synced with the Fabric workspace.

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
    -   Export schemas/DQ reports
    -   Commit results back to Git
3.  **Evening (Claude Code):**
    -   Pull latest (includes DQ reports)
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

    -   Examples: `clean_columnsAndHeaders.Notebook`, `silver-to-gold2.Notebook`

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

**Bronze Layer Checks:**

-   [ ] Row count validation (expected vs actual)

-   [ ] Schema drift detection

-   [ ] Null checks on required fields

-   [ ] Duplicate detection (primary keys)

-   [ ] Date range validation (no future dates, etc.)

**Silver Layer Checks:**

-   [ ] Referential integrity (orphaned records)

-   [ ] Business rule validation

-   [ ] Data type consistency

-   [ ] Outlier detection (amounts, quantities)

-   [ ] Completeness checks

**Gold Layer Checks:**

-   [ ] Aggregate totals reconciliation

-   [ ] Historical trend validation (no sudden spikes/drops without explanation)

**Current DQ Implementation:**

-   Unmapped values: Logged to audit tables, assigned to placeholder dimensions

-   Failures: Logged with check_unmapped() function

-   Results: Stored in gold_data_quality_metrics table

-   Visualization: quality_category field available in facts for filtering

### Expected Data Profiles

**Procurement Transactions:**

-   Row count range: **NEEDS DOCUMENTATION**

-   Date range: **NEEDS DOCUMENTATION** (dynamically determined from data)

-   Amount range: Min/Max/Avg **NEEDS DOCUMENTATION**

-   Null rate acceptance: **NEEDS DOCUMENTATION**

-   Key fields: date, materialname, suppliername, quantity, unitpriceeur

**EPI Scores:**

-   Countries covered: \~180-200 (from EPI dataset)

-   Indicators: \~30-40 (wide format in bronze)

-   Years: 2024 (current implementation)

-   Score range: Varies by indicator (EPI overall: 0-100)

-   Null rate: **NEEDS DOCUMENTATION**

**WGI Indicators:**

-   Countries covered: \~200+ (from World Bank)

-   Indicators: 6 governance dimensions

-   Years: 2020 (filtered in transformation)

-   Score range: 0-100 (filtered in transformation)

-   Null rate: **NEEDS DOCUMENTATION**

**Supply Shares:**

-   Materials covered: 80+ critical raw materials

-   Countries covered: Global (major producers)

-   Stages: 2 (Extraction, Processing)

-   Share range: 0-100% (with "\<1%" special handling)

-   Year: 2023 (assigned in gold layer)

------------------------------------------------------------------------

## Infrastructure & Deployment

### Fabric Workspace Configuration

**Workspace Name:** **NEEDS DOCUMENTATION**

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

**Partitioning Strategy:** **NEEDS DOCUMENTATION** **Optimization Settings:** **NEEDS DOCUMENTATION** (V-Order, etc.) **Format:** Delta Lake (confirmed from write operations)

### Warehouse Configuration

**Warehouse Name:** `oem_wh`

**Warehouse ID:** b1cb7506-8d2d-4e4a-97cc-2b580da8eda0 (from expressions.tmdl)

**Purpose:** SQL-queryable layer for Power BI DirectLake semantic model

**Tables/Views:**

-   Mirrors gold layer tables (based on semantic model source)

-   Schema: dbo (default schema)

-   DirectLake queries these tables directly from parquet files

**Connection:**

-   Endpoint: 2BINPJYTVAEEVEF26XKMILPX4E-NXGOJGODN2TUTLWZW2NQJKL2VE.datawarehouse.fabric.microsoft.com

-   Database ID: b1cb7506-8d2d-4e4a-97cc-2b580da8eda0

### Security & Access

**Authentication:**

-   Azure SQL: **NEEDS DOCUMENTATION** (setup scripts exist: user_creation.sql, grant_permissions.sql)

-   Lakehouse: Workspace identity (inferred from artifact connections)

-   Semantic Model: Workspace connection (from expressions.tmdl)

**Row-Level Security (RLS):**

-   Implemented?No. Not implemented.

-   Roles defined? None. A task has been created to design and implement RLS.

**Column-Level Security:**

-   Any sensitive fields masked? **NEEDS DOCUMENTATION**

**Access Control:**

-   Who can read/write lakehouse? **NEEDS DOCUMENTATION**

-   Who can edit notebooks/pipelines? **NEEDS DOCUMENTATION**

-   Who can refresh semantic model? **NEEDS DOCUMENTATION**

------------------------------------------------------------------------

## Performance Optimization

### Current Performance Status

**Pipeline Runtime:** **NEEDS DOCUMENTATION**

-   Bronze ingestion: X minutes

-   Silver transformation: X minutes - Gold transformation: X minutes

-   Total end-to-end: X minutes

**Known Bottlenecks:** **NEEDS DOCUMENTATION**

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

**Unit Tests:** None exist **Integration Tests:** None exist **Data Validation Tests:** Partial (quality checks in gold layer)

**Desired Testing Approach:**

-   [ ] Unit tests for transformation functions (stable_key, clean_and_rename, etc.)

-   [ ] Schema validation tests

-   [ ] Data quality tests (expand current checks)

-   [ ] Pipeline integration tests

-   [ ] Semantic model validation (relationship integrity)

-   [ ] Regression tests for alias mappings

**Test Data:** **NEEDS DOCUMENTATION**

-   Test environment with sample data?

-   Synthetic data generation?

------------------------------------------------------------------------

## Business Logic & Calculations

### Key Business Rules

**Supplier Concentration Risk:**

-   Definition: Percentage of global supply from single country

-   Calculation: MAX(share_pct) per material/stage

-   Threshold for "high risk":

    -   Critical: \>50% from single country

    -   High: \>30%

    -   Medium: \>20%

    -   Low: ≤20%

-   Source: Implemented in v_supply_concentration_risk view

**Environmental Score Aggregation:**

-   How are multiple EPI indicators combined? **NEEDS DOCUMENTATION**

-   Current implementation: Individual indicators stored separately in fact_epi_score

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

-   Fiscal year start: **NEEDS DOCUMENTATION** (currently uses calendar year) - Reporting periods: Daily grain available in gold_dim_date with quarter/month aggregations

### DAX Measures (High-Level)

**NEEDS DOCUMENTATION** - Actual DAX formulas not found in synced files

**Expected measures based on business requirements:**

-   Total Spend = SUM(fact_procurement\[spend_eur\])

-   Total Quantity = SUM(fact_procurement\[quantity_base\])

-   Avg Unit Price = DIVIDE(\[Total Spend\], \[Total Quantity\])

-   Supplier Count = DISTINCTCOUNT(fact_procurement\[supplier_hq_country_key\])

-   Material Count = DISTINCTCOUNT(fact_procurement\[material_key\])

-   Avg EPI Score = AVERAGE(fact_epi_score\[score\])

-   Supply Concentration = MAX(fact_supply_share\[share_pct\])

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

-   Refresh schedule: **NEEDS DOCUMENTATION**

-   Data owner: **NEEDS DOCUMENTATION**

-   SLA: **NEEDS DOCUMENTATION**

**EPI Dataset:**

-   Source URL/provider: **NEEDS DOCUMENTATION** (file-based dataflow ingestion)

-   Update schedule: Annual (typically Q2-Q3 each year)

-   File location: **NEEDS DOCUMENTATION**

-   Manual vs automated ingestion: Automated via dataflow (manual file upload?)

-   Current year: 2024

**WGI Dataset:**

-   Source: World Bank (WGI = World Governance Indicators)

-   Update schedule: Annual (typically Q3-Q4)

-   File location: **NEEDS DOCUMENTATION**

-   Manual vs automated ingestion: Automated via dataflow

-   Current year: 2020 (filtered in transformation)

**EU CRM Supply Shares:**

-   Source: GitHub repository CSV file (HTTP endpoint)

-   Update schedule: **NEEDS DOCUMENTATION**

-   Connection type: HTTP REST endpoint

-   Current year: 2023 (assigned in gold layer)

### Downstream Consumers

**Power BI Report:**

-   Report ID: report.Report (in /fabric folder)

-   Who uses it? **NEEDS DOCUMENTATION**

-   Refresh schedule: Automatic with DirectLake (on lakehouse update)

-   Published to Power BI Service? **NEEDS DOCUMENTATION**

**Semantic Model**

-   Connected applications: Power BI reports via DirectLake

-   Query mode: DirectLake (direct parquet file access)

-   Refresh: Automatic (no explicit refresh needed with DirectLake)

**Other Systems:**

-   Any external systems consuming gold tables? **NEEDS DOCUMENTATION**

-   APIs or data exports? **NEEDS DOCUMENTATION**

------------------------------------------------------------------------

## Open Questions & Decisions Needed

### Technical Decisions

1.  **Incremental vs Full Load:**
    -   Which tables need incremental load?
    -   What's the incremental key? (Date field, timestamp?)
    -   **DECISION:** **NEEDS DOCUMENTATION**
    -   **Note:** Pipeline has parameters (`p_full_load`, `p_from_date`) but logic not implemented
2.  **Partitioning Strategy:**
    -   Partition by date? Country? Material? Both?
    -   **DECISION:** **NEEDS DOCUMENTATION**
3.  **SCD Implementation:**
    -   Which dimensions need history tracking?
    -   Type 1 vs Type 2?
    -   **DECISION:** Currently all Type 1 (overwrite)
    -   **Recommendation:** Consider Type 2 for gold_dim_country, gold_dim_material if names/attributes change
4.  **Data Retention:**
    -   How long to keep bronze data?
    -   Archive strategy?
    -   **DECISION:** **NEEDS DOCUMENTATION**
5.  **Error Handling:**
    -   Fail fast or continue on error?
    -   Quarantine bad records?
    -   **DECISION:** Currently fail-fast (0 retries in pipeline)
    -   **Recommendation:** Add retry logic for transient failures

### Business Decisions

1.  **EPI Indicator Selection:**
    -   Which of \~30 indicators to include in reports?
    -   Any custom weighting for composite scores?
    -   **DECISION:** **NEEDS DOCUMENTATION**
    -   **Current:** All indicators included in fact_epi_score
2.  **Supplier Risk Thresholds:**
    -   What defines "high risk"? (Current: \>50% concentration = Critical)
    -   Multiple dimensions (env + governance)?
    -   **DECISION:** Concentration risk thresholds implemented, but ESG risk thresholds **NEEDS DOCUMENTATION**
3.  **Reporting Granularity:**
    -   Daily, weekly, monthly aggregates?
    -   **DECISION:** Daily grain in fact_procurement, yearly grain in fact_epi_score and fact_supply_share
    -   **Current:** gold_dim_date provides daily grain with month/quarter/week attributes
4.  **Material Hierarchy:**
    -   How many levels? (Current: 1 level - commodity_group)
    -   Categories defined? (Current: 13 commodity groups)
    -   Need sub-categories? (e.g., Battery metals → Lithium compounds)
    -   **DECISION:** **NEEDS DOCUMENTATION**
5.  **Fiscal Calendar:**
    -   Fiscal year different from calendar year?
    -   **DECISION:** **NEEDS DOCUMENTATION** (currently calendar year only)

------------------------------------------------------------------------

## Next Steps & Priorities

### Immediate Priorities (Next 2 Weeks)

**NEEDS DOCUMENTATION:**

1.  [ ] **Priority 1:** \[What needs to be done first?\]
2.  [ ] **Priority 2:** \[Second most important?\]
3.  [ ] **Priority 3:** \[Third?\]

**Suggested priorities based on gaps identified:**

-   **Priority 1: Enhance Data Quality & Matching Visibility:** Create a new notebook or Power BI report page dedicated to surfacing the results of the alias resolution process. This should clearly show unmapped values, match confidence scores, and the impact of assumptions for countries and materials. This directly addresses the main technical debt.

-   **Priority 2: Redesign Semantic Model & DAX Measures:** Brainstorm and document the key business questions the report should answer. Based on that, redesign the semantic model and implement a core set of DAX measures for key metrics (e.g., Total Spend, Supplier Concentration, Weighted EPI Score).

-   **Priority 3: Redesign Power BI Report:** Build a new Power BI report on top of the redesigned semantic model. Start with an overview page and a deep-dive page for supplier risk.

-   **Priority 4: Design Row-Level Security (RLS):** Research and document a conceptual RLS model. For example, create roles like "Procurement Manager - Americas" who can only see data for their region.

### Short-Term Goals (Next Month)

**NEEDS DOCUMENTATION:**

-   [ ] **Goal 1:** Implement the designed Row-Level Security (RLS) in the semantic model and test it.

-   [ ] **Goal 2:** Investigate automating the ingestion of at least one external data source (e.g., the EU Supply Shares from its source GitHub URL) to replace the manual CSV upload.

-   [ ] **Goal 3:** Complete documentation for all remaining NEEDS DOCUMENTATION sections.

### Long-Term Vision (Next Quarter)

**NEEDS DOCUMENTATION:**

-   [ ] Vision item 1: Expand to additional data sources

-   [ ] Vision item 2: Implement predictive analytics

-   [ ] Vision item 3: Real-time data integration

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