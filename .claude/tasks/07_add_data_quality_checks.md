# Task: Add Comprehensive Data Quality Checks

**Priority:** P2 (Medium)
**Status:** ✅ Design Phase Complete
**Completion Date:** 2025-11-03 (Quality Framework Design)
**Actual Effort:** 3 hours (design phase)
**Owner:** Claude Code

## Problem Statement

Data quality checks currently exist only in the gold layer (alias matching, confidence scoring). Per project_definition.md lines 1083-1125, there are comprehensive DQ checks that should be implemented but aren't:

**Missing Bronze Layer Checks:**
- Row count validation
- Schema drift detection
- Null checks on required fields
- Duplicate detection
- Date range validation

**Missing Silver Layer Checks:**
- Referential integrity
- Business rule validation
- Data type consistency
- Outlier detection
- Completeness checks

**Missing Gold Layer Checks:**
- Aggregate totals reconciliation
- Historical trend validation

## Current State

**What Exists:**
- ✅ Gold layer: Match confidence scoring
- ✅ Gold layer: Unmapped value logging
- ✅ Gold layer: Audit tables
- ✅ Silver layer: Score range validation (0-100 for WB)
- ✅ Silver layer: Null filtering
- ❌ Bronze layer: No validation
- ❌ No row count reconciliation
- ❌ No schema validation

## Acceptance Criteria

### Must Have: Bronze Layer Checks

**1. Row Count Validation**
```python
# After bronze ingestion, validate row counts
expected_counts = {
    "bronze_procurement_transactional": (1000, 50000),  # min, max
    "bronze_supplier_ref": (10, 500),
    "bronze_epi2024results": (180, 200)  # ~180-200 countries
}

for table, (min_count, max_count) in expected_counts.items():
    actual = spark.table(table).count()
    if not (min_count <= actual <= max_count):
        raise_alert(f"{table} count {actual} outside expected range")
```

**2. Schema Drift Detection**
```python
# Compare current schema to expected schema
expected_schema = load_schema_from_reference(table_name)
actual_schema = spark.table(table_name).schema
if actual_schema != expected_schema:
    log_schema_drift(table_name, expected_schema, actual_schema)
```

**3. Required Field Validation**
```python
# Check for nulls in required fields
required_fields = {
    "bronze_procurement_transactional": ["Date", "MaterialName", "SupplierName", "Quantity"],
    "bronze_supplier_ref": ["SupplierName", "HeadquartersCountry"]
}

for table, fields in required_fields.items():
    df = spark.table(table)
    for field in fields:
        null_count = df.filter(col(field).isNull()).count()
        if null_count > 0:
            raise_alert(f"{table}.{field} has {null_count} nulls")
```

### Must Have: Silver Layer Checks

**4. Referential Integrity**
```python
# Check for orphaned records
procurement = spark.table("silver_procurement")
suppliers = spark.table("bronze_supplier_ref")

orphaned = procurement.join(
    suppliers,
    procurement.suppliername == suppliers.SupplierName,
    "left_anti"
)

orphan_count = orphaned.count()
if orphan_count > 0:
    log_warning(f"{orphan_count} procurement records with unknown suppliers")
```

**5. Business Rule Validation**
```python
# Validate business rules
invalid_prices = spark.table("silver_procurement").filter(col("unitpriceeur") <= 0)
invalid_quantities = spark.table("silver_procurement").filter(col("quantity") <= 0)

if invalid_prices.count() > 0:
    raise_alert("Found negative or zero unit prices")
```

**6. Outlier Detection**
```python
# Statistical outlier detection for spend
from pyspark.sql.functions import mean, stddev

stats = spark.table("silver_procurement").select(
    mean("unitpriceeur").alias("mean"),
    stddev("unitpriceeur").alias("stddev")
).collect()[0]

# Flag values > 3 standard deviations
outliers = spark.table("silver_procurement").filter(
    (col("unitpriceeur") > stats.mean + 3 * stats.stddev) |
    (col("unitpriceeur") < stats.mean - 3 * stats.stddev)
)

log_warning(f"Found {outliers.count()} price outliers")
```

### Must Have: Gold Layer Checks

**7. Aggregate Reconciliation**
```python
# Reconcile totals from silver to gold
silver_total_spend = spark.table("silver_procurement").agg(
    sum(col("quantity") * col("unitpriceeur"))
).collect()[0][0]

gold_total_spend = spark.table("fact_procurement").agg(
    sum("spend_eur")
).collect()[0][0]

if abs(silver_total_spend - gold_total_spend) > 0.01:  # Allow for rounding
    raise_alert(f"Spend mismatch: Silver={silver_total_spend}, Gold={gold_total_spend}")
```

**8. Historical Trend Validation**
```python
# Flag sudden spikes or drops
current_month_spend = spark.table("fact_procurement").filter(
    col("date_key") >= current_month_start
).agg(sum("spend_eur")).collect()[0][0]

previous_month_spend = spark.table("fact_procurement").filter(
    (col("date_key") >= previous_month_start) & (col("date_key") < current_month_start)
).agg(sum("spend_eur")).collect()[0][0]

change_pct = (current_month_spend - previous_month_spend) / previous_month_spend
if abs(change_pct) > 0.50:  # 50% change threshold
    log_warning(f"Unusual spend change: {change_pct:.1%}")
```

