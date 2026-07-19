# Incremental Load Strategy - OEMMatInsightBI

**Status:** Design Complete
**Last Updated:** 2025-11-03
**Owner:** Claude Code

## Executive Summary

This document defines the incremental load strategy for the OEMMatInsightBI data pipeline. The pipeline currently has parameters (`p_full_load`, `p_from_date`) but lacks implementation logic. This strategy focuses on **procurement transactional data** for incremental loading while maintaining full refresh for reference and external data sources.

**Key Decisions:**
- ✅ **Incremental:** Procurement transactional data (daily growth)
- ✅ **Full Refresh:** Reference tables, external ESG data (annual snapshots)
- ✅ **Merge Strategy:** UPSERT using Delta Lake MERGE operations
- ✅ **High-Water Mark:** Metadata table tracks last successful load dates

**Expected Benefits:**
- **Performance:** 70-90% reduction in load time for incremental runs
- **Scalability:** Handles growing data volume without linear time increase
- **Freshness:** Daily incremental loads vs weekly full refreshes
- **Cost:** Reduced compute resource consumption

---

## 1. Incremental Load Requirements by Table

### Table Classification Matrix

| Table Name | Layer | Incremental Key | Strategy | Update Frequency | Rationale |
|------------|-------|----------------|----------|------------------|-----------|
| **bronze_procurement_transactional** | Bronze | `Date` | 🔄 **Incremental** | Daily | Transactional data, grows continuously |
| **bronze_supplier_ref** | Bronze | N/A | 🔁 Full Refresh | Weekly | Small reference table (~100 rows), changes rare |
| **bronze_epi2024results** | Bronze | N/A | 🔁 Full Refresh | Annual | Annual snapshot, version-based |
| **bronze_wgi_raw** | Bronze | N/A | 🔁 Full Refresh | Annual | Annual snapshot, API provides full dataset |
| **bronze_GlobalSupplyShares** | Bronze | N/A | 🔁 Full Refresh | Annual | Static material shares, rarely updated |
| **silver_procurement** | Silver | `date` | 🔄 **Incremental** | Daily | Derived from bronze procurement |
| **silver_supplier** | Silver | N/A | 🔁 Full Refresh | Weekly | Derived from bronze supplier (small) |
| **silver_epi** | Silver | N/A | 🔁 Full Refresh | Annual | Cleaned EPI data |
| **silver_wgi** | Silver | N/A | 🔁 Full Refresh | Annual | Cleaned WGI data |
| **fact_procurement** | Gold | `date_key` | 🔄 **Incremental** | Daily | Fact table with surrogate keys |
| **fact_epi_score** | Gold | `year` | 🔁 Full Refresh | Annual | Low volume, full refresh acceptable |
| **fact_supply_share** | Gold | N/A | 🔁 Full Refresh | Annual | Static shares, full refresh acceptable |
| **gold_dim_country** | Gold | N/A | 🔄 **SCD Type 1** | On change | Slowly changing dimension |
| **gold_dim_material** | Gold | N/A | 🔄 **SCD Type 1** | On change | Slowly changing dimension |
| **gold_dim_date** | Gold | N/A | 🔁 Append Only | Daily | Date dimension, append new dates |
| **gold_dim_indicator** | Gold | N/A | 🔁 Full Refresh | Annual | Static indicators |
| **gold_dim_stage** | Gold | N/A | 🔁 Full Refresh | Rarely | Static lifecycle stages |

### Load Strategy Summary

- **🔄 Incremental (3 tables):** procurement transactional data + fact_procurement
- **🔁 Full Refresh (14 tables):** Reference data, external data, small dimensions
- **Expected Time Savings:** Incremental run ~5 min vs Full load ~30 min (83% faster)

---

## 2. Incremental Key Selection

### Procurement Data Incremental Key

**Selected Key:** `Date` (procurement transaction date)

**Analysis:**

