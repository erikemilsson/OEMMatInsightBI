# Incremental Load Strategy - OEMMatInsightBI

**Status:** Implemented — silver/gold load mechanics shipped (task-024); high-water-mark tracking (§ 4-5) shipped (task-029). Dataflow-side pushdown deferred (criterion 6, § 5).
**Last Updated:** 2026-08-04 (task-006_3: § 6 actual full-vs-incremental timings measured and recorded; corrected-date-space `p_from_date` gotcha documented). Previously 2026-07-28 (task-029: § 4-5 rewritten to match the shipped watermark system — `bronze_load_metadata` + `get_last_load_date` + `update_load_metadata` + auto-retrieve sentinel + gold coordination via `exclude_execution_id`)
**Owner:** Claude Code

## Executive Summary

This document defines the incremental load strategy for the OEMMatInsightBI data pipeline. It focuses on **procurement transactional data** for incremental loading while maintaining full refresh for reference and external data sources.

`p_full_load` and `p_from_date` are wired end to end and **the load logic exists** (task-024): both `bronze-to-silver` and `silver-to-gold2` branch on `p_full_load` and window on `p_from_date`. The *watermark source* landed in task-029: `bronze_load_metadata` records one row per pipeline run per tracked source, `get_last_load_date` auto-retrieves the last SUCCESSful run's max date, and `update_load_metadata` writes a SUCCESS or FAILED row after each procurement load. The effective watermark is resolved once per run and consumed by both silver and gold (one mechanism, one value per run — § 4-5).

**Key Decisions:**
- ✅ **Incremental:** Procurement transactional data (daily growth)
- ✅ **Full Refresh:** Reference tables, external ESG data (annual snapshots)
- ⚠️ **Merge Strategy:** ~~UPSERT using Delta Lake MERGE~~ → **delete-insert over the load
  window**, decided and implemented in task-024 (2026-07-14). The natural-key MERGE this
  document originally designed is *incorrect* for the transaction grain — see § 3 Silver
  and Gold layer strategies below.
- ✅ **High-Water Mark:** Metadata table tracks last successful load dates

**Expected Benefits:**
- **Performance:** 70-90% reduction in load time for incremental runs *(projected; the
  measured 2026-08-04 result is more modest — −9% total, concentrated in silver, gold
  full-scope-bound — see § 6)*
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
| **bronze_epi{year}results** | Bronze | N/A | 🔁 Full Refresh | Annual | Annual snapshot; a new vintage lands in its own table (`p_epi_year`) |
| **bronze_WGI** | Bronze | N/A | 🔁 Full Refresh | Annual | Annual snapshot, World Bank API provides the full dataset |
| **bronze_GlobalSupplyShares** | Bronze | N/A | 🔁 Full Refresh | Annual | Static material shares, rarely updated |
| **bronze_EUSupplyShares** | Bronze | N/A | 🔁 Full Refresh | Annual | EU-scope companion to the global shares; consumed by `bronze-to-silver` since task-038_1 |
| **silver_procurement** | Silver | `date` | 🔄 **Incremental** | Daily | Derived from bronze procurement (delete-insert) |
| **silver_epi{year}results** | Silver | N/A | 🔁 Full Refresh | Annual | Cleaned EPI data |
| **silver_wgi** | Silver | N/A | 🔁 Full Refresh | Annual | Cleaned WGI data (long format) |
| **silver_globalsupplyshares** | Silver | N/A | 🔁 Full Refresh | Annual | Cleaned global supply shares (`t` retained since task-038_1) |
| **silver_eusupplyshares** | Silver | N/A | 🔁 Full Refresh | Annual | Cleaned EU-sourcing shares; same column contract as the global table (task-038_1) |
| **fact_procurement** | Gold | `date_key` | 🔄 **Incremental** | Daily | Fact table with surrogate keys |
| **fact_epi_score** | Gold | `year` | 🔁 Full Refresh | Annual | Low volume, full refresh acceptable |
| **fact_supply_share** | Gold | N/A | 🔁 Full Refresh | Annual | Static shares, full refresh acceptable |
| **gold_dim_country** | Gold | N/A | 🔄 **SCD Type 1** | On change | Slowly changing dimension |
| **gold_dim_material** | Gold | N/A | 🔄 **SCD Type 1** | On change | Slowly changing dimension |
| **gold_dim_date** | Gold | N/A | 🔁 Append Only | Daily | Date dimension, append new dates |
| **gold_dim_indicator** | Gold | N/A | 🔁 Full Refresh | Annual | Static indicators |
| **gold_dim_stage** | Gold | N/A | 🔁 Full Refresh | Rarely | Static lifecycle stages |