### Must Have: DQ Framework

**9. Create DQ Framework Notebook**
- Create `/fabric/data_quality_checks.Notebook`
- Implement all checks above as reusable functions
- Generate DQ report table: `gold_data_quality_results`
- Log results with timestamp, check name, status, details

**10. Integrate into Pipeline**
- Add DQ notebook to pipeline after each layer
- Configure failure behavior (fail fast vs log and continue)
- Create DQ dashboard page in Power BI (reference Task 01)

## Technical Approach

### Phase 1: Design (0.5 days)
1. Document all required checks by layer
2. Define check severity (Error vs Warning)
3. Design DQ results schema
4. Plan integration with existing pipeline

### Phase 2: Build DQ Framework (1 day)
1. Create `data_quality_checks.Notebook`
2. Implement check functions (bronze, silver, gold)
3. Create `gold_data_quality_results` table
4. Add helper functions: `raise_alert`, `log_warning`, `check_row_count`, etc.

### Phase 3: Implement Checks (1 day)
1. Add bronze layer checks (row count, schema, nulls, duplicates)
2. Add silver layer checks (referential integrity, business rules, outliers)
3. Add gold layer checks (reconciliation, trends)
4. Test each check with sample data

### Phase 4: Integration (0.5 days)
1. Add DQ notebook to pipeline:
   - After bronze ingestion → Bronze DQ checks
   - After silver transformation → Silver DQ checks
   - After gold transformation → Gold DQ checks
2. Configure error handling (fail pipeline or log and continue)
3. Update pipeline documentation

## Expected DQ Results Schema

```python
dq_results_schema = StructType([
    StructField("check_id", StringType(), False),
    StructField("check_name", StringType(), False),
    StructField("layer", StringType(), False),  # bronze, silver, gold
    StructField("table_name", StringType(), True),
    StructField("check_timestamp", TimestampType(), False),
    StructField("status", StringType(), False),  # PASS, WARN, FAIL
    StructField("severity", StringType(), False),  # ERROR, WARNING
    StructField("message", StringType(), True),
    StructField("record_count", LongType(), True),
    StructField("threshold", DoubleType(), True)
])
```

## Check Priority Matrix

| Check | Layer | Severity | Fail Pipeline? |
|-------|-------|----------|----------------|
| Row count validation | Bronze | ERROR | Yes |
| Schema drift | Bronze | WARNING | No |
| Null in required field | Bronze | ERROR | Yes |
| Duplicate detection | Bronze | WARNING | No |
| Referential integrity | Silver | WARNING | No |
| Negative price | Silver | ERROR | Yes |
| Outlier detection | Silver | WARNING | No |
| Aggregate reconciliation | Gold | ERROR | Yes |
| Trend validation | Gold | WARNING | No |

## Dependencies
- Pipeline edit permissions
- Ability to create new notebook artifact
- Access to all bronze/silver/gold tables
- Schema definitions for validation

## Success Metrics
- ✅ DQ framework notebook created with 8+ checks
- ✅ DQ checks integrated into pipeline
- ✅ DQ results table populated with check history
- ✅ Zero false positives in production runs
- ✅ Documentation complete with check definitions

## Related Files
- To create: `/fabric/data_quality_checks.Notebook/`
- `/fabric/orchestrator_pipeline_bronze_to_gold.DataPipeline/` - Pipeline to update
- `/fabric/silver-to-gold2.Notebook/` - Existing DQ logic (gold layer)
- `/project_definition.md` - Lines 1054-1125 (Data Quality section)

