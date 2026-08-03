# Performance Optimized — orchestrator_pipeline_bronze_to_gold

> **Status: TEMPLATE — awaiting retest data (task-012_5).**
> Baseline columns are pre-filled from `performance_baseline.md` (task-012_1, final).
> Every `___` is a slot for Erik to fill from Fabric Monitoring. Delete this banner
> and replace it with a FINAL status line when the retest is complete.
>
> **No improvement target exists.** Per spec § Performance Optimization the pipeline is
> *not benchmarked, runs at portfolio scale, no production load or SLA requirements*.
> The >30% target was retired 2026-07-29. Record the measured deltas whatever they are —
> **including null or negative results** — and call out explicitly any optimization that
> measurably made things worse. A pipeline that was already fast showing no meaningful
> improvement is a valid result, not a failed task.

## Comparability conditions (must match the baseline or the comparison is void)

| Condition | Baseline | Retest | Match? |
|-----------|----------|--------|--------|
| Load mode | **incremental, `p_full_load=false`** | `___` | `___` |
| `p_from_date` | default `1900-01-01` | `___` | `___` |
| `p_epi_year` | `2024` | `___` | `___` |
| Cache state | warm (~7 min idle between runs) | `___` | `___` |
| Runs | 3 | `___` | `___` |
| Duration source | Fabric Monitoring detail pane | `___` | `___` |

⚠️ **Hard condition** (`performance_baseline.md` line 21): a full-load retest is **not**
comparable to this baseline. If the retest ran in full-load mode, stop and re-run.

## Prerequisites applied before the retest

These are the Erik-owned acceptance criteria of task-012_3 and task-012_4. Both parent
tasks closed as Finished with these steps still outstanding, so record the actual outcome
here — including failures, which are themselves findings.

| # | Prerequisite | Source | Applied? | Outcome / error |
|---|--------------|--------|----------|-----------------|
| 1 | `OPTIMIZE` on every gold table (V-Order back-fill of legacy parquet) | task-012_3 AC2 | **Yes — 2026-08-03** | **23/23 tables succeeded**, 20/20 Spark jobs, 3 min 43 s. Notebook on `oem_lh` (Lakehouse), `SHOW TABLES` filtered to `gold_*` + `fact_*`. No errors. |
| 2 | `CREATE INDEX` block of `fabric/sql/warehouse_indexes.sql` | task-012_4 AC5 | **No — rejected 2026-08-03** | `Msg 22424, Level 16, State 0, Line 1: CREATE INDEX is not a supported statement type.` Probe was `CREATE CLUSTERED INDEX CX_gold_dim_country_country_key ON dbo.gold_dim_country (country_key)` against `oem_wh`. Remaining 9 statements not attempted — same statement type. |
| 3 | `UPDATE STATISTICS ... WITH FULLSCAN` block of the same file | task-012_4 AC3 | **No — no-op 2026-08-03** | All 6 statements returned `Warning: Ignoring update of 'ACE-Cardinality' statistics. ACE statistics are auto updated, UPDATE STATISTICS DDL statement is not supported.` No error, but no effect. Statistics are platform-maintained, so the *intent* holds — the DDL is simply redundant. |
| 4 | Semantic model reframed/refreshed after `OPTIMIZE` | prerequisite for §Power BI below | **Yes — 2026-08-03** | `OEMInsightBI_v2` refreshed after the 23-table `OPTIMIZE`, so DirectLake binds to the V-Ordered files. Completed without error. |

**Note on #2:** Fabric Data Warehouse's T-SQL surface does physical clustering via
`CLUSTER BY` on `CREATE TABLE`/CTAS and accepts only `PRIMARY KEY NONCLUSTERED NOT ENFORCED`;
`CREATE CLUSTERED INDEX` / `CREATE NONCLUSTERED INDEX` are not part of it. This was verified
against Fabric docs, not by execution — if the block errored, paste the exact error text
above. A rejected index block means the task-012_4 lever does not exist on this platform,
which the baseline already half-anticipated ("won't move this baseline much").

**Note on #4:** `OPTIMIZE` rewrites the parquet files the DirectLake model binds to. Without
a reframe, the Power BI timings in §4 measure the pre-OPTIMIZE files and are invalid.

## What was optimized (task-012_3, shipped 2026-08-02)

- **V-Order** — `spark.sql.parquet.vorder.enabled=true` set at session start in
  `silver-to-gold2` (gold-only scope, DEC-011: DirectLake reads gold, so write cost lands
  where read benefit accrues).
