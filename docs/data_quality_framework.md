# Data Quality Framework - OEMMatInsightBI

**Role:** Design rationale (ISO 25012 dimensions, check catalogue, scoring weights) for the shipped DQ architecture.
**As-built companion:** `data_quality_architecture.md` — that doc covers how these checks are wired into the medallion pipeline and the gold observability tables (`gold_quality_history`, `gold_gap_registry`, `gold_low_confidence_audit`, `gold_data_gaps`).

## Executive Summary

This document defines the Data Quality (DQ) framework for the OEMMatInsightBI data pipeline: a multi-layer quality framework covering bronze, silver, and gold layers with automated validation, scoring, monitoring, and alerting. The framework is implemented — see `data_quality_architecture.md` for the touchpoints, the blocking gate, and the observability tables that surface these metrics to the report.

**Key Decisions:**
- ✅ **Layered Quality Checks:** Bronze (schema, completeness), Silver (referential integrity, business rules), Gold (aggregate reconciliation)
- ✅ **Quality Dimensions:** 6 dimensions (Completeness, Accuracy, Consistency, Timeliness, Validity, Uniqueness)
- ✅ **Automated Validation:** 20+ validation functions integrated into pipeline
- ✅ **Quality Scoring:** 0-100 score per table/layer with weighted dimensions
- ✅ **Alerting Strategy:** Thresholds for warnings (80-90) and errors (<80)

**Expected Benefits:**
- **Data Trust:** Quantified quality scores build confidence in analytics
- **Early Detection:** Catch data issues at source (bronze) before propagation
- **Operational Excellence:** Automated monitoring reduces manual investigation
- **Portfolio Value:** Demonstrates enterprise data governance practices

---

## 1. Data Quality Dimensions

### Six Quality Dimensions (ISO 25012)

#### 1. Completeness
**Definition:** Extent to which data is not missing and is of sufficient breadth/depth.

**Metrics:**
- **Null Rate:** % of required fields that are null
- **Row Count:** Actual vs expected row counts
- **Field Population:** % of optional fields populated

**Acceptance Criteria:**
- Required fields: 0% null rate
- Optional fields: >50% population for actionable insights

---

#### 2. Accuracy
**Definition:** Degree to which data correctly describes the real-world object/event.

**Metrics:**
- **Range Validation:** Values within expected ranges (e.g., EPI score 0-100)
- **Format Validation:** Data matches expected patterns (e.g., ISO3 country codes)
- **Cross-Source Validation:** External data matches authoritative sources

**Acceptance Criteria:**
- 100% of values within valid ranges
- <1% format violations

---

#### 3. Consistency
**Definition:** Data is consistent across systems and over time.

**Metrics:**
- **Cross-Table Consistency:** Same entity has same attributes across tables
- **Historical Consistency:** Dimension attributes don't change unexpectedly
- **Referential Integrity:** Foreign keys match primary keys

**Acceptance Criteria:**
- 0 orphaned records (referential integrity)
- <5% historical attribute changes per month

---

#### 4. Timeliness
**Definition:** Data is available when needed and represents current state.

**Metrics:**
- **Data Freshness:** Time since last update
- **Load Latency:** Time from source update to availability in reports
- **Staleness:** Age of oldest record in active dataset

**Acceptance Criteria:**
- Procurement data: <24 hours old
- External data (EPI/WGI): <1 year old

---

#### 5. Validity
**Definition:** Data conforms to defined business rules, constraints, and data types.

**Metrics:**
- **Business Rule Violations:** Quantity >0, UnitPrice >0, Date not in future
- **Data Type Conformance:** Numeric fields are numeric, dates are valid dates
- **Domain Validity:** Country codes exist in ISO3 list

**Acceptance Criteria:**
- 0 business rule violations for critical fields
- 100% data type conformance

---

#### 6. Uniqueness
**Definition:** No unwanted duplication exists in the dataset.

**Metrics:**
- **Duplicate Rate:** % of rows that are exact duplicates
- **Key Uniqueness:** Primary/natural keys are unique
- **Record Duplication:** Same transaction appears multiple times

**Acceptance Criteria:**
- 0% duplicate rate on natural keys
- <1% acceptable duplicate rate on descriptive attributes

---

## 2. Quality Check Library

### 2.1 Bronze Layer Checks

**Purpose:** Validate data at ingestion, catch source system issues early

#### Check 1: Row Count Validation
```python
def validate_row_count(
    table_name: str,
    min_count: int,
    max_count: int,
    strict: bool = False
) -> dict:
    """
    Validate table row count is within expected range

    Args:
        table_name: Fully qualified table name (e.g., "oem_lh.bronze_procurement_transactional")
        min_count: Minimum acceptable row count
        max_count: Maximum acceptable row count
        strict: If True, fail pipeline on violation; if False, log warning

    Returns:
        dict: {
            "table": table_name,
            "actual_count": int,
            "expected_range": (min, max),
            "status": "pass" | "fail",
            "message": str
        }
    """

    actual_count = spark.table(table_name).count()

    status = "pass" if (min_count <= actual_count <= max_count) else "fail"
    message = f"{table_name}: {actual_count} rows (expected {min_count}-{max_count})"

    result = {
        "table": table_name,
        "actual_count": actual_count,
        "expected_range": (min_count, max_count),
        "status": status,
        "message": message,
        "timestamp": datetime.now()
    }

    if status == "fail":
        if strict:
            raise DataQualityException(message)
        else:
            print(f"⚠️  WARNING: {message}")

    # Log to quality audit table
    log_quality_check(check_name="row_count_validation", result=result)

    return result

# Usage
validate_row_count("oem_lh.bronze_procurement_transactional", min_count=1000, max_count=100000)
validate_row_count("oem_lh.bronze_epi2024results", min_count=180, max_count=200, strict=True)
```

