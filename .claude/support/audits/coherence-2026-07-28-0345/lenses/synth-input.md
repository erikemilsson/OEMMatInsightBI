# Lens: superseded-decisions

Findings: 0

(No findings on this axis. All 5 decision records (DEC-001 through DEC-005) carry `status: approved` with no `superseded_by` / `superseded_date` frontmatter. There are no superseded or partially_superseded decisions in the project, so no stale superseded language can persist in the active spec.)
# Lens: feedback-decay

Findings: 0

(No findings on this axis. `.claude/support/feedback/feedback.md` contains zero `## FB-NNN` entries — the inbox is empty ("Use `/feedback [text]` to capture an idea"). No feedback items exist to decay.)
# Lens: retired-features

Findings: 0

(No findings on this axis. The `.claude/support/retired/` directory exists but contains no `<feature-slug>/manifest.json` entries — no features have been retired via the retirement workflow, so there are no missing spec retirement markers to surface.)
# Lens: acceptance-reconciliation

Findings: 0

(No findings on this axis — the lens does not apply. The active spec `spec_v1.md` contains no inline `- [ ]` / `- [x]` acceptance-checkbox markup (grep for `^\s*- \[[ x]\]` returns 0). Per the lens contract: "If the spec has no inline acceptance checkboxes, return Findings: 0 — there is nothing to reconcile." This project relies on the dashboard's `### Acceptance Criteria` (verification-result.json `criteria[]`) as the live status surface, per DEC-022, so there is no inline-box staleness to reconcile. Note: phase-verification.json shows only one `phase_complete: true` row — "phase 2 (Silver/Gold transforms + DQ gate)" with 1/1 task — but with no inline boxes this is moot.)
# Lens: vocab-drift

Findings: 2

## F-voc-01
- **Title:** WGI items drift across "governance dimensions" / "WGI dimensions" / "indicators"
- **Severity:** med
- **Source anchor:** spec_v1.md § Business Logic & Calculations (line 1302) — pick one canonical term; § Data Architecture (lines 256, 280), § Data Transformations (line 376), § Data Quality & Validation (line 1101) all drift
- **Files affected (read-only):** .claude/spec_v1.md
- **Files to touch (potential fix):** .claude/spec_v1.md
- **Evidence:**
  - § Data Architecture line 256: "Country-level governance quality metrics across **6 governance dimensions**"
  - § Data Architecture line 280: "Six **indicators** are ingested, not five. Coverage rules must test against six."
  - § Data Transformations line 376: "Coverage rules test against six **indicators** (not five)"
  - § Data Quality & Validation line 1101: "6 **governance dimensions**, years 1996-2023 (annual from 2002; biennial before)"
  - § Business Logic line 1302: "the rescaled inverse of the mean of all six **WGI dimensions**"
- **What:** The same six WGI items are referred to as "governance dimensions", "WGI dimensions", and "indicators" across four sections, with no cross-reference establishing them as the same concept.
- **Why:** "Indicators" is overloaded — EPI also has indicators (30+ of them, line 216/552) — so using "indicators" unqualified for WGI is ambiguous, and a reader cross-referencing § Data Architecture § 3 with § Business Logic has to infer that "governance dimensions" = "WGI dimensions" = "indicators".
- **Suggested fix:** Spec amendment via /iterate to standardize on "WGI dimensions" (per § Business Logic & Calculations line 1302) across § Data Architecture (lines 256, 280), § Data Transformations (line 376), and § Data Quality & Validation (line 1101); reserve "indicators" for EPI, or qualify as "WGI indicators" when used.
- **Suggested kind:** decision

## F-voc-02
- **Title:** "fact table" count: 3 vs 4 across sections
- **Severity:** low
- **Source anchor:** spec_v1.md § Semantic Model & Reporting (line 708) — the "Fact Tables" list includes `gold_supply_risk`; § Current State Assessment (line 844) excludes it
- **Files affected (read-only):** .claude/spec_v1.md
- **Files to touch (potential fix):** .claude/spec_v1.md
- **Evidence:**
  - § Semantic Model line 708-716: lists **4 items under "Fact Tables:"** — `fact_epi_score`, `fact_procurement`, `fact_supply_share`, and `gold_supply_risk` (the last named `gold_*`, not `fact_*`)
  - § Current State line 844: "**3 fact tables created** (procurement, supply_share, epi_score)"
  - § Business Logic line 1306: "Computed over two supply mixes and exposed in `gold_supply_risk`" — describes it as a derived/computed table, not a primary fact
- **What:** The term "fact table" includes `gold_supply_risk` in § Semantic Model but excludes it in § Current State, where only the three `fact_*`-prefixed tables are counted.
- **Why:** A reader checking phase-1 acceptance ("3 fact tables created") against the semantic model's fact-table list sees 4 and cannot tell whether `gold_supply_risk` is a primary fact table or a derived exposure table without reading § Business Logic.
- **Suggested fix:** Spec amendment via /iterate to standardize on "fact table" — either update § Current State line 844 to "4 fact tables (procurement, supply_share, epi_score, supply_risk)" matching § Semantic Model, or relabel `gold_supply_risk` in § Semantic Model as a "derived table" / "calculated table" distinct from primary fact tables.
- **Suggested kind:** decision
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
# Lens: friction-register

Findings: 0

(No findings on this axis. Only 1 open friction entry exists — FR-028 (path_drift, captured 2026-07-26, 2 days old), below the 3-entry clustering threshold and not stale. FR-028 is a code-level dangling table reference (`oem_lh.silver_WB` at `fabric/data_quality_analysis.Notebook/notebook-content.py:421`), not a spec/vision/decision structural contradiction, so it does not rise to the high-severity-single bar — it is routine path_drift evidence that the path-drift lens handles. The entry carries no `owned_by_task` field; `captured_in.task` is task-033 provenance only, and task-033 is Finished, so the register entry is unowned and available for the path-drift lens or a future task to consume.)
