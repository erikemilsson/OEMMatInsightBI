# Review Transformation Logic

Review and analyze data transformation logic across bronze, silver, and gold layers.

## What This Command Does

This command helps you understand and review the transformation logic in the medallion architecture:
- **Bronze → Silver:** Data cleaning, standardization, type conversions
- **Silver → Gold:** Business logic, dimensional modeling, surrogate keys
- Key functions and their purposes
- Data quality rules and validations
- Transformation patterns and best practices

## Prerequisites

- Notebook files accessible in `/fabric` directory
- Basic understanding of PySpark and medallion architecture

## Review Bronze → Silver Transformations

### Notebook: `clean_columnsAndHeaders.Notebook`

**Purpose:** Standardize and clean raw bronze data

**Location:** `/fabric/clean_columnsAndHeaders.Notebook/notebook-content.py`

#### Key Transformations:

**1. EPI Data Cleaning**
```python
# Read bronze EPI data
bronze_epi = spark.read.table("oem_lh.bronze_epi2024results")

# Transformation Logic:
# - Drop columns ending with '.old' (legacy columns)
# - Remove '.new' suffix from column names
# - Cast 'code' to INTEGER type
# - Select only: code, iso, country, EPI + indicator columns

# Implementation:
old_cols = [col for col in bronze_epi.columns if col.endswith('.old')]
bronze_epi = bronze_epi.drop(*old_cols)

# Rename columns (remove .new suffix)
for col in bronze_epi.columns:
    if col.endswith('.new'):
        bronze_epi = bronze_epi.withColumnRenamed(col, col.replace('.new', ''))

# Cast types
bronze_epi = bronze_epi.withColumn("code", col("code").cast(IntegerType()))

# Write to silver
silver_epi = bronze_epi.select("code", "iso", "country", "EPI", ...)
silver_epi.write.mode("overwrite").saveAsTable("oem_lh.silver_epi2024results")
```

**Review Points:**
- Why drop `.old` columns? (Legacy data cleanup)
- Is hardcoded column selection brittle? (Yes - breaks if new indicators added)
- Could this be more dynamic? (Yes - use pattern matching)

**2. Global Supply Shares Cleaning**
```python
# Read bronze supply shares
bronze_supply = spark.read.table("oem_lh.bronze_GlobalSupplyShares")

# Transformation Logic:
# - Convert headers to lowercase
# - Replace spaces with underscores
# - Drop unused 't' column

# Implementation:
def clean_column_name(col_name):
    return col_name.lower().replace(' ', '_')

silver_supply = bronze_supply.select([
    col(c).alias(clean_column_name(c))
    for c in bronze_supply.columns if c != 't'
])

silver_supply.write.mode("overwrite").saveAsTable("oem_lh.silver_globalsupplyshares")
```

**Review Points:**
- Why lowercase? (SQL compatibility, consistency)
- Why drop 't' column? (Unused in analysis, no documentation)
- Is column renaming logged? (No - could add logging)

**3. World Bank WGI Unpivoting**
```python
# Read bronze WGI data (wide format with y_2000, y_2001, ... columns)
bronze_wgi = spark.read.table("oem_lh.bronze_WB_ESGCSV")
bronze_series = spark.read.table("oem_lh.bronze_WB_ESGSeries")

# Transformation Logic:
# - Unpivot year columns (y_YYYY) to long format
# - Remove 'y_' prefix from year values
# - Filter for year 2020 only
# - Join with ESGSeries for topic metadata
# - Cast scores to DOUBLE, filter to 0-100 range

# Implementation:
year_cols = [c for c in bronze_wgi.columns if c.startswith('y_')]
wgi_unpivoted = bronze_wgi.select(
    "Country Name", "Country Code", "Indicator Name", "Indicator Code",
    expr(f"stack({len(year_cols)}, {', '.join([f\"'{c}', {c}\" for c in year_cols])}) as (year, score)")
)

# Remove 'y_' prefix and filter
wgi_unpivoted = wgi_unpivoted.withColumn("year", regexp_replace("year", "y_", ""))
wgi_2020 = wgi_unpivoted.filter(col("year") == "2020")

# Join with metadata
silver_wgi = wgi_2020.join(bronze_series, "Indicator Code", "left")

# Cast and filter
silver_wgi = silver_wgi.withColumn("score", col("score").cast(DoubleType()))
silver_wgi = silver_wgi.filter((col("score") >= 0) & (col("score") <= 100))

silver_wgi.write.mode("overwrite").saveAsTable("oem_lh.silver_WB")
```

