CREATE TABLE [dbo].[gold_dim_material] (

	[material_key] bigint NULL, 
	[material_name_std] varchar(8000) NULL, 
	[commodity_group] varchar(8000) NULL, 
	[unit_base] varchar(8000) NULL, 
	[is_placeholder] bit NULL
);