-- ============================================================================
-- warehouse_indexes.sql — OEMMatInsightBI Warehouse Index DDL
-- ============================================================================
-- Purpose:
--   Improves join + filter performance on the SQL analytics endpoint
--   (Warehouse, type "Warehouse" — the second "oem_lh"-named item, NOT the
--   Lakehouse). Adds:
--     1. Clustered rowstore indexes on the surrogate-key (PK) columns of
--        gold_dim_country, gold_dim_material, gold_dim_indicator.
--     2. Nonclustered indexes on the fact-table foreign-key columns that
--        point back to those three dims.
--     3. UPDATE STATISTICS for every indexed table so the query optimizer
--        sees fresh cardinality after the indexes land.
--
-- Target tables (all in [dbo]):
--   Dims : gold_dim_country, gold_dim_material, gold_dim_indicator
--   Facts: fact_procurement, fact_epi_score, fact_supply_share
--
-- Deploy (Erik's step — task-012_4 AC5):
--   Run this script via the SQL analytics endpoint for the oem_lh Lakehouse
--   (a.k.a. the oem_wh Warehouse connection in some tooling). DDL only — no
--   DML, no data movement. Execute the CREATE statements first, then the
--   UPDATE STATISTICS block at the bottom. Each statement is idempotent-safe
--   via IF EXISTS guards so the script can be re-run.
--
-- Scope note:
--   Only the three dims named in task-012_4 are covered. fact_procurement also
--   carries date_key -> gold_dim_date and fact_supply_share carries stage_key
--   -> gold_dim_stage; those FK indexes are intentionally out of scope here
--   and can be added in a follow-up if the bottleneck analysis (task-012_1)
--   shows they matter.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Clustered indexes on dimension surrogate keys (PKs)
-- ----------------------------------------------------------------------------
-- These columns are bigint, non-NULL by construction, and the join key every
-- fact relies on. A clustered rowstore index suits small dim tables that are
-- looked up by key and scanned in star joins.

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.gold_dim_country') AND name = 'CX_gold_dim_country_country_key')
    CREATE CLUSTERED INDEX CX_gold_dim_country_country_key
        ON dbo.gold_dim_country (country_key);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.gold_dim_material') AND name = 'CX_gold_dim_material_material_key')
    CREATE CLUSTERED INDEX CX_gold_dim_material_material_key
        ON dbo.gold_dim_material (material_key);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.gold_dim_indicator') AND name = 'CX_gold_dim_indicator_indicator_key')
    CREATE CLUSTERED INDEX CX_gold_dim_indicator_indicator_key
        ON dbo.gold_dim_indicator (indicator_key);
GO

-- ----------------------------------------------------------------------------
-- 2. Nonclustered indexes on fact-table foreign keys
-- ----------------------------------------------------------------------------
-- One index per FK column that references the three scoped dims. Separate
-- single-column indexes (not composite) because the joins are independent
-- and the optimizer can pick any one for a star-join plan.

-- fact_procurement: material_key -> gold_dim_material
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.fact_procurement') AND name = 'IX_fact_procurement_material_key')
    CREATE NONCLUSTERED INDEX IX_fact_procurement_material_key
        ON dbo.fact_procurement (material_key);
GO

-- fact_procurement: supplier_hq_country_key -> gold_dim_country
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.fact_procurement') AND name = 'IX_fact_procurement_supplier_hq_country_key')
    CREATE NONCLUSTERED INDEX IX_fact_procurement_supplier_hq_country_key
        ON dbo.fact_procurement (supplier_hq_country_key);
GO

-- fact_procurement: production_country_key -> gold_dim_country
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.fact_procurement') AND name = 'IX_fact_procurement_production_country_key')
    CREATE NONCLUSTERED INDEX IX_fact_procurement_production_country_key
        ON dbo.fact_procurement (production_country_key);
GO

-- fact_epi_score: country_key -> gold_dim_country
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.fact_epi_score') AND name = 'IX_fact_epi_score_country_key')
    CREATE NONCLUSTERED INDEX IX_fact_epi_score_country_key
        ON dbo.fact_epi_score (country_key);
GO

-- fact_epi_score: indicator_key -> gold_dim_indicator
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.fact_epi_score') AND name = 'IX_fact_epi_score_indicator_key')
    CREATE NONCLUSTERED INDEX IX_fact_epi_score_indicator_key
        ON dbo.fact_epi_score (indicator_key);
GO

-- fact_supply_share: material_key -> gold_dim_material
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.fact_supply_share') AND name = 'IX_fact_supply_share_material_key')
    CREATE NONCLUSTERED INDEX IX_fact_supply_share_material_key
        ON dbo.fact_supply_share (material_key);
GO

-- fact_supply_share: country_key -> gold_dim_country
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.fact_supply_share') AND name = 'IX_fact_supply_share_country_key')
    CREATE NONCLUSTERED INDEX IX_fact_supply_share_country_key
        ON dbo.fact_supply_share (country_key);
GO

-- ----------------------------------------------------------------------------
-- 3. UPDATE STATISTICS for every indexed table
-- ----------------------------------------------------------------------------
-- Run AFTER all CREATE INDEX statements so the optimizer picks up the new
-- index paths immediately. WITH FULLSCAN gives the most accurate cardinality
-- for these small-to-mid portfolio-scale tables.

UPDATE STATISTICS dbo.gold_dim_country WITH FULLSCAN;
GO
UPDATE STATISTICS dbo.gold_dim_material WITH FULLSCAN;
GO
UPDATE STATISTICS dbo.gold_dim_indicator WITH FULLSCAN;
GO
UPDATE STATISTICS dbo.fact_procurement WITH FULLSCAN;
GO
UPDATE STATISTICS dbo.fact_epi_score WITH FULLSCAN;
GO
UPDATE STATISTICS dbo.fact_supply_share WITH FULLSCAN;
GO