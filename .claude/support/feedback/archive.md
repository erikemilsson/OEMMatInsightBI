# Archived Feedback

Items triaged as not relevant during `/feedback review`, or promoted and applied via `/iterate`. Preserved for reference.

---

## FB-001: Spec references obsolete `clean_columnsAndHeaders.Notebook` (renamed to `bronze-to-silver`)

**Status:** promoted
**Captured:** 2026-05-17
**Promoted:** 2026-05-17 — Incorporated into spec v1 §§ Data Transformations, Pipeline Stage 2, Current State Assessment, Naming Conventions
**Source:** audit-coherence-2026-05-17-1436 C-01

Spec referenced `clean_columnsAndHeaders.Notebook` in four places; on-disk the cleaning notebook is `bronze-to-silver.Notebook` (no archive entry of the old name). All four references swapped. The deeper `[purpose]_[source]to[target].Notebook` naming-convention rule on line 1000 was kept unchanged — line 1004's existing caveat ("Inconsistency: Uses both underscores and hyphens") carries the drift acknowledgement.

Side-effect: `task-012_3.json` `files_affected` array also updated to swap the stale notebook path.

---

## FB-002: Spec lists `semantic_model_oeminsightbi`; active model is `OEMInsightBI_v2`

**Status:** promoted
**Captured:** 2026-05-17
**Promoted:** 2026-05-17 — Incorporated into spec v1 §§ Technical Architecture, Semantic Model & Reporting
**Source:** audit-coherence-2026-05-17-1436 C-02

Spec updated to name the active semantic model `OEMInsightBI_v2`. Line 82 also notes the old name is archived in `fabric/archive/` for historical traceability.

---

## FB-003: Spec names `report.Report`; active artifact is `report2.Report`

**Status:** promoted
**Captured:** 2026-05-17
**Promoted:** 2026-05-17 — Incorporated into spec v1 §§ Semantic Model & Reporting, Dependencies & External Systems
**Source:** audit-coherence-2026-05-17-1436 C-03

Both references updated to `report2.Report`. Line 1429 also notes the old name is archived in `fabric/archive/`.

---

## FB-004: Spec locates Azure SQL setup scripts in `azure/`; actual path is `secure/` (gitignored)

**Status:** promoted
**Captured:** 2026-05-17
**Promoted:** 2026-05-17 — Incorporated into spec v1 §§ Data Architecture / Azure SQL Database, Security & Access
**Source:** audit-coherence-2026-05-17-1436 C-04

`user_creation.sql` and `grant_permissions.sql` references moved to `secure/`. The Setup Scripts list was split into "Credential scripts (in `/secure` — gitignored)" and "Schema scripts (in `/azure` — tracked)", because `procurement.sql` and `supplier_info.sql` remain under `azure/` (schema-only, no secrets). Resolved as `[NEEDS APPROVAL] D2` during /iterate.

---

## FB-005: Inconsistent "DQ" vs "data quality" terminology across spec sections

**Status:** promoted
**Captured:** 2026-05-17
**Promoted:** 2026-05-17 — Incorporated into spec v1 §§ Development Workflow, Data Quality & Validation, Implementation Status
**Source:** audit-coherence-2026-05-17-1436 C-05

Canonicalized on "data quality" (dropping "DQ" entirely) across four lines: 980, 983, 1088, 1499. Matches the long-form usage already present 17+ times in the spec. Resolved as `[NEEDS APPROVAL] D3` during /iterate.

---

## FB-006: "Quality observability tables" vs "data quality observability tables" within § Current State Assessment

**Status:** promoted
**Captured:** 2026-05-17
**Promoted:** 2026-05-17 — Incorporated into spec v1 § Current State Assessment
**Source:** audit-coherence-2026-05-17-1436 C-06

Line 898 updated to "Data quality observability tables added to semantic model" to match line 884. Line 947 deliberately left untouched — the shorter form flows naturally with the preceding "data quality visibility" phrase in the same sentence. Resolved as `[NEEDS APPROVAL] D4` during /iterate.
