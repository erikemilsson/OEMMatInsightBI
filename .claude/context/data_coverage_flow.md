# Data Coverage Flow Visualization

This document explains how data flows through the OEMMatInsightBI pipeline, highlighting where joins occur, where data might be lost, and the business impact of each loss point.

---

## Data Flow Diagram

```mermaid
flowchart TB
    subgraph SOURCE["📦 Source Data"]
        PROC[("fact_procurement<br/>~1000 rows")]
        EPI[("bronze_EPI_2024<br/>~180 countries")]
        WGI[("bronze_WGI<br/>~200 countries")]
    end

    subgraph DIM["📐 Dimension Tables"]
        DIM_C[("gold_dim_country<br/>ISO3 codes")]
        DIM_M[("gold_dim_material<br/>material names")]
    end

    subgraph JOINS["🔗 Join Points"]
        J1["JOIN 1: Procurement → Material<br/>LEFT JOIN on material_name"]
        J2["JOIN 2: Procurement → Country (HQ)<br/>LEFT JOIN on country_name"]
        J3["JOIN 3: Procurement → Country (Prod)<br/>LEFT JOIN on country_name"]
        J4["JOIN 4: EPI → Country<br/>LEFT JOIN on iso3"]
        J5["JOIN 5: WGI → Country<br/>INNER JOIN on iso3<br/>+ HAVING COUNT >= 5"]
    end

    subgraph LOSS["⚠️ Data Loss Points"]
        L1["DLP1: Unmapped Materials<br/>→ Assigned 'Unknown Material'<br/>IMPACT: 0 loss, low confidence"]
        L2["DLP2: Unmapped Countries<br/>→ Assigned 'Unknown Country'<br/>IMPACT: 0 loss, low confidence"]
        L3["DLP3: EPI Country Mismatch<br/>→ Records DROPPED<br/>IMPACT: ~5-20 countries lost"]
        L4["DLP4: WGI Partial Coverage<br/>→ Requires ALL 5 indicators<br/>IMPACT: Partial = No Coverage"]
    end

    subgraph COVERAGE["📊 Coverage Analysis"]
        GAP["gold_data_gaps table"]
        OVERLAP["Coverage Status:<br/>• Full Coverage (EPI + WGI)<br/>• EPI Only<br/>• WGI Only<br/>• No Coverage"]
    end

    %% Flows
    PROC --> J1
    DIM_M --> J1
    J1 --> L1
    L1 --> J2

    DIM_C --> J2
    J2 --> L2
    L2 --> J3
    J3 --> PROCFINAL["fact_procurement<br/>(all rows retained)"]

    EPI --> J4
    DIM_C --> J4
    J4 --> L3
    L3 --> EPIFINAL["countries_with_epi<br/>(only matched)"]

    WGI --> J5
    DIM_C --> J5
    J5 --> L4
    L4 --> WGIFINAL["countries_with_wgi<br/>(only complete)"]

    PROCFINAL --> GAP
    EPIFINAL --> GAP
    WGIFINAL --> GAP
    GAP --> OVERLAP

    %% Styling
    style L1 fill:#fff3cd,stroke:#856404
    style L2 fill:#fff3cd,stroke:#856404
    style L3 fill:#f8d7da,stroke:#721c24
    style L4 fill:#f8d7da,stroke:#721c24
    style OVERLAP fill:#d4edda,stroke:#155724
```

---

## Data Loss Points Explained

| Point | Location | What Happens | Records Lost | Business Impact |
|-------|----------|--------------|--------------|-----------------|
| **DLP1** | Procurement → Material | Unmatched materials get `material_key = NULL` → Replaced with "Unknown Material" | **0** | No loss, but €X spend has unknown material classification |
| **DLP2** | Procurement → Country | Unmatched countries get `country_key = NULL` → Replaced with "Unknown Country" | **0** | No loss, but €X spend has unknown country risk |
| **DLP3** | EPI → Country | EPI ISO codes that don't match `dim_country.iso3` are **dropped** | **5-20** | Countries with EPI data excluded from sustainability analysis |
| **DLP4** | WGI → Country | Countries with <5 WGI indicators marked as "No WGI" | **Variable** | Partial governance data treated as no governance data |

