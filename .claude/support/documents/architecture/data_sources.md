# Data Sources - OEMMatInsightBI

## Overview

This project integrates data from 4 primary sources: 1 transactional database + 3 external datasets.

## 1. Azure SQL Database (Transactional System)

**Server:** `procurement-supplier.database.windows.net`
**Database:** `procurement-supplier-db`
**Authentication:** (TBD - verify in dataflow connection)

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

**Ingestion:** Dataflow `bronze_azureSQLdb2table.Dataflow`
**Frequency:** (TBD - currently manual/on-demand)
**Load Type:** Full refresh (incremental planned in Task 06)

**Setup Scripts:** (in `/azure` folder)
- `user_creation.sql` - Database user setup
- `grant_permissions.sql` - Access control
- `procurement.sql` - Procurement table schema/data
- `supplier_info.sql` - Supplier reference schema/data

## 2. Environmental Performance Index (EPI)

**Source:** Yale Center for Environmental Law & Policy
**Format:** CSV file
**Year:** 2024
**URL:** (TBD - currently manual file upload)

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

**Ingestion:** Dataflow `EPI_file2table.Dataflow`
**Frequency:** Annual (typically Q2-Q3 each year)
**Load Type:** Full replacement (annual snapshot)
**Current Table:** `bronze_epi2024results`

**Transformation:**
- Bronze: Wide format (one row per country, 30+ columns)
- Silver: Cleaned (drop .old columns, cast types)
- Gold: Pivoted to long format (one row per country × indicator)

**Update Schedule:** Manually update when new EPI release published
**Automation:** Task 05 - Investigate automated ingestion

## 3. World Governance Indicators (WGI)

**Source:** World Bank
**Format:** CSV files (2 files: data + metadata)
**Year:** 2020 (filtered during transformation)
**URL:** (TBD - currently manual file upload)

### Content

**Purpose:** Country-level governance quality metrics
**Grain:** One row per country × indicator × year
**Countries:** ~200+ countries
**Indicators:** 6 governance dimensions

**Key Fields:**
- `Country Name` (STRING) - Full country name
- `Country Code` (STRING) - ISO country code
- `Indicator Name` (STRING) - Name of governance indicator
- `Indicator Code` (STRING) - Coded identifier
- `Topic` (STRING) - Governance dimension (from ESGSeries metadata)
- `y_[YEAR]` columns (DOUBLE) - Score values by year
- `Score` (DOUBLE) - Unpivoted score (after transformation)

**Ingestion:** Dataflow `WGI_file2table.Dataflow`
**Frequency:** Annual (typically Q3-Q4)
**Load Type:** Full replacement
**Current Tables:** `bronze_WB_ESGCSV`, `bronze_WB_ESGSeries`

**Transformation:**
- Bronze: Wide format (year columns y_2000, y_2001, ...)
- Silver: Unpivoted to long format, filtered to year 2020
- Gold: Joined with EPI data via country_key

**Automation:** Task 05 - Investigate World Bank API integration

## 4. EU Critical Raw Materials - Global Supply Shares

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

**Ingestion:** Copy activity `bronzecopy_EUSupplyShares` (in pipeline)
**Frequency:** (TBD - currently on-demand)
**Load Type:** Full replacement
**Current Table:** `bronze_GlobalSupplyShares`

**Transformation:**
- Bronze: String share values with % symbols
- Silver: Clean headers, drop unused column
- Gold: Convert "<1%" to 0.5%, cast to numeric, assign year=2023

**Automation:** ✅ Already automated (HTTP source in pipeline)

## Data Integration Architecture

### Source → Bronze
```
Azure SQL ──────────────> bronze_procurement_transactional
                         bronze_supplier_ref

EPI CSV ───────────────> bronze_epi2024results

WGI CSV ───────────────> bronze_WB_ESGCSV
                         bronze_WB_ESGSeries

EU CRM HTTP ───────────> bronze_GlobalSupplyShares
```

### Update Frequencies

| Source | Frequency | Last Update | Next Update |
|--------|-----------|-------------|-------------|
| Azure SQL | Daily (planned) | Manual | Implement scheduling |
| EPI | Annual | 2024 | Q2-Q3 2025 |
| WGI | Annual | 2020 | Q3-Q4 2024 |
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
- **Issues:** Requires unpivoting, year filtering

### EU CRM
- **Reliability:** High (EU Commission official data)
- **Completeness:** Medium (focused on critical materials only)
- **Consistency:** Medium (country name variations)
- **Issues:** Special value handling ("<1%")

## Troubleshooting Data Sources

### Azure SQL Connection Failed
- Check firewall rules (allow Fabric IP addresses)
- Verify authentication credentials in dataflow
- Test connection in dataflow editor

### EPI/WGI File Not Found
- Verify CSV files uploaded to workspace Files section
- Check dataflow source configuration
- Ensure file paths and names match exactly

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
- `/fabric/bronze_azureSQLdb2table.Dataflow/` - SQL ingestion
- `/fabric/EPI_file2table.Dataflow/` - EPI ingestion
- `/fabric/WGI_file2table.Dataflow/` - WGI ingestion
- `/.claude/tasks/05_automate_external_data_ingestion.md` - Automation task
- `/project_definition.md` - Lines 126-319 (Data Sources section)
