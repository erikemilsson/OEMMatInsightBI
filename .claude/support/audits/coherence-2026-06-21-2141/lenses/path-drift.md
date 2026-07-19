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
