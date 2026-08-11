-- azure/procurement_seed.sql
-- Seed data for dbo.procurement_transactional  (LOAD ORDER: step 2 of 2 for this table)
--
--   step 1  azure/procurement.sql       -- DDL: drops + creates dbo.procurement_transactional
--   step 2  azure/procurement_seed.sql  -- THIS FILE: inserts the 132 transaction rows
--
-- WHY A LITERAL DUMP AND NOT A GENERATOR
-- The transactional table is only 132 rows (11 materials x 12 monthly dates).
-- At that size a literal dump reproduces the source EXACTLY, whereas a seeded
-- generator would only reproduce it plausibly -- and would have to hard-code the
-- same curated structure anyway (one supplier per material, the kg/pcs split, the
-- transposed dates). Exact beats plausible; there is also no RNG to pin, so the
-- determinism question does not arise.
--
-- THE DATES LOOK WRONG ON PURPOSE -- DO NOT "FIX" THEM
-- The source system stores each date with its DAY and YEAR components transposed:
-- raw '2028-02-24' means 2024-02-28. Bronze lands this raw value untouched (a Copy
-- activity cannot transform) and `bronze_to_silver` corrects it via
-- make_date(day+2000, month, year-2000). See src/transformations/procurement_dates.py.
-- Writing corrected dates here would double-correct downstream and silently break
-- every date in silver and gold. The 12 raw dates below are the 12 month-end
-- dates of calendar 2024 after correction.
--
-- Provenance: exported from oem_lh.bronze_procurement_transactional (Delta version
-- 101) on 2026-08-11. Bronze is a byte-faithful full-load Copy of
-- dbo.procurement_transactional, so these values are the source values.
--
-- ONE DELIBERATE DIVERGENCE FROM THE LIVE COLUMN: UnitPriceEUR is written here at
-- 2 decimal places, matching the DECIMAL(18,2) declared in the DDL. The live
-- column is a 4-byte float, so the exported values carry float32 noise
-- (18.67 lands as 18.670000076293945). All 132 exported values were verified to be
-- the exact float32 image of their 2-decimal value (max abs diff 0.0), so rounding
-- recovers the intended figure rather than losing information. A rebuild from this
-- file therefore yields clean decimals where the current live table yields noisy
-- floats; the values are identical to the cent.
--
-- Row order is sorted by (MaterialName, Date) for a readable diff. The table has no
-- primary key and no downstream logic depends on physical row order.
--
-- Contains DATA ONLY. No connection strings, logins or credentials -- those stay
-- in the Fabric connection `oem_azuresql_procurement` (and /secure, gitignored).
--
-- Re-runnable: the DELETE makes a repeat run idempotent.

DELETE FROM dbo.procurement_transactional;

INSERT INTO dbo.procurement_transactional
    ([Date], MaterialName, SupplierName, Region, Quantity, Unit, UnitPriceEUR)
