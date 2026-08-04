# Semantic Model — OEMMatInsightBI

## Overview

**Model:** `OEMInsightBI_v2.SemanticModel`
**Mode:** DirectLake (queries run directly against Delta tables in the `oem_lh` lakehouse)
**Schema:** Star schema — 3 fact tables + 5 dimension tables + 1 derived gold table (`gold_supply_risk`)
**Relationships:** 10, all active, single-direction (dimension → fact)
**DAX measures:** 45 across 8 measure-bearing tables — see `dax_measure_library.md` for the full as-built catalogue
**Refresh:** DirectLake auto-refreshes when the underlying lakehouse tables change (no scheduled refresh needed)

## DirectLake configuration

The model reads from the **`oem_lh` lakehouse**, not a warehouse. The single source expression (`expressions.tmdl`) is:

```
expression 'DirectLake - oem_lh' =
    let
        Source = AzureStorage.DataLake("https://onelake.dfs.fabric.microsoft.com/99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9/488fb9f8-e635-4683-90c4-ba4fee9dfadb", [HierarchicalNavigation=true])
    in
        Source
```

The GUIDs are the workspace ID and the `oem_lh` lakehouse ID. There is no warehouse, no `copyjob1`, and no SQL endpoint in the path — DirectLake binds to the lakehouse's Delta tables directly. (An earlier version of this doc named `oem_wh` as the source; that was wrong.)

`PBI_IncludeFutureArtifacts = False` plus the `PBI_RemovedChildren` annotation pins the model to an explicit allowlist of 14 tables — bronze/silver tables and helper/lookup tables that exist in the lakehouse are deliberately excluded from the model so they don't surface in the report field list.

### Benefits / limitations

**Benefits:** near-real-time data (no import lag); queries run directly on Delta/parquet; automatic refresh on lakehouse table update; lower memory footprint than Import mode.

**Limitations:** calculated tables and some DAX features are not supported in DirectLake; performance depends on the underlying Delta layout (V-Order is recommended — see `performance_optimized.md`); falls back to DirectQuery automatically for unsupported operations.

## Star schema

```
                       gold_dim_date
                            │ date_key
                            │
  gold_dim_material ─── fact_procurement ─── gold_dim_country
        │ material_key         │                  ▲ production_country_key
        │                      │ date_key
        │
        ├────────────── fact_supply_share ─── gold_dim_country
        │                │ material_key          │ country_key
   gold_dim_stage ───────┘ │ stage_key
        │                    │ country_key
        │
   gold_dim_indicator ── fact_epi_score ─── gold_dim_country
        │ indicator_key        │ country_key

   gold_supply_risk ─── gold_dim_material  (material_key)
        │             └── gold_dim_stage    (stage_key)
```

## Tables (14)

### Fact tables

**`fact_procurement`** — one row per procurement transaction
- Columns: `date_key`, `material_key`, `supplier_hq_country_key`, `production_country_key`, `quantity_base`, `unitprice_eur`, `spend_eur`, `data_quality_score`, `quality_category`, `source_row_id`
- Foreign keys: `date_key` → `gold_dim_date`, `material_key` → `gold_dim_material`, `production_country_key` → `gold_dim_country`
- `supplier_hq_country_key` is an attribute column (counted by the `Supplier Countries Count` measure) — it is **not** a relationship path
- Source: built by `silver-to-gold2` from `silver_procurement`
- Measures: 5 (`Total Spend EUR`, `Transaction Count`, `Materials Count`, `Supplier Countries Count`, `Total Spend by Country`)

**`fact_supply_share`** — one row per material × stage × country × year × supply mix
- Columns: `material_key`, `stage_key`, `country_key`, `year`, `share_pct`, `data_quality_score`, `quality_category`, `has_unmapped_material`, `has_unmapped_country`, `unmapped_impact_score`, `source_row_id`, `supply_mix`, `t`, `wgi_year`, `wgi_weight`
- Foreign keys: `material_key`, `stage_key`, `country_key`
- Source: built by `silver-to-gold2` from `silver_globalsupplyshares` / `silver_eusupplyshares`
- Measures: 1 (`Supply Concentration Index`)

**`fact_epi_score`** — one row per country × indicator × year
- Columns: `country_key`, `indicator_key`, `year`, `score`
- Foreign keys: `country_key` → `gold_dim_country`, `indicator_key` → `gold_dim_indicator`
- Source: built by `silver-to-gold2` from `silver_epi2024results` (pivoted from wide to long)
- Measures: 3 (`Avg EPI Score`, `Countries with EPI Data`, `Weighted EPI Score`)

### Dimension tables

**`gold_dim_country`** — `country_key`, `iso3`, `iso_numeric`, `wb_code`, `country_name_std`, `region`, `is_placeholder`
**`gold_dim_date`** — `date_key`, `date`, `year`, `month`, `day`, `month_name`, `quarter`, `day_of_week`, `week_of_year`
**`gold_dim_material`** — `material_key`, `material_name_std`, `commodity_group`, `unit_base`, `is_placeholder`
**`gold_dim_indicator`** — `indicator_key`, `source_system`, `type`, `abbrev`, `variable_name`, `policyobjective`, `issuecategory`, `indicator_code`, `description`, `parent_indicator`, `weight`
**`gold_dim_stage`** — `stage_key`, `stage_code`, `stage_name`