**Test Scenario:**
- Bronze procurement loaded with 500 rows (below threshold of 1000)
- Expected: Warning logged, pipeline continues
- Actual: `⚠️  WARNING: bronze_procurement_transactional: 500 rows (expected 1000-100000)`

---

#### Check 2: Schema Validation
```python
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, DateType

def validate_schema(
    table_name: str,
    expected_schema: StructType,
    allow_additional_columns: bool = True
) -> dict:
    """
    Validate table schema matches expected structure

    Args:
        table_name: Table to validate
        expected_schema: Expected StructType schema
        allow_additional_columns: If True, additional columns are warnings; if False, they fail

    Returns:
        dict: {
            "missing_columns": List[str],
            "extra_columns": List[str],
            "type_mismatches": List[dict],
            "status": "pass" | "fail"
        }
    """

    actual_schema = spark.table(table_name).schema

    # Build column name -> type mapping
    expected_map = {field.name: field.dataType for field in expected_schema.fields}
    actual_map = {field.name: field.dataType for field in actual_schema.fields}

    # Find differences
    missing_columns = set(expected_map.keys()) - set(actual_map.keys())
    extra_columns = set(actual_map.keys()) - set(expected_map.keys())

    # Check type mismatches for common columns
    type_mismatches = []
    for col in set(expected_map.keys()) & set(actual_map.keys()):
        if expected_map[col] != actual_map[col]:
            type_mismatches.append({
                "column": col,
                "expected_type": str(expected_map[col]),
                "actual_type": str(actual_map[col])
            })

    # Determine status
    has_errors = len(missing_columns) > 0 or len(type_mismatches) > 0
    has_warnings = len(extra_columns) > 0

    if has_errors:
        status = "fail"
    elif has_warnings and not allow_additional_columns:
        status = "fail"
    else:
        status = "pass"

    result = {
        "table": table_name,
        "missing_columns": list(missing_columns),
        "extra_columns": list(extra_columns),
        "type_mismatches": type_mismatches,
        "status": status,
        "timestamp": datetime.now()
    }

    # Log findings
    if missing_columns:
        print(f"❌ MISSING COLUMNS in {table_name}: {missing_columns}")
    if extra_columns:
        print(f"⚠️  EXTRA COLUMNS in {table_name}: {extra_columns}")
    if type_mismatches:
        print(f"❌ TYPE MISMATCHES in {table_name}: {type_mismatches}")

    log_quality_check(check_name="schema_validation", result=result)

    if status == "fail":
        raise DataQualityException(f"Schema validation failed for {table_name}")

    return result

# Usage
expected_procurement_schema = StructType([
    StructField("Date", DateType(), False),
    StructField("MaterialName", StringType(), False),
    StructField("SupplierName", StringType(), False),
    StructField("Quantity", DoubleType(), False),
    StructField("Unit", StringType(), False),
    StructField("UnitPriceEUR", DoubleType(), False)
])

validate_schema("oem_lh.bronze_procurement_transactional", expected_procurement_schema)
```

---

#### Check 3: Required Field Completeness
```python
def validate_required_fields(
    table_name: str,
    required_fields: List[str],
    null_tolerance_pct: float = 0.0
) -> dict:
    """
    Check for null values in required fields

    Args:
        table_name: Table to validate
        required_fields: List of column names that must not be null
        null_tolerance_pct: Max acceptable % of nulls (0.0 = no nulls allowed)

    Returns:
        dict: {
            "field_results": {field_name: null_count},
            "status": "pass" | "fail"
        }
    """

    df = spark.table(table_name)
    total_rows = df.count()

    field_results = {}
    failed_fields = []

    for field in required_fields:
        null_count = df.filter(F.col(field).isNull()).count()
        null_pct = (null_count / total_rows) * 100 if total_rows > 0 else 0

        field_results[field] = {
            "null_count": null_count,
            "null_pct": null_pct,
            "status": "pass" if null_pct <= null_tolerance_pct else "fail"
        }

        if null_pct > null_tolerance_pct:
            failed_fields.append(f"{field} ({null_count} nulls, {null_pct:.2f}%)")
            print(f"❌ {table_name}.{field}: {null_count} nulls ({null_pct:.2f}%) exceeds tolerance {null_tolerance_pct}%")

    status = "pass" if len(failed_fields) == 0 else "fail"

    result = {
        "table": table_name,
        "field_results": field_results,
        "failed_fields": failed_fields,
        "status": status,
        "timestamp": datetime.now()
    }

    log_quality_check(check_name="required_field_completeness", result=result)

    if status == "fail":
        raise DataQualityException(f"Required fields have nulls: {failed_fields}")

    return result

# Usage
validate_required_fields(
    "oem_lh.bronze_procurement_transactional",
    required_fields=["Date", "MaterialName", "SupplierName", "Quantity", "UnitPriceEUR"],
    null_tolerance_pct=0.0  # 0% nulls allowed
)
```

---

