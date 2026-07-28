# Coherence Audit — 2026-07-28 — OEMMatInsightBI

`.claude/support/audits/coherence-2026-07-28-0308` · 7 lenses · 9 raw findings → 7 after dedupe → 7 surfaced (0 routed to in-flight tasks)

## Top findings

### C-01 · DQ analysis notebook reads retired silver_WB table
- **Kind:** fix-eligible · **Severity:** med · **Lenses:** friction-register
- **Source anchor:** fabric/data_quality_analysis.Notebook/notebook-content.py:421 (FR-028)
- **Files to touch:** fabric/data_quality_analysis.Notebook/notebook-content.py
- **Evidence:** "fabric/data_quality_analysis.Notebook line 421 still reads oem_lh.silver_WB, a table the retired World Bank ESG lineage produced and which no longer exists."
- **Why:** Latent (not a pipeline activity) but will fail if the notebook is run manually — a stale reference waiting to bite.
- **Suggested fix:** Remove or repoint the `spark.table(silver_WB)` read at line 421, or retire the notebook section if the analysis is obsolete.
- **Action:** [Promote to feedback] *(fix-eligible — manual review pending future DEC)*

### C-02 · FB-007 untriaged 44 days
- **Kind:** fix-eligible · **Severity:** med · **Lenses:** feedback-decay
- **Source anchor:** .claude/support/feedback/feedback.md (FB-007)
- **Files to touch:** .claude/support/feedback/feedback.md
- **Evidence:** `{"id":"FB-007","status":"new","captured":"2026-06-14","age_days":44}` — past the 30-day decay threshold.
- **Why:** Untriaged feedback accumulates; a 30+ day `new` entry signals the feedback loop is not draining.
- **Suggested fix:** Triage FB-007 via `/feedback review` (accept, decline, or merge).
- **Action:** [Promote to feedback] *(fix-eligible — manual review pending future DEC)*

### C-03 · Stale friction entries FR-025 & FR-029 — underlying issues already fixed
- **Kind:** fix-eligible · **Severity:** med · **Lenses:** friction-register
- **Source anchor:** .claude/support/friction.jsonl (FR-025, FR-029)
- **Files to touch:** .claude/support/friction.jsonl
- **Evidence:** "FR-025 (bronze_WGI DQ schema contradiction) is still open, but `data_quality_checks.Notebook` now uses the WB API long-format contract (commit c752953, task-035 comments present). FR-029 (semantic model doc vs TMDL) is still open, but `fabric_workspace.md § Semantic Model` now correctly states DirectLake on `oem_lh` and explicitly disclaims the warehouse."
- **Why:** Both friction entries were captured before the fixes landed; the register was never updated, so the audit re-surfaced resolved issues. Stale open entries erode trust in the friction register as a work-queue.
- **Suggested fix:** Close FR-025 and FR-029 in `.claude/support/friction.jsonl` with `status: closed` and a resolution note referencing the fixing commits (c752953 for FR-025; task-033 doc sweep for FR-029).
- **Action:** [Promote to feedback] *(fix-eligible — friction-register protocol, not inline-apply)*

### C-04 · Spec EPI ingestion drift — retired Dataflow named across 6 sections
- **Kind:** decision · **Severity:** high · **Lenses:** vocab-drift, friction-register
- **Source anchor:** spec_v1.md § Data Sources #2 (line 208), § Data Sources #3 (line 254), § Current State Assessment (lines 822/824), § Dependencies & External Systems (lines 1432/1444), § Development Workflow (line 985), § Orchestration (lines 621/623) — FR-027
- **Files to touch:** .claude/spec_v1.md
- **Evidence:** "spec_v1 § Data Sources #2 line 208 states the EPI ingestion method is EPI_file2table.Dataflow while line 238 of the same section and the live pipeline both use bronze_ingest_epi.Notebook. Matching stale checkbox at line 822."
- **Why:** The spec's own § Data Sources declares the notebooks as live and the dataflows as retired, but 6+ other sections still use the retired dataflow names as current, misrouting any reader or agent using the spec as the source of truth.
- **Suggested fix:** `/iterate` to standardize on `bronze_ingest_epi.Notebook` / `bronze_ingest_wgi.Notebook` across § Data Sources #2 (line 208), § Current State (lines 822/824), § Dependencies (lines 1432/1444), § Development Workflow (line 985), and reconcile § Orchestration `RefreshDataflow` labels (lines 621/623).
- **Action:** [Promote to feedback]
- **iterate_routing:** { "reason": "spec file modification — read-only outside /iterate" }

### C-05 · Spec describes CI/CD files (parameter.yml, fabric-deploy.yml) that don't exist
- **Kind:** decision · **Severity:** med · **Lenses:** path-drift
- **Source anchor:** spec_v1.md § Infrastructure & Deployment (lines 1197, 1200, 1205, 1210)
- **Files to touch:** .claude/spec_v1.md
- **Evidence:** "Spec § Infrastructure & Deployment names `parameter.yml` and `.github/workflows/fabric-deploy.yml` as present-tense artifacts; `.github/workflows/` contains only `test.yml`; no `parameter.yml` on disk."
- **Why:** The spec is internally inconsistent — § Next Steps & Priorities (line 1536) marks "Phase 4 | CI/CD Deployment | Planned", but § Infrastructure & Deployment describes the same artifacts in the present tense with specific file paths. A reader would expect on-disk files that were never created.
- **Suggested fix:** `/iterate` in § Infrastructure & Deployment: either reframe the CI/CD subsection as "Planned approach" with explicit "not yet implemented" markers, or move file-path specifics into the Phase 4 deliverables list.
- **Action:** [Promote to feedback]
- **iterate_routing:** { "reason": "spec file modification — read-only outside /iterate" }

