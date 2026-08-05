# Pipeline Scheduling Guide

> **Status: ACTIVE since 2026-08-05.** The schedule described below **is configured and enabled** in the Fabric workspace — daily 06:00 Europe/Stockholm, schedule id `17288b67-a36f-4db8-88fe-cfa4ce1dba61`. This document is both the design rationale and the runbook for re-creating or editing it; the configuration steps are a record of what was done, not work still outstanding. Verification evidence is in the footer.

## Overview

The `orchestrator_pipeline_bronze_to_gold` pipeline (`fabric/orchestrator_pipeline_bronze_to_gold.DataPipeline`) runs the full medallion flow: it ingests raw sources into Bronze, cleans into Silver, and builds the Gold star schema. It runs **automatically every day at 06:00 Europe/Stockholm** (active since 2026-08-05); it can still be started manually from the pipeline editor when needed. This guide documents that schedule, why those settings were chosen, and how failure detection works for an unattended run.

> **Configure in the UI, or in the repo?** Two of the three settings below live *outside* the pipeline's item definition and are therefore safe to set in the Fabric UI: the **schedule** itself and the **failure notifications** attached to it. Both are held by Fabric's job scheduler, not by `pipeline-content.json`, so a `fabric-cicd` publish does not touch them. **Anything that changes the pipeline's activity list is a different matter** — the repo is the single source of truth and the next push to `main` overwrites the workspace copy (spec § Development Workflow: *"Fabric UI edits are not a sync path"*). Do not add, remove, or rewire activities in the UI; author them in `fabric/orchestrator_pipeline_bronze_to_gold.DataPipeline/pipeline-content.json` and let the deploy publish them.

**What this pipeline does on each run** (activity order from the pipeline definition):

1. **Bronze ingestion** (six activities, run in parallel):
   - `bronze_copy_eu_supply_shares` — `Copy` activity pulling the EU CRM supply-shares CSV over HTTP into `bronze_eu_supply_shares`.
   - `bronze_copy_global_supply_shares` — `Copy` activity pulling the global supply-shares CSV over HTTP into `bronze_global_supply_shares`.
   - `bronze_wgi` — `Notebook` activity loading WGI governance indicators (task-035).
   - `bronze_copy_procurement_transactional`, `bronze_copy_supplier_ref` — `Copy` activities loading the Azure SQL procurement data (task-048 replaced the `bronze_procurement` RefreshDataflow; SPN-safe). No RefreshDataflow activities remain.
   - `bronze_epi` — `Notebook` activity loading EPI scores (task-035).
2. **`bronze_to_silver_cleaning`** — notebook; runs after all six Bronze activities succeed.
3. **`silver_to_gold`** — notebook; runs after Silver succeeds. Produces the Gold dimensions, facts, and data-quality tables.

The pipeline accepts three parameters: `p_full_load` (bool, default `false`), `p_from_date` (string, default `1900-01-01`), and `procurement_array` (the Azure SQL source→sink list). The scheduled run uses the defaults — an **incremental** load (`p_full_load = false`).

---

## 📅 Recommended Schedule

| Setting | Value |
|---------|-------|
| **Frequency** | Daily |
| **Time** | 06:00 |
| **Time zone** | Europe/Stockholm (Central European [Summer] Time) |
| **Schedule type** | Fixed |
| **Parameters** | Defaults (`p_full_load = false`, incremental load) |
| **Expected runtime** | 15–30 minutes (measured functional total ~16.6 min — see [performance_baseline.md](../performance_baseline.md)) |
| **Pausable?** | Yes — disable via the Schedule pane toggle for maintenance windows |

### Why daily at 06:00 Europe/Stockholm?

The upstream procurement data is refreshed nightly in **Azure SQL** and finishes landing by roughly **05:00** local time. Scheduling the pipeline at **06:00** leaves a buffer after the upstream batch completes, so the Bronze ingestion reads a settled, complete source rather than racing a partially-written one. A one-hour margin absorbs minor variance in when the upstream batch finishes without pushing the refreshed data so late that it misses the start of the working day.

Daily cadence matches the transactional procurement source, which changes every business day. The 15–30 minute runtime means the Gold layer and the Power BI report are refreshed and ready well before users typically open the report.