#### Check 4: Duplicate Detection
```python
def detect_duplicates(
    table_name: str,
    key_columns: List[str],
    duplicate_tolerance_pct: float = 0.0
) -> dict:
    """
    Detect duplicate records based on key columns

    Args:
        table_name: Table to check
        key_columns: Columns that define uniqueness
        duplicate_tolerance_pct: Max acceptable % of duplicates

    Returns:
        dict: {
            "total_rows": int,
            "unique_rows": int,
            "duplicate_count": int,
            "duplicate_pct": float,
            "status": "pass" | "fail"
        }
    """

    df = spark.table(table_name)
    total_rows = df.count()

    # Count distinct keys
    unique_rows = df.select(key_columns).distinct().count()
    duplicate_count = total_rows - unique_rows
    duplicate_pct = (duplicate_count / total_rows) * 100 if total_rows > 0 else 0

    status = "pass" if duplicate_pct <= duplicate_tolerance_pct else "fail"

    result = {
        "table": table_name,
        "key_columns": key_columns,
        "total_rows": total_rows,
        "unique_rows": unique_rows,
        "duplicate_count": duplicate_count,
        "duplicate_pct": duplicate_pct,
        "status": status,
        "timestamp": datetime.now()
    }

    if status == "fail":
        print(f"❌ {table_name}: {duplicate_count} duplicates ({duplicate_pct:.2f}%) exceeds tolerance {duplicate_tolerance_pct}%")

        # Log sample duplicates for investigation
        duplicates_df = (df
            .groupBy(key_columns)
            .count()
            .filter(F.col("count") > 1)
            .orderBy(F.desc("count"))
            .limit(10))

        print("Top 10 duplicate keys:")
        duplicates_df.show(truncate=False)

    log_quality_check(check_name="duplicate_detection", result=result)

    if status == "fail" and duplicate_tolerance_pct == 0.0:
        raise DataQualityException(f"Duplicates detected: {duplicate_count}")

    return result

# Usage
detect_duplicates(
    "oem_lh.bronze_procurement_transactional",
    key_columns=["Date", "MaterialName", "SupplierName", "Quantity"],
    duplicate_tolerance_pct=0.0
)
```

---

### 2.2 Silver Layer Checks

**Purpose:** Validate transformations, business rules, referential integrity

#### Check 5: Referential Integrity
```python
def validate_referential_integrity(
    fact_table: str,
    fact_key: str,
    dim_table: str,
    dim_key: str,
    tolerance_pct: float = 0.0
) -> dict:
    """
    Check for orphaned records (fact records without matching dimension)

    Args:
        fact_table: Fact table to check
        fact_key: Foreign key column in fact table
        dim_table: Dimension table
        dim_key: Primary key column in dimension table
        tolerance_pct: Max acceptable % of orphaned records

    Returns:
        dict: {
            "orphaned_count": int,
            "orphaned_pct": float,
            "status": "pass" | "fail"
        }
    """

    fact_df = spark.table(fact_table)
    dim_df = spark.table(dim_table)

    # Left anti join finds fact records without dimension match
    orphaned_df = fact_df.join(
        dim_df,
        fact_df[fact_key] == dim_df[dim_key],
        "left_anti"
    )

    total_fact_rows = fact_df.count()
    orphaned_count = orphaned_df.count()
    orphaned_pct = (orphaned_count / total_fact_rows) * 100 if total_fact_rows > 0 else 0

    status = "pass" if orphaned_pct <= tolerance_pct else "fail"

    result = {
        "fact_table": fact_table,
        "dim_table": dim_table,
        "total_fact_rows": total_fact_rows,
        "orphaned_count": orphaned_count,
        "orphaned_pct": orphaned_pct,
        "status": status,
        "timestamp": datetime.now()
    }

    if status == "fail":
        print(f"❌ Referential integrity violation: {orphaned_count} {fact_table} records have no match in {dim_table}")

        # Show sample orphaned keys
        print("Sample orphaned keys:")
        orphaned_df.select(fact_key).distinct().limit(10).show()

    log_quality_check(check_name="referential_integrity", result=result)

    if status == "fail" and tolerance_pct == 0.0:
        raise DataQualityException(f"Orphaned records detected: {orphaned_count}")

    return result

# Usage
validate_referential_integrity(
    fact_table="oem_lh.fact_procurement",
    fact_key="material_key",
    dim_table="oem_lh.gold_dim_material",
    dim_key="material_key",
    tolerance_pct=0.0
)
```

---

#### Check 6: Business Rule Validation
```python
def validate_business_rules(
    table_name: str,
    rules: List[dict]
) -> dict:
    """
    Validate business rules on table

    Args:
        table_name: Table to validate
        rules: List of rule definitions:
            {
                "name": "Positive Quantity",
                "condition": "quantity_base > 0",
                "severity": "error" | "warning"
            }

    Returns:
        dict: {
            "rule_results": List[dict],
            "status": "pass" | "fail"
        }
    """

    df = spark.table(table_name)
    total_rows = df.count()

    rule_results = []
    failed_rules = []

    for rule in rules:
        rule_name = rule["name"]
        condition = rule["condition"]
        severity = rule.get("severity", "error")

        # Invert condition to find violations
        violation_condition = f"NOT ({condition})"
        violations_df = df.filter(F.expr(violation_condition))
        violation_count = violations_df.count()
        violation_pct = (violation_count / total_rows) * 100 if total_rows > 0 else 0

        rule_status = "pass" if violation_count == 0 else "fail"

        rule_result = {
            "rule_name": rule_name,
            "condition": condition,
            "violation_count": violation_count,
            "violation_pct": violation_pct,
            "severity": severity,
            "status": rule_status
        }

        rule_results.append(rule_result)

        if rule_status == "fail":
            symbol = "❌" if severity == "error" else "⚠️ "
            print(f"{symbol} Rule '{rule_name}' failed: {violation_count} violations ({violation_pct:.2f}%)")

            if severity == "error":
                failed_rules.append(rule_name)

    overall_status = "pass" if len(failed_rules) == 0 else "fail"

    result = {
        "table": table_name,
        "rule_results": rule_results,
        "failed_rules": failed_rules,
        "status": overall_status,
        "timestamp": datetime.now()
    }

    log_quality_check(check_name="business_rule_validation", result=result)

    if overall_status == "fail":
        raise DataQualityException(f"Business rules failed: {failed_rules}")

    return result

# Usage
business_rules = [
    {"name": "Positive Quantity", "condition": "quantity_base > 0", "severity": "error"},
    {"name": "Positive Unit Price", "condition": "unitprice_eur > 0", "severity": "error"},
    {"name": "Date Not in Future", "condition": "date <= current_date()", "severity": "error"},
    {"name": "Reasonable Unit Price", "condition": "unitprice_eur < 10000", "severity": "warning"}  # Outlier detection
]

validate_business_rules("oem_lh.silver_procurement", business_rules)
```

