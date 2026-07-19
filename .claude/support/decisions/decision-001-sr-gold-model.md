---
id: DEC-001
title: Supply Risk (SR) gold-model fidelity — EU CRM methodology
status: approved
category: methodology
created: 2026-06-22
decided: 2026-07-19
related:
  tasks: [task-022, task-031, task-038]
  decisions: []
implementation_anchors: []
inflection_point: true
spec_revised: true
spec_revised_date: 2026-07-20
blocks: []
---

# Supply Risk (SR) gold-model fidelity — EU CRM methodology

## Select an Option

Mark your selection by checking one box:

- [ ] Option A: Concentration index only (current trajectory)
- [x] Option B: Governance- & trade-weighted dual HHI (global + EU), reported side by side  *(recommended)*
- [ ] Option C: Blended Supply Risk core (IR-weighted global/EU)
- [ ] Option D: Full EU CRM Supply Risk (incl. recycling + substitution filters)

*Check one box above, then fill in the Decision section below.*

## Background

This decision sets **how faithfully the gold layer should implement the EU Critical Raw Materials Supply Risk (SR) methodology** for the supply-shares analysis.

**How we got here.** Coherence-audit finding C-02 (a spec naming inconsistency between `bronze_GlobalSupplyShares` and `bronze_EUSupplyShares`) was grounded during `/iterate` and turned out to mirror a real data issue (FR-004): the pipeline ingests only the EU CSV, silver reads a Global table that is a one-off 22×-duplicated bad load, and the two tables are *complementary measures from the same EU CRM report*, not duplicates. **task-022** fixes the duplication (wire the Global CSV correctly). With the data understood, the open question is the gold model itself.

**Current build state.**
- `fact_supply_share` (gold) exists — dimensional fact over Material × Country × Stage × Share (+ the `t` trade variable), currently sourced from the **Global** table only.
- The only "risk" computed today is in **DAX** (`dax_measure_library.md` §6.1): `HHI Index`, `Max/Top-3 Supply Concentration %` — i.e. **plain share concentration**. There is **no** governance (WGI) weighting, **no** trade parameter, **no** EU-vs-global blend, and **no** import reliance.

**What the methodology actually prescribes** (EU CRM Guidelines, EC 2017, doi:10.2873/769526 — verified 2026-06-22):

```
SR = [ HHI_WGI,t(GS)·(IR/2)  +  HHI_WGI,t(EUsourcing)·(1 − IR/2) ] · (1 − EoL_RIR) · SI_SR
HHI_WGI,t = Σ_c (Sᶜ)² · WGIᶜ · tᶜ        (computed once for global supply, once for EU sourcing)
```

So a methodology-faithful SR needs **both** supply tables (global supply + EU sourcing), **WGI** per country (the project already has this — the World Bank / `silver_WB` table), the **trade parameter `t`** (the `t` column in both CSVs: 0.8 EU, 1.0 baseline non-EU, >1 export-restricted), **import reliance `IR`** per material (NOT yet in the project — needs Eurostat import/export/production), and the risk-reducing **recycling (`EoL_RIR`)** and **substitution (`SI_SR`)** filters (also not in the project).

**The trade-off this decision resolves:** methodological fidelity vs. data-sourcing scope, for a project whose *primary purpose is to demonstrate data engineering on Microsoft Fabric* (per `CLAUDE.md`), not to reproduce the Commission's criticality research.

**Prerequisite for all options:** task-022 (deduplicate `bronze_GlobalSupplyShares`) — every option computes on supply shares, and a 22× duplication distorts any HHI/concentration. B–D additionally require wiring the **EU** table into silver and joining **WGI** to the supply fact.

## Options Comparison

| Criteria | A — Concentration only | B — Dual HHI (gov+trade) | C — Blended SR core | D — Full EU CRM SR |
|----------|------------------------|--------------------------|---------------------|--------------------|
| Methodology fidelity | Low (plain HHI) | Medium (faithful core metric, no blend) | High (the SR blend) | Full |
| Data already in project | Yes | Yes (after task-022 + wire EU + join WGI) | No — needs import reliance | No — needs IR + recycling + substitution |
| New external data sourcing | None | None | Eurostat import/export/production | Eurostat IR + recycling rates + substitution dataset |
| Engineering effort | Low | Medium | High | Very high |
| Portfolio value (DE role) | Low | **High** | High | Medium (scope-creep risk) |
| Dashboard story | Weak (one number) | **Strong** (global concentration vs EU exposure, governance-weighted) | Strong (single SR) | Strong but complex |
| **Overall** | Undersells the data | **Best fidelity-per-effort; recommended** | Best if IR data is sourced | Likely over-scope for a DE portfolio |

