# Coherence Audit — 2026-07-28 — OEMMatInsightBI

`.claude/support/audits/coherence-2026-07-28-0345` · 7 lenses · 3 raw findings → 3 after dedupe → 3 surfaced (0 routed to in-flight tasks)

## Top findings

### C-01 · Stale `silver_WB` reference in data_quality_analysis notebook
- **Kind:** fix-eligible · **Severity:** med · **Lenses:** path-drift, friction-register (FR-028 cited)
- **Source anchor:** `fabric/data_quality_analysis.Notebook/notebook-content.py:421` (FR-028, open)
- **Files to touch:** `fabric/data_quality_analysis.Notebook/notebook-content.py`
- **Evidence:** `notebook-content.py:421` reads `wb_countries = (spark.table(f"{DB}.silver_WB")`; `silver-to-gold2.Notebook/notebook-content.py:331` carries `# NOTE: silver_WB table removed (World Bank ESG data not available)`; `spec_v1.md:380` and `spec_v1.md:1602` confirm retirement; grep confirms zero live producers of `silver_WB`.
- **Why:** Running the notebook would raise `AnalysisException: Table not found` — the retired World Bank ESG lineage has no successor; the reference is latent only because this notebook is not a pipeline activity.
- **Suggested fix:** Edit `fabric/data_quality_analysis.Notebook/notebook-content.py:421` to drop or replace the `silver_WB` reference — closing FR-028. The fix offers a *choice* (redirect to `silver_wgi` OR remove the WB coverage leg entirely), so this is **fix-eligible, not bundle-eligible**: applying it requires a judgment call between two options, which fails the "no new judgment" bundle criterion (DEC-013 Option C; "when in doubt → fix-eligible").
- **Action:** [Promote to feedback] *(fix-eligible — manual review pending future DEC)*

### C-02 · WGI items drift across "governance dimensions" / "WGI dimensions" / "indicators"
- **Kind:** decision · **Severity:** med · **Lenses:** vocab-drift
- **Source anchor:** spec_v1.md § Business Logic & Calculations (line 1302) — canonical "WGI dimensions"; drift in § Data Architecture (lines 256, 280), § Data Transformations (line 376), § Data Quality & Validation (line 1101)
- **Files to touch:** `.claude/spec_v1.md`
- **Evidence:** § Data Architecture line 256: "6 governance dimensions"; line 280: "Six **indicators** are ingested"; § Data Transformations line 376: "six **indicators**"; § Data Quality & Validation line 1101: "6 governance dimensions"; § Business Logic line 1302: "six **WGI dimensions**" — same six items, three different terms, no cross-reference.
- **Why:** "Indicators" is overloaded — EPI also has indicators (30+) — so unqualified "indicators" for WGI is ambiguous; a reader cross-referencing § Data Architecture § 3 with § Business Logic must infer the equivalence.
- **Suggested fix:** Spec amendment via `/iterate` to standardize on "WGI dimensions" (per § Business Logic line 1302) across lines 256, 280, 376, 1101; reserve "indicators" for EPI, or qualify as "WGI indicators" when used.
- **Action:** [Promote to feedback] → routes to `/iterate` (spec file modification)
- **iterate_routing:** `{ "reason": "spec/decision/vision file modification — read-only outside /iterate" }`

### C-03 · "fact table" count: 3 vs 4 across sections
- **Kind:** decision · **Severity:** low · **Lenses:** vocab-drift
- **Source anchor:** spec_v1.md § Semantic Model & Reporting (line 708) lists 4 fact tables incl. `gold_supply_risk`; § Current State Assessment (line 844) counts 3
- **Files to touch:** `.claude/spec_v1.md`
- **Evidence:** § Semantic Model lines 708-716 lists 4 items under "Fact Tables:" (`fact_epi_score`, `fact_procurement`, `fact_supply_share`, `gold_supply_risk`); § Current State line 844: "3 fact tables created (procurement, supply_share, epi_score)"; § Business Logic line 1306 describes `gold_supply_risk` as a computed table.
- **Why:** A reader checking phase-1 acceptance ("3 fact tables created") against the semantic model's list sees 4 and cannot tell whether `gold_supply_risk` is a primary fact or derived exposure without reading § Business Logic.
- **Suggested fix:** Spec amendment via `/iterate` to standardize — either update § Current State line 844 to "4 fact tables" matching § Semantic Model, or relabel `gold_supply_risk` in § Semantic Model as a "derived/calculated table" distinct from primary fact tables.
- **Action:** [Promote to feedback] → routes to `/iterate` (spec file modification)
- **iterate_routing:** `{ "reason": "spec/decision/vision file modification — read-only outside /iterate" }`

## Annotations — already covered by in-flight work

_(none)_

## Per-lens raw counts

| Lens | Raw | After cluster |
|------|-----|---------------|
| superseded-decisions | 0 | 0 |
| vocab-drift | 2 | 2 |
| path-drift | 1 | 1 |
| feedback-decay | 0 | 0 |
| retired-features | 0 | 0 |
| friction-register | 0 | 0 |
| acceptance-reconciliation | 0 | 0 |

## Promote to feedback

Tick the box, then run `/audit-coherence promote 2026-07-28-0345`.

- [ ] C-01 — Stale `silver_WB` reference in data_quality_analysis notebook
- [ ] C-02 — WGI items drift across "governance dimensions" / "WGI dimensions" / "indicators"
- [ ] C-03 — "fact table" count: 3 vs 4 across sections