---

#### Check 7: Outlier Detection (Statistical)
```python
def detect_outliers_zscore(
    table_name: str,
    numeric_column: str,
    z_threshold: float = 3.0
) -> dict:
    """
    Detect outliers using Z-score method

    Args:
        table_name: Table to analyze
        numeric_column: Column to check for outliers
        z_threshold: Z-score threshold (typically 3.0 = 99.7% confidence)

    Returns:
        dict: {
            "outlier_count": int,
            "outlier_pct": float,
            "outlier_values": List[float]
        }
    """

    df = spark.table(table_name)

    # Calculate mean and stddev
    stats = df.select(
        F.mean(numeric_column).alias("mean"),
        F.stddev(numeric_column).alias("stddev")
    ).collect()[0]

    mean_val = stats["mean"]
    stddev_val = stats["stddev"]

    if stddev_val is None or stddev_val == 0:
        return {"outlier_count": 0, "status": "pass", "message": "No variance in data"}

    # Calculate Z-score and find outliers
    outliers_df = df.withColumn(
        "z_score",
        F.abs((F.col(numeric_column) - mean_val) / stddev_val)
    ).filter(F.col("z_score") > z_threshold)

    total_rows = df.count()
    outlier_count = outliers_df.count()
    outlier_pct = (outlier_count / total_rows) * 100 if total_rows > 0 else 0

    result = {
        "table": table_name,
        "column": numeric_column,
        "mean": mean_val,
        "stddev": stddev_val,
        "z_threshold": z_threshold,
        "outlier_count": outlier_count,
        "outlier_pct": outlier_pct,
        "status": "pass",  # Outliers are informational, not failures
        "timestamp": datetime.now()
    }

    if outlier_count > 0:
        print(f"ℹ️  {outlier_count} outliers detected in {table_name}.{numeric_column} ({outlier_pct:.2f}%)")

        # Show outlier samples
        outlier_samples = outliers_df.select(numeric_column, "z_score") \
                                     .orderBy(F.desc("z_score")) \
                                     .limit(10)
        print("Top 10 outliers:")
        outlier_samples.show()

    log_quality_check(check_name="outlier_detection", result=result)

    return result

# Usage
detect_outliers_zscore("oem_lh.silver_procurement", "unitprice_eur", z_threshold=3.0)
detect_outliers_zscore("oem_lh.silver_procurement", "quantity_base", z_threshold=3.0)
```

---

### 2.3 Gold Layer Checks

**Purpose:** Validate aggregations, trends, and business metrics

#### Check 8: Aggregate Reconciliation
```python
def reconcile_aggregates(
    source_table: str,
    target_table: str,
    source_column: str,
    target_column: str,
    tolerance_pct: float = 0.01
) -> dict:
    """
    Reconcile aggregate totals between source and target layers

    Args:
        source_table: Source table (e.g., silver)
        target_table: Target table (e.g., gold fact)
        source_column: Column to sum in source
        target_column: Column to sum in target
        tolerance_pct: Max acceptable difference % (0.01 = 1%)

    Returns:
        dict: {
            "source_total": float,
            "target_total": float,
            "difference": float,
            "difference_pct": float,
            "status": "pass" | "fail"
        }
    """

    source_total = spark.table(source_table).select(F.sum(source_column)).collect()[0][0] or 0
    target_total = spark.table(target_table).select(F.sum(target_column)).collect()[0][0] or 0

    difference = target_total - source_total
    difference_pct = abs(difference / source_total) * 100 if source_total != 0 else 0

    status = "pass" if difference_pct <= tolerance_pct else "fail"

    result = {
        "source_table": source_table,
        "target_table": target_table,
        "source_total": source_total,
        "target_total": target_total,
        "difference": difference,
        "difference_pct": difference_pct,
        "tolerance_pct": tolerance_pct,
        "status": status,
        "timestamp": datetime.now()
    }

    if status == "fail":
        print(f"❌ Reconciliation failed: {difference_pct:.4f}% difference exceeds tolerance {tolerance_pct}%")
        print(f"   Source total: {source_total:,.2f}")
        print(f"   Target total: {target_total:,.2f}")
        print(f"   Difference: {difference:,.2f}")

    log_quality_check(check_name="aggregate_reconciliation", result=result)

    if status == "fail":
        raise DataQualityException(f"Aggregate reconciliation failed: {difference_pct:.4f}% difference")

    return result

# Usage
reconcile_aggregates(
    source_table="oem_lh.silver_procurement",
    target_table="oem_lh.fact_procurement",
    source_column="spend_eur",
    target_column="spend_eur",
    tolerance_pct=0.01  # 1% tolerance for rounding
)
```

---

