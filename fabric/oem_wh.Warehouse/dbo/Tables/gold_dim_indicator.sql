CREATE TABLE [dbo].[gold_dim_indicator] (

	[indicator_key] bigint NULL, 
	[source_system] varchar(8000) NULL, 
	[type] varchar(8000) NULL, 
	[abbrev] varchar(8000) NULL, 
	[variable_name] varchar(8000) NULL, 
	[policyobjective] varchar(8000) NULL, 
	[issuecategory] varchar(8000) NULL, 
	[indicator_code] varchar(8000) NULL, 
	[weight] varchar(8000) NULL, 
	[description] varchar(8000) NULL, 
	[parent_indicator_key] bigint NULL
);