# Lens: vocab-drift

Findings: 2

No open `vocab_drift`/`terminology_mismatch` friction entries exist (FR-025/027/028/029 are `design_contradiction`/`spec_implementation_gap`/`path_drift` — not this lens's kinds). Two clear cross-section vocabulary drift pairs found in the spec itself.

## F-voc-01
- **Title:** External ingestion artifact naming drift (EPI/WGI)
- **Severity:** med
- **Source anchor:** spec_v1.md § Data Sources #2 (line 208) and § Data Sources #3 (line 254) — canonical sections
- **Files affected (read-only):** `.claude/spec_v1.md`
- **Files to touch (potential fix):** `.claude/spec_v1.md`
- **Evidence:**
  - § Data Sources #2 line 208: "**Ingestion Method:** `EPI_file2table.Dataflow`" vs line 238: "Bronze table: `bronze_epi2024results` — derived by `bronze_ingest_epi.Notebook`"
  - § Data Sources #3 line 254: "**Ingestion Method:** `bronze_ingest_wgi.Notebook` (PySpark, API-based). Supersedes the retired `WGI_file2table.Dataflow` CSV lineage."
  - § Current State Assessment lines 822/824: "[x] EPI file ingestion (`EPI_file2table.Dataflow`)" / "[x] WGI file ingestion (`WGI_file2table.Dataflow`)"
  - § Dependencies & External Systems lines 1432/1444: "Ingestion: Automated via dataflow after manual file upload" (for both EPI and WGI)
  - § Development Workflow line 985: "Examples: `bronze_azureSQLdb2table`, `EPI_file2table`, `WGI_file2table`"
- **What:** The same concept (EPI/WGI ingestion method) is named with three different artifact terms across sections — the current notebooks (`bronze_ingest_epi.Notebook`, `bronze_ingest_wgi.Notebook`), the retired dataflows (`EPI_file2table.Dataflow`, `WGI_file2table.Dataflow`), and generic "dataflow"/"RefreshDataflow" wording.
- **Why:** § Data Sources explicitly declares the notebooks as the live method and the dataflows as retired, but § Current State, § Dependencies, and § Development Workflow still use the retired dataflow names as if they were current, misrouting any reader who follows those references.
- **Suggested fix:** Spec amendment via /iterate to standardize on `bronze_ingest_epi.Notebook` / `bronze_ingest_wgi.Notebook` (per § Data Sources #2/#3) across § Current State Assessment (lines 822/824), § Dependencies & External Systems (lines 1432/1444), § Development Workflow naming-convention examples (line 985), and to reconcile the § Orchestration table's `RefreshDataflow` activity-type labels (lines 621/623).
- **Suggested kind:** decision

## F-voc-02
- **Title:** WGI/WB conflation in Appendix sample record
- **Severity:** med
- **Source anchor:** spec_v1.md § Appendix: Sample Data Patterns (lines 1598-1610) and § Data Transformations (line 380)
- **Files affected (read-only):** `.claude/spec_v1.md`
- **Files to touch (potential fix):** `.claude/spec_v1.md`
- **Evidence:**
  - Line 1598: "### Sample WGI Record"
  - Line 1600: "**From silver_WB:**" with fields `country_code`, `country_name`, `indicator_code`, `indicator_name`, `topic`, `score: 85.3`, "year 2020 filtered"
  - § Data Transformations line 380: "*(Supersedes the retired `bronze_WB_ESGCSV` + `bronze_WB_ESGSeries` → `silver_WB` CSV/dataflow lineage — no live artifact produces those tables.)*"
  - § Data Sources #3 line 274: "`Value` (DOUBLE) - Governance score for that country/indicator/year" (on the −2.5…+2.5 estimate scale per line 424, not 0-100)
- **What:** The Appendix heading says "Sample WGI Record" but the source label says "From silver_WB" and the fields shown (`topic`, `score: 85.3` on a 0-100 scale, `country_code`, `year 2020 filtered`) match the retired `silver_WB` (World Bank ESG) lineage, not the current `silver_wgi` schema (which uses `country_iso3`, `country_name`, `indicator_name`, `Year`, `Value` on −2.5…+2.5 with no `topic` field).
- **Why:** "WGI" (current governance indicators) and "WB" (retired World Bank ESG) are distinct concepts that share World Bank provenance; the Appendix uses the terms as synonyms, contradicting § Data Transformations' explicit retirement note for `silver_WB` and presenting retired-lineage fields under a "WGI" heading.
- **Suggested fix:** Spec amendment via /iterate to either relabel the section "Sample WB Record (retired lineage)" or replace the sample with fields from the current `silver_wgi` schema per § Data Sources #3 and § Data Transformations.
- **Suggested kind:** decision