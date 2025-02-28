# Project Journal

In this journal I track my progress in this Fabric project. Although it is mainly for myself to keep tabs on what I've done, I'm sharing it here in case it is of use to anyone looking in.

## 2025-02-14

#### Previous days

A few days ago I created this github repository and set up Fabric to use it for version control. It required going into the Admin Portal to allow the Github to be used. It wasn't particularly difficult to follow the Microsoft Learn documentation.

I also created two separate workspaces for what I foresee could be two discrete use-cases for analytics on manufacturing, critical raw materials, and pricing. I have some general idea for what I want to create, but I'm also flexible on changing direction if I find that something else makes more sense. The two workspaces are:

- risk&insights_team workspace: Meant for data engineers and data analysts who set up the data pipelines and design dashboards for reporting and analysis.
- communication_team workspace: Meant almost solely for end-users of the data, with more restrictions on how they're allowed to use the data.

I also started thinking of what type of data sources I could bring into Fabric to get valuable insights related to the sourcing of materials for e.g. an electronics manufacturer. There are many choices. Using an LLM, I get a few options:

- **Bill of Materials (BOM) Database** – Stores structured information on components, materials, and subassemblies required for each product
- **Product Lifecycle Management (PLM) Database** – Tracks product versions, engineering changes, and component obsolescence.
- **Supplier & Vendor Database** – Contains information on approved suppliers, material costs, and sourcing history.
- **Enterprise Resource Planning (ERP) Database** – Centralizes purchasing, financials, and supply chain data, often integrating with other databases.

I'll look into what attributes each database might have at a later stage. For now it is good that I did some research into this, so I know I'm on the right path. My aim is to later create one or more databases using synthetic data, using SQL server on my local desktop PC to mimic an on-premises database. I plan to use a data gateway so I can create a secure connection to Fabric.

Apart from the data that a manufacturer keeps on-premises, I also want to connect the data to some live data. I first considered creating my own, with sensors, or using an iterating Python script. However, since I couldn't envision them adding any additional value to the reports and visualizations I was going to create, I scrapped both ideas. 

Then I started looking into the possiblity of using raw material price data to get live data into Fabric using an EventStream. My inital thought was to create a web scraping script with Python, store the snapshots in SQL Server locally, and creating a Data Gateway and expose it to Fabric. However, the terms of use in most services that provide price don't allow for it, so I decided to look for an API and do more research on possible sources.

#### Today

Today I looked over several sources that provide commodity (metals and minerals) data with APIs that I can load into a Fabric Eventhouse. after looking around at various sources I found one that was called MetalPriceAPI that has a free-tier (that provides data in 30-minute intervals), and a basic-tier for about 100SEK (which provides data in 10-minute intervals). It has several precious metals and base metals, and also prices in many currencies. I will get started with the free-tier, and then upgrade once everything else is built and connected.

## 2025-02-18

I looked through the MetalPriceAPI [documentaton](https://metalpriceapi.com/documentation). It's an external HTTP API, so it can't connect to a Fabric Eventstream directly as it isn't listed as one a type of source it can connect to. However, Azure services like Eventhubs are available as an Evenstream source, so i could use that with either Azure Functions or Logic Apps to 