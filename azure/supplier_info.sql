-- azure/supplier_info.sql
-- DDL for dbo.supplier_ref  (LOAD ORDER: step 1 of 2)
--
--   step 1  azure/supplier_info.sql       -- THIS FILE: drops + creates the table
--   step 2  azure/supplier_info_seed.sql  -- inserts the 11 reference rows
--
-- DESTRUCTIVE. The DROP clears the table. Always run step 2 straight after step 1;
-- together they rebuild the Azure SQL source from the repo alone.
--
-- TABLE NAME. This script previously created `dbo.SupplierInfo`, a name no live
-- artifact has ever read. Both the current Copy activity
-- (`bronze_copy_supplier_ref`) and the dataflow it replaced read `dbo.supplier_ref`,
-- so the DDL was creating an object the pipeline would never ingest. Corrected to
-- the name the pipeline actually reads.

IF OBJECT_ID('dbo.supplier_ref') IS NOT NULL DROP TABLE dbo.supplier_ref;
CREATE TABLE dbo.supplier_ref (
    SupplierName NVARCHAR(200),
    HeadquartersCountry NVARCHAR(100),
    ProductionCountry NVARCHAR(100),
    Region NVARCHAR(100)
);
