# OEMMatInsightBI — Procurement Analytics & Supply-Risk Intelligence on Microsoft Fabric

**Portfolio case study** · Erik Emilsson
**Stack:** Microsoft Fabric (Lakehouse, Data Pipelines, Notebooks) · PySpark · Delta Lake · Power BI / DAX / TMDL · Azure SQL · GitHub Actions
**Repository:** [github.com/erikemilsson/OEMMatInsightBI](https://github.com/erikemilsson/OEMMatInsightBI)

---

## What this project is

An end-to-end Microsoft Fabric solution that joins an OEM's procurement ledger against external environmental and governance data to answer one question: **where is our sourcing actually exposed, and how confident can we be in that answer?**

It is a portfolio project, built to demonstrate production data-engineering patterns end to end rather than to serve a real procurement team.

**About the data — stated up front, because it changes how the numbers should be read:**

| Source | Provenance | Scale |
|---|---|---|
| Procurement transactions | **Synthetic** — generated for this project | ~500 records |
| Environmental Performance Index (Yale EPI) | **Real** public dataset, automated HTTP download | ~180–200 countries, ~30–40 indicators |
| Worldwide Governance Indicators (World Bank WGI) | **Real** public dataset, World Bank API v2 | ~200 countries × 6 dimensions × 1996–2023 |
| Critical-raw-material supply shares (EU CRM study) | **Real** public dataset | 80+ materials × 2 stages |

The consequence is deliberate and worth being explicit about: **the risk methodology and every external input are real; the spend figures are illustrative.** This case study therefore makes claims about *method and engineering*, not about discovered business facts. Any "insight" derived from a synthetic ledger would be an artifact of the generator, and presenting one as a finding would be dishonest.

---

## The problem

Procurement organisations typically know what they spend and with whom. What they usually cannot answer:

1. **Is our sourcing concentrated?** Not "which supplier is biggest" but the economically meaningful question — how concentrated is the *upstream* supply of the materials we depend on?
2. **Is that concentration in places that are risky?** A 60% share from a well-governed country is not the same risk as 60% from a poorly-governed one.
3. **Is our exposure worse than the world's?** If Europe sources a material more narrowly than global production is distributed, that is a distinct, actionable risk.
4. **How much of the answer is missing?** Every real dataset has coverage gaps. A risk index that quietly treats "no data" as "no risk" is worse than no index.

Question 4 is the one that drove most of the engineering below.

---

## Architecture

A medallion lakehouse orchestrated by a single Fabric Data Pipeline (10 activities).

```
Azure SQL ──┐
Yale EPI  ──┼──► Bronze (raw, full load)  ──►  Silver (cleaned,   ──►  Gold (star schema  ──►  Power BI
World Bank ─┤     6 parallel activities        conformed, aliased)      + risk model)          (DirectLake)
EU CRM    ──┘                                                                │
                                                                             └──► Quality observability
                                                                                  + blocking gate
```

- **Bronze** — 4 Copy activities (Azure SQL, supply-share CSVs) + 2 PySpark notebooks that fetch EPI (HTTP download) and WGI (World Bank API v2) directly. No manual file uploads.
- **Silver** — one PySpark notebook: type coercion, date correction, unit normalisation to kg, and country/material alias resolution with confidence scoring.
- **Gold** — star schema (3 facts, 5 dimensions) plus `gold_supply_risk`, the weighted risk model. DirectLake semantic model over the gold layer.
- **Quality** — a terminal `data_quality_checks` notebook that persists results *and* can halt the pipeline, plus an error handler that runs on every outcome.

Incrementality lives in **silver**, not bronze: bronze is a full load, and `p_from_date` drives a 7-day look-back in the bronze→silver notebook against corrected dates. This is a deliberate simplification for portfolio-scale data, and worth saying out loud rather than implying a more elaborate design than exists.

---

## The engineering decisions worth defending

This is the part of the project I would actually want to be interviewed on.

### 1. The governance weight must be inverted — or the index ranks risk backwards

Supply risk is a governance- and trade-weighted Herfindahl index, computed per material × stage × year:

```
HHI_WGI,t  =  Σ_c  (Sᶜ)² · WGIᶜ · tᶜ
```

where `Sᶜ` is country *c*'s supply share, `tᶜ` a trade parameter (0.8 EU / 1.0 baseline / >1 export-restricted), and `WGIᶜ` a governance weight in `0..1` where **1 = worst governance**.

Raw World Bank WGI estimates run ≈ −2.5…+2.5 with **higher = better** governance. Used unmodified as a multiplier, the index *rewards* poorly-governed sourcing:

```
WGIᶜ = clamp( (2.5 − mean₆(WGI estimates, latest year available)) / 5 , 0, 1 )
```

**Why this is the interesting bug:** an un-inverted index still computes, still returns plausible-looking numbers in the right order of magnitude, and still renders fine in a report. Nothing errors. Every risk ranking is simply upside-down. There is no test that catches this except knowing the sign convention of your source data — which is exactly the class of defect that survives to production. The inversion is specified as mandatory, not incidental.

### 2. Rescale on fixed theoretical bounds, not observed min/max

The rescaling divisor is the WGI scale's **theoretical** range (−2.5…+2.5), not the observed range of whatever countries happen to be loaded.

With observed bounds, adding one country — or ingesting a new WGI vintage — silently re-ranks every material in the model. Before/after comparisons across runs become meaningless, and the "improvement" you measure after an optimisation is partly just a moved goalpost. Fixed bounds make the index **reproducible across runs and data vintages**; the `clamp` handles the rare country whose mean falls outside ±2.5.

### 3. NULL is not zero

A material × stage with global supply data but no EU sourcing rows yields `hhi_eu_sourcing = NULL` and `contrast_ratio = NULL` — **never 0**.

This matters because **0 is a legitimate value** in this index: it means perfectly diffuse supply, i.e. *no concentration risk*. Coercing a coverage gap to 0 doesn't just lose information — it inverts the meaning, reporting the safest possible reading for the case where you know least. Missing coverage is measured and surfaced through the audit mechanism instead of being silently filled.

### 4. Taiwan is a permanent, documented gap — not a bug to fix

While building the governance join, the country-coverage audit flagged Taiwan (TWN) as having no WGI data. The instinct is to treat this as an aliasing failure and go hunting for the alias.

It isn't one. **The World Bank publishes no WGI for Taiwan, and never has** — Taiwan is not a member state. No amount of alias mapping will resolve it.

The correct engineering response was to stop trying to fix it and instead make it visible: an `incomplete_wgi_coverage` flag on the affected rows, so that materials with meaningful Taiwanese supply are known to have an **understated** risk score rather than a wrong one presented as complete. Semiconductor-adjacent materials are exactly where this bites.

This is the decision I would most want to be asked about, because the tempting alternatives — drop the country, impute a regional average, coerce to zero — are all defensible-sounding and all wrong in a different way.

### 5. The blocking gate and the breach flag are different signals

Data quality checks are not advisory. `data_quality_checks` is the pipeline's terminal activity and raises `DataQualityException` when any check in a fixed 13-entry `BLOCKING_CHECKS` set fails — schema validation, required-field completeness, duplicate detection, referential integrity at 0% tolerance across all three gold facts, and grain uniqueness.

The exception is raised **after** results are persisted, so a blocked run still leaves a complete audit trail rather than failing dark.

The subtle part: a separate `breach_flag` tracks a *score* threshold (< 70.0) and is advisory only. **The two diverge routinely.** A grain-uniqueness failure on 2 rows out of 2,561 scores ~99.9 — far above the breach threshold — yet halts the pipeline. A run can record **zero breaches and still be a blocked run.** Asserting "the gate passed" by reading `breach_flag` reads the wrong field entirely. The gate therefore writes its own explicit verdict rows (`dq_gate_raised`, `dq_gate_blocking_failures`, `dq_gate_blocking_evaluated`) so the outcome is answerable from the table alone, without reading notebook source — including a guard against a stale `BLOCKING_CHECKS` entry silently demoting a check to advisory.

### 6. Duplicated logic, pinned by contract instead of left to drift

Fabric notebooks cannot import from the repository's `src/` package at runtime, so transformation logic necessarily exists twice: once inline in the notebook (what actually runs) and once in `src/transformations/` (what is testable).

Rather than pretend one is the source of truth, the duplication is made a **tested contract**: the pytest suite loads the notebook's own functions and pins them against the `src/` implementations. Where semantics intentionally differ, the *difference itself* is asserted rather than quietly reconciled. Changing one side without the other fails CI by design.

**235 tests** currently run against this arrangement on Python 3.10/3.11/3.12.

---

## Data quality as an observable system

Quality is modelled as three gold tables that accumulate over time rather than as a pass/fail printout:

- **`gold_quality_history`** — per-check results per run, so quality is a *trend*, not a snapshot
- **`gold_gap_registry`** / **`gold_data_gaps`** — what is missing and where coverage is incomplete
- **`gold_low_confidence_audit`** / unmapped-value audits — alias resolutions that matched weakly enough to warrant review

Country and material names arrive inconsistently across four independent sources ("USA" vs "United States"; "Copper Wire" vs "Copper, refined"). Resolution is alias mapping plus confidence scoring, with every low-confidence and unmapped value written to an audit table instead of being dropped or silently force-matched.

---

## Deployment

Automated Fabric deployment via GitHub Actions and Microsoft's `fabric-cicd` library:

- Service Principal authentication (Azure AD app registration; secrets in GitHub, never committed)
- `parameter.yml` for environment-specific rebinding (lakehouse IDs, connections)
- Publish on merge to `main`; retired artifacts under `fabric/archive/` excluded from deploy by folder regex
- A dry-run mode that reports the deployment plan without publishing

One honest note carried in the workflow itself: `fabric-cicd` 1.2.0 exposes **no public dry-run or resolve-only API**, so the dry-run path calls private helpers. That coupling is documented at the call site with an explicit upgrade trigger, and degrades to a warning rather than a hard failure if the helpers are renamed. Choosing to document a known limitation precisely beat both pretending it wasn't there and blocking indefinitely on an upstream release that may never come.

---

## Performance

Measured over 3 warm-cache incremental runs. Run 3 figures are exact from Fabric's monitoring detail pane:

| Stage | Wall clock | Share of functional chain |
|---|---|---|
| Bronze (6 activities, parallel) | 74 s | 7% |
| Silver (`bronze-to-silver`) | 142 s | 13% |
| **Gold (`silver-to-gold` → `data_quality_checks`)** | **844 s** | **80%** |
| Functional total | **1,060 s (17m 40s)** | |

`silver-to-gold` alone is 638 s — **~60% of the entire functional chain**, and the unambiguous optimisation target. Bronze parallelism means the six ingestion activities cost only their slowest member (74 s), not their sum.

Optimisations applied on the strength of that measurement: V-Order on gold writes (where DirectLake reads accrue the benefit), broadcast joins on the small conformed dimensions, DataFrame caching of reusable lookups, and clustered/non-clustered warehouse indexes with statistics.

> **Retest pending.** The before/after comparison is measured under the same incremental, warm-cache methodology as the baseline and published in `performance_optimized.md` — including null or negative results. At portfolio scale a pipeline that is already fast may show no meaningful improvement; that is a valid finding, not a failed optimisation. No SLA or throughput target is claimed for this project.

---

## Scope boundaries and limitations

Stated because a risk model without stated boundaries is a liability:

- **Gross supply risk only.** No import-reliance blend of the global and EU indices into a single figure; no recycling (`EoL_RIR`) or substitution (`SI_SR`) adjustment. These are **not** official EU CRM Supply Risk values and must not be labelled as such.
- **Governance coverage is incomplete** for non-member states (Taiwan, permanently). Affected rows are flagged, and their risk is understated by construction.
- **The procurement ledger is synthetic.** No business conclusion should be drawn from the spend figures.
- **Supply shares are a 2023 annual snapshot**; `"<1%"` source values are treated as 0.5% midpoint estimates.
- **Bronze is a full load.** Incremental behaviour applies to silver and gold only.
- **Portfolio scale** (~500 procurement records). Nothing here has been load-tested.

---

## What I would do differently

- **Profile the source data before writing alias maps.** Most of the alias work was reactive; an upfront profiling pass would have surfaced the same mismatches faster and produced the mapping table as a by-product.
- **Decide the notebook/module duplication policy on day one.** Making it an asserted contract was the right answer, but it was reached after the drift had already appeared. Starting there would have been cheaper.
- **Establish the performance baseline earlier.** Optimisations were chosen partly on intuition before the measurement existed; the measurement then showed one stage dominated at ~60%, which would have redirected the earlier effort.
- **Treat coverage gaps as a first-class design input, not a late discovery.** The Taiwan case reframed how the whole index handles missing data — that lesson should have arrived at design time.

---

## Repository map

| Path | Contents |
|---|---|
| `fabric/*.Notebook/` | PySpark transformation notebooks (the code that runs) |
| `fabric/*.DataPipeline/` | Orchestrator definition (10 activities) |
| `fabric/*.SemanticModel/` | TMDL semantic model — model as code, not `.pbix` |
| `fabric/sql/` | SQL finding documents (e.g. why `CREATE INDEX` is rejected on Fabric DW) — reference, not deployed |
| `src/transformations/` | Testable mirror of the notebook logic |
| `tests/` | 235 pytest tests, incl. the notebook↔module parity contract |
| `.github/workflows/` | CI (tests) and CD (`fabric-cicd` deployment) |
| `docs/` | Architecture, schemas, runbooks, measure and quality guides |

---

*Companion project: [nordgrid-data-engineering](https://github.com/erikemilsson/nordgrid-data-engineering) — SQL/dbt depth (MERGE, stored procedures, SCD patterns, Airflow orchestration).*
