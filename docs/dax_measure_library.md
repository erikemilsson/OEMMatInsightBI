# DAX Measure Library — OEMMatInsightBI

**Status:** As-built (mirrors the live TMDL)
**Source of truth:** `fabric/OEMInsightBI_v2.SemanticModel/definition/tables/*.tmdl`
**Semantic model:** `OEMInsightBI_v2` · DirectLake on the `oem_lh` lakehouse (NOT a warehouse — see `architecture/semantic_model.md`)

## Summary

The semantic model ships **45 measures** across **8 measure-bearing tables** (14 tables total), connected by **10 active relationships** over a star schema of 3 fact tables + 5 dimension tables. Measures live on the tables that own their grain — there is no separate `_Measures` table — and are grouped with display folders (`Data Gaps`, `Quality Observability`).

A second surface — four gold observability tables (`gold_data_gaps`, `gold_gap_registry`, `gold_quality_history`, `gold_low_confidence_audit`) — carries the model's data-quality observability story, exposed to report consumers through dedicated measures.

| Surface | Tables | Measures |
|---|---|---|
| Procurement | `fact_procurement` | 5 |
| EPI scoring | `fact_epi_score` | 3 |
| Supply share | `fact_supply_share` | 1 |
| Supply risk | `gold_supply_risk` | 3 |
| Data-gap coverage | `gold_data_gaps` | 16 |
| Quality observability | `gold_gap_registry`, `gold_quality_history`, `gold_low_confidence_audit` | 7 + 5 + 5 |
| **Total** | **8 measure tables** | **45** |

---

## 1. Star schema & relationships

**Fact tables (3):**
- `fact_procurement` — procurement transactions (spend, quantity, price, keys to date/material/country)
- `fact_epi_score` — Environmental Performance Index scores by country × indicator × year
- `fact_supply_share` — global/EU supply-chain shares by material × country × stage

**Dimension tables (5):**
- `gold_dim_date` — calendar (date_key, year, …)
- `gold_dim_country` — countries (country_key, country_name_std, iso3, region)
- `gold_dim_material` — materials (material_key, material_name, commodity_group)
- `gold_dim_indicator` — ESG indicators (indicator_key, abbrev, type, source_system, weight)
- `gold_dim_stage` — supply-chain stages (stage_key, stage_name: Extraction/Processing/Manufacturing)

**Derived gold table:**
- `gold_supply_risk` — precomputed HHI concentration per material × stage × year (consumed by the risk measures; also related to `gold_dim_material` and `gold_dim_stage`)

### Relationships (10, all active)

```
fact_procurement
  ├─ gold_dim_date      (date_key             → date_key)
  ├─ gold_dim_country   (production_country_key → country_key)   ← active country rel
  └─ gold_dim_material  (material_key         → material_key)

fact_epi_score
  ├─ gold_dim_country   (country_key          → country_key)
  └─ gold_dim_indicator (indicator_key        → indicator_key)

fact_supply_share
  ├─ gold_dim_country   (country_key          → country_key)
  ├─ gold_dim_material  (material_key         → material_key)
  └─ gold_dim_stage      (stage_key            → stage_key)

gold_supply_risk
  ├─ gold_dim_material  (material_key         → material_key)
  └─ gold_dim_stage      (stage_key            → stage_key)
```

> **Note on the country relationship.** `fact_procurement` carries both `production_country_key` and `supplier_hq_country_key`, but only `production_country_key` has an active relationship to `gold_dim_country`. `supplier_hq_country_key` is an attribute column accessed via `DISTINCTCOUNT` in the `Supplier Countries Count` measure — it is not a relationship path. Earlier drafts of this doc described `supplier_hq_country_key` as the active relationship; that was wrong.

---

## 2. Measures by table

### 2.1 `fact_procurement` — procurement (5)

| Measure | DAX | Format |
|---|---|---|
| `Total Spend EUR` | `SUM(fact_procurement[spend_eur])` | general |
| `Transaction Count` | `COUNTROWS(fact_procurement)` | `0` |
| `Materials Count` | `DISTINCTCOUNT(fact_procurement[material_key])` | `0` |
| `Supplier Countries Count` | `DISTINCTCOUNT(fact_procurement[supplier_hq_country_key])` | `0` |
| `Total Spend by Country` | `SUM(fact_procurement[spend_eur])` | general |

