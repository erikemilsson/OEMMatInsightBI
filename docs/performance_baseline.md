# Performance Baseline — orchestrator_pipeline_bronze_to_gold

> **Status: FINAL — Run 3 exact; Runs 1–2 derived from minute-granular start timestamps (±1 min).**
> Run 3 durations are the exact values from Fabric's Monitoring detail pane.
> Runs 1 and 2 are derived from the gaps between each activity's start timestamp
> and its downstream dependent's start (real measurements, minute resolution) and
> are marked `~`. Fabric's monitoring detail for those two earlier runs is no
> longer retrievable, so the gap-derived values stand. The bottleneck conclusion
> (`silver-to-gold` ~58–60%) is robust across all three runs regardless.
>
> Per spec § Performance Optimization: the pipeline is *not benchmarked, runs
> at portfolio scale, no production load or SLA requirements*. The goal is
> honest measurement — **not** a >30% improvement target (retired 2026-07-29).
> A pipeline already fast may show no meaningful improvement after optimization;
> that is a valid result.

## Measurement Method

- **Pipeline:** `orchestrator_pipeline_bronze_to_gold`
- **Runs measured:** 3, on 2026-08-02 (pipeline starts ~05:08, ~05:32, ~05:57)
- **Load mode: incremental (`p_full_load=false`).** ⚠️ **Hard condition:** the task-012_5 retest MUST use the same incremental mode for a valid before/after comparison. A full-load retest would not be comparable to this baseline.
- **Cache state:** warm. Runs are ~24–25 min apart (pipeline-start to pipeline-start) with only ~7 min idle between runs, so runs 2–3 (and likely run 1) ran on a warm Spark session. Comparable to each other; this is a steady-state warm baseline, not a cold start.
- **Source of durations:** Run 3 = exact (Fabric Monitoring detail pane); Runs 1–2 = gap-derived from start timestamps (pending exact paste).
- **Activity names** below are the names **as they were on 2026-08-02**, the measurement date. They no longer match the live pipeline: the Phase 5 snake_case rename (2026-08-04/05) changed 8 of the 10 activity names. The names in this document are deliberately left as measured — see *Activity names predate the Phase 5 rename* below for the mapping to current names.

### Activity names predate the Phase 5 rename

**Added 2026-08-06 (task-060).** Every activity name in this document is the pre-rename
name in use on 2026-08-02. The **Phase 5 snake_case rename (2026-08-04/05)** renamed 8 of
the 10 pipeline activities. The measured rows below are point-in-time records and are
**deliberately not rewritten** — rewriting them would falsify the measurement. Use this
mapping to relate them to the current pipeline:

| Name in this document (2026-08-02) | Current live name |
|---|---|
| `bronzecopy_EUSupplyShares` | `bronze_copy_eu_supply_shares` |
| `bronzecopy_GlobalSupplyShares` | `bronze_copy_global_supply_shares` |
| `bronzecopy_procurement_transactional` | `bronze_copy_procurement_transactional` |
| `bronzecopy_supplier_ref` | `bronze_copy_supplier_ref` |
| `bronze_EPI` | `bronze_epi` |
| `bronze_WGI` | `bronze_wgi` |
| `bronze-to-silver data cleaning` | `bronze_to_silver_cleaning` |
| `silver-to-gold` | `silver_to_gold` |
| `data_quality_checks` | `data_quality_checks` *(unchanged)* |
| `pipeline_error_handler` | `pipeline_error_handler` *(unchanged)* |

Verified 2026-08-06 against the live `getDefinition` payload: 10 activities, 5 parameters,
names exactly as in the right-hand column. The earlier parenthetical about "different
display names (`silver-to-gold2`, `bronze_ingest_*`)" conflated two things and is dropped —
`bronze_ingest_epi` / `bronze_ingest_wgi` are **notebook** names, not activity names; the
activities that invoke them were `bronze_EPI` / `bronze_WGI` and are now `bronze_epi` /
`bronze_wgi`.

## Live pipeline activity set (10 activities, as observed 2026-08-02)

