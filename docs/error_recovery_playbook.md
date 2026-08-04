# Error Recovery Playbook - OEMMatInsightBI

**Status:** Active
**Last Updated:** 2026-04-05
**Related:** [Error Handling Strategy](error_handling_strategy.md)

---

## Quick Reference

### Retry Configuration

All 10 pipeline activities, as configured in `pipeline-content.json` (`policy.retry` / `policy.retryIntervalInSeconds`):

| Activity | Retries | Interval | Total Wait |
|----------|---------|----------|------------|
| bronzecopy_procurement_transactional | 3 | 5 min | 15 min |
| bronzecopy_supplier_ref | 3 | 5 min | 15 min |
| bronzecopy_EUSupplyShares | 3 | 5 min | 15 min |
| bronzecopy_GlobalSupplyShares | 3 | 5 min | 15 min |
| bronze_EPI | 2 | 30 s | 1 min |
| bronze_WGI | 2 | 30 s | 1 min |
| bronze-to-silver data cleaning | 2 | 2 min | 4 min |
| silver-to-gold | 2 | 2 min | 4 min |
| data_quality_checks | 1 | 2 min | 2 min |
| pipeline_error_handler | 0 | — | none (runs on every outcome, never retried) |

**Rationale:** Bronze ingestion activities (procurement, EU and global supply) have the highest retry counts because they depend on external sources prone to transient outages. EPI/WGI notebooks retry quickly (30 s) — the source APIs either respond fast or fail fast. Transformation notebooks get fewer retries since Spark failures are typically not resolved by retrying alone. `pipeline_error_handler` is the terminal observer — it runs on every pipeline outcome (success or failure) to record the run and must not itself retry, or duplicate run-records would be written. `data_quality_checks` retries once: a second transient failure usually means a real data problem, not a flake.

---

## Error Categories

### Transient Errors (Auto-Retry)

Temporary conditions that typically resolve on their own. The pipeline retries automatically.

**Common patterns:**
- Network timeout / connection reset
- Resource busy / capacity exceeded
- 502 Bad Gateway / 503 Service Unavailable / 504 Gateway Timeout
- Spark session failed to start / executor lost
- Rate limit exceeded / throttled

**What to do if retries exhaust:**
1. Check Fabric capacity usage (Settings > Capacity metrics)
2. Check source system status (Azure SQL portal, GitHub status, World Bank API)
3. Wait 15 minutes and re-run the pipeline manually
4. If recurring, check the execution log: `SELECT * FROM gold_pipeline_execution_log WHERE error_category = 'Transient' ORDER BY start_time DESC LIMIT 20`

### Permanent Errors (Immediate Failure)

Require human intervention. The pipeline does not retry these.

**Common patterns:**
- Authentication failed / 401 Unauthorized / 403 Forbidden / token expired
- Table not found / schema mismatch / column not found
- 404 Not Found / path does not exist
- Constraint violation / duplicate key

**What to do:**
1. Read the error message in the Fabric pipeline run details
2. Follow the specific resolution steps below based on error type

### Unknown Errors

Errors that do not match known patterns. Treated conservatively (1 retry, then fail).

**What to do:**
1. Read the full error message in the execution log
2. Search for the error text in Microsoft Learn / Stack Overflow
3. If the error recurs, add the pattern to `TRANSIENT_ERROR_PATTERNS` or `PERMANENT_ERROR_PATTERNS` in `pipeline_error_handler.Notebook`
4. Document the new pattern in this playbook

---

## Resolution Steps by Scenario

### 1. Azure SQL Connection Failure (bronzecopy_procurement_transactional / bronzecopy_supplier_ref)

**Symptoms:** Timeout, connection refused, or authentication error on the procurement Copy activities (`bronzecopy_procurement_transactional`, `bronzecopy_supplier_ref`).

**Resolution:**
1. Open Azure Portal > SQL Server > check server status
2. Verify the Fabric connection `oem_azuresql_procurement` (Manage connections and
   gateways → Connections). The `bronze_azureSQLdb2table` dataflow was retired
   2026-07-31 — procurement ingestion is now the Copy activities
   `bronzecopy_procurement_transactional` and `bronzecopy_supplier_ref`.
3. Check if the SQL Server firewall allows Fabric IPs
4. If credentials expired: update the connection in Fabric workspace > Manage connections
5. Re-run pipeline after fixing

### 2. HTTP Endpoint Unavailable (bronzecopy_EUSupplyShares)

**Symptoms:** HTTP 404, 500, or timeout when fetching the EU Critical Raw Materials CSV from GitHub.

**Resolution:**
1. Check the source URL manually in a browser: verify the GitHub raw file URL is accessible
2. If the file has been moved or renamed, update the connection in Fabric
3. If GitHub is down (check github.com/status), wait and retry
4. Consider caching the CSV locally as a fallback

### 3. Notebook Failure (bronze_WGI, bronze_EPI)

**Symptoms:** TridentNotebook activity fails — World Bank API (WGI) or Yale EPI server
unreachable, schema changed at source, or resource contention on the Fabric capacity.

**Resolution:**
1. Open Fabric workspace > the pipeline `orchestrator_pipeline_bronze_to_gold` > check
   the `bronze_WGI` / `bronze_EPI` activity's output cell. EPI/WGI ingestion has been via
   TridentNotebook activities (`bronze_ingest_wgi`, `bronze_ingest_epi`) since task-035 —
   not dataflow refreshes; the `WGI_file2table` and `EPI_file2table` dataflow items still
   exist in the workspace but are not on the pipeline's activity path.
