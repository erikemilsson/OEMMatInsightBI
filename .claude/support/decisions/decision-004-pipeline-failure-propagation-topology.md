---
id: DEC-004
title: Failure-propagation topology for wiring pipeline_error_handler into the orchestrator
status: proposed
category: architecture
created: 2026-07-23
decided:
related:
  tasks: [task-041, task-037, task-011]
  decisions: []
implementation_anchors:
  - fabric/orchestrator_pipeline_bronze_to_gold.DataPipeline/pipeline-content.json
  - fabric/pipeline_error_handler.Notebook/notebook-content.py
inflection_point: false
spec_revised:
spec_revised_date:
blocks: [task-041]
---

# Failure-propagation topology for wiring pipeline_error_handler into the orchestrator

## Select an Option

Mark your selection by checking one box:

- [ ] Option A: Pipeline-level on-failure activities using `dependencyConditions: ["Failed", "Skipped"]` — fan-in on the terminal activity + a trailing `Fail`, 2 activities total  *(recommended, contingent on one experiment)*
- [ ] Option B: `%run` the handler from inside each transformation notebook  *(requires a recorded scope reduction — fails criterion 2 as written)*
- [ ] Option C: Wrapper / parent pipeline invoking the current one, with centralized failure handling

*Check one box above, then fill in the Decision section below.*

> Option A's label was sharpened on 2026-07-23 after research: the original said `["Failed"]` alone,
> which would miss the 7 upstream activities that go `Skipped` rather than `Failed` when something
> earlier in the chain breaks. The `Skipped` condition is what makes the one-handler fan-in work.

## Background

`pipeline_error_handler.Notebook` is a complete 521-line implementation — error categorization
against transient/permanent pattern lists, the `gold_pipeline_execution_log` schema plus
`ensure_log_table_exists`, `log_activity_start` / `log_activity_success` / `log_activity_failure`,
`get_execution_summary`, failure reporting, and `get_retry_effectiveness`. **Nothing calls any of
it.** It is not a pipeline activity, no notebook `%run`s it, and `gold_pipeline_execution_log` is
referenced by no other artifact in `fabric/`, so every reporting function queries an empty table.
(Verified with a positive control, per `rules/agents.md § Negative Findings`.)

All 8 pipeline activities depend on their predecessors with `dependencyConditions: ["Succeeded"]`
only. **There is no `Failed` branch anywhere in the pipeline**, so no failure path exists to log
from. Retry policies *are* configured and demonstrably work (retry 3/3/2/3/2/2/2/1;
`data_quality_checks` at retry=1 produced exactly two attempts on both of 2026-07-22's failing
runs) — task-011 delivered real resilience. What is missing is *observability* of failures, not
resilience against them.

task-041 criterion 1 requires this topology be decided and recorded **before** implementation,
because the three options differ materially in coverage and cost. Criterion 2 then requires that a
failure in a **non-notebook** activity (Copy or RefreshDataflow) produce a log row — which is
precisely the coverage Option B cannot satisfy — and explicitly forbids collapsing the criterion to
notebook-only logging without an explicit, recorded scope reduction.

**Pipeline activities (8):** `bronzecopy_EUSupplyShares`, `bronzecopy_GlobalSupplyShares` (Copy);
`bronze_WGI`, `bronze_procurement`, `bronze_EPI` (RefreshDataflow); `bronze-to-silver data
cleaning`, `silver-to-gold`, `data_quality_checks` (TridentNotebook).

## Open research questions — ANSWERED 2026-07-23 (research-agent)

