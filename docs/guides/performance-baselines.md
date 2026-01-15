# Performance Baselines & Monitoring Guide

## Executive Summary

This document establishes performance baselines for the OEMMatInsightBI data pipeline and provides monitoring guidelines to ensure optimal performance and early detection of issues.

---

## 📊 Current Performance Baselines

### Pipeline Execution Times

| Component | Typical Duration | Max Acceptable | Data Volume | Last Measured |
|-----------|-----------------|----------------|-------------|---------------|
| **Bronze Layer** |
| Azure SQL Ingestion | 2-3 min | 5 min | ~50K rows | 2025-11-16 |
| EPI File Import | 30-45 sec | 2 min | 195 countries | 2025-11-16 |
| WGI File Import | 30-45 sec | 2 min | 200 countries | 2025-11-16 |
| **Silver Layer** |
| Column Cleaning | 3-4 min | 7 min | ~50K rows | 2025-11-16 |
| Data Quality Checks | 1-2 min | 3 min | All tables | 2025-11-16 |
| Alias Resolution | 30 sec | 1 min | ~1K unique values | 2025-11-16 |
| **Gold Layer** |
| Dimension Creation | 2-3 min | 5 min | 5 dimensions | 2025-11-16 |
| Fact Table Creation | 3-5 min | 10 min | 3 fact tables | 2025-11-16 |
| Key Generation | 1-2 min | 3 min | ~50K keys | 2025-11-16 |
| **Warehouse Load** |
| MERGE Operations | 2-3 min | 5 min | ~50K rows | 2025-11-16 |
| **End-to-End** |
| Full Pipeline | 15-20 min | 30 min | All data | 2025-11-16 |
| Incremental Load | 5-8 min | 15 min | Delta only | 2025-11-16 |

### Data Volume Metrics

| Table | Current Rows | Growth Rate | Storage Size | Compression |
|-------|-------------|-------------|--------------|-------------|
| **Bronze Layer** |
| bronze_procurement | 45,000 | +500/day | 12 MB | 3:1 |
| bronze_suppliers | 500 | +2/week | 150 KB | 2:1 |
| bronze_materials | 1,000 | +10/month | 300 KB | 2:1 |
| bronze_epi_scores | 195 | Yearly update | 50 KB | 2:1 |
| bronze_wgi_indicators | 200 | Yearly update | 60 KB | 2:1 |
| **Gold Layer** |
| fact_transactions | 45,000 | +500/day | 15 MB | 3:1 |
| fact_supply_share | 5,000 | +50/month | 1.5 MB | 2:1 |
| fact_sustainability | 400 | Yearly update | 120 KB | 2:1 |
| dim_country | 200 | Static | 60 KB | 2:1 |
| dim_material | 1,000 | +10/month | 300 KB | 2:1 |
| dim_supplier | 500 | +2/week | 150 KB | 2:1 |
| dim_date | 730 | +1/day | 220 KB | 2:1 |
| dim_product | 100 | +1/month | 30 KB | 2:1 |

---

## 🎯 Performance Targets

### Response Time SLAs

| Operation | Target | Maximum | Priority |
|-----------|--------|---------|----------|
| Power BI Report Load | < 3 sec | 5 sec | P1 |
| Dashboard Refresh | < 10 sec | 15 sec | P1 |
| Drill-through Actions | < 2 sec | 3 sec | P2 |
| Export to Excel | < 30 sec | 60 sec | P3 |

### Pipeline SLAs

| Pipeline Type | Frequency | Start Time | Must Complete By |
|--------------|-----------|------------|------------------|
| Full Load | Weekly (Sunday) | 02:00 UTC | 04:00 UTC |
| Incremental | Daily | 06:00 UTC | 06:30 UTC |
| Quick Refresh | Hourly | :00 | :10 |

---

## 📈 Performance Monitoring

### Key Performance Indicators (KPIs)