All 10 activities from the repo definition ran in the live pipeline — no deploy
drift at measurement time, and re-confirmed still 10 activities on 2026-08-06 (names
per the mapping above). The 6 bronze activities start in parallel; silver and gold are
sequential.

| Stage | Activities | Parallel? | Stage wall-clock |
|-------|------------|-----------|------------------|
| Bronze | `bronzecopy_EUSupplyShares`, `bronzecopy_GlobalSupplyShares`, `bronzecopy_procurement_transactional`, `bronzecopy_supplier_ref`, `bronze_EPI`, `bronze_WGI` | yes (all start together) | max() of the six |
| Silver | `bronze-to-silver data cleaning` | n/a | its duration |
| Gold | `silver-to-gold` → `data_quality_checks` | sequential | sum() |
| (handler) | `pipeline_error_handler` | runs every time (on Succeeded/Failed/Skipped of dq) | excluded from optimization analysis |

## Run results

### Run 3 — pipeline start ~05:57 — EXACT (from Fabric Monitoring)
| Activity | Stage | Start | Duration |
|----------|-------|-------|----------|
| `bronzecopy_EUSupplyShares` | Bronze | 05:57:54 | 17 s |
| `bronzecopy_GlobalSupplyShares` | Bronze | 05:57:54 | 19 s |
| `bronzecopy_procurement_transactional` | Bronze | 05:57:54 | 1m 11s (71 s) |
| `bronzecopy_supplier_ref` | Bronze | 05:57:54 | 1m 6s (66 s) |
| `bronze_EPI` | Bronze | 05:57:54 | 1m 14s (74 s) ← stage max |
| `bronze_WGI` | Bronze | 05:57:54 | 1m 13s (73 s) |
| `bronze-to-silver data cleaning` | Silver | 05:59:09 | 2m 22s (142 s) |
| `silver-to-gold` | Gold | 06:01:34 | **10m 38s (638 s)** |
| `data_quality_checks` | Gold | 06:12:13 | 3m 26s (206 s) |
| `pipeline_error_handler` | (handler) | 06:15:41 | 1m 7s (67 s) — excluded |

- Bronze / Silver / Gold / **Functional total**: 74 / 142 / 844 / **1060 s (17m 40s)**
- Functional chain = 05:57:54 (first bronze) → 06:15:39 (dq end) = 17m 45s ✓
- + handler 67 s (excluded) + <1 min pipeline ramp → **Pipeline total ≈ 19.7 min**
- Cache state: warm

### Run 2 — pipeline start ~05:32 — GAP-DERIVED (pending exact)
| Activity | Stage | Duration | Notes |
|----------|-------|----------|-------|
| Bronze (6 activities, parallel) | Bronze | ~120 s | stage = max(); individual not separable from start times |
| `bronze-to-silver data cleaning` | Silver | ~240 s | |
| `silver-to-gold` | Gold | ~540 s | |
| `data_quality_checks` | Gold | ~180 s | |
| `pipeline_error_handler` | (handler) | 67 s (from run 3; excluded) | exact value pending |

- Bronze / Silver / Gold / **Functional total**: ~120 / ~240 / ~720 / **~1080 s (18.0 min)**
- Cache state: warm

### Run 1 — pipeline start ~05:08 — GAP-DERIVED (pending exact)
| Activity | Stage | Duration | Notes |
|----------|-------|----------|-------|
| Bronze (6 activities, parallel) | Bronze | ~60 s | |
| `bronze-to-silver data cleaning` | Silver | ~120 s | |
| `silver-to-gold` | Gold | ~540 s | |
| `data_quality_checks` | Gold | ~120 s | |
| `pipeline_error_handler` | (handler) | 67 s (from run 3; excluded) | exact value pending |

- Bronze / Silver / Gold / **Functional total**: ~60 / ~120 / ~660 / **~840 s (14.0 min)**
- + ~3 min ramp (coldest Spark session of the three) → **Pipeline total ≈ 17.0 min**
- Cache state: warm (possibly coldest of the three)

## Per-stage summary (3-run average)

