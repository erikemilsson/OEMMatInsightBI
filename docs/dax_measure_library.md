# DAX Measure Library — OEMMatInsightBI

**Status:** As-built (mirrors the live TMDL)
**Source of truth:** `fabric/OEMInsightBI.SemanticModel/definition/tables/*.tmdl`
**Semantic model:** `OEMInsightBI` · DirectLake on the `oem_lh` lakehouse (NOT a warehouse — see `architecture/semantic_model.md`)

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
AVERAGEX(
    VALUES(gold_dim_country[country_key]),
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
        DIVIDE(WeightedScores, TotalWeights)
)
```
Weighted by `gold_dim_indicator[weight]` (sourced from EPI's `epi2024weights.csv`; see `epi_wgi_ingestion.md` and `decision-013-epi-weight-sourcing-gold-dim-indicator-rebuild.md`). The 58 sub-indicator weights sum to 100. The filter excludes the parent `EPI` row and the `Index`/`Objective` rollups so only `type = "Indicator"` sub-indicators contribute — which is why the measure renders a 0–100 score only after the weights table is loaded.

**Reads 0–100 at every grain, including the grand total (task-061).** The inner `VAR`/`RETURN` body is the weighted average for *one* country; the `AVERAGEX` wrapper is what makes it safe to place on an uncontexted card. Without the wrapper the denominator did not scale with country cardinality — `TotalWeights` sums the 58 sub-indicator weights (= 100) once regardless of context, while `WeightedScores` fans out over every country in context, so the uncontexted measure returned the *sum* of the per-country scores (measured 7945.40 across 180 countries on 2026-08-11) instead of a score. Wrapped, a single-country context is bit-for-bit unchanged (verified against the live model: max delta 0.0 across all 194 country keys) and the grand total is the mean across the countries in context (44.14 world-wide, 58.59 filtered to `region = "Europe"`). "Every grain" means the value is always a score rather than a running sum — it does **not** mean every axis filters it; see the non-country-grain caveat below.

**No `0` fallback on the `DIVIDE` — defensive hygiene, not a behaviour change.** The pre-task-061 measure ended `DIVIDE(WeightedScores, TotalWeights, 0)`; the `0` was dropped alongside the wrapper. Dropping it changed nothing observable, because **the alternate result was unreachable here**. DAX substitutes the third argument only when the *denominator* is blank or zero **and** the numerator is non-blank; a **blank numerator returns BLANK regardless of the denominator**. Measured on this model 2026-08-11: `DIVIDE(BLANK(), 58, 0)`, `DIVIDE(BLANK(), BLANK(), 0)` and `DIVIDE(BLANK(), 0, 0)` all return BLANK, while the positive controls `DIVIDE(1, BLANK(), 0)`, `DIVIDE(1, 0, 0)` and `DIVIDE(0, 0, 0)` return `0` and `DIVIDE(0, BLANK(), 7)` returns `7`. In this measure `TotalWeights` can only go blank when `EpiSubIndicators` is empty or every visible weight is BLANK — and both of those force `WeightedScores` blank too (a `SUMX` over an empty filtered fact is BLANK; `score × BLANK` is BLANK). Numerator and denominator go blank together, so the `0` branch had no way in. `TotalWeights = 0` exactly is unreachable as well: the 58 sub-indicator weights sum to `100.00000011920929`, the minimum is `0.1`, and no row has a blank or zero weight. Confirmed against the live, still-unwrapped measure for the exact scenario the fallback was supposed to cover — `CALCULATE([Weighted EPI Score], gold_dim_indicator[source_system] = "WGI")` returns BLANK, not `0`.

The `0` stays off because a missing external score must never coerce to `0`: `0` is a legitimate EPI value meaning *worst environmental performance*, so a fallback that ever did fire would mislabel a data gap as a catastrophic score, and BLANK countries are skipped by `AVERAGEX` rather than dragging the mean down. Same rule as the `NULL`-governance handling in `data_quality_framework.md`. But this is insurance against a future edit that makes the numerator non-blank independently of the denominator — **not** a fix for an observed zero. In particular, the pre-task-056 all-NULL-weight state did *not* render `0`: `silver_to_gold.Notebook` (line 1196), `bronze_ingest_epi.Notebook` (lines 232–233) and `decision-013` all record that it rendered BLANK.

**Caveat — the wrapper makes a non-country grain look plausible rather than obviously broken.** `fact_epi_score` has no material grain, so grouping this measure by anything that does not filter countries leaves every row with the same country set, and every row therefore returns the same world-wide mean. Measured 2026-08-11, all 13 `gold_dim_material[commodity_group]` rows return exactly `44.14112500396361` — identical to the grand total. That is expected, not a defect, but it is a *quieter* failure mode than before: the unwrapped measure returned a constant `7945.40` on those same rows, a number no reviewer would accept, whereas the wrapped one returns a constant that reads as a real score. Slice this measure by country or a country attribute, and read a value repeating identically down a non-country axis as the signal that the axis does not filter `fact_epi_score`.

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
| `Latest Coverage Rate` | `coverage_rate` at *its own* latest run, ÷ 100 (see below) | `0.0%` |
| `Latest Match Rate` | `match_rate` at *its own* latest run, ÷ 100 | `0.0%` |
| `Pipeline Runs Count` | `DISTINCTCOUNT(gold_quality_history[refresh_timestamp])` | `#,##0` |
| `Threshold Breaches` | `CALCULATE(COUNTROWS(gold_quality_history), gold_quality_history[breach_flag] = TRUE)` | `#,##0` |
| `Quality Metrics Count` | `COUNTROWS(gold_quality_history)` | `#,##0` |

