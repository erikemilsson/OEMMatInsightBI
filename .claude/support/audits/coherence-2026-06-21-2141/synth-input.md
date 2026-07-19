# Lens: superseded-decisions

Findings: 0

(No findings on this axis. `inputs/decisions.json` is empty — the project has 0 decision records on disk (`.claude/support/decisions/decision-*.md` glob returns nothing), so there are no `superseded` / `partially_superseded` decisions whose old language could still linger in the spec.)


---

# Lens: vocab-drift

Findings: 3

## F-voc-01
- **Title:** EU supply-shares bronze table named two ways
- **Severity:** med
- **Source anchor:** § Data Architecture (canonical: line 320) vs § Orchestration (line 626)
- **Files affected (read-only):** `.claude/spec_v1.md`
- **Files to touch (potential fix):** `.claude/spec_v1.md`
- **Evidence:** § Data Architecture L320: "Bronze table: `bronze_GlobalSupplyShares`" (also L356, L402 in § Data Transformations). § Orchestration L626: "Sink: `bronze_EUSupplyShares` table in oem_lh". Same physical bronze table; the copy activity `bronzecopy_EUSupplyShares` (consistent, L296/621/846) writes a table named two different ways with no cross-reference.
- **What:** The bronze table produced by the EU CRM copy activity is `bronze_GlobalSupplyShares` in Data Architecture/Transformations but `bronze_EUSupplyShares` in Orchestration.
- **Why:** A reader/implementer cannot tell which is the real Delta table the silver cleaning step reads from, so bronze→silver lineage is ambiguous.
- **Suggested fix:** Spec amendment via /iterate to standardize on `bronze_GlobalSupplyShares` (per § Data Transformations) in § Orchestration L626.
- **Suggested kind:** decision

## F-voc-02
- **Title:** Observability third table named two ways
- **Severity:** med
- **Source anchor:** § Data Quality & Validation (line 1097) vs § Current State Assessment (line 880)
- **Files affected (read-only):** `.claude/spec_v1.md`
- **Files to touch (potential fix):** `.claude/spec_v1.md`
- **Evidence:** § Current State L880: "observability tables (gold_quality_history, gold_gap_registry, `gold_quality_snapshot`)". § Data Quality L1097: "Observability tables: gold_quality_history, gold_gap_registry, `gold_low_confidence_audit` (task-018)". First two members agree; the third differs.
- **What:** The third data-quality observability table is `gold_quality_snapshot` in Current State but `gold_low_confidence_audit` in Data Quality.
- **Why:** Anyone querying observability output cannot tell which Delta table exists (or whether two distinct tables were intended), undermining the data-quality-observability story.
- **Suggested fix:** Spec amendment via /iterate to standardize across L880 and L1097 — the task-018-anchored `gold_low_confidence_audit` is better-provenanced.
- **Suggested kind:** decision

## F-voc-03
- **Title:** silver_WB table casing inconsistent
- **Severity:** low
- **Source anchor:** § Data Transformations (`silver_WB`, L284/366/384/418/660) vs § Data Architecture (`silver_wb`, L530/570)
- **Files affected (read-only):** `.claude/spec_v1.md`
- **Files to touch (potential fix):** `.claude/spec_v1.md`
- **Evidence:** `silver_WB` at L284/366/384/418/660/1568. `silver_wb` at L530 ("EPI (silver_epi2024results) + World Bank (silver_wb)") and L570 ("WB: `silver_wb` table"). Same World Bank silver Delta table, two casings.
- **What:** The World Bank silver table is `silver_WB` in most sections but `silver_wb` in the gold-dimension source notes.
- **Why:** Cosmetic (Spark/Delta resolves case-insensitively), but same-noun casing drift reads as inconsistency in a portfolio spec.
- **Suggested fix:** Spec amendment via /iterate to standardize on `silver_WB` at L530 and L570.
- **Suggested kind:** decision