2. If the World Bank API (WGI) or Yale EPI server is down, wait and retry
3. If resource contention: check Fabric capacity utilization and retry during off-peak
4. If schema changed at source: update the ingest notebook's parsing logic (the dataflows
   no longer map source columns — they are retired from the pipeline path)

### 4. Spark Session Failure (bronze-to-silver, silver-to-gold)

**Symptoms:** "Spark session failed to start", "executor lost", or out-of-memory errors.

**Resolution:**
1. Check Fabric capacity (is it at 100% utilization?)
2. If out-of-memory: consider running during off-peak hours or reducing parallelism
3. If the notebook code itself has an error: check the notebook output in Fabric
4. For schema mismatches after source changes: update the transformation logic in the notebook

### 5. Delta Table Write Failure (silver-to-gold)

**Symptoms:** MERGE/write fails on a gold Delta table.

**Resolution:**
1. Check if the target table exists and is accessible
2. Check for concurrent writes (another pipeline or notebook writing to the same table)
3. If schema evolution issue: verify column types match between source and target
4. If table is corrupted: run `FSCK REPAIR TABLE` in a Spark notebook

---

## Execution Log Queries

### Check Recent Failures
```sql
SELECT activity_name, start_time, error_category, error_message, retry_attempt
FROM oem_lh.gold_pipeline_execution_log
WHERE status = 'FAILED'
  AND start_time >= current_timestamp() - INTERVAL 24 HOURS
ORDER BY start_time DESC;
```

### Check Retry Patterns
```sql
SELECT activity_name, COUNT(*) AS attempts,
       SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) AS successes,
       SUM(CASE WHEN retry_attempt > 0 THEN 1 ELSE 0 END) AS retries
FROM oem_lh.gold_pipeline_execution_log
WHERE start_time >= current_timestamp() - INTERVAL 7 DAYS
GROUP BY activity_name
ORDER BY attempts DESC;
```

### Find Repeated Failures (Escalation Trigger)
```sql
SELECT activity_name, COUNT(*) AS failure_count
FROM oem_lh.gold_pipeline_execution_log
WHERE status = 'FAILED'
  AND start_time >= current_timestamp() - INTERVAL 24 HOURS
GROUP BY activity_name
HAVING COUNT(*) >= 3
ORDER BY failure_count DESC;
```

---

## Email Notification Setup (Fabric UI)

**Pipeline-level** email notifications are configured in the Fabric workspace UI — they
cannot be set via the pipeline JSON. **Activity-level** notifications *can*: see the
`notifyOption` note below.

> ⚠️ **Notifications do not fire for on-demand runs.** They are attached to the
> *schedule*, so a pipeline you trigger manually — which is how this project is run
> today (task-010, scheduling, is On Hold) — will fail silently no matter what is
> configured here. Do not treat this setup as coverage until the pipeline is scheduled.

### Steps to Configure

1. Open the Fabric workspace: [OEMMatInsightBI Workspace](https://app.fabric.microsoft.com/groups/99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9)
2. Navigate to the orchestrator pipeline
3. **Home** > **Schedule** > **Failure notifications**
   *(The older path — Settings gear > Notifications — no longer exists.)*
4. Enable email notifications for:
   - **Pipeline failure** (after all retries exhausted)
   - **Pipeline success** (optional, for daily summary)
5. Add recipients: data engineering team email(s)
6. Save

### Activity-level `notifyOption` (JSON-settable)

**Obsolete since task-048 (2026-07-31): there are no RefreshDataflow activities left in the pipeline, so this `notifyOption` route no longer exists.** Historically, the three `RefreshDataflow` activities in `orchestrator_pipeline_bronze_to_gold` each
carry a `notifyOption` property, currently `"NoNotification"`. Setting it to
`"MailOnFailure"` in `pipeline-content.json` gives per-activity mail without touching
the UI — and, unlike the schedule-attached pipeline notification above, it is version
controlled. It covers only those three activities, so it complements rather than
replaces the pipeline-level setup.

> Choosing between these (or deferring both with a recorded reason) is **task-041**
> criterion 5. Do not configure ad hoc — the decision belongs with the error-handler
> wiring.

### Alternative: Power Automate / Logic App

For richer notifications (Slack, Teams, custom formatting):
1. Create a Power Automate flow triggered by "When a Fabric pipeline fails"
2. Configure the flow to send Teams/Slack messages with error details
3. Include: pipeline name, activity name, error message, link to pipeline run

---

## Escalation Procedures

| Severity | Condition | Action | Timeline |
|----------|-----------|--------|----------|
| Low | Single transient failure, auto-retried successfully | No action (logged) | N/A |
| Medium | Activity fails after all retries | Review execution log, re-run manually | Within 4 hours |
| High | Permanent error detected | Fix root cause, re-run pipeline | Within 2 hours |
| Critical | 3+ failures in 24 hours for same activity | Disable scheduled run, investigate root cause | Within 1 hour |

---

## Maintenance

- **Monthly:** Review execution log for recurring transient errors; tune retry intervals if needed
- **After source changes:** Verify pipeline still works; update ingest notebook parsing (EPI/WGI) or Copy activity column mappings (Azure SQL / HTTP) if schemas changed — there are no dataflow mappings on the pipeline path (task-035, task-048)
- **After Fabric updates:** Check if retry behavior or notification APIs changed
- **New error patterns:** Add to `TRANSIENT_ERROR_PATTERNS` or `PERMANENT_ERROR_PATTERNS` in the error handler notebook and update this playbook
