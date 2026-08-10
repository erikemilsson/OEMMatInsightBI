# OEMMatInsightBI — Portfolio Assets

**Project:** OEMMatInsightBI — Procurement Analytics & ESG Supply-Risk Intelligence
**Stack:** Microsoft Fabric (Lakehouse, Pipelines, Notebooks) · PySpark · Delta Lake · Power BI / DAX / TMDL · Azure SQL · GitHub Actions
**Status:** Built. Pipeline runs, semantic model ships 45 measures, report renders. Visual assets (screenshots, PDF) are generated from the live report.

> **Honesty frame (read first):** the procurement ledger is **synthetic**; the external data (EPI, WGI, EU CRM supply shares) is **real**. This project demonstrates *method and engineering*, not discovered business facts. The case study states this up front, and the portfolio assets below follow the same rule — they showcase what was built and how, not fabricated "findings." See [CASE_STUDY.md](./CASE_STUDY.md) for the full provenance statement.

---

## 1. Case study — `CASE_STUDY.md`

The portfolio centerpiece. Covers the problem, the medallion build, the data-quality observability layer, the HHI supply-risk methodology, the incremental-load / parity-contract engineering, and the honest null-result (Taiwan's permanent WGI gap). Suitable for a portfolio page, LinkedIn article, resume attachment, or interview discussion guide.

**Portfolio use:** publish to `erikemilsson.com`, link from resume, walk through in interviews.

---

## 2. Report design — `PORTFOLIO_DESIGN.md`

Power BI report design specification: page layouts, measure wiring, theme, and accessibility notes. Pairs with the live `report2.Report` (built from the `OEMInsightBI` semantic model).

**Demonstrates:** dashboard design thinking (visual hierarchy, storytelling), Power BI best practices (measure organization, DirectLake), and professional handoff-grade documentation.

---

## 3. DAX measure library — the as-built catalogue

**Source of truth:** `fabric/OEMInsightBI.SemanticModel/definition/tables/*.tmdl` (the live TMDL).
**Readable catalogue:** [`docs/dax_measure_library.md`](../dax_measure_library.md) — 45 measures transcribed from the live model.

The model has one canonical version (`OEMInsightBI`, DirectLake on `oem_lh`). Measures live on the table that owns their grain — there is no `_Measures` table — grouped with display folders:

| Group | Table(s) | Measures | What it shows |
|---|---|---|---|
| Procurement | `fact_procurement` | 5 | Spend, transaction/material/country counts |
| EPI scoring | `fact_epi_score` | 3 | Avg EPI, country coverage, weighted EPI score |
| Supply share | `fact_supply_share` | 1 | Supply concentration index |
| Supply risk (HHI) | `gold_supply_risk` | 3 | Global vs EU HHI + contrast |
| Data-gap coverage | `gold_data_gaps` | 16 | EPI/WGI coverage by country and spend |
| Quality observability | `gold_gap_registry`, `gold_quality_history`, `gold_low_confidence_audit` | 17 | Gap lifecycle, run history, low-confidence audit |
| **Total** | **8 measure tables** | **45** | |

**The interview narrative:** the model deliberately foregrounds **data-quality observability** — coverage %, gap resolution, threshold breaches, low-confidence audit — because *is the data trustworthy, and where are the holes* became the project's centre of gravity. That is a data-engineering judgment about what a model should surface, not just DAX breadth.

**DAX patterns in use:** `DIVIDE(...,0)` safe division, `VAR`/`RETURN`, `CALCULATE` boolean filters, `RELATED` inside `SUMX` (weighted EPI), `MAXX`-isolated latest-run metrics, display folders.

**Portfolio use:** link the specific `.tmdl` files as code samples; the catalogue doc is the readable companion.

---

## 4. Engineering artifacts (code samples)

| Artifact | Path | Why it's worth showing |
|---|---|---|
| Semantic model (TMDL) | `fabric/OEMInsightBI.SemanticModel/definition/` | Model-as-code: 14 tables, 10 relationships, 45 measures, DirectLake expression |
| Pipeline | `fabric/orchestrator_pipeline_bronze_to_gold.DataPipeline/` | 10-activity orchestration (Copy + Notebook) with per-activity retry policy |
| Silver→Gold notebook | `fabric/silver_to_gold.Notebook/` | Star-schema build + observability tables + Delta MERGE |
| Parity contract | `tests/test_notebook_parity.py`, `src/transformations/` | `src/` is a tested mirror of notebook logic; CI pins parity (Task-032) |
| Data quality | `fabric/data_quality_checks.Notebook/`, `src/transformations/data_quality.py` | Blocking DQ gate + observability population |
| EPI/WGI ingestion | `fabric/bronze_ingest_epi.Notebook/`, `fabric/bronze_ingest_wgi.Notebook/` | Automated HTTP/API ingestion of real public datasets |

---

## 5. Visual assets

Generated from the live `report2.Report` in the Fabric workspace:

| Asset | How to produce | Use |
|---|---|---|
| Dashboard screenshots | Power BI Desktop → Export / OS screenshot at 1920×1080 | Portfolio hero images, LinkedIn, case-study figures |
| PDF export | Power BI Desktop → File → Export → PDF | Email attachment, printable portfolio piece |
| PBIX | Save from Power BI Desktop | Interactive sharing (data is synthetic/public-safe) |

These are produced from the *real* report on the *real* model — no mockups or "implementation pending" placeholders.

---

## What recruiters / interviewers see

**Technical skills validated:** DAX (time intelligence, weighted aggregation, safe division, `SUMX`/`RELATED`), data modeling (star schema, DirectLake), data engineering (medallion, PySpark, Delta MERGE, incremental load), data quality (ISO 25012 framework, observability tables, blocking gate), CI/CD (`fabric-cicd` deploy, GitHub Actions), testing (235-test parity contract).

**Engineering judgment demonstrated:** honest null-result handling (Taiwan WGI gap surfaced, not coerced to 0), measured baselines over guessed numbers, the parity contract as deliberate drift-prevention, six defended decisions in the case study.

---

## Recommended next actions

1. **Publish the case study** → `erikemilsson.com` + LinkedIn (reframed around method, not "findings" — see template below).
2. **Upload to GitHub** → the repo *is* the portfolio; the README links the case study and featured code.
3. **Capture visual assets** → screenshots + PDF from the live report.

---

## LinkedIn post template (honest framing)

> 📊 Shared a new end-to-end data-engineering project: OEMMatInsightBI — procurement analytics & supply-risk intelligence on Microsoft Fabric.
>
> What it demonstrates:
> ✅ A medallion lakehouse (Bronze/Silver/Gold) with PySpark + Delta MERGE and an incremental-load strategy with measured runtimes
> ✅ A DirectLake semantic model with 45 DAX measures, including a data-quality observability layer (coverage %, gap registry, threshold breaches)
> ✅ Real external data (Yale EPI, World Bank WGI, EU CRM supply shares) automated via HTTP/API ingestion, joined to a synthetic procurement ledger
> ✅ A 235-test parity contract that pins notebook logic to a tested `src/` mirror, and an honest null-result (Taiwan's permanent WGI gap surfaced, not coerced to zero)
>
> The procurement ledger is synthetic, so the project makes claims about *method and engineering*, not discovered business facts — I've written that up explicitly in the case study.
>
> Tech: Microsoft Fabric, PySpark, Delta Lake, Power BI / DAX / TMDL, Azure SQL, GitHub Actions.
>
> Full write-up: [link to case study]
>
> #DataEngineering #MicrosoftFabric #PowerBI #DAX #SupplyChainAnalytics

> **Why this framing:** the case study states up front that the spend figures are illustrative. A LinkedIn post that claims "identified 4 high-risk materials" or quotes a spend-weighted EPI gap as a discovered finding would contradict that honesty frame and misrepresent synthetic-data output as a business result. The template above advertises the *engineering* and is explicit about the synthetic ledger.

---

## File locations

| Asset | Path | Status |
|---|---|---|
| Case study | `docs/portfolio/CASE_STUDY.md` | ✅ Ready |
| Report design | `docs/portfolio/PORTFOLIO_DESIGN.md` | ✅ Ready |
| DAX measure catalogue | `docs/dax_measure_library.md` | ✅ Ready (as-built, 45 measures) |
| Semantic model | `fabric/OEMInsightBI.SemanticModel/` | ✅ Built |
| Report | `fabric/report2.Report/` | ✅ Built |
| Pipeline | `fabric/orchestrator_pipeline_bronze_to_gold.DataPipeline/` | ✅ Built |
| Tests | `tests/` | ✅ 235 tests |
| Screenshots / PDF / PBIX | produced from the live report | ⏳ Capture on demand |