# Lens: path-drift

Findings: 1

## F-pat-01
- **Title:** Stale `silver_WB` reference in data_quality_analysis notebook
- **Severity:** med
- **Source anchor:** `fabric/data_quality_analysis.Notebook/notebook-content.py:421` (FR-028, open)
- **Files affected (read-only):** `fabric/data_quality_analysis.Notebook/notebook-content.py`, `.claude/spec_v1.md` § Data Transformations (line 380, 1602 — confirm `silver_WB` retired), `fabric/silver-to-gold2.Notebook/notebook-content.py:331,675,1020` (the removal site)
- **Files to touch (potential fix):** `fabric/data_quality_analysis.Notebook/notebook-content.py`
- **Evidence:**
  - `notebook-content.py:421` reads exactly: `wb_countries = (spark.table(f"{DB}.silver_WB")`
  - `silver-to-gold2.Notebook/notebook-content.py:331` carries: `# NOTE: silver_WB table removed (World Bank ESG data not available)`
  - `spec_v1.md:380`: "Supersedes the retired `bronze_WB_ESGCSV` + `bronze_WB_ESGSeries` → `silver_WB` CSV/dataflow lineage — no live artifact produces those tables."
  - `spec_v1.md:1602`: "From silver_WB (retired — no live artifact produces this table)"
  - Grep confirms zero live producers of `silver_WB` across all `.py/.sql/.tmdl/.yml/.json` files (only references are in retired-lineage notes, the analysis notebook's stale read, and documentation noting retirement).
- **What:** The analysis-only notebook `data_quality_analysis.Notebook` still calls `spark.table(f"{DB}.silver_WB")` at line 421, but no live artifact writes that table — the World Bank ESG lineage was retired and `silver-to-gold2.Notebook` explicitly notes its removal.
- **Why:** Running the notebook would raise `AnalysisException: Table not found` because the retired lineage that produced `oem_lh.silver_WB` has no successor; the reference is latent only because this notebook is not a pipeline activity (per spec § Orchestration, the terminal DQ activity is `data_quality_checks.Notebook`, a different file).
- **Suggested fix:** Edit `fabric/data_quality_analysis.Notebook/notebook-content.py:421` to drop or replace the `silver_WB` reference (e.g., redirect to `silver_wgi` which is the live World Bank governance table, or remove the WB coverage leg entirely) — closing FR-028.
- **Suggested kind:** fix-eligible
