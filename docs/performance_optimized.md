# Performance Optimized — orchestrator_pipeline_bronze_to_gold

> **Status: FINAL — retest complete 2026-08-03 (task-012_5).**
> Three comparable runs at `p_full_load=false`, warm cache, durations read from the Fabric
> Monitoring detail pane. **Headline: the primary target (`silver-to-gold`) is a null result
> (+6 %, inside noise); one confirmed regression (`data_quality_checks`, +43 %); functional
> total +18 %.** Nothing measurably improved. See § Conclusion.
> All five acceptance criteria are satisfied; no open gaps.
>
> **No improvement target exists.** Per spec § Performance Optimization the pipeline is
> *not benchmarked, runs at portfolio scale, no production load or SLA requirements*.
> The >30% target was retired 2026-07-29. Record the measured deltas whatever they are —
> **including null or negative results** — and call out explicitly any optimization that
> measurably made things worse. A pipeline that was already fast showing no meaningful
> improvement is a valid result, not a failed task.
>
> **Activity names in this document predate the Phase 5 rename** (added 2026-08-06,
> task-060). Every activity name here — `silver-to-gold`, `bronze-to-silver data cleaning`,
> `bronze_EPI`, `bronze_WGI`, `bronzecopy_*` — is the name in use on the retest date
> (2026-08-03). The **Phase 5 snake_case rename (2026-08-04/05)** subsequently renamed 8 of
> the 10 pipeline activities, so these names no longer match the live pipeline. The measured
> rows are point-in-time records and are **deliberately not rewritten** — rewriting them
> would falsify the measurement. Old → new mapping (single-sourced, not duplicated here):
> `performance_baseline.md` § *Activity names predate the Phase 5 rename*.

## Comparability conditions (must match the baseline or the comparison is void)

| Condition | Baseline | Retest | Match? |
|-----------|----------|--------|--------|
| Load mode | **incremental, `p_full_load=false`** | `false` (pipeline default, untouched) | ✅ |
| `p_from_date` | default `1900-01-01` | `1900-01-01` (default, untouched) | ✅ |
| `p_epi_year` | `2024` | `2024` (default, untouched) | ✅ |
| Cache state | warm (~7 min idle between runs) | warm (~5–7 min idle) | ✅ |
| Runs | 3 | 3 | ✅ |
| Duration source | Fabric Monitoring detail pane | Fabric Monitoring detail pane | ✅ |
| WGI `per_page` | `1000` | `1000` | ✅ (raised to 10000, measured, reverted — see below) |

⚠️ **Hard condition** (`performance_baseline.md` line 21): a full-load retest is **not**
comparable to this baseline. If the retest ran in full-load mode, stop and re-run.

✅ **`bronze_WGI` comparability is intact.** task-052 briefly raised `per_page` to `10000` on
2026-08-03, which *would* have re-baselined the stage — but the change was measured against
the live API the same day, found to be **worse on both latency and robustness**, and
reverted. `per_page` is back to `1000`, so the 73 s baseline figure remains like-for-like and
the retest can report a real bronze delta. See § Findings → *Rejected: larger WGI page size*.

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

**RESOLVED 2026-08-03 in two steps, both before run 1 of 3:**

- **task-050** hardened the failure path only — capped exponential backoff with jitter
  (5/10/20/40 s, cap 60, ±25%), 5 attempts, 120 s read timeout. Comparability preserved by
  construction. A standalone probe after deploying it **completed** (324 s total, 265 s in
  the fetch cell) where the same notebook had failed twice earlier the same day. The timing
  is consistent with two read timeouts absorbed and retried into success — `2 × (120 s
  timeout + ~5 s backoff)` plus a healthy fetch ≈ 265 s — which supports the premise behind
  the raised timeout: **the server was slow, not absent**, and the old 60 s ceiling was
  cutting off answers that were still coming.
- **task-052** then raised `per_page` 1000 → 10000, cutting a run from ~36 requests to ~6 —
  and was **reverted the same day after measurement**. It made the fetch about twice as slow
  and left every request near the read-timeout ceiling. Details below; comparability with the
  73 s baseline is therefore intact.

##### Rejected: larger WGI page size (task-052)

Ran standalone at `per_page=10000`, 2026-08-03 18:46.

