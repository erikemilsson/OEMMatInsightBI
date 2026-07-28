===== superseded-decisions.md =====
# Lens: superseded-decisions

Findings: 0

(No findings on this axis.)

No decisions in `.claude/support/decisions/` carry `status: superseded` or `status: partially_superseded`. All five decision records (DEC-001 through DEC-005) are `status: approved` per their frontmatter and per the extracted `decisions.json`. The only "supersede" mention in the corpus is an in-body prerequisite-chain note inside `decision-001-sr-gold-model.md` line 171 ("supersedes the two bullets above for B specifically") — that is a local prose clarification, not a decision-level supersession, so it does not trigger this lens. With zero superseded decisions, there are no spec-vs-decision drift candidates to report.
===== vocab-drift.md =====
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
===== path-drift.md =====
# Lens: path-drift

Findings: 2

## F-pat-01
- **Title:** Stale template-era .claude paths in spec header
- **Severity:** low
- **Source anchor:** `.claude/spec_v1.md § Project Overview` (lines 18, 20, 22 — the "Instructions for Claude Code" preamble)
- **Files affected (read-only):** `.claude/spec_v1.md`
- **Files to touch (potential fix):** `.claude/spec_v1.md` — synthesizer will classify as `kind: decision`
- **Evidence:**
  ```
  > -   Context documentation (`.claude/context/`)
  > -   Reference files (`.claude/reference/`)
  > -   Standards and conventions (`.claude/context/standards/`)
  ```
- **What:** The spec's "Instructions for Claude Code" preamble references three paths that do not exist on disk (`.claude/context/`, `.claude/reference/`, `.claude/context/standards/`).
- **Why:** The actual canonical locations are `.claude/support/documents/` (context docs), `.claude/support/reference/` (reference docs), and `.claude/support/documents/standards/` (standards) — verified by `ls .claude/support/documents/` and `ls .claude/support/reference/`. The `.claude/context/` directory does not exist at all. These stale paths are template-era boilerplate that was never updated when the project adopted the `.claude/support/` layout (documented in root `CLAUDE.md` and `.claude/CLAUDE.md`).
- **Suggested fix:** Spec amendment via `/iterate`: replace `.claude/context/` with `.claude/support/documents/`, `.claude/reference/` with `.claude/support/reference/`, and `.claude/context/standards/` with `.claude/support/documents/standards/` in § Project Overview (lines 18, 20, 22).
- **Suggested kind:** decision

## F-pat-02
- **Title:** CI/CD paths described as existing, never created
- **Severity:** med
- **Source anchor:** `.claude/spec_v1.md § Infrastructure & Deployment` (lines 1197, 1200, 1205, 1210)
- **Files affected (read-only):** `.claude/spec_v1.md`
- **Files to touch (potential fix):** `.claude/spec_v1.md` — synthesizer will classify as `kind: decision`
- **Evidence:**
  ```
  -   **Parameterization:** `parameter.yml` for environment-specific config (lakehouse IDs, connection strings)
  ...
  **GitHub Actions Workflow:** `.github/workflows/fabric-deploy.yml`
  ...
  -   Environment-specific find-and-replace via `parameter.yml`
  ...
  -   Notebook-to-Lakehouse bindings don't auto-update across environments — `parameter.yml` handles this
  ```
- **What:** The spec's "CI/CD Deployment" subsection describes `parameter.yml` and `.github/workflows/fabric-deploy.yml` as if they currently exist, but neither file exists on disk — `find` returns no matches and `.github/workflows/` contains only `test.yml` (an unrelated "Tests & Quality Checks" workflow).
- **Why:** The spec is internally inconsistent: § Next Steps & Priorities (line 1536) marks "Phase 4 | CI/CD Deployment | Planned", but § Infrastructure & Deployment describes the same CI/CD artifacts in the present tense with specific file paths. A reader following the spec would expect on-disk files that were never created. This is path-drift because the spec mentions concrete paths (`parameter.yml`, `.github/workflows/fabric-deploy.yml`) that have no on-disk counterpart and no renamed-equivalent nearby (the only sibling in `.github/workflows/` is `test.yml`, which has a different function entirely). No open friction-register entry covers this — FR-028 is a code-path drift (`oem_lh.silver_WGI` in `data_quality_analysis.Notebook`), not a spec-path drift.
- **Suggested fix:** Spec amendment via `/iterate` in § Infrastructure & Deployment: either (a) reframe the CI/CD Deployment subsection as "Planned approach" with explicit "not yet implemented" markers on `parameter.yml` and `.github/workflows/fabric-deploy.yml`, or (b) move the file-path specifics into the Phase 4 deliverables list (§ Next Steps & Priorities line 1545 already lists `parameter.yml` correctly as a future deliverable) and keep only the approach description in Infrastructure & Deployment.
- **Suggested kind:** decision
===== feedback-decay.md =====
# Lens: feedback-decay