> **Headline: question 1 resolves the *opposite* way to task-041's assumption.** The AND premise is
> correct and now confirmed on a Fabric-native page — but the inference drawn from it is wrong for
> *this* pipeline. Option A costs **2 activities, not 8**.
>
> **A trap that was not in this record and must be designed around.** Attaching an on-failure branch
> to the terminal activity produces the documented **Try-Catch** shape, and Try-Catch makes the
> overall run report **Success** ("Pipeline result is success if and only if all nodes evaluated
> succeed", evaluated over leaf activities). That would silently convert every failing run into a
> green one and **undo task-026's DQ gate**. The fix is a trailing native **Fail** activity on the
> handler's `Succeeded` path. It is not optional.
>
> **Two repo-side prerequisites this record's cost model omitted**, which apply to Options A and C
> alike: (1) `pipeline_error_handler.Notebook` has **no parameter cell**, and per project memory
> parameter cells are a Fabric-UI toggle that cannot be hand-authored in `notebook-content.py` — so
> Erik must toggle one before any parameter reaches the handler (`owner: both`). (2) The handler's
> logging API is **two-phase** (`log_activity_start` returns a UUID that `log_activity_failure` then
> UPDATEs); a pipeline-level failure branch has no `start` call to pair with, so a one-shot
> `log_activity_outcome(...)` needs adding. Option B is the only option whose API fits as written —
> unsurprising, since the notebook's docstring anticipates B.

**1. Does Fabric AND multiple `dependsOn` entries? — YES, but the cost conclusion was wrong.**
Confirmed Fabric-native: *"If you attach more than one activity to the Outlook activity, all
connected statuses must be met to trigger it… If only one fails, the Outlook activity won't
trigger."* ([outlook-activity](https://learn.microsoft.com/en-us/fabric/data-factory/outlook-activity)).
**But this pipeline is a single convergent DAG with one terminal node** — all 8 activities are
ancestors of `data_quality_checks` — and `Skipped` propagates transitively. So the documented
*"Generic error handling"* pattern applies: one handler attached to the last activity via *both* the
UponFailure and UponSkip paths *"will only run if any of the previous activities fails."*
Confidence: high on the AND rule; moderate-high on the fan-in shape.

**2. Can a parent pipeline recover WHICH child activity failed? — YES, but not from the Invoke
activity.** The Fabric Invoke pipeline page documents **no output schema at all** (ADF's
`output.pipelineRunId` is not documented for Fabric). Granularity comes from the REST
`queryactivityruns` call — *which is the same mechanism Option A's fan-in handler already needs*. So
Q2 does not differentiate C from A; it just means C costs a second artifact for no added granularity.

**3. What is reachable at failure time? — SPLIT.** Via pipeline expressions: `pipeline_run_id`
(`@pipeline().RunId`) and error message (`@activity('X').Error.Message`) yes; **retry attempt is
absent from the documented system-variable list**; and `@activity('X')` is *unsafe* for any activity
that did not run — in the fan-in case most upstream activities are `Skipped`, which have no `error`
field (observed error: *"property 'error' cannot be selected"*). Via REST `queryactivityruns`: **all
four**, per activity, including `retryAttempt` — a superset of what `log_activity_failure` needs *and*
of what `log_activity_start`/`log_activity_success` need. One call satisfies criteria 2, 3 and 4
together without touching any transformation notebook.

**4. Notification sinks? — FOUR real ones; criterion 5 can be a decision, not a deferral.** Cheapest
credible: **scheduled-run Failure notifications** (Home ▸ Schedule ▸ Failure notifications) — zero
pipeline JSON, zero connection, zero CI/CD exposure. Its one documented gap: *"Notifications aren't
sent for on-demand runs"* — which is exactly what task-037's induced-failure test would be. Pair with
an **Activator** rule on pipeline job events (survives CI/CD, covers on-demand) to close it. Flipping
the three RefreshDataflow `notifyOption`s from `"NoNotification"` to `"MailOnFailure"` is a one-word
freebie but low-confidence delivery and partial coverage — not an answer to criterion 5 on its own.
The **Outlook/Teams activity** is the only sink that can put the actual error text in front of a
recipient, but carries *"will be inactive when using CI/CD"* and *"does not support WI or SPN"* —
a standing re-binding chore on every deploy, against a project that already has documented
deploy-drift and silent connection-unbinding hazards.

### The two experiments that remain

Neither is answerable from docs. Both use throwaway artifacts and touch nothing real.

- **Settles Option A (~30 min, do this one first).** Does `queryactivityruns` return rows for a run
  that is **still in progress**? The handler executes inside the run it would query, and the docs do
  not address it. Scratch pipeline: `Wait` (2s) → a deliberately-failing activity → a scratch notebook
  attached with `["Failed","Skipped"]` that POSTs `queryactivityruns` with `@pipeline().RunId` and
  prints the raw response. Rows present → the recommended shape is confirmed end-to-end. Empty/404 →
  fall back to Option A's 8-handler form with literal names and `@activity('X').Error.Message` (which
  works precisely because each such handler only ever reads an activity that ran and failed). 401/403
  → the `notebookutils.credentials.getToken('pbi')` scope caveat has bitten; needs MSAL or a
  workspace-identity connection.
