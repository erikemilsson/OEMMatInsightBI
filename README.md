# OEMMatInsightBI

OEMMatInsightBI is a data analytics solution built on Microsoft Fabric that aims to show how common databases at OEMs (Original Equipment Manufacturers) can be linked and connected to various material databases and datasets to provide live insights into the impacts of the materials used in their products.

Microsoft Fabric is a user-friendly SaaS (Software as a Service) data analytics platform built upon OneLake that integrates data lakes, data warehouses, real-time analytics, data science, and BI-reports and dashboards.

## Technologies Used

*   **Cloud Platform:** Microsoft Azure
*   **Data Analytics Suite:** Microsoft Fabric
*   **Data Storage:** Azure SQL Database (for synthetic ERP data), OneLake
*   **BI & Visualization:** Power BI
*   **Data Integration:** Fabric Data Factory
*   **Data Transformation:** DAX

## Setup and Installation

This project is built entirely on the Microsoft Fabric SaaS platform and does not require local installation. The setup involves the following:

1.  **Azure SQL Database & SQL Server:** A provisioned Azure SQL Database is used to host the synthetic procurement data. SQL Server is used to interact with the database.
2.  **Microsoft Fabric Workspace:** A Fabric workspace is set up to serve as the central environment for data integration, modeling, and visualization.
3.  **Data Ingestion:** Data pipelines in Fabric are configured to ingest data from the Azure SQL Database. Country-level ESG indicators and country-level material-use shares are uploaded to the Fabric OneLake.
1.  **Semantic Model:** A Power BI semantic model is developed within Fabric to create relationships between the different data sources and define key metrics.
2.  **Power BI Report:** A Power BI report is created on top of the semantic model to build the interactive dashboards.

## Project Summary

### Background:

SwiftBike Tech is a fictional company that manufactures high-performance electric scooters and bikes designed for both casual riders and sports enthusiasts. The company emphasizes lightweight materials and efficient motors to deliver superior performance. As an international enterprise, SwiftBike Tech has manufacturing plants in Europe and Asia and has recently transitioned most of their on-premises ERP (Engineering Resource Planning) data to Azure SQL Database to support their expanding global business.

SwiftBike Tech has chosen Microsoft Fabric to manage analytics and provide a dashboard to for full transparency of their environmental, social, and govenance (ESG) impacts, albeit with their critical data being anonymized. A more detailed analytical dashboard is also created from the same data for SwiftBike Tech to help procurement to work proactively to minimize the company's ESG impacts.

### Method:

1.  **Data Ingestion, Cleaning, and Transformation:**
    *   Data from various sources are ingested into Microsoft Fabric.
    *   The data undergoes cleaning and transformation processes to ensure accuracy and consistency.
    *   Data pipelines are created and orchestrated to automate updates and maintain real-time data freshness.
2.  **Semantic Model Development:**
    *   Semantic models are built using the cleaned and transformed data in Fabric, tailored specifically for the business use cases of SwiftBike Tech.
    *   These models will support the prioritization of part numbers based on various impact indicators and enable filtering by part ID.
3.  **Dashboard Creation:**
    *   Dashboards are developed with comprehensive tables and custom DAX (Data Analysis Expressions) scripting to meet the project goals.
    *   Visualizations are designed to provide clear insights into part impacts, enabling users to easily prioritize and filter part numbers as required.

### Data Sources Overview

*   **ESG Indicators:** From [Yale Environmental Performance Index](https://epi.yale.edu/), [World Bank Worldwide Governance Indicators](https://www.worldbank.org/en/publication/worldwide-governance-indicators), 
*   **Country-Level Material-Use Shares:** Data on material use-shares at different production stages.
*   **Synthetic Supplier & Procurement data in Azure Database:** Bill of Materials (BOMs) and Sales Tracking data.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Author

**Erik Emilsson**
   *   [LinkedIn Profile](https://www.linkedin.com/in/erikemilsson/)
   *   [GitHub Profile](https://github.com/erikemilsson)