Findings: 1

## F-fee-01
- **Title:** FB-007 new and untriaged 44 days
- **Severity:** med
- **Source anchor:** .claude/support/feedback/feedback.md (FB-007)
- **Files affected (read-only):** .claude/support/feedback/feedback.md, .claude/support/audits/coherence-2026-07-28-0308/inputs/feedback-status.json
- **Files to touch (potential fix):** .claude/support/feedback/feedback.md
- **Evidence:** `{"id":"FB-007","status":"new","captured":"2026-06-14","title":": dashboard-render.py mermaid edge sources skip mermaid_id() sanitization","age_days":44}` — status is `new`, captured 2026-06-14, today 2026-07-28 (44 days).
- **What:** FB-007 has sat in `new` status for 44 days without a status change, past the 30-day decay threshold.
- **Why:** Untriaged feedback accumulates; a 30+ day `new` entry signals the feedback loop is not draining.
- **Suggested fix:** Triage FB-007 via /feedback review (see feedback.md § FB-007).
- **Suggested kind:** bundle-eligible
===== retired-features.md =====
# Lens: retired-features

Findings: 0

(No findings on this axis. No retired-feature manifests exist in this project.)
===== friction-register.md =====
# Lens: friction-register

Findings: 4

Four open entries; no 3+ cluster sharing both `kind` and overlapping `source_anchor` (two `design_contradiction` entries FR-025 and FR-029 sit in unrelated files — one in a notebook, the other in `fabric_workspace.md` vs `expressions.tmdl`). No entry is >60 days old (max age 5 days). Each entry describes a structural problem, so all four pass through as single-instance findings.

## F-fri-01
- **Title:** Bronze WGI schema contradiction (DQ vs bronze-to-silver)
- **Severity:** high
- **Source anchor:** `fabric/data_quality_checks.Notebook/notebook-content.py` § schema_checks / completeness_checks (oem_lh.bronze_WGI)
- **Files affected (read-only):** `fabric/data_quality_checks.Notebook/notebook-content.py`, `fabric/bronze-to-silver.Notebook/notebook-content.py`
- **Files to touch (potential fix):** `fabric/data_quality_checks.Notebook/notebook-content.py` (absorb DQ contract update per task-035)
- **Evidence:** "bronze-to-silver HARD-REQUIRES ['Indicator Code','Year','Value']; data_quality_checks.Notebook asserts schema {'Country Name','Country Code','Series Name','Percentile Rank 2023'} with required fields ['Country Name','Country Code','Series Name']"
- **What:** Two notebooks hold contradictory schema expectations for the same `bronze_WGI` table.
- **Why:** The DQ schema check is not in BLOCKING_CHECKS, so the mismatch stays latent until bronze-to-silver succeeds and the DQ activity runs, then logs an advisory fail.
- **Suggested fix:** Resolve FR-025 by having task-035 absorb the DQ contract update to match bronze-to-silver's `['Indicator Code','Year','Value']` shape.
- **Suggested kind:** fix-eligible

