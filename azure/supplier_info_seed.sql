-- azure/supplier_info_seed.sql
-- Seed data for dbo.supplier_ref  (LOAD ORDER: step 2 of 2 for this table)
--
--   step 1  azure/supplier_info.sql       -- DDL: drops + creates dbo.supplier_ref
--   step 2  azure/supplier_info_seed.sql  -- THIS FILE: inserts the 11 reference rows
--
-- Supplier master data: reference data, low cardinality, stable. Committed as a
-- literal INSERT so a fresh clone reproduces the source EXACTLY -- no RNG, no seed
-- to pin, and the rows review as plain text in a diff.
--
-- Provenance: exported from the lakehouse table oem_lh.bronze_supplier_ref
-- (Delta version 99) on 2026-08-11. Bronze is a byte-faithful full-load Copy of
-- dbo.supplier_ref, so these values are the source values.
--
-- Contains DATA ONLY. No connection strings, logins or credentials -- those stay
-- in the Fabric connection `oem_azuresql_procurement` (and /secure, gitignored).
--
-- Re-runnable: the DELETE makes a repeat run idempotent.

DELETE FROM dbo.supplier_ref;

INSERT INTO dbo.supplier_ref
    (SupplierName, HeadquartersCountry, ProductionCountry, Region)
VALUES
    (N'AltMiner SA', N'Canada', N'Chile', N'NA/SA'),
    (N'AndeanCopper Corp', N'Chile', N'Chile', N'SA'),
    (N'CongoMetals Ltd', N'DRC (HQ in South Africa)', N'DRC', N'AF'),
    (N'EuroAl Industries', N'France', N'France', N'EU'),
    (N'GlobalRubber SA', N'USA', N'Mexico', N'NA'),
    (N'MetaWorks GmbH', N'Germany', N'Germany', N'EU'),
    (N'MicroTech Pte Ltd', N'Singapore', N'Malaysia', N'APAC'),
    (N'NordicSteel AB', N'Sweden', N'Sweden', N'EU'),
    (N'PolyChem BV', N'Netherlands', N'Netherlands', N'EU'),
    (N'REE Global Inc.', N'Singapore', N'China', N'APAC'),
    (N'SinoGraphite Co.', N'China', N'China', N'APAC');

IF (SELECT COUNT(*) FROM dbo.supplier_ref) <> 11
    THROW 50001, 'supplier_ref seed did not land 11 rows', 1;
