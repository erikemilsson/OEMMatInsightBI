CREATE TABLE [dbo].[gold_dim_country] (

	[country_key] bigint NULL, 
	[iso3] varchar(8000) NULL, 
	[iso_numeric] int NULL, 
	[wb_code] varchar(8000) NULL, 
	[country_name_std] varchar(8000) NULL
);