---

## How Coverage is Calculated

The `gold_data_gaps` table determines coverage status for each country used in procurement:

### Step 1: Identify Procurement Countries
```sql
-- All unique countries from fact_procurement (HQ + Production)
SELECT DISTINCT country_key FROM fact_procurement
```

### Step 2: Check EPI Coverage
```sql
-- Countries that have EPI data joined via ISO3
SELECT country_key FROM gold_fact_epi
WHERE epi_score IS NOT NULL
```

### Step 3: Check WGI Coverage (Strict)
```sql
-- Countries must have ALL 5 WGI indicators:
-- 1. Voice and Accountability
-- 2. Political Stability and Absence of Violence/Terrorism
-- 3. Government Effectiveness
-- 4. Regulatory Quality
-- 5. Control of Corruption
SELECT country_key
FROM gold_fact_wgi
GROUP BY country_key
HAVING COUNT(DISTINCT indicator_name) = 5
```

### Step 4: Determine Coverage Status
```
Coverage Status = CASE
    WHEN has_epi AND has_wgi_complete THEN 'Full Coverage'
    WHEN has_epi AND NOT has_wgi_complete THEN 'EPI Only'
    WHEN NOT has_epi AND has_wgi_complete THEN 'WGI Only'
    ELSE 'No Coverage'
END
```

---

## Key Insight: The Coverage Overlap

The `gold_data_gaps` table answers: **"For each procurement country, do we have EPI and WGI data?"**

```
Procurement Countries (12 in sample)
├── Countries with EPI: 12 (100%) ← All matched
├── Countries with WGI (all 5 indicators): 12 (100%) ← All matched
└── Coverage Status:
    ├── Full Coverage: 12 (100%)
    ├── EPI Only: 0
    ├── WGI Only: 0
    └── No Coverage: 0
```

---

## Why Sample Data Shows 100% Coverage

The current sample data shows 100% coverage because all 12 procurement countries are **major economies** with complete external data:

| Country | EPI Status | WGI Status | Notes |
|---------|------------|------------|-------|
| Germany | ✅ Complete | ✅ All 5 indicators | Major EU economy |
| China | ✅ Complete | ✅ All 5 indicators | Major global supplier |
| USA | ✅ Complete | ✅ All 5 indicators | Major economy |
| Japan | ✅ Complete | ✅ All 5 indicators | Major economy |
| ... | ... | ... | ... |

**Real-world scenarios where gaps would appear:**
- Emerging markets (some smaller African/Asian countries)
- Disputed territories (Taiwan, Kosovo)
- Micro-states (Monaco, San Marino)
- Recently independent nations

---

## Impact Analysis by Data Loss Point

### DLP1 & DLP2: Unmapped Values (Low Risk)
- **No data loss** - records are retained with fallback keys
- **Impact**: Reduced analytical confidence
- **Mitigation**: Review `unmapped_countries` / `unmapped_materials` tables regularly

### DLP3: EPI Country Mismatch (Medium Risk)
- **Data loss**: Countries in EPI data that don't exist in dim_country
- **Impact**: Sustainability scores unavailable for some procurement origins
- **Mitigation**: Expand country alias mappings in `country_alias_mapping.md`

### DLP4: WGI Partial Coverage (Medium-High Risk)
- **Data loss**: Countries with 1-4 WGI indicators treated as having NO governance data
- **Impact**: Binary "all or nothing" - partial data provides no value
- **Mitigation**: Consider relaxing to "3+ indicators" or "core indicators only"

---

## Related Documents

- [Data Quality Framework](./data_quality_framework.md) - ISO 25012 quality dimensions
- [Business Requirements](./business_requirements.md) - Stakeholder expectations for data coverage
- [External Data Automation](./external_data_automation.md) - EPI/WGI source details

---

*Last Updated: 2026-01-17*
*Purpose: Visualize data flow and identify coverage risks*