### Load Strategy Summary

- **🔄 Incremental (3 tables):** procurement transactional data, `silver_procurement`,
  `fact_procurement`. All three use **delete-insert over the load window**, not MERGE.
- **🔁 Full Refresh (14 tables):** Reference data, external data, small dimensions
- **⚠️ SCD Type 1 rows are design-only.** `gold_dim_country` and `gold_dim_material` are
  written today by `write_tbl()` — a plain overwrite. No SCD merge is implemented.
- **Expected Time Savings:** Incremental run ~5 min vs Full load ~30 min (83% faster)
  *(projection; measured 2026-08-04 is −9% total — see § 6 for why the saving is modest)*.
  **Now realisable:** with high-water-mark tracking (§ 4, task-029 shipped), a second
  consecutive incremental run auto-retrieves the last SUCCESS watermark and reads only the
  7-day look-back window — the silver/gold delete-insert becomes truly incremental rather
  than rewriting the full history each run. Bronze extraction remains a full refresh
  (criterion 6 deferred — acceptable at demo volume).

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

These are **window keys**, not merge keys: they select which rows are read and which
rows are deleted before the window is re-appended. There is no natural or surrogate merge
key at either layer — see § 3.

---

## 3. Load Strategies by Layer

### Bronze Layer Strategy

#### Procurement (Incremental)

**Current Behavior:**
```powerquery
// HISTORICAL — bronze_azureSQLdb2table.Dataflow, retired 2026-07-31
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

#### Procurement (Incremental — delete-insert, IMPLEMENTED)

> **This section was rewritten 2026-07-26 (task-033) to match what task-024 shipped.**
> The natural-key MERGE originally designed below is preserved after the implemented
> version as a *rejected design*, because the reason it was rejected is the load-bearing
> part.

**Implemented behavior** — `bronze-to-silver.Notebook`, cell "Write silver_procurement":

```python
# is_full_load / the 7-day look-back window are derived earlier in the notebook.
if is_full_load:
    silver_df.write.format("delta").mode("overwrite").saveAsTable("silver_procurement")
elif not spark.catalog.tableExists("oem_lh.silver_procurement"):
    # First load — create the table via overwrite
    silver_df.write.format("delta").mode("overwrite").saveAsTable("silver_procurement")
else:
    # Delete-insert over the look-back window.
    # Boundary = the MINIMUM date actually present in this run's window, NOT p_from_date.
    window_min_date = silver_df.agg(F.min("date")).first()[0]
    if window_min_date is not None:
        target_table = DeltaTable.forName(spark, "oem_lh.silver_procurement")
        target_table.delete(F.col("date") >= F.lit(window_min_date))
        silver_df.write.format("delta").mode("append").saveAsTable("silver_procurement")
```

**Why the boundary is the window's minimum date, not `p_from_date`:** `silver_df` was read
with a 7-day look-back, so it contains every bronze row at or after the look-back date.
Deleting only `>= p_from_date` would leave the `[look-back, p_from_date)` rows in place and
then re-append them — duplicating exactly that range. Deleting from the window minimum
replaces the window exactly: lossless in, lossless out, and re-running is idempotent.

**No deduplication is applied.** This is deliberate and is the opposite of the "Deduplication
Strategy" the rejected design prescribes below.

##### Rejected design: natural-key MERGE

**Why it was rejected (task-024, 2026-07-14).** Bronze grain is *one row per material
purchase*. Two same-day purchases of the same material from the same supplier are
**legitimately distinct transactions**, but they share the natural key
`(date, materialname, suppliername, region)`. The MERGE therefore collapsed them:

| Case | MERGE outcome |
|---|---|
| Both duplicates in the same batch | Delta raises *"multiple source rows matched"* — the run **crashes** |
| Duplicates across runs | `whenMatchedUpdateAll` silently overwrites the earlier one — **data loss** |

The dedupe step below "fixes" the crash by *causing* the data loss deliberately, so it was
rejected with the MERGE. `region` was additionally dropped from the silver layer entirely
(`silver_df = df_joined.drop("region")`), so a merge key naming it could not have been
built as written.

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

**Deduplication Strategy (NOT IMPLEMENTED — do not apply):**

⚠️ The block below silently drops legitimate duplicate transactions. It exists only to
make the rejected MERGE survive its own key collision. The shipped pipeline keeps every
transaction.

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

**Implementation status:** only `fact_procurement` is incremental, and it uses
delete-insert (below). Every other gold table — the three facts' siblings, all
dimensions, the lookups and the audit tables — is written by `write_tbl()`, which is a
plain **`mode("overwrite")` with `overwriteSchema`**. The SCD Type 1 MERGE design in
"Dimension Tables" further down is a design sketch, not shipped code.

#### fact_procurement (Incremental — delete-insert, IMPLEMENTED)

**Implemented behavior** — `silver-to-gold2.Notebook`, cell "gold.fact_procurement":

```python
_is_full_load = p_full_load.strip().lower() == "true"
_fact_exists = spark.catalog.tableExists(f"{DB}.fact_procurement")