Run 3 exact; Runs 1–2 approx (`~`). Functional total = Bronze + Silver + Gold.

| Stage | Run 1 (~) | Run 2 (~) | Run 3 (exact) | Avg | Spread |
|-------|-----------|-----------|---------------|-----|--------|
| Bronze (6 parallel, max) | 60 s | 120 s | 74 s | **~85 s (1.4 min)** | 60–120 |
| Silver (`bronze-to-silver`) | 120 s | 240 s | 142 s | **~167 s (2.8 min)** | 120–240 |
| Gold — `silver-to-gold` | 540 s | 540 s | 638 s | **~573 s (9.5 min)** | 540–638 |
| Gold — `data_quality_checks` | 120 s | 180 s | 206 s | **~169 s (2.8 min)** | 120–206 |
| **Gold stage total** | 660 s | 720 s | 844 s | **~741 s (12.4 min)** | 660–844 |
| **Functional total** | 840 s | 1080 s | 1060 s | **~993 s (16.6 min)** | 840–1080 |

## Bottleneck ranking (acceptance criterion: slowest activities identified)

Functional total avg ≈ 993 s. Share = activity avg / 993 s. Run-3 exact share in parentheses.

| Rank | Activity | Stage | Avg duration | % of functional | Optimization target |
|------|----------|-------|--------------|-----------------|---------------------|
| 1 | `silver-to-gold` | Gold | ~573 s (9.5 min) | **~58%** (60% exact run 3) | **task-012_3** — V-Order on gold writes, broadcast join hints for small dim joins, DataFrame caching. Primary lever. |
| 2 | `bronze-to-silver data cleaning` | Silver | ~167 s (2.8 min) | ~17% | task-012_3 (caching, broadcast hints) — secondary |
| 2 | `data_quality_checks` | Gold | ~169 s (2.8 min) | ~17% | task-012_4 (warehouse indexes) if it reads via SQL endpoint; otherwise fixed-cost reads — limited headroom |
| 4 | Bronze (6 parallel) | Bronze | ~85 s (1.4 min) | ~9% | Within bronze, `bronze_EPI`/`bronze_WGI` (74/73 s) and `bronzecopy_procurement_transactional` (71 s) dominate; supply-share copies are fast (17/19 s). EPI/WGI are external-API-bound — little Spark-side headroom |

## Notes / anomalies

- **Run 3 is exact; Runs 1–2 are approximations** pending the exact Monitoring paste. The bottleneck conclusion (`silver-to-gold` ~58–60%) is robust across all three runs regardless of exact values.
- **Warm cache:** all three runs are warm (~7 min idle between runs). Steady-state baseline, not cold-start. Documented.
- **Run 1 anomaly:** longest ramp (~3 min, coldest Spark session) but fastest functional total (~840 s) — `silver-to-gold` was 9 min in both runs 1 and 2, rising to 10m 38s in run 3.
- **`pipeline_error_handler` runs on every success** (dependency condition includes `Succeeded`), adding 67 s after `data_quality_checks`. Excluded from optimization analysis — it's a post-run handler, not part of the bronze→gold chain.
- **Load mode is incremental.** Any retest (task-012_5) must use `p_full_load=false` to be comparable.

## Conclusion

The pipeline's functional bronze→gold chain averages **~16.6 min** (warm, incremental
load; ~17.7 min for run 3 exact). **`silver-to-gold` is the clear bottleneck at
~58–60% of functional runtime** (~573 s avg, 638 s exact in run 3) and is the
most variable activity. **`task-012_3` (V-Order + broadcast join hints + caching)
is the primary optimization lever** and should target `silver-to-gold` first.
`task-012_4` (warehouse indexes) targets the SQL-endpoint / Power BI read path
rather than pipeline runtime, so it won't move this baseline much — its effect
shows in the task-012_5 Power BI query validation, not the pipeline retest.

This baseline is final. Commit `performance_baseline.md` and run
`/work complete task-012_1` to close the task and unblock `task-012_3` (mine) +
`task-012_4` (both).