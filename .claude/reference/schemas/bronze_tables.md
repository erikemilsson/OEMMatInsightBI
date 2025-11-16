# Bronze Layer Table Schemas

## bronze_procurement_transactional
Source: Azure SQL dbo.Procurement
Grain: One row per material purchase
```
Date                        DATE
MaterialName                STRING (NVARCHAR(100))
SupplierName                STRING (NVARCHAR(200))
Region                      STRING (NVARCHAR(100))
Quantity                    DECIMAL(18,2)
Unit                        STRING (NVARCHAR(50))
UnitPriceEUR                DECIMAL(18,2)
```

## bronze_supplier_ref
Source: Azure SQL dbo.SupplierInfo
Grain: One row per supplier
```
SupplierName                STRING (NVARCHAR(200))
HeadquartersCountry         STRING (NVARCHAR(100))
ProductionCountry           STRING (NVARCHAR(100))
Region                      STRING (NVARCHAR(100))
```

## bronze_epi2024results
Source: EPI CSV file
Grain: One row per country (wide format)
```
code                        INTEGER
iso                         STRING (ISO3)
country                     STRING
EPI                         DOUBLE
[30+ indicator columns]     DOUBLE (e.g., AIR, BIO, CLI, etc.)
```

## bronze_WB_ESGCSV
Source: WGI CSV file
Grain: One row per country × indicator (wide format with year columns)
```
Country Name                STRING
Country Code                STRING (ISO3)
Indicator Name              STRING
Indicator Code              STRING
y_2000, y_2001, ..., y_2023 DOUBLE (year columns)
```

## bronze_WB_ESGSeries
Source: WGI metadata CSV
Grain: One row per indicator
```
Indicator Code              STRING
Topic                       STRING
Indicator Name              STRING
```

## bronze_GlobalSupplyShares
Source: EU CRM GitHub CSV (HTTP)
Grain: One row per material × stage × country
```
Material                    STRING
Stage                       STRING ("E" or "P")
Country                     STRING
Share                       STRING (percentage with % symbol)
t                           STRING (unused, dropped in silver)
```
