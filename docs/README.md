# OEMMatInsightBI Documentation

Canonical project documentation. The project root [`README.md`](../README.md) is the entry point (what the project demonstrates, setup, portfolio links); this directory is the structured reference.

## 🏗️ Architecture

| Doc | What it covers |
|---|---|
| [architecture/medallion_architecture.md](./architecture/medallion_architecture.md) | Bronze / Silver / Gold layer responsibilities |
| [architecture/data-flow-diagram.md](./architecture/data-flow-diagram.md) | End-to-end pipeline flow, orchestration, incremental load, error handling |
| [architecture/orchestration.md](./architecture/orchestration.md) | Pipeline activity detail (10 activities) |
| [architecture/semantic_model.md](./architecture/semantic_model.md) | DirectLake model on `oem_lh` — 14 tables, 10 relationships, 45 measures |
| [architecture/star-schema-erd.md](./architecture/star-schema-erd.md) | ER diagram + relationship cardinality + surrogate-key generation |
| [architecture/fabric-artifacts-inventory.md](./architecture/fabric-artifacts-inventory.md) | Every Fabric artifact, its status, and dependencies |
| [architecture/data_sources.md](./architecture/data_sources.md) | Source systems (Azure SQL, EPI, WGI, EU/global supply shares) |
| [architecture/fabric_workspace.md](./architecture/fabric_workspace.md) | Workspace + lakehouse setup |

## 📐 Schemas & transformations

| Doc | What it covers |
|---|---|
| [schemas/bronze_tables.md](./schemas/bronze_tables.md) | Bronze table schemas |
| [schemas/gold_tables.md](./schemas/gold_tables.md) | Gold fact / dimension / observability table schemas |
| [transformations/alias_mappings.md](./transformations/alias_mappings.md) | Country / material alias mappings and confidence scoring |
| [calculations.md](./calculations.md) | Authoritative business formulas (spend, HHI, coverage) |
| [business_rules.md](./business_rules.md) | Business rules (spend formula, quality categories) |
| [epi_wgi_ingestion.md](./epi_wgi_ingestion.md) | EPI / WGI ingestion and weight loading |

## 📊 Measures & quality

| Doc | What it covers |
|---|---|
| [dax_measure_library.md](./dax_measure_library.md) | **As-built** measure catalogue — 45 measures across 8 tables (mirrors the live TMDL) |
| [data_quality_architecture.md](./data_quality_architecture.md) | Shipped DQ observability surface (touchpoints, gate, tables) |
| [data_quality_framework.md](./data_quality_framework.md) | ISO 25012 dimension definitions + scoring weights (design rationale) |
| [data_quality_guide.md](./data_quality_guide.md) | DQ monitoring system guide |
| [data_coverage_flow.md](./data_coverage_flow.md) | Coverage dashboard flow |
| [rls_security_strategy.md](./rls_security_strategy.md) | RLS six-role design (unimplemented — see spec reconciliation) |

## 🚀 Guides

| Guide | What it covers |
|---|---|
| [guides/dax_measure_guide.md](./guides/dax_measure_guide.md) | How to read and extend the DAX measures |
| [guides/data_quality_page_guide.md](./guides/data_quality_page_guide.md) | Building the Data Gaps page in Power BI |
| [guides/pipeline_schedule.md](./guides/pipeline_schedule.md) | Pipeline schedule (daily 06:00 Europe/Stockholm) |
| [guides/FAQ.md](./guides/FAQ.md) | Frequently asked questions |

## ⚡ Performance & operations

| Doc | What it covers |
|---|---|
| [performance_baseline.md](./performance_baseline.md) | **Measured** 3-run pipeline baseline (~16.6 min functional total) |
| [performance_optimized.md](./performance_optimized.md) | V-Order / DirectLake optimization notes |
| [incremental_load_strategy.md](./incremental_load_strategy.md) | Delta MERGE patterns + watermark mechanism |
| [error_recovery_playbook.md](./error_recovery_playbook.md) | Operational playbook — per-activity retry table, resolution steps, log queries |
| [error_handling_strategy.md](./error_handling_strategy.md) | Retry / categorization / notification design rationale |

## 📦 Portfolio

| Doc | What it covers |
|---|---|
| [portfolio/CASE_STUDY.md](./portfolio/CASE_STUDY.md) | Portfolio case study (centerpiece) |
| [portfolio/PORTFOLIO_DESIGN.md](./portfolio/PORTFOLIO_DESIGN.md) | Power BI report design |
| [portfolio/PORTFOLIO_ASSETS_README.md](./portfolio/PORTFOLIO_ASSETS_README.md) | Guide to portfolio deliverables |

## 🛠️ Setup & standards

| Doc | What it covers |
|---|---|
| [setup/TROUBLESHOOTING.md](./setup/TROUBLESHOOTING.md) | Common issues and solutions |
| [standards/coding_standards.md](./standards/coding_standards.md) | Coding standards |
| [standards/sql_standards.md](./standards/sql_standards.md) | SQL standards |
| [standards/naming_standards.md](./standards/naming_standards.md) | Naming conventions (snake_case, layer-prefixed) |
| [standards/git_workflow.md](./standards/git_workflow.md) | Git workflow + commit conventions |

Also: [business_context.md](./business_context.md) (problem, stakeholders, business questions), [glossary.md](./glossary.md) (domain + technical terms), [PROJECT_PROGRESS.md](./PROJECT_PROGRESS.md) (task summary).

## 🔗 Beyond `docs/`

- [Root README](../README.md) — project overview, what it demonstrates, portfolio links
- [CONTRIBUTING.md](../CONTRIBUTING.md) — dev setup and contribution guide
- [CHANGELOG.md](../CHANGELOG.md) — version history
- [`.claude/spec_v1.md`](../.claude/spec_v1.md) — the project specification (source of truth)
- [`.claude/support/decisions/`](../.claude/support/decisions/) — 13 architecture decision records
- [`fabric/`](../fabric/) — Microsoft Fabric artifacts (notebooks, pipeline, semantic model)

## 📊 At a glance

- **Semantic model:** 45 measures, 14 tables, 10 relationships (DirectLake on `oem_lh`)
- **Pipeline:** 10 activities, daily 06:00 Europe/Stockholm, measured ~16.6 min functional total
- **Tests:** 300 pytest tests (local PySpark over in-memory fixtures; `src/` is a tested mirror of the notebook logic)
- **Docs:** this directory is the canonical documentation surface