`Latest Coverage Rate` (the `Latest Match Rate` measure is structurally identical, with `metric_name = "match_rate"` in both places):
```dax
VAR LatestRun =
    CALCULATE(
        MAX(gold_quality_history[refresh_timestamp]),
        gold_quality_history[metric_name] = "coverage_rate"
    )
VAR LatestValue =
    CALCULATE(
        AVERAGE(gold_quality_history[metric_value]),
        gold_quality_history[refresh_timestamp] = LatestRun,
        gold_quality_history[metric_name] = "coverage_rate"
    )
RETURN
    DIVIDE(LatestValue, 100)
```

Two things are load-bearing here, and **shipping only the first re-introduces the second**:

1. **`LatestRun` is resolved per metric, not table-wide.** The `metric_name` boolean filter inside `CALCULATE` overrides any `metric_name` filter in the outer context, so each measure finds the newest run *that actually carries its own metric*. Filters on every other column (a date slicer, `entity`, `layer`, `producer`) still apply, so the measure stays responsive exactly as the previous `MAXX` form was — measured: slicing to `refresh_timestamp < 2026-07-23` returns `99.436%` against `99.418%` unfiltered, and slicing by `entity` splits the unfiltered figure into its two constituent rows (`fact_procurement` `99.091%`, `fact_supply_share` `99.745%`, mean `99.418%`). With no slicer the measure therefore averages *all* entity rows of that metric in the latest run, which is the pre-existing `AVERAGE` grain, not something this fix introduced.
2. **`DIVIDE(…, 100)` converts the stored whole percentage to a fraction.** The producers write `99.42` to mean 99.42%, but `0.0%` is a *percent* format string and multiplies by 100 on render. **The measure side was changed, not the format string** — `0.0%` is retained so these two match the model's other rate measures (`Gap Resolution Rate` = `0.4` → `40.0%`), which all store a fraction under a percent format. Measured control: `FORMAT(99.41791580255338, "0.0%;-0.0%;0.0%")` = `"9941.8%"`, which is precisely what a `LatestRun`-only fix would have shipped.

