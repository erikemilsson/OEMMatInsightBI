# Glossary - OEMMatInsightBI

## Business Terms

**CRM (Critical Raw Materials):** Materials essential for economic and technological activities, classified by EU Commission based on economic importance and supply risk.

**EPI (Environmental Performance Index):** Yale University's country-level index measuring environmental health and ecosystem vitality across 30+ indicators.

**ESG (Environmental, Social, Governance):** Framework for evaluating organizational sustainability and ethical impact.

**OEM (Original Equipment Manufacturer):** Company that manufactures products or components used by another company in its end products.

**Procurement:** Process of acquiring goods/services, including sourcing, purchasing, and supply chain management.

**Supply Concentration Risk:** Dependency on limited sources for critical materials, measured by percentage of global supply from single country.

**Sustainability:** Meeting current needs without compromising future generations' ability to meet theirs.

**WGI (World Governance Indicators):** World Bank's country-level governance quality metrics across 6 dimensions.

## Technical Terms

**Bronze Layer:** Raw data ingestion layer in medallion architecture, exact copy of source systems.

**Delta Lake:** Open-source storage layer providing ACID transactions, time travel, and schema evolution for data lakes.

**DirectLake:** Fabric query mode allowing Power BI to query Delta tables directly without data import.

**Gold Layer:** Business-ready layer with dimensional modeling, surrogate keys, and business logic applied.

**Medallion Architecture:** Data lakehouse pattern with bronze (raw), silver (cleaned), gold (business-ready) layers.

**Silver Layer:** Cleaned and validated data layer with standardized schema but no business logic.

**Star Schema:** Dimensional modeling with central fact tables connected to surrounding dimension tables.

**Surrogate Key:** Artificial key (not from source) used to uniquely identify dimension records, generated via hashing.

## Data Model Terms

**Confidence Score:** Numeric value (0-1) indicating quality of alias match, with 1.0 being exact match.

**Dimension Table:** Reference data table (countries, dates, materials) joined to facts via foreign keys.

**Fact Table:** Transaction or event data table containing measures and foreign keys to dimensions.

**Foreign Key:** Column referencing primary key in another table, used to join facts to dimensions.

**Grain:** Level of detail in a table (e.g., one row per transaction, one row per country per day).

**Placeholder Dimension:** Default dimension record for unmapped values (e.g., "Unknown Material").

**Role-Playing Dimension:** Dimension used multiple times in same fact with different meanings (e.g., HQ country vs production country).

**Surrogate Key:** Artificial identifier generated via xxhash64 of natural key columns.

## Transformation Terms

**Alias:** Alternative name for same entity (e.g., "USA" is alias for "United States of America").

**Commodity Group:** Category of materials (13 groups: battery metals, base metals, rare earths, etc.).

**Unit Normalization:** Converting all quantities to common unit (kg) for consistent analysis.

**Unmapped Value:** Source value that couldn't be matched to standard dimension via alias resolution.

**Unpivoting:** Converting wide-format data (columns) to long format (rows), e.g., year columns to year rows.

## Project-Specific Abbreviations

**HQ:** Headquarters (supplier HQ country)
**LH:** Lakehouse (oem_lh)
**WH:** Warehouse (oem_wh)
**YoY:** Year-over-Year (comparing to same period last year)
**MoM:** Month-over-Month (comparing to previous month)
**DQ:** Data Quality
**RLS:** Row-Level Security
**SCD:** Slowly Changing Dimension
**TMDL:** Tabular Model Definition Language (semantic model format)

## Country Codes

**ISO3:** Three-letter country code (e.g., USA, CHN, SWE) per ISO 3166-1 alpha-3 standard
**ISO Numeric:** Numeric country code per ISO 3166-1 numeric standard
**WB Code:** World Bank country code (may differ from ISO3)

## Material Stages

**E (Extraction):** Mining/harvesting raw materials from earth
**P (Processing):** Refining/manufacturing materials into usable forms

## Quality Categories

**High (0.90-1.00):** Excellent data quality, exact or standard alias matches
**Medium (0.70-0.89):** Good quality, common variants or territory mappings
**Low (0.50-0.69):** Uncertain quality, needs review
**Unmapped (0.00):** No match found, assigned to placeholder
