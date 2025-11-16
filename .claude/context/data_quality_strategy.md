# Data Quality Strategy - OEMMatInsightBI

## Overview

This document defines the data quality approach, checks, and monitoring strategy for the OEMMatInsightBI project.

## Data Quality Philosophy

### Principles
1. **Transparency:** All data quality issues visible and tracked
2. **No Data Loss:** Never discard data - assign to placeholders and audit
3. **Confidence Tracking:** Every match has a confidence score
4. **Continuous Improvement:** Regular review and refinement of alias mappings

## Quality Dimensions

### 1. Accuracy
**Definition:** Data correctly represents real-world values

**Checks:**
- Alias matching with confidence scores
- Country/material name standardization
- Unit price within expected ranges

**Target:** >90% high-confidence matches

### 2. Completeness
**Definition:** All required fields populated

**Checks:**
- NULL checks on required fields (date, material, supplier, quantity, price)
- Missing dimension attributes (country ISO codes, material groups)

**Target:** <1% records with missing required fields

### 3. Consistency
**Definition:** Data standardized across all sources

**Checks:**
- Column naming conventions (lowercase, underscores)
- Data type consistency (dates as DATE, amounts as DECIMAL)
- Unit normalization (all quantities in kg)

**Target:** 100% adherence to standards

### 4. Timeliness
**Definition:** Data refreshed according to schedule

**Checks:**
- Pipeline execution success rate
- Time since last refresh
- Data latency (transaction date vs load date)

**Target:** Daily refresh success rate >95%

### 5. Validity
**Definition:** Data conforms to business rules

**Checks:**
- Negative values where inappropriate
- Score ranges (EPI 0-100, WGI 0-100)
- Date ranges (no future dates for historical data)

**Target:** <0.1% invalid values

## Quality Checks by Layer

### Bronze Layer

**Objective:** Detect source system issues early

**Checks Implemented:**
- ✅ Row count within expected range (rough validation)
- ❌ Schema drift detection (Task 07)
- ❌ NULL checks on primary keys (Task 07)
- ❌ Duplicate detection (Task 07)

**Checks Needed (Task 07):**
```python
# Row count validation
expected_counts = {
    "bronze_procurement_transactional": (1000, 50000),
    "bronze_supplier_ref": (10, 500),
    "bronze_epi2024results": (180, 200)
}

# Schema validation
validate_schema(table, expected_columns, expected_types)

# NULL checks
check_nulls(table, required_fields)

# Duplicate detection
check_duplicates(table, natural_key_columns)
```

### Silver Layer

**Objective:** Validate cleaning and standardization

**Checks Implemented:**
- ✅ Score range validation (0-100 for WB indicators)
- ✅ Null filtering on key fields
- ✅ Duplicate removal
- ❌ Referential integrity (Task 07)
- ❌ Business rule validation (Task 07)

**Checks Needed (Task 07):**
```python
# Referential integrity
check_orphaned_records(child_table, parent_table, join_key)

# Business rules
validate_rule(table, "unitpriceeur > 0", "Price must be positive")
validate_rule(table, "quantity > 0", "Quantity must be positive")

# Outlier detection
flag_outliers(table, column, threshold=3)  # 3 std deviations
```

### Gold Layer

**Objective:** Track data quality and provide visibility

**Checks Implemented:**
- ✅ Match confidence scoring (0-1 scale)
- ✅ Quality categorization (High/Medium/Low/Unmapped)
- ✅ Unmapped value logging
- ✅ Audit trail tables
- ✅ Coverage matrix
- ❌ Aggregate reconciliation (Task 07)
- ❌ Historical trend validation (Task 07)

**Checks Needed (Task 07):**
```python
# Reconciliation
silver_total = spark.table("silver_procurement").agg(sum("quantity")).collect()[0][0]
gold_total = spark.table("fact_procurement").agg(sum("quantity_base")).collect()[0][0]
assert_close(silver_total, gold_total, tolerance=0.01)

# Trend validation
flag_unusual_changes(table, metric, threshold=0.50)  # >50% change
```

## Confidence Scoring System

### Country Matching

| Confidence | Match Type | Example |
|-----------|-----------|---------|
| 1.00 | Exact ISO3 match | "USA" → USA |
| 0.95 | Standard alias | "United States" → USA |
| 0.90 | Common variant | "US" → USA |
| 0.85 | Territory mapping | "Hong Kong" → China |
| 0.80 | Encoding variant | "Türkiye" → Turkey |
| 0.00 | No match | "Atlantis" → Unknown - Global |

### Material Matching

| Confidence | Match Type | Example |
|-----------|-----------|---------|
| 0.95 | Case variation | "COPPER" → Copper |
| 0.95 | Spelling variant | "Aluminum" → Aluminium |
| 0.90 | Unit suffix | "Copper (kg)" → Copper |
| 0.00 | No match | "Unobtainium" → Unknown Material |

### Overall Quality Score
```
data_quality_score = (material_conf + hq_country_conf + prod_country_conf) / 3
```

## Audit Tables

### Purpose
Log all data quality issues for review and improvement.

### Tables Created