| Candidate Key | Pros | Cons | Selected? |
|---------------|------|------|-----------|
| **Date** | ✅ Business-meaningful<br>✅ Indexed in source<br>✅ Supports time-based filtering | ⚠️ Late-arriving transactions possible | ✅ **YES** |
| **Modified_Date** | ✅ Captures updates to existing records | ❌ Not available in source schema | ❌ No |
| **Surrogate_ID** | ✅ Unique identifier | ❌ Doesn't support date filtering<br>❌ Requires full scan | ❌ No |

**Decision Rationale:**
- Procurement transactions are time-series data (ordered by Date)
- Source system (Azure SQL) has index on `Date` column
- Late-arriving transactions are acceptable (handled by merge logic)
- Date-based watermark aligns with business reporting cycles

**Handling Late-Arriving Data:**
```
Strategy: Look-back window of 7 days
- Incremental load: Load all records where Date >= (last_load_date - 7 days)
- Merge operation: UPDATE existing records, INSERT new records
- Ensures late transactions (e.g., weekend batches arriving Monday) are captured
```

### Silver/Gold Incremental Keys

| Layer | Table | Incremental Key | Notes |
|-------|-------|----------------|-------|
| **Silver** | `silver_procurement` | `date` | Derived from bronze `Date`, after cleaning |
| **Gold** | `fact_procurement` | `date_key` | Integer format YYYYMMDD (e.g., 20240115) |

---

## 3. Load Strategies by Layer

### Bronze Layer Strategy

#### Procurement (Incremental)

**Current Behavior:**
```powerquery
// In bronze_azureSQLdb2table.Dataflow
Source = Sql.Database("server", "db"),
Procurement = Source{[Schema="dbo",Item="Procurement"]}[Data]
// Loads ALL rows every time
```

**Target Behavior:**
```powerquery
// Modified with parameter support
let
    Source = Sql.Database("server", "db"),
    Procurement = Source{[Schema="dbo",Item="Procurement"]}[Data],

    // Get parameter (default to full load if not set)
    FromDate = try #"Parameter: p_from_date" otherwise #datetime(1900, 1, 1, 0, 0, 0),

    // Filter based on parameter
    FilteredRows = if FromDate = #datetime(1900, 1, 1, 0, 0, 0) then
                      Procurement
                   else
                      Table.SelectRows(Procurement, each [Date] >= FromDate),

    // Apply look-back window (7 days) for late-arriving data
    LookBackDate = Date.AddDays(FromDate, -7),
    FinalFiltered = if FromDate = #datetime(1900, 1, 1, 0, 0, 0) then
                       FilteredRows
                    else
                       Table.SelectRows(Procurement, each [Date] >= LookBackDate)
in
    FinalFiltered
```

**SQL Query Pushdown (Preferred):**
```powerquery
// Generate SQL WHERE clause for better performance
let
    Source = Sql.Database("server", "db"),
    FromDate = try #"Parameter: p_from_date" otherwise "1900-01-01",

    // Build SQL with WHERE clause
    SqlQuery = if FromDate = "1900-01-01" then
                  "SELECT * FROM dbo.Procurement"
               else
                  "SELECT * FROM dbo.Procurement WHERE Date >= '" & FromDate & "'",

    QueryResult = Sql.Database("server", "db"){[Name=SqlQuery]}[Data]
in
    QueryResult
```

**Benefits of SQL Pushdown:**
- ✅ Leverages database indexes
- ✅ Reduces data transfer over network
- ✅ Faster execution (filter at source vs in memory)

#### Reference Tables (Full Refresh)

**Strategy:** Continue current behavior (overwrite)

```python
# Example: bronze_supplier_ref
df_suppliers = spark.read.format("sqlserver").load()
df_suppliers.write.format("delta").mode("overwrite").saveAsTable("bronze_supplier_ref")
```

**Rationale:**
- Small data volume (~100-500 rows)
- Full refresh faster than merge logic overhead
- Rare changes (quarterly at most)

### Silver Layer Strategy

#### Procurement (Incremental with Merge)

**Current Behavior:**
```python
# In bronze-to-silver.Notebook
bronze_procurement = spark.table("bronze_procurement_transactional")
silver_procurement = transform_procurement(bronze_procurement)
# OVERWRITES entire table
silver_procurement.write.format("delta").mode("overwrite").saveAsTable("silver_procurement")
```