## Option Details

### Option A: Concentration index only (current trajectory)

**Description:** Keep computing `HHI`/concentration % on supply shares in DAX (as today), just on the corrected post-task-022 data. Optionally add an EU-sourcing concentration measure alongside the global one. No WGI, no `t`, no IR blend.

**Strengths:**
- Minimal effort — largely already built.
- Simple to explain; no new data.

**Weaknesses:**
- Not the EU CRM SR — it's raw concentration; omits the governance/trade/EU-sourcing elements that *define* the methodology.
- Underuses data already in the project (WGI, `t`, the EU table).
- Weakest portfolio narrative — "I computed an HHI" vs "I implemented the EU criticality supply-risk model."

### Option B: Governance- & trade-weighted dual HHI (global + EU), reported side by side  *(recommended)*

**Description:** Implement `HHI_WGI,t = Σ_c (Sᶜ)²·WGIᶜ·tᶜ` for **both** the global supply mix and the EU sourcing mix, at the bottleneck stage (E/P). Expose both as gold measures (e.g. `gold_supply_risk` with `hhi_global` and `hhi_eu_sourcing`) plus their contrast. Do **not** blend them (no import reliance needed).

**Strengths:**
- Faithful to the methodology's **core risk metric** (the governance- and trade-weighted HHI), which is the distinctive, defensible part.
- Uses **both** supply tables → showcases the EU-vs-global data modeling (a genuinely good data story; mirrors the methodology's Fig 1a-b).
- **Self-contained** — every input is already in the project (after task-022 + wiring the EU table + joining `silver_WB` WGI). No open-ended external-data project.
- Bounded, demonstrable, and a strong dashboard narrative (global concentration vs EU exposure, governance-weighted).
- Clean upgrade path to C (just add the IR weighting later).

**Weaknesses:**
- Not the *full* SR — the two HHIs are shown separately rather than combined into one IR-weighted SR number.
- Omits the recycling/substitution risk-reducing filters.

**Research Notes:** WGI is currently in the EPI/indicator branch (`gold_dim_indicator`, `fact_epi_score`), not joined to the supply fact — B requires joining WGI per country onto `fact_supply_share`. The `t` column is already present in the supply CSVs.

### Option C: Blended Supply Risk core (IR-weighted global/EU)

**Description:** Compute the methodology's SR blend `SR_core = HHI_WGI,t(GS)·IR/2 + HHI_WGI,t(EU)·(1−IR/2)` — a single SR number per material — but omit the `(1−EoL_RIR)·SI_SR` filters.

**Strengths:**
- Implements the methodology's distinctive **blend structure** (global supply + EU sourcing, weighted by import reliance) → a single, credible SR per material.
- Very faithful on the supply-concentration axis.

**Weaknesses:**
- Requires sourcing **import reliance** per material (Eurostat import/export/production) — a new ingestion + source, and the data-quality work that comes with it.
- Still omits recycling/substitution.

### Option D: Full EU CRM Supply Risk (incl. recycling + substitution)

**Description:** The complete formula including `(1−EoL_RIR)` recycling and `SI_SR` substitution filters (methodology §2.2, §3.5–3.6).

**Strengths:**
- Fully faithful — the actual EU CRM SR number.

**Weaknesses:**
- Substantial extra data sourcing (recycling rates; the substitution dataset SP/SCr/SCo) **and** the substitution sub-methodology, which is a project in itself.
- Likely beyond the value-add of a *data-engineering* portfolio; real scope-creep risk.

## Your Notes & Constraints

*This section is yours — Claude reads it but never overwrites it.*

**Constraints:**
- [e.g., "I do / don't have ready Eurostat import-reliance data for these materials"]
- [e.g., "Portfolio deadline / how much time to invest in the analytical depth"]

**Questions:**
- [e.g., "Is WGI already loaded per-country in a form joinable to the supply fact, or only as EPI indicators?"]

## Decision

**Selected:** Option B — Governance- & trade-weighted dual HHI (global + EU), reported side by side

**Decided:** 2026-07-19

**Rationale:**
Best fidelity-per-effort for a project whose primary purpose is demonstrating data engineering on Microsoft Fabric. B implements the methodology's *distinctive, defensible core* — the governance- and trade-weighted HHI — and uses both supply tables, which is the genuinely interesting data-modeling story (global concentration vs. EU exposure, mirroring the methodology's Fig 1a-b). It needs **no new external data source**, so it cannot turn into an open-ended ingestion project the way C and D can. It also leaves a clean upgrade path to C: adding the IR weighting later is additive, not a rewrite.