| | `per_page=1000` | `per_page=10000` |
|---|---|---|
| Requests per run | ~36 | ~6 |
| Fetch cell | **265 s** | **496 s** (8 m 16 s) |
| Timeouts logged | inferred 1–2 | 1 (`VA.EST` p1) |
| Cost per successful request | ~0.4–3.9 s | **~53 s** |
| Share of the 120 s read-timeout budget | <3 % | **~44 %** |
| Records fetched | — | **31,122** (identical) |

Two independent reasons it fails, both now recorded in the notebook's own constant block so
the next person to have the idea reads them before acting:

1. **Slower.** Serialising one ~5,150-record page costs the API far more than six
   1,000-record pages, which swamps the request-count saving. Per-request cost rose between
   13× and 130× (the range reflects genuine uncertainty about the earlier run's timeout
   count, which was inferred arithmetically rather than logged — the conclusion holds across
   all of it).
2. **More fragile, not less.** The premise *"fewer requests means fewer chances to fail"*
   assumes per-request failure probability is independent of page size. It isn't. At ~53 s
   against a 120 s ceiling every request sits near the edge — which is precisely how
   `VA.EST` page 1 timed out during the run meant to demonstrate the improvement.

**Data was identical** (31,122 records; `CC.EST` 5158 / `GE.EST` 5127 / `PV.EST` 5214 match
the earlier run exactly), so this is purely a latency and robustness finding.

**What actually fixed the degraded API was task-050's backoff** — the 265 s run completed
where the notebook had failed twice that morning. `per_page` was a fix for a solved problem.

**Confirmed on a recovered API, 2026-08-03 19:51** (`per_page=1000`, back to baseline config):
fetch cell **22 s, zero retries**, 31,122 records. So a healthy fetch is ~22 s (~0.6 s across
~36 requests), which retroactively confirms the 265 s run was ~22 s of work plus two 120 s
timeouts — the inference the earlier bound rested on. It also makes the page-size comparison
direct rather than bounded: **~53 s per request at 10000 vs ~0.6 s at 1000, ~88×.**

Total notebook 77 s against the 73 s baseline — **the World Bank API has recovered and the
3-run retest is unblocked.**

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
DEC-004's failure-propagation topology.

**RESOLVED 2026-08-03 by task-051.** `summarize_final_outcomes()` collapses the per-attempt
rows to one outcome per activity, ranking `activityRunStart` to find the final attempt — the
same derivation `derive_retry_attempt()` already used, and for the same reason (`retryAttempt`
is always null). The re-raise now keys off each activity's **final** attempt, so a
retried-then-succeeded activity is reported as recovered rather than failing the run, while
an activity whose last attempt failed still ends the run red — task-026's DQ gate and
DEC-004's propagation are preserved. Every attempt is still logged, because that per-attempt
detail is exactly what `get_retry_effectiveness()` reads. Under the corrected logic the 14:08
run would have been reported **Succeeded**, with `bronze_WGI (2 failed attempt(s))` noted as
recovered.

### Retest Run 1 — pipeline start 2026-08-03 20:15:07

All 10 activities **Succeeded**; the run ended green. Total wall clock 21 m 49 s
(20:15:07 → 20:36:56).

| Activity | Stage | Start | Duration | vs baseline |
|----------|-------|-------|----------|-------------|
| `bronzecopy_EUSupplyShares` | Bronze | 20:15:07 | 23 s | 17 s → +6 s |
| `bronzecopy_GlobalSupplyShares` | Bronze | 20:15:07 | 19 s | 19 s → identical |
| `bronzecopy_procurement_transactional` | Bronze | 20:15:07 | 72 s | 71 s → +1 s |
| `bronzecopy_supplier_ref` | Bronze | 20:15:07 | 72 s | 66 s → +6 s |
| `bronze_EPI` | Bronze | 20:15:07 | 75 s | 74 s → +1 s |
| `bronze_WGI` | Bronze | 20:15:07 | 89 s | 73 s → +22 %, no retries |
| `bronze-to-silver data cleaning` | Silver | 20:16:37 | **233 s** | ~167 s avg (120–240) → +40 % vs mean, inside range |
| `silver-to-gold` | Gold | 20:20:31 | **607 s** | ~573 s avg (540–638) → **+6 %, inside range** |
| `data_quality_checks` | Gold | 20:30:40 | **292 s** | ~169 s avg (120–206) → **+73 % vs mean, +42 % over baseline MAX** |
| `pipeline_error_handler` | (handler) | 20:35:33 | 83 s | — excluded |

