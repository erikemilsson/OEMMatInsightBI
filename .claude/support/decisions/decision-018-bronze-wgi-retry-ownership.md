---
id: DEC-018
title: bronze_wgi retry ownership sits with the notebook; the pipeline activity retries zero times
status: approved
category: architecture
created: 2026-08-20
decided: 2026-08-20
decided_by: user
related:
  tasks: ["075", "066"]
  decisions: ["DEC-017"]
implementation_anchors:
  - file: "fabric/orchestrator_pipeline_bronze_to_gold.DataPipeline/pipeline-content.json"
    description: "bronze_wgi activity policy.retry 2 -> 0 (one-line diff; retryIntervalInSeconds left at 30 and now unused)"
  - file: "fabric/bronze_ingest_wgi.Notebook/notebook-content.py"
    description: "Notebook keeps its 8-attempt/120s classified budget as the sole retry budget; failure messages reworded to name both layers accurately"
  - file: "docs/epi_wgi_ingestion.md"
    description: "§ 'Retry ownership and the total attempt budget' — the single canonical home for the attempt arithmetic (AC3's 'one place' requirement)"
inflection_point: false
spec_revised: true
spec_revised_date: 2026-08-21
blocks: []
---

# bronze_wgi retry ownership sits with the notebook; the pipeline activity retries zero times

## Select an Option

Mark your selection by checking one box:

- [x] Option A: Notebook owns retries; activity `policy.retry` → 0
- [ ] Option B: Activity owns retries; notebook stops classifying
- [ ] Option C: Leave both layers as-is (status quo)

## Background

task-066 gave `bronze_ingest_wgi` a classified retry policy: transient errors retried within an 8-attempt/120s budget, everything else raised immediately with a message reading *"not retried, this needs a human"*. That notebook-level decision was silently overridden by the orchestrator one layer up, because the `bronze_wgi` activity carried `policy.retry=2, retryIntervalInSeconds=30`.

The override was invisible until it was measured. On the **2026-08-17 04:00 scheduled run** (`cb9be8a4-4067-4045-a9cd-35d391e2ed55`), `bronze_wgi` failed at 04:00:03 after 168s carrying exactly that permanent-error message for an HTTP 400 on `GOV_WGI_CC.EST`. The activity then retried the byte-identical URL at 04:03:22 — a ~31s gap matching `retryIntervalInSeconds=30` exactly — and it **succeeded** (968s). The run finished `Completed`. Nobody was paged, and no human was needed.

So the notebook's careful classification was doing no work on the pipeline path: a spurious failure was masked (which hid a real API defect for two days), and a *genuinely* permanent failure — a retired indicator code, the exact scenario the path was built for — would still be retried twice at ~16 minutes each before the run went red.

## Options Comparison

| Criteria | Option A (notebook owns) | Option B (activity owns) | Option C (status quo) |
|----------|--------------------------|--------------------------|-----------------------|
| Attempts on a permanent error | 1 | 3 | 3 |
| Time to red on a retired indicator | ~3 min | ~35 min | ~35 min |
| Classification actually load-bearing | Yes | No (discarded) | No (inert) |
| Covers notebook-infrastructure failure | No | Yes | Yes |
| Reader can tell total attempt count | Yes, one place | Yes | No — two layers disagree |
| Overall | **Selected** | Rejected | Rejected |

## Option Details

### Option A: Notebook owns retries; activity `policy.retry` → 0

**Description:** The `bronze_wgi` activity's `policy.retry` drops 2 → 0, making the notebook's classified 8-attempt/120s budget the only retry budget in the path.

**Strengths:**
- Puts the budget where the semantic knowledge is — only the notebook can tell a transient gateway 502 from a retired indicator code
- A genuinely permanent error goes red on attempt 1 (~3 min) instead of ~35 min
- Makes task-066's classification load-bearing instead of decorative
- The notebook's failure message becomes *true* rather than misleading

**Weaknesses:**
- A notebook-**infrastructure** failure (Spark session start, driver OOM) now gets no retry where it previously got two — the one way this change can make a run redder than before

**Research Notes:** `pipeline_error_handler` already ships `retry=0` in this same pipeline, so 0 is a proven-deployable value here.

### Option B: Activity owns retries; notebook stops classifying

**Description:** Remove the notebook's retry loop and its permanent/transient classification; the activity's `policy.retry=2` becomes the single budget.

**Strengths:**
- Simpler; one layer, one number
- Also covers infrastructure failures

**Weaknesses:**
- Blunt: retries a genuinely permanent error twice at ~16 min each
- Discards the classification work task-066 built, and with it any ability to fail fast on an unrecoverable error

### Option C: Leave both layers as-is

**Description:** Status quo — an 8-attempt notebook budget stacked under two activity retries.

**Weaknesses:**
- Directly violates task-075 AC3, which requires the two layers be made coherent
- Leaves the notebook asserting "not retried" while the pipeline retries

## Your Notes & Constraints

*Add any constraints, preferences, or context that should inform this decision. This section is yours — Claude reads it but never overwrites it.*

**Constraints:**
-

**Questions:**
-

## Decision

**Selected:** Option A — Notebook owns retries; activity `policy.retry` → 0.

**Rationale:**
Only the notebook can distinguish a transient gateway 502 from a retired indicator code, so the retry budget belongs where that semantic knowledge lives. The activity's blind retry is precisely what made task-066's classification inert — demonstrated, not inferred, by the 08-17 run where the notebook raised "this needs a human" and the pipeline quietly succeeded on replay 31 seconds later. Choosing correct, fast failure on real API errors over blanket resilience is consistent with the project's standing preference for root-cause fixes over symptom patches.

## Trade-offs

**Gaining:**
- A permanent error surfaces red in ~3 minutes instead of ~35
- One authoritative attempt budget a reader can actually find (`docs/epi_wgi_ingestion.md`)
- A failure message that accurately describes what both layers will do

**Giving Up:**
- Retry coverage for notebook-infrastructure failures (session start, OOM). Accepted deliberately; worth watching over the first weeks of scheduled runs, since it is the only way this change can make a run redder than before.

## Impact

**Implementation Notes:**
Shipped in task-075 as uncommitted working-tree changes. The pipeline JSON edit is a single line (`retry: 2 → 0`) on the `bronze_wgi` activity only — verified by enumerating all 10 activities after the edit. Erik's half is to deploy and observe at least one scheduled run (04:00 UTC daily), confirming `queryactivityruns` returns exactly **one** `bronze_wgi` row for that run; two rows would mean the change did not deploy.

**Affected Areas:**
- `fabric/orchestrator_pipeline_bronze_to_gold.DataPipeline/pipeline-content.json`
- `fabric/bronze_ingest_wgi.Notebook/notebook-content.py`
- `docs/epi_wgi_ingestion.md`, `docs/error_recovery_playbook.md`, `docs/architecture/orchestration.md`, `docs/error_handling_strategy.md`
- Related tasks: task-075, task-066

**Risks:**
- Infrastructure-failure exposure as noted above
- `spec_v1.md § Orchestration` still describes `bronze_wgi` as retry=2 and "1–3 retries" — stale as of this decision; correcting it routes through `/iterate` per DEC-016