#### Check 9: Trend Validation (Anomaly Detection)
```python
def validate_historical_trend(
    table_name: str,
    metric_column: str,
    date_column: str,
    anomaly_threshold_pct: float = 50.0
) -> dict:
    """
    Detect anomalous changes in historical trends

    Args:
        table_name: Table with historical data
        metric_column: Column to track (e.g., "total_spend")
        date_column: Date column for time series
        anomaly_threshold_pct: % change threshold (50 = 50% increase/decrease triggers alert)

    Returns:
        dict: {
            "current_value": float,
            "previous_value": float,
            "pct_change": float,
            "status": "pass" | "fail"
        }
    """

    df = spark.table(table_name)

    # Get current and previous period values
    current_date = df.select(F.max(date_column)).collect()[0][0]
    previous_date = df.filter(F.col(date_column) < current_date) \
                      .select(F.max(date_column)) \
                      .collect()[0][0]

    if previous_date is None:
        return {"status": "pass", "message": "Not enough history for trend validation"}

    current_value = df.filter(F.col(date_column) == current_date) \
                      .select(F.sum(metric_column)) \
                      .collect()[0][0] or 0

    previous_value = df.filter(F.col(date_column) == previous_date) \
                       .select(F.sum(metric_column)) \
                       .collect()[0][0] or 0

    if previous_value == 0:
        pct_change = 0
    else:
        pct_change = ((current_value - previous_value) / previous_value) * 100

    status = "pass" if abs(pct_change) <= anomaly_threshold_pct else "fail"

    result = {
        "table": table_name,
        "current_date": current_date,
        "previous_date": previous_date,
        "current_value": current_value,
        "previous_value": previous_value,
        "pct_change": pct_change,
        "anomaly_threshold_pct": anomaly_threshold_pct,
        "status": status,
        "timestamp": datetime.now()
    }

    if status == "fail":
        direction = "increase" if pct_change > 0 else "decrease"
        print(f"⚠️  Anomalous {direction} detected: {abs(pct_change):.1f}% change in {metric_column}")
        print(f"   Current ({current_date}): {current_value:,.2f}")
        print(f"   Previous ({previous_date}): {previous_value:,.2f}")

    log_quality_check(check_name="trend_validation", result=result)

    return result

# Usage
validate_historical_trend(
    table_name="oem_lh.fact_procurement",
    metric_column="spend_eur",
    date_column="date_key",
    anomaly_threshold_pct=50.0  # Alert if spend changes >50% month-over-month
)
```

---

## 3. Quality Scoring System

### 3.1 Dimension-Level Scoring

**Formula:**
```
Dimension Score (0-100) = (1 - Error Rate) * 100

Where Error Rate = Failed Rows / Total Rows
```

**Example:**
```python
def calculate_completeness_score(table_name: str, required_fields: List[str]) -> float:
    """Calculate completeness score for a table"""

    df = spark.table(table_name)
    total_rows = df.count()
    total_cells = total_rows * len(required_fields)

    # Count null cells
    null_cells = 0
    for field in required_fields:
        null_cells += df.filter(F.col(field).isNull()).count()

    completeness_rate = 1 - (null_cells / total_cells) if total_cells > 0 else 0
    completeness_score = completeness_rate * 100

    return completeness_score

# Usage
completeness_score = calculate_completeness_score(
    "oem_lh.bronze_procurement_transactional",
    ["Date", "MaterialName", "SupplierName", "Quantity", "UnitPriceEUR"]
)
print(f"Completeness Score: {completeness_score:.1f}/100")
```

---

### 3.2 Overall Table Quality Score

**Weighted Average of Dimension Scores:**

```python
def calculate_table_quality_score(
    table_name: str,
    dimension_scores: dict,
    dimension_weights: dict = None
) -> float:
    """
    Calculate overall quality score for a table

    Args:
        table_name: Table to score
        dimension_scores: {dimension_name: score}
        dimension_weights: {dimension_name: weight} (defaults to equal weights)

    Returns:
        float: Overall quality score (0-100)
    """

    if dimension_weights is None:
        # Default: equal weights
        dimension_weights = {dim: 1.0 for dim in dimension_scores.keys()}

    # Normalize weights to sum to 1.0
    total_weight = sum(dimension_weights.values())
    normalized_weights = {dim: w / total_weight for dim, w in dimension_weights.items()}

    # Calculate weighted score
    weighted_score = sum(
        dimension_scores[dim] * normalized_weights.get(dim, 0)
        for dim in dimension_scores.keys()
    )

    return weighted_score

# Usage
dimension_scores = {
    "completeness": 98.5,
    "accuracy": 100.0,
    "consistency": 95.0,
    "validity": 99.0,
    "uniqueness": 100.0,
    "timeliness": 90.0
}

# Custom weights (more important dimensions have higher weight)
dimension_weights = {
    "completeness": 0.25,
    "accuracy": 0.25,
    "consistency": 0.20,
    "validity": 0.15,
    "uniqueness": 0.10,
    "timeliness": 0.05
}

overall_score = calculate_table_quality_score(
    "oem_lh.bronze_procurement_transactional",
    dimension_scores,
    dimension_weights
)

print(f"Overall Quality Score: {overall_score:.1f}/100")
```

**Quality Score Categorization:**
```python
def categorize_quality_score(score: float) -> str:
    """Categorize quality score into rating"""

    if score >= 95:
        return "Excellent"
    elif score >= 85:
        return "Good"
    elif score >= 70:
        return "Fair"
    elif score >= 50:
        return "Poor"
    else:
        return "Critical"
```

---

## 4. Quality Audit Table

### Schema
```python
quality_audit_schema = StructType([
    StructField("audit_id", StringType(), False),           # UUID
    StructField("check_timestamp", TimestampType(), False),  # When check ran
    StructField("check_name", StringType(), False),          # "row_count_validation", etc.
    StructField("check_layer", StringType(), False),         # "bronze", "silver", "gold"
    StructField("table_name", StringType(), False),          # Table checked
    StructField("check_result", StringType(), True),         # JSON of full result
    StructField("status", StringType(), False),              # "pass", "fail", "warning"
    StructField("score", DoubleType(), True),                # Quality score (0-100)
    StructField("failed_rows", LongType(), True),            # Count of rows failing check
    StructField("total_rows", LongType(), True),             # Total rows in table
    StructField("execution_time_ms", IntegerType(), True)    # How long check took
])
```

