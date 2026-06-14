# Pipeline Scheduling Guide

> **Status:** This document is a **runbook and design rationale**. It describes the *intended* schedule and the steps to configure it in Microsoft Fabric. At the time of writing, the orchestrator pipeline still runs **on demand** — the schedule below becomes active only after the Fabric configuration steps in [How to Configure the Schedule in Fabric](#-how-to-configure-the-schedule-in-fabric) are applied in the workspace.

## Overview

The `orchestrator_pipeline_bronze_to_gold` pipeline (`fabric/orchestrator_pipeline_bronze_to_gold.DataPipeline`) runs the full medallion flow: it ingests raw sources into Bronze, cleans into Silver, and builds the Gold star schema. Today it is started manually from the pipeline editor; this guide defines an automated daily schedule so the data is refreshed without operator intervention, plus the failure alerting and downstream Power BI refresh that make the scheduled run safe to leave unattended.

**What this pipeline does on each run** (activity order from the pipeline definition):

1. **Bronze ingestion** (four activities, run in parallel):
   - `bronzecopy_EUSupplyShares` — Copy activity pulling the EU CRM supply-shares CSV over HTTP into `bronze_EUSupplyShares`.
   - `bronze_procurement`, `bronze_WGI`, `bronze_EPI` — `RefreshDataflow` activities loading the Azure SQL procurement data, WGI indicators, and EPI scores.
2. **`bronze-to-silver data cleaning`** — notebook; runs after all four Bronze activities succeed.
3. **`silver-to-gold`** — notebook; runs after Silver succeeds. Produces the Gold dimensions, facts, and data-quality tables.

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
| **Expected runtime** | 15–30 minutes (typical end-to-end ~15–20 min — see [performance-baselines.md](./performance-baselines.md)) |
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

The procurement source sets the schedule because it is the only source that changes every business day — stale procurement data is the failure mode that matters for a daily operational report. The three external ESG/governance datasets (EPI, WGI, EU CRM supply shares) update on an **annual** cycle, so a daily re-pull adds no freshness; it is tolerated only because folding them into the single daily run is simpler to operate than maintaining separate weekly schedules for low-volume files. If orchestration cost or run time ever becomes a concern, these three can be split into their own infrequent (weekly/manual) schedule and removed from the daily run — the supply-shares Copy and the EPI/WGI dataflows are independent Bronze activities, so they can be lifted out without disturbing the procurement path.

For a portfolio reviewer: this is the standard "drive the cadence off the fastest-changing source, piggyback the slow ones until cost forces a split" trade-off.

---

## ✅ Prerequisites

Confirm all of the following **before** enabling the schedule:

| Prerequisite | Why it matters |
|--------------|----------------|
| **Error handling & retry logic in place (task-011)** | A scheduled pipeline runs unattended. Per-activity retry policies are already configured in the pipeline (e.g., 2–3 retries with 120–300 s intervals on the Bronze and notebook activities). This must be in place so transient source/network hiccups self-recover instead of failing the whole nightly run. |
| **Pipeline fully tested on demand** | The schedule should automate a run that already succeeds manually — not debug it. Run the pipeline on demand and confirm a clean Bronze→Gold pass first. |
| **Source systems available at 06:00** | The Azure SQL nightly batch must have completed (~05:00) and the HTTP source for the EU CRM CSV must be reachable. |
| **Fabric capacity available** | The workspace must have capacity headroom at 06:00. The downstream Power BI refresh additionally requires **Power BI Premium, Premium Per User, or Embedded** capacity. |
| **Notification recipients identified** | Have the failure-alert email address(es) / group ready at configuration time (see [Failure Notifications](#-failure-notifications)). |

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

### Step 3 — Configure failure notifications

1. Still in the **Schedule** pane (Home → Schedule), find **Failure notifications**.
2. Add the user(s) or group(s) who should be emailed when a **scheduled** run fails.
   - Placeholder — replace at configuration time: `data-eng-alerts@<your-domain>` (or Erik's individual address).
   - **Note:** failure notifications fire for **scheduled** runs only, not for on-demand runs. See [Failure Notifications](#-failure-notifications) for richer alerting options.

### Step 4 — Add the downstream Power BI refresh (recommended)

So the report reflects the new Gold data automatically, add a **Semantic model refresh** activity to the pipeline, chained after `silver-to-gold` (see [Downstream Power BI Refresh](#-downstream-power-bi-refresh) for details), then re-save the pipeline.

### Step 5 — Verify the first scheduled run

1. Let the first scheduled run fire (or use **Schedule → Run now** to trigger an immediate run for verification — note this counts as an on-demand run, so it will **not** exercise failure notifications).
2. Watch the **Output** tab at the bottom of the canvas; each activity shows a green check on success, and the run status updates to **Succeeded**.
3. Confirm in the **Monitoring Hub** that the run is recorded as a scheduled (not on-demand) invocation.
4. Confirm the Gold tables and the Power BI report reflect the refreshed data.

### Pausing / editing / deleting the schedule

- **Pause for a maintenance window:** Home → **Schedule**, then use the **toggle switch** in *Manage scheduled runs* to disable the schedule. Re-enable the toggle to resume. No need to delete and recreate.
- **Edit:** select the **Edit** (pencil) icon next to the schedule.
- **Delete:** in the Edit Schedule pane, select **Delete schedule** at the bottom.
- *(Interval-based schedules, which are in preview, cannot be edited/toggled — they must be deleted and recreated. The recommendation here is a **Fixed** schedule, which supports the toggle.)*

---

## 🔔 Failure Notifications

The pipeline runs unattended, so an undetected failure means stale data with no warning. Three options, in increasing capability:

| Option | What it covers | When to use |
|--------|----------------|-------------|
| **Schedule → Failure notifications** (native) | Emails recipients when a **scheduled** run fails. Simplest to set up. | Baseline — set this up at minimum (Step 3 above). |
| **In-pipeline Outlook / Teams activity** | Add an **Outlook 365** (email) or **Teams** activity wired to the failure path of a specific activity, for activity-level alerts with custom messages (e.g., include `@{activity('...').error.message}`). | When you want a tailored message or to alert on a specific activity, including for on-demand runs. |
| **Data Activator on job events** | Reacts to pipeline **job events** (succeed *and* fail) and sends email or Teams. Workspace-level KQL/Activator rules can cover all pipelines at once. | When you want success confirmations too, or fleet-wide monitoring across many pipelines. |

**Recommendation for this project:** start with native **Failure notifications** on the schedule (one-time setup, covers the daily run). Add a Data Activator job-event rule later if a "nightly success" confirmation is wanted for portfolio polish.

> Replace the placeholder recipient `data-eng-alerts@<your-domain>` with the real address(es) when configuring. *Test the alert* by forcing a failure (e.g., temporarily point a source at a bad path) and confirming the email arrives — this is one of the task acceptance criteria.

---

## 📊 Downstream Power BI Refresh

After a successful pipeline run, the Power BI semantic model should refresh so the report shows the new Gold data. Add a **Semantic model refresh** activity to the pipeline:

1. In the pipeline editor, add a **Semantic model refresh** activity (from the Activities bar or the home-screen card).
2. Chain it so it runs **after `silver-to-gold` succeeds** (drag the success/green output of `silver-to-gold` to the new activity). This guarantees the model only refreshes once the Gold tables are rebuilt.
3. In the activity **Settings**, pick (or create) a **Power BI connection**, then select the **Workspace** and the project **semantic model** (`OEMInsightBI_v2`).
4. Leave **Wait on completion** on (default) so the pipeline run isn't marked complete until the refresh finishes — this way a refresh failure surfaces through the same failure-notification path as the rest of the pipeline.
5. By default this performs a **full refresh**. For this dataset's size that is fine; tables/partitions can be selected later if incremental refresh is configured.

**Capacity requirement:** the semantic model refresh activity requires the workspace to be on **Power BI Premium, Premium Per User, or Power BI Embedded** capacity, and works only with semantic models you own. *Verify your capacity tier in the tenant before relying on this step.*

> **Alternative:** instead of an in-pipeline activity, the semantic model's own scheduled refresh can be set to a time comfortably after the pipeline finishes (e.g., 07:00). The in-pipeline activity is preferred because it is **event-ordered** (refresh happens *because* Gold finished) rather than **time-guessed** (refresh happens at a clock time and hopes Gold is done).

---

## 🧭 Design Rationale (Summary)

For a portfolio reader, the scheduling design comes down to four decisions:

1. **Daily at 06:00 local** — driven by the fastest-changing source (Azure SQL procurement, daily), placed an hour after the upstream nightly batch settles (~05:00) so it reads complete data, and early enough that the report is fresh before the working day.
2. **One orchestrated run, cadence driven by the fastest source** — annual ESG/governance datasets (EPI, WGI, EU CRM) are piggybacked on the daily run for operational simplicity; they can be split into a weekly/manual schedule if cost or run time ever demands it.
3. **Unattended-safe before automated** — error handling/retry (task-011) and a proven on-demand run are prerequisites; native failure notifications give a detection path; the schedule is **pausable** via toggle for maintenance.
4. **Event-ordered downstream refresh** — the Power BI refresh is chained to `silver-to-gold` success rather than guessed by clock time, so the report never refreshes against a half-built Gold layer.

---

## 📚 References

Microsoft Learn documentation used to ground the Fabric configuration steps in this guide:

- [Run, schedule, or use events to trigger a pipeline](https://learn.microsoft.com/fabric/data-factory/pipeline-runs) — scheduled runs, fixed schedule, time zone, start/end-date requirement, managing/pausing schedules, scheduling with parameters, native failure notifications.
- [Concept: Create alerts for pipeline runs](https://learn.microsoft.com/fabric/data-factory/create-alerts-for-pipeline-runs) — activity-level (Outlook/Teams) alerts, scheduled-run failure notifications, Data Activator job-event alerts, workspace-level alerting.
- [Use the Semantic model refresh activity to refresh a Power BI Dataset](https://learn.microsoft.com/fabric/data-factory/semantic-model-refresh-activity) — adding the refresh activity, connection/workspace/dataset settings, Wait on completion, full-refresh default, capacity prerequisites.
- [Refresh a semantic model using data pipelines (preview)](https://learn.microsoft.com/power-bi/connect-data/data-pipeline-templates) — scheduled / event-driven / after-dataflow refresh patterns and adding notifications.

Related project documents:

- [performance-baselines.md](./performance-baselines.md) — pipeline runtime baselines and SLAs.
- [TROUBLESHOOTING.md](../setup/TROUBLESHOOTING.md) — common pipeline issues.

---

*Last Updated: 2026-06-14*
*Status: Runbook — schedule not yet active in Fabric (pending workspace configuration). Update this line to "Active since YYYY-MM-DD" once the schedule is enabled and the first scheduled run completes.*