**Target Behavior (Incremental Merge):**
```python
from delta.tables import DeltaTable

def incremental_load_silver_procurement(p_full_load=False, p_from_date="1900-01-01"):
    """
    Load silver procurement with incremental logic

    Args:
        p_full_load: If True, reload all data (overwrite)
        p_from_date: Watermark date for incremental load
    """

    # Read new/changed bronze records
    if p_full_load:
        bronze_df = spark.table("oem_lh.bronze_procurement_transactional")
    else:
        # Incremental: only load records >= watermark date (with 7-day look-back)
        from datetime import datetime, timedelta
        watermark_date = datetime.strptime(p_from_date, "%Y-%m-%d")
        lookback_date = watermark_date - timedelta(days=7)

        bronze_df = spark.table("oem_lh.bronze_procurement_transactional") \
                         .filter(f"Date >= '{lookback_date.strftime('%Y-%m-%d')}'")

    # Transform bronze → silver
    silver_df = transform_procurement(bronze_df)

    # Check if target table exists
    if not spark.catalog.tableExists("oem_lh.silver_procurement"):
        # First load: create table
        silver_df.write.format("delta").mode("overwrite").saveAsTable("oem_lh.silver_procurement")
        print(f"✓ Created silver_procurement with {silver_df.count():,} rows")
    else:
        # Incremental: MERGE into existing table
        target_table = DeltaTable.forName(spark, "oem_lh.silver_procurement")

        # Define merge keys (natural key for procurement)
        merge_condition = """
            target.date = source.date AND
            target.materialname = source.materialname AND
            target.suppliername = source.suppliername AND
            target.region = source.region
        """

        # Perform MERGE (UPSERT)
        (target_table.alias("target")
         .merge(silver_df.alias("source"), merge_condition)
         .whenMatchedUpdateAll()   # UPDATE if key exists (late-arriving data)
         .whenNotMatchedInsertAll() # INSERT if key doesn't exist (new data)
         .execute())

        print(f"✓ Merged {silver_df.count():,} rows into silver_procurement")

    return silver_df
```

**Merge Key Selection:**

**Natural Key for Procurement:**
```
(date, materialname, suppliername, region)
```

**Rationale:**
- Combination uniquely identifies a transaction
- Handles updates to existing transactions (e.g., corrections)
- No need for surrogate key at silver layer

**Deduplication Strategy:**

If source data has duplicates:
```python
# Deduplicate before merge
silver_df_dedup = (silver_df
    .withColumn("row_num", F.row_number().over(
        Window.partitionBy("date", "materialname", "suppliername", "region")
              .orderBy(F.desc("load_timestamp"))  # Keep most recent
    ))
    .filter(F.col("row_num") == 1)
    .drop("row_num"))
```

### Gold Layer Strategy

#### Fact Tables (Incremental with Merge)

**fact_procurement Incremental Load:**

```python
from delta.tables import DeltaTable

def incremental_load_fact_procurement(p_full_load=False, p_from_date="1900-01-01"):
    """
    Load fact_procurement with incremental logic

    Args:
        p_full_load: If True, reload all data
        p_from_date: Watermark date for incremental load
    """

    # Read changed silver records
    if p_full_load:
        silver_df = spark.table("oem_lh.silver_procurement")
    else:
        watermark_date_key = int(p_from_date.replace("-", ""))  # 2024-01-15 → 20240115
        silver_df = spark.table("oem_lh.silver_procurement") \
                         .filter(f"date_key >= {watermark_date_key - 7}")  # 7-day look-back

    # Join with dimensions to get surrogate keys
    fact_df = (silver_df
        .join(dim_country, silver_df.supplier_country == dim_country.iso3, "left")
        .join(dim_material, silver_df.material_name_std == dim_material.material_name, "left")
        .select(
            F.col("date_key"),
            F.col("country_key").alias("supplier_hq_country_key"),
            F.col("material_key"),
            F.col("quantity_base"),
            F.col("unitprice_eur"),
            (F.col("quantity_base") * F.col("unitprice_eur")).alias("spend_eur")
        ))

    # Check if target exists
    if not spark.catalog.tableExists("oem_lh.fact_procurement"):
        fact_df.write.format("delta").mode("overwrite").saveAsTable("oem_lh.fact_procurement")
        print(f"✓ Created fact_procurement with {fact_df.count():,} rows")
    else:
        # Incremental: MERGE
        target_table = DeltaTable.forName(spark, "oem_lh.fact_procurement")

        # Merge on surrogate keys + date
        merge_condition = """
            target.date_key = source.date_key AND
            target.material_key = source.material_key AND
            target.supplier_hq_country_key = source.supplier_hq_country_key
        """

        (target_table.alias("target")
         .merge(fact_df.alias("source"), merge_condition)
         .whenMatchedUpdateAll()    # UPDATE spend if transaction updated
         .whenNotMatchedInsertAll()  # INSERT new transactions
         .execute())

        print(f"✓ Merged {fact_df.count():,} rows into fact_procurement")
```

