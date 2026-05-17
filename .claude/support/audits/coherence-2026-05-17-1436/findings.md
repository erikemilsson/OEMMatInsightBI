# Coherence Audit — 2026-05-17 — OEMMatInsightBI

`.claude/support/audits/coherence-2026-05-17-1436/` · 6 lenses · 6 raw findings → 6 after dedupe → 6 surfaced (0 routed to in-flight tasks)

All six findings touch `.claude/spec_v1.md` — per the HARD RULE (spec / decision / vision read-only outside `/iterate`), all classify as `kind: decision`. Route via `/iterate`.

## Top findings

### C-01 · Spec references obsolete `clean_columnsAndHeaders.Notebook` (renamed to `bronze-to-silver`)
- **Kind:** decision · **Severity:** high · **Lenses:** path-drift
- **Source anchor:** spec_v1.md § Data Transformations (lines 334, 654), § Current State Assessment (line 856), § Naming Conventions (line 1002)
- **Files to touch:** `.claude/spec_v1.md`
- **Evidence:**
  - Spec line 334: `**Notebook:** \`clean_columnsAndHeaders.Notebook\``
  - Spec line 654: `Notebook: \`clean_columnsAndHeaders.Notebook\``
  - Spec line 856: `[x] Cleaning notebook (\`clean_columnsAndHeaders.Notebook\`)`
  - Disk: `fabric/bronze-to-silver.Notebook/` exists; `fabric/clean_columnsAndHeaders.Notebook/` does not (no archive entry).
- **Why:** Readers searching the repo for `clean_columnsAndHeaders.Notebook` will not find it. Worse, task-012_3 (Pending) still lists the stale path in `files_affected` — drift has propagated into task data.
- **Suggested fix:** `/iterate` to replace all four occurrences of `clean_columnsAndHeaders.Notebook` with `bronze-to-silver.Notebook` and update the naming-convention example accordingly (new name no longer fits the `[purpose]_[source]to[target]` template).
- **Action:** [Promote to feedback]
- **`iterate_routing`:** `{ "reason": "spec/decision/vision file modification — read-only outside /iterate" }`

### C-02 · Spec lists `semantic_model_oeminsightbi`; active model is `OEMInsightBI_v2`
- **Kind:** decision · **Severity:** high · **Lenses:** path-drift
- **Source anchor:** spec_v1.md § Technical Architecture (line 82), § Semantic Model & Reporting (line 722)
- **Files to touch:** `.claude/spec_v1.md`
- **Evidence:**
  - Spec line 82: `**Semantic Model:** \`semantic_model_oeminsightbi\` (Power BI data model)`
  - Spec line 722: `### Semantic Model: \`semantic_model_oeminsightbi\``
  - Disk: `ls -d fabric/*.SemanticModel` returns only `fabric/OEMInsightBI_v2.SemanticModel`. The old model lives under `fabric/archive/semantic_model_oeminsightbi.SemanticModel/` (deliberately superseded).
- **Why:** Spec's "single source of truth" claim is violated; anyone following the named artifact lands in an archived definition rather than the live model.
- **Suggested fix:** `/iterate` to update both spec mentions to `OEMInsightBI_v2.SemanticModel` (or `OEMInsightBI_v2` when used as a bare model name).
- **Action:** [Promote to feedback]
- **`iterate_routing`:** `{ "reason": "spec/decision/vision file modification — read-only outside /iterate" }`

### C-03 · Spec names `report.Report`; active artifact is `report2.Report`
- **Kind:** decision · **Severity:** med · **Lenses:** path-drift
- **Source anchor:** spec_v1.md § Semantic Model & Reporting (line 822), § Dependencies & External Systems (line 1429)
- **Files to touch:** `.claude/spec_v1.md`
- **Evidence:**
  - Spec line 822: `### Power BI Report: \`report.Report\``
  - Spec line 1429: `Report ID: report.Report (in /fabric folder)`
  - Disk: `fabric/report.Report` does not exist; `fabric/report2.Report` does; original under `fabric/archive/report.Report/`.
- **Why:** Spec readers and any deployment automation keying on the spec name will target an archived artifact.
- **Suggested fix:** `/iterate` to update both occurrences to `report2.Report` and reflect the new name in the section heading at line 822.
- **Action:** [Promote to feedback]
- **`iterate_routing`:** `{ "reason": "spec/decision/vision file modification — read-only outside /iterate" }`

### C-04 · Spec locates Azure SQL setup scripts in `azure/`; actual path is `secure/` (gitignored)
- **Kind:** decision · **Severity:** med · **Lenses:** path-drift
- **Source anchor:** spec_v1.md § Data Architecture / Azure SQL Database (lines 112, 156–160), § Security & Access (line 1225)
- **Files to touch:** `.claude/spec_v1.md`
- **Evidence:**
  - Spec line 112: `Authentication method: SQL authentication (see \`azure/user_creation.sql\`)`
  - Spec line 156: `**Setup Scripts:** (in \`/azure\` folder)` followed by `user_creation.sql` and `grant_permissions.sql`
  - Spec line 1225: `(see \`azure/user_creation.sql\`, \`azure/grant_permissions.sql\`)`
  - Disk: `ls azure/` returns only `procurement.sql` and `supplier_info.sql`. The two credential-bearing scripts live at `secure/user_creation.sql` and `secure/grant_permissions.sql`; `.gitignore` line 32 lists `secure/`.