**Read after 1 of 3:**

- **`silver-to-gold` — the actual optimization target — shows no improvement.** 607 s against
  a 573 s mean is +6 %, comfortably inside the baseline's own 540–638 s spread, and it is
  *above* the mean rather than below. Note the swing against the 14:08 preliminary (548 s):
  59 s, ~11 %, run to run, with no code change between them. That spread is the reason for
  n=3 and it is why +6 % cannot be called a regression either.
- **`data_quality_checks` is the standout.** 292 s against a 120–206 s baseline is 42 % above
  the highest figure ever recorded for it, and it is the **second consecutive** run over that
  max (231 s at 14:08) — and worse the second time. Two points is not a trend, but this is
  now the finding most likely to survive to the write-up.
- **Bronze is flat**, as expected: five of six activities within 6 s of baseline. `bronze_WGI`
  at 89 s vs 73 s ran with zero retries, so the gap is residual API latency, not the notebook.
- **task-051 was NOT exercised.** No activity retried, so the handler's success here proves
  only that a clean run stays clean — the old logic would also have passed. The fix only
  becomes observable on a run where something retries and recovers.

- Bronze / Silver / Gold / **Functional total**: 89 s / 233 s / 899 s / **1221 s**
- Cache state: warm

### Retest Run 2 — pipeline start 2026-08-03 21:02:08

Run `1ee5f0d4-adcb-4043-9ca0-8c387e70fa6b`. All 10 activities **Succeeded**. Total wall clock
20 m 47 s (21:02:08 → 21:22:55).

| Activity | Stage | Start | Duration | vs baseline | vs Run 1 |
|----------|-------|-------|----------|-------------|----------|
| `bronzecopy_EUSupplyShares` | Bronze | 21:02:08 | **105 s** | 17 s → **+518 %** | 23 s → +82 s |
| `bronzecopy_GlobalSupplyShares` | Bronze | 21:02:08 | **103 s** | 19 s → **+442 %** | 19 s → +84 s |
| `bronzecopy_procurement_transactional` | Bronze | 21:02:08 | 103 s | 71 s → +45 % | 72 s → +31 s |
| `bronzecopy_supplier_ref` | Bronze | 21:02:08 | 99 s | 66 s → +50 % | 72 s → +27 s |
| `bronze_EPI` | Bronze | 21:02:08 | 81 s | 74 s → +9 % | 75 s → +6 s |
| `bronze_WGI` | Bronze | 21:02:08 | 65 s | 73 s → **−11 %** | 89 s → −24 s |
| `bronze-to-silver data cleaning` | Silver | 21:03:54 | 216 s | ~167 s avg (120–240) → +29 %, inside range | 233 s → −17 s |
| `silver-to-gold` | Gold | 21:07:32 | **578 s** | ~573 s avg (540–638) → **+1 %, on the mean** | 607 s → −29 s |
| `data_quality_checks` | Gold | 21:17:10 | **217 s** | ~169 s avg (120–206) → +28 % vs mean, **+5 % over max** | 292 s → −75 s |
| `pipeline_error_handler` | (handler) | 21:20:49 | 126 s | — excluded | 83 s → +43 s |

**Read after 2 of 3:**

- **`silver-to-gold` is a null result and increasingly clearly so.** 578 s lands within 5 s of
  the 573 s baseline mean. Three post-optimization measurements now read 548 / 607 / 578 —
  scattered either side of the mean, all inside the baseline's own 540–638 spread. The V-Order
  and broadcast-hint work did not move the primary target measurably at this scale.
- **`data_quality_checks` stays above the baseline maximum — 3 for 3.** 231 / 292 / 217 against
  a 120–206 s baseline. The spread is wide, so the *magnitude* is unreliable, but every single
  post-optimization observation exceeds the highest pre-optimization figure. That consistency
  is the signal; the average (~247 s) is not trustworthy given the scatter.
