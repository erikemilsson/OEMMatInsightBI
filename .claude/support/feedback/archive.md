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

---

## FB-007: dashboard-render.py mermaid edge sources skip mermaid_id() sanitization

**Status:** obsolete (superseded upstream)
**Captured:** 2026-06-14
**Archived:** 2026-07-28 — superseded by DEC-024 (template v5.0.0, 2026-06-24), which deleted the mermaid renderer entirely; the bug cannot exist at template 5.x. This project synced to 5.4.0 on 2026-07-22; the dashboard is now generated HTML with an inline-SVG dependency graph (no mermaid), so the hand-workaround is no longer needed and a `/work` regen no longer reintroduces broken edges. Template-side triage: `harvest-2026-07-19-triage.md` ("superseded — DEC-024/v5.0.0 deleted the mermaid renderer; the bug can't exist at 5.x; action: sync to 5.x; archive the bridge"). Note: the template's own FB-007 is an unrelated item (spec-edit guardrail, DEC-016) — this downstream item never landed as a template FB; the mermaid issue was tracked only via the interaction-logs bridge (`interaction-logs/processed/OEMMatInsightBI-feedback-FB-007-2026-06-14.json`).

In `render_mermaid()`, `resolve_dep()` returned the raw `f"T{dep}"` without passing it through `mermaid_id()`, so task-dependency edge *sources* kept hyphens while node definitions and edge *targets* were underscore-sanitized — every dependency edge pointed from a phantom node and the Project Overview graph rendered disconnected. The 70-test script suite passed despite the bug. Code path no longer exists.

---

## FB-008: dashboard-render.py --html writes to stdout; docs omit the redirect step

**Status:** addressed (template v5.4.1)
**Captured:** 2026-07-22
**Archived:** 2026-07-28 — addressed upstream in template v5.4.1 (2026-07-28). The reference doc `dashboard-regeneration.md § 3 "Generate Dashboard"` already stated the redirect ("run `dashboard-render.py --html ...` and `Write` its stdout to `.claude/dashboard.html`"); v5.4.1 sharpened the `rules/dashboard.md § Regeneration Strategy` summary to the explicit `python3 .claude/scripts/dashboard-render.py --html > .claude/dashboard.html` form with a note on the silent-stale failure mode (omitting the redirect leaves `dashboard.html` stale with no error). The suggested `--write`/`-o` flag was not added — the explicit-redirect doc clarification closes the gap at zero script change. Template-side bridge file moved from `interaction-logs/inbox/` to `processed/` (`OEMMatInsightBI-feedback-FB-008-2026-07-22.json`). Note: the template's own FB-008 is an unrelated item ("/work fails to restore context at session boundaries"); this downstream item was tracked only via the interaction-logs bridge.

`dashboard-render.py --html` renders the full dashboard HTML to **stdout** (`print(render_full_html(...))`) — the on-disk `dashboard.html` only updates when the caller redirects. Observed here during `/health-check` 2026-07-22: a regen piped to `tail -15` for inspection left `dashboard.html` stale until a second pass with an explicit `> .claude/dashboard.html` redirect. The `--task-hash` mode is correctly stdout-only, so the asymmetry was easy to misread.
