# OEMMatInsightBI

Microsoft Fabric-based BI solution for OEM procurement material sourcing analysis. Uses a medallion architecture (Bronze/Silver/Gold) with PySpark notebooks, Delta Lake tables, a Power BI semantic model (TMDL), and DAX measures.

> Full environment instructions: `.claude/CLAUDE.md`

## Purpose

Portfolio project for a data engineering role. Demonstrates Microsoft Fabric end-to-end: Lakehouse, PySpark, Delta Lake, DirectLake semantic model, Power BI, and pipeline orchestration. Also a learning vehicle for production patterns (incremental Delta MERGE, data quality observability, CI/CD with `fabric-cicd`).

Companion project: `nordgrid-data-engineering` — covers SQL/dbt depth (MERGE, stored procs, SCD, execution plans, Airflow). Between the two projects, the core data engineering skill set is covered.

## Technology Stack

Microsoft Fabric, PySpark, Delta Lake, Power BI, DAX, TMDL

## Project Structure

```
OEMMatInsightBI/
├── fabric/                    # Microsoft Fabric artifacts
│   ├── *.Notebook/            # PySpark transformation notebooks
│   ├── *.SemanticModel/       # Power BI semantic model (TMDL)
│   ├── *.DataPipeline/        # Orchestrator pipeline
│   └── *.Lakehouse/           # Lakehouse metadata
├── src/transformations/       # Testable Python modules
└── tests/                     # pytest unit tests
```

## Key Commands

**Pipeline Operations:**
- `/run-bronze` - Run bronze layer ingestion
- `/run-silver` - Run silver transformations
- `/run-gold` - Run gold layer creation
- `/run-full-pipeline` - Run complete pipeline (Bronze to Gold)

**Data Quality:**
- `/check-quality` - Run data quality checks
- `/validate-schema` - Validate table schemas
- `/view-unmapped` - View unmapped values
- `/review-transformations` - Review transformation logic

**Fabric Sync:**
- `/sync-from-fabric` - Pull changes from Fabric workspace
- `/sync-to-fabric` - Push changes to Fabric workspace

## Conventions

- **Medallion architecture**: Bronze (raw) -> Silver (cleaned) -> Gold (business logic)
- **Delta Lake**: All gold tables use Delta format for MERGE support
- **TMDL**: Semantic model defined as code (not .pbix)
- **Quality observability**: Three tables track data quality trends over time
- **Testable transforms**: Python modules in `src/` with pytest coverage
- Erik works in Fabric UI; Claude writes code locally. Tasks with `owner: "both"` need coordination.
- **Friction register**: frictions are *not* converted to tasks — they carry `owned_by_task` and are clustered by `/audit-coherence`. Local conventions: `.claude/support/reference/project-friction-conventions.md`

## Domain Knowledge

Located in `.claude/support/documents/`:
- `architecture/` - Medallion layers, semantic model, data sources, orchestration
- `schemas/` - Bronze and gold table schemas
- `standards/` - Coding, SQL, naming, git workflow
- `transformations/` - Country/material alias mappings
- `glossary.md` - 98 terms defined
- `dax_measure_library.md` - 40+ DAX measures
- `rls_security_strategy.md` - 6 security roles
- `data_quality_framework.md` - ISO 25012 quality checks
- `data_quality_architecture.md` - Quality observability tables
- `incremental_load_strategy.md` - Delta MERGE patterns
- `external_data_automation.md` - EPI/WGI automation

## Gotchas

- Fabric workspace ID: `99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9`
- Lakehouse: `oem_lh` (ID: `488fb9f8-e635-4683-90c4-ba4fee9dfadb`)
- [Open Workspace](https://app.fabric.microsoft.com/groups/99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9)
- [Lakehouse (oem_lh)](https://app.fabric.microsoft.com/groups/99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9/lakehouses/488fb9f8-e635-4683-90c4-ba4fee9dfadb)
- `settings.local.json` easily gets polluted with captured shell commands — check periodically
- **PySpark transformation logic IS locally testable.** `pyspark` 4.0.1 and OpenJDK 17 are installed; a `local[1]` SparkSession over an in-memory fixture runs pure-DataFrame logic in under a minute. Do not accept "no Spark session, Fabric-only" as a verification ceiling for transformation code — execute it. The genuine local ceiling is **Delta-specific operations** (MERGE, time travel — `delta-spark` is *not* installed) and anything lakehouse-dependent. Established 2026-07-23 when verify-agent measured task-027's restructure (9/9 assertions) that both the task notes and the dispatch brief had assumed could only be reasoned about.
- **pyspark `Row` subclasses `tuple`**, so an aliased column named `count` (or `index`) shadows the tuple method: `row.count` returns the bound method, and `float(row.count)` raises `TypeError`. Never alias a column `as count` if the result is read by attribute access.
