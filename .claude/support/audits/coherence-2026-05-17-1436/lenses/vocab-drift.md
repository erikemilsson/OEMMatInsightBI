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
