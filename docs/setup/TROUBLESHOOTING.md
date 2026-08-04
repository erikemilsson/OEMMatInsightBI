# Troubleshooting Guide

Common issues and their solutions for the OEMMatInsightBI project.

---

## Pipeline Issues (Fabric Workspace)

### Issue: Bronze ingestion fails - Azure SQL connection timeout

**Symptoms:** `bronze_copy_procurement_transactional` or `bronze_copy_supplier_ref`
fails. (Before 2026-07-31 this was a `bronze_procurement` dataflow refresh; that
dataflow is retired and deleted.)

**Read the error text before diagnosing — the four cases are distinct:**

| Error | Meaning |
|---|---|
| `Database ... is not currently available` | **Most likely.** Serverless auto-pause; the DB is resuming. Says nothing about credentials. |
| `Login failed for user X` | A credential IS bound and is wrong |
| `Credentials are required to connect` | NO credential bound |
| `Login timeout expired` / `TCP Provider` | Never reached the server — firewall/port |

**Diagnosis:**
1. `az sql db show -g RG1 -s procurement-supplier -n procurement-supplier-db --query '{status:status,autoPause:autoPauseDelay,resumed:resumedDate}'`
   — the DB is serverless (`GP_S_Gen5`, `autoPauseDelay: 60`), so a run after 60 min
   idle hits a ~40s resume window and the first attempt fails
2. Check the Fabric connection `oem_azuresql_procurement` is still shared with
   `Fabric-SPN-Access` (needed for SPN-driven deploys)
3. Only if the error is a genuine timeout: check the Azure SQL firewall

**Solution:**
- Auto-pause resume: **no action needed** — `retry 3 / 300s` on both Copy activities
  covers it. A cold run may show one failed attempt then succeed. Do NOT set these
  activities to retry 0.
- Credential problems: re-enter it on the connection, username `erikdatabase`
  (NOT `erikdatabase2`, a stale contained-DB user)

---

### Issue: Silver transformation notebook fails - Spark session error

**Symptoms:** `bronze-to-silver.Notebook` fails to start Spark session

**Diagnosis:**
- Check Fabric capacity usage (may be at limit)
- Review Spark logs in notebook execution history

**Solution:**
- Restart Spark pool in Fabric workspace
- Increase capacity units if at limit
- Optimize PySpark code to reduce memory usage

---

### Issue: Gold layer creation fails - MERGE operation error

**Symptoms:** `silver-to-gold2.Notebook` fails with "MERGE not supported" error

**Diagnosis:** Check if tables are Delta format (not Parquet)

**Solution:**
```python
# Verify table format
spark.sql("DESCRIBE FORMATTED oem_lh.silver_procurement").show()
# Look for "Provider: delta"

# If Parquet, convert to Delta:
df = spark.read.parquet("path/to/parquet")
df.write.format("delta").saveAsTable("oem_lh.silver_procurement")
```

**Prevention:** Always use Delta Lake format (ADR-002).

---

## Semantic Model Issues

### Issue: DAX measure returns blank

**Symptoms:** Measure shows (Blank) in Power BI

**Diagnosis:**
1. Check measure formula for errors
2. Verify referenced columns exist
3. Test with simple SUM first

**Solution:**
```dax
# Debug pattern
Test Measure =
VAR BaseValue = SUM(fact_procurement[spend_eur])
RETURN
    IF(ISBLANK(BaseValue), "No Data", BaseValue)
```

---

### Issue: Row-Level Security not filtering correctly

**Symptoms:** User sees data from wrong region

**Diagnosis:**
1. Check role assignment: Is user in correct role?
2. Test with "View as Role" in Power BI Desktop
3. Verify DAX filter syntax

**Solution:**
```dax
# Verify filter is applied
[region] = "Americas"

# Not:
[region] == "Americas"  // Wrong syntax!
```

---

## Data Quality Issues

### Issue: High unmapped value count

**Symptoms:** `gold_unmapped_procurement_audit` has many rows

**Diagnosis:** Check alias resolution logic

**Solution:**
1. Review aliases: [`docs/transformations/alias_mappings.md`](../transformations/alias_mappings.md)
2. Add missing aliases to lookup tables
3. Re-run silver-to-gold transformation

---

### Issue: Spend totals don't reconcile (silver vs gold)

**Symptoms:** Silver total spend ≠ Gold total spend

**Diagnosis:**
```python
# Check reconciliation
silver_total = spark.sql("SELECT SUM(quantity * unitpriceeur) FROM silver_procurement").collect()[0][0]
gold_total = spark.sql("SELECT SUM(spend_eur) FROM fact_procurement").collect()[0][0]
diff = abs(silver_total - gold_total)
print(f"Difference: {diff}")
```

