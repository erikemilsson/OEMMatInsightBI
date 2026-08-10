# Spec excerpt — `oem_wh` Warehouse

Captured from `.claude/spec_v1.md` at retirement SHA `b12cfbbce6e0d50dd7268aeb78cb94471885d421` (2026-08-10).

This file is the historical record of what the spec said about the warehouse *before* the retirement markers were added. Per `.claude/rules/feature-retirement.md` Step 4, the spec sections themselves were annotated, not excised.

> ⚠️ **Several claims below were measured false against the live warehouse on 2026-08-10.** They are reproduced verbatim as historical record. See "Measured reality at retirement" at the bottom.

---

## § Project Context (spec line 48)

> **Secondary Purpose:** This project also serves as hands-on preparation for a data engineering consultant role (Rejlers). Beyond demonstrating a working BI solution, it exercises production patterns commonly encountered at client sites: incremental Delta MERGE loading, SQL warehouse stored procedures alongside PySpark notebooks, pipeline error handling with retry logic, and CI/CD deployment via GitHub Actions. The hybrid Lakehouse + Warehouse approach reflects standard Fabric practice.

## § Fabric Artifacts (spec line 80)

> -   **Warehouse:** `oem_wh` (SQL-queryable layer for BI)

## § Orchestration — planned work (spec line 682)

> **Planned — not yet orchestrated:** warehouse sync (gold → `oem_wh`). No pipeline activity exists for this today. The warehouse itself is real — see § Infrastructure & Deployment (SQL endpoint, views, `usp_merge_fact_procurement`); only the automated sync is outstanding.

## § Infrastructure & Deployment — Warehouse Configuration (spec lines 1191–1225)

> ### Warehouse Configuration
>
> **Warehouse Name:** `oem_wh`
>
> **Warehouse ID:** b1cb7506-8d2d-4e4a-97cc-2b580da8eda0 (from `fabric/oem_wh.Warehouse/.platform`)
>
> **Purpose:** SQL-queryable analytics layer with business-logic transformations. Combines mirrored gold tables from the Lakehouse with native SQL views and stored procedures.
>
> **Tables/Views:**
>
> -   Mirrors gold layer tables via Lakehouse-to-Warehouse sync (Copy Job)
> -   Schema: dbo (default schema)
> -   The semantic model does not query this warehouse — its DirectLake mode reads the `oem_lh` lakehouse's Delta/parquet tables directly (see § Semantic Model & Reporting)
>
> **SQL Business Logic Objects (in `oem_wh`):**
>
> The warehouse hosts SQL views and stored procedures that complement PySpark notebook transformations. This hybrid approach follows standard Fabric practice — notebooks handle complex ETL in the Lakehouse, SQL handles structured analytics and business rules in the Warehouse.
>
> **Views:**
> -   `dbo.v_procurement_summary` — Procurement spend aggregated by material, country, and time period with dimension attributes joined
> -   `dbo.v_supply_concentration_risk` — Supply concentration risk analysis by material and stage, with risk tier classification (Critical/High/Medium/Low)
> -   `dbo.v_supplier_sustainability_scorecard` — Combines procurement spend with EPI and WGI scores per supplier country for ESG reporting
> -   `dbo.v_data_quality_overview` — Cross-table data quality summary (match rates, unmapped counts, confidence distributions)
>
> **Stored Procedures:**
> -   `dbo.usp_merge_fact_procurement` — Incremental MERGE for fact_procurement using watermark-based change detection. Demonstrates the Delta MERGE pattern in T-SQL as an alternative to PySpark.
> -   `dbo.usp_refresh_quality_metrics` — Refreshes aggregated data quality metrics from audit tables
>
> **Connection:**
>
> -   Endpoint: 2BINPJYTVAEEVEF26XKMILPX4E-NXGOJGODN2TUTLWZW2NQJKL2VE.datawarehouse.fabric.microsoft.com
> -   Database ID: b1cb7506-8d2d-4e4a-97cc-2b580da8eda0

## § Remaining Work (spec lines 1299, 1608)

> -   [x] ~~Index creation in warehouse~~ — **not applicable** (platform limitation), see DEC-012. Task-012_4 was retired on this basis (2026-08-03).

> 2. **SQL Warehouse Analytics Layer** — already implemented (4 views + 2 stored procedures in `oem_wh`). No additional work needed.

---

## Measured reality at retirement (2026-08-10)

Queried live over TDS (`sys.objects WHERE is_ms_shipped = 0`) against
`2binpjytvaeevef26xkmilpx4e-…datawarehouse.fabric.microsoft.com`, database `oem_wh`:

- **8 `USER_TABLE` objects. Zero views. Zero stored procedures.**
- All 8 created `2026-01-16 08:14`, with `modify_date == create_date` — never altered.
- None of the 4 views or 2 stored procedures the spec describes have ever existed as warehouse objects. The three `v_*` names are Spark-catalog views created inside `silver_to_gold.Notebook` over the lakehouse (established independently by task-038_2, which noted they are "invisible to the SQL endpoint").

Row counts, `oem_wh` (frozen 2026-01-16) vs `oem_lh` (live, same day):

| Table | `oem_wh` | `oem_lh` |
|---|---:|---:|
| fact_epi_score | 206 | 12,196 |
| fact_supply_share | 58,542 | 3,463 |
| fact_procurement | 144 | 132 |
| gold_dim_material | 93 | 96 |
| gold_dim_date | 336 | 337 |
| gold_dim_country | 193 | 193 |
| gold_dim_indicator | 73 | 73 |
| gold_dim_stage | 2 | 2 |

The warehouse diverged from the live model in **both** directions — 59× understated on `fact_epi_score`, 17× overstated on `fact_supply_share`.