### Usage
```python
def log_quality_check(check_name: str, result: dict):
    """Log quality check result to audit table"""

    import uuid
    import json

    audit_record = spark.createDataFrame([{
        "audit_id": str(uuid.uuid4()),
        "check_timestamp": datetime.now(),
        "check_name": check_name,
        "check_layer": result.get("layer", "unknown"),
        "table_name": result.get("table", "unknown"),
        "check_result": json.dumps(result),
        "status": result.get("status", "unknown"),
        "score": result.get("score", None),
        "failed_rows": result.get("failed_rows", None),
        "total_rows": result.get("total_rows", None),
        "execution_time_ms": result.get("execution_time_ms", None)
    }], schema=quality_audit_schema)

    # Append to audit table
    audit_record.write.format("delta").mode("append").saveAsTable("oem_lh.gold_quality_audit")
```

---

## 5. Implementation Strategy

### Phase 1: Bronze Layer (0.5 days)
- Implement row count validation
- Implement schema validation
- Implement required field completeness
- Implement duplicate detection

### Phase 2: Silver Layer (1 day)
- Implement referential integrity checks
- Implement business rule validation
- Implement outlier detection

### Phase 3: Gold Layer (0.5 days)
- Implement aggregate reconciliation
- Implement trend validation

### Phase 4: Quality Scoring (0.5 days)
- Implement dimension score calculation
- Implement overall table score
- Create quality dashboard in Power BI

### Phase 5: Alerting (0.5 days)
- Configure email alerts for failures
- Create quality monitoring dashboard

---

## 6. Alert Strategy

**Severity Levels:**

> ⚠️ **This table is ASPIRATIONAL and describes score bands only. No row of it halts
> the pipeline** — the implemented gate ignores `score` entirely. Read the section
> immediately below before acting on this table; conflating the two is a recorded
> source of mis-scoped work (FR-012).

| Score Range | Severity | Intended Action | Notification |
|-------------|----------|-----------------|--------------|
| 95-100 | Excellent | None | None |
| 85-94 | Good | Log warning | Daily summary email |
| 70-84 | Fair | Alert | Email on check failure |
| 50-69 | Poor | Escalate | Email + Slack alert |
| 0-49 | Critical | Escalate (does **not** block — see below) | Email + Slack + PagerDuty |

**Implementation status:** none of the notification actions in this table are wired —
the pipeline currently carries `NoNotification` on every activity and no
email/Teams/webhook configuration (task-041 owns that decision). The only column with
a live implementation is the score band itself, via
`gold_quality_history.breach_flag` at a `< 70.0` threshold — which is advisory.

### Score severity vs. the blocking gate (they are different mechanisms)

The severity table above is a **score** band. It is not what halts the pipeline. Two independent mechanisms exist and they are routinely confused:

| | `breach_flag` (score threshold) | The gate (`status` over `BLOCKING_CHECKS`) |
|---|---|---|
| **What it is** | `metric_value < threshold` — for DQ check rows, `score < 70.0` (`data_quality_checks`, section 5) | `result["status"] == "fail"` for any check in the `BLOCKING_CHECKS` set (`data_quality_checks`, section 7) |
| **Where it lands** | `gold_quality_history.breach_flag` | `gold_quality_history.status`, plus the `entity = 'gate'` verdict rows |
| **Effect on the pipeline** | None. Advisory / trending only. | Raises `DataQualityException` once, after persistence — fails the `data_quality_checks` activity and halts the pipeline. |

**They diverge, and the divergence is not rare.** `grain_uniqueness` on `fact_supply_share` failing on 2 duplicate grains out of 2,561 rows scores ~99.9. That is far above the 70.0 breach threshold, so `breach_flag` is `false` — and the check is in `BLOCKING_CHECKS` with `status = "fail"`, so the pipeline halts anyway. A run can therefore record **0 breaches and still be a blocked run**. Asserting "the DQ gate passed" from `breach_flag` reads the wrong field and produces a PASS that is evidence of nothing. Observed live on 2026-07-22: two runs recorded 0 breaches while one of them carried a blocking failure.

**To answer "did the gate pass on run X" from the table alone** (task-040 — one query, no notebook source):

```sql
SELECT metric_name, metric_value, status
FROM   oem_lh.gold_quality_history
WHERE  entity = 'gate'
  AND  refresh_timestamp = (SELECT MAX(refresh_timestamp)
                            FROM   oem_lh.gold_quality_history
                            WHERE  entity = 'gate');
```

`status` is `'pass'` or `'fail'`. `dq_gate_raised = 1.0` means the aggregated raise fired and the pipeline halted there; `dq_gate_blocking_failures` is the count; `dq_gate_blocking_evaluated` guards against a stale `BLOCKING_CHECKS` entry silently demoting a check to advisory. `refresh_timestamp` is written in **UTC** while the Fabric UI shows local time (UTC+2 CEST) — a correct, current measurement reads two hours "early".

**Column conventions on `gold_quality_history`** (both added by task-040):

- `status` — `'pass' | 'fail' | 'warning'` on per-check rows; `'n/a'` on rows that are not a single check result (dimension/overall aggregates, silver_to_gold's coverage metrics, the gate's evaluated-count row); **NULL only on rows written before task-040**, which are deliberately not backfilled because their gate outcome was never recorded.
- `producer` — `'data_quality_checks'` or `'silver_to_gold'`. Both notebooks append to this table on every pipeline run, each with its own `refresh_timestamp`, so `COUNT(DISTINCT refresh_timestamp)` over the whole table double-counts runs. Filter by `producer` first.

---

## 7. Persistent Advisory Failures (Measured and Accepted)

Three checks record a non-`pass` row on **every** pipeline run. None is a broken gate, and none is a defect the pipeline should repair silently — but until 2026-08-06 none was documented either, so a reader meeting `dq_data_type_consistency = 75.0` in `gold_quality_history` had nowhere to look. This section is that place.

None of the three is in `BLOCKING_CHECKS`, so the gate correctly does not raise on them (§ "Score severity vs. the blocking gate" above). They stay in the check set deliberately: each makes a real property of the data visible, and removing one — or relabelling its expectation to force a green score — would hide the property instead of resolving it.