**Review Points:**
- Why unpivot? (Enables time-series analysis, normalizes data)
- Why filter to 2020 only? (Most recent complete dataset at time of design)
- Is hardcoded year flexible? (No - should be parameter)
- Why 0-100 filter? (Data quality - removes invalid values)

**4. Procurement + Supplier Join**
```python
# Read bronze procurement and supplier reference
bronze_proc = spark.read.table("oem_lh.bronze_procurement_transactional")
bronze_supplier = spark.read.table("oem_lh.bronze_supplier_ref")

# Transformation Logic:
# - Left join procurement with supplier ref on SupplierName
# - Clean column names (lowercase, underscores)
# - Drop duplicate columns (region, suppliername from supplier_ref)

# Implementation:
silver_proc = bronze_proc.alias("p").join(
    bronze_supplier.alias("s"),
    col("p.SupplierName") == col("s.SupplierName"),
    "left"
)

# Select and rename
silver_proc = silver_proc.select(
    col("p.Date").alias("date"),
    col("p.MaterialName").alias("materialname"),
    col("p.Quantity").alias("quantity"),
    col("p.Unit").alias("unit"),
    col("p.UnitPriceEUR").alias("unitpriceeur"),
    col("s.HeadquartersCountry").alias("headquarterscountry"),
    col("s.ProductionCountry").alias("productioncountry")
)

silver_proc.write.mode("overwrite").saveAsTable("oem_lh.silver_procurement")
```

**Review Points:**
- Why left join? (Keep all procurement records even if supplier not in ref table)
- What happens to unmatched suppliers? (HQ/production country will be NULL)
- Should this be inner join? (No - would lose data)
- Is NULL handling needed? (Yes - handled in gold layer with "Unknown" placeholder)

## Review Silver → Gold Transformations

### Notebook: `silver-to-gold2.Notebook`

**Purpose:** Create business-ready star schema with dimensional modeling

**Location:** `/fabric/silver-to-gold2.Notebook/notebook-content.py`

#### Key Functions:

**1. Surrogate Key Generation**
```python
from pyspark.sql.functions import xxhash64, concat_ws

def stable_key(*cols):
    """
    Generate deterministic 64-bit surrogate key using xxhash64.

    Args:
        *cols: Columns to hash (usually natural key columns)

    Returns:
        Column with BIGINT hash value

    Example:
        df.withColumn("country_key", stable_key(col("iso3")))
    """
    return xxhash64(concat_ws("||", *cols))
```

**Review Points:**
- Why xxhash64? (Fast, deterministic, good distribution)
- Why concatenate with ||? (Separator prevents collisions: "A"+"BC" vs "AB"+"C")
- Is 64-bit sufficient? (Yes - ~18 quintillion unique values)
- Could this produce collisions? (Extremely rare, but theoretically possible)

**2. Unit Normalization**
```python
def normalize_to_kg(quantity, unit):
    """
    Normalize quantity to base unit (kg).

    Conversion factors:
    - kg: 1.0
    - g: 0.001
    - mg: 0.000001
    - t (tonne): 1000.0

    Args:
        quantity: Quantity column
        unit: Unit column (string)

    Returns:
        Normalized quantity in kg
    """
    return when(lower(col(unit)) == "kg", col(quantity)) \
           .when(lower(col(unit)) == "g", col(quantity) * 0.001) \
           .when(lower(col(unit)) == "mg", col(quantity) * 0.000001) \
           .when(lower(col(unit)) == "t", col(quantity) * 1000.0) \
           .otherwise(col(quantity))  # Assume kg if unknown
```

**Review Points:**
- Why kg as base unit? (International standard, most common)
- What if unit is NULL? (Defaults to kg - could be risky)
- Should log unknown units? (Yes - add to data quality checks)
- Are there other units to handle? (Possibly: lb, oz - not in current data)

**3. Alias Resolution**
```python
# Country alias lookup (simplified example)
country_aliases = {
    "USA": ("United States of America", 1.0),
    "US": ("United States of America", 1.0),
    "United States": ("United States of America", 0.95),
    "UK": ("United Kingdom", 1.0),
    "GB": ("United Kingdom", 1.0),
    "Türkiye": ("Turkey", 0.80),  # Encoding variant
    "Hong Kong": ("China", 0.85)   # Territory mapping
}

def resolve_country_alias(country_name):
    """
    Resolve country name to standard name with confidence score.

    Returns:
        Tuple of (standard_name, confidence_score)
    """
    if country_name in country_aliases:
        return country_aliases[country_name]
    else:
        return (country_name, 1.0)  # Assume exact match

# Apply to dataframe
df = df.withColumn("match_result", resolve_country_alias(col("country_raw")))
df = df.withColumn("country_name_std", col("match_result")[0])
df = df.withColumn("country_confidence", col("match_result")[1])
```

