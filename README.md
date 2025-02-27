# OEMMatInsightBI
OEMMatInsightBI is a data analytics solution built on Microsoft Fabric that aims to show what how common databases at OEMs (Original Equipment Manufacturers) can be linked and connected to various material databases and datasets to provide live insights into the impacts of the materials used in their products. 

Microsoft Fabric is a user-friendly SaaS (Software as a Service) data analytics platform that integrates data lakes, data warehouses, real-time analytics, data science, and BI-reports and dashboards. The platform is built upon OneLake, which uses the delta parquet format.

## Project Summary

**Project Description and Goals:**

SwiftBike Tech is a fictional company that manufactures high-performance electric scooters and bikes designed for both casual riders and sports enthusiasts. The company emphasizes lightweight materials and efficient motors to deliver superior performance. As an international enterprise, SwiftBike Tech has manufacturing plants in Europe and Asia and has recently transitioned most of their on-premises ERP (Engineering Resource Planning) data to Azure Blob storage to support their expanding global business.

To manage analytics and distribute dashboards and reports to various groups, SwiftBike Tech has chosen Microsoft Fabric. This move is part of their broader strategy to leverage modern cloud technologies for better decision-making and operational efficiency between developers, data professionals, and various user groups.

The primary objectives for the initial phase of this project are:

1. **Prioritize Part Numbers by Impact Indicators:** 
   - Users should be able to easily prioritize part numbers based on their impacts on various selectable indicators such as environmental impact, cost, weight, and performance metrics.
   
2. **Filter Part Impacts by Part ID:**
   - Users should have the ability to filter and view the main impacts of specific part numbers by entering a unique part ID.

These goals aim to provide *designers* with actionable insights into their material sourcing and usage, enabling them to make informed decisions that align with their business objectives and sustainability goals.

**Method Overivew:**

1. **Data Ingestion, Cleaning, and Transformation:**
   - Data from various sources are ingested into Microsoft Fabric.
   - The data undergoes cleaning and transformation processes to ensure accuracy and consistency.
   - Data pipelines are created and orchestrated to automate updates and maintain real-time data freshness.

2. **Semantic Model Development:**
   - Semantic models are built using the cleaned and transformed data in Fabric, tailored specifically for the business use cases of SwiftBike Tech.
   - These models will support the prioritization of part numbers based on various impact indicators and enable filtering by part ID.

3. **Dashboard Creation:**
   - Dashboards are developed with comprehensive tables and custom DAX (Data Analysis Expressions) scripting to meet the project goals.
   - Visualizations are designed to provide clear insights into part impacts, enabling users to easily prioritize and filter part numbers as required.

**Data Sources Overview**

1. **Live Commodity Prices:**
   - Data from metalpriceapi.com provides real-time commodity prices, which are crucial for tracking the cost impacts of materials used in manufacturing.

2. **Indicators:**
   - **ESG (Environmental, Social, and Governance):** Metrics to assess the environmental impact, social responsibility, and governance practices related to material sourcing.
   - **Value Added (VA):** Indicators to measure the value added by each part or component in the production process.

3. **Country-Level Use-Shares:**
   - Data on the use-shares of materials at various stages such as mining, refining, and manufacturing, broken down by country level.

4. **Synthetic ERP-Data in Azure Blob Storage:**
   - **BOMs (Bill of Materials) Database:** Contains detailed information about the parts and components used in each product.
   - **Sales Tracking Database:** Tracks sales data to understand demand and performance metrics related to different part numbers.
