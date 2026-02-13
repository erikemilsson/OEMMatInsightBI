# Run Silver Layer Transformation

Execute the bronze-to-silver data cleaning and standardization transformations.

## What This Command Does

This command runs the `clean_columnsAndHeaders.Notebook` which performs:
- Column name standardization (lowercase with underscores)
- Data type conversions and casting
- Unpivoting and reshaping (WGI year columns)
- Filtering and quality checks
- Join operations (procurement + supplier reference)

**Input:** Bronze tables
**Output:** Silver tables (cleaned and validated data)

## Prerequisites

- Bronze layer tables populated (run `/run-bronze` first)
- Lakehouse `oem_lh` accessible with write permissions
- Spark compute available

## Steps

### Option 1: Run via Fabric Pipeline

1. Navigate to Fabric workspace
2. Open pipeline: `orchestrator_pipeline_bronze_to_gold`
3. If you want to run only silver transformation:
   - You cannot run individual stages from UI
   - Run full pipeline and monitor silver stage
4. Silver transformation is the "bronze-to-silver data cleaning" activity

### Option 2: Run Notebook Directly (Recommended for development)

1. Navigate to Fabric workspace
2. Open notebook: `clean_columnsAndHeaders`
3. Click "Run all" button
4. Monitor cell execution progress
5. Check outputs in lakehouse

### Option 3: Run via VS Code (Local development with Fabric sync)

```python
# Note: This requires Fabric notebook sync to local environment
# Currently a manual process - see /sync-from-fabric command

# After syncing notebook locally:
# 1. Open clean_columnsAndHeaders.Notebook/notebook-content.py
# 2. Execute cells in Python environment with PySpark
```

## Transformations Applied

### 1. EPI Data Cleaning
```python
# Input: bronze_epi2024results
# Output: silver_epi2024results
# Operations:
#   - Drop columns ending with '.old'
#   - Remove '.new' suffix from column names
#   - Cast 'code' to INTEGER
#   - Select: code, iso, country, EPI columns
```

### 2. Global Supply Shares Cleaning
```python
# Input: bronze_GlobalSupplyShares
# Output: silver_globalsupplyshares
# Operations:
#   - Convert headers to lowercase
#   - Replace spaces with underscores
#   - Drop unused 't' column
```

### 3. World Bank WGI Cleaning
```python
# Input: bronze_WB_ESGCSV + bronze_WB_ESGSeries
# Output: silver_WB
# Operations:
#   - Unpivot year columns (y_2000, y_2001, ...) to long format
#   - Filter for year 2020 only
#   - Join with ESGSeries for topic metadata
#   - Cast scores to DOUBLE
#   - Filter scores to 0-100 range
```

### 4. Procurement Data Cleaning
```python
# Input: bronze_procurement_transactional + bronze_supplier_ref
# Output: silver_procurement
# Operations:
#   - Left join procurement with supplier reference on SupplierName
#   - Convert headers to lowercase with underscores
#   - Drop duplicate columns (region, suppliername from supplier_ref)
#   - Result includes: date, materialname, quantity, unit, unitpriceeur,
#                      headquarterscountry, productioncountry
```

## Validation

After silver transformation completes, verify:

```python
# Check silver table row counts
silver_tables = [
    "silver_epi2024results",
    "silver_globalsupplyshares",
    "silver_WB",
    "silver_procurement"
]

for table in silver_tables:
    count = spark.table(f"oem_lh.{table}").count()
    print(f"{table}: {count:,} rows")
```

**Expected Row Counts:**
- silver_epi2024results: ~180-200 rows (same as bronze)
- silver_globalsupplyshares: ~5,000-10,000 rows (same as bronze)
- silver_WB: ~1,200-1,500 rows (unpivoted from wide format, filtered to 2020)
- silver_procurement: ~100,000-200,000 rows (joined with supplier ref)

**Data Quality Checks:**
```python
# Check for nulls in key fields
spark.table("oem_lh.silver_procurement").filter("date is null or materialname is null").count()
# Should be 0

# Check WB score range
spark.table("oem_lh.silver_WB").filter("score < 0 or score > 100").count()
# Should be 0
```

## Troubleshooting

**Notebook Fails to Start:**
- Check Spark compute pool status
- Verify lakehouse attachment in notebook
- Restart kernel and try again

**Bronze Tables Not Found:**
- Ensure bronze layer ran successfully first
- Check table names match exactly (case-sensitive)
- Verify lakehouse name is correct (`oem_lh`)

**Join Results in Unexpected Row Counts:**
- Check for duplicate SupplierNames in supplier_ref
- Verify join keys match (check for leading/trailing spaces)
- Review join type (left join expected)

**Schema Errors:**
- Verify bronze table schemas match expected format
- Check for schema drift in source data
- Review column name changes

## Next Steps

After silver transformation succeeds:
1. Run `/run-gold` to apply business logic
2. Or run `/check-quality` to validate data quality
3. Check silver tables in lakehouse to verify results

## Related Files

- `/fabric/clean_columnsAndHeaders.Notebook/`
- `/.claude/support/documents/architecture/medallion_architecture.md`
- `/.claude/support/documents/schemas/silver_tables.md`