- **Why:** A reader pulling the repo will not find these files at the documented path. The relocation was a deliberate secrets-handling decision (folder is gitignored) — the spec should reflect that intent.
- **Suggested fix:** `/iterate` to update the three references to `secure/user_creation.sql` / `secure/grant_permissions.sql` and add a one-line note that `secure/` is gitignored (credentials kept locally per project convention).
- **Action:** [Promote to feedback]
- **`iterate_routing`:** `{ "reason": "spec/decision/vision file modification — read-only outside /iterate" }`

### C-05 · Inconsistent "DQ" vs "data quality" terminology across spec sections
- **Kind:** decision · **Severity:** med · **Lenses:** vocab-drift
- **Source anchor:** spec_v1.md § Data Quality & Validation (line 1088), § Development Workflow (lines 980, 983), § Next Steps & Priorities (line 1499), § Current State Assessment (line 934)
- **Files to touch:** `.claude/spec_v1.md`
- **Evidence:**
  - § Current State Assessment (line 934): "Comprehensive data quality checks in pipeline (task-007)"
  - § Next Steps & Priorities (line 1499): "DQ checks run in pipeline, external data ingestion scripted"
  - § Development Workflow (lines 980, 983): "Run data quality checks" vs "Export schemas/DQ reports" / "Pull latest (includes DQ reports)"
  - § Data Quality & Validation (line 1088): `**Current DQ Implementation:**` (heading) while the surrounding section uses "Data Quality" headings throughout.
- **Why:** Readers scanning Phase 2 acceptance criteria must mentally bridge "DQ checks run in pipeline" to "data quality checks" used elsewhere; the task-007 implementor may be unsure whether the two refer to the same scope.
- **Suggested fix:** `/iterate` to canonicalize on "data quality" in prose. Either drop "DQ" entirely or introduce it explicitly once (e.g., "data quality (DQ)") in § Data Quality & Validation and use the short form consistently afterward. Update at least lines 980, 983, 1088, 1499.
- **Action:** [Promote to feedback]
- **`iterate_routing`:** `{ "reason": "spec/decision/vision file modification — read-only outside /iterate" }`

### C-06 · "Quality observability tables" vs "data quality observability tables" within § Current State Assessment
- **Kind:** decision · **Severity:** low · **Lenses:** vocab-drift
- **Source anchor:** spec_v1.md § Current State Assessment (lines 884, 898, 947)
- **Files to touch:** `.claude/spec_v1.md`
- **Evidence:**
  - Line 884: "[x] Data quality observability tables (gold_quality_history, gold_gap_registry, gold_quality_snapshot)"
  - Line 898: "[x] Quality observability tables added to semantic model"
  - Line 947: "Previously identified gap (data quality visibility) addressed via quality observability tables in tasks 018/019."
- **Why:** Minor. Same section, close together — but a reader searching for "data quality observability" via Cmd+F may miss the shorter variant when scoping work or building dashboard rollups.
- **Suggested fix:** `/iterate` to pick one canonical form (recommend "data quality observability tables", matching the supporting doc `data_quality_architecture.md`) and use it in all three locations within § Current State Assessment.
- **Action:** [Promote to feedback]
- **`iterate_routing`:** `{ "reason": "spec/decision/vision file modification — read-only outside /iterate" }`

## Annotations — already covered by in-flight work

(None — no Pending / In Progress / Awaiting Verification task modifies `.claude/spec_v1.md`.)

> Side note: task-012_3 (Pending) lists `fabric/clean_columnsAndHeaders.Notebook/` in `files_affected` — the stale path from C-01 has propagated into task data. Not a finding in itself (the task only references the path; it doesn't claim to fix the spec), but worth fixing the task's `files_affected` when the spec is updated.

## Per-lens raw counts

| Lens | Raw | After cluster |
|------|-----|---------------|
| superseded-decisions | 0 | 0 |
| vocab-drift | 2 | 2 |
| path-drift | 4 | 4 |
| feedback-decay | 0 | 0 |
| retired-features | 0 | 0 |
| friction-register | 0 | 0 |
| **Total** | **6** | **6** |

## Promote to feedback

Tick the box, then run `/audit-coherence promote 2026-05-17-1436`.

- [x] C-01 → FB-001 promoted 2026-05-17
- [x] C-02 → FB-002 promoted 2026-05-17
- [x] C-03 → FB-003 promoted 2026-05-17
- [x] C-04 → FB-004 promoted 2026-05-17
- [x] C-05 → FB-005 promoted 2026-05-17
- [x] C-06 → FB-006 promoted 2026-05-17