- **Broadcast hints** — `F.broadcast()` on `dim_country`, `dim_material`, `dim_indicator`
  and their derived lookups. `dim_date_lu` deliberately **not** broadcast (years of daily
  rows may exceed the threshold).
- **Caching** — `.cache()` on `dim_country`, `dim_material`, `country_lookup`,
  `material_lookup`, `fact_procurement_complete`, `fact_supply_share_final` (8+ downstream
  uses), plus `silver_df` and `df_wgi_clean` in `bronze-to-silver`.

---

## Run results

### Preliminary run — 2026-08-03 14:08 — ⚠️ VOID for the 3-run set, silver/gold usable

Pipeline run `1983b919-411a-4b64-acaa-37090d2027e8`. Kept as a side data point, **not** one
of the three comparable runs: the Bronze stage was contaminated by a World Bank API outage
(see anomalies below), so Bronze and the functional total are not comparable to the
baseline. Silver and Gold durations are independent of how long Bronze took and are usable.

| Activity | Stage | Start | Duration | vs baseline |
|----------|-------|-------|----------|-------------|
| `bronzecopy_EUSupplyShares` | Bronze | 14:08:22 | 24 s | (17 s) |
| `bronzecopy_GlobalSupplyShares` | Bronze | 14:08:22 | 22 s | (19 s) |
| `bronzecopy_procurement_transactional` | Bronze | 14:08:22 | 71 s | (71 s) — identical |
| `bronzecopy_supplier_ref` | Bronze | 14:08:22 | 69 s | (66 s) |
| `bronze_EPI` | Bronze | 14:08:22 | 75 s | (74 s) — identical |
| `bronze_WGI` (attempt 1) | Bronze | 14:08:22 | 16m 47s | ❌ FAILED — API read timeout |
| `bronze_WGI` (attempt 2) | Bronze | 14:25:41 | 3m 54s | ❌ FAILED — API read timeout |
| `bronze_WGI` (attempt 3) | Bronze | 14:30:06 | 4m 7s | ✅ succeeded (73 s baseline) |
| `bronze-to-silver data cleaning` | Silver | 14:34:15 | **179 s** | ~167 s avg (range 120–240) → **+7%, in range** |
| `silver-to-gold` | Gold | 14:37:15 | **548 s** | ~573 s avg (range 540–638) → **−4%, inside noise** |
| `data_quality_checks` | Gold | 14:46:24 | **231 s** | ~169 s avg (range 120–206) → **+37%, above baseline max** |
| `pipeline_error_handler` | (handler) | 14:50:17 | 81 s | ❌ FAILED — see anomaly 2; excluded |

- Bronze: **non-comparable.** Excluding WGI, the max of the other five is `bronze_EPI` at
  75 s vs 74 s at baseline — i.e. bronze is unchanged where it was measurable.
- **Preliminary read on the primary target:** `silver-to-gold` moved −4% against a baseline
  whose own spread was 540–638 s (18%). That is **null result territory**, not an
  improvement. Three clean runs are needed before stating this as a finding.
- `data_quality_checks` at 231 s is above the baseline maximum. Watch whether this
  reproduces across the clean runs — if it does, it is a candidate regression.

#### Anomaly 1 — World Bank API outage contaminated Bronze

`bronze_WGI` failed twice with `Read timed out (read timeout=60)` on `GOV_WGI_GE.EST`
(page 3, then page 4) before succeeding on the third attempt. Root cause is remote: the
World Bank API was slow/degraded on 2026-08-03. The notebook's own retry
(`fetch_indicator`, `max_retries=3`, `timeout=60`, backoff `2 * attempt` = 2 s then 4 s)
is too tight to outlast a degraded endpoint — it retries into the same congestion 2 seconds
after a 60-second timeout, so a failing page costs ~3m06s and gives the remote side no time
to recover. The job makes ~48 requests (6 indicators × ~8 pages at `per_page=1000` for
1996–2023), so exposure is high.

**Second observation, 15:24 — standalone `bronze_ingest_wgi` probe, still failing.** Run
for 11m 35s, then `RuntimeError` on `GOV_WGI_RL.EST` page 3 after 3 attempts. Partial
progress: `CC.EST` 5,158 records ✓, `GE.EST` 5,127 ✓, `PV.EST` 5,214 ✓, `RL.EST` ✗.

Two things this second run establishes that the first could not:

1. **The failure is random per request, not indicator- or page-specific.** `GE.EST` failed
   twice in the 14:08 pipeline run and succeeded here; the failure moved to `RL.EST`.
   Page 2 of `RL.EST` needed all three attempts before succeeding, then page 3 exhausted
   all three. Roughly half the requests were timing out during this window.
2. **~5,150 records per indicator** at `per_page=1000` means ~6 pages × 6 indicators ≈ **36
   requests per run**. At an observed ~50% timeout rate with only 3 attempts per page, the
   probability of a clean run is effectively nil — which is why both attempts failed.

**Step 4 was parked on 2026-08-03 as a result.** The three comparable runs need a stable
Bronze stage; retrying into a degraded endpoint burns ~20 minutes per attempt.

**Not changed during the retest** — altering the notebook mid-measurement would break
comparability. Note however that the three clean runs have **not yet started** (0 of 3), so
hardening the retry *before* run 1 would preserve comparability: exponential backoff only
changes failure-path behavior, and the baseline's `bronze_WGI` figure (73 s) is a
happy-path measurement that longer backoff does not affect. See § Findings.

#### Anomaly 2 — a functionally successful run is reported as Failed

Every functional activity succeeded (bronze → silver → gold → DQ). The pipeline is marked
**Failed** solely because `pipeline_error_handler` raised on the two *superseded* WGI
attempts: `"had 2 failed activity(ies); 11 row(s) were written to the execution log first"`.

The handler (`pipeline_error_handler.Notebook` line 862) raises whenever any activity run
carries status `Failed`, and the `queryactivityruns` response returns `retryAttempt` as
null — so it **structurally cannot distinguish** a failed attempt that a later retry
superseded from an activity that genuinely failed. Any transient retry anywhere in the
pipeline therefore marks the whole run Failed.

This matters beyond the retest: it is a false-positive failure signal for **task-010**
(pipeline scheduling — scheduled runs would alert on self-healing transients) and touches
DEC-004's failure-propagation topology. Recorded here; not actioned.

### Retest Run 1 — pipeline start `___`

| Activity | Stage | Start | Duration |
|----------|-------|-------|----------|
| `bronzecopy_EUSupplyShares` | Bronze | `___` | `___` |
| `bronzecopy_GlobalSupplyShares` | Bronze | `___` | `___` |
| `bronzecopy_procurement_transactional` | Bronze | `___` | `___` |
| `bronzecopy_supplier_ref` | Bronze | `___` | `___` |
| `bronze_EPI` | Bronze | `___` | `___` |
| `bronze_WGI` | Bronze | `___` | `___` |
| `bronze-to-silver data cleaning` | Silver | `___` | `___` |
| `silver-to-gold` | Gold | `___` | `___` |
| `data_quality_checks` | Gold | `___` | `___` |
| `pipeline_error_handler` | (handler) | `___` | `___` — excluded |

- Bronze / Silver / Gold / **Functional total**: `___` / `___` / `___` / **`___`**
- Cache state: `___`

### Retest Run 2 — pipeline start `___`

| Activity | Stage | Start | Duration |
|----------|-------|-------|----------|
| `bronzecopy_EUSupplyShares` | Bronze | `___` | `___` |
| `bronzecopy_GlobalSupplyShares` | Bronze | `___` | `___` |
| `bronzecopy_procurement_transactional` | Bronze | `___` | `___` |
| `bronzecopy_supplier_ref` | Bronze | `___` | `___` |
| `bronze_EPI` | Bronze | `___` | `___` |
| `bronze_WGI` | Bronze | `___` | `___` |
| `bronze-to-silver data cleaning` | Silver | `___` | `___` |
| `silver-to-gold` | Gold | `___` | `___` |
| `data_quality_checks` | Gold | `___` | `___` |
| `pipeline_error_handler` | (handler) | `___` | `___` — excluded |

- Bronze / Silver / Gold / **Functional total**: `___` / `___` / `___` / **`___`**
- Cache state: `___`

### Retest Run 3 — pipeline start `___`

| Activity | Stage | Start | Duration |
|----------|-------|-------|----------|
| `bronzecopy_EUSupplyShares` | Bronze | `___` | `___` |
| `bronzecopy_GlobalSupplyShares` | Bronze | `___` | `___` |
| `bronzecopy_procurement_transactional` | Bronze | `___` | `___` |
| `bronzecopy_supplier_ref` | Bronze | `___` | `___` |
| `bronze_EPI` | Bronze | `___` | `___` |
| `bronze_WGI` | Bronze | `___` | `___` |
| `bronze-to-silver data cleaning` | Silver | `___` | `___` |
| `silver-to-gold` | Gold | `___` | `___` |
| `data_quality_checks` | Gold | `___` | `___` |
| `pipeline_error_handler` | (handler) | `___` | `___` — excluded |