**Fact Table Merge Key:**
```
(date_key, material_key, supplier_hq_country_key)
```

**Note:** If multiple transactions per day for same material/supplier, use aggregation:
```python
fact_df_agg = fact_df.groupBy("date_key", "material_key", "supplier_hq_country_key") \
                     .agg(
                         F.sum("quantity_base").alias("total_quantity"),
                         F.avg("unitprice_eur").alias("avg_unitprice"),
                         F.sum("spend_eur").alias("total_spend")
                     )
```

#### Dimension Tables (SCD Type 1)

**gold_dim_country (Slowly Changing Dimension Type 1):**

```python
def load_dim_country_scd1():
    """
    Load country dimension with SCD Type 1 (overwrite changes)
    """

    # Source: silver layer + enrichment
    silver_countries = spark.table("oem_lh.silver_supplier") \
                            .select("supplier_country").distinct()

    # Generate dimension records with surrogate keys
    dim_df = (silver_countries
        .withColumn("country_key", stable_key("supplier_country"))
        .withColumn("country_name", F.col("supplier_country"))
        .withColumn("iso3", lookup_iso3(F.col("supplier_country")))
        .withColumn("last_updated", F.current_timestamp()))

    # MERGE (not overwrite) to preserve existing keys
    if not spark.catalog.tableExists("oem_lh.gold_dim_country"):
        dim_df.write.format("delta").mode("overwrite").saveAsTable("oem_lh.gold_dim_country")
    else:
        target = DeltaTable.forName(spark, "oem_lh.gold_dim_country")

        (target.alias("target")
         .merge(dim_df.alias("source"), "target.country_key = source.country_key")
         .whenMatchedUpdate(set={
             "country_name": "source.country_name",
             "iso3": "source.iso3",
             "last_updated": "source.last_updated"
         })
         .whenNotMatchedInsertAll()
         .execute())
```

**SCD Type 1 Characteristics:**
- Overwrites changed attributes (no history tracking)
- Surrogate key remains stable (xxhash64 based on business key)
- Sufficient for slowly changing attributes (country names, ISO codes)

**If SCD Type 2 Required (Future):**
```python
# Add columns: valid_from, valid_to, is_current
# On change: expire old record (is_current = False), insert new record (is_current = True)
```

---

## 4. High-Water Mark Tracking

### Metadata Table Schema

**Table:** `bronze_load_metadata`

```python
from pyspark.sql.types import StructType, StructField, StringType, DateType, TimestampType, LongType

metadata_schema = StructType([
    StructField("source_table", StringType(), False),      # e.g., "bronze_procurement_transactional"
    StructField("last_load_date", DateType(), False),      # Max date loaded (watermark)
    StructField("load_timestamp", TimestampType(), False), # When load completed
    StructField("rows_loaded", LongType(), True),          # Count of rows in this load
    StructField("load_status", StringType(), False),       # SUCCESS, FAILED, IN_PROGRESS
    StructField("execution_id", StringType(), True)        # Pipeline run ID (for debugging)
])

# Initialize table (first run only)
initial_metadata = spark.createDataFrame([
    ("bronze_procurement_transactional", date(1900, 1, 1), datetime.now(), 0, "SUCCESS", None)
], schema=metadata_schema)

initial_metadata.write.format("delta").mode("overwrite").saveAsTable("oem_lh.bronze_load_metadata")
```

