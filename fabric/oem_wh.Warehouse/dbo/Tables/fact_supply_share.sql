CREATE TABLE [dbo].[fact_supply_share] (

	[material_key] bigint NULL, 
	[stage_key] bigint NULL, 
	[country_key] bigint NULL, 
	[year] int NULL, 
	[share_pct] varchar(8000) NULL, 
	[intensity_t] varchar(8000) NULL
);