### Clean (no drift) — verified
"commodity" appears only as "commodity group(s)" (a defined attribute, consistent with `gold_dim_material.commodity_group`), never as a synonym for "material". No "vendor"/"nation" usage — "supplier"/"country" used consistently. `gold_data_quality_metrics` consistent (L605/L1091). FR-001 is `path_drift`, out of scope for this lens — correctly excluded.


---

# Lens: path-drift

Findings: 1 (formal) + orchestrator-verified sibling renames folded into the cluster at synthesis

## F-pat-01
- **Title:** Stale active semantic-model name `semantic_model_oeminsightbi` across surfaces (FR-001)
- **Severity:** med (raised to high at synthesis — see C-01, after sibling-rename expansion)
- **Source anchor:** `docs/architecture/fabric-artifacts-inventory.md § Active Artifacts` (line 33, listed "✅ Active") — canonical surface for the cluster. Spec `spec_v1.md §§ L82 / L726` is ALREADY CORRECTED to `OEMInsightBI_v2` and is NOT a fix target.
- **Files affected (read-only):** Disk reality confirmed: `fabric/OEMInsightBI_v2.SemanticModel/` (active) and `fabric/archive/semantic_model_oeminsightbi.SemanticModel/` (archived). Live report `fabric/report2.Report/definition.pbir:6` binds `"path": "../OEMInsightBI_v2.SemanticModel"`.
- **Files to touch (potential fix):** `docs/architecture/fabric-artifacts-inventory.md`, `docs/README.md`, `docs/portfolio/PORTFOLIO_ASSETS_README.md`, `README.md`, `project_definition.md`, `.claude/support/documents/architecture/semantic_model.md`, `.claude/support/documents/dax_measures.md`, `.claude/support/documents/fabric_workspace.md`, `.claude/support/documents/standards/naming_standards.md`, `.claude/commands/sync-from-fabric.md`, `.claude/commands/sync-to-fabric.md`, `.claude/commands/run-full-pipeline.md`. **`spec_v1.md` is NOT in this list** — already corrected, so the cluster is NOT kind:decision.
- **Evidence:** `ls fabric/*.SemanticModel` → only `fabric/OEMInsightBI_v2.SemanticModel`; old name lives ONLY at `fabric/archive/...`. Spec clean (L82 = "OEMInsightBI_v2 … old semantic_model_oeminsightbi archived"; L726 = "### Semantic Model: OEMInsightBI_v2"). STILL-STALE-ACTIVE surfaces (today, excl `.git/`, `audits/`, `fabric/archive/`, `friction.jsonl`, `feedback/archive.md`, `dashboard.md` FR-row, spec "archived" notes): `fabric-artifacts-inventory.md` ×4 (L33 "✅ Active" + L49/L58/L84), `dax_measures.md` ×4, `architecture/semantic_model.md` ×3, `project_definition.md` ×2, `fabric_workspace.md` ×2, `sync-to-fabric.md` ×2, `sync-from-fabric.md` ×2, plus README/docs-README/PORTFOLIO/naming_standards/run-full-pipeline ×1 each. Raw repo count (pre-judgment): 46.
- **What:** The renamed-and-archived semantic model `semantic_model_oeminsightbi` (superseded by `OEMInsightBI_v2` on disk) is still presented as the active/current model across ~12 non-spec doc/command surfaces — most damagingly `fabric-artifacts-inventory.md:33` which literally tags it "✅ Active".
- **Why:** The 2026-05-17 audit flagged this and fixed the spec, but the cross-surface sweep "was never completed" (per FR-001), so portfolio-facing docs misname the live artifact.
- **Suggested fix:** Sweep-replace `semantic_model_oeminsightbi` → `OEMInsightBI_v2` in the doc/command files above (NOT a blind global replace — preserve historical references; decide separately on task-file provenance arrays); resolves FR-001.
- **Suggested kind:** fix-eligible.