> **History — the defect this replaced (diagnosed under task-061 2026-08-11, fixed under task-065 2026-08-12).** Both measures previously read `VAR LatestRun = MAXX(gold_quality_history, gold_quality_history[refresh_timestamp])`, taking the max `refresh_timestamp` over the *whole* table. Two notebooks append to `gold_quality_history` in the same pipeline run, each stamping its own `pipeline_run_ts`: `silver_to_gold` writes `coverage_rate` / `match_rate`, then `data_quality_checks` writes `dq_*` rows ~10 minutes later. The later timestamp therefore always won and never carried either metric, so the `refresh_timestamp = LatestRun` and `metric_name = "…"` filters intersected to nothing and both measures returned BLANK in every filter context — a computation defect, not a data gap. Measured 2026-08-11: newest `match_rate` at `2026-08-11T04:06:33` = `99.42`, table max `2026-08-11T04:17:09` (producer `data_quality_checks`, all `dq_*`). Still reproducible on the live model 2026-08-12 with a fresh pipeline run — table max `2026-08-12T16:06:16.627`, producer `data_quality_checks`, **zero** `match_rate` rows at that timestamp, and both published measures `ISBLANK` = `TRUE` — while the new expressions return `99.4%` / `99.9%` over the same data. `producer` was considered as the discriminator and rejected: the column was added part-way through the table's life, so **541 of 3,361 rows carry a NULL `producer`** — every one of them stamped at or before `2026-07-22T19:53:09.09`, with the first non-NULL at `2026-07-22T23:55:45.623`. A `producer = "silver_to_gold"` filter would therefore silently drop the table's own history, whereas `metric_name` is populated on every row.

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

- **`DIVIDE(numerator, denominator, alternate)`** for safe division without the `/0` error. The third argument substitutes **only when the denominator is blank or zero *and* the numerator is non-blank** — a blank numerator returns BLANK whatever the third argument says, so the alternate result can neither rescue a blank numerator nor corrupt one (measured on this model under task-061; discriminator and controls in § 2.2). Supply it where a blank/zero denominator has a real answer (a resolution rate over zero gaps is genuinely 0%). Omit it for scored quantities, where `0` is itself a meaningful value — `Weighted EPI Score` omits it, though *defensively* rather than to change behaviour: its numerator and denominator always go blank together, so the fallback was unreachable in either form.
- **`VAR` / `RETURN`** for any non-trivial measure (`Weighted EPI Score`, all the coverage-rate and resolution-rate ratios, the latest-run quality metrics) — variables make filter context explicit and avoid re-evaluation.
- **`CALCULATE` with boolean filter arguments** (`gold_data_gaps[has_epi_score] = TRUE`) for conditional aggregation.
- **`RELATED`** to pull `weight` from `gold_dim_indicator` into a row-context `SUMX` (`Weighted EPI Score`) — the only measure that crosses a relationship inside a row iteration.
- **Nested `CALCULATE(MAX(…), <same-column filter>)`** to isolate the latest pipeline run *for one metric* (`gold_quality_history` measures) rather than relying on a TOPN visual. The inner filter is what makes it correct: a bare `MAXX` over the table finds the newest row of *any* metric, which in a table several producers append to is usually not a row the measure wants (§ 2.7).
- **`FORMAT`-concatenated text measures** (`EPI Gap Summary`, `Coverage Summary`) for headline cards.
- **Display folders** (`Data Gaps`, `Quality Observability`) keep the field list scannable rather than hiding measures in a `_Measures` table.

## 5. Regenerating this doc

The measures above are transcribed from the live TMDL. To regenerate after a model change, the source of truth is:

```
fabric/OEMInsightBI.SemanticModel/definition/tables/*.tmdl
fabric/OEMInsightBI.SemanticModel/definition/relationships.tmdl
fabric/OEMInsightBI.SemanticModel/definition/expressions.tmdl
```

Each `measure '<name>' = <expr>` block in a table TMDL is one row in the tables above; `displayFolder:` annotations map to the folder groupings; `formatString:` maps to the Format column.