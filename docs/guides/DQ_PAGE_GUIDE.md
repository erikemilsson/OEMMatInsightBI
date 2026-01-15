# Data Quality Page Guide

**Purpose:** Step-by-step instructions for building the Data Quality page in Power BI.

**Prerequisites:**
- Task 015 complete (relationships fixed)
- Pipeline run complete (`silver-to-gold2.Notebook` executed)
- Semantic model synced with `gold_data_quality_dashboard` table visible

---

## Page Overview

The Data Quality page provides transparency into data matching confidence and highlights areas needing attention. It answers:
- What is our overall data quality score?
- Which records have low confidence matches?
- Which unmapped values need mapping rules added?

---

## Visual Layout

```
+------------------------------------------------------------------+
|  Page Title: "Data Quality Dashboard"                             |
+------------------------------------------------------------------+
|                                                                   |
|  +------------------+  +------------------+  +------------------+ |
|  |   OVERALL MATCH  |  |  HIGH CONFIDENCE |  |    UNMAPPED      | |
|  |      RATE %      |  |    RECORDS %     |  |    RECORDS       | |
|  |      [KPI]       |  |      [KPI]       |  |     [KPI]        | |
|  +------------------+  +------------------+  +------------------+ |
|                                                                   |
|  +----------------------------------+  +------------------------+ |
|  |     CONFIDENCE DISTRIBUTION     |  |   MATCH RATE BY SOURCE | |
|  |         [Pie Chart]             |  |     [Bar Chart]        | |
|  |  High / Medium / Low / Unmapped |  | Procurement vs Supply  | |
|  +----------------------------------+  +------------------------+ |
|                                                                   |
|  +------------------------------------------------------------------+
|  |               TOP UNMAPPED VALUES                               |
|  |                   [Table]                                        |
|  | Category | Value | Count | Action Needed                        |
|  +------------------------------------------------------------------+
|                                                                   |
+------------------------------------------------------------------+
```

---

## Step-by-Step Instructions

### Step 1: Create the Page

1. Open the Power BI report in Fabric portal or Power BI Desktop
2. Add a new page (right-click on page tabs > "New page")
3. Rename the page to "Data Quality"
4. Set page size: 16:9 (standard) or Custom (1280 x 720)

---

### Step 2: Add Page Title

1. Insert > Text box
2. Type: **"Data Quality Dashboard"**
3. Format:
   - Font: Segoe UI Semibold, 24pt
   - Color: #333333
   - Position: Top left corner

---

### Step 3: Create KPI Card - Overall Match Rate

1. Insert > Visualizations > Card
2. Fields:
   - Value: `_Measures[Overall Match Rate %]`