| Check | Table | Score | `status` | `breach_flag` | Disposition |
|---|---|---|---|---|---|
| `date_range_validation` | `bronze_procurement_transactional` | `0.0` | `warning` | `true` | **Expected by design** — bronze is byte-faithful to a malformed source |
| `business_rule_validation` | `silver_procurement` | `81.82` | `fail` | `false` | **Accepted** — a dimensionally impossible conversion |
| `data_type_consistency` | `silver_procurement` | `75.00` | `fail` | `false` | **Accepted** — divergence recorded; migration path in 7.3 |

**Measurement provenance.** Every figure below was measured on **2026-08-06** directly from the Delta transaction log and data files over the OneLake DFS API (`silver_procurement` at version 93 — checkpoint `…090.checkpoint.parquet` plus commits 091–093), *not* inferred from the check's own score. Each score is then reproduced arithmetically from the measured data. If these numbers ever stop reconciling, the data changed — the reading was not loose.

### 7.1 `date_range_validation = 0.0` on `bronze_procurement_transactional` — expected

**Measured:** 132 of 132 bronze rows (100.00%) fall outside the plausible window `[2015-01-01, today]`, and all 132 are *future* dates. The raw range is `2028-02-24` → `2031-12-24`. Score `= (1 − 100.00/100) × 100 = 0.0`; `status = "warning"` because `validate_date_range` is informational by construction (`status` is `"warning"`, never `"fail"`, once `out_of_range_pct > tolerance_pct`).

**Why it is correct.** The source table `dbo.procurement_transactional` stores every transaction date with its **day and year components transposed** — the calendar year sits in the day position, and the day-of-month sits in the year position as an offset from 2000. Raw `2028-02-24` means `2024-02-28`. Bronze deliberately holds the source's raw, malformed value: the retired `bronze_azureSQLdb2table` Dataflow Gen2 used to fix this at ingestion, but a Copy activity cannot transform, so the correction moved to `bronze_to_silver` (`DATE_SWAP_EPOCH = 2000`, `correct_procurement_date`). Keeping bronze byte-faithful to the source is the better medallion practice and is what makes this warning inevitable.

**So the check is measuring the right thing and reporting it honestly.** A bronze date-range score of `0.0` on this table is the *expected steady state*; it becoming non-zero would mean the source stopped transposing dates, which is the event worth noticing. Silver is where dates are correct — `silver_procurement` spans calendar 2024.

### 7.2 `business_rule_validation = 81.82` on `silver_procurement` — accepted

**Measured:** the `unit` domain is exactly `{kg: 108, pcs: 24}` across 132 rows, with **no NULLs**. The single rule on this table is `Unit In Conversion Domain` (`unit IS NOT NULL AND lower(trim(unit)) IN ('kg','g','mg','t')`, severity `error`), so 24 rows violate it. Score `= (1 − 24/132) × 100 = 81.8181… → 81.82`.

The 24 violating rows are **two materials only**, 12 months each:

| Material | `unit` | rows |
|---|---|---|
| Tires (Rubber compound) | `pcs` | 12 |
| Electronics (controllers, sensors) | `pcs` | 12 |

**Why it is accepted rather than fixed.** `pcs` is a **count**, not a mass. There is no universal pieces→kilogram factor — it depends on the per-item mass of each specific part — so no entry can be added to `UNIT_CONVERSION_FACTORS` to make this convert. The divergence is dimensional, not a data error.

`silver_to_gold` already handles it correctly and deliberately (task-030 AC2/AC3): a unit outside `{kg, g, mg, t}` yields a **NULL `quantity_base`**, while `spend_eur` is still computed on the per-row-unit basis (`quantity × unitpriceeur`), because tyres and electronic control units are genuinely priced per piece. **An unrecognized unit therefore withholds MASS, not SPEND.** The practical consequence, worth stating plainly for anyone reading a report:

- **Spend analysis covers all 132 rows.** `spend_eur` is real for `pcs` rows.
- **Mass/kg analysis covers 108 rows.** `quantity_base` is NULL for the 24 `pcs` rows, by design.
- The unrecognized slice is persisted every run to `gold_unmapped_unit_audit`, and `silver_to_gold` prints the observed unit domain, so the boundary is observable rather than inferred.

**This check is the mechanism that makes those NULLs visible**, and it fires one layer earlier than the NULLs themselves. That is why it must keep failing: silencing it would restore the pre-task-030 situation in which a non-mass unit was invisible. It is advisory by design — promoting it to `BLOCKING_CHECKS` would halt the pipeline on the first exotic unit, which is a separate decision (see the in-notebook rationale on Check 7).

### 7.3 `data_type_consistency = 75.00` on `silver_procurement` — accepted

**Measured schema** (Delta types, exactly as `spark.table(...).schema` reports them):

| Column | Expected by the check | **Actual** | Conforms |
|---|---|---|---|
| `date` | `date` | `date` | ✅ |
| `materialname` | `string` | `string` | ✅ |
| `suppliername` | `string` | `string` | ✅ |
| `unit` | `string` | `string` | ✅ |
| `headquarterscountry` | `string` | `string` | ✅ |
| `productioncountry` | `string` | `string` | ✅ |
| `quantity` | `decimal` | **`short`** | ❌ |
| `unitpriceeur` | `decimal` | **`double`** | ❌ |

6 of 8 conform → score `= 6/8 × 100 = 75.00`. Both columns **exist**, so this is a type mismatch, not the `column missing` branch.

**Root cause — the expectation was never true at any layer.** `decimal` appears nowhere in the chain:

| Layer | `quantity` | price / spend |
|---|---|---|
| `bronze_procurement_transactional` (from Azure SQL via Copy activity) | `short` | `UnitPriceEUR double` |
| `silver_procurement` | `short` | `unitpriceeur double` |
| `fact_procurement` | `quantity_base double` | `unitprice_eur double`, `spend_eur double` |

