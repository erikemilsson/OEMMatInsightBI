CREATE TABLE [dbo].[fact_supply_share] (

	[material_key] bigint NULL, 
	[stage_key] bigint NULL, 
	[country_key] bigint NULL, 
	[year] int NULL, 
	[share_pct] float NULL, 
	[data_quality_score] float NULL, 
	[quality_category] varchar(8000) NULL, 
	[has_unmapped_material] bit NULL, 
	[has_unmapped_country] bit NULL, 
	[unmapped_impact_score] float NULL, 
	[source_row_id] bigint NULL
);