- **New in this run: the four Bronze Copy activities all converged on ~100 s** (99–105 s) from
  19–72 s in Run 1. All four start simultaneously at 21:02:08, and the two smallest jumped
  most — `EUSupplyShares` 23 → 105 s, `GlobalSupplyShares` 19 → 103 s. A shared ceiling hit by
  four parallel activities at once looks like contention (capacity throttling, or load on the
  Azure SQL source) rather than four independent slowdowns. **This is unrelated to anything
  task-012_3 changed** — no optimization touched the Copy activities. Run 3 decides whether it
  reproduces.
- `bronze_WGI` came in at 65 s, *below* the 73 s baseline, confirming the API has fully
  recovered and that `per_page=1000` is at parity with the baseline configuration.
- **task-051 still not exercised** — no activity retried in this run either.

- Bronze / Silver / Gold / **Functional total**: 105 s / 216 s / 795 s / **1116 s**
- Cache state: warm (~7 min idle after Run 1)

### Retest Run 3 — pipeline start 2026-08-03 21:25:33

Run `9451efda-ab49-4c62-bb4d-5c13bafd781b`. All 10 activities **Succeeded**. Total wall clock
21 m 00 s (21:25:33 → 21:46:33).

| Activity | Stage | Start | Duration | vs baseline | vs Run 2 |
|----------|-------|-------|----------|-------------|----------|
| `bronzecopy_EUSupplyShares` | Bronze | 21:25:33 | 26 s | 17 s → +9 s | 105 s → **−79 s** |
| `bronzecopy_GlobalSupplyShares` | Bronze | 21:25:33 | 26 s | 19 s → +7 s | 103 s → **−77 s** |
| `bronzecopy_procurement_transactional` | Bronze | 21:25:33 | 67 s | 71 s → −4 s | 103 s → −36 s |
| `bronzecopy_supplier_ref` | Bronze | 21:25:33 | 64 s | 66 s → −2 s | 99 s → −35 s |
| `bronze_EPI` | Bronze | 21:25:33 | 102 s | 74 s → +38 % | 81 s → +21 s |
| `bronze_WGI` | Bronze | 21:25:33 | 87 s | 73 s → +19 % | 65 s → +22 s |
| `bronze-to-silver data cleaning` | Silver | 21:27:17 | 216 s | ~167 s avg (120–240) → +29 %, inside range | 216 s → identical |
| `silver-to-gold` | Gold | 21:30:54 | **638 s** | ~573 s avg (540–638) → **+11 %, equals baseline max** | 578 s → +60 s |
| `data_quality_checks` | Gold | 21:41:33 | **217 s** | ~169 s avg (120–206) → **+5 % over max** | 217 s → identical |
| `pipeline_error_handler` | (handler) | 21:45:11 | 82 s | — excluded | 126 s → −44 s |

- Bronze / Silver / Gold / **Functional total**: 102 s / 216 s / 855 s / **1173 s**
- Cache state: warm (~5 min idle after Run 2)

**Run 3 settles both open questions:**

