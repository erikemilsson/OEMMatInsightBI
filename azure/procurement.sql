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
-- the documented contract in the spec and docs/schemas/bronze_tables.md. DEC-016
-- (2026-08-12, Option B-minimal) RATIFIED these declarations — they are the contract,
-- and this file is not to be edited to match whatever the live table happens to hold.
--
-- The live column is currently SMALLINT / FLOAT, a hand-created shape that predates
-- this file. FLOAT with no length is FLOAT(53) — an 8-byte double, NOT a 4-byte float.
-- (T-SQL REAL is the 4-byte type: REAL = FLOAT(24). Microsoft Learn, "float and real
-- (Transact-SQL)": "The ISO synonym for real is float(24)".) An earlier version of this
-- comment and DEC-015 both said "4-byte float"; that was wrong, and it mattered — a fix
-- built on that premise would have declared REAL, which lands as Spark `float` and would
-- have broken silver from the opposite side. The 18.670000076293945-style values are
-- float32 rounding error already baked into the stored numbers, held in an 8-byte
-- column; see azure/procurement_seed.sql.
--
-- RUNNING THIS FILE CHANGES BRONZE'S DELTA TYPES from short/double to decimal(18,2).
-- That is intended under DEC-016, but it is only safe once bronze_to_silver's
-- decimal(18,2) casts + overwriteSchema (task-069) are DEPLOYED and the next silver run
-- is p_full_load=true. Running it before that reproduces the 2026-08-12
-- DELTA_FAILED_TO_MERGE_FIELDS outage. Order: deploy the notebook, run full-load, then
-- run this DDL + seed, then run a normal scheduled (incremental) run to prove the append.

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