```python
# Add to monitoring notebook
def calculate_pipeline_kpis(run_history_df):
    """Calculate pipeline performance KPIs"""

    kpis = {
        'avg_duration_min': run_history_df['duration_min'].mean(),
        'p95_duration_min': run_history_df['duration_min'].quantile(0.95),
        'success_rate': (run_history_df['status'] == 'Success').mean() * 100,
        'avg_rows_per_sec': run_history_df['rows_processed'] / run_history_df['duration_sec'],
        'data_freshness_hours': (datetime.now() - run_history_df['last_update'].max()).total_seconds() / 3600
    }

    return kpis
```

### Monitoring Queries

#### 1. Pipeline Duration Trend
```sql
-- Track pipeline execution time over last 30 days
SELECT
    DATE(run_timestamp) as run_date,
    pipeline_name,
    AVG(duration_minutes) as avg_duration,
    MAX(duration_minutes) as max_duration,
    COUNT(*) as run_count
FROM pipeline_runs
WHERE run_timestamp >= DATEADD(day, -30, GETDATE())
GROUP BY DATE(run_timestamp), pipeline_name
ORDER BY run_date DESC;
```

#### 2. Data Quality Metrics
```sql
-- Monitor data quality scores
SELECT
    check_date,
    table_name,
    quality_dimension,
    score,
    CASE
        WHEN score >= 95 THEN 'Excellent'
        WHEN score >= 90 THEN 'Good'
        WHEN score >= 80 THEN 'Acceptable'
        ELSE 'Needs Attention'
    END as quality_status
FROM data_quality_scores
WHERE check_date >= DATEADD(day, -7, GETDATE())
ORDER BY check_date DESC, table_name;
```

#### 3. Resource Utilization
```sql
-- Check warehouse resource usage
SELECT
    snapshot_time,
    used_storage_gb,
    max_storage_gb,
    (used_storage_gb / max_storage_gb * 100) as storage_percent,
    active_queries,
    queued_queries,
    cpu_percent,
    memory_percent
FROM sys.dm_resource_stats
WHERE snapshot_time >= DATEADD(hour, -24, GETDATE())
ORDER BY snapshot_time DESC;
```

---

## 🚨 Performance Alerts

### Alert Thresholds

| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| Pipeline Duration | > 25 min | > 30 min | Check for blocking queries |
| Success Rate | < 95% | < 90% | Review error logs |
| Data Freshness | > 2 hours | > 4 hours | Trigger manual refresh |
| Storage Usage | > 80% | > 90% | Archive old data |
| Query Queue | > 5 | > 10 | Scale up compute |
| CPU Usage | > 80% | > 95% | Optimize queries |

### Alert Configuration

```python
# Example alert configuration for Azure Monitor
alert_rules = [
    {
        'name': 'Pipeline Duration Alert',
        'metric': 'pipeline_duration_minutes',
        'threshold': 30,
        'operator': 'GreaterThan',
        'severity': 'Critical',
        'action_group': 'DataEngineering-Team'
    },
    {
        'name': 'Data Quality Alert',
        'metric': 'quality_score',
        'threshold': 80,
        'operator': 'LessThan',
        'severity': 'Warning',
        'action_group': 'DataQuality-Team'
    }
]
```

---

## 🔧 Performance Optimization Techniques

### 1. Query Optimization

**Current Optimizations:**
- ✅ Clustered columnstore indexes on fact tables
- ✅ Statistics updated after each load
- ✅ Appropriate distribution keys (hash on transaction_key)

**Recommended Improvements:**
```sql
-- Add filtered indexes for common queries
CREATE INDEX idx_transactions_date_filtered
ON fact_transactions(date_key)
WHERE order_type = 'Purchase'
WITH (ONLINE = ON);

-- Materialized views for complex aggregations
CREATE MATERIALIZED VIEW mv_monthly_spend AS
SELECT
    date_key,
    supplier_key,
    SUM(total_price) as monthly_spend,
    COUNT(*) as transaction_count
FROM fact_transactions
GROUP BY date_key, supplier_key;
```

### 2. Pipeline Optimization

