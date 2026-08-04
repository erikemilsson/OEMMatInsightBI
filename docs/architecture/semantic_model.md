# Semantic Model - OEMMatInsightBI

## Overview

**Model Name:** `OEMInsightBI_v2`
**Mode:** DirectLake (direct query to Delta tables in Fabric Lakehouse)
**Schema:** Star Schema (3 fact tables + 5 dimension tables)
**Refresh:** Automatic (no manual refresh needed with DirectLake)

## Star Schema Design

```
                    gold_dim_date
                         |
                         | date_key
                         |
    gold_dim_material ───┼─── fact_procurement ─── gold_dim_country
                         |         |                      |
                         |         |                      | (role: supplier_hq)
                  material_key  date_key            country_key
                                                           |
                                                           | (role: production)
                                                      country_key


    gold_dim_indicator ───── fact_epi_score ───── gold_dim_country
          |                       |                     |
    indicator_key            country_key          country_key


    gold_dim_material ───┐
                          ├─ fact_supply_share ─── gold_dim_country
    gold_dim_stage ──────┘           |                  |
                                  year              country_key
```

## Tables

### Fact Tables

**1. fact_procurement**
- **Grain:** One row per procurement transaction
- **Measures:** quantity_base (kg), unitprice_eur, spend_eur, data_quality_score
- **Foreign Keys:** date_key, material_key, supplier_hq_country_key, production_country_key
- **Source:** silver_procurement (via silver-to-gold2 notebook)
- **Row Count:** ~100,000-200,000 (dynamic)

**2. fact_supply_share**
- **Grain:** One row per material × stage × country × year
- **Measures:** share_pct (0-100), data_quality_score
- **Foreign Keys:** material_key, stage_key, country_key, year
- **Source:** silver_globalsupplyshares
- **Row Count:** ~5,000-15,000

**3. fact_epi_score**
- **Grain:** One row per country × indicator × year
- **Measures:** score (indicator value)
- **Foreign Keys:** country_key, indicator_key, year
- **Source:** silver_epi2024results (pivoted from wide format)
- **Row Count:** ~3,000-10,000

### Dimension Tables

**1. gold_dim_country**
- **Grain:** One row per country
- **Attributes:** iso3, iso_numeric, wb_code, country_name_std, region, is_placeholder
- **Key:** country_key (BIGINT - xxhash64)
- **Row Count:** ~186 real + 6 placeholders = ~192

**2. gold_dim_date**
- **Grain:** One row per day
- **Attributes:** date, year, month, day, month_name, quarter, day_of_week, week_of_year
- **Key:** date_key (INTEGER - yyyyMMdd format)
- **Row Count:** Dynamic (min to max procurement date, ~365-3650 rows)

**3. gold_dim_material**
- **Grain:** One row per unique material
- **Attributes:** material_name_std, commodity_group (13 categories), unit_base, is_placeholder
- **Key:** material_key (BIGINT - xxhash64)
- **Row Count:** ~50-200 materials

**4. gold_dim_indicator**
- **Grain:** One row per EPI/WGI indicator
- **Attributes:** source_system, abbrev, variable_name, indicator_code, weight, description
- **Key:** indicator_key (BIGINT - xxhash64)
- **Row Count:** ~30-50 indicators

**5. gold_dim_stage**
- **Grain:** One row per production stage
- **Attributes:** stage_code ("E" or "P"), stage_name ("Extraction" or "Processing")
- **Key:** stage_key (BIGINT - xxhash64)
- **Row Count:** 2 (fixed)

## Relationships

All relationships are **many-to-one** with **single direction** filtering (dimension → fact).

### Date Relationships
- `gold_dim_date[date_key]` (1) → `fact_procurement[date_key]` (*)
- **Note:** fact_epi_score and fact_supply_share use year column, not date_key

### Country Relationships
- `gold_dim_country[country_key]` (1) → `fact_procurement[supplier_hq_country_key]` (*)
- `gold_dim_country[country_key]` (1) → `fact_procurement[production_country_key]` (*)
- `gold_dim_country[country_key]` (1) → `fact_epi_score[country_key]` (*)
- `gold_dim_country[country_key]` (1) → `fact_supply_share[country_key]` (*)

**Role-Playing Dimension:** gold_dim_country plays two roles in fact_procurement (HQ and production)

### Material Relationships
- `gold_dim_material[material_key]` (1) → `fact_procurement[material_key]` (*)
- `gold_dim_material[material_key]` (1) → `fact_supply_share[material_key]` (*)

### Indicator Relationship
- `gold_dim_indicator[indicator_key]` (1) → `fact_epi_score[indicator_key]` (*)

