# Validate Table Schemas

Verify that table schemas match expected definitions across bronze, silver, and gold layers.

## What This Command Does

This command validates:
- Column names and data types
- Required columns are present
- No unexpected schema changes (schema drift)
- Consistency across layers (bronze → silver → gold)

## Prerequisites

- Tables exist in lakehouse `oem_lh`
- Reference schemas documented (see `/.claude/support/documents/schemas/`)

## Quick Schema Validation

```python
from pyspark.sql import SparkSession
from pyspark.sql.types import *

def validate_schema(table_name, expected_columns):
    """
    Validate table schema against expected column definitions.

    Args:
        table_name: Full table name (e.g., "oem_lh.bronze_procurement_transactional")
        expected_columns: Dict of {column_name: expected_data_type_string}

    Returns:
        Tuple of (is_valid, issues_list)
    """
    try:
        df = spark.table(table_name)
        actual_schema = {field.name: str(field.dataType) for field in df.schema.fields}

        issues = []

        # Check for missing columns
        missing_cols = set(expected_columns.keys()) - set(actual_schema.keys())
        if missing_cols:
            issues.append(f"Missing columns: {', '.join(missing_cols)}")

        # Check for unexpected columns
        extra_cols = set(actual_schema.keys()) - set(expected_columns.keys())
        if extra_cols:
            issues.append(f"Unexpected columns: {', '.join(extra_cols)}")

        # Check data types
        for col, expected_type in expected_columns.items():
            if col in actual_schema:
                actual_type = actual_schema[col]
                if actual_type != expected_type:
                    issues.append(f"Column '{col}': expected {expected_type}, got {actual_type}")

        is_valid = len(issues) == 0
        return is_valid, issues

    except Exception as e:
        return False, [f"Error accessing table: {str(e)}"]

# Bronze Layer Validation
print("=" * 80)
print("BRONZE LAYER SCHEMA VALIDATION")
print("=" * 80)

# Bronze Procurement Transactional
bronze_procurement_expected = {
    "Date": "DateType()",
    "MaterialName": "StringType()",
    "SupplierName": "StringType()",
    "Region": "StringType()",
    "Quantity": "DecimalType(18,2)",
    "Unit": "StringType()",
    "UnitPriceEUR": "DecimalType(18,2)"
}

is_valid, issues = validate_schema("oem_lh.bronze_procurement_transactional", bronze_procurement_expected)
print(f"\n✓ bronze_procurement_transactional: {'PASS' if is_valid else 'FAIL'}")
if issues:
    for issue in issues:
        print(f"  - {issue}")

# Bronze Supplier Ref
bronze_supplier_expected = {
    "SupplierName": "StringType()",
    "HeadquartersCountry": "StringType()",
    "ProductionCountry": "StringType()",
    "Region": "StringType()"
}

is_valid, issues = validate_schema("oem_lh.bronze_supplier_ref", bronze_supplier_expected)
print(f"\n✓ bronze_supplier_ref: {'PASS' if is_valid else 'FAIL'}")
if issues:
    for issue in issues:
        print(f"  - {issue}")

# Bronze EPI
bronze_epi_expected = {
    "code": "IntegerType()",
    "iso": "StringType()",
    "country": "StringType()",
    "EPI": "DoubleType()"
    # Note: ~30+ additional indicator columns not listed here
}

is_valid, issues = validate_schema("oem_lh.bronze_epi2024results", bronze_epi_expected)
print(f"\n✓ bronze_epi2024results: {'PASS' if is_valid else 'FAIL'}")
if issues:
    for issue in issues:
        print(f"  - {issue}")

# Silver Layer Validation
print("\n" + "=" * 80)
print("SILVER LAYER SCHEMA VALIDATION")
print("=" * 80)

# Silver Procurement
silver_procurement_expected = {
    "date": "DateType()",
    "materialname": "StringType()",
    "quantity": "DecimalType(18,2)",
    "unit": "StringType()",
    "unitpriceeur": "DecimalType(18,2)",
    "headquarterscountry": "StringType()",
    "productioncountry": "StringType()"
}

is_valid, issues = validate_schema("oem_lh.silver_procurement", silver_procurement_expected)
print(f"\n✓ silver_procurement: {'PASS' if is_valid else 'FAIL'}")
if issues:
    for issue in issues:
        print(f"  - {issue}")

# Silver EPI
silver_epi_expected = {
    "code": "IntegerType()",
    "iso": "StringType()",
    "country": "StringType()",
    "EPI": "DoubleType()"
}

is_valid, issues = validate_schema("oem_lh.silver_epi2024results", silver_epi_expected)
print(f"\n✓ silver_epi2024results: {'PASS' if is_valid else 'FAIL'}")
if issues:
    for issue in issues:
        print(f"  - {issue}")

# Gold Layer Validation
print("\n" + "=" * 80)
print("GOLD LAYER SCHEMA VALIDATION")
print("=" * 80)

# Fact Procurement
fact_procurement_expected = {
    "date_key": "IntegerType()",
    "material_key": "LongType()",
    "supplier_hq_country_key": "LongType()",
    "production_country_key": "LongType()",
    "quantity_base": "DoubleType()",
    "unitprice_eur": "DoubleType()",
    "spend_eur": "DoubleType()",
    "data_quality_score": "DoubleType()",
    "quality_category": "StringType()"
}

is_valid, issues = validate_schema("oem_lh.fact_procurement", fact_procurement_expected)
print(f"\n✓ fact_procurement: {'PASS' if is_valid else 'FAIL'}")
if issues:
    for issue in issues:
        print(f"  - {issue}")

# Gold Dim Country
dim_country_expected = {
    "country_key": "LongType()",
    "iso3": "StringType()",
    "iso_numeric": "IntegerType()",
    "wb_code": "StringType()",
    "country_name_std": "StringType()",
    "region": "StringType()",
    "is_placeholder": "BooleanType()"
}

is_valid, issues = validate_schema("oem_lh.gold_dim_country", dim_country_expected)
print(f"\n✓ gold_dim_country: {'PASS' if is_valid else 'FAIL'}")
if issues:
    for issue in issues:
        print(f"  - {issue}")

# Gold Dim Material
dim_material_expected = {
    "material_key": "LongType()",
    "material_name_std": "StringType()",
    "commodity_group": "StringType()",
    "unit_base": "StringType()",
    "is_placeholder": "BooleanType()"
}

is_valid, issues = validate_schema("oem_lh.gold_dim_material", dim_material_expected)
print(f"\n✓ gold_dim_material: {'PASS' if is_valid else 'FAIL'}")
if issues:
    for issue in issues:
        print(f"  - {issue}")

# Gold Dim Date
dim_date_expected = {
    "date_key": "IntegerType()",
    "date": "DateType()",
    "year": "IntegerType()",
    "month": "IntegerType()",
    "day": "IntegerType()",
    "month_name": "StringType()",
    "quarter": "IntegerType()",
    "day_of_week": "IntegerType()",
    "week_of_year": "IntegerType()"
}

is_valid, issues = validate_schema("oem_lh.gold_dim_date", dim_date_expected)
print(f"\n✓ gold_dim_date: {'PASS' if is_valid else 'FAIL'}")
if issues:
    for issue in issues:
        print(f"  - {issue}")
```

