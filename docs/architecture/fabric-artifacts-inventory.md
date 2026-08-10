# Fabric Artifacts Inventory

As-built inventory of Fabric artifacts in the `oem_lh` workspace. Mirrors what is tracked in `fabric/` in this repo (the source `fabric-cicd` deploys from).

## Active artifacts

### 🔄 Pipeline

| Artifact | Type | Purpose | Status |
|---|---|---|---|
| `orchestrator_pipeline_bronze_to_gold` | DataPipeline | Main orchestration (10 activities: 4 Copy + 6 Notebook) | ✅ Active |

### 📓 Notebooks

| Artifact (repo dir) | Pipeline activity | Purpose | Status |
|---|---|---|---|
| `bronze_ingest_epi` | `bronze_EPI` | EPI ingestion from Yale (since task-035) | ✅ Active |
| `bronze_ingest_wgi` | `bronze_wgi` | WGI ingestion from World Bank API (since task-035) | ✅ Active |
| `bronze_to_silver` | `bronze_to_silver_cleaning` | Bronze → Silver cleaning + alias resolution | ✅ Active |
| `silver_to_gold` | `silver_to_gold` | Silver → Gold star schema (facts, dims, observability) | ✅ Active |
| `data_quality_checks` | `data_quality_checks` | Pipeline data-quality gate | ✅ Active |
| `pipeline_error_handler` | `pipeline_error_handler` | Error categorisation + execution-log write; runs on **every** outcome | ✅ Active |
| `data_quality_analysis` | — | DQ analysis (manual run, not on pipeline path) | ✅ Active (manual) |
| `sample_quality_data` | — | Demo-seed notebook for sample DQ rows | ⚠️ Demo seed — not part of the production pipeline path |

### 💾 Storage & serving

| Artifact | Type | Purpose | Status |
|---|---|---|---|
| `oem_lh` | Lakehouse | Medallion storage (Bronze/Silver/Gold Delta tables); **DirectLake source for the semantic model** | ✅ Active |
| `oem_lh` (SQL endpoint) | SQLEndpoint | Auto-created read-only T-SQL surface over the lakehouse. Distinct from a standalone Warehouse item, and **not** in the DirectLake path either | ✅ Active (auto-managed) |

### 📊 Analytics

| Artifact | Type | Purpose | Status |
|---|---|---|---|
| `OEMInsightBI` | SemanticModel | Star schema, DirectLake on `oem_lh`, **45 measures** across 8 tables / 10 relationships | ✅ Active |
| `oem_report` | Report | Power BI report over the semantic model | ✅ Active |

> **No Dataflow Gen2 items remain.** The last two (`EPI_file2table`, `WGI_file2table`) were retired 2026-08-10 — see *Previously removed* below.

## Previously removed

| Artifact | Type | Reason | Backup |
|---|---|---|---|
| `EPI_file2table` | Dataflow | Orphaned by task-035 (2026-07-26) when the pipeline moved to `bronze_ingest_epi`; removed 2026-08-10. Read a hand-uploaded CSV; the notebook downloads from `epi.yale.edu` directly | `.claude/support/retired/epi-wgi-file2table-dataflows/manifest.json` |
| `WGI_file2table` | Dataflow | Orphaned by task-035 (2026-07-26) when the pipeline moved to `bronze_ingest_wgi`; removed 2026-08-10. Read a hand-uploaded Excel extract (2023 only); the notebook pulls all 6 indicators 1996–2023 from the World Bank API | `.claude/support/retired/epi-wgi-file2table-dataflows/manifest.json` |
| `oem_wh` | Warehouse | Never read by anything — the semantic model is DirectLake on `oem_lh`, no pipeline activity or notebook wrote to it, and its data was a frozen 2026-01-16 snapshot. Removed 2026-08-10 | `.claude/support/retired/oem-wh-warehouse/manifest.json` |
| `StagingLakehouseForDataflows_20250822093021` | Lakehouse + SQLEndpoint | Auto-created Dataflow Gen2 staging; held 0 tables. Removed 2026-08-10 with the dataflows | — (Fabric-generated) |
| `StagingWarehouseForDataflows_20250822093045` | Warehouse | Auto-created Dataflow Gen2 staging; held 0 tables. Removed 2026-08-10 with the dataflows | — (Fabric-generated) |
| `Notebook_1` | Notebook | Scratch notebook from the Phase-5 snake_case rename verification; never in the repo. Removed 2026-08-10 | — (scratch) |
| `Report Usage Metrics Report` / `Report Usage Metrics Model` | Report / SemanticModel | Power BI auto-generated usage telemetry, not project content. Removed 2026-08-10 | — (Fabric-generated) |

