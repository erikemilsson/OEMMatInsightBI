# Changelog

Notable changes to the OEMMatInsightBI project. The project does not cut versioned releases — it evolves on `main` — so this log is organized by phase rather than by semver tag. Dates are approximate phase boundaries, not release dates.

---

## 2026-08 — Pre-publishing curation

### Changed
- **Doc migration:** domain docs moved from `.claude/support/documents/` → `docs/` as the canonical documentation surface; `.claude/` curtailed to spec, decisions, and agent environment (rigor public, scaffolding gitignored).
- **DAX library rewritten** against the live TMDL — 45 measures across 8 tables / 10 relationships (was a 2025-11 design doc claiming "no measures").
- **Architecture docs rewritten** — DirectLake source corrected to `oem_lh` lakehouse (not `oem_wh` warehouse); as-built star schema (replaced fictional `dim_supplier`/`dim_product`/`fact_transactions`); `xxhash64` surrogate keys (not SHA-256/base64); 10-activity pipeline flow.
- **Error-recovery playbook retry table** completed from `pipeline-content.json` (was missing 3 of 10 activities; corrected EPI/WGI retry intervals).
- **Renames:** `external_data_automation.md` → `epi_wgi_ingestion.md`; `DQ_PAGE_GUIDE.md` → `data_quality_page_guide.md`; `MEASURE_GUIDE.md` → `dax_measure_guide.md`.
- **Removed:** fabricated `guides/performance-baselines.md` (kept the measured `performance_baseline.md` as single source).

### Removed
- Root clutter (`nb-*.png`, `project_definition.md`, `MISSION_CONTROL.md`, `OEMMatInsightBI.code-workspace`).
- Dead docs (`dax_measures.md`, `complete-task-legacy.md`, `hooks-reference.md`, `templates-reference.md`).
- `src/monitoring/performance_monitor.py` (sole parity-contract violator — parity is now uniform).
- Unused pytest markers (`integration`, `slow`, `smoke`) and dead conftest fixtures; `load_notebook_functions` consolidated.

---

## 2026-05 through 2026-07 — Build phase

### Added
- **EPI/WGI ingestion notebooks** (`bronze_ingest_epi`, `bronze_ingest_wgi`) replacing the retired `EPI_file2table` / `WGI_file2table` dataflows (task-035).
- **Azure SQL Copy activities** (`bronzecopy_procurement_transactional`, `bronzecopy_supplier_ref`) replacing the retired `bronze_azureSQLdb2table` dataflow.
- **Data-quality observability layer** — `gold_data_gaps`, `gold_gap_registry`, `gold_quality_history`, `gold_low_confidence_audit`, populated by `silver-to-gold2` and `data_quality_checks`; blocking DQ gate.
- **45 DAX measures** in the `OEMInsightBI_v2` semantic model (DirectLake on `oem_lh`), including the weighted EPI score (task-056 weight ingestion), HHI supply risk, and the 33-measure coverage/observability set.
- **Parity contract** (task-032) — `tests/` load notebook functions and pin parity against `src/`; semantic gaps asserted, not fixed.
- **`fabric-cicd` deploy** via GitHub Actions; `pipeline_error_handler` wired to run on every pipeline outcome.
- **Measured performance baseline** (3-run, warm-cache) and honest null-result documentation (Taiwan's permanent WGI gap).

### Changed
- Pipeline grew to 10 activities; live per-activity retry policy configured.
- 13 architecture decision records (ADRs) captured under `.claude/support/decisions/`.

---

## 2025-11 — Initial design phase

### Added
- Project specification (`.claude/spec_v1.md`) — the source of truth.
- Medallion architecture design (Bronze / Silver / Gold), star schema (3 facts + 5 dimensions), DAX measure library design, RLS six-role strategy, ISO 25012 DQ framework, incremental-load strategy, error-handling strategy.
- 10 custom slash commands for pipeline operations.
- pytest unit-test framework for `src/transformations/`.

---

*Task history is summarized in [`docs/PROJECT_PROGRESS.md`](docs/PROJECT_PROGRESS.md); the project spec is [`.claude/spec_v1.md`](.claude/spec_v1.md).*