### Usage Pattern

**Before Load: Get Watermark**
```python
def get_last_load_date(source_table):
    """Retrieve last successful load date for a table"""

    result = spark.sql(f"""
        SELECT last_load_date
        FROM oem_lh.bronze_load_metadata
        WHERE source_table = '{source_table}'
          AND load_status = 'SUCCESS'
        ORDER BY load_timestamp DESC
        LIMIT 1
    """).collect()

    if result:
        return result[0]["last_load_date"]
    else:
        return date(1900, 1, 1)  # Default: load all data

# Usage in pipeline
p_from_date = get_last_load_date("bronze_procurement_transactional")
```

**After Load: Update Watermark**
```python
def update_load_metadata(source_table, max_date, rows_loaded, status="SUCCESS"):
    """Update metadata after successful load"""

    new_metadata = spark.createDataFrame([
        (source_table, max_date, datetime.now(), rows_loaded, status, dbutils.widgets.get("execution_id"))
    ], schema=metadata_schema)

    new_metadata.write.format("delta").mode("append").saveAsTable("oem_lh.bronze_load_metadata")

# Usage after load
max_date_loaded = silver_df.agg(F.max("date")).collect()[0][0]
rows_loaded = silver_df.count()
update_load_metadata("bronze_procurement_transactional", max_date_loaded, rows_loaded)
```

**Error Handling:**
```python
try:
    # Perform incremental load
    load_procurement_incremental(p_from_date)
    update_load_metadata("bronze_procurement_transactional", max_date, rows, "SUCCESS")
except Exception as e:
    update_load_metadata("bronze_procurement_transactional", p_from_date, 0, "FAILED")
    raise e
```

---

## 5. Pipeline Parameter Wiring

### Pipeline Parameters

**Existing Parameters (orchestrator_pipeline_bronze_to_gold):**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `p_full_load` | Boolean | `false` | If true, perform full refresh instead of incremental |
| `p_from_date` | String | `"1900-01-01"` | Watermark date for incremental loads (YYYY-MM-DD) |

### Parameter Flow

```
Pipeline Parameters
  ├─ p_full_load → Dataflow activities (via expression)
  │                 └─ If true: load all data
  │                 └─ If false: use p_from_date filter
  │
  └─ p_from_date → Notebook activities (via widget)
                   └─ Get watermark from metadata table
                   └─ Filter bronze data >= watermark
                   └─ Merge into silver/gold layers
```

### Dataflow Parameter Passing

**In Pipeline Activity:**
```json
{
  "name": "bronze_procurement_dataflow",
  "type": "RefreshDataflow",
  "typeProperties": {
    "dataflow": "bronze_azureSQLdb2table",
    "parameters": {
      "p_from_date": {
        "value": "@pipeline().parameters.p_from_date",
        "type": "Expression"
      }
    }
  }
}
```

**In Dataflow (bronze_azureSQLdb2table.Dataflow):**
```powerquery
// Define parameter
Parameter: p_from_date = "1900-01-01"

// Use in query
let
    FromDate = #"Parameter: p_from_date",
    FilteredData = Table.SelectRows(Source, each [Date] >= Date.FromText(FromDate))
in
    FilteredData
```

### Notebook Parameter Passing

**In Pipeline Activity:**
```json
{
  "name": "clean_columnsAndHeaders",
  "type": "ExecuteNotebook",
  "typeProperties": {
    "notebook": "clean_columnsAndHeaders",
    "parameters": {
      "p_full_load": {
        "value": "@pipeline().parameters.p_full_load",
        "type": "Expression"
      },
      "p_from_date": {
        "value": "@pipeline().parameters.p_from_date",
        "type": "Expression"
      }
    }
  }
}
```