# Read window: mirror bronze-to-silver's 7-day look-back, or the whole table on a
# full/first load.
if _is_full_load or not _fact_exists:
    proc = spark.table(f"{DB}.silver_procurement")
else:
    _lookback_str = (datetime.strptime(p_from_date, "%Y-%m-%d")
                     - timedelta(days=7)).strftime("%Y-%m-%d")
    proc = (spark.table(f"{DB}.silver_procurement")
            .filter(F.col("date").cast("date") >= F.lit(_lookback_str)))

# ... dimension joins, quality scoring ...

# Write
if _is_full_load or not _fact_exists:
    write_tbl(fact_procurement_complete, "fact_procurement")     # overwrite
else:
    # Boundary = min date_key in the window, EXCLUDING the UNKNOWN-DATE member.
    window_min_date_key = (fact_procurement_complete
        .filter(F.col("date_key") != F.lit(UNKNOWN_DATE_KEY))
        .agg(F.min("date_key")).first()[0])
    if window_min_date_key is not None:
        target = DeltaTable.forName(spark, f"{DB}.fact_procurement")
        target.delete(F.col("date_key") >= F.lit(window_min_date_key))
        (fact_procurement_complete.write.format("delta").mode("append")
            .saveAsTable(f"{DB}.fact_procurement"))
        spark.sql(f"OPTIMIZE {DB}.fact_procurement")
```

**Delete-insert boundary:** `MIN(date_key)` over the windowed fact — the gold analogue of
the silver rule above, and lossless for the same reason.

**The UNKNOWN-DATE member must be excluded from the boundary** (task-030). Undated
transactions carry `date_key = 19000101`, which is below every real `date_key`. If one
reached the boundary computation, the delete would collapse to `date_key >= 19000101` and
**wipe the entire fact table** before re-inserting only the window. The incremental read
filter already drops undated rows, so the exclusion is belt-and-braces — and it keeps the
code correct if that filter ever changes. Undated rows written by a full load sit below
the boundary and are therefore preserved by subsequent incremental runs.

**Grain is unchanged:** one row per transaction, no aggregation, no dedupe.

##### Rejected design: surrogate-key MERGE

**Why it was rejected (task-024).** The proposed key
`(date_key, material_key, supplier_hq_country_key)` — later
`(…, production_country_key)` — is **coarser than the transaction grain**, so it fails the
same way the silver MERGE did: same-batch duplicates crash on Delta's *"multiple source
rows matched"*, cross-run duplicates are silently overwritten. The "use aggregation"
escape hatch at the end of this block changes the fact's grain from *transaction* to
*day × material × supplier*, which contradicts the grain declared in `schemas/gold_tables.md`.

⚠️ The sketch below also carries `spend_eur = quantity_base × unitprice_eur`. That formula
was **removed in task-030**: `quantity_base` is NULL for non-mass units, so it collapsed
every `pcs` row's spend to NULL. The shipped formula is `quantity_original × unitprice_eur`
— see `calculations.md § Spend EUR`.

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

#### Dimension Tables (SCD Type 1) — DESIGN SKETCH, NOT IMPLEMENTED

⚠️ Nothing below is shipped. `gold_dim_country` and `gold_dim_material` are written by
`write_tbl()` (plain `mode("overwrite")` + `overwriteSchema`) on every gold run. The
sketch also reads a table named `silver_supplier`, which does not exist — supplier
attributes are joined into `silver_procurement` at the silver layer, and the dimension is
actually sourced from the EPI silver table plus a curated missing-countries list. Treat
this section as a future design, not as documentation of current behavior.

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
    StructField("last_load_date", DateType(), False),       # Max date loaded (watermark)
    StructField("load_timestamp", TimestampType(), False),  # When this row was written
    StructField("rows_loaded", LongType(), True),           # Count of rows in this load (NULL on FAILED)
    StructField("load_status", StringType(), False),        # SUCCESS, FAILED, IN_PROGRESS
    StructField("execution_id", StringType(), True)          # Pipeline run id (for gold coordination)
])
```

