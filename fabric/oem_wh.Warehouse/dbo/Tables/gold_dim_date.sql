CREATE TABLE [dbo].[gold_dim_date] (

	[date_key] int NULL, 
	[date] date NULL, 
	[year] int NULL, 
	[month] int NULL, 
	[day] int NULL, 
	[month_name] varchar(8000) NULL, 
	[quarter] int NULL, 
	[day_of_week] int NULL, 
	[week_of_year] int NULL
);