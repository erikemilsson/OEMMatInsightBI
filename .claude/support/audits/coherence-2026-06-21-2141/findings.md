# Coherence Audit — 2026-06-21 — OEMMatInsightBI

`.claude/support/audits/coherence-2026-06-21-2141/` · 7 lenses (2 dispatched, 5 short-circuited on provably-empty inputs) · 4 raw findings → 4 after dedupe → 4 surfaced (0 routed to in-flight tasks)

**Headline:** the spec itself is in good shape. The drift is a recurring **incomplete artifact-rename sweep** pattern — three Fabric artifacts were renamed, the spec was corrected each time, but the surrounding portfolio docs/commands were never swept (C-01). Plus three spec-internal table-naming inconsistencies the spec author should reconcile (C-02–C-04).

---

## Top findings

### C-01 · Three renamed Fabric artifacts still named by old names across portfolio docs
- **Kind:** fix-eligible · **Severity:** high · **Lenses:** path-drift
- **Source anchor:** `docs/architecture/fabric-artifacts-inventory.md § Active Artifacts` · `README.md:33-36` · subsumes FR-001 (open friction) · reopens FB-001 (archived feedback)
- **Files to touch:** ≥20 surfaces — principal: `README.md`, `project_definition.md`, `docs/README.md`, `docs/architecture/fabric-artifacts-inventory.md`, `docs/architecture/data-flow-diagram.md`, `docs/portfolio/PORTFOLIO_ASSETS_README.md`, `docs/guides/FAQ.md`, `docs/setup/TROUBLESHOOTING.md`, `.claude/commands/{sync-from-fabric,sync-to-fabric,run-full-pipeline,run-silver,review-transformations,validate-schema}.md`, `.claude/support/documents/{architecture/semantic_model.md,architecture/medallion_architecture.md,architecture/orchestration.md,dax_measures.md,fabric_workspace.md,standards/naming_standards.md,incremental_load_strategy.md,error_handling_strategy.md}`. **`spec_v1.md` is NOT touched** (already correct → not a `/iterate` item).
- **Evidence (disk + grep, today):**
  - Disk canonical (positive control PRESENT): `fabric/OEMInsightBI_v2.SemanticModel/`, `fabric/bronze-to-silver.Notebook/`, `fabric/report2.Report/`. Old names exist ONLY under `fabric/archive/`.
  - The README directory tree (lines 33-36) shows **all three** stale names at once: `clean_columnsAndHeaders.Notebook`, `semantic_model_oeminsightbi.SemanticModel`, `report.Report` — none of which exist on disk.
  - `docs/architecture/fabric-artifacts-inventory.md` marks `clean_columnsAndHeaders` (L20) **and** `semantic_model_oeminsightbi` (L33) as "✅ Active" — directly false.
  - Raw repo footprints (pre-judgment, excl `.git/`/`archive/`/`audits/`/tracking files): `semantic_model_oeminsightbi` **46**, `clean_columnsAndHeaders` **40**, `report.Report` **15**.
- **Sub-instances (three renames, same root cause = incomplete cross-surface sweep):**
  1. `semantic_model_oeminsightbi` → `OEMInsightBI_v2` — **FR-001 (open)**; flagged by the 2026-05-17 audit, sweep never completed. ~12 judged active-stale surfaces.
  2. `clean_columnsAndHeaders.Notebook` → `bronze-to-silver.Notebook` — **FB-001 (archived as resolved, but only the spec was fixed)**; the doc/command sweep was never done.
  3. `report.Report` → `report2.Report` — same pattern; 15 raw refs incl. README:36, `project_definition.md:823`.
- **Why:** This is a **portfolio project for a data-engineering role** (per CLAUDE.md). The README is the front door, and it — plus the "fabric artifacts inventory" — name three artifacts that don't exist and tag two of them "✅ Active". A recruiter cross-checking the README against `fabric/` sees an immediate mismatch.
- **Suggested fix:** One coordinated cross-surface sweep, old→new, for the three artifacts — **with per-file judgment** (do NOT blind-replace): preserve (a) historical/archived notes, (b) naming-convention *discussions* (`naming_standards.md`, `fabric-artifacts-inventory.md:64` "Consider renaming…"), (c) the pipeline **activity** name `clean_columnsAndHeaders` in `error_handling_strategy.md` (the activity, not the notebook artifact), and (d) decide deliberately on stale task-file `files_affected` provenance arrays (002/003/004/009/013/014/015, 006, 012, 013, 016). Start with `README.md` + `docs/architecture/fabric-artifacts-inventory.md` (highest visibility).
- **Pending-work dedupe note:** NOT suppressed to `task-010` despite `FR-001.task_id == task-010`. task-010 is "Configure Pipeline Scheduling" (files: pipeline + `pipeline_schedule.md`) and FR-001 explicitly scopes the sweep OUT of task-010. No pending task (the 012_* batch is all performance work) touches these surfaces.
- **Why fix-eligible, not bundle-eligible:** >3 files and the fix requires per-file judgment (the exclusions above) — fails bundle criteria (e) and (d)/(g). No inline `[Fix it]`; route via `triage` or a dedicated `/work` task.