VALUES
    ('2028-02-24', N'Aluminum', N'EuroAl Industries', N'EU', 2667.00, N'kg', 2.47),
    ('2030-04-24', N'Aluminum', N'EuroAl Industries', N'EU', 2559.00, N'kg', 2.11),
    ('2030-06-24', N'Aluminum', N'EuroAl Industries', N'EU', 2663.00, N'kg', 2.08),
    ('2030-09-24', N'Aluminum', N'EuroAl Industries', N'EU', 2692.00, N'kg', 2.46),
    ('2030-11-24', N'Aluminum', N'EuroAl Industries', N'EU', 2275.00, N'kg', 2.37),
    ('2031-01-24', N'Aluminum', N'EuroAl Industries', N'EU', 2318.00, N'kg', 2.24),
    ('2031-03-24', N'Aluminum', N'EuroAl Industries', N'EU', 2329.00, N'kg', 2.39),
    ('2031-05-24', N'Aluminum', N'EuroAl Industries', N'EU', 2698.00, N'kg', 2.33),
    ('2031-07-24', N'Aluminum', N'EuroAl Industries', N'EU', 2310.00, N'kg', 2.17),
    ('2031-08-24', N'Aluminum', N'EuroAl Industries', N'EU', 2272.00, N'kg', 2.49),
    ('2031-10-24', N'Aluminum', N'EuroAl Industries', N'EU', 2554.00, N'kg', 2.27),
    ('2031-12-24', N'Aluminum', N'EuroAl Industries', N'EU', 2465.00, N'kg', 2.30),
    ('2028-02-24', N'Cobalt', N'CongoMetals Ltd', N'AF', 311.00, N'kg', 40.30),
    ('2030-04-24', N'Cobalt', N'CongoMetals Ltd', N'AF', 284.00, N'kg', 41.76),
    ('2030-06-24', N'Cobalt', N'CongoMetals Ltd', N'AF', 281.00, N'kg', 40.94),
    ('2030-09-24', N'Cobalt', N'CongoMetals Ltd', N'AF', 320.00, N'kg', 35.99),
    ('2030-11-24', N'Cobalt', N'CongoMetals Ltd', N'AF', 278.00, N'kg', 38.00),
    ('2031-01-24', N'Cobalt', N'CongoMetals Ltd', N'AF', 296.00, N'kg', 38.73),
    ('2031-03-24', N'Cobalt', N'CongoMetals Ltd', N'AF', 294.00, N'kg', 39.31),
    ('2031-05-24', N'Cobalt', N'CongoMetals Ltd', N'AF', 324.00, N'kg', 35.79),
    ('2031-07-24', N'Cobalt', N'CongoMetals Ltd', N'AF', 326.00, N'kg', 35.92),
    ('2031-08-24', N'Cobalt', N'CongoMetals Ltd', N'AF', 299.00, N'kg', 36.76),
    ('2031-10-24', N'Cobalt', N'CongoMetals Ltd', N'AF', 315.00, N'kg', 37.05),
    ('2031-12-24', N'Cobalt', N'CongoMetals Ltd', N'AF', 292.00, N'kg', 35.63),
    ('2028-02-24', N'Copper', N'AndeanCopper Corp', N'SA', 818.00, N'kg', 9.04),
    ('2030-04-24', N'Copper', N'AndeanCopper Corp', N'SA', 945.00, N'kg', 8.23),
    ('2030-06-24', N'Copper', N'AndeanCopper Corp', N'SA', 950.00, N'kg', 9.53),
    ('2030-09-24', N'Copper', N'AndeanCopper Corp', N'SA', 921.00, N'kg', 8.96),
    ('2030-11-24', N'Copper', N'AndeanCopper Corp', N'SA', 878.00, N'kg', 8.33),
    ('2031-01-24', N'Copper', N'AndeanCopper Corp', N'SA', 892.00, N'kg', 8.02),
    ('2031-03-24', N'Copper', N'AndeanCopper Corp', N'SA', 833.00, N'kg', 8.41),
    ('2031-05-24', N'Copper', N'AndeanCopper Corp', N'SA', 928.00, N'kg', 9.12),
    ('2031-07-24', N'Copper', N'AndeanCopper Corp', N'SA', 923.00, N'kg', 9.52),
    ('2031-08-24', N'Copper', N'AndeanCopper Corp', N'SA', 969.00, N'kg', 8.97),
    ('2031-10-24', N'Copper', N'AndeanCopper Corp', N'SA', 868.00, N'kg', 9.46),
    ('2031-12-24', N'Copper', N'AndeanCopper Corp', N'SA', 972.00, N'kg', 9.24),
    ('2028-02-24', N'Electronics (controllers, sensors)', N'MicroTech Pte Ltd', N'APAC', 3231.00, N'pcs', 44.69),
    ('2030-04-24', N'Electronics (controllers, sensors)', N'MicroTech Pte Ltd', N'APAC', 3192.00, N'pcs', 46.60),
    ('2030-06-24', N'Electronics (controllers, sensors)', N'MicroTech Pte Ltd', N'APAC', 3221.00, N'pcs', 48.97),
    ('2030-09-24', N'Electronics (controllers, sensors)', N'MicroTech Pte Ltd', N'APAC', 2862.00, N'pcs', 49.39),
    ('2030-11-24', N'Electronics (controllers, sensors)', N'MicroTech Pte Ltd', N'APAC', 3109.00, N'pcs', 46.79),
    ('2031-01-24', N'Electronics (controllers, sensors)', N'MicroTech Pte Ltd', N'APAC', 2796.00, N'pcs', 47.16),
    ('2031-03-24', N'Electronics (controllers, sensors)', N'MicroTech Pte Ltd', N'APAC', 3068.00, N'pcs', 42.21),
    ('2031-05-24', N'Electronics (controllers, sensors)', N'MicroTech Pte Ltd', N'APAC', 2973.00, N'pcs', 43.40),
    ('2031-07-24', N'Electronics (controllers, sensors)', N'MicroTech Pte Ltd', N'APAC', 3120.00, N'pcs', 42.43),
    ('2031-08-24', N'Electronics (controllers, sensors)', N'MicroTech Pte Ltd', N'APAC', 2724.00, N'pcs', 47.79),
    ('2031-10-24', N'Electronics (controllers, sensors)', N'MicroTech Pte Ltd', N'APAC', 2847.00, N'pcs', 42.65),
    ('2031-12-24', N'Electronics (controllers, sensors)', N'MicroTech Pte Ltd', N'APAC', 3293.00, N'pcs', 44.23),
    ('2028-02-24', N'Graphite', N'SinoGraphite Co.', N'APAC', 1356.00, N'kg', 6.89),
    ('2030-04-24', N'Graphite', N'SinoGraphite Co.', N'APAC', 1466.00, N'kg', 6.72),
    ('2030-06-24', N'Graphite', N'SinoGraphite Co.', N'APAC', 1427.00, N'kg', 6.97),
    ('2030-09-24', N'Graphite', N'SinoGraphite Co.', N'APAC', 1429.00, N'kg', 7.06),
    ('2030-11-24', N'Graphite', N'SinoGraphite Co.', N'APAC', 1491.00, N'kg', 6.90),
    ('2031-01-24', N'Graphite', N'SinoGraphite Co.', N'APAC', 1426.00, N'kg', 6.72),
    ('2031-03-24', N'Graphite', N'SinoGraphite Co.', N'APAC', 1642.00, N'kg', 6.79),
    ('2031-05-24', N'Graphite', N'SinoGraphite Co.', N'APAC', 1467.00, N'kg', 6.60),
    ('2031-07-24', N'Graphite', N'SinoGraphite Co.', N'APAC', 1481.00, N'kg', 7.71),
    ('2031-08-24', N'Graphite', N'SinoGraphite Co.', N'APAC', 1532.00, N'kg', 7.55),
    ('2031-10-24', N'Graphite', N'SinoGraphite Co.', N'APAC', 1524.00, N'kg', 6.92),
    ('2031-12-24', N'Graphite', N'SinoGraphite Co.', N'APAC', 1632.00, N'kg', 7.92),
    ('2028-02-24', N'Lithium', N'AltMiner SA', N'NA', 770.00, N'kg', 58.78),
    ('2030-04-24', N'Lithium', N'AltMiner SA', N'NA', 729.00, N'kg', 60.17),
    ('2030-06-24', N'Lithium', N'AltMiner SA', N'NA', 834.00, N'kg', 65.79),
    ('2030-09-24', N'Lithium', N'AltMiner SA', N'NA', 856.00, N'kg', 64.29),
    ('2030-11-24', N'Lithium', N'AltMiner SA', N'NA', 849.00, N'kg', 68.75),
    ('2031-01-24', N'Lithium', N'AltMiner SA', N'NA', 828.00, N'kg', 69.85),
    ('2031-03-24', N'Lithium', N'AltMiner SA', N'NA', 750.00, N'kg', 62.90),
    ('2031-05-24', N'Lithium', N'AltMiner SA', N'NA', 879.00, N'kg', 60.53),
    ('2031-07-24', N'Lithium', N'AltMiner SA', N'NA', 743.00, N'kg', 64.61),
    ('2031-08-24', N'Lithium', N'AltMiner SA', N'NA', 753.00, N'kg', 65.67),
    ('2031-10-24', N'Lithium', N'AltMiner SA', N'NA', 841.00, N'kg', 66.91),
    ('2031-12-24', N'Lithium', N'AltMiner SA', N'NA', 875.00, N'kg', 65.65),
    ('2028-02-24', N'Nickel', N'MetaWorks GmbH', N'EU', 1139.00, N'kg', 19.04),
    ('2030-04-24', N'Nickel', N'MetaWorks GmbH', N'EU', 1137.00, N'kg', 17.19),
    ('2030-06-24', N'Nickel', N'MetaWorks GmbH', N'EU', 1317.00, N'kg', 20.16),
    ('2030-09-24', N'Nickel', N'MetaWorks GmbH', N'EU', 1255.00, N'kg', 17.45),
    ('2030-11-24', N'Nickel', N'MetaWorks GmbH', N'EU', 1257.00, N'kg', 17.96),
    ('2031-01-24', N'Nickel', N'MetaWorks GmbH', N'EU', 1137.00, N'kg', 18.67),
    ('2031-03-24', N'Nickel', N'MetaWorks GmbH', N'EU', 1312.00, N'kg', 19.39),
    ('2031-05-24', N'Nickel', N'MetaWorks GmbH', N'EU', 1269.00, N'kg', 17.74),
    ('2031-07-24', N'Nickel', N'MetaWorks GmbH', N'EU', 1258.00, N'kg', 19.32),
    ('2031-08-24', N'Nickel', N'MetaWorks GmbH', N'EU', 1132.00, N'kg', 18.14),
    ('2031-10-24', N'Nickel', N'MetaWorks GmbH', N'EU', 1145.00, N'kg', 19.10),
    ('2031-12-24', N'Nickel', N'MetaWorks GmbH', N'EU', 1101.00, N'kg', 17.31),
    ('2028-02-24', N'Plastic (ABS)', N'PolyChem BV', N'EU', 2114.00, N'kg', 1.48),
    ('2030-04-24', N'Plastic (ABS)', N'PolyChem BV', N'EU', 2066.00, N'kg', 1.63),
    ('2030-06-24', N'Plastic (ABS)', N'PolyChem BV', N'EU', 2371.00, N'kg', 1.59),
    ('2030-09-24', N'Plastic (ABS)', N'PolyChem BV', N'EU', 2418.00, N'kg', 1.36),
    ('2030-11-24', N'Plastic (ABS)', N'PolyChem BV', N'EU', 2279.00, N'kg', 1.64),
    ('2031-01-24', N'Plastic (ABS)', N'PolyChem BV', N'EU', 2133.00, N'kg', 1.54),
    ('2031-03-24', N'Plastic (ABS)', N'PolyChem BV', N'EU', 2127.00, N'kg', 1.43),
    ('2031-05-24', N'Plastic (ABS)', N'PolyChem BV', N'EU', 2076.00, N'kg', 1.38),
    ('2031-07-24', N'Plastic (ABS)', N'PolyChem BV', N'EU', 2250.00, N'kg', 1.61),
    ('2031-08-24', N'Plastic (ABS)', N'PolyChem BV', N'EU', 2313.00, N'kg', 1.38),
    ('2031-10-24', N'Plastic (ABS)', N'PolyChem BV', N'EU', 2371.00, N'kg', 1.64),
    ('2031-12-24', N'Plastic (ABS)', N'PolyChem BV', N'EU', 2093.00, N'kg', 1.35),
    ('2028-02-24', N'Rare Earths (NdPr)', N'REE Global Inc.', N'APAC', 128.00, N'kg', 82.92),
    ('2030-04-24', N'Rare Earths (NdPr)', N'REE Global Inc.', N'APAC', 118.00, N'kg', 89.50),
    ('2030-06-24', N'Rare Earths (NdPr)', N'REE Global Inc.', N'APAC', 128.00, N'kg', 83.21),
    ('2030-09-24', N'Rare Earths (NdPr)', N'REE Global Inc.', N'APAC', 123.00, N'kg', 91.72),
    ('2030-11-24', N'Rare Earths (NdPr)', N'REE Global Inc.', N'APAC', 121.00, N'kg', 88.13),
    ('2031-01-24', N'Rare Earths (NdPr)', N'REE Global Inc.', N'APAC', 119.00, N'kg', 89.59),
    ('2031-03-24', N'Rare Earths (NdPr)', N'REE Global Inc.', N'APAC', 130.00, N'kg', 89.36),
    ('2031-05-24', N'Rare Earths (NdPr)', N'REE Global Inc.', N'APAC', 120.00, N'kg', 88.22),
    ('2031-07-24', N'Rare Earths (NdPr)', N'REE Global Inc.', N'APAC', 112.00, N'kg', 84.50),
    ('2031-08-24', N'Rare Earths (NdPr)', N'REE Global Inc.', N'APAC', 120.00, N'kg', 91.86),
    ('2031-10-24', N'Rare Earths (NdPr)', N'REE Global Inc.', N'APAC', 129.00, N'kg', 77.68),
    ('2031-12-24', N'Rare Earths (NdPr)', N'REE Global Inc.', N'APAC', 108.00, N'kg', 86.01),
    ('2028-02-24', N'Steel (high-tensile)', N'NordicSteel AB', N'EU', 1827.00, N'kg', 1.92),
    ('2030-04-24', N'Steel (high-tensile)', N'NordicSteel AB', N'EU', 1697.00, N'kg', 2.02),
    ('2030-06-24', N'Steel (high-tensile)', N'NordicSteel AB', N'EU', 1628.00, N'kg', 2.02),
    ('2030-09-24', N'Steel (high-tensile)', N'NordicSteel AB', N'EU', 1830.00, N'kg', 1.75),
    ('2030-11-24', N'Steel (high-tensile)', N'NordicSteel AB', N'EU', 1687.00, N'kg', 2.01),
    ('2031-01-24', N'Steel (high-tensile)', N'NordicSteel AB', N'EU', 1736.00, N'kg', 1.79),
    ('2031-03-24', N'Steel (high-tensile)', N'NordicSteel AB', N'EU', 1632.00, N'kg', 2.00),
    ('2031-05-24', N'Steel (high-tensile)', N'NordicSteel AB', N'EU', 1767.00, N'kg', 1.78),
    ('2031-07-24', N'Steel (high-tensile)', N'NordicSteel AB', N'EU', 1841.00, N'kg', 2.00),
    ('2031-08-24', N'Steel (high-tensile)', N'NordicSteel AB', N'EU', 1939.00, N'kg', 2.07),
    ('2031-10-24', N'Steel (high-tensile)', N'NordicSteel AB', N'EU', 1886.00, N'kg', 1.74),
    ('2031-12-24', N'Steel (high-tensile)', N'NordicSteel AB', N'EU', 1649.00, N'kg', 1.91),
    ('2028-02-24', N'Tires (Rubber compound)', N'GlobalRubber SA', N'NA', 579.00, N'pcs', 12.44),
    ('2030-04-24', N'Tires (Rubber compound)', N'GlobalRubber SA', N'NA', 545.00, N'pcs', 12.37),
    ('2030-06-24', N'Tires (Rubber compound)', N'GlobalRubber SA', N'NA', 588.00, N'pcs', 11.62),
    ('2030-09-24', N'Tires (Rubber compound)', N'GlobalRubber SA', N'NA', 587.00, N'pcs', 10.94),
    ('2030-11-24', N'Tires (Rubber compound)', N'GlobalRubber SA', N'NA', 636.00, N'pcs', 11.00),
    ('2031-01-24', N'Tires (Rubber compound)', N'GlobalRubber SA', N'NA', 588.00, N'pcs', 13.13),
    ('2031-03-24', N'Tires (Rubber compound)', N'GlobalRubber SA', N'NA', 588.00, N'pcs', 12.79),
    ('2031-05-24', N'Tires (Rubber compound)', N'GlobalRubber SA', N'NA', 572.00, N'pcs', 13.20),
    ('2031-07-24', N'Tires (Rubber compound)', N'GlobalRubber SA', N'NA', 555.00, N'pcs', 13.15),
    ('2031-08-24', N'Tires (Rubber compound)', N'GlobalRubber SA', N'NA', 603.00, N'pcs', 11.12),
    ('2031-10-24', N'Tires (Rubber compound)', N'GlobalRubber SA', N'NA', 582.00, N'pcs', 12.91),
    ('2031-12-24', N'Tires (Rubber compound)', N'GlobalRubber SA', N'NA', 547.00, N'pcs', 12.97);

IF (SELECT COUNT(*) FROM dbo.procurement_transactional) <> 132
    THROW 50002, 'procurement_transactional seed did not land 132 rows', 1;