**Parallel Processing:**
```python
# Current: Sequential processing
for table in tables:
    process_table(table)

# Optimized: Parallel processing
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=4) as executor:
    executor.map(process_table, tables)
```

**Incremental Load Pattern:**
```python
# Efficient incremental load with watermark
def incremental_load(table_name, watermark_column, last_watermark):
    query = f"""
    SELECT * FROM {table_name}
    WHERE {watermark_column} > '{last_watermark}'
    AND {watermark_column} <= GETDATE()
    """
    return spark.sql(query)
```

### 3. Data Optimization

**Partitioning Strategy:**
```python
# Partition by date for time-series data
df.write.partitionBy("year", "month") \
    .mode("overwrite") \
    .format("delta") \
    .save(f"{gold_path}/fact_transactions")
```

**V-Order Optimization:**
```sql
-- Enable V-Order for better compression
ALTER TABLE fact_transactions
REBUILD WITH (VORDER = ON);
```

---

## 📉 Performance Degradation Playbook

### Step 1: Identify the Bottleneck

```python
# Performance diagnosis query
SELECT
    step_name,
    start_time,
    end_time,
    DATEDIFF(second, start_time, end_time) as duration_sec,
    rows_processed,
    rows_processed / NULLIF(DATEDIFF(second, start_time, end_time), 0) as rows_per_sec
FROM pipeline_execution_log
WHERE pipeline_run_id = (SELECT MAX(pipeline_run_id) FROM pipeline_runs)
ORDER BY start_time;
```

### Step 2: Common Issues & Solutions

| Symptom | Likely Cause | Solution |
|---------|-------------|----------|
| Slow Bronze ingestion | Network latency | Check connection, use batch size tuning |
| Silver transformation timeout | Data skew | Add repartitioning, check for nulls |
| Gold layer slow | Complex joins | Optimize join order, add broadcast hints |
| Warehouse MERGE slow | Missing statistics | Update statistics, rebuild indexes |
| Report slow | Too many visuals | Reduce visual count, use aggregations |

### Step 3: Emergency Response

```bash
# Quick fixes for common issues

# 1. Kill blocking queries
KILL {session_id};

# 2. Clear query cache
DBCC DROPCLEANBUFFERS;

# 3. Update statistics
UPDATE STATISTICS fact_transactions WITH FULLSCAN;

# 4. Rebuild indexes
ALTER INDEX ALL ON fact_transactions REBUILD;
```

---

## 📅 Performance Review Schedule

### Daily Checks (Automated)
- Pipeline completion status
- Data quality scores
- Query performance metrics
- Storage utilization

### Weekly Review (Manual)
- Performance trend analysis
- Slow query identification
- Optimization opportunities
- Capacity planning

### Monthly Deep Dive
- End-to-end performance testing
- Benchmark comparison
- Architecture review
- Cost optimization

---

## 🎯 Performance Improvement Roadmap

### Short-term (Next Sprint)
1. ✅ Establish baselines (Complete)
2. 🚧 Implement monitoring queries
3. 📋 Add performance logging to notebooks
4. 📋 Create automated alert rules

### Medium-term (Next Quarter)
1. 📋 Implement partitioning strategy
2. 📋 Add materialized views
3. 📋 Optimize DAX measures
4. 📋 Implement caching layer

### Long-term (Next 6 Months)
1. 📋 Auto-scaling configuration
2. 📋 ML-based anomaly detection
3. 📋 Predictive performance modeling
4. 📋 Cost-performance optimization

---

## 📚 References

- [Microsoft Fabric Performance Best Practices](https://learn.microsoft.com/fabric/performance)
- [Delta Lake Optimization Guide](https://docs.delta.io/latest/optimizations-oss.html)
- [Power BI Performance Analyzer](https://learn.microsoft.com/power-bi/create-reports/desktop-performance-analyzer)
- [PySpark Performance Tuning](https://spark.apache.org/docs/latest/tuning.html)

---

*Last Updated: 2025-12-15*
*Next Review: After Task 014 (Power BI deployment) for actual metrics*