- **Settles Option C (~15 min, only if C is in play).** Scratch parent: `Invoke pipeline` (wait on
  completion) → `Set Variable` = `@string(activity('Invoke child').output)`. Run, read the Output pane.
  No child run id → nothing to pass to `queryactivityruns`, and C collapses to logging "the child
  pipeline failed".

### Original framing (retained)

These were the evidence gaps that made this a research decision rather than a judgement call:

1. **Does Fabric AND multiple `dependsOn` entries on a single activity?** task-041's criterion 1
   asserts it does, which would mean one handler activity with N `Failed` dependencies fires only
   when *all* N have failed — useless for guarding N activities. If true, Option A costs N handler
   activities, not one. Confirm against Microsoft Learn / the Data Factory dependency semantics, and
   determine whether any fan-in shape (e.g. `Completed` conditions plus an in-handler status query)
   avoids the multiplication.
2. **Can a parent pipeline recover *which child activity* failed?** Option C's value collapses if
   the wrapper can only see "the child pipeline failed". Determine whether the child run's
   activity-level detail is reachable — via the `ExecutePipeline` activity output, a Fabric REST
   call to the pipeline-run's activity runs, or not at all.
3. **What is actually available to a handler activity at failure time?** Specifically whether the
   failed activity's name, error message, `pipeline_run_id` and retry attempt are reachable from
   `@activity(...).Error` / `@pipeline().*` system variables — `log_activity_failure` needs all four,
   and `error_category` needs a real Fabric error string to categorize.
4. **What notification sinks does a Fabric pipeline actually offer here?** All three RefreshDataflow
   activities carry `"NoNotification"` and the pipeline JSON contains no email/Teams/webhook
   configuration of any kind. task-037's notification criterion has nothing to exercise today.
   Criterion 5 accepts an explicit deferral with a reason, but not an undecided gap.

## Options Comparison

| Criteria | A: `Failed` branches | B: `%run` in notebooks | C: wrapper pipeline |
|----------|----------------------|------------------------|---------------------|
| Covers Copy activities (2) | Yes | No | Yes |
| Covers RefreshDataflow (3) | Yes | No | Yes |
| Covers notebooks (3) | Yes | Yes | Yes |
| Survives a hard notebook crash | Yes | No — handler code never runs | Yes |
| Identifies *which* activity failed | Yes | Yes | Yes — via REST `queryactivityruns` on the child run id, **not** from the Invoke activity's output |
| Reaches `retry_attempt` | Yes, via REST (`retryAttempt`) — **not** via any pipeline expression | No | Yes, via REST |
| Rich in-Python error context | Partial — REST gives `errorCode` / `message` / `failureType`, no stack trace or Spark-side state | Yes — real exception objects, tracebacks, table state | Partial — same as A |
| Activities added to the pipeline | **1 handler + 1 `Fail`** (fan-in on the terminal activity), or 8 handlers if per-activity `@activity().Error` is used instead of REST | 0 | 1 handler + 1 `Fail` + a new pipeline artifact |
| Preserves the pipeline's `Failed` run status | Only with a trailing `Fail` activity — a bare on-failure branch is the documented Try-Catch shape and reports **Success** | Yes, inherently (`raise` re-fails the activity) | Same caveat as A |
| Needs a parameter cell toggled in the Fabric UI | Yes (`owner: both`) | No | Yes (`owner: both`) |
| Needs a new one-shot function in the handler notebook | Yes — the two-phase `log_activity_start` → `log_activity_failure` API has nothing to pair with | No — fits the API as written | Yes |
| Survives a git / `fabric-cicd` round trip cleanly | Yes (plain activities) | Yes | Yes |
| Satisfies criterion 2 as written | Yes | **No** — needs recorded scope reduction | Yes |
| Satisfies criterion 3 (successes logged too) | Yes — the same REST response carries `Succeeded` rows | Only for the 3 notebooks | Yes |

## Option Details

### Option A: Pipeline-level on-failure activities (`dependencyConditions: ["Failed"]`)

**Description:** Add handler activity/activities to the orchestrator that depend on the guarded
activities with a `Failed` condition, invoking `pipeline_error_handler` with the failure context.

