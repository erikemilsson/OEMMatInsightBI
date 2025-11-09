-- =====================================================================
-- DATA QUALITY SUMMARY VIEWS FOR POWER BI
-- =====================================================================
-- These views create aggregated quality metrics that are optimized
-- for Power BI visualizations in the data quality dashboard.
--
-- Run this script in the oem_wh warehouse after gold layer loads
-- =====================================================================

-- =====================================================================
-- VIEW 1: Quality Summary Statistics
-- =====================================================================
-- Provides high-level KPIs for the executive summary

CREATE OR REPLACE VIEW dbo.v_quality_summary AS
SELECT
    -- Procurement quality
    COUNT(*) FILTER (WHERE source_table = 'fact_procurement') as total_procurement_records,
    AVG(data_quality_score) FILTER (WHERE source_table = 'fact_procurement') as avg_procurement_score,
    COUNT(*) FILTER (WHERE source_table = 'fact_procurement' AND quality_category = 'High') as high_quality_procurement,
    COUNT(*) FILTER (WHERE source_table = 'fact_procurement' AND quality_category = 'Medium') as medium_quality_procurement,
    COUNT(*) FILTER (WHERE source_table = 'fact_procurement' AND quality_category = 'Low') as low_quality_procurement,
    COUNT(*) FILTER (WHERE source_table = 'fact_procurement' AND quality_category = 'Unmapped') as unmapped_procurement,

    -- Supply quality
    COUNT(*) FILTER (WHERE source_table = 'fact_supply_share') as total_supply_records,
    AVG(data_quality_score) FILTER (WHERE source_table = 'fact_supply_share') as avg_supply_score,
    COUNT(*) FILTER (WHERE source_table = 'fact_supply_share' AND quality_category = 'High') as high_quality_supply,
    COUNT(*) FILTER (WHERE source_table = 'fact_supply_share' AND quality_category = 'Medium') as medium_quality_supply,
    COUNT(*) FILTER (WHERE source_table = 'fact_supply_share' AND quality_category = 'Low') as low_quality_supply,
    COUNT(*) FILTER (WHERE source_table = 'fact_supply_share' AND quality_category = 'Unmapped') as unmapped_supply,

    -- Overall metrics
    COUNT(*) as total_records,
    AVG(data_quality_score) as overall_avg_score,
    CURRENT_TIMESTAMP as snapshot_time
FROM (
    SELECT
        'fact_procurement' as source_table,
        data_quality_score,
        quality_category
    FROM dbo.fact_procurement

    UNION ALL

    SELECT
        'fact_supply_share' as source_table,
        data_quality_score,
        quality_category
    FROM dbo.fact_supply_share
) combined;

-- =====================================================================
-- VIEW 2: Quality Distribution by Category
-- =====================================================================
-- For donut/pie charts showing quality breakdown

CREATE OR REPLACE VIEW dbo.v_quality_distribution AS
SELECT
    source_table,
    quality_category,
    COUNT(*) as record_count,
    AVG(data_quality_score) as avg_score,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY source_table), 2) as pct_of_total
FROM (
    SELECT
        'Procurement' as source_table,
        quality_category,
        data_quality_score
    FROM dbo.fact_procurement

    UNION ALL

    SELECT
        'Supply Share' as source_table,
        quality_category,
        data_quality_score
    FROM dbo.fact_supply_share
) combined
GROUP BY source_table, quality_category;

-- =====================================================================
-- VIEW 3: Quality Score Bands
-- =====================================================================
-- For histogram showing distribution of quality scores

CREATE OR REPLACE VIEW dbo.v_quality_score_bands AS
SELECT
    source_table,
    score_band,
    COUNT(*) as record_count,
    MIN(data_quality_score) as min_score,
    MAX(data_quality_score) as max_score,
    AVG(data_quality_score) as avg_score