- Bronze / Silver / Gold / **Functional total**: `___` / `___` / `___` / **`___`**
- Cache state: `___`

> **Capture the Monitoring detail per run, immediately.** The baseline lost exact values
> for runs 1–2 because Fabric's detail pane was no longer retrievable afterwards, leaving
> them gap-derived from minute-granular start timestamps. Don't repeat that.

---

## Before / after — per-stage summary (3-run average)

Δ = retest avg − baseline avg. Negative Δ = faster.

| Stage | Baseline avg | Retest avg | Δ (s) | Δ (%) | Verdict |
|-------|--------------|------------|-------|-------|---------|
| Bronze (6 parallel, max) | ~85 s | `___` | `___` | `___` | `___` |
| Silver (`bronze-to-silver`) | ~167 s | `___` | `___` | `___` | `___` |
| Gold — `silver-to-gold` | **~573 s** | `___` | `___` | `___` | `___` |
| Gold — `data_quality_checks` | ~169 s | `___` | `___` | `___` | `___` |
| **Gold stage total** | ~741 s | `___` | `___` | `___` | `___` |
| **Functional total** | **~993 s (16.6 min)** | `___` | `___` | `___` | `___` |

**Baseline per-run detail** (for spread comparison — Run 3 exact, Runs 1–2 `~` gap-derived):

| Stage | Base Run 1 | Base Run 2 | Base Run 3 (exact) | Base spread |
|-------|-----------|-----------|--------------------|-------------|
| Bronze | ~60 s | ~120 s | 74 s | 60–120 |
| Silver | ~120 s | ~240 s | 142 s | 120–240 |
| `silver-to-gold` | ~540 s | ~540 s | 638 s | 540–638 |
| `data_quality_checks` | ~120 s | ~180 s | 206 s | 120–206 |
| **Functional total** | ~840 s | ~1080 s | 1060 s | 840–1080 |

### Signal vs noise

`silver-to-gold` was the most variable activity in the baseline (540 / 540 / 638 s — an
18% spread) and the functional total ranged 840–1080 s (a 29% spread). With n=3 at that
variance, **treat a change under roughly 15% as noise, not signal.** State this explicitly
in the conclusion rather than reporting a small delta as an improvement.

## Bottleneck re-ranking after optimization

Did the bottleneck move? Baseline ranking is pre-filled.

| Rank | Activity | Baseline avg | Baseline % | Retest avg | Retest % | Still the bottleneck? |
|------|----------|--------------|------------|------------|----------|----------------------|
| 1 | `silver-to-gold` | ~573 s | ~58% | `___` | `___` | `___` |
| 2 | `bronze-to-silver data cleaning` | ~167 s | ~17% | `___` | `___` | `___` |
| 2 | `data_quality_checks` | ~169 s | ~17% | `___` | `___` | `___` |
| 4 | Bronze (6 parallel) | ~85 s | ~9% | `___` | `___` | `___` |

---

## Power BI query performance

