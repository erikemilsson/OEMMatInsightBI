# Troubleshooting Guide

Common issues and their solutions for the OEMMatInsightBI project.

---

## Task Management Issues

### Issue: "Task must be broken down first" error

**Symptoms:**
```
⚠️  Cannot start task-003 (Difficulty: 8)
Reason: Task must be broken down first (difficulty ≥7)
```

**Cause:** Task has difficulty ≥7 and requires subtask decomposition before work can begin.

**Solution:**
```bash
/breakdown task-003
# Follow prompts to create subtasks
# Then retry:
/complete-task task-003
```

---

### Issue: Task shows as "Blocked"

**Symptoms:**
```
❌ Cannot start task-003
Blocked by: task-002 (In Progress)
```

**Cause:** Task has unfinished dependencies.

**Solution:**
1. Check dependencies in task JSON: `cat .claude/tasks/task-003.json | grep dependencies`
2. Complete blocking tasks first
3. Run `/sync-tasks` to verify unblocked
4. Retry `/complete-task task-003`

**Workaround:** If dependency is optional (not truly blocking), edit task JSON to remove dependency.

---

### Issue: `/sync-tasks` reports JSON schema errors

**Symptoms:**
```
❌ Validation failed for task-002.json
Error: Missing required field 'difficulty'
```

**Cause:** Task JSON file is malformed or missing required fields.

**Solution:**
1. Open the reported file: `.claude/tasks/task-002.json`
2. Compare against template: `.claude/templates/task-template.json`
3. Add missing fields
4. Run `/sync-tasks` to revalidate

**Required Fields:**
- `id`, `title`, `description`, `status`, `priority`, `difficulty`, `estimatedEffort`, `acceptanceCriteria`, `dependencies`, `subtasks`

---

### Issue: Progress percentage not updating

**Symptoms:** Completed subtasks but parent task still shows 0%

**Cause:** `/sync-tasks` hasn't run recently.

**Solution:**
```bash
/sync-tasks
# This recalculates all progress and updates task-overview.md
```

**Note:** Progress is not real-time - run `/sync-tasks` after each subtask completion.

---

## Pipeline Issues (Fabric Workspace)

### Issue: Bronze ingestion fails - Azure SQL connection timeout

**Symptoms:** `bronze_procurement` dataflow fails with timeout error

**Diagnosis:**
1. Check Azure SQL firewall: Is Fabric IP whitelisted?
2. Check Azure SQL service health
3. Verify connection string in dataflow

**Solution:**
- Add Fabric service tag to SQL firewall rules
- Increase dataflow timeout (currently 12 hours)
- Check network connectivity from Fabric

**Related Task:** Task 011 (Error Handling) - designed retry logic for transient failures

---

### Issue: Silver transformation notebook fails - Spark session error

**Symptoms:** `clean_columnsAndHeaders.Notebook` fails to start Spark session

**Diagnosis:**
- Check Fabric capacity usage (may be at limit)
- Review Spark logs in notebook execution history

**Solution:**
- Restart Spark pool in Fabric workspace
- Increase capacity units if at limit
- Optimize PySpark code to reduce memory usage

**Related Task:** Task 012 (Performance Optimization) - designed optimization strategies

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

**Related Task:** Task 002 (DAX Measures) - comprehensive measure library design

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

**Related Task:** Task 004 (RLS Security) - 6 roles designed with correct DAX filters

---

## Data Quality Issues

### Issue: High unmapped value count

**Symptoms:** `gold_unmapped_procurement_audit` has many rows

**Diagnosis:** Check alias resolution logic

**Solution:**
1. Review aliases: `/.claude/reference/country_alias_mapping.md`
2. Add missing aliases to lookup tables
3. Re-run silver-to-gold transformation

**Related Tasks:**
- Task 001 (DQ Visibility) - creates dashboard to monitor
- Task 007 (Data Quality Checks) - framework to validate

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

**Related Task:** Task 007 (Data Quality) - designed aggregate reconciliation check

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

**Related Task:** Task 008 (Unit Tests) - framework complete

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

### Issue: Merge conflict in task JSON files

**Symptoms:** Git conflict in `.claude/tasks/task-XXX.json`

**Solution:**
1. **Don't manually edit JSON during conflict** - corrupts structure
2. Choose one version (local or remote)
3. Run `/sync-tasks` to validate
4. If needed, manually re-apply changes to chosen version

**Prevention:** Always run `/sync-tasks` before committing task JSON files.

---

## Performance Issues

### Issue: Pipeline takes >1 hour to complete

**Symptoms:** End-to-end runtime very slow

**Diagnosis:** Check current runtime by stage (see task-012.json notes)

**Solution (Priority Order):**
1. **Enable incremental load** (Task 006) - 94% time reduction expected
2. **Implement partitioning** (Task 012) - 20-40% improvement
3. **Enable V-Order** (Task 012) - 10-30% improvement for DirectLake
4. **Optimize transformations** - broadcast joins, caching

**Related Task:** Task 012 (Performance Optimization) - comprehensive strategy

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

**Related Tasks:**
- Task 002 (DAX Measures) - designed with performance in mind
- Task 012 (Performance) - warehouse indexing for BI queries

---

## Common Error Messages

### "Task already in progress"

**Solution:** Continue current subtask or view progress with `/sync-tasks`

### "Circular dependency detected"

**Solution:** Edit task JSON files to remove circular references

### "Invalid status transition"

**Solution:** Don't reopen finished tasks - create new tasks instead

### "Subtask effort doesn't match parent"

**Solution:** Recalculate - subtask efforts should sum to parent estimate

---

## Getting Additional Help

**For Task Management:**
- See `/.claude/reference/workflow-patterns.md`
- See `/.claude/reference/task-management-rules.md`

**For Technical Issues:**
- See relevant `/.claude/context/` documentation
- Check `/project_definition.md` for architecture details

**For Data Issues:**
- See `/.claude/context/data_quality_framework.md`
- Check audit tables in gold layer

---

*Last Updated: 2025-11-16*
*For frequently asked questions, see FAQ.md*
