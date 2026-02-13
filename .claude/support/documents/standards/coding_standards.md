# Coding Standards - Python/PySpark

## General Principles
- **Readability:** Code is read more than written
- **Simplicity:** Prefer simple over clever
- **Consistency:** Follow established patterns
- **Documentation:** Comment why, not what

## Python Style

### PEP 8 Compliance
- Indentation: 4 spaces (no tabs)
- Line length: 88 characters (Black formatter default)
- Imports: Standard library, third-party, local (separated by blank lines)

### Example
```python
from datetime import datetime
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, sum as _sum

def calculate_spend(quantity, unit_price):
    """Calculate total spend in EUR."""
    return quantity * unit_price
```

## PySpark Best Practices

### 1. Avoid Collecting Large DataFrames
```python
✗ Bad:
all_data = df.collect()  # Loads entire DataFrame to driver
for row in all_data:
    process(row)

✓ Good:
df.foreach(lambda row: process(row))  # Distributed processing
```

### 2. Use Column Objects, Not Strings
```python
✗ Bad:
df.filter("spend_eur > 1000")

✓ Good:
df.filter(col("spend_eur") > 1000)
```

### 3. Cache Intermediate Results
```python
✓ Good:
silver_df = spark.table("silver_procurement").cache()
# Use silver_df multiple times
```

### 4. Broadcast Small Dimensions
```python
from pyspark.sql.functions import broadcast

fact_df.join(broadcast(small_dim_df), "key")
```

## Function Documentation

### Docstring Format (Google Style)
```python
def stable_key(*cols):
    """Generate deterministic surrogate key via xxhash64.
    
    Args:
        *cols: Columns to hash (usually natural key)
    
    Returns:
        Column with BIGINT hash value
    
    Example:
        >>> df.withColumn("country_key", stable_key(col("iso3")))
    """
    return xxhash64(concat_ws("||", *cols))
```

## Error Handling

### Use Try-Except for Known Failures
```python
try:
    df = spark.table("oem_lh.silver_procurement")
except Exception as e:
    log_error(f"Table not found: {str(e)}")
    raise
```

### Validate Inputs
```python
def normalize_unit(quantity, unit):
    """Normalize quantity to kg."""
    if unit not in ["kg", "g", "mg", "t"]:
        raise ValueError(f"Unknown unit: {unit}")
    # ... conversion logic
```

## Data Quality Patterns

### Check for Nulls
```python
null_count = df.filter(col("key_field").isNull()).count()
if null_count > 0:
    log_warning(f"Found {null_count} null values in key_field")
```

### Log Unmapped Values
```python
unmapped_df = df.filter(col("country_key").isNull())
if unmapped_df.count() > 0:
    unmapped_df.write.mode("append").saveAsTable("gold_unmapped_audit")
```

## Performance Patterns

### Predicate Pushdown
```python
✓ Good: Filter early
df = spark.table("fact_procurement").filter(col("year") == 2024)
```

### Minimize Shuffles
```python
✓ Good: Use repartition wisely
df.repartition("date_key").write.partitionBy("year", "month").saveAsTable(...)
```

## Notebook Organization

### Structure
```
Cell 1: Imports and configuration
Cell 2: Read source tables
Cell 3-N: Transformation steps (one logical step per cell)
Cell N+1: Write output tables
Cell N+2: Validation checks
```

### Cell Comments
```python
# ==================================================
# STEP 1: Load Bronze Tables
# ==================================================
bronze_proc = spark.table("oem_lh.bronze_procurement")
```

## SQL Standards (for Spark SQL)

### Formatting
```sql
-- Clear indentation
SELECT
    date_key,
    material_key,
    SUM(spend_eur) AS total_spend
FROM oem_lh.fact_procurement
WHERE date_key >= 20240101
GROUP BY date_key, material_key
ORDER BY total_spend DESC
```

### Table References
```sql
-- Always use fully qualified names
SELECT * FROM oem_lh.gold_dim_country  -- ✓ Good
SELECT * FROM gold_dim_country          -- ✗ Bad (ambiguous)
```

## Testing (Planned - Task 08)

### Unit Test Pattern
```python
import pytest

def test_stable_key_consistency():
    """Test surrogate key generation is deterministic."""
    key1 = stable_key(lit("USA"))
    key2 = stable_key(lit("USA"))
    assert key1 == key2
```

## Code Review Checklist
- [ ] Follows naming standards
- [ ] Has docstrings for functions
- [ ] No hardcoded values (use config)
- [ ] Error handling in place
- [ ] Data quality checks added
- [ ] Performance considerations (caching, broadcast)
- [ ] Git commit message clear
