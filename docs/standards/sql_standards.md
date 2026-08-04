# SQL Standards - OEMMatInsightBI

## General SQL Style

### Formatting
- **Keywords:** UPPERCASE
- **Table/Column names:** lowercase_with_underscores
- **Indentation:** 4 spaces
- **Line breaks:** One clause per line for readability

### Example
```sql
SELECT
    date_key,
    material_name_std,
    SUM(spend_eur) AS total_spend,
    COUNT(*) AS transaction_count
FROM oem_lh.fact_procurement fp
INNER JOIN oem_lh.gold_dim_material m
    ON fp.material_key = m.material_key
WHERE date_key >= 20240101
GROUP BY date_key, material_name_std
ORDER BY total_spend DESC
LIMIT 100;
```

## Naming Conventions

### Tables
```sql
-- Always use fully qualified names
SELECT * FROM oem_lh.fact_procurement  -- ✓ Good
SELECT * FROM fact_procurement          -- ✗ Bad
```

### Aliases
```sql
-- Use meaningful abbreviations
FROM fact_procurement fp            -- ✓ Good
FROM gold_dim_country c             -- ✓ Good
FROM fact_procurement x             -- ✗ Bad (meaningless)
```

### Columns
```sql
-- Prefix calculated columns clearly
SUM(spend_eur) AS total_spend      -- ✓ Good
AVG(score) AS avg_epi_score        -- ✓ Good
COUNT(*) AS cnt                    -- ✗ Bad (unclear abbreviation)
```

## Query Patterns

### Select Statements
```sql
-- Order clauses consistently
SELECT [columns]
FROM [table]
[JOIN clauses]
WHERE [conditions]
GROUP BY [columns]
HAVING [conditions]
ORDER BY [columns]
LIMIT [number];
```

### Joins
```sql
-- Explicit JOIN syntax (not implicit)
✓ Good:
SELECT *
FROM fact_procurement fp
INNER JOIN gold_dim_country c
    ON fp.supplier_hq_country_key = c.country_key

✗ Bad:
SELECT *
FROM fact_procurement fp, gold_dim_country c
WHERE fp.supplier_hq_country_key = c.country_key
```

### Subqueries
```sql
-- Use CTEs for readability
WITH high_spend_materials AS (
    SELECT material_key, SUM(spend_eur) AS total
    FROM fact_procurement
    GROUP BY material_key
    HAVING SUM(spend_eur) > 100000
)
SELECT m.material_name_std, hsm.total
FROM high_spend_materials hsm
JOIN gold_dim_material m ON hsm.material_key = m.material_key;
```

## Delta Lake Operations

### Create Table
```sql
CREATE TABLE oem_lh.fact_procurement (
    date_key INT,
    material_key BIGINT,
    spend_eur DOUBLE
)
USING DELTA
PARTITIONED BY (year, month);
```

### Merge (Upsert)
```sql
MERGE INTO oem_lh.gold_dim_country target
USING new_countries source
ON target.country_key = source.country_key
WHEN MATCHED THEN
    UPDATE SET *
WHEN NOT MATCHED THEN
    INSERT *;
```

### Optimize
```sql
OPTIMIZE oem_lh.fact_procurement ZORDER BY (material_key);
OPTIMIZE oem_lh.fact_procurement VORDER;
```

## Data Quality Queries

### Check for Nulls
```sql
SELECT COUNT(*) AS null_count
FROM oem_lh.fact_procurement
WHERE material_key IS NULL
   OR date_key IS NULL;
```

### Find Duplicates
```sql
SELECT date_key, material_key, COUNT(*) AS dup_count
FROM oem_lh.fact_procurement
GROUP BY date_key, material_key
HAVING COUNT(*) > 1;
```

### Validate Ranges
```sql
SELECT COUNT(*) AS invalid_count
FROM oem_lh.fact_epi_score
WHERE score < 0 OR score > 100;
```

## Performance Best Practices

### 1. Filter Early
```sql
✓ Good: Filter in WHERE before joining
SELECT fp.*, m.material_name_std
FROM (
    SELECT * FROM fact_procurement
    WHERE date_key >= 20240101
) fp
JOIN gold_dim_material m ON fp.material_key = m.material_key;
```

### 2. Use EXPLAIN
```sql
EXPLAIN SELECT * FROM fact_procurement WHERE date_key = 20240115;
```

### 3. Leverage Partitioning
```sql
-- Query uses partition filter (efficient)
SELECT * FROM fact_procurement WHERE year = 2024 AND month = 1;
```

## Warehouse Queries

### Create Indexes (if supported)
```sql
CREATE INDEX idx_material_key ON fact_procurement(material_key);
```

### Update Statistics
```sql
UPDATE STATISTICS oem_wh.fact_procurement;
```

## Comments

### Table Comments
```sql
COMMENT ON TABLE oem_lh.fact_procurement IS 'Procurement transactions with normalized quantities and surrogate keys';
```

### Column Comments
```sql
ALTER TABLE oem_lh.fact_procurement
ALTER COLUMN spend_eur
COMMENT 'Total spend in EUR (quantity_base × unitprice_eur)';
```

## Anti-Patterns to Avoid

### SELECT *
```sql
✗ Avoid: SELECT * FROM fact_procurement
✓ Better: SELECT date_key, spend_eur FROM fact_procurement
```

### Implicit Conversions
```sql
✗ Bad: WHERE date_key = '20240115'  -- String comparison
✓ Good: WHERE date_key = 20240115   -- Integer comparison
```

### Missing WHERE Clause on Large Tables
```sql
✗ Dangerous: SELECT COUNT(*) FROM fact_procurement  -- Full scan
✓ Better: SELECT COUNT(*) FROM fact_procurement WHERE year = 2024
```
