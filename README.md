# OEMMatInsightBI

OEMMatInsightBI is a data analytics solution built on Microsoft Fabric that aims to show how common databases at OEMs (Original Equipment Manufacturers) can be linked and connected to various material databases and datasets to provide live insights into the impacts of the materials used in their products.

Microsoft Fabric is a user-friendly SaaS (Software as a Service) data analytics platform built upon OneLake that integrates data lakes, data warehouses, real-time analytics, data science, and BI-reports and dashboards.

## Technologies Used

-   **Cloud Platform:** Microsoft Azure
-   **Data Analytics Suite:** Microsoft Fabric
-   **Data Storage:** Azure SQL Database (for synthetic ERP data), OneLake
-   **BI & Visualization:** Power BI
-   **Data Integration:** Fabric Data Factory (Pipelines and Dataflows)
-   **Data Transformation:** PySpark 3.4+ (in Fabric Notebooks), Power Query M (in Dataflows), SQL, and DAX
-   **Build Tools:** Microsoft.Build.Sql 0.1.19-preview (for SQL project management)
-   **Testing Framework:** pytest 8.0+, pytest-cov 4.1+, pytest-xdist 3.5+
-   **Local Development:** Python 3.12+, PySpark 3.4+

## Project Structure

This repository is organized into the following directories:

-   `azure/`: Contains SQL scripts for setting up the initial Azure SQL database.
-   `data/`: Contains sample data files used in the project.
-   `fabric/`: Contains all the Microsoft Fabric artifacts, including notebooks, dataflows, pipelines, lakehouse, warehouse, and the Power BI semantic model.
    -   `oem_wh.Warehouse/`: SQL Data Warehouse project using Microsoft.Build.Sql tooling
        -   `oem_wh.sqlproj`: Project file with configuration including ProjectGuid for build tool identification
-   `src/`: Contains reusable Python transformation functions for data processing.
    -   `transformations/`: Key generation and data quality functions used in notebooks.
-   `tests/`: Unit and integration tests for transformation functions using pytest.

## Setup and Installation

This project is built entirely on the Microsoft Fabric SaaS platform and does not require local installation. The setup involves the following:

1.  **Azure SQL Database & SQL Server:** A provisioned Azure SQL Database is used to host the synthetic procurement data. The SQL scripts in the `azure/` directory can be used to create the necessary tables.
2.  **Microsoft Fabric Workspace:** A Fabric workspace is set up to serve as the central environment for data integration, modeling, and visualization.
3.  **Data Ingestion:**
    -   The `bronze_azureSQLdb2table.Dataflow` and `copyjob1.CopyJob` are used to ingest data from the Azure SQL Database into the `oem_lh.Lakehouse`.
    -   The `EPI_file2table.Dataflow` and `WB_file2table.Dataflow` are used to ingest data from uploaded files.
4.  **Data Transformation:**
    -   The `clean_columnsAndHeaders.Notebook` and `Silver-to-Gold.Notebook` (PySpark notebooks) are used to clean and transform the data from the bronze to the silver and gold layers of the lakehouse.
    -   The `silver-to-gold-dataflow.Dataflow` is also used for data transformation.
5.  **Data Warehousing:** The transformed data is loaded into the `oem_wh.Warehouse`.
6.  **Semantic Model:** A Power BI semantic model (`semantic_model_oeminsightbi.SemanticModel`) is developed within Fabric to create relationships between the different data sources and define key metrics.
7.  **Power BI Report:** A Power BI report (`report.Report`) is created on top of the semantic model to build the interactive dashboards.

## Local Development Workflow

While the main project runs on Microsoft Fabric, local development is supported for testing and validating transformation logic:

### Prerequisites

-   **Python 3.12+** installed on your system
-   **Git** for version control
-   **Virtual environment tool** (venv, recommended)

### Setting Up Local Environment