3. Format:
   - Title: "Overall Match Rate"
   - Callout value:
     - Font size: 36pt
     - Color: Use conditional formatting:
       - Green (#107C10) if >= 90%
       - Yellow (#FFB900) if >= 70%
       - Red (#D13438) if < 70%
   - Size: 200px wide x 120px tall
   - Position: Top row, left

**Tip:** If measure shows BLANK, the `gold_data_quality_dashboard` table may not have loaded. Re-run the pipeline.

---

### Step 4: Create KPI Card - High Confidence Records

1. Insert > Visualizations > Card
2. Fields:
   - Value: `_Measures[High Confidence Records %]`
3. Format:
   - Title: "High Confidence Records"
   - Callout value: Same conditional formatting as Step 3
   - Size: 200px wide x 120px tall
   - Position: Top row, center

---

### Step 5: Create KPI Card - Unmapped Records

1. Insert > Visualizations > Card
2. Fields:
   - Value: `_Measures[Unmapped Records Count]`
3. Format:
   - Title: "Unmapped Records"
   - Callout value:
     - Font size: 36pt
     - Color: Conditional formatting (reverse):
       - Green if < 100
       - Yellow if < 500
       - Red if >= 500
   - Size: 200px wide x 120px tall
   - Position: Top row, right

---

### Step 6: Create Confidence Distribution Pie Chart

1. Insert > Visualizations > Pie chart
2. Fields:
   - Legend: `gold_data_quality_dashboard[metric_name]`
   - Values: `gold_data_quality_dashboard[metric_value]`
3. Filter:
   - `gold_data_quality_dashboard[category]` = "Procurement"
   - `gold_data_quality_dashboard[metric_name]` IN ("High Confidence Count", "Medium Confidence Count", "Low Confidence Count", "Unmapped Count")
4. Format:
   - Title: "Procurement Confidence Distribution"
   - Legend: Show at right
   - Colors:
     - High Confidence: Green (#107C10)
     - Medium Confidence: Yellow (#FFB900)
     - Low Confidence: Orange (#FF8C00)
     - Unmapped: Red (#D13438)
   - Size: 300px wide x 250px tall
   - Position: Second row, left

---

### Step 7: Create Match Rate by Source Bar Chart

1. Insert > Visualizations > Clustered bar chart
2. Fields:
   - Y-axis: `gold_data_quality_dashboard[category]`
   - X-axis: `gold_data_quality_dashboard[metric_value]`
3. Filter:
   - `gold_data_quality_dashboard[metric_name]` = "Match Rate"
   - `gold_data_quality_dashboard[category]` IN ("Procurement", "Supply")
4. Format:
   - Title: "Match Rate by Data Source"
   - Data labels: On
   - X-axis: Format as percentage (0.0%)
   - Size: 280px wide x 250px tall
   - Position: Second row, right

---

### Step 8: Create Top Unmapped Values Table

1. Insert > Visualizations > Table
2. Fields:
   - `gold_data_quality_dashboard[category]`
   - `gold_data_quality_dashboard[metric_name]`
   - `gold_data_quality_dashboard[metric_value]`
   - `gold_data_quality_dashboard[description]`
3. Filter:
   - `gold_data_quality_dashboard[category]` IN ("Unmapped Materials", "Unmapped Countries")
4. Sort:
   - By `metric_value` descending
5. Format:
   - Title: "Top Unmapped Values (Prioritize for Mapping)"
   - Headers: Bold, dark background (#F5F5F5)
   - Alternating rows: Light gray
   - Size: Full width, 200px tall
   - Position: Bottom row

---

### Step 9: Add Insights Text Box

1. Insert > Text box
2. Position: Below the table
3. Content:
   ```
   **How to use this page:**
   - GREEN indicators = healthy data quality
   - YELLOW/RED indicators = action needed
   - Review "Top Unmapped Values" table for mapping rule additions
   - Contact Data Engineering to add new mapping rules
   ```
4. Format:
   - Font: Segoe UI, 10pt
   - Background: Light blue (#E6F2FF)

---

## Verification Checklist

After building the page, verify:

- [ ] Overall Match Rate shows a percentage (e.g., 87.5%)
- [ ] High Confidence shows a percentage (e.g., 75.2%)
- [ ] Unmapped Records shows a count (e.g., 234)
- [ ] Pie chart shows 4 segments with correct colors
- [ ] Bar chart shows Procurement and Supply bars
- [ ] Table shows unmapped materials and countries with counts

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| All measures show BLANK | Re-run `silver-to-gold2.Notebook` and refresh semantic model |
| Table shows no data | Check filter is set to "Unmapped Materials" / "Unmapped Countries" |
| Pie chart shows only 1 segment | Check filter on `metric_name` includes all confidence categories |
| Colors not showing conditionally | Apply conditional formatting in Format > Callout value > Color |

---

## Alternative: Simple Version

If you want a simpler page, use just:

1. **3 KPI cards** (Match Rate, High Confidence %, Unmapped Count)
2. **1 Table** showing the full `gold_data_quality_dashboard` table with slicers for category

This takes ~10 minutes vs the full version (~30 minutes).

---

## Next Steps

After completing this page:
1. Export a screenshot (PNG) for portfolio documentation
2. Add a bookmark to navigate from Executive Dashboard to DQ page
3. Consider adding a "Data Quality" filter to other pages

---

*Created for Task 001: Enhance Data Quality & Matching Visibility*
