# Run Bronze Layer Ingestion

Execute the bronze layer data ingestion from all source systems.

## What This Command Does

This command guides you through running the bronze layer ingestion, which includes:
1. **Azure SQL Database** - Procurement and Supplier data
2. **EPI Dataset** - Environmental Performance Index data
3. **WGI Dataset** - World Governance Indicators data
4. **EU CRM Supply Shares** - Global supply concentration data

All four sources run in parallel in the Fabric pipeline.

## Prerequisites

- Access to Microsoft Fabric workspace
- Source systems available (Azure SQL, data files)
- Lakehouse `oem_lh` accessible

## Steps

### Option 1: Run via Fabric UI (Recommended for testing)

1. Navigate to Fabric workspace
2. Open pipeline: `orchestrator_pipeline_bronze_to_gold`
3. Click "Run" button
4. In the parameters dialog:
   - Set `p_full_load` = `true` (for full refresh)
   - Set `p_from_date` = `"1900-01-01"` (load all historical data)
5. Click "OK" to start execution
6. Monitor progress in the "Output" tab
7. Bronze stage should complete in ~5-10 minutes

### Option 2: Run via Azure CLI (For automation)

```bash
# Trigger pipeline run
az datafactory pipeline create-run \
  --resource-group <resource-group> \
  --factory-name <workspace-name> \
  --name orchestrator_pipeline_bronze_to_gold \
  --parameters '{"p_full_load": true, "p_from_date": "1900-01-01"}'
```

### Option 3: Run Individual Bronze Activities (For debugging)

**Bronze Procurement (Azure SQL):**
1. Open dataflow: `bronze_azureSQLdb2table`
2. Click "Refresh" button
3. Outputs: `bronze_procurement_transactional`, `bronze_supplier_ref`

**Bronze EPI:**
1. Open dataflow: `EPI_file2table`
2. Click "Refresh" button
3. Outputs: `bronze_epi2024results`

**Bronze WGI:**
1. Open dataflow: `WGI_file2table`
2. Click "Refresh" button
3. Outputs: `bronze_WB_ESGCSV`, `bronze_WB_ESGSeries`

**Bronze EU Supply Shares:**
1. Run copy activity: `bronzecopy_EUSupplyShares` from pipeline
2. Outputs: `bronze_GlobalSupplyShares`

## Validation

After bronze ingestion completes, verify data landed correctly:

```python
# In Fabric notebook or local development
from pyspark.sql import SparkSession

# Check row counts
tables = [
    "bronze_procurement_transactional",
    "bronze_supplier_ref",
    "bronze_epi2024results",
    "bronze_WB_ESGCSV",
    "bronze_WB_ESGSeries",
    "bronze_GlobalSupplyShares"
]

for table in tables:
    count = spark.table(f"oem_lh.{table}").count()
    print(f"{table}: {count:,} rows")
```

**Expected Row Counts:**
- bronze_procurement_transactional: ~100,000-200,000 rows
- bronze_supplier_ref: ~50-200 rows
- bronze_epi2024results: ~180-200 rows (countries)
- bronze_WB_ESGCSV: ~8,000-10,000 rows
- bronze_WB_ESGSeries: ~100-200 rows
- bronze_GlobalSupplyShares: ~5,000-10,000 rows

## Troubleshooting

**Azure SQL Connection Failed:**
- Check firewall rules allow Fabric IP addresses
- Verify authentication credentials in dataflow connection
- Test connection in dataflow editor

**EPI/WGI File Not Found:**
- Verify CSV files uploaded to workspace
- Check dataflow source configuration
- Ensure file paths are correct

**HTTP Copy Failed (EU Supply Shares):**
- Check internet connectivity from Fabric
- Verify GitHub URL is accessible
- Check for rate limiting

## Next Steps

After bronze ingestion succeeds:
1. Run `/run-silver` to transform to silver layer
2. Or run `/run-full-pipeline` for end-to-end execution
3. Check `/check-quality` to validate data quality

## Related Files

- `/fabric/orchestrator_pipeline_bronze_to_gold.DataPipeline/`
- `/fabric/bronze_azureSQLdb2table.Dataflow/`
- `/fabric/EPI_file2table.Dataflow/`
- `/fabric/WGI_file2table.Dataflow/`
