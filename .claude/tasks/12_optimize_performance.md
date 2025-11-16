# Task: Optimize Pipeline Performance

**Priority:** P3 (Infrastructure)
**Status:** Not Started
**Estimated Effort:** 2-4 days
**Owner:** TBD

## Problem Statement

Per project_definition.md lines 1262-1289:
> "**Pipeline Runtime:** **NEEDS DOCUMENTATION**
> - Bronze ingestion: X minutes
> - Silver transformation: X minutes
> - Gold transformation: X minutes
> - Total end-to-end: X minutes
>
> **Known Bottlenecks:** **NEEDS DOCUMENTATION**"

The pipeline is functional but not optimized for performance. Current optimization opportunities include:
- Partitioning strategy for large tables
- Predicate pushdown in transformations
- Incremental load (see Task 06)
- Caching strategies
- Warehouse indexing
- DirectLake optimization (V-Order columnar format)

## Current State

**What Exists:**
- ✅ Working pipeline with 4 sequential stages
- ✅ Parallel bronze ingestion (4 sources)
- ✅ Delta Lake format in lakehouse
- ✅ Some predicate pushdown (filters in silver-to-gold)
- ❌ No partitioning strategy
- ❌ No performance benchmarks
- ❌ No identified bottlenecks
- ❌ No V-Order optimization

**Current Runtime:** Unknown (needs measurement)

## Acceptance Criteria

### Must Have:

**1. Performance Baseline**
- Run pipeline end-to-end 3 times
- Measure duration of each stage and activity
- Document results in `/.claude/reference/performance_baseline.md`
- Identify slowest activities (bottlenecks)

**Expected Baseline Format:**
```markdown
## Performance Baseline (as of 2024-01-15)

| Stage | Activity | Duration | Rows Processed | Throughput |
|-------|----------|----------|----------------|------------|
| Bronze | bronzecopy_EUSupplyShares | 2m 34s | 5,432 | 35 rows/sec |
| Bronze | bronze_procurement | 8m 12s | 125,000 | 254 rows/sec |
| Bronze | bronze_WGI | 3m 45s | 8,500 | 38 rows/sec |
| Bronze | bronze_EPI | 4m 20s | 12,350 | 47 rows/sec |
| Silver | bronze-to-silver (Notebook) | 5m 48s | 151,282 | 434 rows/sec |
| Gold | silver-to-gold (Notebook) | 12m 35s | 875,345 | 1,159 rows/sec |
| Warehouse | Copy job1 | 3m 22s | 875,345 | 4,331 rows/sec |
| **TOTAL** | **End-to-End** | **25m 16s** | - | - |
```

**2. Implement Partitioning Strategy**

**Identify Partitioning Candidates:**
- `fact_procurement` - Partition by year/month (date_key)
- `fact_epi_score` - Partition by year
- `fact_supply_share` - Partition by year

**Implement Partitioning:**
```python
# In silver-to-gold2.Notebook

# Write fact_procurement with partitioning
fact_procurement.write \
    .format("delta") \
    .mode("overwrite") \
    .partitionBy("year", "month") \
    .option("overwriteSchema", "true") \
    .saveAsTable("oem_lh.fact_procurement")

# Note: Add year/month columns derived from date_key first
fact_procurement = fact_procurement \
    .withColumn("year", (col("date_key") / 10000).cast("int")) \
    .withColumn("month", ((col("date_key") % 10000) / 100).cast("int"))
```

**Benefits:**
- Query performance: Filter by year/month scans fewer files
- Maintenance: Easier to delete/update specific partitions
- Incremental loads: Append to specific partitions

**3. Enable V-Order Optimization**

V-Order is Fabric's optimized columnar format for DirectLake:
```python
# Enable V-Order on write
spark.conf.set("spark.sql.parquet.vorder.enabled", "true")
spark.conf.set("spark.microsoft.delta.optimizeWrite.enabled", "true")

# Rewrite existing tables with V-Order
for table in ["fact_procurement", "fact_epi_score", "fact_supply_share",
              "gold_dim_country", "gold_dim_material"]:
    spark.sql(f"OPTIMIZE oem_lh.{table} VORDER")
```

**4. Optimize Notebook Transformations**

**Bronze-to-Silver Optimization:**
```python
# Current: Read entire table
bronze_procurement = spark.read.table("oem_lh.bronze_procurement_transactional")

# Optimized: Use partition pruning if available
# Also: Cache intermediate results if reused
bronze_procurement = spark.read.table("oem_lh.bronze_procurement_transactional") \
    .filter("Date >= '2023-01-01'")  # If incremental load
    .cache()  # If used multiple times
```

**Silver-to-Gold Optimization:**
```python
# Current: May have multiple reads of same table
silver_procurement = spark.read.table("oem_lh.silver_procurement")

# Optimized: Broadcast small dimensions
gold_dim_material = spark.read.table("oem_lh.gold_dim_material").cache()
broadcast_material = broadcast(gold_dim_material)

fact_procurement = silver_procurement.join(
    broadcast_material,
    silver_procurement.materialname == broadcast_material.material_name_std
)
```

**5. Warehouse Indexing**

