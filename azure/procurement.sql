-- azure/procurement.sql
-- DDL for dbo.procurement_transactional  (LOAD ORDER: step 1 of 2)
--
--   step 1  azure/procurement.sql       -- THIS FILE: drops + creates the table
--   step 2  azure/procurement_seed.sql  -- inserts the 132 transaction rows
--
-- DESTRUCTIVE. The DROP clears the table. Always run step 2 straight after step 1;
-- together they rebuild the Azure SQL source from the repo alone.
--
-- TABLE NAME. This script previously created `dbo.Procurement`, a name no live
-- artifact has ever read. Both the current Copy activity
-- (`bronze_copy_procurement_transactional`) and the dataflow it replaced read
-- `dbo.procurement_transactional`, so the DDL was creating an object the pipeline
-- would never ingest. Corrected to the name the pipeline actually reads.
--
-- COLUMN TYPES. `Quantity` and `UnitPriceEUR` are declared DECIMAL(18,2), matching
-- the documented contract in the spec and docs/schemas/bronze_tables.md. The live
-- column is currently a 4-byte float, which is why bronze shows values like
-- 18.670000076293945 for a price of 18.67; see azure/procurement_seed.sql.

IF OBJECT_ID('dbo.procurement_transactional') IS NOT NULL DROP TABLE dbo.procurement_transactional;
CREATE TABLE dbo.procurement_transactional (
    [Date] DATE,
    MaterialName NVARCHAR(100),
    SupplierName NVARCHAR(200),
    Region NVARCHAR(100),
    Quantity DECIMAL(18,2),
    Unit NVARCHAR(50),
    UnitPriceEUR DECIMAL(18,2)
);
