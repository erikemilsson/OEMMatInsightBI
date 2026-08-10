# Naming Standards - OEMMatInsightBI

## Current State Analysis

### Inconsistencies Identified
- **Table prefixes:** Mix of bronze_/silver_/gold_dim_
- **Notebook names:** ✅ resolved — all notebooks are snake_case as of 2026-08-10 (`sample-quality-data`, the last hyphenated name, became `sample_quality_data`)
- **Column names:** Inconsistent (Date vs date, MaterialName vs materialname)
- **Artifact names:** Mix of camelCase and underscores (`bronze_azureSQLdb2table` vs `orchestrator_pipeline_bronze_to_gold`) — *`bronze_azureSQLdb2table` was retired 2026-07-31; kept here as a naming example only*

## Recommended Standards

### Table Naming

**Pattern:** `[layer]_[entity]` or `[layer]_dim_[dimension]` for dimensions

**Bronze:**
```
bronze_[source]_[entity]
Examples: bronze_procurement_transactional, bronze_supplier_ref, bronze_epi2024results
```

**Silver:**
```
silver_[entity]
Examples: silver_procurement, silver_epi2024results, silver_globalsupplyshares
```

**Gold Facts:**
```
fact_[subject]
Examples: fact_procurement, fact_supply_share, fact_epi_score
```

**Gold Dimensions:**
```
gold_dim_[dimension]
Examples: gold_dim_country, gold_dim_date, gold_dim_material
```

**Supporting Tables:**
```
gold_[purpose]_[entity]
Examples: gold_unmapped_procurement_audit, gold_data_quality_metrics
```

### Column Naming

**Standard:** lowercase with underscores (snake_case)

```
✓ Good: date_key, material_name, spend_eur, data_quality_score
✗ Bad: Date, MaterialName, SpendEUR, DataQualityScore
```

**Foreign Keys:** `[dimension]_key`
```
Examples: date_key, material_key, country_key
```

**Measures:** `[metric]_[unit]`
```
Examples: spend_eur, quantity_base, share_pct
```

### Notebook Naming

**Pattern:** `[purpose]_[source]_to_[target].Notebook`

**Recommended:**
```
bronze_to_silver_cleaning.Notebook
silver_to_gold_business_logic.Notebook
data_quality_checks.Notebook
```

**Current (inconsistent):**
```
data_quality_checks.Notebook   (underscores)
bronze_ingest_wgi.Notebook     (underscores)
silver_to_gold.Notebook       (underscores)
bronze_to_silver.Notebook      (underscores)
sample_quality_data.Notebook   (underscores — was hyphenated until 2026-08-10)
```

### Pipeline Naming

**Pattern:** `[purpose]_pipeline_[scope].DataPipeline`

```
Examples:
orchestrator_pipeline_bronze_to_gold.DataPipeline
incremental_load_pipeline_procurement.DataPipeline
```

### Dataflow Naming

**Pattern:** `[layer]_[source]_to_table.Dataflow`

```
Examples:
bronze_azuresql_to_table.Dataflow
bronze_epi_file_to_table.Dataflow
```

### Warehouse/Lakehouse Naming

**Pattern:** `[project_abbreviation]_[type]`

```
Examples:
oem_lh (lakehouse)
oem_wh (warehouse) — convention example only; the item was retired 2026-08-10
```

### Semantic Model & Report Naming

Semantic models and reports are Fabric-facing artifacts that follow Fabric's
display-name conventions (PascalCase, project-prefixed), **not** the snake_case
`[layer]_[entity]` pattern used for lakehouse tables, notebooks, and pipelines.
Applying the snake pattern here produces a name no Fabric artifact actually
carries (the prior `semantic_model_oeminsightbi` recommendation was just such a
fictional example).

**Semantic model:** `OEMInsightBI` — ✅ live as of 2026-08-10; the `_v2` suffix was dropped that day.
**Report:** `oem_report` — project-prefixed, co-named with its semantic model so the pair reads as one brand. ✅ live as of 2026-08-10; renamed from `report2`.

## File & Directory Standards

### Directory Structure
```
/
├── .claude/                    # Claude Code configuration
│   ├── tasks/                  # Task files (numbered)
│   ├── commands/               # Slash commands
│   ├── context/                # Documentation
│   │   ├── architecture/
│   │   └── standards/
│   └── reference/              # Reference docs
│       ├── schemas/
│       └── transformations/
├── .venv/                      # Python virtual environment
├── .vscode/                    # VS Code settings
├── azure/                      # Azure SQL scripts
├── data/                       # Local data files
├── fabric/                     # Fabric artifacts
│   ├── [ArtifactName].[Type]/
│   │   ├── .platform
│   │   └── [content files]
├── README.md
└── project_definition.md
```

### File Naming
```
✓ lowercase_with_underscores.md
✓ numbered_task_files_01_description.md
✗ CamelCaseFiles.md
✗ Mixed-naming_Styles.md
```

## Variable & Function Naming

### Python (PySpark)
```python
# Functions: snake_case
def stable_key(cols):
    pass

def calculate_quality_score(conf1, conf2, conf3):
    pass

# Variables: snake_case
date_key = 20240115
spend_eur = 1000.50

# Constants: UPPER_SNAKE_CASE
DATABASE_NAME = "oem_lh"
DEFAULT_CONFIDENCE = 1.0
```

### DAX
```dax
-- Measures: Title Case with spaces
Total Spend = SUM(fact_procurement[spend_eur])
YoY Growth % = ...

-- Columns: lowercase_with_underscores (from tables)
fact_procurement[spend_eur]
gold_dim_country[country_name_std]
```

### SQL
```sql
-- Tables: lowercase_with_underscores
SELECT * FROM oem_lh.fact_procurement

-- Columns: lowercase_with_underscores
SELECT date_key, spend_eur FROM fact_procurement
```

## Git Commit Messages

**Pattern:** `[Type]: Brief description (50 chars max)`

**Types:**
- feat: New feature
- fix: Bug fix
- docs: Documentation only
- refactor: Code restructuring
- test: Adding tests
- chore: Maintenance

**Examples:**
```
feat: Add incremental load logic to procurement dataflow
fix: Correct unit conversion for tonnes
docs: Update README with setup instructions
refactor: Extract alias resolution to separate function
```

## Enforcement

### Automated Checks (Future)
- Linting: black (Python), sqlfluff (SQL)
- Schema validation: Data quality checks
- Naming validation: Custom scripts

### Manual Review
- Code reviews before merge
- Documentation updates with naming changes
- Consistent application in new artifacts

## Migration Plan

### Priority 1: New artifacts use standards
### Priority 2: Rename on major refactor
### Priority 3: Document exceptions clearly
