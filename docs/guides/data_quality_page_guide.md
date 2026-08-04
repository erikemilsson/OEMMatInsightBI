# Data Gaps Page Guide

**Purpose:** Step-by-step instructions for building the Data Gaps page in Power BI, showing which countries/materials are MISSING sustainability indicator data.

**Business Value:** Actionable insights like "Contact suppliers in these countries for sustainability data" and "€X spend is at risk due to missing indicator data."

**Prerequisites:**
- Pipeline run complete (`silver-to-gold2.Notebook` executed)
- Semantic model synced with `gold_data_gaps` and `gold_data_gaps_summary` tables visible
- `_Measures` table showing new "Data Gaps" folder measures

---

## Page Overview

The Data Gaps page provides transparency into sustainability data coverage. It answers:
- How many of our supplier countries have EPI data?
- How much spend is with suppliers where we lack sustainability data?
- Which specific countries need follow-up for data collection?

**Key Insight:** This page helps identify suppliers to contact for sustainability data improvement.

---

## Visual Layout

```
+------------------------------------------------------------------+
|  Page Title: "Data Gaps - Sustainability Coverage"                |
+------------------------------------------------------------------+
|                                                                   |
|  +------------------+  +------------------+  +------------------+ |
|  | COUNTRY COVERAGE |  |  SPEND COVERAGE  |  |    COUNTRIES     | |
|  |        %         |  |        %         |  |  WITHOUT DATA    | |
|  |      [KPI]       |  |      [KPI]       |  |     [KPI]        | |
|  +------------------+  +------------------+  +------------------+ |
|                                                                   |
|  +----------------------------------+  +------------------------+ |
|  |   COVERAGE BY STATUS            |  |  SPEND BY DATA STATUS  | |
|  |      [Donut Chart]              |  |     [Bar Chart]        | |
|  | Has Data vs Missing Data        |  | EUR with/without data  | |
|  +----------------------------------+  +------------------------+ |
|                                                                   |
|  +------------------------------------------------------------------+
|  |     COUNTRIES WITHOUT EPI DATA (Action Required)                 |
|  |                   [Table]                                        |
|  | Country | Region | Spend EUR | Transactions | Action Needed     |
|  +------------------------------------------------------------------+
|                                                                   |
+------------------------------------------------------------------+
```

---

## Step-by-Step Instructions

### Step 1: Create the Page

1. Open the Power BI report in Fabric portal or Power BI Desktop
2. Add a new page (right-click on page tabs > "New page")
3. Rename the page to "Data Gaps"
4. Set page size: 16:9 (standard)

---

### Step 2: Add Page Title

1. Insert > Text box
2. Type: **"Data Gaps - Sustainability Coverage"**
3. Format:
   - Font: Segoe UI Semibold, 24pt
   - Color: #333333
   - Position: Top left corner
4. Add subtitle: "Identify suppliers needing sustainability data follow-up"
   - Font: Segoe UI, 12pt, #666666

---

### Step 3: Create KPI Card - Country Coverage %

1. Insert > Visualizations > Card
2. Fields:
   - Value: `_Measures[Country Coverage %]`
