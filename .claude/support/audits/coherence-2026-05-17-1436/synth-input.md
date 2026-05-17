# Lens: feedback-decay

Findings: 0

(No findings on this axis — feedback.md has no captured entries yet.)
# Lens: friction-register

Findings: 0

(No findings on this axis — `.claude/support/friction.jsonl` does not exist; no open friction entries to cluster.)
# Lens: path-drift

Findings: 4

## F-pat-01
- **Title:** Silver cleaning notebook renamed
- **Severity:** high
- **Source anchor:** spec_v1.md § Data Transformations (lines 334, 654, 856, 1002) + § Naming Conventions (line 1002)
- **Files affected (read-only):** .claude/spec_v1.md, fabric/bronze-to-silver.Notebook/, fabric/orchestrator_pipeline_bronze_to_gold.DataPipeline/pipeline-content.json
- **Files to touch (potential fix):** .claude/spec_v1.md
- **Evidence:** Spec line 334: `**Notebook:** \`clean_columnsAndHeaders.Notebook\``; spec line 654: `Notebook: \`clean_columnsAndHeaders.Notebook\``; spec line 856: `[x] Cleaning notebook (\`clean_columnsAndHeaders.Notebook\`)`. Disk reality: `ls fabric/` shows `bronze-to-silver.Notebook` exists and `clean_columnsAndHeaders.Notebook` does not. The pipeline JSON (`pipeline-content.json`) names the activity `"bronze-to-silver data cleaning"`, and the notebook body declares itself `nb_silver_standardize`. No `clean_columnsAndHeaders*` artifact remains anywhere in the repo (including archive).
- **What:** The bronze→silver cleaning notebook has been renamed from `clean_columnsAndHeaders.Notebook` to `bronze-to-silver.Notebook`, but the spec still references the old name in 4 places (transformation header, orchestration step, current-state checklist, naming-conventions example).
- **Why:** Readers searching the repo for `clean_columnsAndHeaders.Notebook` will not find it; the spec's "Current State Assessment" misrepresents what is actually implemented.
- **Suggested fix:** Replace all 4 occurrences of `clean_columnsAndHeaders.Notebook` with `bronze-to-silver.Notebook` (and update the naming-convention example accordingly, since the new name is no longer of the form `[purpose]_[source]to[target]`).
- **Suggested kind:** decision

## F-pat-02
- **Title:** Semantic model name diverged from disk
- **Severity:** high
- **Source anchor:** spec_v1.md § Technical Architecture (line 82) + § Semantic Model & Reporting (line 722)
- **Files affected (read-only):** .claude/spec_v1.md, fabric/OEMInsightBI_v2.SemanticModel/, fabric/archive/semantic_model_oeminsightbi.SemanticModel/
- **Files to touch (potential fix):** .claude/spec_v1.md
- **Evidence:** Spec line 82: `**Semantic Model:** \`semantic_model_oeminsightbi\` (Power BI data model)`; spec line 722: `### Semantic Model: \`semantic_model_oeminsightbi\``. Disk reality: `ls -d fabric/*.SemanticModel` returns only `fabric/OEMInsightBI_v2.SemanticModel`. The old `semantic_model_oeminsightbi.SemanticModel` exists only under `fabric/archive/`, i.e., it was deliberately superseded.
- **What:** The active semantic model on disk is `OEMInsightBI_v2.SemanticModel`, while the spec still names it `semantic_model_oeminsightbi`.
- **Why:** The spec's "single source of truth" claim is violated; anyone navigating to the named artifact lands in an archived definition rather than the live model.
- **Suggested fix:** Update both spec mentions to `OEMInsightBI_v2.SemanticModel` (or `OEMInsightBI_v2` when used as a bare model name).
- **Suggested kind:** decision