- **The Run 2 Bronze Copy slowdown was a one-off.** All four Copy activities returned to
  normal (26 / 26 / 67 / 64 s vs Run 2's 105 / 103 / 103 / 99 s), two of them *below*
  baseline. Transient contention, exactly as suspected — **not a regression**, and nothing
  task-012_3 touched. Recorded and dismissed.
- **`data_quality_checks` reproduced at 217 s**, identical to Run 2 to the second. Three
  retest runs plus the 14:08 preliminary now sit at 292 / 217 / 217 / 231 s against a
  120–206 s baseline: **4 for 4 above the previous maximum.** Confirmed.

**task-051 was never exercised across any of the three runs** — no activity retried, so the
handler's corrected final-attempt logic remains unproven in production. It is verified by unit
test only (14 tests, negative control confirming the old logic fails the same rows).

> **Capture the Monitoring detail per run, immediately.** The baseline lost exact values
> for runs 1–2 because Fabric's detail pane was no longer retrievable afterwards, leaving
> them gap-derived from minute-granular start timestamps. Don't repeat that.

---

## Before / after — per-stage summary (3-run average)

Δ = retest avg − baseline avg. Negative Δ = faster.

| Stage | Baseline avg | Retest avg | Δ (s) | Δ (%) | Verdict |
|-------|--------------|------------|-------|-------|---------|
| Bronze (6 parallel, max) | ~85 s | 99 s | +14 s | +16 % | **No change** — inside baseline 60–120 spread |
| Silver (`bronze-to-silver`) | ~167 s | 222 s | +55 s | +33 % | **Suggestive, not proven** — inside baseline 120–240 spread |
| Gold — `silver-to-gold` | **~573 s** | **608 s** | **+35 s** | **+6 %** | **NULL RESULT** — under the 15 % noise floor; ranges overlap |
| Gold — `data_quality_checks` | ~169 s | **242 s** | **+73 s** | **+43 %** | **REGRESSION** — all 3 runs exceed baseline max |
| **Gold stage total** | ~741 s | 850 s | +109 s | +15 % | Driven entirely by `data_quality_checks` |
| **Functional total** | **~993 s (16.6 min)** | **1170 s (19.5 min)** | **+177 s** | **+18 %** | **Slower** — all 3 runs exceed baseline max |

**Retest per-run detail** (all values exact from the Monitoring detail pane):

| Stage | Run 1 | Run 2 | Run 3 | Retest spread | Baseline spread | Separated? |
|-------|-------|-------|-------|---------------|-----------------|------------|
| Bronze | 89 s | 105 s | 102 s | 89–105 | 60–120 | No — overlaps |
| Silver | 233 s | 216 s | 216 s | 216–233 | 120–240 | No — overlaps |
| `silver-to-gold` | 607 s | 578 s | 638 s | 578–638 | 540–638 | No — overlaps |
| `data_quality_checks` | 292 s | 217 s | 217 s | 217–292 | 120–206 | **Yes — no overlap** |
| **Functional total** | 1221 s | 1116 s | 1173 s | 1116–1221 | 840–1080 | **Yes — no overlap** |

The *separated* column is the load-bearing one. Comparing averages against a baseline whose
own spread is 18–29 % proves little; **non-overlapping ranges** do. Only two rows clear that
bar, and they are the two this write-up rests on.

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
| 1 | `silver-to-gold` | ~573 s | ~58% | 608 s | **52%** | **Yes** — still over half the run |
| 2 | `data_quality_checks` | ~169 s | ~17% | 242 s | **21%** | Rose from tied-2nd to clear 2nd |
| 3 | `bronze-to-silver data cleaning` | ~167 s | ~17% | 222 s | 19% | Unchanged in rank |
| 4 | Bronze (6 parallel) | ~85 s | ~9% | 99 s | 8% | Unchanged in rank |

**The bottleneck did not move.** `silver-to-gold` remains the dominant cost. Its *share* fell
from 58 % to 52 %, but that is not an improvement — it is arithmetic: the denominator grew
because `data_quality_checks` got slower. In absolute terms `silver-to-gold` is 35 s slower,
not faster.

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
- **Page identification:** resolved 2026-08-03 from the report definition in git
  (`fabric/report2.Report/definition/pages/`), not from recollection. `pageOrder` is
  `Executive Dashboard` → `Risk & Sustainability` → `Data Quality Monitoring` →
  `Supply Risk Verify`, and the visual counts (6 / 4 / 1 / 3) corroborate the query counts
  measured. **Pages 2 and 4 were renamed on 2026-08-03, after these measurements were taken**
  (`Riks & Sustainability` → `Risk & Sustainability`, `SR verify` → `Supply Risk Verify`).
  Names below are the current ones; nothing about the timings changed.

| Report page | Queries | Timings | Verdict |
|-------------|---------|---------|---------|
| **Executive Dashboard** (page 1) | 6 | 150 / 132 / 130 / 116 / 116 / 106 ms | healthy — includes session cold-start |
| Data Quality Monitoring | 1 | **116 ms** | healthy |
| **Supply Risk Verify** | 1 | **171 ms** | healthy |
| **Risk & Sustainability** (cold) | 4 | **84 s · 84 s · 6.58 s · 3.98 s** | first touch after model refresh |
| **Risk & Sustainability** (warm) | 4 | **109 / 105 / 95 / 85 ms** | same 4 queries, re-run immediately |

**Two notes on the table above:**

- **`Supply Risk Verify` holds 3 visuals but only 1 query was captured.** Not a discrepancy in the
  measurement — visuals that resolve from already-cached columns, or that carry no DAX
  (text, image, shape), issue no `query` XHR. The other three pages match their visual counts
  exactly, which is what makes the `Executive Dashboard` identification unambiguous.
- **Both page names were corrected on 2026-08-03**, after measurement: the `Riks` typo was
  fixed and `SR verify` became `Supply Risk Verify`. Done by editing `displayName` in the PBIR
  definition rather than in the Fabric UI — push-to-main auto-publishes repo → workspace, so
  the repo is authoritative and a UI-only edit would be overwritten on the next push. Page IDs
  were untouched, so `pageOrder`, the drillthrough binding on page 4 and every visual
  reference are unaffected.

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

**Nothing measurably improved.** No stage was faster than baseline by more than noise, and no
stage's retest range sat below its baseline range.

This is stated plainly rather than softened. The optimization work shipped in task-012_3
(V-Order, broadcast hints, caching, plus the 23-table `OPTIMIZE` back-fill) produced no
measurable pipeline-runtime benefit at this data scale.

Two genuinely useful things were *learned* in the process, but neither is a runtime
improvement and neither is claimed as one:

- **Direct Lake cold-start behaviour on `gold_supply_risk`** (~84 s cold vs ~100 ms warm,
  ~800×) — see § Power BI. Operationally important; not an optimization result.
- **The World Bank page-size finding** (task-052) — see § Rejected: larger WGI page size.

### What did not move (null results)

**`silver-to-gold` — the primary target — is a null result.**

608 s retest average against a 573 s baseline: +6 %, well under the 15 % noise floor this
document set in advance, with retest (578–638 s) and baseline (540–638 s) ranges overlapping
almost completely. Three post-optimization measurements read 607 / 578 / 638 s, scattered
either side of the baseline mean.

This is the headline result of task-012_5. V-Order and the broadcast hints were aimed
squarely at this activity and did not move it at portfolio scale. That is a legitimate
finding, not a failure — spec § Performance Optimization explicitly states the pipeline is
*not benchmarked, runs at portfolio scale, no production load or SLA requirements*. A
pipeline that was already fast enough had little to give.

**Bronze is flat** (99 s vs 85 s, inside the 60–120 s baseline spread), which is expected —
no optimization targeted it.

**`bronze-to-silver` is suggestive but unproven**: +33 % on the average, yet 216–233 s sits
inside the 120–240 s baseline spread. Not claimed as either an improvement or a regression.

### What got worse (regressions)

> Acceptance criterion 5 requires this section to be filled honestly:
> *"Any optimization that measurably made things worse is called out explicitly rather
> than omitted."* If nothing regressed, write "None measured" — do not delete the section.

**1. `data_quality_checks` — confirmed regression, +43 %.**

| | Baseline | 14:08 | Run 1 | Run 2 | Run 3 |
|---|---|---|---|---|---|
| Duration | 120 / 180 / **206** s | 231 s | 292 s | 217 s | 217 s |

Four post-optimization observations, **all above the highest pre-optimization figure**, with
no overlap between the ranges. The baseline's own 206 s figure is the exact one (Runs 1–2 were
gap-derived), so the comparison holds against the most reliable baseline point available.