Create indexes in `oem_wh` warehouse for common query patterns:
```sql
-- Date dimension index (for time intelligence)
CREATE INDEX idx_date_key ON gold_dim_date(date_key);

-- Country dimension index (for geographic filters)
CREATE INDEX idx_country_key ON gold_dim_country(country_key);

-- Material dimension index (for commodity filters)
CREATE INDEX idx_material_key ON gold_dim_material(material_key);

-- Fact table foreign key indexes
CREATE INDEX idx_fact_procurement_date ON fact_procurement(date_key);
CREATE INDEX idx_fact_procurement_material ON fact_procurement(material_key);
CREATE INDEX idx_fact_procurement_country ON fact_procurement(supplier_hq_country_key);
```

**6. Performance Testing & Documentation**

After optimizations:
- Run pipeline 3 times with optimizations
- Compare to baseline (target: >30% improvement)
- Document results in `/.claude/reference/performance_optimized.md`
- Update project_definition.md with optimization notes

### Nice to Have:
- Adaptive query execution (AQE) in Spark
- Z-ordering on foreign keys in fact tables
- Materialized views for common aggregations
- Query result caching in warehouse
- Parallel execution of independent gold transformations

## Technical Approach

### Phase 1: Baseline Measurement (0.5 days)

**Measure Current Performance:**
1. Clear all lakehouse tables
2. Run pipeline with full load
3. Record start/end time for each activity
4. Check Fabric monitoring for detailed metrics
5. Document row counts and throughput
6. Identify top 3 slowest activities

**Tools:**
- Fabric pipeline monitoring page
- Spark UI for notebook execution details
- Lakehouse table properties for row counts

### Phase 2: Partitioning Implementation (1 day)

**Design Partitioning Strategy:**
```
fact_procurement:
  - Partition by: year, month (from date_key)
  - Rationale: Most queries filter by date range
  - Expected partition count: ~24 (2 years × 12 months)

fact_epi_score:
  - Partition by: year
  - Rationale: Annual snapshots
  - Expected partition count: 1 (2024 only currently)

fact_supply_share:
  - Partition by: year
  - Rationale: Annual snapshots
  - Expected partition count: 1 (2023 only currently)
```

**Implement:**
1. Modify `silver-to-gold2.Notebook` to add partition columns
2. Update write statements with `.partitionBy(...)`
3. Test with sample data
4. Rewrite existing tables with partitions

### Phase 3: V-Order & Optimization (1 day)

**Enable V-Order:**
1. Set Spark configuration in notebooks
2. Run OPTIMIZE command on all tables
3. Verify file format in lakehouse (should show V-Order)
4. Test query performance improvement

**Optimize Transformations:**
1. Add broadcast hints for small dimension tables
2. Enable caching for reused DataFrames
3. Push down filters where possible
4. Reduce shuffle operations (coalesce/repartition)

### Phase 4: Warehouse Indexing (0.5 days)

**Create Indexes:**
1. Connect to oem_wh via SQL endpoint
2. Run CREATE INDEX statements
3. Rebuild statistics: `UPDATE STATISTICS [table]`
4. Test query performance with EXPLAIN PLAN

### Phase 5: Testing & Validation (1 day)

**Retest Pipeline:**
1. Run optimized pipeline 3 times
2. Measure performance metrics
3. Compare to baseline
4. Validate correctness (row counts match)
5. Test Power BI report performance (query times)

**Performance Goals:**
- Bronze stage: <10 minutes (currently unknown)
- Silver stage: <5 minutes
- Gold stage: <10 minutes
- Total end-to-end: <20 minutes
- Power BI query response: <3 seconds

## Expected Performance Improvements

| Optimization | Expected Impact | Complexity |
|--------------|-----------------|------------|
| Partitioning | 20-40% faster queries | Medium |
| V-Order | 10-30% faster DirectLake queries | Low |
| Broadcast joins | 15-25% faster gold transformation | Low |
| Warehouse indexes | 30-50% faster BI queries | Low |
| Incremental load | 50-80% faster (see Task 06) | High |

**Total Expected Improvement:** 30-50% reduction in pipeline runtime

## Dependencies
- Baseline performance measurements (need to run pipeline)
- Delta Lake format (already in use)
- Fabric capacity sufficient for V-Order optimization
- SQL endpoint access for warehouse indexing
- No schema changes during optimization

## Success Metrics
- ✅ Performance baseline documented
- ✅ Partitioning implemented on 3 fact tables
- ✅ V-Order enabled on all gold tables
- ✅ Warehouse indexes created
- ✅ Performance improvement >30% vs baseline
- ✅ Power BI query times <3 seconds
- ✅ Documentation updated with optimization notes

## Related Files
- `/fabric/clean_columnsAndHeaders.Notebook/` - Silver transformations to optimize
- `/fabric/silver-to-gold2.Notebook/` - Gold transformations to optimize
- `/fabric/orchestrator_pipeline_bronze_to_gold.DataPipeline/` - Pipeline to benchmark
- To create: `/.claude/reference/performance_baseline.md` - Baseline measurements
- To create: `/.claude/reference/performance_optimized.md` - Post-optimization results
- `/project_definition.md` - Lines 1262-1289 (Performance section)

## Notes
- Measure before optimizing - avoid premature optimization
- Partitioning strategy depends on query patterns
- V-Order is specific to Microsoft Fabric (not standard Delta Lake)
- Indexing in warehouse helps BI queries but not lakehouse queries
- Balance optimization effort with actual performance gains
- Document trade-offs (e.g., partitioning adds complexity)
- For portfolio, demonstrate systematic performance optimization approach