**Grounding correction (2026-07-19).** The Background section's claim that B is "self-contained — every input is already in the project" was verified during selection and is **true at the bronze/source layer only**. The current pipeline actively discards two of B's three distinctive inputs:

| Input | Current state | Anchor |
|-------|---------------|--------|
| Trade parameter `t` | Explicitly dropped: `.drop('t')` | `fabric/bronze-to-silver.Notebook/notebook-content.py:139` |
| WGI governance scores | Silver keeps only `country_iso3` / `country_name` / `indicator_name`; `Value` discarded. The inline comment "Score column not present in current dataflow" is **stale** — `bronze_ingest_wgi` does fetch `Value` per country/indicator/year from the World Bank API | `fabric/bronze-to-silver.Notebook/notebook-content.py:282-289` vs `fabric/bronze_ingest_wgi.Notebook/notebook-content.py:243,255,287` |
| EU sourcing table | Not wired (task-022 scope, already known) | — |

This does not change the selection — all three are small plumbing fixes in files already in flight, versus C's whole new Eurostat source — but it renames the work from "join what's already there" to "stop discarding three things, then join," and it adds **task-031** to the prerequisite chain. task-031 did not exist when this record was written (2026-06-22); it was created by the 2026-07-13 pipeline audit.

## Trade-offs

**Gaining:**
- The methodology's core risk metric (`HHI_WGI,t = Σ_c (Sᶜ)²·WGIᶜ·tᶜ`) computed faithfully, twice — global supply mix and EU sourcing mix.
- Both supply tables in active use, plus WGI joined onto the supply fact — three datasets that are currently ingested and then wasted.
- A strong, bounded dashboard narrative: global concentration vs. EU exposure, governance-weighted.
- No new external data dependency, and therefore no new data-quality surface.
- Additive upgrade path to Option C.

**Giving Up:**
- A single headline SR number per material — B reports the two HHIs side by side rather than blending them by import reliance.
- The risk-*reducing* half of the methodology: recycling (`EoL_RIR`) and substitution (`SI_SR`) filters are out of scope, so the figures represent gross rather than net supply risk. Worth stating explicitly on the report page so the numbers aren't read as EU CRM SR values.

## Impact

**Implementation Notes:**
- All options depend on **task-022** (deduplicate `bronze_GlobalSupplyShares`) landing first.
- B–D additionally require: a copy activity / silver read for the **EU** table, and joining **WGI** per country onto the supply fact.
- As an **inflection point**, the chosen model changes the spec's Business-Logic / DAX-measures sections — after selection, `/work` will suggest `/iterate` to update the spec (SR definition, the new gold measures, the EU-vs-global lineage).

**Prerequisite chain for the selected Option B** (established 2026-07-19 — supersedes the two bullets above for B specifically):

1. **task-022** — wire the Global CSV correctly (removes the 22× duplication that would distort any HHI). *In Progress, awaiting Fabric.*
2. **task-031** — preserve WGI `Year`/`Value` into `silver_wgi`. **Hard prerequisite**: B's `WGIᶜ` weight does not exist downstream without it. Note task-031 offers "or descope" as an alternative — that branch is now **closed**; DEC-001 Option B makes preservation mandatory.
3. **Un-drop `t`** at `bronze-to-silver.Notebook:139` — one-line change, folded into task-038. Coordinate with **task-024**, which is already editing that file.
4. **task-038** — build the `gold_supply_risk` model (the follow-on task this record called for).

**Sequencing note:** step 3 touches `bronze-to-silver.Notebook/notebook-content.py`, which task-024 (In Progress) also edits. Apply task-024 in Fabric before starting task-038 to avoid clobbering the delete-insert grain fix.

**Affected Areas:**
- `fabric/silver-to-gold2.Notebook/notebook-content.py` (`fact_supply_share`, a new `gold_supply_risk` build for B+)
- `.claude/support/documents/dax_measure_library.md` (§6.1 Concentration Risk → SR measures)
- `fabric/OEMInsightBI_v2.SemanticModel/` (new measures / relationships)
- spec `.claude/spec_v1.md` — Business Logic & Calculations, DAX Measures sections
- Related tasks: **task-022** (prerequisite); a follow-on "build SR gold model" task to be created on selection.

**Risks:**
- C/D introduce an external-data dependency (Eurostat IR / recycling / substitution) with its own DQ burden.
- Over-fidelity (D) risks turning a data-engineering portfolio into a criticality-research reproduction.