## Detailed Schema Inspection

View complete schema for any table:

```python
def print_schema_details(table_name):
    """Print detailed schema information for a table."""
    df = spark.table(table_name)

    print(f"\n{'=' * 80}")
    print(f"Schema Details: {table_name}")
    print(f"{'=' * 80}\n")

    print(f"Total Columns: {len(df.columns)}")
    print(f"Total Rows: {df.count():,}\n")

    print(f"{'Column Name':<40} {'Data Type':<30} {'Nullable':<10}")
    print("-" * 80)

    for field in df.schema.fields:
        print(f"{field.name:<40} {str(field.dataType):<30} {str(field.nullable):<10}")

    # Sample first 5 rows
    print(f"\n{'Sample Data (first 5 rows)':^80}")
    print("-" * 80)
    df.limit(5).show(truncate=False)

# Example usage:
print_schema_details("oem_lh.fact_procurement")
print_schema_details("oem_lh.gold_dim_country")
```

## Schema Drift Detection

Compare current schema to previous version (if schema history is tracked):

```python
def detect_schema_drift(table_name, baseline_schema):
    """
    Detect schema changes since baseline.

    Args:
        table_name: Table to check
        baseline_schema: Dict of {column_name: data_type} from previous version
    """
    current_df = spark.table(table_name)
    current_schema = {field.name: str(field.dataType) for field in current_df.schema.fields}

    print(f"\nSchema Drift Report: {table_name}")
    print("-" * 80)

    # Added columns
    added_cols = set(current_schema.keys()) - set(baseline_schema.keys())
    if added_cols:
        print(f"\n✓ Added Columns ({len(added_cols)}):")
        for col in added_cols:
            print(f"  + {col} ({current_schema[col]})")

    # Removed columns
    removed_cols = set(baseline_schema.keys()) - set(current_schema.keys())
    if removed_cols:
        print(f"\n✗ Removed Columns ({len(removed_cols)}):")
        for col in removed_cols:
            print(f"  - {col} ({baseline_schema[col]})")

    # Type changes
    type_changes = []
    for col in set(current_schema.keys()) & set(baseline_schema.keys()):
        if current_schema[col] != baseline_schema[col]:
            type_changes.append((col, baseline_schema[col], current_schema[col]))

    if type_changes:
        print(f"\n⚠ Type Changes ({len(type_changes)}):")
        for col, old_type, new_type in type_changes:
            print(f"  ~ {col}: {old_type} → {new_type}")

    if not added_cols and not removed_cols and not type_changes:
        print("\n✓ No schema drift detected.")
```