Measured **after** the semantic model was reframed (prerequisite #4). State the method —
Performance Analyzer in Desktop (live connection to the published model) and wall-clock
page render in the service are **not** comparable to each other.

- **Method used:** Browser DevTools → Network → Fetch/XHR, filtered to the `query` XHR
  (the POST carrying each visual's DAX query). Power BI Desktop's Performance Analyzer is
  Windows-only and unavailable on macOS; the `query` request time is the end-to-end
  server round trip per visual.
- **Measured on:** 2026-08-03, after the 23-table `OPTIMIZE` and a semantic-model refresh.

| Report page | Queries | Timings | Verdict |
|-------------|---------|---------|---------|
| First page (name TBC) | 6 | 150 / 132 / 130 / 116 / 116 / 106 ms | healthy — includes session cold-start |
| Data Quality Monitoring | 1 | **116 ms** | healthy |
| SR Verify | 1 | **171 ms** | healthy |
| **Risk & Sustainability** (cold) | 4 | **84 s · 84 s · 6.58 s · 3.98 s** | first touch after model refresh |
| **Risk & Sustainability** (warm) | 4 | **109 / 105 / 95 / 85 ms** | same 4 queries, re-run immediately |

### Finding — Direct Lake cold-start transcoding on `gold_supply_risk`, ~800× cold/warm

The Risk & Sustainability page was measured twice. The **same four queries** (matched by
request payload sizes) returned **84 s / 84 s / 6.58 s / 3.98 s** on first access and
**109 / 105 / 95 / 85 ms** when re-run moments later. The slow reading is **not
reproducible**, so this is **not a defect in the page or its measures**.

**What it is:** Direct Lake pages columns from OneLake parquet into engine memory on first
demand (transcoding). The measurement ran immediately after a semantic-model refresh, so
this was the first touch of `gold_supply_risk`'s columns — the widest and heaviest table in
the model (task-038: governance- and trade-weighted dual HHI, global vs EU-sourcing,
bottleneck flagging). Once the columns are resident, queries settle at ~100 ms, in line
with every other page.

Corroborating detail: the DevTools waterfall showed the time in a long TTFB segment rather
than content download — engine-side work, consistent with transcoding rather than a
payload or network effect. The first page loaded after the refresh was *also* cold yet
answered in 106–150 ms, which fits a **column-level**, not model-level, warm-up: cheap
columns transcode invisibly, `gold_supply_risk`'s do not.

**Not a DirectQuery fallback.** A fallback would persist across re-runs. It did not.

**Where this actually matters — task-010 (pipeline scheduling).** If a scheduled pipeline
run refreshes the semantic model overnight, the **first user to open Risk & Sustainability
each morning pays ~1.4 minutes**, and every user after them pays ~100 ms. That is a real
user-facing cost hiding behind an excellent steady-state number, and it is invisible to any
measurement taken on a warm model. Worth a warm-up strategy (a scheduled query against the
page's measures after each refresh) if the report ever gets real users.

**Honest limits of this finding:** two data points, one cold and one warm, captured
opportunistically. The 84 s figure is a single observation and the cold/warm boundary was
not controlled. Treat the *direction* as established and the *magnitude* as indicative.
task-012_1 measured no Power BI baseline, so none of this is attributable to task-012_3
either way.

> task-012_1 did not measure Power BI query times, so these are **first measurements**, not
> a before/after. Record them as the forward baseline. If prerequisite #2 (indexes) failed,
> note that these timings reflect V-Order + statistics only.

---

## Findings

### What improved

`___`

### What did not move (null results)

`___`

### What got worse (regressions)

> Acceptance criterion 5 requires this section to be filled honestly:
> *"Any optimization that measurably made things worse is called out explicitly rather
> than omitted."* If nothing regressed, write "None measured" — do not delete the section.

`___`

### Prerequisites that could not be applied

**task-012_4 delivered no measurable effect — the lever does not exist on this platform.**
Confirmed empirically 2026-08-03 against `oem_wh`, not merely predicted:

- `CREATE INDEX` is rejected outright (`Msg 22424`). Fabric Data Warehouse does physical
  clustering via `CLUSTER BY` at `CREATE TABLE`/CTAS time and accepts only
  `PRIMARY KEY NONCLUSTERED NOT ENFORCED`. There is no post-hoc index DDL.
- `UPDATE STATISTICS` is accepted but ignored — ACE statistics are auto-updated by the
  engine. The optimizer does get fresh cardinality; it just isn't something you ask for.

**Therefore task-012_3 (V-Order + broadcast hints + caching, plus the 23-table `OPTIMIZE`
back-fill) is the only optimization lever in play in this retest.** Any measured delta is
attributable to it alone. This also means the Power BI timings in §4 measure V-Order and
statistics-as-maintained-by-the-platform — not indexes.

The baseline anticipated the direction of this ("task-012_4 targets the SQL-endpoint read
path rather than pipeline runtime, so it won't move this baseline much") but not the
magnitude: the effect is not small, it is zero.

`___` *(add any further prerequisites that could not be applied)*

## Conclusion

`___`

---

## Acceptance criteria (task-012_5)

- [ ] Pipeline retest run 3 times, matching the methodology used for the task-012_1 baseline
- [ ] Activity-level durations recorded and compared against the baseline, bronze/silver/gold broken out
- [ ] Power BI query response times recorded for representative report pages
- [ ] A before/after comparison table committed here, stating the measured deltas whatever they are — including null or negative results
- [ ] Any optimization that measurably made things worse is called out explicitly rather than omitted

**Sources:** baseline `performance_baseline.md` (task-012_1) · optimizations task-012_3
(DEC-011) · index DDL `fabric/sql/warehouse_indexes.sql` (task-012_4)
