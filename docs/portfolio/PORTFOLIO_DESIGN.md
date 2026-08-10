# OEMMatInsightBI - Portfolio Report Design
**Version:** 1.0 (design spec for the built `report2.Report`)
**Purpose:** 2-page Power BI report design for portfolio showcase (erikemilsson.com)

> The report this spec describes is **built** (`fabric/report2.Report`) on the `OEMInsightBI` semantic model. The visual specs below are the design; the as-built measure set is documented in [`docs/dax_measure_library.md`](../dax_measure_library.md) (45 measures). Where a visual below names a measure that was reframed during the model's redesign, substitute the nearest as-built measure from the catalogue — e.g. `[Supply Risk (Global)]` for HHI, `Weighted EPI Score` for the spend-weighted sustainability gauge.

---

## Design Philosophy

**Goal:** Create visually compelling, insight-driven pages that demonstrate:
- Data visualization best practices
- Advanced DAX skills (time intelligence, weighted calculations, risk metrics)
- Business storytelling (sustainability + risk narrative)
- Professional design (consistent theme, clear hierarchy, actionable insights)

**Scope:** 2 polished pages (vs. 5 in full Task 003 approach)
- **Page 1:** Executive Dashboard (procurement performance)
- **Page 2:** Risk & Sustainability Analysis (ESG + supply chain risk)

**Target Audience:** Recruiters, hiring managers, data professionals

---

## Page 1: Executive Dashboard

### Layout Overview
```
┌──────────────────────────────────────────────────────────────┐
│  PROCUREMENT OVERVIEW - 2023                                  │
├─────────────────┬─────────────────┬──────────────────────────┤
│  TOTAL SPEND    │  YOY GROWTH %   │  SUPPLIER COUNTRIES      │
│  €12.5M         │  +8.3%          │  23                      │
│  (KPI Card)     │  (KPI Card)     │  (KPI Card)              │
├─────────────────┴─────────────────┴──────────────────────────┤
│  SPEND TREND (2020-2023)                                      │
│  [Line Chart: Monthly spend with YoY comparison]             │
│                                                               │
├────────────────────────────────┬──────────────────────────────┤
│  TOP 10 MATERIALS BY SPEND     │  GEOGRAPHIC DISTRIBUTION     │
│  [Horizontal Bar Chart]        │  [Map Visual]                │
│                                │                              │
└────────────────────────────────┴──────────────────────────────┘
```

### Visual Specifications