### C-02 · EU supply-shares bronze table named two ways in spec
- **Kind:** decision · **Severity:** med · **Lenses:** vocab-drift
- **Source anchor:** `spec_v1.md § Data Architecture (L320)` vs `§ Orchestration (L626)`
- **Files to touch:** `.claude/spec_v1.md`
- **Evidence:** L320 "Bronze table: `bronze_GlobalSupplyShares`" (also L356/L402) vs L626 "Sink: `bronze_EUSupplyShares`". Same physical table (copy activity `bronzecopy_EUSupplyShares` is consistent at L296/621/846).
- **Why:** The bronze→silver lineage is ambiguous — which Delta table does the silver cleaning step read?
- **Suggested fix:** `/iterate` to standardize on `bronze_GlobalSupplyShares` (per § Data Transformations) at L626.
- **iterate_routing:** spec file modification — read-only outside `/iterate`.

### C-03 · Data-quality observability third table named two ways in spec
- **Kind:** decision · **Severity:** med · **Lenses:** vocab-drift
- **Source anchor:** `spec_v1.md § Current State Assessment (L880)` vs `§ Data Quality & Validation (L1097)`
- **Files to touch:** `.claude/spec_v1.md`
- **Evidence:** L880 triad ends `gold_quality_snapshot`; L1097 triad ends `gold_low_confidence_audit (task-018)`. First two members (`gold_quality_history`, `gold_gap_registry`) agree.
- **Why:** Readers can't tell which Delta table the observability framework actually emits — weakens the data-quality-observability story (a headline feature of this project).
- **Suggested fix:** `/iterate` to standardize across L880/L1097 — `gold_low_confidence_audit` is better-provenanced (task-018). Confirm against what task-018 actually built on disk.
- **iterate_routing:** spec file modification — read-only outside `/iterate`.

### C-04 · `silver_WB` vs `silver_wb` casing drift in spec
- **Kind:** decision · **Severity:** low · **Lenses:** vocab-drift
- **Source anchor:** `spec_v1.md § Data Transformations (silver_WB)` vs `§ Data Architecture L530/L570 (silver_wb)`
- **Files to touch:** `.claude/spec_v1.md`
- **Evidence:** `silver_WB` at L284/366/384/418/660/1568; `silver_wb` at L530/L570.
- **Why:** Cosmetic (Spark/Delta is case-insensitive on table names) but reads as inconsistency in a portfolio spec.
- **Suggested fix:** `/iterate` to standardize on `silver_WB` at L530/L570.
- **iterate_routing:** spec file modification — read-only outside `/iterate`.

---

## Annotations — already covered by in-flight work

(None. No clustered finding was suppressed against a Pending / In Progress / Awaiting Verification task. See C-01's pending-work dedupe note for the FR-001/task-010 non-suppression rationale.)

---

## Per-lens raw counts

| Lens | Raw | After cluster | Notes |
|------|-----|---------------|-------|
| superseded-decisions | 0 | 0 | 0 decision records on disk |
| vocab-drift | 3 | 3 (C-02,C-03,C-04) | dispatched sub-agent |
| path-drift | 1 | 1 (C-01) | dispatched sub-agent; C-01 expands to 3 sibling renames at synthesis |
| feedback-decay | 0 | 0 | only FB-007, age 7d |
| retired-features | 0 | 0 | 0 retired manifests |
| friction-register | 0 | 0 | 1 open entry (<3); FR-001 surfaced via path-drift |
| acceptance-reconciliation | 0 | 0 | spec has 0 inline acceptance checkboxes |

---

## Promote to feedback

Tick the box, then run `/audit-coherence promote 2026-06-21-2141`.

- [ ] C-01 — Three renamed Fabric artifacts still named by old names across portfolio docs
- [ ] C-02 — EU supply-shares bronze table named two ways in spec
- [ ] C-03 — Data-quality observability third table named two ways in spec
- [ ] C-04 — `silver_WB` vs `silver_wb` casing drift in spec

**Or** triage interactively: `/audit-coherence triage 2026-06-21-2141`