FROM (
    SELECT
        'Procurement' as source_table,
        data_quality_score,
        CASE
            WHEN data_quality_score >= 0.95 THEN '0.95 - 1.00 (Excellent)'
            WHEN data_quality_score >= 0.90 THEN '0.90 - 0.95 (Very Good)'
            WHEN data_quality_score >= 0.80 THEN '0.80 - 0.90 (Good)'
            WHEN data_quality_score >= 0.70 THEN '0.70 - 0.80 (Fair)'
            WHEN data_quality_score >= 0.50 THEN '0.50 - 0.70 (Low)'
            ELSE '< 0.50 (Poor)'
        END as score_band
    FROM dbo.fact_procurement

    UNION ALL

    SELECT
        'Supply Share' as source_table,
        data_quality_score,
        CASE
            WHEN data_quality_score >= 0.95 THEN '0.95 - 1.00 (Excellent)'
            WHEN data_quality_score >= 0.90 THEN '0.90 - 0.95 (Very Good)'
            WHEN data_quality_score >= 0.80 THEN '0.80 - 0.90 (Good)'
            WHEN data_quality_score >= 0.70 THEN '0.70 - 0.80 (Fair)'
            WHEN data_quality_score >= 0.50 THEN '0.50 - 0.70 (Low)'
            ELSE '< 0.50 (Poor)'
        END as score_band
    FROM dbo.fact_supply_share
) combined
GROUP BY source_table, score_band;

-- =====================================================================
-- VIEW 4: Top Unmapped Values
-- =====================================================================
-- Shows most frequent unmapped values for prioritization

CREATE OR REPLACE VIEW dbo.v_top_unmapped_values AS
SELECT
    unmapped_dimension,
    original_value,
    COUNT(*) as occurrence_count,
    SUM(business_impact) as total_impact
FROM (
    -- Procurement unmapped values
    SELECT
        unmapped_type as unmapped_dimension,
        COALESCE(original_material, original_hq_country, original_prod_country) as original_value,
        1 as business_impact  -- Could be enhanced with spend amounts
    FROM dbo.gold_unmapped_procurement_audit

    UNION ALL

    -- Supply share unmapped values
    SELECT
        unmapped_dimension,
        COALESCE(original_material, original_country) as original_value,
        COALESCE(share_pct, 0) as business_impact
    FROM dbo.gold_unmapped_supply_audit
) combined
GROUP BY unmapped_dimension, original_value;

-- =====================================================================
-- VIEW 5: Quality Impact by Dimension
-- =====================================================================
-- Shows quality by material, country, etc.

CREATE OR REPLACE VIEW dbo.v_quality_by_material AS
SELECT
    m.material_name_std,
    m.commodity_group,
    COUNT(*) as usage_count,
    AVG(fp.data_quality_score) as avg_quality_score,
    SUM(fp.spend_eur) as total_spend,
    ROUND(AVG(fp.data_quality_score) * 100, 1) as quality_pct,
    CASE
        WHEN AVG(fp.data_quality_score) >= 0.90 THEN 'High'
        WHEN AVG(fp.data_quality_score) >= 0.70 THEN 'Medium'
        WHEN AVG(fp.data_quality_score) >= 0.50 THEN 'Low'
        ELSE 'Unmapped'
    END as quality_level
FROM dbo.fact_procurement fp
JOIN dbo.gold_dim_material m ON fp.material_key = m.material_key
GROUP BY m.material_name_std, m.commodity_group;

CREATE OR REPLACE VIEW dbo.v_quality_by_country AS
SELECT
    c.country_name_std,
    c.iso3,
    c.region,
    COUNT(*) as usage_count,
    AVG(fp.data_quality_score) as avg_quality_score,
    SUM(fp.spend_eur) as total_spend,
    ROUND(AVG(fp.data_quality_score) * 100, 1) as quality_pct,
    CASE
        WHEN AVG(fp.data_quality_score) >= 0.90 THEN 'High'
        WHEN AVG(fp.data_quality_score) >= 0.70 THEN 'Medium'
        WHEN AVG(fp.data_quality_score) >= 0.50 THEN 'Low'
        ELSE 'Unmapped'
    END as quality_level
FROM dbo.fact_procurement fp
JOIN dbo.gold_dim_country c ON fp.supplier_hq_country_key = c.country_key
GROUP BY c.country_name_std, c.iso3, c.region;

-- =====================================================================
-- VIEW 6: Alias Statistics
-- =====================================================================
-- Shows alias coverage and confidence distribution

CREATE OR REPLACE VIEW dbo.v_alias_statistics AS
SELECT
    dimension_name,
    match_type,
    confidence_band,
    COUNT(*) as alias_count,
    AVG(confidence) as avg_confidence