`Supplier Countries Count` counts the supplier-HQ country attribute directly rather than traversing the country dimension (which is related on `production_country_key`, not `supplier_hq_country_key`). `Total Spend by Country` reuses `Total Spend EUR` semantics and is intended to be sliced by `gold_dim_country` (the production-country relationship).

### 2.2 `fact_epi_score` — EPI scoring (3)

**`Avg EPI Score`**
```dax
CALCULATE(AVERAGE(fact_epi_score[score]), gold_dim_indicator[abbrev] = "EPI")
```
Average score restricted to the parent EPI indicator row (`abbrev = "EPI"`), not its sub-indicators.

**`Countries with EPI Data`**
```dax
CALCULATE(DISTINCTCOUNT(fact_epi_score[country_key]), gold_dim_indicator[abbrev] = "EPI")
```
Distinct countries that have a top-level EPI score. Format `0`.

**`Weighted EPI Score`** — the portfolio's headline weighted-aggregation measure:
```dax
VAR EpiSubIndicators =
    FILTER(
        gold_dim_indicator,
        gold_dim_indicator[source_system] = "EPI"
            && gold_dim_indicator[abbrev] <> "EPI"
            && gold_dim_indicator[type] = "Indicator"
    )
VAR WeightedScores =
    CALCULATE(
        SUMX(
            fact_epi_score,
            fact_epi_score[score] * RELATED(gold_dim_indicator[weight])
        ),
        EpiSubIndicators
    )
VAR TotalWeights =
    CALCULATE(SUM(gold_dim_indicator[weight]), EpiSubIndicators)
RETURN
    DIVIDE(WeightedScores, TotalWeights, 0)
```
Weighted by `gold_dim_indicator[weight]` (sourced from EPI's `epi2024weights.csv`; see `epi_wgi_ingestion.md` / the Weighted EPI Score note in the root `CLAUDE.md`). The filter excludes the parent `EPI` row and the `Index`/`Objective` rollups so only `type = "Indicator"` sub-indicators contribute — this is why the measure renders a 0–100 score only after the weights table is loaded (a `NULL` weight collapses it to 0 via the `DIVIDE(..., 0)` fallback).

### 2.3 `fact_supply_share` — supply share (1)

| Measure | DAX |
|---|---|
| `Supply Concentration Index` | `CALCULATE(MAX(fact_supply_share[share_pct]), fact_supply_share[supply_mix] = "global")` |

The maximum single-country share within the `global` supply mix — a quick concentration signal complementary to the HHI measures on `gold_supply_risk`.

### 2.4 `gold_supply_risk` — HHI supply risk (3)

| Measure | DAX |
|---|---|
| `Supply Risk (Global)` | `MAX(gold_supply_risk[hhi_global])` |
| `Supply Risk (EU Sourcing)` | `MAX(gold_supply_risk[hhi_eu_sourcing])` |
| `Supply Risk Contrast` | `DIVIDE([Supply Risk (EU Sourcing)], [Supply Risk (Global)])` |

The HHI (Herfindahl–Hirschman Index) is precomputed in the gold transform; these measures surface the max concentration across the current filter context and the EU-vs-global contrast ratio. A contrast > 1 flags materials where EU sourcing is more concentrated than the global baseline.

### 2.5 `gold_data_gaps` — data-gap coverage (16, folder: `Data Gaps`)

Coverage of EPI and WGI scores across procurement countries and spend. All measures live under the `Data Gaps` display folder.

**EPI coverage**

| Measure | DAX | Format |
|---|---|---|
| `Procurement Countries with EPI` | `CALCULATE(DISTINCTCOUNT(gold_data_gaps[country_key]), gold_data_gaps[has_epi_score] = TRUE)` | `#,##0` |
| `Procurement Countries without EPI` | `CALCULATE(DISTINCTCOUNT(gold_data_gaps[country_key]), gold_data_gaps[has_epi_score] = FALSE)` | `#,##0` |
| `EPI Country Coverage %` | `DIVIDE([Procurement Countries with EPI], [Procurement Countries with EPI] + [Procurement Countries without EPI], 0)` | `0.0%` |
| `Procurement Spend with EPI` | `CALCULATE(SUM(gold_data_gaps[spend_eur]), gold_data_gaps[has_epi_score] = TRUE)` | `€#,##0` |
| `Procurement Spend without EPI` | `CALCULATE(SUM(gold_data_gaps[spend_eur]), gold_data_gaps[has_epi_score] = FALSE)` | `€#,##0` |
| `EPI Spend Coverage %` | `DIVIDE([Procurement Spend with EPI], SUM(gold_data_gaps[spend_eur]), 0)` | `0.0%` |

**WGI coverage**

| Measure | DAX | Format |
|---|---|---|
| `Procurement Countries with WGI` | `CALCULATE(DISTINCTCOUNT(gold_data_gaps[country_key]), gold_data_gaps[has_wgi_score] = TRUE)` | `#,##0` |
| `Procurement Countries without WGI` | `CALCULATE(DISTINCTCOUNT(gold_data_gaps[country_key]), gold_data_gaps[has_wgi_score] = FALSE)` | `#,##0` |
| `WGI Country Coverage %` | `DIVIDE([Procurement Countries with WGI], [Procurement Countries with WGI] + [Procurement Countries without WGI], 0)` | `0.0%` |

**Combined coverage**

| Measure | DAX | Format |
|---|---|---|
| `Full Indicator Coverage` | `CALCULATE(DISTINCTCOUNT(gold_data_gaps[country_key]), gold_data_gaps[has_epi_score] = TRUE && gold_data_gaps[has_wgi_score] = TRUE)` | `#,##0` |
| `Partial Coverage` | countries with exactly one of EPI/WGI | `#,##0` |
| `No Coverage` | `CALCULATE(DISTINCTCOUNT(gold_data_gaps[country_key]), gold_data_gaps[has_epi_score] = FALSE && gold_data_gaps[has_wgi_score] = FALSE)` | `#,##0` |
| `Full Coverage %` | `DIVIDE([Full Indicator Coverage], [Total Procurement Countries], 0)` | `0.0%` |

`Partial Coverage` DAX:
```dax
CALCULATE(
    DISTINCTCOUNT(gold_data_gaps[country_key]),
    (gold_data_gaps[has_epi_score] = TRUE  && gold_data_gaps[has_wgi_score] = FALSE) ||
    (gold_data_gaps[has_epi_score] = FALSE && gold_data_gaps[has_wgi_score] = TRUE)
)
```

**Rollup helpers**

| Measure | DAX | Format |
|---|---|---|
| `Total Procurement Countries` | `DISTINCTCOUNT(gold_data_gaps[country_key])` | `#,##0` |
| `EPI Gap Summary` | `FORMAT([Procurement Countries with EPI], "#") & " of " & FORMAT([Total Procurement Countries], "#") & " countries"` | text |
| `Coverage Summary` | `FORMAT([Full Indicator Coverage], "#") & " of " & FORMAT([Total Procurement Countries], "#") & " countries have full coverage"` | text |

### 2.6 `gold_gap_registry` — gap registry (7, folder: `Quality Observability`)

Lifecycle measures over tracked data gaps (`Open` / `Resolved`).

| Measure | DAX | Format |
|---|---|---|
| `Open Gaps Count` | `CALCULATE(COUNTROWS(gold_gap_registry), gold_gap_registry[current_status] = "Open")` | `#,##0` |
| `Resolved Gaps Count` | `CALCULATE(COUNTROWS(gold_gap_registry), gold_gap_registry[current_status] = "Resolved")` | `#,##0` |
| `Total Gaps Count` | `COUNTROWS(gold_gap_registry)` | `#,##0` |
| `Gap Resolution Rate` | `DIVIDE([Resolved Gaps Count], [Total Gaps Count], 0)` | `0.0%` |
| `Avg Gap Age Days` | `AVERAGEX(FILTER(gold_gap_registry, gold_gap_registry[current_status] = "Open"), DATEDIFF(gold_gap_registry[first_seen], TODAY(), DAY))` | `#,##0` |
| `Total Gap Occurrences` | `SUM(gold_gap_registry[total_occurrences])` | `#,##0` |
| `Estimated Gap Impact` | `SUM(gold_gap_registry[estimated_impact])` | `€#,##0` |

### 2.7 `gold_quality_history` — quality history (5, folder: `Quality Observability`)

Point-in-time quality metrics per pipeline run.

| Measure | DAX | Format |
|---|---|---|
| `Latest Coverage Rate` | latest run's `coverage_rate` metric value (see below) | `0.0%` |
| `Latest Match Rate` | latest run's `match_rate` metric value | `0.0%` |
| `Pipeline Runs Count` | `DISTINCTCOUNT(gold_quality_history[refresh_timestamp])` | `#,##0` |
| `Threshold Breaches` | `CALCULATE(COUNTROWS(gold_quality_history), gold_quality_history[breach_flag] = TRUE)` | `#,##0` |
| `Quality Metrics Count` | `COUNTROWS(gold_quality_history)` | `#,##0` |

`Latest Coverage Rate` (the `Latest Match Rate` measure follows the same pattern with `metric_name = "match_rate"`):
```dax
VAR LatestRun = MAXX(gold_quality_history, gold_quality_history[refresh_timestamp])
RETURN
    CALCULATE(
        AVERAGE(gold_quality_history[metric_value]),
        gold_quality_history[refresh_timestamp] = LatestRun,
        gold_quality_history[metric_name] = "coverage_rate"
    )
```

### 2.8 `gold_low_confidence_audit` — low-confidence alias matches (5, folder: `Quality Observability`)

Surfaces the alias-matching friction that the silver→gold confidence threshold defers to human review.

| Measure | DAX | Format |
|---|---|---|
| `Low Confidence Matches Count` | `COUNTROWS(gold_low_confidence_audit)` | `#,##0` |
| `Avg Match Confidence` | `AVERAGE(gold_low_confidence_audit[confidence])` | `0.00` |
| `Low Confidence Spend Impact` | `SUM(gold_low_confidence_audit[spend_impact])` | `€#,##0` |
| `Low Confidence Frequency` | `SUM(gold_low_confidence_audit[frequency])` | `#,##0` |
| `Critical Low Confidence Count` | `CALCULATE(COUNTROWS(gold_low_confidence_audit), gold_low_confidence_audit[confidence] < 0.80)` | `#,##0` |

---

## 3. Observability surface

The four gold observability tables exist so the report can show *data quality as a first-class metric* rather than an afterthought. They are populated by the `data_quality_analysis` notebook and the `pipeline_error_handler` (which runs on every pipeline outcome).

| Table | Role | Key measures |
|---|---|---|
| `gold_data_gaps` | EPI/WGI coverage per procurement country + spend | 16 coverage measures (§2.5) |
| `gold_gap_registry` | Tracked gaps with Open→Resolved lifecycle, occurrences, € impact | 7 lifecycle measures (§2.6) |
| `gold_quality_history` | Per-run quality metrics (coverage_rate, match_rate, breach_flag) | 5 run-history measures (§2.7) |
| `gold_low_confidence_audit` | Alias matches below the confidence threshold, with spend impact | 5 confidence measures (§2.8) |

See `data_quality_architecture.md` for the shipped design and `data_quality_framework.md` for the ISO 25012 framework rationale.

---

## 4. DAX patterns in use

- **`DIVIDE(numerator, denominator, 0)`** everywhere a ratio is computed — safe division with explicit zero fallback (the `Weighted EPI Score` collapse-to-0 case is a direct consequence).
- **`VAR` / `RETURN`** for any non-trivial measure (`Weighted EPI Score`, all the coverage-rate and resolution-rate ratios, the latest-run quality metrics) — variables make filter context explicit and avoid re-evaluation.
- **`CALCULATE` with boolean filter arguments** (`gold_data_gaps[has_epi_score] = TRUE`) for conditional aggregation.
- **`RELATED`** to pull `weight` from `gold_dim_indicator` into a row-context `SUMX` (`Weighted EPI Score`) — the only measure that crosses a relationship inside a row iteration.
- **`MAXX` + `CALCULATE`** to isolate the latest pipeline run (`gold_quality_history` measures) rather than relying on a TOPN visual.
- **`FORMAT`-concatenated text measures** (`EPI Gap Summary`, `Coverage Summary`) for headline cards.
- **Display folders** (`Data Gaps`, `Quality Observability`) keep the field list scannable rather than hiding measures in a `_Measures` table.

## 5. Regenerating this doc

The measures above are transcribed from the live TMDL. To regenerate after a model change, the source of truth is:

```
fabric/OEMInsightBI_v2.SemanticModel/definition/tables/*.tmdl
fabric/OEMInsightBI_v2.SemanticModel/definition/relationships.tmdl
fabric/OEMInsightBI_v2.SemanticModel/definition/expressions.tmdl
```

Each `measure '<name>' = <expr>` block in a table TMDL is one row in the tables above; `displayFolder:` annotations map to the folder groupings; `formatString:` maps to the Format column.