3. Format:
   - Title: "Country Coverage"
   - Subtitle: "% of procurement countries with EPI data"
   - Callout value:
     - Font size: 40pt
     - Color: Use conditional formatting:
       - Green (#107C10) if >= 80%
       - Yellow (#FFB900) if >= 50%
       - Red (#D13438) if < 50%
   - Size: 220px wide x 140px tall
   - Position: Top row, left

---

### Step 4: Create KPI Card - Spend Coverage %

1. Insert > Visualizations > Card
2. Fields:
   - Value: `_Measures[Spend Coverage %]`
3. Format:
   - Title: "Spend Coverage"
   - Subtitle: "% of spend with sustainability data"
   - Callout value: Same conditional formatting as Step 3
   - Size: 220px wide x 140px tall
   - Position: Top row, center

---

### Step 5: Create KPI Card - Countries Without Data

1. Insert > Visualizations > Card
2. Fields:
   - Value: `_Measures[Countries without EPI Data]`
3. Format:
   - Title: "Countries Without Data"
   - Subtitle: "Require follow-up"
   - Callout value:
     - Font size: 40pt
     - Color: Conditional formatting (reverse - lower is better):
       - Green if = 0
       - Yellow if <= 3
       - Red if > 3
   - Size: 220px wide x 140px tall
   - Position: Top row, right

---

### Step 6: Create Coverage Donut Chart

1. Insert > Visualizations > Donut chart
2. Fields:
   - Legend: `gold_data_gaps[data_status]`
   - Values: `gold_data_gaps[country_key]` (Count Distinct)
3. Format:
   - Title: "Countries by Data Status"
   - Legend: Show at right
   - Colors:
     - "Has Indicator Data": Green (#107C10)
     - "Missing Indicator Data": Red (#D13438)
   - Size: 320px wide x 280px tall
   - Position: Second row, left

---

### Step 7: Create Spend Impact Bar Chart

1. Insert > Visualizations > Clustered bar chart
2. Fields:
   - Y-axis: `gold_data_gaps[data_status]`
   - X-axis: `_Measures[Spend with EPI Data]` AND `_Measures[Spend without EPI Data]`
3. **Alternative (simpler):**
   - Y-axis: `gold_data_gaps[data_status]`
   - X-axis: `gold_data_gaps[spend_eur]` (Sum)
4. Format:
   - Title: "Procurement Spend by Data Availability"
   - Data labels: On (show EUR values)
   - X-axis: Format as currency (€#,##0)
   - Colors:
     - "Has Indicator Data": Green (#107C10)
     - "Missing Indicator Data": Red (#D13438)
   - Size: 350px wide x 280px tall
   - Position: Second row, right

---

### Step 8: Create Action Table - Countries Without Data

**This is the most important visual - it shows which countries need follow-up.**

1. Insert > Visualizations > Table
2. Fields (in this order):
   - `gold_data_gaps[country_name_std]`
   - `gold_data_gaps[iso3]`
   - `gold_data_gaps[region]`
   - `gold_data_gaps[spend_eur]`
   - `gold_data_gaps[transaction_count]`
3. Filter:
   - `gold_data_gaps[has_epi_score]` = FALSE
4. Sort:
   - By `spend_eur` descending (highest impact first)
5. Format:
   - Title: "Countries Without EPI Data (Action Required)"
   - Headers: Bold, red background (#FDE7E9)
   - Column widths:
     - Country: 200px
     - ISO3: 60px
     - Region: 100px
     - Spend EUR: 120px (format as €#,##0)
     - Transactions: 100px
   - Size: Full width, 220px tall
   - Position: Bottom section

---

### Step 9: Add Insights/Action Text Box

1. Insert > Text box
2. Position: Below the table
3. Content:
   ```
   **How to use this page:**

   1. Countries in the RED table are missing sustainability indicator data
   2. Prioritize by spend - contact suppliers in high-spend countries first
   3. Request EPI/sustainability data from suppliers or research public sources
   4. Once data is collected, update the EPI source table and re-run pipeline

   **Goal:** Achieve 100% coverage of procurement spend with sustainability data
   ```
4. Format:
   - Font: Segoe UI, 11pt
   - Background: Light yellow (#FFF8E1)
   - Border: 1px solid #FFB900

---

## Verification Checklist

After building the page, verify:

- [ ] Country Coverage % shows a percentage (e.g., 70.0%)
- [ ] Spend Coverage % shows a percentage (e.g., 85.2%)
- [ ] Countries Without Data shows a count (e.g., 3)
- [ ] Donut chart shows two segments: green and red
- [ ] Bar chart shows spend amounts with green/red bars
- [ ] Table shows ONLY countries where `has_epi_score = FALSE`
- [ ] Table is sorted by spend (highest first)

---

## Expected Results

Based on your current data, you should see:
- **Country Coverage:** ~70-80% (most procurement countries have EPI data)
- **Spend Coverage:** Higher than country coverage (major suppliers typically have data)
- **Action Table:** 2-5 countries typically missing data

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| All measures show BLANK | Re-run `silver-to-gold2.Notebook` and refresh semantic model |
| Table shows no countries | Check filter is set to `has_epi_score = FALSE` |
| Coverage % shows 100% | All procurement countries have EPI data - great! Consider showing materials instead |
| Donut chart shows only 1 segment | Either all data is present or all is missing - check the filter |

---

## Alternative: Quick Version (15 minutes)

If you want a simpler page:

1. **2 KPI cards:** Country Coverage %, Spend Coverage %
2. **1 Table:** Full `gold_data_gaps` table filtered to `has_epi_score = FALSE`
3. Add a slicer for `data_status` to toggle between views

---

## DAX Measures Available

These measures are in the `_Measures` table under "Data Gaps" folder:

| Measure | Description |
|---------|-------------|
| `Countries with EPI Data` | Count of procurement countries with EPI scores |
| `Countries without EPI Data` | Count of countries MISSING EPI data |
| `Country Coverage %` | Percentage of countries with data |
| `Spend with EPI Data` | EUR spend where sustainability data exists |
| `Spend without EPI Data` | EUR spend at risk (no data) |
| `Spend Coverage %` | Percentage of spend with data |
| `Total Procurement Countries` | Total distinct countries |
| `Data Gap Summary` | Text: "X of Y countries" |

---

## Next Steps

After completing this page:
1. Export a screenshot (PNG) for portfolio documentation
2. Add a navigation button from Executive Dashboard to Data Gaps page
3. Share the "Action Required" table with procurement team
4. Set up a monthly review cadence to improve coverage

---

*Created for Task 001: Data Gaps Visibility Dashboard (Revised)*
*Last Updated: 2026-01-16*