The table is created idempotently (`CREATE TABLE IF NOT EXISTS ... USING DELTA`) on the
first `update_load_metadata` call — no separate initialization step is needed. The first
SUCCESS row advances the watermark from the implicit default (1900-01-01, returned when
no prior SUCCESS row exists) to whatever max date the first run loaded.

### Source-table naming convention

One `source_table` key per tracked source. The procurement pipeline uses a single key,
`"bronze_procurement_transactional"`, shared by both the silver and gold layers — that
gives ONE watermark mechanism and ONE effective watermark value per run, consumed
identically by `bronze-to-silver` (which writes the metadata row) and `silver-to-gold2`
(which reads it). There is no second watermark for gold.

### Effective-watermark precedence (criterion 3)

The notebook resolves the effective watermark once, early in the run, and uses it for the
look-back window. Precedence (with the sentinel convention documented inline):

```
1. p_full_load == "true"          -> "1900-01-01"  (full load; load from epoch)
2. p_from_date  != "1900-01-01"   -> p_from_date   (explicit manual override)
3. last SUCCESS row exists        -> that row's last_load_date (auto-retrieve)
4. otherwise                      -> "1900-01-01"  (no prior SUCCESS; load from epoch)
```

The default `p_from_date == "1900-01-01"` is the "not explicitly set" sentinel. `p_full_load=true`
is the explicit "load from epoch" path, so a caller that wants a full refresh sets `p_full_load`
rather than relying on the default. This avoids a three-way ambiguity between "default",
"explicit full", and "explicit override".

```python
def resolve_effective_watermark(p_full_load, p_from_date, last_load_date):
    if (p_full_load or "").strip().lower() == "true":
        return "1900-01-01"
    override = (p_from_date or "").strip()
    if override and override != "1900-01-01":
        return override
    if last_load_date is not None:
        return last_load_date.strftime("%Y-%m-%d")
    return "1900-01-01"
```

### Read: get_last_load_date

```python
def get_last_load_date(metadata_df, source_table, exclude_execution_id=None):
    """Return the last SUCCESSful load's last_load_date for source_table, or None.

    exclude_execution_id: if non-empty, rows with this execution_id are excluded.
        silver-to-gold2 passes the current run's execution_id so it reads the
        PREVIOUS run's watermark (bronze-to-silver has already written its SUCCESS
        row by the time gold starts), keeping both layers on the same effective
        watermark for a given run.
    """
    q = (metadata_df
         .filter(F.col("source_table") == source_table)
         .filter(F.col("load_status") == "SUCCESS"))
    if exclude_execution_id:
        q = q.filter(F.col("execution_id") != F.lit(exclude_execution_id))
    row = (q.orderBy(F.col("load_timestamp").desc())
            .limit(1)
            .select("last_load_date")
            .collect())
    if not row:
        return None
    ld = row[0]["last_load_date"]
    return ld.date() if isinstance(ld, datetime) else ld
```

### Write: update_load_metadata

```python
def update_load_metadata(source_table, last_load_date, rows_loaded, status,
                          execution_id=None, now=None):
    """Append one metadata row to bronze_load_metadata (creates the table on first call)."""
    row = metadata_row(source_table, last_load_date, rows_loaded, status,
                       execution_id=execution_id, now=now)
    df = spark.createDataFrame([row], schema=metadata_schema)
    try:
        spark.sql(f"CREATE TABLE IF NOT EXISTS oem_lh.bronze_load_metadata "
                  f"USING DELTA AS SELECT * FROM df")
    except Exception:
        pass  # table already exists (normal case after first run)
    df.write.format("delta").mode("append").saveAsTable("oem_lh.bronze_load_metadata")
```