`bronze_to_silver` applies **no cast** to these columns — it joins the two bronze tables, lowercases column names and replaces spaces with underscores, and drops `region`. Silver therefore inherits Azure SQL's types verbatim. The check's expectation of `decimal` describes an *intent* that no layer implements, and its own docstring compounded this by citing "DECIMAL bronze quantity" — bronze `Quantity` is `short`, and never was DECIMAL. (That docstring is corrected as of 2026-08-06.)

**Two real sub-findings, recorded rather than fixed:**

1. **`unitpriceeur` carries float32-widening noise.** 124 of 132 values have more than two decimal places — e.g. `17.309999465942383` for an intended `17.31`, `1.350000023841858` for `1.35`. The magnitudes are exactly what a REAL/`float32` source column widened to `float64` produces. Because `spend_eur = quantity × unitpriceeur`, that noise propagates into gold and into `Total Spend EUR`. At 132 rows the absolute error is sub-cent, but storing money as a float is a genuine anti-pattern rather than a cosmetic one.
2. **`quantity` is 16-bit.** `short` caps at 32,767. Observed range is 108 → 3,293, so headroom is ~29,000 — no current overflow, but a single order of 33,000+ units would silently exceed the type.

**Why accepted (decision, 2026-08-06).** Fixing the types is not a cast edit — it is a three-layer schema migration on a live, scheduled, fully-verified pipeline:

- The default write path is the incremental delete-insert ending in `mode("append")`. **An append whose DataFrame schema differs from the table's is rejected**, and that failure writes a `FAILED` watermark row and re-raises — halting the pipeline. So the change requires `.option("overwriteSchema","true")` on the full-load branch *plus* one `p_full_load = true` run to re-establish the schema before incrementals resume.
- It propagates: decimal inputs make `fact_procurement.spend_eur` decimal, changing the **gold** schema and the DirectLake semantic model's column types (TMDL).

Weighed against sub-cent precision noise on a 132-row synthetic dataset, that migration was judged the wrong trade at this point in the project. **The check is left failing on purpose** — it is the standing, visible record of the divergence, and the expectation was *not* relabelled to `short`/`double`, because an expectation edited to match whatever exists is a tautology that carries no information.

**Migration path, if it is ever wanted** (in order):

1. Decide the intended contract per column — `unitpriceeur → decimal(18,2)` is unambiguous for money; `quantity` is a count, so `integer` is arguably more correct than `decimal`, and the check's expectation should be updated to whatever is *decided* rather than to what is *observed*.
2. Add the casts in `bronze_to_silver` immediately after the rename/drop step, and `.option("overwriteSchema","true")` to the full-load write.
3. Run once with `p_full_load = true` (lossless here — bronze is a full copy every run, and silver full-load reads all of bronze).
4. Verify `fact_procurement`'s resulting types and update the TMDL column types if they shifted.
5. Confirm `data_type_consistency` reaches 100.0 for the *right* reason, and that `Total Spend EUR` changes only by the recovered precision.

### 7.4 Why the mismatch list is not in `gold_quality_history`

`log_check_result` accepts a `details` string, and both checks above populate it with exactly the diagnostic a reader wants — `data_type_consistency` builds `f"Type mismatches: {mismatches}"` naming each offending column, and `business_rule_validation` builds `f"{n}/{m} rules violated: {names}"`. **`details` is then dropped at the persistence boundary:** the appended tuple maps onto the nine live `gold_quality_history` columns — `refresh_timestamp, layer, entity, metric_name, metric_value, threshold, breach_flag, status, producer` — and there is no `details` column among them.

> Note the column is **`entity`**, not `table_name`. The notebook's local variable is `table_name` and it is written into the `entity` column, so a query built from the notebook's variable names will reference a column that does not exist.

So the explanation of every failure exists, is computed on every run, is printed to the notebook's console output, and is discarded. **That is the structural reason these three checks went undocumented for as long as they did**, and it is why diagnosing them required reading the Delta log directly rather than querying the quality table.

Until that is addressed, the mismatch list for a given run is recoverable only from the `data_quality_checks` notebook's cell output in that pipeline run's snapshot. Adding a nullable `details` column would make future failures self-documenting, and `ensure_quality_history_columns()` already establishes the safe idempotent `ALTER TABLE … ADD COLUMNS` pattern for exactly this kind of additive change (task-040 used it twice).

---

**Document Status:** Implemented and running in production. The `data_quality_checks`
notebook executes on every pipeline run — including the daily 06:00 Europe/Stockholm
schedule — and persists per-check scores to `gold_quality_history`. Sections 1–6 are the
original design; § 7 records the measured behaviour of the built system.
**Next Steps:** § 7.4 (`details` is computed but not persisted) is the one open
improvement identified against the running implementation.

---

## Summary: 14 Quality Checks

**Bronze (5):** Row count, Schema validation, Required fields, Duplicates, Date range validation
**Silver (5):** Referential integrity, Business rules, Outlier detection (Z-score), Data type consistency, Completeness (post-join)
**Gold (4):** Aggregate reconciliation, Trend validation, Lookup-name uniqueness, Duplicate-grain on facts

> The earlier "9 Core Quality Checks / Bronze (4) / Silver (3) / Gold (2)" summary predated
> the task-020 and task-026 additions and was corrected 2026-08-06. Counts here match the
> `data_quality_checks` notebook header, which is the authority. Three of these 14 record a
> non-`pass` row on every run by design — see § 7.

**Quality Dimensions (6):** Completeness, Accuracy, Consistency, Timeliness, Validity, Uniqueness

**Scoring:** Weighted average of dimensions → Overall table score (0-100) → Quality rating (Excellent/Good/Fair/Poor/Critical)