## F-pat-03
- **Title:** Power BI report name stale (report → report2)
- **Severity:** med
- **Source anchor:** spec_v1.md § Semantic Model & Reporting (line 822) + § Dependencies & External Systems (line 1429)
- **Files affected (read-only):** .claude/spec_v1.md, fabric/report2.Report/, fabric/archive/report.Report/
- **Files to touch (potential fix):** .claude/spec_v1.md
- **Evidence:** Spec line 822: `### Power BI Report: \`report.Report\``; spec line 1429: `Report ID: report.Report (in /fabric folder)`. Disk reality: `fabric/report.Report` does not exist; `fabric/report2.Report` exists; the original `report.Report` lives under `fabric/archive/`.
- **What:** The active Power BI report has been renamed `report2.Report`, but the spec still references `report.Report` as the live artifact location.
- **Why:** Spec readers and any deployment automation keying on the spec name will target an archived artifact.
- **Suggested fix:** Update both occurrences of `report.Report` to `report2.Report` (and reflect this in the report's heading on line 822).
- **Suggested kind:** decision

## F-pat-04
- **Title:** Azure SQL setup scripts location stale (azure/ → secure/)
- **Severity:** med
- **Source anchor:** spec_v1.md § Data Architecture / Azure SQL Database (lines 112, 156–160) + § Security & Access (line 1225)
- **Files affected (read-only):** .claude/spec_v1.md, secure/user_creation.sql, secure/grant_permissions.sql, .gitignore
- **Files to touch (potential fix):** .claude/spec_v1.md
- **Evidence:** Spec line 112: `Authentication method: SQL authentication (see \`azure/user_creation.sql\`)`; spec line 156: `**Setup Scripts:** (in \`/azure\` folder)` followed by `user_creation.sql` and `grant_permissions.sql`; spec line 1225: `(see \`azure/user_creation.sql\`, \`azure/grant_permissions.sql\`)`. Disk reality: `ls azure/` contains only `procurement.sql` and `supplier_info.sql`. The two credential-bearing scripts live at `secure/user_creation.sql` and `secure/grant_permissions.sql`, and `.gitignore` line 32 lists `secure/` (intentionally untracked).
- **What:** `user_creation.sql` and `grant_permissions.sql` were moved out of the tracked `azure/` folder into the gitignored `secure/` folder, but the spec still locates them under `azure/`.
- **Why:** A reader pulling the repo will not find these files at the documented path; the move was a deliberate secret-handling decision that the spec should reflect.
- **Suggested fix:** Update the three references to point to `secure/user_creation.sql` and `secure/grant_permissions.sql`, and add a note that `secure/` is gitignored (credentials kept locally per project convention).
- **Suggested kind:** decision
# Lens: retired-features

Findings: 0

(No findings on this axis — no retired-feature manifests in `.claude/support/retired/`.)
# Lens: superseded-decisions

Findings: 0

(No findings on this axis — no decision records exist yet.)
# Lens: vocab-drift

Findings: 2

## F-voc-01
- **Title:** "DQ" vs "data quality" inconsistent across sections
- **Severity:** med
- **Source anchor:** spec_v1.md § Data Quality & Validation
- **Files affected (read-only):** .claude/spec_v1.md (§ Data Quality & Validation, § Development Workflow, § Current State Assessment, § Next Steps & Priorities, § Infrastructure & Deployment)
- **Files to touch (potential fix):** .claude/spec_v1.md
- **Evidence:**
  - § Current State Assessment (line 934): "Comprehensive data quality checks in pipeline (task-007)"
  - § Next Steps & Priorities (line 1499): "DQ checks run in pipeline, external data ingestion scripted"
  - § Development Workflow (lines 979-983): "Run data quality checks" / "Export schemas/DQ reports" / "Pull latest (includes DQ reports)"
  - § Data Quality & Validation (line 1088): "**Current DQ Implementation:**" (heading) while surrounding section (lines 1028-1056) uses "Data Quality" headings throughout
- **What:** The same concept (data-quality checks, reports, and current state) is referred to as "data quality" in some sections and "DQ" in others, without a single point of abbreviation introduction.
- **Why:** A reader scanning the Phase 2 acceptance criteria sees "DQ checks run in pipeline" and must mentally bridge to "data quality checks" used elsewhere; the implementor of task-007 may also be unsure whether the two terms denote the same scope.
- **Suggested fix:** Canonicalize as "data quality" in prose; either drop "DQ" entirely or introduce it explicitly once (e.g., "data quality (DQ)") in § Data Quality & Validation, then use consistently. Update at least lines 980, 983, 1088, and 1499.
- **Suggested kind:** decision

## F-voc-02
- **Title:** "quality observability tables" vs "data quality observability tables"
- **Severity:** low
- **Source anchor:** spec_v1.md § Current State Assessment
- **Files affected (read-only):** .claude/spec_v1.md (§ Current State Assessment, § Semantic Model & Reporting cross-refs in Current State Assessment)
- **Files to touch (potential fix):** .claude/spec_v1.md
- **Evidence:**
  - § Current State Assessment (line 884): "[x] Data quality observability tables (gold_quality_history, gold_gap_registry, gold_quality_snapshot)"
  - § Current State Assessment (line 898): "[x] Quality observability tables added to semantic model"
  - § Current State Assessment (line 947): "Previously identified gap (data quality visibility) addressed via quality observability tables in tasks 018/019."
- **What:** The same feature is named "Data quality observability tables" in the Gold Layer subsection and "Quality observability tables" two subsections later (Semantic Model, Known Issues/Technical Debt), within a single `##` section.
- **Why:** Minor — same section, close together — but a downstream reader looking for "data quality observability" via search may miss the shorter variant when scoping work or building the dashboard rollup.
- **Suggested fix:** Pick one canonical form (recommend "data quality observability tables", matching the supporting document `data_quality_architecture.md`) and use it in all three locations within § Current State Assessment.
- **Suggested kind:** decision