### C-06 · Spec Appendix "Sample WGI Record" uses retired silver_WB fields
- **Kind:** decision · **Severity:** med · **Lenses:** vocab-drift
- **Source anchor:** spec_v1.md § Appendix: Sample Data Patterns (lines 1598-1610), § Data Transformations (line 380)
- **Files to touch:** .claude/spec_v1.md
- **Evidence:** "Appendix heading 'Sample WGI Record' (line 1598) but source label 'From silver_WB' (line 1600) with fields `topic`, `score: 85.3` on a 0-100 scale — matching the retired WB ESG lineage, not the current `silver_wgi` schema (`country_iso3`, `Year`, `Value` on −2.5…+2.5, no `topic`)."
- **Why:** "WGI" (current governance indicators) and "WB" (retired World Bank ESG) are distinct concepts sharing World Bank provenance; the Appendix uses them as synonyms, contradicting § Data Transformations' explicit retirement note for `silver_WB`.
- **Suggested fix:** `/iterate` to either relabel the section "Sample WB Record (retired lineage)" or replace the sample with fields from the current `silver_wgi` schema per § Data Sources #3.
- **Action:** [Promote to feedback]
- **iterate_routing:** { "reason": "spec file modification — read-only outside /iterate" }

### C-07 · Spec header references stale .claude/context/ and .claude/reference/ paths
- **Kind:** decision · **Severity:** low · **Lenses:** path-drift
- **Source anchor:** spec_v1.md § Project Overview (lines 18, 20, 22)
- **Files to touch:** .claude/spec_v1.md
- **Evidence:** "Spec § Project Overview preamble references `.claude/context/`, `.claude/reference/`, `.claude/context/standards/` — none exist on disk (verified by `ls`). Canonical locations are `.claude/support/documents/`, `.claude/support/reference/`, `.claude/support/documents/standards/`."
- **Why:** Template-era boilerplate that was never updated when the project adopted the `.claude/support/` layout (documented in root `CLAUDE.md` and `.claude/CLAUDE.md`).
- **Suggested fix:** `/iterate` in § Project Overview: replace `.claude/context/` → `.claude/support/documents/`, `.claude/reference/` → `.claude/support/reference/`, `.claude/context/standards/` → `.claude/support/documents/standards/`.
- **Action:** [Promote to feedback]
- **iterate_routing:** { "reason": "spec file modification — read-only outside /iterate" }

## Annotations — already covered by in-flight work

*(None — no findings matched a Pending / In Progress / Awaiting Verification task.)*

## Per-lens raw counts

| Lens | Raw | After cluster |
|------|-----|---------------|
| superseded-decisions | 0 | 0 |
| vocab-drift | 2 | 2 |
| path-drift | 2 | 2 |
| feedback-decay | 1 | 1 |
| retired-features | 0 | 0 |
| friction-register | 4 | 3 |
| acceptance-reconciliation | 0 | 0 |

## Notes from synthesis

- **Two friction entries were re-verified against current code and found stale.** FR-025 (bronze_WGI DQ schema contradiction) and FR-029 (semantic model doc vs TMDL) describe issues that have since been fixed on disk (commit c752953 updated `data_quality_checks.Notebook` to the WB API long-format contract; task-033's doc sweep corrected `fabric_workspace.md § Semantic Model` to DirectLake on `oem_lh`). They are reframed as C-03 (friction-register hygiene: close the entries) rather than surfaced as live code/doc defects. The lens agents trusted the open friction entries without re-checking the source files.
- **No pending-task coverage.** All friction entries were captured in task-031 / task-033 (both Finished); FR-025's `owned_by_task` (task-035) is also Finished. No finding routed to in-flight work.
- **acceptance-reconciliation lens** reported 0 findings — the spec's 77 inline checkboxes are a thematic project-status inventory, not phase-scoped acceptance criteria, so unticked boxes for incomplete phases are legitimate.
- **Hard-rule sanity check passed:** all 4 `decision` items touch `.claude/spec_v1.md`; no `bundle-eligible` item touches a spec/decision/vision path.

## Promote to feedback

Tick the box, then run `/audit-coherence promote 2026-07-28-0308`.

- [ ] C-01 — DQ analysis notebook reads retired silver_WB table
- [ ] C-02 — FB-007 untriaged 44 days
- [ ] C-03 — Stale friction entries FR-025 & FR-029 — underlying issues already fixed
- [ ] C-04 — Spec EPI ingestion drift — retired Dataflow named across 6 sections
- [ ] C-05 — Spec describes CI/CD files (parameter.yml, fabric-deploy.yml) that don't exist
- [ ] C-06 — Spec Appendix "Sample WGI Record" uses retired silver_WB fields
- [ ] C-07 — Spec header references stale .claude/context/ and .claude/reference/ paths