1. **Clone the repository:**
   ```bash
   git clone https://github.com/erikemilsson/OEMMatInsightBI.git
   cd OEMMatInsightBI
   ```

2. **Create and activate a virtual environment:**
   ```bash
   # Create virtual environment
   python3 -m venv .venv

   # Activate on macOS/Linux
   source .venv/bin/activate

   # Activate on Windows
   .venv\Scripts\activate
   ```

3. **Install test dependencies:**
   ```bash
   pip install -r requirements-test.txt
   ```

### Development Cycle

1. **Make changes** to transformation functions in `src/transformations/`
2. **Write tests** in `tests/` following existing patterns
3. **Run tests locally** to validate changes (see Testing section)
4. **Commit changes** with descriptive commit messages
5. **Deploy to Fabric** by copying updated code to Fabric notebooks

### SQL Project Development

The `oem_wh.sqlproj` file is managed by Microsoft.Build.Sql tooling:

-   **ProjectGuid:** Uniquely identifies the project for build tools
-   **DSP:** SqlDwUnifiedDatabaseSchemaProvider for Fabric Warehouse compatibility
-   **DefaultCollation:** Latin1_General_100_BIN2_UTF8 for consistent data sorting

## Project Summary

### Background:

SwiftBike Tech is a fictional company that manufactures high-performance electric scooters and bikes designed for both casual riders and sports enthusiasts. The company emphasizes lightweight materials and efficient motors to deliver superior performance. As an international enterprise, SwiftBike Tech has manufacturing plants in Europe and Asia and has recently transitioned most of their on-premises ERP (Engineering Resource Planning) data to Azure SQL Database to support their expanding global business.

SwiftBike Tech has chosen Microsoft Fabric to manage analytics and provide a dashboard to for full transparency of their environmental, social, and govenance (ESG) impacts, albeit with their critical data being anonymized. A more detailed analytical dashboard is also created from the same data for SwiftBike Tech to help procurement to work proactively to minimize the company's ESG impacts.

### Method:

1.  **Data Ingestion, Cleaning, and Transformation:**
    -   Data from various sources are ingested into Microsoft Fabric.
    -   The data undergoes cleaning and transformation processes to ensure accuracy and consistency.
    -   The `orchestrator_pipeline_bronze_to_gold.DataPipeline` is used to automate updates and maintain real-time data freshness.
2.  **Semantic Model Development:**
    -   Semantic models are built using the cleaned and transformed data in Fabric, tailored specifically for the business use cases of SwiftBike Tech.
    -   These models will support the prioritization of part numbers based on various impact indicators and enable filtering by part ID.
3.  **Dashboard Creation:**
    -   Dashboards are developed with comprehensive tables and custom DAX (Data Analysis Expressions) scripting to meet the project goals.
    -   Visualizations are designed to provide clear insights into part impacts, enabling users to easily prioritize and filter part numbers as required.

### Data Sources Overview