**Review Points:**
- Why tiered confidence scores? (Reflects match quality for data quality tracking)
- Is hardcoded dictionary maintainable? (No - should be lookup table)
- What if multiple aliases map to same standard name? (Intended - that's the point)
- How to add new aliases? (Currently: edit notebook, redeploy - should be data-driven)

**4. Data Quality Scoring**
```python
def calculate_quality_score(material_conf, hq_country_conf, prod_country_conf):
    """
    Calculate overall data quality score as average of match confidences.

    Args:
        material_conf: Material match confidence (0-1)
        hq_country_conf: HQ country match confidence (0-1)
        prod_country_conf: Production country match confidence (0-1)

    Returns:
        Average confidence score (0-1)
    """
    return (material_conf + hq_country_conf + prod_country_conf) / 3.0

def categorize_quality(score):
    """
    Categorize quality score into bands.

    Bands:
    - High: 0.90-1.00
    - Medium: 0.70-0.89
    - Low: 0.50-0.69
    - Unmapped: 0.00
    """
    return when(col(score) >= 0.90, "High") \
           .when(col(score) >= 0.70, "Medium") \
           .when(col(score) >= 0.50, "Low") \
           .otherwise("Unmapped")
```

**Review Points:**
- Why simple average? (Easy to understand, treats all dimensions equally)
- Should dimensions be weighted? (Possibly - material might be more critical)
- Is 0.90 threshold for "High" appropriate? (Subjective - could be configured)
- Are categories useful for reporting? (Yes - enables filtering by quality)

## Transformation Patterns

### Pattern 1: Medallion Architecture
```
Bronze (Raw) → Clean → Silver (Validated) → Transform → Gold (Business-Ready)
```

### Pattern 2: Type 1 SCD (Slowly Changing Dimension)
```python
# Dimensions are overwritten (no history)
dimension.write.mode("overwrite").saveAsTable("gold_dim_country")
```

### Pattern 3: Placeholder Dimensions
```python
# For unmapped values, assign to placeholder dimension
if country_not_found:
    country_key = unknown_country_key  # -1 or hash of "Unknown - Global"
    is_placeholder = True
```

### Pattern 4: Audit Trail
```python
# Log unmapped values for review
unmapped_audit = df.filter(col("country_key").isNull()).select(
    "source_value", "unmapped_field", "spend_impact"
)
unmapped_audit.write.mode("append").saveAsTable("gold_unmapped_audit")
```

## Review Checklist

When reviewing transformations, ask:

**Correctness:**
- [ ] Does logic match business requirements?
- [ ] Are edge cases handled (nulls, zeros, invalid values)?
- [ ] Are data types appropriate?
- [ ] Are joins using correct keys and types?

**Performance:**
- [ ] Are transformations efficient (avoid cartesian joins)?
- [ ] Is caching used appropriately?
- [ ] Are broadcast joins used for small dimensions?
- [ ] Is partitioning strategy optimal?

**Maintainability:**
- [ ] Is code readable and well-commented?
- [ ] Are magic numbers explained (e.g., confidence thresholds)?
- [ ] Are hardcoded values in configuration?
- [ ] Is logic modular and reusable?

**Data Quality:**
- [ ] Are quality checks in place?
- [ ] Are unmapped values logged?
- [ ] Is data loss tracked (input vs output row counts)?
- [ ] Are assumptions documented?

## Next Steps

After reviewing transformations:
1. Document findings in project notes
2. Identify improvement opportunities
3. Create tasks for enhancements (e.g., Task 06: Incremental Load)
4. Test transformations with edge cases
5. Optimize performance bottlenecks

## Related Files

- `/fabric/clean_columnsAndHeaders.Notebook/` - Bronze → Silver
- `/fabric/silver-to-gold2.Notebook/` - Silver → Gold
- `/.claude/context/architecture/medallion_architecture.md`
- `/.claude/reference/transformations/` - Transformation documentation
- `/.claude/tasks/08_create_unit_tests.md` - Add tests for transformations