### Usage pattern (bronze-to-silver)

```python
# Resolve the effective watermark for THIS run (auto-retrieve if p_from_date is the sentinel)
_metadata_df = (spark.table("oem_lh.bronze_load_metadata")
                if spark.catalog.tableExists("oem_lh.bronze_load_metadata") else None)
_last_load_date = (get_last_load_date(_metadata_df, "bronze_procurement_transactional")
                  if _metadata_df is not None else None)
effective_from_date = resolve_effective_watermark(p_full_load, p_from_date, _last_load_date)

# Use effective_from_date for the 7-day look-back window ...
try:
    # ... perform the silver write (full overwrite or delete-insert over the window) ...
    max_date_loaded = silver_df.agg(F.max("date")).first()[0]
    rows_loaded = silver_df.count()
    update_load_metadata("bronze_procurement_transactional", max_date_loaded, rows_loaded,
                         status="SUCCESS", execution_id=p_execution_id)
except Exception as e:
    # FAILED row records the watermark that was attempted (does NOT advance — the
    # next run re-reads from the same previous watermark).
    update_load_metadata("bronze_procurement_transactional", effective_from_date, 0,
                         status="FAILED", execution_id=p_execution_id)
    raise
```

### Gold coordination (criterion 4)

`silver-to-gold2` runs AFTER `bronze-to-silver` in the pipeline, so bronze-to-silver's
SUCCESS row for the current run is already in the table when gold starts. To use the SAME
effective watermark silver used (the PREVIOUS run's watermark), gold passes its own
`p_execution_id` to `get_last_load_date` as `exclude_execution_id`:

```python
# silver-to-gold2: same mechanism, same source_table key, exclude the current run
_metadata_df = (spark.table("oem_lh.bronze_load_metadata")
                if spark.catalog.tableExists("oem_lh.bronze_load_metadata") else None)
_last_load_date = (get_last_load_date(_metadata_df, "bronze_procurement_transactional",
                                       exclude_execution_id=p_execution_id)
                   if _metadata_df is not None else None)
effective_from_date = resolve_effective_watermark(p_full_load, p_from_date, _last_load_date)
# ... use effective_from_date for the gold-side 7-day look-back window ...
```

One watermark mechanism (`bronze_load_metadata`), one `source_table` key, one effective
watermark value per run — consumed by both layers. No second mechanism.

### Error handling

```python
try:
    # Perform incremental load (delete-insert over the look-back window)
    load_procurement_incremental(effective_from_date)
    update_load_metadata("bronze_procurement_transactional", max_date_loaded, rows, "SUCCESS")
except Exception as e:
    update_load_metadata("bronze_procurement_transactional", effective_from_date, 0, "FAILED")
    raise e
```

The FAILED row's `last_load_date` records the watermark that was *attempted*, not a new
max date (there is no new max — the load failed). The next run's `get_last_load_date`
filters to `load_status = 'SUCCESS'`, so the FAILED row is skipped and the watermark stays
at the previous SUCCESS value — the next run re-processes from the same window, which is
correct (the failed run loaded nothing).

---

## 5. Pipeline Parameter Wiring

### Pipeline Parameters

**Existing Parameters (orchestrator_pipeline_bronze_to_gold):**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `p_full_load` | Boolean | `false` | If true, perform full refresh instead of incremental |
| `p_from_date` | String | `"1900-01-01"` | Watermark date for incremental loads (YYYY-MM-DD). The sentinel `"1900-01-01"` means "not explicitly set — auto-retrieve from `bronze_load_metadata`". |
| `p_execution_id` | String | `""` | Pipeline run identifier (task-029). The pipeline sets this to `@pipeline().RunId`; gold passes it to `get_last_load_date(exclude_execution_id=...)` so it reads the previous run's watermark. Empty for manual notebook runs — the exclude filter is then a no-op. |

### Parameter Flow

```
Pipeline Parameters
  ├─ p_full_load  → Notebook activities (via widget)
  ├─ p_from_date  → Notebook activities (via widget)
  │                   └─ Notebook resolves effective watermark:
  │                       full_load -> "1900-01-01"
  │                       p_from_date != "1900-01-01" -> p_from_date (explicit override)
  │                       else -> get_last_load_date("bronze_procurement_transactional")
  │                   └─ 7-day look-back window applied to the silver + gold reads
  │
  └─ p_execution_id → Notebook activities (via widget)
                       └─ bronze-to-silver: stamps the SUCCESS/FAILED metadata row
                       └─ silver-to-gold2: excludes the current run's row so it
                          reads the PREVIOUS run's watermark (gold coordination)
```

### Bronze dataflows — full refresh (criterion 6, deferred)

Historically the bronze Power Query dataflows (`bronze_procurement`, `bronze_WGI`, `bronze_EPI`) took
**no parameters** and run as full refresh on every pipeline run. The watermark gates the
silver/gold MERGE window, **not** the bronze extract.

**Decision (task-029, 2026-07-28):** dataflow-side pushdown of `p_from_date` into the
bronze Power Query dataflows is **deferred**. At demo volume the bronze tables are small
enough that full-refresh extraction is acceptable. **Superseded 2026-07-31 (task-048):**
that dataflow is now retired and procurement ingestion is two Copy activities, which are
plain full-table copies with no source query — so bronze-side pushdown is no longer merely
deferred, it is designed out. Note the dataflow's look-back was always dead code anyway:
the pipeline never passed `p_from_date` to the RefreshDataflow activity, so the branch
guarded by `if p_from_date = "1900-01-01"` always took the full-table path. The honest trade-off: incremental *efficiency* is realised at the silver/gold
layers (the delete-insert window); bronze remains a full extract.

The earlier version of this section claimed bronze dataflows received `p_from_date` and
filtered at source — that was an overclaim. The § 1 Bronze Layer Strategy "Target Behavior"
Power Query sketch (SQL pushdown with `WHERE Date >= ...`) remains a valid future
enhancement but is **not** the live behavior.

### Notebook Parameter Passing

**In Pipeline Activity (bronze-to-silver):**
```json
{
  "name": "bronze-to-silver data cleaning",
  "type": "TridentNotebook",
  "typeProperties": {
    "notebook": "bronze-to-silver",
    "parameters": {
      "p_full_load":   { "value": "@string(pipeline().parameters.p_full_load)", "type": "Expression" },
      "p_from_date":   { "value": "@pipeline().parameters.p_from_date",         "type": "Expression" },
      "p_epi_year":     { "value": "@pipeline().parameters.p_epi_year",           "type": "string" },
      "p_execution_id": { "value": "@pipeline().RunId",                           "type": "string" }
    }
  }
}
```

**In Notebook (bronze-to-silver.Notebook) — parameters cell:**
```python
p_full_load = "false"          # overridden by pipeline
p_from_date = "1900-01-01"     # sentinel: "not set" -> auto-retrieve
p_epi_year  = "2024"
p_execution_id = ""            # overridden by pipeline (@pipeline().RunId)
```

**In Notebook (bronze-to-silver.Notebook) — watermark resolution:**
```python
# Resolve effective watermark once, early in the run
_metadata_df = (spark.table("oem_lh.bronze_load_metadata")
                if spark.catalog.tableExists("oem_lh.bronze_load_metadata") else None)
_last_load_date = (get_last_load_date(_metadata_df, "bronze_procurement_transactional")
                  if _metadata_df is not None else None)
effective_from_date = resolve_effective_watermark(p_full_load, p_from_date, _last_load_date)
# ... 7-day look-back window keys off effective_from_date, not the raw p_from_date ...
```

`silver-to-gold2.Notebook` resolves its effective watermark the same way, passing
`exclude_execution_id=p_execution_id` so it reads the previous run's watermark.

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

**Actual Performance — measured 2026-08-04 (task-006_3, full vs incremental run)**

The projected table above assumed 100k rows/year (≈275/day) and a 500k-row history. The
demo dataset is far smaller — **132 procurement rows** spanning 2024-02-28 → 2024-12-31
(corrected-date space; see "p_from_date is in corrected-date space" below). Measured
full-vs-incremental stage wall-clock (parallel bronze = slowest activity; one full load
vs one incremental with a 22-row window, `p_from_date=2024-12-01`):

| Stage | Full load (132 rows) | Incremental (22-row window) | Δ | Interpretation |
|-------|----------------------|------------------------------|---|-----------------|
| Bronze (parallel) | 4m 46s | 1m 42s | −3m 04s (−64%) | **warm-cache artifact, not incremental** — bronze is always a full load (the 6 Copy activities copy the same source regardless of `p_full_load`); the full load ran first from a cold Spark pool, the incremental reused a warm pool |
| Silver | 4m 08s | 3m 37s | −0m 31s (−12%) | the procurement delete-insert path is a small fraction of silver runtime (supplier_ref join + notebook overhead dominate) |
| Gold | 9m 40s | 11m 08s | +1m 28s (+15%) | **gold is full-scope-bound** — `fact_supply_share` (rollup + territory merge over 3,468 records), the dimensions, and the quality metrics process the full dataset regardless of `p_from_date`; the 22-row procurement window is a negligible fraction, so incremental procurement loads cannot speed up gold |
| DQ | 3m 51s | 3m 52s | +0m 01s | flat |
| **Data wall-clock** | **22m 25s** | **20m 19s** | **−2m 06s (−9%)** | |

**Honest read (task-006_3 AC4):** the incremental saving is **modest and concentrated
in silver**, not the 94% across-the-board win the projection implied. Two findings:

1. **Bronze shows no incremental saving.** Bronze is a full extract by design (task-048
   retired the parameterized dataflow; the replacement Copy activities take no source
   query). The measured −64% is a **warm-pool artifact** — cold full load vs warm
   incremental. This is the bronze-no-saving case the task anticipated; the measured
   delta is environmental, not incremental.
2. **Gold shows no saving (slightly slower).** Only `fact_procurement` is incremental in
   the gold notebook; everything else gold does (`fact_supply_share` rollup, dimensions,
   quality metrics) is full-scope on every run and dominates gold runtime. Incremental
   procurement loads therefore cannot shrink gold. The architectural implication:
   **incrementality at gold would require windowing `fact_supply_share` too**, which is
   not currently done.

**Warm-cache-isolated signal.** A second incremental run with an *empty* procurement
window (both runs warm, only the window differs) measured silver 2m 35s (0 rows) vs
3m 37s (22 rows) and gold 10m 38s vs 11m 08s — i.e. the 22-row delete-insert itself
costs **~1m 02s in silver and ~30s in gold**, confirming the window-dependent cost is
small and gold is full-scope-bound (not window-bound).

**Correctness (task-006_3 AC1–3):** the 22-row delete-insert was idempotent —
`bronze == silver == fact == 132` held before and after (delete-insert deletes the
window and re-inserts the same rows; net zero), and the content-hash duplicate check
showed `rows == distinct_content` on both silver and fact → no duplicates introduced.
`p_full_load=false` reached both notebooks (task-039 AC4 runtime proof — both took the
INCREMENTAL branch, not the full-overwrite branch).

**`p_from_date` is in corrected-date space.** The raw
`bronze_procurement_transactional.Date` column is day/year-transposed with a ±2000 epoch
(task-048 `correct_procurement_date`). The SQL-endpoint values you see
(e.g. `2028-02-24 … 2031-12-24`) are **transposed**; `bronze-to-silver` applies the
correction *before* the window filter, so the window and the watermark are in
**corrected (actual) date space** (`2024-02-28 … 2024-12-31`). **Specify `p_from_date`
in corrected space** — a value derived from the raw column (e.g. `2031-12-24`) is in the
wrong calendar and yields an empty window. The watermark
(`bronze_load_metadata.last_load_date`) is likewise stored in corrected space, so the
auto-retrieve path is already correct; only explicit manual `p_from_date` overrides are
at risk of this footgun.

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
- [x] ~~Modify `bronze_azureSQLdb2table.Dataflow` to support `p_from_date` parameter~~ —
      **obsolete 2026-07-31:** the dataflow is retired (task-048). Bronze is a full load by
      design; incrementality lives in the silver delete-insert window.
- [x] ~~Add SQL WHERE clause with date filter~~ — obsolete, same reason
- [x] ~~Test dataflow with parameter values~~ — obsolete, same reason
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
- [x] Measure performance (full vs incremental) — **measured 2026-08-04 (task-006_3); see § 6**
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