**1. gold_unmapped_procurement_audit**
- Tracks procurement records with unmapped dimensions
- Columns: unmapped_value, unmapped_field, spend_eur, source_row
- Use case: Identify missing aliases, assess financial impact

**2. gold_unmapped_supply_audit**
- Tracks supply share records with unmapped values
- Columns: unmapped_material, unmapped_country, share_pct, unmapped_impact_score
- Use case: Prioritize alias additions by supply concentration impact

**3. gold_data_quality_metrics**
- Summary statistics on data quality
- Columns: metric_name, metric_value, timestamp
- Use case: Track quality trends over time

**4. gold_country_coverage_matrix**
- Shows which countries appear in which data sources
- Columns: country_name, in_procurement, in_epi, in_wgi, in_supply_shares
- Use case: Understand data source coverage gaps

## Quality Monitoring

### Daily Checks (Automated in Pipeline)
- [ ] Pipeline execution success (Task 10, 11)
- [ ] Row count validation (Task 07)
- [ ] Unmapped value count <1% (Task 01)
- [ ] High quality records >85% (Task 01)

### Weekly Review (Manual)
- [ ] Review new unmapped values
- [ ] Add high-impact aliases
- [ ] Check for data source updates (EPI, WGI, EU CRM)
- [ ] Validate quality score distribution

### Monthly Review (Manual)
- [ ] Analyze quality trends
- [ ] Refine confidence thresholds
- [ ] Update business rules if needed
- [ ] Review outliers and edge cases

## Quality Improvement Process

### 1. Identify Issues
```bash
# Run quality checks
/check-quality

# View unmapped values
/view-unmapped
```

### 2. Prioritize
- **Critical (P0):** High-spend or high-concentration unmapped values
- **High (P1):** Frequently occurring unmapped values (>100 records)
- **Medium (P2):** Occasionally occurring (10-100 records)
- **Low (P3):** Rare unmapped values (<10 records)

### 3. Research & Resolve
- Look up correct standard name (ISO codes, Wikipedia, official sources)
- Determine appropriate confidence score
- Add to lookup table or notebook

### 4. Re-run & Validate
```bash
# Re-run gold transformation
/run-gold

# Validate improvement
/check-quality
```

### 5. Document
- Update alias mappings documentation
- Commit changes with clear message
- Update data quality metrics baseline

## Quality Metrics & Targets

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| High confidence records | TBD | >85% | 📊 Measure |
| Unmapped procurement | TBD | <1% | 📊 Measure |
| Unmapped supply | TBD | <5% | 📊 Measure |
| Pipeline success rate | TBD | >95% | 📊 Measure |
| Avg quality score | TBD | >0.92 | 📊 Measure |

## Data Quality Dashboard (Task 01)

### Planned Visuals
1. **Quality Scorecard:** Overall quality percentage, unmapped count
2. **Confidence Distribution:** Pie chart of High/Medium/Low/Unmapped
3. **Unmapped Trend:** Line chart showing unmapped count over time
4. **Top Unmapped Values:** Table with impact assessment
5. **Source Coverage:** Matrix showing country presence across sources

### Implementation
- Create notebook: `data_quality_report.Notebook`
- Generate table: `gold_data_quality_dashboard`
- Add to Power BI report as dedicated page

## Handling Quality Issues

### Low Confidence Matches
**Issue:** Many records have quality score 0.7-0.89

**Action:**
1. Review alias mappings for affected dimensions
2. Add more standard aliases (0.95 confidence)
3. Re-run transformation

### High Unmapped Rate
**Issue:** >1% of records unmapped

**Action:**
1. Export unmapped values: `/view-unmapped`
2. Research top 20 by frequency/impact
3. Add aliases to lookup tables
4. Re-run transformation and validate

### Data Source Gaps
**Issue:** Country in procurement but not in EPI/WGI

**Action:**
1. Check if country is valid (could be alias issue)
2. If valid, accept gap (not all countries have EPI/WGI data)
3. Note in coverage matrix for stakeholder awareness

### Outliers
**Issue:** Unit prices or quantities far from normal range

**Action:**
1. Investigate: data entry error or legitimate edge case?
2. If error: Correct in source system
3. If legitimate: Document as business rule exception

## Quality Improvement Roadmap

### Phase 1: Measurement (Current)
- ✅ Implement confidence scoring
- ✅ Create audit tables
- 📋 Create DQ dashboard (Task 01)
- 📋 Establish baseline metrics

### Phase 2: Automation (Task 07)
- 📋 Add bronze/silver layer checks
- 📋 Automated alerting on quality issues
- 📋 Daily quality reports
- 📋 Integration with pipeline orchestration

### Phase 3: Advanced (Future)
- Machine learning for alias matching
- Anomaly detection for outliers
- Predictive quality scoring
- Real-time quality monitoring

## Related Files

- `/.claude/tasks/01_enhance_data_quality_visibility.md` - DQ Dashboard
- `/.claude/tasks/07_add_data_quality_checks.md` - Automated checks
- `/.claude/commands/check-quality.md` - Quality check command
- `/.claude/commands/view-unmapped.md` - Unmapped values command
- `/fabric/silver-to-gold2.Notebook/` - Quality scoring implementation