-   **ESG Indicators:** From [Yale Environmental Performance Index](https://epi.yale.edu/), [World Bank Worldwide Governance Indicators](https://www.worldbank.org/en/publication/worldwide-governance-indicators),
-   **Country-Level Material-Use Shares:** Data on material use-shares at different production stages.
-   **Synthetic Supplier & Procurement data in Azure Database:** Bill of Materials (BOMs) and Sales Tracking data.

## Technical Overview

### Pipeline Overview

The `orchestrator_pipeline_bronze_to_gold.DataPipeline` orchestrates the entire data flow, from ingesting the raw data from Azure SQL and files to the final gold layer in the data warehouse. It executes the dataflows and notebooks in the correct order to ensure data consistency and freshness.

### Data governance + incremental strategy

**Pipeline Parameter Specification**

| Name | Type | Default Value | Example Value | Consumed in | Purpose |
|--------|--------|--------------------------------|--------|--------|--------|
| procurement_array | Array | \[{"source":"dbo.Suppliers","sink":"bronze_suppliers"},{"source":"dbo.Materials","sink":"bronze_materials","translator":{"type":"TabularTranslator","mappings":\[{"source":{"name":"Material ID","type":"String","physicalType":"String"},"sink":{"name":"Material_ID","physicalType":"string"}},{"source":{"name":"Short Name","type":"String","physicalType":"String"},"sink":{"name":"Short_Name","physicalType":"string"}}\]}},{"source":"dbo.Purchases","sink":"bronze_purchases"}\] | \[{"source":"dbo.Procurement"},{"source":"dbo.Suppliers"}\] | Dataflow / Copy activities | Controls which source tables to ingest for procurement-related data. Useful if you want to add/remove sources without editing activity code. |
| p_full_load | Bool | FALSE | true / false | All Silver notebooks | Switches between full refresh (overwrite all data) and incremental (merge only new/changed rows). |
| p_from_date | String | "1900-01-01" | "2024-01-01" | nb_silver_standardize, nb_silver_integrate (procurement filtering) | Watermark date for incremental loads. Filters order_date \>= p_from_date so only new data is processed. |

#### Usage pattern

```
•   First run (initial load):
•   p_full_load = true
•   p_from_date = "1900-01-01" (ignored because full load)
•   Subsequent runs (incremental):
•   p_full_load = false
•   p_from_date = @{pipeline().parameters.last_success_date} (or manually set)
```

## Data Warehouse Schema

The `oem_wh.Warehouse` serves as the gold layer, providing optimized, business-ready data for analytics and reporting.

### Warehouse Configuration

-   **Provider:** SqlDwUnifiedDatabaseSchemaProvider (Fabric Data Warehouse)
-   **Collation:** Latin1_General_100_BIN2_UTF8 (case-sensitive, UTF-8 encoding)
-   **Build Tool:** Microsoft.Build.Sql 0.1.19-preview

### Data Architecture

The warehouse follows a dimensional modeling approach with:

**Fact Tables:**
-   Sales and procurement transaction data
-   Material usage metrics
-   ESG impact measurements

**Dimension Tables:**
-   `dim_country`: Country information with ESG indicators
-   `dim_material`: Material master data
-   `dim_supplier`: Supplier information
-   `dim_date`: Date dimension for time-based analysis
-   `dim_product`: Product hierarchy and bill of materials

**Integration:**
-   Data is loaded from the gold layer of `oem_lh.Lakehouse`
-   Surrogate keys ensure referential integrity
-   Slowly Changing Dimensions (SCD) type 1 for current-state tracking

### Semantic Model

The `semantic_model_oeminsightbi.SemanticModel` sits on top of the warehouse and provides:
-   Pre-calculated measures using DAX
-   Relationships between fact and dimension tables
-   Role-based security (if implemented)
-   Optimized for Power BI reporting

## Testing

This project includes a comprehensive unit test suite for transformation functions, ensuring data quality and consistency across the pipeline.

### Test Coverage

The test suite validates:

-   **Key Generation:** Surrogate key functions (`stable_key`, `generate_country_key`, `generate_material_key`, `generate_date_key`)
-   **Data Quality:** Null checks, duplicate detection, schema validation
-   **Transformation Logic:** Data type conversions, column mappings, filtering rules

Current test modules:
-   `tests/test_key_generation.py`: Tests for deterministic hash-based surrogate keys
-   `tests/test_data_quality.py`: Tests for data validation and quality checks
-   `tests/conftest.py`: Shared pytest fixtures including SparkSession setup

### Running Tests Locally

**Prerequisites:**
- Python 3.12+ installed
- Virtual environment recommended (see Local Development Workflow)

**Setup:**

``` bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install test dependencies
pip install -r requirements-test.txt
```

**Run All Tests:**

``` bash
# Run all tests with verbose output
pytest tests/ -v

# Run specific test file
pytest tests/test_key_generation.py -v

# Run specific test class or function
pytest tests/test_key_generation.py::TestStableKey -v
pytest tests/test_key_generation.py::TestStableKey::test_stable_key_consistency -v

# Run tests with specific marker
pytest tests/ -m unit -v
```

**Run Tests with Coverage:**

``` bash
# Generate coverage report
pytest --cov=src --cov-report=html tests/

# View coverage report
open htmlcov/index.html  # On macOS
start htmlcov/index.html  # On Windows
xdg-open htmlcov/index.html  # On Linux

# Generate terminal coverage report
pytest --cov=src --cov-report=term-missing tests/
```

**Run Tests in Parallel:**

``` bash
# Use multiple CPU cores for faster test execution
pytest tests/ -n auto

# Specify number of workers
pytest tests/ -n 4
```

**Additional Test Options:**

``` bash
# Run with detailed output
pytest tests/ -vv

# Stop on first failure
pytest tests/ -x

# Show local variables in tracebacks
pytest tests/ -l

# Run tests that failed last time
pytest tests/ --lf
```

### Test Structure

```
tests/
├── conftest.py              # Pytest fixtures (SparkSession, sample data)
├── __init__.py              # Package initialization
├── test_key_generation.py   # Tests for surrogate key generation
│   ├── TestStableKey        # Hash-based key consistency tests
│   ├── TestCountryKey       # Country dimension key tests
│   ├── TestMaterialKey      # Material dimension key tests
│   └── TestDateKey          # Date dimension key tests
└── test_data_quality.py     # Tests for data quality checks
    ├── TestNullChecks       # Missing value validation
    ├── TestDuplicates       # Duplicate detection
    └── TestSchemaValidation # Schema conformance tests

src/transformations/
├── __init__.py              # Package initialization
├── key_generation.py        # Surrogate key functions
└── data_quality.py          # Data quality check functions
```

### Test Categories

Tests are marked with categories:
- `@pytest.mark.unit` - Fast unit tests for individual functions
- `@pytest.mark.integration` - Integration tests requiring external resources
- `@pytest.mark.slow` - Tests that take significant time
- `@pytest.mark.smoke` - Quick smoke tests for basic functionality

**Run specific category:**

``` bash
pytest tests/ -m unit        # Run only unit tests
pytest tests/ -m "not slow"  # Skip slow tests
pytest tests/ -m smoke       # Run smoke tests only
pytest tests/ -m "unit or smoke"  # Run unit OR smoke tests
```

### Continuous Integration

Tests can be integrated into CI/CD pipelines:

``` yaml
# Example GitHub Actions workflow
- name: Run tests
  run: |
    pip install -r requirements-test.txt
    pytest tests/ --cov=src --cov-report=xml

# Example with quality gates
- name: Run tests with coverage threshold
  run: |
    pip install -r requirements-test.txt
    pytest tests/ --cov=src --cov-report=term --cov-fail-under=80
```

### Writing New Tests

When adding new transformation functions:

1. **Create test file** in `tests/` matching the module name (e.g., `test_new_feature.py`)
2. **Use fixtures** from `conftest.py` for SparkSession and sample data
3. **Add markers** to categorize tests (`@pytest.mark.unit`, etc.)
4. **Follow naming conventions**: `test_<function_name>_<scenario>`
5. **Include docstrings** explaining what each test validates

Example test structure:

```python
import pytest
from src.transformations.new_feature import new_function

class TestNewFunction:
    """Tests for new_function."""

    @pytest.mark.unit
    def test_new_function_basic_case(self, spark):
        """Test that new_function handles basic input correctly."""
        # Arrange
        data = [("value1",), ("value2",)]
        df = spark.createDataFrame(data, ["column"])

        # Act
        result = new_function(df)

        # Assert
        assert result.count() == 2
```

## Troubleshooting

Common issues and solutions when working with the project:

### Local Testing Issues

**Problem: `ModuleNotFoundError` when running tests**

```bash
ModuleNotFoundError: No module named 'pyspark'
```

**Solution:**
- Ensure you've activated your virtual environment: `source .venv/bin/activate`
- Install test dependencies: `pip install -r requirements-test.txt`
- Verify installation: `pip list | grep pyspark`

**Problem: Java not found when running PySpark tests**

```bash
Exception: Java gateway process exited before sending its port number
```

**Solution:**
- PySpark requires Java 8 or 11. Install Java:
  - macOS: `brew install openjdk@11`
  - Ubuntu: `sudo apt-get install openjdk-11-jdk`
  - Windows: Download from [Oracle](https://www.oracle.com/java/technologies/downloads/) or use [Chocolatey](https://chocolatey.org/)
- Set `JAVA_HOME` environment variable:
  ```bash
  # macOS/Linux
  export JAVA_HOME=/path/to/java
  # Windows
  set JAVA_HOME=C:\Program Files\Java\jdk-11
  ```

**Problem: Tests pass locally but fail in different environments**

**Solution:**
- Ensure consistent Python version (3.12+)
- Pin exact package versions if needed
- Check for OS-specific file path issues (use `pathlib.Path` instead of string concatenation)

### Microsoft Fabric Issues

**Problem: Pipeline fails with "Activity failed" error**

**Solution:**
- Check pipeline run details for specific activity errors
- Verify notebook parameters are correctly passed
- Ensure lakehouse/warehouse connections are valid
- Check for data type mismatches in dataflows

**Problem: Incremental load not detecting new records**

**Solution:**
- Verify `p_from_date` parameter is set correctly
- Check source table has timestamp column for watermarking
- Confirm `p_full_load` is set to `false`
- Review filter logic in notebooks (should use `>=` not `>`)

**Problem: Warehouse project build fails**

```
Error: The project file could not be loaded
```

**Solution:**
- Ensure `ProjectGuid` is present in `oem_wh.sqlproj`
- Verify Microsoft.Build.Sql SDK version compatibility
- Check XML syntax in `.sqlproj` file
- Clear build cache: delete `obj/` and `bin/` directories if present

### Data Quality Issues

**Problem: Surrogate keys are changing between runs**

**Solution:**
- Ensure using `stable_key()` function from `src/transformations/key_generation.py`
- Verify input columns are consistently formatted (trim whitespace, consistent casing)
- Check for null values in key generation columns

**Problem: Duplicate records in gold layer**

**Solution:**
- Review deduplication logic in transformation notebooks
- Check if merge mode is correctly set (update vs. append)
- Verify unique constraints on business keys
- Run data quality tests: `pytest tests/test_data_quality.py -v`

### Performance Issues

**Problem: Notebook execution taking too long**

**Solution:**
- Enable incremental loads instead of full refresh
- Add partitioning to large tables
- Optimize Spark configurations (increase executor memory/cores)
- Use broadcast joins for small dimension tables
- Cache intermediate DataFrames if reused multiple times

**Problem: Out of memory errors in PySpark**

**Solution:**
- Increase Spark executor memory in Fabric notebook settings
- Use `repartition()` or `coalesce()` to manage partition sizes
- Avoid collecting large DataFrames to driver
- Process data in batches for very large datasets

### Getting Help

If you encounter issues not covered here:

1. **Check logs:** Review detailed error messages in Fabric pipeline/notebook logs
2. **Run tests:** Execute `pytest tests/ -v` to identify transformation issues
3. **Consult documentation:**
   - [Microsoft Fabric Documentation](https://learn.microsoft.com/en-us/fabric/)
   - [PySpark API Reference](https://spark.apache.org/docs/latest/api/python/)
4. **Report bugs:** Open an issue on the [GitHub repository](https://github.com/erikemilsson/OEMMatInsightBI/issues)

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Author

**Erik Emilsson**

-   [LinkedIn Profile](https://www.linkedin.com/in/erikemilsson/)

-   [GitHub Profile](https://github.com/erikemilsson)