## Previously removed (archived 2025-12-15)

| Artifact | Type | Reason | Backup |
|---|---|---|---|
| `bronze_azureSQLdb2table` | Dataflow | Replaced by Copy activities `bronze_copy_procurement_transactional` + `bronze_copy_supplier_ref` (2026-07-31) | `.claude/support/retired/bronze-azuresqldb2table-dataflow/manifest.json` |
| `StagingLakehouseForDataflows_20250822093021` | SemanticModel | Auto-generated staging model | `.archive/fabric-cleanup-20251215-132143/` |
| `StagingWarehouseForDataflows_20250822093045` | SemanticModel | Auto-generated staging model | `.archive/fabric-cleanup-20251215-132143/` |
| `oem_wh.SemanticModel` | SemanticModel | Empty model superseded by `OEMInsightBI` | `.archive/fabric-cleanup-20251215-132143/` |
| `oem_lh.SemanticModel` | SemanticModel | Auto-generated from lakehouse | `.archive/fabric-cleanup-20251215-132143/` |
| `copyjob1.CopyJob` | CopyJob | Experimental/unused copy operation | `.archive/fabric-cleanup-20251215-132143/` |

## Artifact dependencies

```mermaid
graph TD
    Pipeline[orchestrator_pipeline_bronze_to_gold]

    BC1[bronze_copy_procurement_transactional<br/>+ bronze_copy_supplier_ref]
    BE[bronze_ingest_epi / bronze_EPI]
    BW[bronze_ingest_wgi / bronze_wgi]

    BS[bronze_to_silver]
    SG[silver_to_gold]
    DQ[data_quality_checks]
    EH[pipeline_error_handler]

    LH[oem_lh.Lakehouse]
    SM[OEMInsightBI.SemanticModel]
    Report[oem_report.Report]

    Pipeline --> BC1 & BE & BW & BS & SG & DQ
    BC1 --> LH
    BE --> LH
    BW --> LH
    BS --> LH
    SG --> LH
    DQ --> LH
    Pipeline -.every outcome.-> EH
    EH --> LH

    LH --> SM
    SM --> Report

    style Pipeline fill:#e3f2fd
    style SM fill:#fff3e0
    style Report fill:#ffebee
```

The model's DirectLake source is `oem_lh`, read directly over OneLake. EPI/WGI ingestion is via notebooks. The `oem_wh` warehouse and both `*_file2table` dataflows that once sat alongside this graph were retired 2026-08-10; nothing in the graph referenced them.

## Naming-convention status

- ✅ `orchestrator_pipeline_bronze_to_gold` — clear, snake_case
- ✅ `oem_lh` — short, lowercase
- ✅ `silver_to_gold` — renamed from `silver-to-gold2` in Phase 5 (snake_case, dropped the version stamp)
- ✅ `OEMInsightBI` — renamed from `OEMInsightBI_v2` on 2026-08-10 (dropped the version suffix)
- ✅ `sample_quality_data` — renamed from `sample-quality-data` on 2026-08-10 (last hyphenated notebook name)
- ✅ `oem_report` — renamed from `report2` on 2026-08-10 (co-named with its semantic model per `standards/naming_standards.md § Semantic Model & Report Naming`)

**All naming targets are now closed.** No open renames remain.
- ✅ Bronze activities are snake_case since Phase 4 (`bronze_copy_*`, `bronze_epi`, `bronze_wgi`); the three PascalCase bronze **tables** were renamed to snake_case in Phase 5 batch B

See `standards/naming_standards.md` for the canonical convention (snake_case, layer-prefixed) and the planned reconciliations.

## Maintenance guidelines

**Remove when:** auto-generated `Staging*` models; empty semantic models with no business logic; experimental artifacts not referenced by the pipeline; artifacts superseded by a replacement (with a retirement manifest under `.claude/support/retired/`).

**Keep when:** referenced by the pipeline; carries business logic (DAX, transforms); part of the medallion; required by the report.

## Related docs

- `semantic_model.md` — semantic model detail (DirectLake on `oem_lh`)
- `orchestration.md` — pipeline activity detail
- `standards/naming_standards.md` — naming conventions + planned renames