**In Notebook (bronze-to-silver.Notebook):**
```python
# Get parameters from pipeline
p_full_load = dbutils.widgets.get("p_full_load").lower() == "true"
p_from_date = dbutils.widgets.get("p_from_date")

# Use in load logic
if p_full_load:
    print("Performing FULL LOAD...")
    load_mode = "overwrite"
else:
    print(f"Performing INCREMENTAL LOAD from {p_from_date}...")
    load_mode = "merge"

# Call incremental load function
incremental_load_silver_procurement(p_full_load, p_from_date)
```

### Dynamic Watermark (Advanced)

**Automatically retrieve watermark from metadata table:**

```python
# In notebook startup cell
from datetime import date

# Get parameters
p_full_load = dbutils.widgets.get("p_full_load").lower() == "true"
p_from_date_override = dbutils.widgets.get("p_from_date")  # Optional manual override

# Determine watermark
if p_full_load:
    p_from_date = "1900-01-01"  # Load all data
elif p_from_date_override != "1900-01-01":
    p_from_date = p_from_date_override  # Use manual override
else:
    # Auto-retrieve from metadata table
    p_from_date = get_last_load_date("bronze_procurement_transactional").strftime("%Y-%m-%d")

print(f"Load Mode: {'FULL' if p_full_load else 'INCREMENTAL'}")
print(f"Watermark Date: {p_from_date}")
```

---

## 6. Performance Optimization

### Expected Performance Gains

**Assumptions:**
- Procurement table: 100,000 rows/year (avg ~275 rows/day)
- Daily incremental load: ~300 rows (275 current + 25 late-arriving)
- Full table size: 500,000 rows (5 years history)

**Load Time Comparison:**

| Operation | Full Load | Incremental | Savings |
|-----------|-----------|-------------|---------|
| **Bronze Ingestion** | 120 sec | 5 sec | 96% |
| **Silver Transformation** | 180 sec | 10 sec | 94% |
| **Gold Merge** | 240 sec | 15 sec | 94% |
| **Total Pipeline** | **540 sec (9 min)** | **30 sec** | **94%** |

**Actual Performance (Measure After Implementation):**
```python
# Add timing to notebook
import time

start_time = time.time()
incremental_load_silver_procurement(p_full_load, p_from_date)
elapsed_time = time.time() - start_time

print(f"Execution Time: {elapsed_time:.2f} seconds")

# Log to performance table
log_performance_metric("silver_procurement", elapsed_time, rows_processed)
```

### Optimization Techniques

**1. Partition Pruning**
```python
# Partition bronze tables by year/month for faster filtering
df.write.format("delta") \
   .partitionBy("year", "month") \
   .saveAsTable("bronze_procurement_transactional")

# Query with partition filter
spark.table("bronze_procurement_transactional") \
     .filter("year = 2024 AND month >= 10")  # Prunes partitions
```

**2. Z-Ordering (Delta Lake)**
```sql
-- Optimize table for date-based queries
OPTIMIZE oem_lh.bronze_procurement_transactional ZORDER BY (Date);

-- Materialize frequently queried date ranges
OPTIMIZE oem_lh.fact_procurement ZORDER BY (date_key, material_key);
```

**3. Reduce Shuffle Operations**
```python
# Broadcast small dimension tables (< 10 MB)
from pyspark.sql.functions import broadcast

fact_df = silver_df.join(
    broadcast(dim_country),  # Broadcast to all executors
    "supplier_country",
    "left"
)
```

**4. Caching for Iterative Operations**
```python
# Cache silver layer if used multiple times
silver_df.cache()

# Materialize cache
silver_df.count()

# Use in multiple joins
fact_procurement = join_with_dimensions(silver_df)
fact_quality = aggregate_quality_metrics(silver_df)

# Unpersist when done
silver_df.unpersist()
```

---

## 7. Testing & Validation

### Test Scenarios

**Scenario 1: First Load (Full Refresh)**
```python
# Parameters
p_full_load = True
p_from_date = "1900-01-01"

# Expected Behavior
- Load ALL rows from source
- CREATE target tables (no merge)
- Update metadata with max date

# Validation
assert fact_procurement.count() == bronze_procurement.count()
assert metadata["load_status"] == "SUCCESS"
```

