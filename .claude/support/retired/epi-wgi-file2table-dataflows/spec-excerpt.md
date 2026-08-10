# Spec excerpt — `EPI_file2table` / `WGI_file2table` Dataflow Gen2

Captured from `.claude/spec_v1.md` at retirement SHA `b12cfbbce6e0d50dd7268aeb78cb94471885d421` (2026-08-10).

This file is the historical record of what the spec said about these two dataflows *before* the retirement markers were added. Per `.claude/rules/feature-retirement.md` Step 4, the spec sections themselves were annotated, not excised.

---

## § Data Sources — EPI (spec line 210)

> **Ingestion Method:** `bronze_ingest_epi.Notebook` (PySpark, automated HTTP download from `epi.yale.edu` with retry; year-parameterised per task-028). Supersedes the retired `EPI_file2table.Dataflow` CSV lineage.

## § Data Sources — WGI (spec lines 257, 263)

> **File Format:** CSV (inferred from dataflow type)

> **Ingestion Method:** `bronze_ingest_wgi.Notebook` (PySpark, API-based). Supersedes the retired `WGI_file2table.Dataflow` CSV lineage.

## § Data Quality — WGI range rule (spec line 435)

> Score range validation — EPI scores 0-100. **Not applied to WGI:** the World Bank API serves *estimates* (approx. −2.5…+2.5), not the retired `WGI_file2table.Dataflow` extract's 0-100 percentile ranks. No range rule is enforced on `silver_wgi`.

## § Naming Conventions — Dataflows (spec lines 1012–1018)

> **Dataflows:**
>
> **Retired (2026-07-31)** — the example below no longer exists. The convention itself still stands for `EPI_file2table` / `WGI_file2table`, which remain as items.
>
> -   `[layer]_[source]_[method]2table.Dataflow`
>
> -   Examples: ~~`bronze_azureSQLdb2table`~~ (retired), `EPI_file2table`, `WGI_file2table`

## § Naming Conventions — consistency notes (spec line 1038)

> Remaining non-snake_case names are Fabric-generated or convention-bound: `StagingLakehouseForDataflows_*` / `StagingWarehouseForDataflows_*` (auto-created for dataflow staging) are camelCase; […] `EPI_file2table` / `WGI_file2table` follow the dataflow convention above. […] **`copyjob1` does not exist** in the workspace — 22 items enumerated 2026-08-06.

## § Appendix — EPI source note (spec line 1485)

> -   Source: Yale EPI (https://epi.yale.edu/), file-based dataflow ingestion

---

## What the dataflows actually did (captured from the snapshot)

**`EPI_file2table`** — read a hand-uploaded CSV at `Files/EPI/epi2024results.csv` from the `oem_lh` lakehouse, promoted headers (149 columns), wrote to lakehouse table `bronze_epi2024results`. No filtering, no renaming, no year parameterisation.

**`WGI_file2table`** — read a hand-uploaded Excel extract at `Files/WGI/P_Data_Extract_From_Worldwide_Governance_Indicators.xlsx`, kept only the 2023 percentile-rank column, renamed `2023 [YR2023]` → `Percentile Rank 2023`, selected 4 columns (`Country Name`, `Country Code`, `Series Name`, `Percentile Rank 2023`), stripped `": Percentile Rank"` from the series name, wrote to `bronze_WGI` (same table as the notebook's `bronze_wgi` — the metastore lowercases identifiers).

Both depended on a **manual file upload** into the lakehouse `Files/` area, which is the lineage the notebooks eliminated.
