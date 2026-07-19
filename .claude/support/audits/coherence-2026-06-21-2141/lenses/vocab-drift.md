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
