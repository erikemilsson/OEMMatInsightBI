# Star Schema Entity Relationship Diagram

## Semantic Model Overview

```mermaid
erDiagram
    fact_transactions ||--o{ dim_country : "country_key"
    fact_transactions ||--o{ dim_material : "material_key"
    fact_transactions ||--o{ dim_supplier : "supplier_key"
    fact_transactions ||--o{ dim_date : "date_key"
    fact_transactions ||--o{ dim_product : "product_key"

    fact_supply_share ||--o{ dim_country : "country_key"
    fact_supply_share ||--o{ dim_material : "material_key"

    fact_sustainability ||--o{ dim_country : "country_key"
    fact_sustainability ||--o{ dim_date : "date_key"

    fact_transactions {
        string transaction_key PK
        string country_key FK
        string material_key FK
        string supplier_key FK
        string date_key FK
        string product_key FK
        decimal quantity
        decimal total_price
        decimal unit_price
        string currency_code
        string order_type
    }

    fact_supply_share {
        string supply_share_key PK
        string country_key FK
        string material_key FK
        decimal extraction_percent
        decimal processing_percent
        decimal production_percent
        decimal supply_risk_index
    }

    fact_sustainability {
        string sustainability_key PK
        string country_key FK
        string date_key FK
        decimal epi_score
        decimal air_quality_score
        decimal water_resources_score
        decimal wgi_control_corruption
        decimal wgi_govt_effectiveness
        decimal wgi_regulatory_quality
        decimal composite_esg_score
    }

    dim_country {
        string country_key PK
        string country_code
        string country_name
        string region
        string sub_region
        decimal gdp_usd
        int population
        string income_level
    }

    dim_material {
        string material_key PK
        string material_id
        string material_name
        string material_category
        string material_type
        string unit_of_measure
        boolean is_critical_raw
        boolean is_hazardous
    }

    dim_supplier {
        string supplier_key PK
        string supplier_id
        string supplier_name
        string supplier_country
        string supplier_type
        string payment_terms
        decimal reliability_score
    }

    dim_date {
        string date_key PK
        date date_value
        int year
        int quarter
        int month
        int week
        string month_name
        string day_name
        boolean is_weekend
    }

    dim_product {
        string product_key PK
        string product_id
        string product_name
        string product_category
        string product_line
        decimal weight_kg
        string bom_level
    }
```

## Measure Table Structure

```mermaid
graph TB
    subgraph Measures["📊 _Measures Table"]
        subgraph Procurement["💰 Procurement Metrics"]
            M1[Total Spend]
            M2[Total Quantity]
            M3[Transaction Count]
            M4[Avg Unit Price]
            M5[Avg Spend per Transaction]
            M6[Unique Suppliers Count]
            M7[Supplier Countries Count]
        end

        subgraph Sustainability["🌱 Sustainability Metrics"]
            M8[Avg EPI Score]
            M9[Latest EPI Score]
            M10[EPI YoY Change]
            M11[Avg WGI Effectiveness]
        end

        subgraph Risk["⚠️ Risk Metrics"]
            M12[HHI Index]
            M13[Material Risk Index]
            M14[Spend Exposure at Risk]
            M15[Top 3 Countries Spend %]
            M16[Diversification Score]
            M17[Materials Count]
            M18[Risk-Adjusted Spend]
        end
    end

    style Procurement fill:#e3f2fd
    style Sustainability fill:#e8f5e9
    style Risk fill:#fff3e0
```

## Relationship Cardinality

| From Table | To Table | Relationship Type | Cardinality | Active |
|------------|----------|-------------------|-------------|---------|
| fact_transactions | dim_country | Many-to-One | M:1 | ✅ Yes |
| fact_transactions | dim_material | Many-to-One | M:1 | ✅ Yes |
| fact_transactions | dim_supplier | Many-to-One | M:1 | ✅ Yes |
| fact_transactions | dim_date | Many-to-One | M:1 | ✅ Yes |
| fact_transactions | dim_product | Many-to-One | M:1 | ✅ Yes |
| fact_supply_share | dim_country | Many-to-One | M:1 | ✅ Yes |
| fact_supply_share | dim_material | Many-to-One | M:1 | ✅ Yes |
| fact_sustainability | dim_country | Many-to-One | M:1 | ✅ Yes |
| fact_sustainability | dim_date | Many-to-One | M:1 | ❌ No (avoid ambiguity) |

## Key Generation Pattern

```mermaid
flowchart LR
    subgraph Input["Input Columns"]
        C1[country_code]
        C2[supplier_id]
        C3[material_id]
    end

    subgraph Process["stable_key() Function"]
        P1[Concatenate]
        P2[Add Separator]
        P3[SHA-256 Hash]
        P4[Base64 Encode]
    end

    subgraph Output["Surrogate Key"]
        K1[country_key<br/>e.g., 'Zm9vYmFy...']
    end

    C1 --> P1
    C2 --> P1
    C3 --> P1
    P1 --> P2
    P2 --> P3
    P3 --> P4
    P4 --> K1

    style Input fill:#bbdefb
    style Process fill:#c5e1a5
    style Output fill:#ffe082
```

## Data Volume Estimates

```mermaid
pie title "Data Distribution by Table"
    "fact_transactions" : 45
    "fact_supply_share" : 5
    "fact_sustainability" : 5
    "dim_country" : 10
    "dim_material" : 15
    "dim_supplier" : 10
    "dim_date" : 5
    "dim_product" : 5
```

### Row Count Estimates
- **fact_transactions**: ~50,000 rows (2 years of data)
- **fact_supply_share**: ~5,000 rows (country-material combinations)
- **fact_sustainability**: ~400 rows (200 countries × 2 years)
- **dim_country**: ~200 rows
- **dim_material**: ~1,000 rows
- **dim_supplier**: ~500 rows
- **dim_date**: ~730 rows (2 years)
- **dim_product**: ~100 rows

---

*Last Updated: 2025-12-15*