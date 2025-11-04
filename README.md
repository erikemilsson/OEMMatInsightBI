# OEMMatInsightBI

OEMMatInsightBI is a data analytics solution built on Microsoft Fabric that aims to show how common databases at OEMs (Original Equipment Manufacturers) can be linked and connected to various material databases and datasets to provide live insights into the impacts of the materials used in their products.

Microsoft Fabric is a user-friendly SaaS (Software as a Service) data analytics platform built upon OneLake that integrates data lakes, data warehouses, real-time analytics, data science, and BI-reports and dashboards.

## Technologies Used

-   **Cloud Platform:** Microsoft Azure
-   **Data Analytics Suite:** Microsoft Fabric
-   **Data Storage:** Azure SQL Database (for synthetic ERP data), OneLake
-   **BI & Visualization:** Power BI
-   **Data Integration:** Fabric Data Factory (Pipelines and Dataflows)
-   **Data Transformation:** PySpark (in Fabric Notebooks), Power Query M (in Dataflows), SQL, and DAX

## Project Structure

This repository is organized into the following directories:

-   `azure/`: Contains SQL scripts for setting up the initial Azure SQL database.
-   `data/`: Contains sample data files used in the project.
-   `fabric/`: Contains all the Microsoft Fabric artifacts, including notebooks, dataflows, pipelines, lakehouse, warehouse, and the Power BI semantic model.

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

## Testing

This project includes a comprehensive unit test suite for transformation functions.

### Running Tests Locally

**Prerequisites:** - Python 3.12+ installed - Virtual environment recommended

**Setup:**

``` bash
# Create and activate virtual environment
python -m venv .venv
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

# Run tests with specific marker
pytest tests/ -m unit -v
```

**Run Tests with Coverage:**

``` bash
# Generate coverage report
pytest --cov=src --cov-report=html tests/

# View coverage report
open htmlcov/index.html  # On macOS
```

**Run Tests in Parallel:**

``` bash
# Use multiple CPU cores for faster test execution
pytest tests/ -n auto
```

### Test Structure

```         
tests/
├── conftest.py              # Pytest fixtures (SparkSession, sample data)
├── test_key_generation.py   # Tests for surrogate key generation
└── test_data_quality.py     # Tests for data quality checks

src/transformations/
├── key_generation.py        # Surrogate key functions
└── data_quality.py          # Data quality check functions
```

### Test Categories

Tests are marked with categories: - `@pytest.mark.unit` - Fast unit tests for individual functions - `@pytest.mark.integration` - Integration tests requiring external resources - `@pytest.mark.slow` - Tests that take significant time - `@pytest.mark.smoke` - Quick smoke tests for basic functionality

**Run specific category:**

``` bash
pytest tests/ -m unit        # Run only unit tests
pytest tests/ -m "not slow"  # Skip slow tests
```

### Continuous Integration

Tests can be integrated into CI/CD pipelines:

``` yaml
# Example GitHub Actions workflow
- name: Run tests
  run: |
    pip install -r requirements-test.txt
    pytest tests/ --cov=src --cov-report=xml
```

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Author

**Erik Emilsson**

-   [LinkedIn Profile](https://www.linkedin.com/in/erikemilsson/)

-   [GitHub Profile](https://github.com/erikemilsson)