## F-fri-02
- **Title:** Spec § Data Sources #2 contradicts live pipeline (EPI ingestion)
- **Severity:** high
- **Source anchor:** `spec_v1.md` § Data Sources #2 (line 208; checkbox at line 822)
- **Files affected (read-only):** `.claude/spec_v1.md`
- **Files to touch (potential fix):** `.claude/spec_v1.md` (line 208 + checkbox at line 822, via `/iterate`)
- **Evidence:** "spec_v1 § Data Sources #2 line 208 states the EPI ingestion method is EPI_file2table.Dataflow while line 238 of the same section and the live pipeline both use bronze_ingest_epi.Notebook. Matching stale checkbox at line 822."
- **What:** The spec names a Dataflow as the EPI ingestion method while the spec's own line 238 and the live pipeline both use a notebook.
- **Why:** Spec drift between two adjacent lines plus a stale acceptance checkbox misleads any reader or agent using the spec as the source of truth.
- **Suggested fix:** Resolve FR-027 via `/iterate` to align line 208 and the line 822 checkbox with the notebook ingestion method actually used.
- **Suggested kind:** decision

## F-fri-03
- **Title:** DQ analysis notebook references retired World Bank table
- **Severity:** med
- **Source anchor:** `fabric/data_quality_analysis.Notebook/notebook-content.py:421`
- **Files affected (read-only):** `fabric/data_quality_analysis.Notebook/notebook-content.py`
- **Files to touch (potential fix):** `fabric/data_quality_analysis.Notebook/notebook-content.py` (line 421)
- **Evidence:** "fabric/data_quality_analysis.Notebook line 421 still reads oem_lh.silver_WB, a table the retired World Bank ESG lineage produced and which no longer exists."
- **What:** A latent notebook still reads a table dropped when the World Bank ESG lineage retired.
- **Why:** Not a pipeline activity so it fails only if the notebook is run manually — a stale reference waiting to bite.
- **Suggested fix:** Resolve FR-028 by removing or repointing the `silver_WB` read at line 421, or retire the notebook section if the analysis is obsolete.
- **Suggested kind:** fix-eligible

## F-fri-04
- **Title:** Semantic model doc claims warehouse; TMDL declares DirectLake lakehouse
- **Severity:** high
- **Source anchor:** `fabric_workspace.md` § Semantic Model vs `fabric/OEMInsightBI_v2.SemanticModel/definition/expressions.tmdl:1`
- **Files affected (read-only):** `fabric_workspace.md`, `fabric/OEMInsightBI_v2.SemanticModel/definition/expressions.tmdl`
- **Files to touch (potential fix):** `fabric_workspace.md` § Semantic Model
- **Evidence:** "fabric_workspace.md described the semantic model as connected to the oem_wh warehouse while expressions.tmdl declares DirectLake against the oem_lh lakehouse. The mismatch is what made the never-populated warehouse look load-bearing across several docs."
- **What:** Documentation says warehouse; the actual TMDL connection is DirectLake to the lakehouse — the warehouse was never populated and is not load-bearing.
- **Why:** The doc/contract mismatch propagated into multiple docs treating a dead warehouse as a real dependency.
- **Suggested fix:** Resolve FR-029 by correcting `fabric_workspace.md` § Semantic Model to reflect the DirectLake-against-`oem_lh` connection declared in `expressions.tmdl`.
- **Suggested kind:** fix-eligible
===== acceptance-reconciliation.md =====
# Lens: acceptance-reconciliation

Findings: 0

(No findings on this axis.)

**Notes:** The spec renders 77 inline checkboxes, but they are a thematic project-status inventory (`### What's Implemented ✅` / `### What's Incomplete/Needs Work ⚠️` / `### Data Quality Checks Implemented ✅` / `### Data Quality Checks Needed` / `### Current Performance Status` / `### Current Testing Status`), not phase-scoped acceptance criteria. The spec's actual phase acceptance criteria are prose in the `### Phase Structure` table (lines 1531-1536), not inline boxes.

The only `phase_complete: true` phase is phase 2 single-task "Silver/Gold transforms + DQ gate" (task-042). Its scope items appear in `### What's Implemented ✅` at lines 842-860 and are all ticked `[x]` — correct, not stale, not over-claim. The 17 unticked `[ ]` boxes map to work in incomplete phases (1, 2 main, 3, 4-planned) — legitimate untick. verification-result.json is ABSENT, so no authoritative tier to match against.

The over-claim pattern (ticked `[x]` for an incomplete phase) would require confident box-to-phase mapping, but the boxes are thematic, not phase-tagged — asserting divergence would be a guess, which the lens method prohibits.