### Positive control (negative-findings rule)
`grep -rl "OEMInsightBI_v2"` returns `fabric/report2.Report/definition.pbir`, `fabric/OEMInsightBI_v2.SemanticModel/.platform`, `spec_v1.md`, `docs/guides/pipeline_schedule.md` — so "clean elsewhere" results are real, not silent grep failures.

### Other spec paths verified CLEAN (exist on disk as spec states)
All Fabric artifacts (`bronze_azureSQLdb2table.Dataflow`, `EPI_file2table.Dataflow`, `WGI_file2table.Dataflow`, `bronze-to-silver.Notebook`, `silver-to-gold2.Notebook`, `orchestrator_pipeline_bronze_to_gold.DataPipeline`, `data_quality_checks.Notebook`, `report2.Report`), SQL files under `secure/`/`azure/`, support docs (`dax_measure_library.md`, `rls_security_strategy.md`) — all present.

### Correctly-HISTORICAL references (NOT flagged)
Spec L82 "archived in fabric/archive/" note; spec L1432 `report.Report` "old … archived"; `fabric/archive/*`; prior audit dir `coherence-2026-05-17-1436/`; `feedback/archive.md:20` (FB-002); `friction.jsonl` (FR-001); `dashboard.md:48` (FR-001 status row).

### NOT path-drift (forward-looking / planned)
`parameter.yml` (spec L1203/1211/1216/1513) and `.github/workflows/fabric-deploy.yml` (spec L1206) are MISSING on disk BUT spec marks Phase 4 CI/CD as "Planned" — references to future artifacts, not stale paths. No finding.

### Secondary observation (expanded by orchestrator at synthesis → folded into C-01)
`README.md:33` lists `clean_columnsAndHeaders.Notebook` as the bronze→silver transform, but disk/spec canonical is `bronze-to-silver.Notebook` (`clean_columnsAndHeaders.Notebook` absent on disk). Orchestrator verification confirmed this is a SECOND incomplete rename sweep (~40 raw refs, archived FB-001 only fixed the spec) and a THIRD (`report.Report` → `report2.Report`, ~15 raw refs). All three renames co-occur in `README.md` lines 33-36 and `fabric-artifacts-inventory.md`. See C-01 in findings.md.


---

# Lens: feedback-decay

Findings: 0

(No findings on this axis. The feedback log holds a single entry — FB-007, captured 2026-06-14, age 7 days, status `new`. Decay criteria: (1) age >= 30 days with `new`/`refined`/`ready` status — 7 < 30, fails; (2) a `deferred` entry whose gating condition lapsed — status is not `deferred`, fails; (3) missing status field — status `new` is present, fails. No criteria met.)


---

# Lens: retired-features

Findings: 0

(No findings on this axis. `inputs/retired-manifests.json` is empty — the `.claude/support/retired/*/manifest.json` glob returns nothing. No features have been retired via the retirement workflow, so there are no retirement markers to reconcile against the spec.)


---

# Lens: friction-register

Findings: 0

(No findings on this axis. The open friction register holds 1 entry — FR-001 (`type: path_drift`) — below the lens's 3-entry clustering threshold, so no premature clustering (per the lens's explicit "<3 open entries → Findings: 0" rule). FR-001 is a genuine structural cross-surface path-drift issue and IS surfaced — by the **path-drift** lens, which cross-references open friction entries with `type: path_drift`. Surfacing it here too would double-count; the synthesizer dedupes by `source_anchor`. Age check: FR-001 captured 2026-06-13 (8 days), well under the 60-day staleness bar.)


---

# Lens: acceptance-reconciliation

Findings: 0

(No findings on this axis. This lens only applies when the spec renders acceptance criteria as inline `- [ ]` / `- [x]` checkboxes. `spec_v1.md` contains **0** inline acceptance checkboxes (verified: `grep -cE '^\s*- \[[ x]\]' spec_v1.md` → 0). Per the lens's own gate, there is nothing to reconcile — return 0. (Note: `verification-result.json` is also absent and acceptance status is carried per-task via `task_verification.result`; this is consistent — the project does not use inline spec acceptance boxes.))


---