**Solution:**
- If difference > 0.01: Investigate transformation logic
- Check for rows dropped during gold transformation
- Verify unmapped audit tables

---

## Development Environment Issues

### Issue: pytest tests fail - PySpark session error

**Symptoms:**
```
ModuleNotFoundError: No module named 'pyspark'
```

**Solution:**
```bash
# Activate virtual environment
source .venv/bin/activate  # Or: .venv\Scripts\activate on Windows

# Install test dependencies
pip install -r requirements-test.txt

# Run tests
pytest tests/ -v
```

---

### Issue: Cannot import from src/transformations

**Symptoms:**
```
ImportError: No module named 'transformations'
```

**Solution:**
```bash
# Add src to PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"

# Or in pytest.ini (already configured):
[pytest]
pythonpath = src
```

---

## Git & Version Control Issues

### Issue: Large files committed (notebook outputs)

**Symptoms:** Repo size grows, slow pushes

**Solution:**
```bash
# Clean notebook outputs before committing
jupyter nbconvert --clear-output --inplace fabric/**/*.ipynb

# Add to .gitignore
echo "*.ipynb_checkpoints" >> .gitignore
```

---

### Issue: Merge conflict in `.claude/tasks/` JSON files

**Symptoms:** Git conflict in a `.claude/tasks/task-XXX.json` file.

**Solution:**
1. **Don't manually edit JSON during conflict** - corrupts structure
2. Choose one version (local or remote), then re-apply the intended change by hand
3. Validate the JSON parses before committing

> Note: the `/complete-task` and `/sync-tasks` commands are deprecated. Task JSON is now hand-maintained against [`docs/PROJECT_PROGRESS.md`](../PROJECT_PROGRESS.md); terminal task files live under the gitignored `.claude/tasks/archive/`.

---

## Performance Issues

### Issue: Pipeline takes longer than expected to complete

**Symptoms:** End-to-end runtime higher than the measured baseline.

**Diagnosis:** Compare against the measured 3-run warm-cache baseline in [`performance_baseline.md`](../performance_baseline.md) — functional total 17m 40s (Bronze 74 s, Silver 142 s, Gold 844 s; pipeline total ~19.7 min with handler + ramp).

**Solution (Priority Order):**
1. **Confirm incremental load** is active (`p_full_load=false`) — full loads reprocess everything
2. **Check Fabric capacity utilization** — a busy capacity inflates every stage
3. **Verify V-Order** on gold Delta tables (see `performance_optimized.md`)
4. **Optimize transformations** — broadcast joins, caching

---

### Issue: Power BI report loads slowly (>10 seconds)

**Symptoms:** Visuals take long to render

**Diagnosis:**
1. Check if using DirectLake mode (should be fast)
2. Test individual DAX measures for performance

**Solution:**
```dax
# Optimize expensive measures with variables
Slow Measure =
    SUMX(
        fact_procurement,
        fact_procurement[quantity] * RELATED(gold_dim_material[cost])
    )

Optimized Measure =
VAR MaterialCosts = gold_dim_material  // Cache lookup
RETURN
    SUMX(
        fact_procurement,
        VAR MaterialCost = LOOKUPVALUE(MaterialCosts[cost], MaterialCosts[material_key], fact_procurement[material_key])
        RETURN fact_procurement[quantity] * MaterialCost
    )
```

- Task 012 (Performance) - warehouse indexing for BI queries

---

## Getting Additional Help

**For pipeline / Fabric issues:**
- [`docs/architecture/orchestration.md`](../architecture/orchestration.md) — pipeline activity detail
- [`docs/error_recovery_playbook.md`](../error_recovery_playbook.md) — per-activity retry table and resolution steps
- [`docs/architecture/fabric-artifacts-inventory.md`](../architecture/fabric-artifacts-inventory.md) — artifact status and dependencies

**For data / model issues:**
- [`docs/data_quality_architecture.md`](../data_quality_architecture.md) — DQ observability surface
- [`docs/dax_measure_library.md`](../dax_measure_library.md) — as-built measure catalogue
- [`docs/architecture/semantic_model.md`](../architecture/semantic_model.md) — DirectLake model on `oem_lh`

**For the project spec:**
- [`.claude/spec_v1.md`](../../.claude/spec_v1.md) — the project specification (source of truth)

---

*For frequently asked questions, see [`FAQ.md`](../guides/FAQ.md)*