> **Time-zone note:** Europe/Stockholm observes daylight saving (CET in winter, CEST in summer). For Fabric schedules with a daily-or-coarser recurrence, the trigger time auto-adjusts across the twice-yearly DST change, so a "06:00" daily schedule stays at 06:00 local year-round. If you ever need a *fixed offset* that does not shift with DST, pick a non-DST zone such as UTC instead — but for "after the local nightly batch" the local zone is the correct choice.

---

## 🔄 Per-Source Refresh Cadence

Not every source changes daily. The pipeline runs once per day as a unit, but the *meaningful* refresh frequency differs per source. The table below documents the intent; the annual external datasets are refreshed daily only as a side effect of the single orchestrated run (cheap to re-pull, and it keeps one schedule to manage).

| Source | Underlying update frequency | Recommended refresh | Notes |
|--------|-----------------------------|---------------------|-------|
| **Azure SQL — Procurement** | Daily (transactional) | Daily 06:00 | The driver of the schedule. Purchases, suppliers, materials. |
| **Azure SQL — Supplier Ref** | Rare (reference data) | Daily (piggybacked) | Changes infrequently; refreshed with the daily run at no extra orchestration cost. |
| **EPI dataset** | Annual (updated Q2–Q3) | Weekly or manual | Environmental Performance Index. Re-pulling daily is harmless but unnecessary. |
| **WGI dataset** | Annual (updated Q3–Q4) | Weekly or manual | Worldwide Governance Indicators. As above. |
| **EU CRM Supply Shares** | Annual | Weekly or manual | Critical Raw Materials supply-share CSV. As above. |

### Why these cadences?

The procurement source sets the schedule because it is the only source that changes every business day — stale procurement data is the failure mode that matters for a daily operational report. The three external ESG/governance datasets (EPI, WGI, EU CRM supply shares) update on an **annual** cycle, so a daily re-pull adds no freshness; it is tolerated only because folding them into the single daily run is simpler to operate than maintaining separate weekly schedules for low-volume files. If orchestration cost or run time ever becomes a concern, these three can be split into their own infrequent (weekly/manual) schedule and removed from the daily run — the supply-shares Copy and the EPI/WGI TridentNotebook activities are independent Bronze activities, so they can be lifted out without disturbing the procurement path.

For a portfolio reviewer: this is the standard "drive the cadence off the fastest-changing source, piggyback the slow ones until cost forces a split" trade-off.

---

## ✅ Prerequisites

Confirm all of the following **before** enabling the schedule:

| Prerequisite | Why it matters |
|--------------|----------------|
| **Error handling & retry logic in place (task-011)** | A scheduled pipeline runs unattended. Per-activity retry policies are already configured in the pipeline (e.g., 2–3 retries with 120–300 s intervals on the Bronze and notebook activities). This must be in place so transient source/network hiccups self-recover instead of failing the whole nightly run. |
| **Pipeline fully tested on demand** | The schedule should automate a run that already succeeds manually — not debug it. Run the pipeline on demand and confirm a clean Bronze→Gold pass first. |
| **Source systems available at 06:00** | The Azure SQL nightly batch must have completed (~05:00) and the HTTP source for the EU CRM CSV must be reachable. |
| **Fabric capacity available** | The workspace must have capacity headroom at 06:00. No Premium/PPU/Embedded tier is needed — the semantic model is DirectLake and the pipeline runs no semantic-model refresh activity (see [Downstream Power BI Refresh](#-downstream-power-bi-refresh)). |
| ~~Notification recipients identified~~ | **No longer a prerequisite** — email alerting was descoped 2026-08-05. Failure detection is `gold_pipeline_execution_log` + run status; see [Failure Notifications](#-failure-notifications). |

---

## 🛠️ How to Configure the Schedule in Fabric

These steps are performed in the Fabric workspace UI by the workspace owner. They follow the official Microsoft Fabric Data Factory scheduling flow (see [References](#-references)).

### Step 1 — Open the pipeline

1. Open the workspace and open `orchestrator_pipeline_bronze_to_gold`.
2. Confirm the latest version is published / saved (schedule a run that you know succeeds on demand).

### Step 2 — Create the schedule

1. On the **Home** tab, select **Schedule** in the top banner. By default the pipeline is **not** on a schedule.
2. Select **Add Schedule**.
3. On the schedule configuration page set:
   - **Schedule type:** Fixed
   - **Frequency:** Daily (every 1 day)
   - **Time:** 06:00
   - **Time zone:** the Europe/Stockholm entry (Central European time). Pick it from the time-zone dropdown — *verify the exact label in your tenant*, as the dropdown lists OS-style names.
   - **Start date / time:** a date on/after today, at 06:00 in the selected zone.
   - **End date / time:** Fabric **requires** an end date — there is no open-ended schedule. Set it far in the future (Microsoft's documented convention is **01/01/2099 12:00 AM**) to approximate "runs indefinitely." You can edit or stop the schedule at any time.
4. **(If prompted for parameters)** The pipeline defines parameters (`p_full_load`, `p_from_date`, `procurement_array`). If the schedule configuration shows a parameters section, the parameter names you enter **must exactly match** the pipeline's parameter names (mismatched names are silently ignored at runtime). For the standard daily incremental run, the pipeline defaults are correct — leave `p_full_load = false`. Supply values directly, or reference a variable library if one is set up.
5. Select **Save**.

### Step 3 — Failure notifications (descoped 2026-08-05 — no action)

**Skip this step.** Email failure notification was evaluated during configuration and deliberately descoped. Leave the **Failure notifications** box in the Schedule pane **empty**. See [Failure Notifications](#-failure-notifications) for the reasoning and for the detection path that replaces it.

### Step 4 — Confirm the semantic model auto-updates (no pipeline change)

**Do not add a refresh activity to the pipeline.** The semantic model is DirectLake, so there is no import refresh to run — the report reads the Gold Delta tables directly and only needs to *reframe* onto the new parquet files, which Fabric does on its own. Instead, verify the setting is on:

1. In the workspace, open the settings for the **`OEMInsightBI_v2`** semantic model.
2. Under the refresh settings, confirm the automatic-update option for Direct Lake is **enabled** (labelled *"Keep your Direct Lake data up to date"* at time of writing — *verify the exact label in your tenant*, as Fabric renames these settings periodically).
3. That is the whole step. No pipeline edit, no re-save, no deploy.

> **Why this is a "confirm", not an "add":** an earlier version of this runbook told you to add a **Semantic model refresh** activity here, in the Fabric UI. That instruction was wrong on two counts and has been removed. First, the pipeline's activity list is part of the item definition, and the repo is the single source of truth — the next push to `main` republishes `pipeline-content.json` over the workspace and would silently delete a UI-added activity, breaking the refresh with no error anywhere (spec § Development Workflow: *"Fabric UI edits are not a sync path"*). Second, it is unnecessary: all 14 tables in `OEMInsightBI_v2` are `mode: directLake` with zero import partitions, so a classic refresh has nothing to do. See [Downstream Power BI Refresh](#-downstream-power-bi-refresh).

### Step 5 — Verify the first scheduled run

1. Let the first scheduled run fire (or use **Schedule → Run now** to trigger an immediate run for verification — note this counts as an on-demand run, so it will **not** exercise failure notifications).
2. Watch the **Output** tab at the bottom of the canvas; each activity shows a green check on success, and the run status updates to **Succeeded**.
3. Confirm in the **Monitoring Hub** that the run is recorded as a scheduled (not on-demand) invocation.
4. Confirm the Gold tables hold the refreshed data.
5. Open the Power BI report **without** manually refreshing anything and confirm the figures moved to match the new Gold data. This is the actual acceptance evidence for the auto-update path — the report reflecting new numbers on its own is what proves reframing happened. If the numbers are stale, check the Step 4 setting before concluding the pipeline failed.

### Pausing / editing / deleting the schedule

- **Pause for a maintenance window:** Home → **Schedule**, then use the **toggle switch** in *Manage scheduled runs* to disable the schedule. Re-enable the toggle to resume. No need to delete and recreate.
- **Edit:** select the **Edit** (pencil) icon next to the schedule.
- **Delete:** in the Edit Schedule pane, select **Delete schedule** at the bottom.
- *(Interval-based schedules, which are in preview, cannot be edited/toggled — they must be deleted and recreated. The recommendation here is a **Fixed** schedule, which supports the toggle.)*

---

## 🔔 Failure Notifications

**Email alerting is descoped for this project (decided 2026-08-05).** The pipeline runs unattended, so failures still need to be *detectable* — but detection and *push notification* are different things, and only the first is load-bearing here.

**What detects a failure today (unchanged, already shipped):**

- `pipeline_error_handler` runs on **every** outcome and logs each activity to `gold_pipeline_execution_log`, re-raising when an activity's final attempt FAILED (a retried-into-success activity is recorded as recovered, not a run failure). This carries per-activity detail no email would.
- A genuinely failed run shows red in the **Monitoring Hub**, and `queryactivityruns` reports per-activity status via API.

**Why push notification was dropped rather than configured:**

1. **The tenant cannot deliver it.** The Schedule pane's Failure-notifications field rejects addresses outside the organization (verified 2026-08-05 — a `gmail.com` address is refused with an "outside your organization" error). The only tenant principal is `fabricuser@<tenant>.onmicrosoft.com`, and a bare `.onmicrosoft.com` account has **no mailbox without an Exchange licence**. Configuring it would have satisfied the acceptance criterion on paper while sending alerts into a void — strictly worse than leaving it empty, because it manufactures false confidence.
2. **The operating context does not need push.** Single-user portfolio project: no on-call rotation, no SLA, no downstream consumers to mislead. The operator is in Fabric regularly and a red run is visible there.

**If push alerting is ever wanted**, in increasing order of effort:

| Option | What it covers | Cost |
|--------|----------------|------|
| **Guest-invite an external address** into the tenant so it resolves as a principal, then use the native Schedule → Failure notifications field | Emails on **scheduled**-run failure only (not on-demand) | Tenant admin work; smallest change that makes the native path real |
| **In-pipeline Outlook / Teams activity** wired to a failure path | Activity-level alerts with custom messages (e.g. `@{activity('...').error.message}`), including on-demand runs | Repo change to `pipeline-content.json` + deploy; **never add this in the UI** — the next publish overwrites it |
| **Data Activator on job events** | Reacts to job events (succeed *and* fail); workspace-level rules cover all pipelines | Most capable, most setup |

> **Provenance:** this descope closes the criterion DEC-004 parked here (*"no on-demand-firing sink exists until task-010 (scheduling) lands … Revisit at task-010"*). It was landed on all three gated surfaces the same day (2026-08-05) via `/iterate`: spec § Orchestration → Notifications, spec § Open Questions → Technical Decisions #5, and `decision-004-pipeline-failure-propagation-topology.md` (`## Amendment — 2026-08-05`, frontmatter `amended:` bumped). **No follow-up is outstanding.**

---

## 📊 Downstream Power BI Refresh

After a successful pipeline run, the report should show the new Gold data. **This requires no pipeline activity and no configuration beyond confirming one setting** (Step 4 above).

**Why nothing is needed.** `OEMInsightBI_v2` is a DirectLake model: all 14 tables carry `mode: directLake` and there are zero import partitions. Nothing is copied into the model, so there is no import refresh to schedule — the report queries the Gold Delta tables in `oem_lh` directly. When `silver_to_gold` rewrites those tables, the model only has to *reframe* onto the new parquet files, and Fabric performs that automatically while the Direct Lake auto-update setting is enabled. This is what the spec means by "Refresh: Automatic (no explicit refresh needed with DirectLake)" (§ Dependencies & External Systems) and "Automatic refresh when lakehouse tables update" (§ Semantic Model & Reporting).

**One thing to watch.** Auto-reframing is *eventually* consistent, not ordered against the pipeline — the model reframes because the tables changed, not because the pipeline said it was finished. In practice the gap is small and harmless for a 06:00 daily run read during the working day. The known way to force a stale read is a full-overwrite write pattern: `mode("overwrite")` erases the Delta log and forces a full DirectLake reload, which is one of the reasons the incremental path uses delete-insert instead (spec § Open Questions → Technical Decisions). Keep that in mind if report figures ever lag a completed run.

**If eventual consistency ever proves too lax**, the upgrade is a **Semantic model refresh** activity chained to `silver_to_gold` success, giving event-ordered reframing. Two constraints if you go there: it must be authored in `pipeline-content.json` and deployed via `fabric-cicd` (never added in the UI — it would be overwritten on the next push), and the activity's Power BI connection must be shared with the service principal or the publish fails with *"User does not have access to the connection."* It would also contradict the three spec lines quoted above, so the spec would need an `/iterate` pass in the same change. Deliberately not done now — see the decision recorded on task-010, 2026-08-05.

---

## 🧭 Design Rationale (Summary)

For a portfolio reader, the scheduling design comes down to four decisions:

1. **Daily at 06:00 local** — driven by the fastest-changing source (Azure SQL procurement, daily), placed an hour after the upstream nightly batch settles (~05:00) so it reads complete data, and early enough that the report is fresh before the working day.
2. **One orchestrated run, cadence driven by the fastest source** — annual ESG/governance datasets (EPI, WGI, EU CRM) are piggybacked on the daily run for operational simplicity; they can be split into a weekly/manual schedule if cost or run time ever demands it.
3. **Unattended-safe before automated** — error handling/retry (task-011) and a proven on-demand run are prerequisites; failure **detection** comes from the `pipeline_error_handler` → `gold_pipeline_execution_log` trail plus run status, with email push deliberately descoped (the tenant cannot deliver it, and this is a single-operator project); the schedule is **pausable** via toggle for maintenance.
4. **No downstream refresh step at all** — the semantic model is DirectLake end to end (14/14 tables, zero import partitions), so the report reads the Gold Delta tables directly and Fabric reframes it automatically. The cheapest correct design is the one with no moving part: nothing to schedule, nothing to keep in sync, no Premium-tier dependency, and no activity that a `fabric-cicd` publish could silently drop.

---

## 📚 References

Microsoft Learn documentation used to ground the Fabric configuration steps in this guide:

- [Run, schedule, or use events to trigger a pipeline](https://learn.microsoft.com/fabric/data-factory/pipeline-runs) — scheduled runs, fixed schedule, time zone, start/end-date requirement, managing/pausing schedules, scheduling with parameters, native failure notifications.
- [Concept: Create alerts for pipeline runs](https://learn.microsoft.com/fabric/data-factory/create-alerts-for-pipeline-runs) — activity-level (Outlook/Teams) alerts, scheduled-run failure notifications, Data Activator job-event alerts, workspace-level alerting.
- [Use the Semantic model refresh activity to refresh a Power BI Dataset](https://learn.microsoft.com/fabric/data-factory/semantic-model-refresh-activity) — *not used by this project;* retained as the reference for the upgrade path described in [Downstream Power BI Refresh](#-downstream-power-bi-refresh) (connection/workspace/dataset settings, Wait on completion, capacity prerequisites).
- [Refresh a semantic model using data pipelines (preview)](https://learn.microsoft.com/power-bi/connect-data/data-pipeline-templates) — *not used by this project;* scheduled / event-driven / after-dataflow refresh patterns, same upgrade-path context.

Related project documents:

- [performance_baseline.md](../performance_baseline.md) — measured pipeline runtimes (3-run baseline).
- [TROUBLESHOOTING.md](../setup/TROUBLESHOOTING.md) — common pipeline issues.

---

*Last Updated: 2026-08-05*
*Status: **ACTIVE since 2026-08-05.** Daily 06:00 Europe/Stockholm, schedule id `17288b67-a36f-4db8-88fe-cfa4ce1dba61`, enabled. Verified end to end the same evening: a test firing at 22:20 started at `20:20:00.63Z` on the exact specified minute, ran 21.9 min, and completed as `invokeType=Scheduled` — the first non-Manual invocation in 58 runs. Direct Lake reframing confirmed behaviorally with no manual refresh (`gold_quality_history` 2767 → 2833 rows, max `refresh_timestamp` advancing to 20:37:01Z). The schedule was then reset from the 22:20 test time to the documented 06:00; the 06:00 firing itself is unobserved until the first morning run.*

*Changelog — 2026-08-05: Step 4 rewritten. It previously instructed adding a **Semantic model refresh** activity in the Fabric UI; that would have been overwritten by the next `fabric-cicd` publish (the pipeline activity list is item definition, and the repo is the source of truth), and it was unnecessary besides — `OEMInsightBI_v2` is DirectLake on all 14 tables with no import partitions. Step 4 is now a one-setting confirmation, the Premium/PPU capacity prerequisite is dropped, and the refresh-activity route is retained only as a documented upgrade path.*