**Scenario 2: Daily Incremental Load**
```python
# Parameters
p_full_load = False
p_from_date = "2024-11-02"  # Yesterday's date

# Expected Behavior
- Load rows where Date >= 2024-10-26 (7-day look-back)
- MERGE into target (UPDATE + INSERT)
- Update metadata with new max date

# Validation
assert rows_loaded == expected_daily_volume (±10%)
assert no_duplicate_keys()
```

**Scenario 3: Late-Arriving Data**
```python
# Simulate late arrival
# Load Day 1: Date = 2024-11-01, 100 rows
# Load Day 2: Date = 2024-11-02, 120 rows + 5 late rows for 2024-11-01

# Expected Behavior
- 7-day look-back captures late rows
- Merge UPDATES 5 existing rows (if changed)
- Merge INSERTS 120 new rows

# Validation
assert fact_procurement.filter("date_key = 20241101").count() == 105
assert fact_procurement.filter("date_key = 20241102").count() == 120
```

**Scenario 4: Reprocessing (Manual Backfill)**
```python
# Parameters
p_full_load = False
p_from_date = "2024-01-01"  # Reprocess entire year

# Expected Behavior
- Load 365 days of data
- MERGE into target (correct any errors)
- Update metadata with latest date

# Validation
assert rows_loaded >= 365 * daily_avg
assert watermark_date == max(silver_df["date"])
```

### Data Quality Checks

**Post-Load Validation:**
```python
def validate_incremental_load(table_name, expected_min_rows=0):
    """Validate incremental load results"""

    # Check 1: No duplicate keys
    duplicates = spark.sql(f"""
        SELECT date_key, material_key, supplier_hq_country_key, COUNT(*) as cnt
        FROM {table_name}
        GROUP BY date_key, material_key, supplier_hq_country_key
        HAVING COUNT(*) > 1
    """)

    if duplicates.count() > 0:
        raise ValueError(f"Found {duplicates.count()} duplicate keys in {table_name}")

    # Check 2: Minimum row count
    total_rows = spark.table(table_name).count()
    if total_rows < expected_min_rows:
        raise ValueError(f"{table_name} has {total_rows} rows, expected >={expected_min_rows}")

    # Check 3: No null surrogate keys
    null_keys = spark.sql(f"""
        SELECT COUNT(*) as null_count
        FROM {table_name}
        WHERE date_key IS NULL OR material_key IS NULL
    """).collect()[0]["null_count"]

    if null_keys > 0:
        raise ValueError(f"Found {null_keys} null keys in {table_name}")

    print(f"✓ {table_name} validation passed ({total_rows:,} rows)")
```

---

## 8. Rollback & Recovery

### Rollback Strategy

**Delta Lake Time Travel:**
```sql
-- View table history
DESCRIBE HISTORY oem_lh.fact_procurement;

-- Rollback to version before bad load
RESTORE TABLE oem_lh.fact_procurement TO VERSION AS OF 10;

-- Rollback to timestamp
RESTORE TABLE oem_lh.fact_procurement TO TIMESTAMP AS OF '2024-11-02T06:00:00';
```

**Metadata Rollback:**
```python
# Reset watermark to previous date
spark.sql("""
    UPDATE oem_lh.bronze_load_metadata
    SET last_load_date = '2024-11-01',
        load_status = 'ROLLED_BACK'
    WHERE source_table = 'bronze_procurement_transactional'
      AND load_timestamp = (SELECT MAX(load_timestamp) FROM oem_lh.bronze_load_metadata)
""")
```

### Disaster Recovery

**Full Refresh After Corruption:**
```python
# 1. Drop corrupted silver/gold tables
spark.sql("DROP TABLE IF EXISTS oem_lh.silver_procurement")
spark.sql("DROP TABLE IF EXISTS oem_lh.fact_procurement")

# 2. Reset metadata
spark.sql("""
    DELETE FROM oem_lh.bronze_load_metadata
    WHERE source_table = 'bronze_procurement_transactional'
""")

# 3. Re-run with full load
p_full_load = True
load_all_layers()
```

---

## 9. Implementation Checklist