FROM (
    -- Country aliases
    SELECT
        'Country' as dimension_name,
        match_type,
        confidence,
        CASE
            WHEN confidence >= 0.95 THEN '0.95 - 1.00 (Excellent)'
            WHEN confidence >= 0.90 THEN '0.90 - 0.95 (Very Good)'
            WHEN confidence >= 0.85 THEN '0.85 - 0.90 (Good)'
            WHEN confidence >= 0.80 THEN '0.80 - 0.85 (Fair)'
            ELSE '< 0.80 (Low)'
        END as confidence_band
    FROM dbo.mapping_country_aliases_confidence

    UNION ALL

    -- Material aliases
    SELECT
        'Material' as dimension_name,
        match_type,
        confidence,
        CASE
            WHEN confidence >= 0.95 THEN '0.95 - 1.00 (Excellent)'
            WHEN confidence >= 0.90 THEN '0.90 - 0.95 (Very Good)'
            WHEN confidence >= 0.85 THEN '0.85 - 0.90 (Good)'
            WHEN confidence >= 0.80 THEN '0.80 - 0.85 (Fair)'
            ELSE '< 0.80 (Low)'
        END as confidence_band
    FROM dbo.mapping_material_aliases_confidence
) combined
GROUP BY dimension_name, match_type, confidence_band;

-- =====================================================================
-- VIEW 7: Quality Trend Over Time
-- =====================================================================
-- For line charts showing quality improvement over time

CREATE OR REPLACE VIEW dbo.v_quality_trend AS
SELECT
    d.year,
    d.month,
    d.month_name,
    d.quarter,
    COUNT(*) as record_count,
    AVG(fp.data_quality_score) as avg_quality_score,
    COUNT(*) FILTER (WHERE fp.quality_category = 'High') as high_quality_count,
    ROUND(COUNT(*) FILTER (WHERE fp.quality_category = 'High') * 100.0 / COUNT(*), 2) as high_quality_pct
FROM dbo.fact_procurement fp
JOIN dbo.gold_dim_date d ON fp.date_key = d.date_key
GROUP BY d.year, d.month, d.month_name, d.quarter
ORDER BY d.year, d.month;

-- =====================================================================
-- VIEW 8: Quality Issues Summary
-- =====================================================================
-- Prioritized list of quality improvement opportunities

CREATE OR REPLACE VIEW dbo.v_quality_issues AS
SELECT
    issue_type,
    issue_description,
    record_count,
    business_impact,
    CASE
        WHEN record_count > total_records * 0.05 THEN 'HIGH'
        WHEN record_count > total_records * 0.02 THEN 'MEDIUM'
        ELSE 'LOW'
    END as priority,
    recommended_action
FROM (
    SELECT
        'Unmapped Procurement' as issue_type,
        'Records with unmapped materials or countries' as issue_description,
        COUNT(*) as record_count,
        (SELECT COUNT(*) FROM dbo.fact_procurement) as total_records,
        0 as business_impact,  -- Could be enhanced
        'Add aliases for top unmapped values' as recommended_action
    FROM dbo.gold_unmapped_procurement_audit

    UNION ALL

    SELECT
        'Unmapped Supply Share' as issue_type,
        'Supply share records with unmapped values' as issue_description,
        COUNT(*) as record_count,
        (SELECT COUNT(*) FROM dbo.fact_supply_share) as total_records,
        SUM(share_pct) as business_impact,
        'Prioritize countries/materials with high supply share' as recommended_action
    FROM dbo.gold_unmapped_supply_audit

    UNION ALL

    SELECT
        'Low Confidence Matches' as issue_type,
        'Records with quality score < 0.80' as issue_description,
        COUNT(*) as record_count,
        (SELECT COUNT(*) FROM dbo.fact_procurement) as total_records,
        0 as business_impact,
        'Review and improve low-confidence aliases' as recommended_action
    FROM dbo.fact_procurement
    WHERE data_quality_score < 0.80
) issues
WHERE record_count > 0;

-- =====================================================================
-- GRANT PERMISSIONS
-- =====================================================================
-- Ensure Power BI can read these views

-- Note: Adjust permissions as needed for your security model
-- GRANT SELECT ON dbo.v_quality_summary TO [PowerBI_Users];
-- GRANT SELECT ON dbo.v_quality_distribution TO [PowerBI_Users];
-- etc.

-- =====================================================================
-- END OF QUALITY VIEWS
-- =====================================================================
