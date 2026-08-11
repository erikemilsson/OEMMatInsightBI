---
id: DEC-014
title: Weighted EPI Score at grand total — wrap the measure rather than document the filter context
status: approved
category: semantic-model
created: 2026-08-11
decided: 2026-08-11
decided_by: Erik
related:
  tasks: ["061"]
  decisions: ["013"]
implementation_anchors:
  - file: "fabric/OEMInsightBI.SemanticModel/definition/tables/fact_epi_score.tmdl"
    description: "Weighted EPI Score wrapped in AVERAGEX(VALUES(gold_dim_country[country_key]), ...); DIVIDE alternate-result 0 removed"
  - file: "docs/dax_measure_library.md"
    description: "Measure definition, total-grain behaviour, and the no-zero-fallback rule"
  - file: "docs/architecture/semantic_model.md"
    description: "One-line measure description (line 132)"
inflection_point: false
spec_revised: false
blocks: []
---

# Weighted EPI Score at grand total — wrap the measure rather than document the filter context

## Select an Option

Mark your selection by checking one box:

- [x] Option A: Wrap the measure so it resolves to a meaningful value outside a single-country context
- [ ] Option B: Document the required filter context and confirm no visual can render it uncontexted

*Selected by Erik 2026-08-11 ("wrap it").*

## Background

Phase-level verification found on 2026-08-05 that `[Weighted EPI Score]` evaluated with no filter context returns **7945.40**, far outside the 0–100 band the measure is documented to produce. Under a single-country filter it behaved as documented, and Erik confirmed the 0–100 rendering on 2026-08-04, so this was a non-additive-at-total artifact rather than a computation defect — but an uncontexted card in `oem_report` would have shown a meaningless 7945.40 to a portfolio reviewer.

The mechanism: the measure was already a weighted average, `DIVIDE(WeightedScores, TotalWeights, 0)`, but the **denominator did not scale with country cardinality**. `gold_dim_indicator` is a dimension, so `TotalWeights` is the same 58-weight sum (summing to 100) whether one country or all are in context, while `WeightedScores` fans out across every country's rows. Measured live: `SUMX(VALUES(country_key), <per-country measure>)` = 7945.40250071345, exactly the old grand total — the total was literally the sum of the 180 per-country weighted averages.

## Options Comparison

| Criteria | Option A (wrap) | Option B (document) |
|----------|-----------------|---------------------|
| Uncontexted card is safe | Yes — reads 44.14 | No — still 7945.40 |
| Single-country behaviour | Unchanged (max delta 0.0 across 194 keys) | Unchanged |
| Ongoing cost | None | Re-audit every visual on each report edit |
| Fix located at | The measure (one expression) | Every consumer, forever |
| Overall | **Selected** | Rejected |

## Option Details

**Option A — wrap (selected).** `AVERAGEX(VALUES(gold_dim_country[country_key]), <existing VAR/RETURN body>)`. In a single-country context `AVERAGEX` over one value returns exactly today's number; at grand total it returns the mean EPI across the countries in context (44.141 world, 58.594 filtered to Europe). Verified against the live published model by running the literal file text as a `DEFINE MEASURE`.

Because the uncontexted value is now meaningful, task-061's AC3 is satisfied by its own parenthetical — no report-wide visual audit is needed.

**Option B — document (rejected).** Leaves a live foot-gun that must be re-audited on every report edit, and still shows a reviewer 7945.40 on any card that slips through.

## Coupled sub-decision — the `DIVIDE` alternate result was removed

**Provenance:** Erik chose *"wrap it"* — the fork in the Options table above. This third-argument removal was **added by the implementer and was never put to Erik**. It is recorded here because it shipped in the same change, not because it was selected.

The third argument (`0`) was dropped. **Two successive rationales for it were wrong, and the correct one is that the fallback was unreachable.** Measured on the live engine with positive controls (verify-agent, 2026-08-11):

| Probe | Result |
|---|---|
| `DIVIDE(BLANK(), 58, 0)` | BLANK |
| `DIVIDE(BLANK(), BLANK(), 0)` | BLANK |
| `DIVIDE(1, BLANK(), 0)` | **0** ← control: it does fire |
| `DIVIDE(0, BLANK(), 7)` | **7** ← control |

**The discriminator: a BLANK numerator returns BLANK regardless of the denominator.** The alternate result fires only on a blank/zero *denominator* with a non-blank numerator. In this measure `TotalWeights` can only go BLANK when `EpiSubIndicators` is empty or every visible weight is BLANK — and both force `WeightedScores` BLANK too (`SUMX` over an empty filtered fact is BLANK; `score × BLANK` is BLANK). Numerator and denominator go blank together, so the `0` was never reachable. Confirmed directly on the live *old* measure: `CALCULATE([Weighted EPI Score], gold_dim_indicator[source_system]="WGI")` returns BLANK, not 0. `TotalWeights = 0` exactly is also unreachable — the 58 sub-indicators sum to 100.0, minimum weight 0.1, with no blank- or zero-weight rows.

For the record, the two rationales that did **not** survive measurement: (a) that a country lacking EPI rows evaluated to `DIVIDE(BLANK, 58, 0)` = 0 — false, blank numerator wins; (b) that a WGI-only or all-NULL-weight context made `TotalWeights` BLANK and returned 0 — false for the same reason, and the pre-task-056 all-NULL state is documented in three places as having rendered **BLANK** (`silver_to_gold` notebook L1196, `bronze_ingest_epi` L232-233, and DEC-013).

**So the removal is a no-op on this measure.** It is retained as defensive hygiene, consistent with the project's standing rule that a missing external score must never coerce to 0 (the Taiwan/WGI precedent — see DEC-009, which reports genuine gaps as NULL rather than a number; the Taiwan gotcha itself lives in auto-memory, not root `CLAUDE.md`) — not because it fixed an observed zero. Measured delta on current data: 0.0.

## Consequences

- The measure is safe in any filter context; no visual-level guard is required.
- **On any non-country grouping the measure now returns a constant 44.14112500396361** (measured across all 13 `commodity_group` rows; the old measure returned a constant 7945.40 there). `fact_epi_score` has no material grain, so this is expected — but note the direction: a self-evidently-broken number became a *plausible-looking* one that a portfolio reviewer would not question. Worth deciding whether such a visual should exist at all.
- `docs/dax_measure_library.md` § 4's DIVIDE-with-0 pattern entry was corrected to state the real rule.
- The spec's § Business Logic & Calculations line 1457 still describes the measure as "non-additive at grand total" and needs an `/iterate` pass (FR-069 / FR-071).
- Deployment and in-report confirmation are Erik's half — the published model still holds the old measure until a push to `main` fires `deploy-fabric.yml`.
- `[Latest Match Rate]` and `[Latest Coverage Rate]` were confirmed BLANK by construction during this task (diagnosed, not fixed — no follow-up task exists yet).