### Phase 1: Bronze Layer (0.5 days)
- [ ] Modify `bronze_azureSQLdb2table.Dataflow` to support `p_from_date` parameter
- [ ] Add SQL WHERE clause with date filter
- [ ] Test dataflow with parameter values
- [ ] Create `bronze_load_metadata` table
- [ ] Implement `get_last_load_date()` and `update_load_metadata()` functions

### Phase 2: Silver Layer (1 day)
- [ ] Update `bronze-to-silver.Notebook` with incremental logic
- [ ] Implement merge operation using Delta Lake MERGE
- [ ] Add deduplication logic
- [ ] Test with sample incremental data
- [ ] Validate merge behavior (UPDATE + INSERT)

### Phase 3: Gold Layer (1 day)
- [ ] Update `silver-to-gold2.Notebook` with incremental logic
- [ ] Implement fact table merge operations
- [ ] Implement SCD Type 1 for dimensions
- [ ] Test end-to-end incremental load
- [ ] Validate data quality post-merge

### Phase 4: Pipeline Integration (0.5 days)
- [ ] Wire `p_full_load` and `p_from_date` parameters to all activities
- [ ] Add conditional logic (IF full_load THEN... ELSE...)
- [ ] Test pipeline with both full and incremental modes
- [ ] Document parameter usage in pipeline README
- [ ] Create runbook for operators

### Phase 5: Validation & Performance (0.5 days)
- [ ] Run all test scenarios (4 scenarios above)
- [ ] Measure performance (full vs incremental)
- [ ] Implement data quality checks
- [ ] Create monitoring dashboard for load metrics
- [ ] Document rollback procedures

---

## 10. Future Enhancements

### Change Data Capture (CDC)

**Azure SQL CDC (Advanced):**
```sql
-- Enable CDC on source table
EXEC sys.sp_cdc_enable_table
    @source_schema = 'dbo',
    @source_name = 'Procurement',
    @role_name = 'cdc_admin';

-- Query CDC changes
SELECT *
FROM cdc.dbo_Procurement_CT
WHERE __$operation IN (2, 4)  -- Insert and Update
  AND __$start_lsn >= @last_lsn;
```

**Benefits:**
- Capture inserts, updates, deletes
- Reduce source system query load
- Near-real-time data freshness

### Incremental External Data

**EPI/WGI Incremental Load:**
```python
# Download only latest year
epi_2024 = download_epi_data(year=2024)
epi_2024["year"] = 2024

# Merge into historical table
target = DeltaTable.forName(spark, "bronze_epi_historical")
target.merge(epi_2024, "target.iso3 = source.iso3 AND target.year = source.year") \
      .whenMatchedUpdateAll() \
      .whenNotMatchedInsertAll() \
      .execute()
```

### Audit Trail

**Track all data changes:**
```python
# Add audit columns to all tables
df_with_audit = df.withColumn("created_timestamp", F.current_timestamp()) \
                  .withColumn("updated_timestamp", F.current_timestamp()) \
                  .withColumn("created_by", F.lit("pipeline_user"))

# On merge, update timestamp
.whenMatchedUpdate(set={
    "updated_timestamp": "current_timestamp()",
    "updated_by": "'pipeline_user'"
})
```

---

## 11. References

### Delta Lake Documentation
- **MERGE Syntax:** https://docs.delta.io/latest/delta-update.html#upsert-into-a-table-using-merge
- **Time Travel:** https://docs.delta.io/latest/delta-batch.html#read-older-versions-of-data-using-time-travel
- **Z-Ordering:** https://docs.delta.io/latest/optimizations-oss.html#z-ordering-multi-dimensional-clustering

### Microsoft Fabric Documentation
- **Dataflow Parameters:** https://learn.microsoft.com/fabric/data-factory/dataflow-gen2-parameters
- **Pipeline Parameters:** https://learn.microsoft.com/fabric/data-factory/parameters
- **Notebook Parameters:** https://learn.microsoft.com/fabric/data-engineering/author-execute-notebook#parameterized-cells

---

**Document Status:** Design complete and ready for implementation
**Next Task:** Task 11 (Error Handling Strategy Documentation)