**Causation is NOT established, and should not be assumed.** task-012_3 did not modify the
`data_quality_checks` notebook. The leading hypothesis — that the quality-observability tables
accumulate rows on every pipeline run, so the checks scan growing history — was **tested under
task-053 and REFUTED on size grounds (2026-08-04).** `gold_quality_history` holds 2,371 total
rows; the only unbounded read (Check 12 `trend_validation`, scanning `dq_overall_score`)
touches 35 rows across 35 runs. That scan completes in well under a second and cannot account
for +73 s of runtime. The read is unbounded *by construction* but harmless at this scale. **The
cause of the +43 % regression remains open** — no second guess is substituted here (per task-053
AC3). The next place to look is the gold-fact scans task-012_3 *did* modify (V-Order, broadcast
hints, caching), which the 13 non-trend checks read; that is a new hypothesis for a follow-up
task, not a conclusion of task-053.

**2. Functional total — 18 % slower, ~993 s → ~1170 s.**

All three retest runs (1116–1221 s) exceed the entire baseline range (840–1080 s). Arithmetically
this is the sum of the parts: `data_quality_checks` (+73 s), `bronze-to-silver` (+55 s),
`silver-to-gold` (+35 s), Bronze (+14 s).

Two honest caveats on this one, both weakening it relative to the `data_quality_checks` finding:

- Baseline Runs 1–2 were **gap-derived from minute-granular timestamps**, not read from the
  detail pane, so the 840–1080 s baseline range is less trustworthy than the per-activity
  figures. Against the one exact baseline run (1060 s) the retest minimum of 1116 s is only
  +5 %.
- Only `data_quality_checks` clears the non-overlap bar on its own. The rest of the +177 s is
  an accumulation of individually-inconclusive drifts.

**Not a regression: the Run 2 Bronze Copy spike.** All four Copy activities hit ~100 s in Run 2
against 19–72 s in Run 1, then returned to 26–67 s in Run 3. Four parallel activities
converging on one value for a single run, in activities no optimization touched, is transient
contention. Recorded for completeness and dismissed.

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

**No further prerequisites were blocked.** Items 1 and 4 of the prerequisites table (the
23-table `OPTIMIZE` back-fill and the semantic-model reframe) both applied cleanly, so V-Order
was genuinely in effect for every measurement in this document — the null result on
`silver-to-gold` is a real null, not an artefact of an unapplied optimization.

## Conclusion

**The optimization work did not make the pipeline faster, and the retest says so.**

`silver-to-gold` — the activity V-Order and the broadcast hints targeted, and 52 % of total
runtime — came in 6 % slower than baseline, comfortably inside noise. That is the answer to
the question task-012_5 was created to ask. Overall functional runtime is ~18 % higher
(~16.6 → ~19.5 min), of which the only individually-defensible component is a confirmed
`data_quality_checks` regression whose cause is **open** — the accumulated-history hypothesis
was tested under task-053 and refuted on size grounds (2,371 rows, sub-second scan), so it is
not the explanation.

Meanwhile **task-012_4's lever does not exist on this platform** — `CREATE INDEX` is rejected
outright by Fabric Data Warehouse and `UPDATE STATISTICS` is a documented no-op. Its
contribution is not small; it is zero.

This is a valid and expected outcome rather than a failed task. Spec § Performance
Optimization states the pipeline is *not benchmarked, runs at portfolio scale, no production
load or SLA requirements*, and the >30 % improvement target was retired on 2026-07-29 precisely
because it had no source in the spec. **A system with no performance problem cannot demonstrate
a performance fix.** The measurement discipline — a pre-registered 15 % noise floor, a
non-overlap test rather than average-chasing, and an explicit refusal to attribute the one real
regression to the optimization without evidence — is the portfolio-relevant output here, not a
speed-up that was never available.

**Recommended follow-ups** (none urgent, none blocking):

1. **`data_quality_checks` hypothesis — tested and refuted (task-053, 2026-08-04).**
   `gold_quality_history` row counts (2,371 total; 35 `dq_overall_score` rows / 35 runs)
   cannot explain +73 s — the unbounded `trend_validation` scan is sub-second at this scale.
   No scan-window fix is warranted. The cause remains open; the gold-fact scans task-012_3
   modified are the next candidate, as a new follow-up.
2. **Do not pursue further pipeline optimization at this scale.** There is no measured problem
   to solve, and the noise floor exceeds any plausible remaining gain.
3. **Keep the Direct Lake cold-start finding visible** — ~84 s first-touch on
   `gold_supply_risk` is the one user-visible latency in the system, and it is a warming
   question, not a query-tuning one.

---

## Acceptance criteria (task-012_5)

- [x] Pipeline retest run 3 times, matching the methodology used for the task-012_1 baseline — runs at 20:15, 21:02, 21:25 on 2026-08-03, all defaults (`p_full_load=false`), warm cache, durations from the Monitoring detail pane
- [x] Activity-level durations recorded and compared against the baseline, bronze/silver/gold broken out — all 10 activities × 3 runs, per-stage summary plus per-run spread
- [x] Power BI query response times recorded for representative report pages — all 4 report pages, identified from the report definition in git (`pageOrder` + visual counts), plus a cold/warm pair on `Risk & Sustainability`
- [x] A before/after comparison table committed here, stating the measured deltas whatever they are — including null or negative results — the primary target is reported as a null result
- [x] Any optimization that measurably made things worse is called out explicitly rather than omitted — `data_quality_checks` +43 %, functional total +18 %, both with their caveats stated

**Sources:** baseline `performance_baseline.md` (task-012_1) · optimizations task-012_3
(DEC-011) · index DDL `fabric/sql/warehouse_indexes.sql` (task-012_4)