#### 1. KPI Card: Total Spend
- **Measure:** `[Total Spend EUR]`
- **Format:** €12.5M (millions, 1 decimal)
- **Trend:** Sparkline showing last 12 months
- **Color:** Dark blue (#003366)
- **Position:** Top-left (1/3 width)

#### 2. KPI Card: YoY Growth %
- **Measure:** `[YoY Spend Growth %]`
- **Format:** +8.3% (percentage with +/- sign)
- **Conditional Color:**
  - Green (#28a745): Growth > 5%
  - Yellow (#ffc107): Growth 0-5%
  - Red (#dc3545): Growth < 0%
- **Position:** Top-center (1/3 width)

#### 3. KPI Card: Supplier Countries
- **Measure:** `DISTINCTCOUNT(fact_procurement[supplier_hq_country_key])`
- **Format:** 23 (whole number)
- **Subtitle:** "Active supplier countries"
- **Color:** Teal (#17a2b8)
- **Position:** Top-right (1/3 width)

#### 4. Line Chart: Spend Trend
- **X-Axis:** `gold_dim_date[year_month]` (Jan 2020 - Dec 2023)
- **Y-Axis:** `[Total Spend EUR]`
- **Series:**
  - Current Year: Solid blue line
  - Prior Year: Dashed gray line (for comparison)
- **Data Labels:** On (endpoint only)
- **Gridlines:** Horizontal only
- **Position:** Mid-section (full width)
- **Height:** ~250px

#### 5. Horizontal Bar Chart: Top 10 Materials
- **Category:** `gold_dim_material[material_name_std]`
- **Value:** `[Total Spend EUR]`
- **Sort:** Descending by spend
- **Top N Filter:** Top 10 materials
- **Color:** Gradient from dark blue to light blue
- **Data Labels:** Show values (€XXk format)
- **Position:** Bottom-left (50% width)

#### 6. Map Visual: Geographic Distribution
- **Location:** `gold_dim_country[country_name_std]`
- **Size:** `[Total Spend EUR]`
- **Color:** Blue gradient (darker = higher spend)
- **Tooltip:**
  - Country name
  - Total spend
  - % of total
  - Supplier count
- **Position:** Bottom-right (50% width)

### Filters (Page-Level)
- **Year Slicer:** Dropdown (default: 2023)
- **Material Slicer:** Multi-select dropdown (default: All)
- **Position:** Top-right corner (collapsible panel)

### Design Notes
- **Color Scheme:** Professional blue palette (#003366, #0066cc, #3399ff)
- **Typography:** Segoe UI, 11pt body, 14pt titles
- **White Space:** Generous padding (10px between visuals)
- **Accessibility:** High contrast, WCAG AA compliant

---

## Page 2: Risk & Sustainability Analysis

### Layout Overview
```
┌──────────────────────────────────────────────────────────────┐
│  RISK & SUSTAINABILITY SCORECARD                              │
├──────────────┬──────────────┬──────────────┬─────────────────┤
│  AVG EPI     │  SPEND-WT    │  HHI INDEX   │  HIGH RISK      │
│  SCORE       │  EPI SCORE   │              │  MATERIALS      │
│  62.3        │  58.7        │  0.18        │  4              │
│  (KPI)       │  (KPI)       │  (Gauge)     │  (KPI)          │
├──────────────┴──────────────┴──────────────┴─────────────────┤
│  SUSTAINABILITY BREAKDOWN                                     │
│  [Donut Chart: % Spend by EPI Category (High/Med/Low)]      │
├────────────────────────────────┬──────────────────────────────┤
│  SUPPLY CONCENTRATION RISK     │  TOP 5 HIGH RISK MATERIALS   │
│  [Clustered Column Chart]      │  [Table]                     │
│  Material | Max % | HHI        │  Material | Country | %      │
└────────────────────────────────┴──────────────────────────────┘
```

### Visual Specifications

#### 1. KPI Card: Avg EPI Score
- **Measure:** `[Avg EPI Score]`
- **Format:** 62.3 (1 decimal)
- **Subtitle:** "Environmental Performance (0-100)"
- **Conditional Formatting:**
  - Green: Score > 60
  - Yellow: Score 40-60
  - Red: Score < 40
- **Position:** Top-left (1/4 width)

#### 2. KPI Card: Spend-Weighted EPI Score
- **Measure:** `[Spend-Weighted EPI Score]`
- **Format:** 58.7 (1 decimal)
- **Subtitle:** "Procurement-adjusted score"
- **Callout:** "Shows actual environmental impact of spending decisions"
- **Position:** Top-center-left (1/4 width)

#### 3. Gauge Visual: HHI Index
- **Measure:** `[HHI Index]`
- **Range:** 0 to 1.0
- **Color Zones:**
  - Green (0 - 0.15): "Low Concentration"
  - Yellow (0.15 - 0.25): "Moderate Concentration"
  - Red (0.25 - 1.0): "High Concentration"
- **Position:** Top-center-right (1/4 width)

#### 4. KPI Card: High Risk Material Count
- **Measure:** `[High Risk Material Count]`
- **Format:** 4 (whole number)
- **Subtitle:** "Materials >50% single-country supply"
- **Alert Icon:** If count > 0
- **Position:** Top-right (1/4 width)

#### 5. Donut Chart: Sustainability Breakdown
- **Legend:** EPI Category (High/Medium/Low)
- **Values:**
  - `[% Spend - High EPI (>60)]`: Green
  - `[% Spend - Medium EPI (40-60)]`: Yellow (calculated measure)
  - `[% Spend - Low EPI (<40)]`: Red (calculated measure)
- **Data Labels:** Percentage + absolute spend
- **Center Label:** "Spend Distribution"
- **Position:** Mid-section (full width, compact height ~200px)

#### 6. Clustered Column Chart: Supply Concentration
- **Category:** `gold_dim_material[material_name_std]`
- **Y-Axis 1:** `[Max Supply Concentration %]` (bars)
- **Y-Axis 2:** `[HHI Index]` (line overlay)
- **Sort:** Descending by max concentration
- **Top N Filter:** Top 10 materials
- **Color:** Red-orange gradient (indicating risk)
- **Position:** Bottom-left (60% width)

#### 7. Table: Top 5 High Risk Materials
- **Columns:**
  1. Material Name
  2. Top Supplier Country
  3. Supply Concentration %
  4. HHI Index
  5. Risk Category (High/Medium/Low)
- **Sort:** Descending by concentration %
- **Top N Filter:** Top 5
- **Conditional Formatting:**
  - Concentration % > 50%: Red background
  - HHI > 0.25: Bold text
- **Position:** Bottom-right (40% width)

### Filters (Page-Level)
- **Material Slicer:** Multi-select dropdown
- **Supply Stage Slicer:** Dropdown (Extraction/Processing/Manufacturing)
- **Position:** Right sidebar (collapsible)

### Design Notes
- **Color Scheme:** Risk-oriented palette (green/yellow/red for categories, dark blue for neutral)
- **Narrative Flow:** Top KPIs → Breakdown → Deep dive
- **Tooltips:** Enhanced with context (e.g., "HHI >0.25 indicates high market concentration")
- **Accessibility:** Color + shape coding (not color alone)

---

## Deleted Content

### Page 3: Debug Visuals (REMOVED)
**Reason:** Page 3 contained only debug/development visuals:
- "Debug - Latest Supply Year"
- "Debug - Latest Indicator Year"
- "Intensity Latest", "Supply Share Latest", "Score Latest"

These are not portfolio-appropriate and have been removed from the report.

---

## Technical Implementation Notes

### As-built measure set

The model ships **45 measures across 8 tables** (no `_Measures` table — measures live on the table that owns their grain, grouped with display folders). The full catalogue is in [`dax_measure_library.md`](../dax_measure_library.md). Headline measures used across the two pages:

- `Total Spend EUR`, `Transaction Count`, `Materials Count`, `Supplier Countries Count` (`fact_procurement`)
- `Avg EPI Score`, `Countries with EPI Data`, `Weighted EPI Score` (`fact_epi_score`)
- `Supply Risk (Global)`, `Supply Risk (EU Sourcing)`, `Supply Risk Contrast` (`gold_supply_risk`)
- `Supply Concentration Index` (`fact_supply_share`)
- 16 coverage measures on `gold_data_gaps` (EPI/WGI coverage by country and spend)
- 17 observability measures across `gold_gap_registry`, `gold_quality_history`, `gold_low_confidence_audit`

### Additional Calculated Columns Needed
None - all logic in measures for performance (DirectLake compatibility).

### Data Requirements
- **Fact Tables:** fact_procurement, fact_epi_score, fact_supply_share
- **Dimensions:** gold_dim_date, gold_dim_country, gold_dim_material, gold_dim_indicator, gold_dim_stage
- **Derived gold:** gold_supply_risk
- **Data Freshness:** Highlight in report footer (DirectLake auto-refreshes from `oem_lh`)

---

## Theme Specification

### Color Palette
```yaml
Primary:
  - Dark Blue: #003366
  - Medium Blue: #0066cc
  - Light Blue: #3399ff

Accent:
  - Green (Positive): #28a745
  - Yellow (Warning): #ffc107
  - Red (Alert): #dc3545
  - Teal: #17a2b8

Neutral:
  - Dark Gray: #343a40
  - Medium Gray: #6c757d
  - Light Gray: #f8f9fa
  - White: #ffffff
```

### Typography
- **Headings:** Segoe UI Bold, 16pt
- **KPI Values:** Segoe UI Semibold, 28pt
- **Body Text:** Segoe UI Regular, 11pt
- **Data Labels:** Segoe UI Regular, 10pt

### Layout Grid
- **Canvas:** 1280px × 720px (16:9 aspect ratio)
- **Margins:** 10px all sides
- **Gutter:** 10px between visuals
- **Grid Columns:** 12-column system

---

## Portfolio Export Checklist

### Assets to Create
- [ ] High-resolution screenshots (1920×1080 PNG)
  - [ ] Page 1: Executive Dashboard
  - [ ] Page 2: Risk & Sustainability Analysis
- [ ] PDF export (vector format, interactive links if possible)
- [ ] PBIX file (for sharing with recruiters)
- [ ] Case study document (1-2 pages, see CASE_STUDY.md)

### Screenshot Requirements
- **Resolution:** 1920×1080 (Full HD)
- **Format:** PNG (lossless compression)
- **Background:** Light theme (better for web display)
- **Annotations:** Optional callouts highlighting key insights
- **File naming:**
  - `oeminsight_page1_executive_dashboard.png`
  - `oeminsight_page2_risk_sustainability.png`

---

## Implementation Steps

1. ✅ **Semantic model** — `OEMInsightBI` ships 45 measures (see `dax_measure_library.md`)
2. ✅ **Report** — `report2.Report` built from the model; the two pages follow the layouts above
3. ✅ **Theme** — applied (colors, fonts from the spec below)
4. **Portfolio asset capture** (on demand):
   - Take screenshots (hi-res PNG, 1920×1080)
   - Export PDF (File → Export → PDF)
   - Save PBIX file
5. ✅ **Case study** — see `CASE_STUDY.md`

---

## Next Steps

**For the report:**
1. Open `report2.Report` in the Fabric workspace (or Power BI Desktop)
2. DirectLake auto-refreshes from `oem_lh`; no manual semantic-model refresh needed
3. Iterate on visuals against the layouts above; consult `dax_measure_library.md` for the authoritative measure list

**For the portfolio:**
1. Publish the case study to `erikemilsson.com` (method + engineering framing, not "findings")
2. Generate high-quality screenshots from the live report
3. Write a brief LinkedIn post (see `PORTFOLIO_ASSETS_README.md` for an honest-framing template)
4. Add to the portfolio page

---

**Design Status:** ✅ Spec complete; report built (`report2.Report`)
