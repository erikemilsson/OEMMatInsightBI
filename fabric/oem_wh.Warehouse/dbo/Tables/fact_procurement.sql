CREATE TABLE [dbo].[fact_procurement] (

	[date_key] int NULL, 
	[material_key] bigint NULL, 
	[supplier_hq_country_key] bigint NULL, 
	[production_country_key] bigint NULL, 
	[quantity_base] float NULL, 
	[unitprice_eur] float NULL, 
	[spend_eur] float NULL
);