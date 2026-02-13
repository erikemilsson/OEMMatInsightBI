# Gold Layer Table Schemas

## Fact Tables

### fact_procurement
Grain: One row per procurement transaction
```
date_key                    INTEGER (yyyyMMdd format)
material_key                BIGINT (xxhash64)
supplier_hq_country_key     BIGINT (xxhash64)
production_country_key      BIGINT (xxhash64)
quantity_base               DOUBLE (normalized to kg)
unitprice_eur              DOUBLE
spend_eur                   DOUBLE (quantity_base × unitprice_eur)
data_quality_score          DOUBLE (0-1 scale)
quality_category            STRING (High/Medium/Low/Unmapped)
```

### fact_supply_share
Grain: One row per material × stage × country × year
```
material_key                BIGINT
stage_key                   BIGINT
country_key                 BIGINT
year                        INTEGER (2023)
share_pct                   DOUBLE (0-100)
data_quality_score          DOUBLE
quality_category            STRING
has_unmapped_material       BOOLEAN
has_unmapped_country        BOOLEAN
unmapped_impact_score       DOUBLE
```

### fact_epi_score
Grain: One row per country × indicator × year
```
country_key                 BIGINT
indicator_key               BIGINT
year                        INTEGER (2024)
score                       DOUBLE
```

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
Grain: One row per day
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