## Export Schemas for Documentation

Save current schemas to reference documentation:

```python
import json
from datetime import datetime

def export_schema_to_json(table_name, output_path):
    """Export table schema to JSON for documentation."""
    df = spark.table(table_name)

    schema_dict = {
        "table_name": table_name,
        "exported_at": datetime.now().isoformat(),
        "row_count": df.count(),
        "columns": [
            {
                "name": field.name,
                "type": str(field.dataType),
                "nullable": field.nullable
            }
            for field in df.schema.fields
        ]
    }

    # In a real implementation, write to Files section of lakehouse
    # For now, just print
    print(json.dumps(schema_dict, indent=2))

    return schema_dict

# Export all key table schemas
tables_to_export = [
    "oem_lh.fact_procurement",
    "oem_lh.fact_supply_share",
    "oem_lh.fact_epi_score",
    "oem_lh.gold_dim_country",
    "oem_lh.gold_dim_material",
    "oem_lh.gold_dim_date",
    "oem_lh.gold_dim_indicator",
    "oem_lh.gold_dim_stage"
]

for table in tables_to_export:
    export_schema_to_json(table, f"Files/schema_exports/{table.split('.')[-1]}.json")
```

## Common Schema Issues

**Issue: Column Not Found**
- Symptom: Error when querying expected column
- Cause: Bronze/silver transformation didn't create column
- Fix: Review transformation notebook, verify source data

**Issue: Type Mismatch**
- Symptom: Cannot cast value to expected type
- Cause: Source data changed format, or casting failed
- Fix: Update transformation with proper type conversion

**Issue: Unexpected Nulls**
- Symptom: Key columns have null values
- Cause: Join failure, missing source data
- Fix: Review join logic, check data quality in bronze layer

**Issue: Column Name Case Sensitivity**
- Symptom: Schema validation fails on column names
- Cause: Spark is case-insensitive by default, but checks are case-sensitive
- Fix: Ensure consistent naming (all lowercase in silver/gold)

## Next Steps

- If schemas valid: Proceed with confidence
- If issues found: Review transformation notebooks
- If drift detected: Update reference documentation and transformations
- Document baseline schemas: See `/.claude/support/documents/schemas/`

## Related Files

- `/.claude/support/documents/schemas/bronze_tables.md`
- `/.claude/support/documents/schemas/silver_tables.md`
- `/.claude/support/documents/schemas/gold_tables.md`
- `/fabric/bronze-to-silver.Notebook/` - Silver transformations
- `/fabric/silver-to-gold2.Notebook/` - Gold transformations
