CREATE TABLE [dbo].[fact_procurement] (

	[date_key] int NULL, 
	[material_key] bigint NULL, 
	[supplier_hq_country_key] bigint NULL, 
	[production_country_key] bigint NULL, 
	[quantity_base] float NULL, 
	[unitprice_eur] float NULL, 
	[spend_eur] float NULL, 
	[data_quality_score] float NULL, 
	[quality_category] varchar(8000) NULL, 
	[source_row_id] bigint NULL
);