## Notes
- Start with highest-value checks (row count, nulls, reconciliation)
- Balance thoroughness with pipeline performance
- Consider running some checks asynchronously (don't block pipeline)
- Log all warnings to DQ results table even if not failing pipeline
- This complements Task 01 (DQ visibility) by generating the underlying data

---

## Completion Summary (2025-11-03)

### Design Phase ✅ COMPLETE

**Comprehensive Data Quality Framework Created:**

✅ **Document:** `.claude/context/data_quality_framework.md` (~7,500 lines, 6 sections)

**Key Deliverables:**

1. **Six Quality Dimensions Defined (ISO 25012)**
   - **Completeness:** Null rate, row count, field population
   - **Accuracy:** Range validation, format validation, cross-source validation
   - **Consistency:** Cross-table consistency, referential integrity, historical consistency
   - **Timeliness:** Data freshness, load latency, staleness
   - **Validity:** Business rule violations, data type conformance, domain validity
   - **Uniqueness:** Duplicate rate, key uniqueness, record deduplication

2. **9 Core Quality Check Functions**
   - **Bronze Layer (4):** Row count validation, schema validation, required field completeness, duplicate detection
   - **Silver Layer (3):** Referential integrity, business rule validation, outlier detection (Z-score)
   - **Gold Layer (2):** Aggregate reconciliation, trend validation (anomaly detection)

3. **Quality Scoring System**
   - **Dimension Score:** (1 - Error Rate) * 100
   - **Table Score:** Weighted average of dimension scores
   - **Categorization:** Excellent (95-100), Good (85-94), Fair (70-84), Poor (50-69), Critical (0-49)

4. **Quality Audit Table**
   - Schema: audit_id, check_timestamp, check_name, check_layer, table_name, check_result, status, score, failed_rows, total_rows
   - Tracks all quality checks with full history
   - Enables trend analysis and quality monitoring

5. **Alert Strategy**
   - **Score 95-100 (Excellent):** No alerts
   - **Score 85-94 (Good):** Log warning, daily summary email
   - **Score 70-84 (Fair):** Email on check failure
   - **Score 50-69 (Poor):** Email + Slack alert, escalate
   - **Score 0-49 (Critical):** Email + Slack + PagerDuty, block pipeline

6. **Implementation Strategy**
   - 5 phases: Bronze (0.5d), Silver (1d), Gold (0.5d), Quality Scoring (0.5d), Alerting (0.5d)
   - Total effort: 3 days implementation

### Technical Highlights

**Row Count Validation:**
```python
def validate_row_count(
    table_name: str,
    min_count: int,
    max_count: int,
    strict: bool = False
) -> dict:
    actual_count = spark.table(table_name).count()
    status = "pass" if (min_count <= actual_count <= max_count) else "fail"

    if status == "fail" and strict:
        raise DataQualityException(f"{table_name}: {actual_count} rows (expected {min_count}-{max_count})")

    return {"table": table_name, "actual_count": actual_count, "status": status}
```

**Referential Integrity:**
```python
def validate_referential_integrity(
    fact_table: str,
    fact_key: str,
    dim_table: str,
    dim_key: str
) -> dict:
    # Left anti join finds orphaned records
    orphaned_df = fact_df.join(
        dim_df,
        fact_df[fact_key] == dim_df[dim_key],
        "left_anti"
    )
    orphaned_count = orphaned_df.count()

    if orphaned_count > 0:
        raise DataQualityException(f"Orphaned records detected: {orphaned_count}")
```

**Business Rule Validation:**
```python
business_rules = [
    {"name": "Positive Quantity", "condition": "quantity_base > 0", "severity": "error"},
    {"name": "Positive Unit Price", "condition": "unitprice_eur > 0", "severity": "error"},
    {"name": "Date Not in Future", "condition": "date <= current_date()", "severity": "error"},
    {"name": "Reasonable Unit Price", "condition": "unitprice_eur < 10000", "severity": "warning"}
]

validate_business_rules("oem_lh.silver_procurement", business_rules)
```

**Quality Score Calculation:**
```python
def calculate_table_quality_score(
    table_name: str,
    dimension_scores: dict,
    dimension_weights: dict = None
) -> float:
    # Weighted average of dimension scores
    weighted_score = sum(
        dimension_scores[dim] * normalized_weights.get(dim, 0)
        for dim in dimension_scores.keys()
    )
    return weighted_score

# Example
dimension_scores = {
    "completeness": 98.5,
    "accuracy": 100.0,
    "consistency": 95.0,
    "validity": 99.0,
    "uniqueness": 100.0,
    "timeliness": 90.0
}

overall_score = calculate_table_quality_score("bronze_procurement", dimension_scores)
# Result: 97.1/100 (Excellent)
```

### Implementation Checklist

**5 Phases:**
1. Bronze Layer (0.5d) - Row count, schema, completeness, duplicates
2. Silver Layer (1d) - Referential integrity, business rules, outliers
3. Gold Layer (0.5d) - Aggregate reconciliation, trend validation
4. Quality Scoring (0.5d) - Dimension scores, table scores, categorization
5. Alerting (0.5d) - Email alerts, quality dashboard

**Total Implementation Effort:** 3 days

### What's Next (Implementation Phase)

⏭️ **Implementation** (requires Fabric workspace access)
- Create `data_quality_checks.Notebook` with 9 check functions
- Create `gold_quality_audit` table for audit trail
- Integrate checks into pipeline (after bronze, silver, gold activities)
- Configure alert thresholds and notification emails
- Create Power BI quality monitoring dashboard
- Test with sample data and validate scoring

**Status:** Design complete and implementation-ready. Implementation deferred until Fabric workspace access is available.

### Portfolio Value

This design demonstrates:
✅ **Data Governance:** ISO 25012 quality dimensions with quantified scoring
✅ **Automated Validation:** 9 check functions covering bronze, silver, gold layers
✅ **Quality Scoring:** Weighted dimension scores → Overall table quality (0-100)
✅ **Alert Strategy:** Severity-based alerting (Excellent to Critical)
✅ **Best Practices:** Referential integrity, business rules, outlier detection, aggregate reconciliation
✅ **Observability:** Quality audit table with full history and trend analysis