Surrogate keys (`country_key`, `material_key`, `indicator_key`, `stage_key`) are deterministic `xxhash64` values; `date_key` is an `yyyyMMdd` integer.

### Derived gold table

**`gold_supply_risk`** — precomputed HHI concentration per material × stage × year
- Columns: `material_key`, `stage_key`, `year`, `hhi_global`, `hhi_eu_sourcing`, `contrast_ratio`, `is_bottleneck`, `incomplete_wgi_coverage`
- Foreign keys: `material_key` → `gold_dim_material`, `stage_key` → `gold_dim_stage`
- Measures: 3 (`Supply Risk (Global)`, `Supply Risk (EU Sourcing)`, `Supply Risk Contrast`)

### Observability tables (gold, no relationships)

Four gold tables carry the data-quality observability surface. They are modelled (DirectLake entities) but carry no outbound relationships — they're consumed directly by report visuals.

- `gold_data_gaps` — EPI/WGI coverage per procurement country (16 measures)
- `gold_gap_registry` — tracked gaps with Open→Resolved lifecycle (7 measures)
- `gold_quality_history` — per-run quality metrics (5 measures)
- `gold_low_confidence_audit` — alias matches below the confidence threshold (5 measures)
- `gold_data_gaps_summary` — long-form metric rollup (`category`, `metric_name`, `metric_value`, `description`, `calculated_at`); no measures

See `dax_measure_library.md` §2.5–2.8 and `data_quality_architecture.md` for the full surface.

## Relationships (10, all active, single-direction)

| Fact table | Dimension | Join key |
|---|---|---|
| `fact_procurement` | `gold_dim_date` | `date_key` |
| `fact_procurement` | `gold_dim_material` | `material_key` |
| `fact_procurement` | `gold_dim_country` | `production_country_key` |
| `fact_epi_score` | `gold_dim_country` | `country_key` |
| `fact_epi_score` | `gold_dim_indicator` | `indicator_key` |
| `fact_supply_share` | `gold_dim_country` | `country_key` |
| `fact_supply_share` | `gold_dim_material` | `material_key` |
| `fact_supply_share` | `gold_dim_stage` | `stage_key` |
| `gold_supply_risk` | `gold_dim_material` | `material_key` |
| `gold_supply_risk` | `gold_dim_stage` | `stage_key` |

`gold_dim_country` is shared across `fact_procurement` (via `production_country_key`), `fact_epi_score`, and `fact_supply_share`. `gold_dim_material` is shared across both procurement and supply-share facts.

> **Country relationship on `fact_procurement`.** The model defines **one** country relationship on `fact_procurement` — via `production_country_key`. `supplier_hq_country_key` exists as a column and is consumed by `DISTINCTCOUNT` in the `Supplier Countries Count` measure, but it is not a relationship path (no second, inactive relationship is defined). Earlier drafts described both as relationships; that was wrong.

## DAX measures

The model ships **45 measures** across 8 tables — the as-built catalogue is in `dax_measure_library.md`. Headline measures:

- `Total Spend EUR` = `SUM(fact_procurement[spend_eur])`
- `Weighted EPI Score` — `SUMX` over `fact_epi_score` weighted by `RELATED(gold_dim_indicator[weight])`, restricted to EPI sub-indicators; renders 0–100 once the EPI weights table is loaded
- `Supply Risk (Global)` / `Supply Risk (EU Sourcing)` / `Supply Risk Contrast` — HHI concentration from `gold_supply_risk`
- 16 coverage measures on `gold_data_gaps` (EPI/WGI coverage by country and spend)
- 17 observability measures across `gold_gap_registry`, `gold_quality_history`, `gold_low_confidence_audit`

Patterns in use: `DIVIDE(..., 0)` safe division, `VAR`/`RETURN`, `CALCULATE` boolean filters, `RELATED` inside `SUMX`, `MAXX`-isolated latest-run metrics, display folders (`Data Gaps`, `Quality Observability`).

## Row-level security

**Not implemented in the model.** No roles are defined in the TMDL. The six-role design (Global Executive, Regional Manager ×2, Material Category Manager, etc.) lives in `rls_security_strategy.md` as a design (unimplemented) artifact — see that doc and Phase 6 spec reconciliation for status.

## Model files

Location: `fabric/OEMInsightBI_v2.SemanticModel/definition/`

- `database.tmdl` — database metadata (compatibility level)
- `expressions.tmdl` — the `DirectLake - oem_lh` source expression + `PBI_RemovedChildren` allowlist
- `model.tmdl` — model-level settings
- `relationships.tmdl` — the 10 relationships
- `tables/*.tmdl` — 14 table definitions

Git-tracked; editable via Tabular Editor or Power BI Desktop and re-synced to Fabric.

## Related docs

- `dax_measure_library.md` — full as-built measure catalogue
- `star-schema-erd.md` — ER diagram
- `data_quality_architecture.md` — observability surface
- `rls_security_strategy.md` — RLS design (unimplemented)
- `performance_optimized.md` — V-Order / DirectLake optimization notes