**Strengths:**
- Catches every activity type, including Copy and RefreshDataflow, whose failures never reach Python.
- Survives hard crashes where no in-notebook handler code would run.
- Directly satisfies criterion 2.

**Weaknesses:**
- Cost is gated on open question 1 — potentially 8 handler activities rather than 1.
- Error context is limited to what pipeline expressions expose (open question 3).

**Research Notes:**

*Open question 1 settles in Option A's favour — the opposite of what task-041 assumed.* Fabric does AND multiple `dependsOn` entries; the Fabric-native confirmation is on the Office 365 Outlook activity page, which describes exactly this case. But this pipeline is a **single convergent DAG with one terminal activity** — all 8 activities are ancestors of `data_quality_checks` — and `Skipped` propagates transitively (*"If Activity X fails, then Activity Y has a status of 'Skipped'… Similarly, Activity Z has a status of 'Skipped' as well"*). So the documented **"Generic error handling"** pattern applies: one handler, attached to the last activity via *both* the UponFailure and UponSkip paths, *"will only run if any of the previous activities fails. It will not run if they all succeed."* **Cost is 1 handler activity, not 8.**

*A trap that must be designed around.* A bare on-failure branch off the terminal activity is the documented **Try-Catch** shape, and Try-Catch makes the overall run report **Success**: *"Pipeline result is success if and only if all nodes evaluated succeed"*, evaluated over leaf activities. That would silently convert every failing run into a green one and undo task-026's DQ gate. The fix is a trailing native **Fail** activity (*"Cause pipeline execution to fail with a customized error message and error code"*) on the handler's `Succeeded` path. Total: **2 new activities**. Neither exists in `fabric/` today (verified with a positive control: a probe for `"type": "(Fail|ExecutePipeline|InvokePipeline|Web|WebHook|Office365Outlook)"` returned nothing, while controls `notifyOption` → 3 hits and `dependencyConditions` → 7 hits in the same tree).

*What the handler can actually see.* Not `@activity('X').Error` — in the fan-in case most upstream activities are `Skipped`, and skipped activities have no `error` field (*"Any references to missing fields may throw errors downstream"*; the observed error is *"property 'error' cannot be selected"*). The handler instead calls `POST /v1/workspaces/{ws}/datapipelines/pipelineruns/{jobId}/queryactivityruns`, which returns per activity: `activityName`, `activityType`, `status`, `activityRunStart`, `activityRunEnd`, `durationInMs`, `error.{errorCode,message,failureType}` and **`retryAttempt`** — a superset of what `log_activity_failure` needs *and* of what `log_activity_start`/`log_activity_success` need. One call satisfies criteria 2, 3 and 4 together, without touching any transformation notebook. Auth from the notebook: `notebookutils.credentials.getToken('pbi')` (scope-limited under SPN; the notebook activities currently carry no `Connection`, so they run as the pipeline owner).

*The one thing docs don't settle:* whether `queryactivityruns` returns rows for a run that is **still in progress** — see "The two experiments that remain" above. If it returns nothing, the fallback is still Option A, in its 8-handler + literal-names form.

*Prerequisites either way:* the parameter-cell toggle and the one-shot `log_activity_outcome(...)` function, both described in the headline block above.