### Stage Relationship
- `gold_dim_stage[stage_key]` (1) → `fact_supply_share[stage_key]` (*)

## DAX Measures (Planned - Task 02)

### Core Measures
```dax
Total Spend = SUM(fact_procurement[spend_eur])
Total Quantity = SUM(fact_procurement[quantity_base])
Avg Unit Price = DIVIDE([Total Spend], [Total Quantity], 0)
Supplier Count = DISTINCTCOUNT(fact_procurement[supplier_hq_country_key])
Material Count = DISTINCTCOUNT(fact_procurement[material_key])
```

### Time Intelligence
```dax
Total Spend LY = CALCULATE([Total Spend], SAMEPERIODLASTYEAR(gold_dim_date[date]))
YoY Spend Growth = DIVIDE([Total Spend] - [Total Spend LY], [Total Spend LY], 0)
```

### Sustainability Metrics
```dax
Avg EPI Score = AVERAGE(fact_epi_score[score])
Weighted EPI Score = SUMX(fact_epi_score, fact_epi_score[score] * RELATED(gold_dim_indicator[weight]))
```

### Risk Metrics
```dax
Max Supply Concentration = MAX(fact_supply_share[share_pct])
High Risk Material Count = CALCULATE(DISTINCTCOUNT(fact_supply_share[material_key]), fact_supply_share[share_pct] > 50)
```

**Current Status:** No custom DAX measures in git-synced files (Task 09: Document existing measures)

## DirectLake Configuration

**Connection:**
- **Source:** oem_wh warehouse
- **Endpoint:** `2BINPJYTVAEEVEF26XKMILPX4E-NXGOJGODN2TUTLWZW2NQJKL2VE.datawarehouse.fabric.microsoft.com`
- **Database ID:** `b1cb7506-8d2d-4e4a-97cc-2b580da8eda0`

**Benefits:**
- Real-time data (no import/refresh delay)
- Queries run directly on parquet files
- Automatic refresh when lakehouse tables update
- Lower memory footprint vs Import mode

**Limitations:**
- Must use Fabric warehouse (not external SQL)
- Some DAX features not supported (e.g., calculated tables)
- Performance depends on underlying data format (V-Order recommended)

## Model Optimization

### Current State
- ✅ Star schema implemented
- ✅ DirectLake mode configured
- ✅ Relationships defined correctly
- ❌ No custom DAX measures (Task 02)
- ❌ No V-Order optimization (Task 12)
- ❌ No Row-Level Security (Task 04)

### Planned Optimizations (Task 12)
- Enable V-Order on warehouse tables
- Add partitioning to large fact tables
- Optimize relationship cardinality
- Review relationship bi-directionality (currently all single-direction)

## Row-Level Security (Planned - Task 04)

**Roles to Implement:**
- Global Executive (all data)
- Regional Manager - Americas (filter: gold_dim_country[region] = "Americas")
- Regional Manager - Europe (filter: gold_dim_country[region] = "Europe")
- Material Category Manager - Battery (filter: gold_dim_material[commodity_group] = "Battery metals")

**Implementation:** Apply DAX filters to dimensions that cascade to facts via relationships

## Model Files

**Location:** `/fabric/OEMInsightBI_v2.SemanticModel/definition/`

**Files:**
- `database.tmdl` - Model metadata
- `expressions.tmdl` - Connection expressions (currently only DB connection)
- `model.tmdl` - Model-level settings
- `relationships.tmdl` - Relationship definitions
- `tables/*.tmdl` - Individual table definitions (8 files)

**Sync:** Git-tracked, can be edited via Tabular Editor or Power BI Desktop

## Troubleshooting

**Model Not Refreshing:**
- Check lakehouse tables are updated (run pipeline)
- Verify warehouse sync completed (copyjob1)
- DirectLake should auto-refresh, but can manually trigger if needed

**Relationships Not Working:**
- Verify surrogate keys match (country_key, material_key, etc.)
- Check for NULL foreign keys (should be assigned to placeholders)
- Validate cardinality is correct (1:many, not many:many)

**Performance Issues:**
- Check underlying table size (>1GB may be slow)
- Enable V-Order optimization (Task 12)
- Review DAX measure complexity
- Consider aggregations for large facts

## Related Files

- `/fabric/OEMInsightBI_v2.SemanticModel/` - Model definition
- `/.claude/tasks/02_redesign_semantic_model.md` - DAX measures implementation
- `/.claude/tasks/04_design_rls_security.md` - RLS implementation
- `/.claude/tasks/09_document_dax_measures.md` - Measure documentation
- `/project_definition.md` - Lines 719-836 (Semantic Model & Reporting)