Sources: [outlook-activity](https://learn.microsoft.com/en-us/fabric/data-factory/outlook-activity), [concepts-pipelines-activities](https://learn.microsoft.com/en-us/azure/data-factory/concepts-pipelines-activities) (ADF), [tutorial-pipeline-failure-error-handling](https://learn.microsoft.com/en-us/azure/data-factory/tutorial-pipeline-failure-error-handling) (ADF), [pipeline-rest-api-capabilities](https://learn.microsoft.com/en-us/fabric/data-factory/pipeline-rest-api-capabilities), [expression-language](https://learn.microsoft.com/en-us/fabric/data-factory/expression-language), [fail-activity](https://learn.microsoft.com/en-us/fabric/data-factory/fail-activity), [notebook-activity](https://learn.microsoft.com/en-us/fabric/data-factory/notebook-activity), [activity-overview](https://learn.microsoft.com/en-us/fabric/data-factory/activity-overview).

### Option B: `%run` the handler from inside each transformation notebook

**Description:** The usage `pipeline_error_handler`'s own docstring anticipates — each transformation
notebook `%run`s it and wraps its work in try/except.

**Strengths:**
- Richest in-Python context: real exception objects, stack traces, table-level state.
- No pipeline JSON changes at all.

**Weaknesses:**
- Covers only 3 of 8 activities; the 2 Copy and 3 RefreshDataflow activities are invisible to it.
- Misses hard crashes (OOM, executor loss) where the handler code never runs.
- **Fails criterion 2 as written** — selecting it requires an explicit, recorded scope reduction.

**Research Notes:**

B is the only option that fits `pipeline_error_handler`'s API **as written** — `log_activity_start()` → work → `log_activity_success()` / `except: log_activity_failure(); raise` is exactly the two-phase shape the notebook implements, and the docstring says so. It needs no pipeline JSON change, no parameter cell, no REST call, no token, and no new function. It also preserves the run's `Failed` status for free, because a re-raised exception fails the activity normally. If the goal were only *rich* error context, B wins outright: real exception objects, tracebacks, and table-level state that no pipeline expression or REST `error` object can reach.

But the coverage gap is structural, not incidental. The 2 Copy and 3 RefreshDataflow activities never enter a Python process at all — there is no `%run` hook to place. Copy and RefreshDataflow failures surface only through the activity-run record or through pipeline expressions, never through user code. And within the 3 notebooks it still misses hard crashes — OOM, executor loss, Spark session failure to start — where the `except` block never executes; the handler's own `TRANSIENT_ERROR_PATTERNS` list contains `"executor lost"` and `"spark session failed to start"`, i.e. patterns it is structurally incapable of ever categorising under this option.

So the record's existing verdict stands: **B fails criterion 2 as written** and selecting it requires an explicit, recorded scope reduction. Worth noting: B is *not* mutually exclusive with A. A gives the coverage and the run-level skeleton (activity, status, timings, `retryAttempt`, error string); B could later be layered inside the 3 notebooks for finer in-Python detail. Nothing in `gold_pipeline_execution_log`'s schema prevents both writers. If B is wanted at all, it belongs as a later enrichment, not as the answer to task-041.

Sources: `fabric/pipeline_error_handler.Notebook/notebook-content.py` (the two-phase API; the transient pattern list), [pipeline-rest-api-capabilities](https://learn.microsoft.com/en-us/fabric/data-factory/pipeline-rest-api-capabilities).

### Option C: Wrapper / parent pipeline with centralized failure handling

**Description:** A new parent pipeline invokes the current orchestrator via `ExecutePipeline` and
carries a single `Failed` branch.

**Strengths:**
- One failure branch total, regardless of how many activities the child grows to.
- Cheapest topology to maintain as the pipeline evolves.

**Weaknesses:**
- Granularity depends entirely on open question 2 — may only be able to log "the pipeline failed".
- Adds a second pipeline artifact to deploy, schedule (task-010) and keep in sync.

**Research Notes:**

*Open question 2 resolves better than this record feared, and it still doesn't rescue C.* A parent CAN recover which child activity failed — but not from the Invoke pipeline activity, whose Fabric page documents **no output schema at all** (ADF's `output.pipelineRunId` is not documented for Fabric). The granularity comes instead from `queryactivityruns`.

That is the decisive point: **the REST call is the same mechanism Option A's fan-in handler already uses.** C therefore buys no granularity that A lacks. What it adds is a second pipeline artifact to author, deploy, schedule (task-010), keep in git sync and keep bound — against a project whose recorded hazards already include *"a workspace update from git silently unbinds every dataflow"* and a live-vs-repo activity-count drift. It also inherits every one of A's prerequisites unchanged: the same parameter-cell toggle, the same one-shot logging function, and the same Try-Catch trap.

One genuine advantage remains, and it is a maintenance argument rather than a capability one: C's single failure branch is attached to the Invoke activity, so it stays correct no matter how the child's internal DAG is reshaped. **A's fan-in shape depends on the child staying singly-terminal** — if a future activity is added that is *not* an ancestor of `data_quality_checks` (a parallel export, say, or a best-effort side-load), the fan-in handler stops covering it *silently*. That is a real, if distant, fragility, and it is the honest case for C. Not worth a second artifact today for an 8-activity pipeline, but worth writing down so the choice is revisited if the DAG ever forks at the tail.

*Unresolved, if C is pursued:* whether the Fabric Invoke pipeline activity exposes the child's run id at all — see the second experiment above.

Sources: [invoke-pipeline-activity](https://learn.microsoft.com/en-us/fabric/data-factory/invoke-pipeline-activity), [pipeline-rest-api-capabilities](https://learn.microsoft.com/en-us/fabric/data-factory/pipeline-rest-api-capabilities), [expression-language](https://learn.microsoft.com/en-us/fabric/data-factory/expression-language), [tutorial-pipeline-failure-error-handling](https://learn.microsoft.com/en-us/azure/data-factory/tutorial-pipeline-failure-error-handling) (ADF).

## Recommendation (research-agent, 2026-07-23) — for Erik to accept or reject

**Not a selection. No box is ticked.**

**Option A, in the fan-in shape.** Add exactly two activities to `orchestrator_pipeline_bronze_to_gold`:

1. A TridentNotebook activity running `pipeline_error_handler`, with
   `dependsOn: [{"activity": "data_quality_checks", "dependencyConditions": ["Failed", "Skipped"]}]`
   and a `pipeline_run_id` parameter bound to `@pipeline().RunId`.
2. A `Fail` activity depending on the handler with `["Succeeded"]`, so the run still reports Failed.

Inside the handler, call `queryactivityruns` with the run id and write one `gold_pipeline_execution_log`
row per activity — `Succeeded` rows included. Notification: configure scheduled-run **Failure
notifications**, record the documented on-demand gap, and flip the three RefreshDataflow
`notifyOption`s to `"MailOnFailure"` as a low-cost extra.

**Why:**

- The main cost axis was question 1, and it resolves opposite to the task's assumption: the
  singly-terminal DAG makes the fan-in shape valid, so A costs 2 activities rather than 8, and does
  not multiply as the pipeline grows.
- One REST call satisfies criteria 2, 3 and 4 simultaneously — non-notebook coverage, success rows,
  and a real Fabric error string for `categorize_error()` — while touching zero transformation
  notebooks. Smaller blast radius than B (edits 3 notebooks, still fails criterion 2) or C (adds an artifact).
- It honours task-041's scope boundary exactly: no retry-count changes, no DQ-gate changes, no new
  error categories. Only new activities and a new function.
- The notification answer keeps the sink **out** of the git-synced pipeline definition, sidestepping
  the *"Outlook activity will be inactive when using CI/CD"* limitation entirely.

**Conditions:**

- **Contingent** on the ~30-minute in-flight `queryactivityruns` experiment. If it returns nothing,
  the fallback is still Option A in its 8-handler form — the decision need not be reopened, only the shape.
- **Requires** Erik to toggle a parameter cell on `pipeline_error_handler` in the Fabric UI.
- **Requires** a new one-shot `log_activity_outcome(...)` in the handler notebook.
- **The trailing `Fail` activity is not optional.** Without it the change makes every failing run
  report Success, silently defeating task-026's DQ gate.

**Confidence:** moderate-high — Q1 and Q4 settled on Fabric-native pages; Q2 and Q3 rest on a
documented Fabric REST API whose behaviour when self-querying an in-flight run is untested.

### Questions the research raised for you

1. **Does task-037's induced-failure test have to work on an on-demand run?** If yes, scheduled-run
   Failure notifications won't fire for it and an Activator rule should be configured too. If the test
   can go through a schedule, the free sink is sufficient.
2. **Is a second pipeline artifact (Option C) acceptable maintenance cost** in exchange for a failure
   branch that stays correct if the DAG ever stops being singly-terminal? The recommendation says no
   for 8 activities, but it is a judgement call about where this project is heading.
3. **Should the Outlook activity be ruled out permanently** for this repo given *"will be inactive
   when using CI/CD"*, or kept as an option for a future manual-deploy surface?

## Your Notes & Constraints

*This section is yours — Claude reads it but never overwrites it.*

**Constraints:**
-

**Questions:**
-

## Decision

**Selected:**

**Rationale:**


## Trade-offs

**Gaining:**

**Giving Up:**


## Impact

**Implementation Notes:**
Blocks task-041, which in turn blocks task-037 (whose criterion 2 asserts a failure is written to the
execution log and criterion 3 asserts a notification fires — neither can pass today). The notification
sink (open question 4) is a separate call that rides along with this one: configure it, or defer it
with a recorded reason.
