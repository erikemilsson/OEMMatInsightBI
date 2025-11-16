# Task: Redesign Power BI Report

**Priority:** P1 (Highest)
**Status:** Not Started
**Estimated Effort:** 3-5 days
**Owner:** TBD

## Problem Statement

Per project_definition.md lines 823-835:
> "The existing report will be discarded. A new set of visualizations and pages will be designed from scratch after the semantic model is finalized."

The current report exists but needs complete redesign with focus on:
- Clear, insightful visualizations
- Effective data storytelling
- Portfolio-quality presentation
- User-friendly navigation

## Current State

**What Exists:**
- ✅ Report artifact connected to semantic model
- ✅ Theme applied (CY24SU10.json)
- ✅ DirectLake connection for real-time data

**What's Missing:**
- ❌ No documented page structure
- ❌ No visual inventory
- ❌ No clear business story
- ❌ No drill-through pages
- ❌ No effective slicers/filters

## Acceptance Criteria

### Must Have: Report Structure

**Page 1: Executive Overview**
- Hero metrics: Total Spend, Supplier Count, Avg EPI Score
- Spend by commodity group (bar chart)
- Spend trend over time (line chart)
- Geographic spend distribution (map visual)
- Top 5 suppliers by spend (table)

**Page 2: Sustainability Dashboard**
- Spend by EPI score band (High/Medium/Low)
- Average EPI score by supplier country (map with color scale)
- Top environmental indicators contributing to low scores
- WGI governance scores for top supplier countries
- Sustainability risk matrix (EPI vs WGI scatter plot)

**Page 3: Supply Chain Risk Analysis**
- Supply concentration by material (bar chart showing max %)
- Critical materials with >50% concentration (table with alerts)
- Our procurement vs global supply patterns (comparison chart)
- Production stage analysis (extraction vs processing)
- Risk heat map (material × country)

**Page 4: Material Deep Dive** (drill-through)
- Material details (name, commodity group, total spend)
- Supplier breakdown for selected material
- Global supply concentration for material
- EPI scores for supplier countries
- Time series: spend trend for material

**Page 5: Data Quality Dashboard** (from Task 01)
- Overall quality scorecard
- Match confidence distribution
- Unmapped values by source
- Quality flags and warnings

### Nice to Have:
- Drill-through from any visual to material/country details
- Bookmarks for different views (Procurement focus, Sustainability focus, Risk focus)
- Mobile-optimized layout
- Tooltips with contextual information
- Interactive filters with "Apply" button

## Design Principles

1. **Visual Hierarchy:** Most important metrics at top-left
2. **Color Consistency:**
   - Spend = Blue
   - EPI/Sustainability = Green
   - Risk/Alerts = Red/Orange
3. **White Space:** Don't overcrowd pages
4. **Actionability:** Every visual should support a decision
5. **Portfolio Quality:** Professional, polished presentation

## Technical Approach

### Phase 1: Design (1-2 days)
1. Sketch page layouts on paper/whiteboard
2. Identify required measures from Task 02
3. Select appropriate visual types for each insight
4. Plan navigation flow and drill-throughs
5. Create color palette and style guide

### Phase 2: Build Overview & Sustainability Pages (1 day)
1. Create Page 1: Executive Overview
2. Add hero metrics, charts, map
3. Create Page 2: Sustainability Dashboard
4. Configure slicers (date, commodity group, region)

### Phase 3: Build Risk & Detail Pages (1 day)
1. Create Page 3: Supply Chain Risk Analysis
2. Add concentration metrics and alerts
3. Create Page 4: Material Deep Dive (drill-through)
4. Configure drill-through actions

### Phase 4: Data Quality & Polish (1 day)
1. Add Page 5: Data Quality Dashboard (from Task 01)
2. Add navigation buttons/bookmarks
3. Apply consistent formatting
4. Test all interactions
5. Optimize performance

### Phase 5: Documentation & Screenshots (0.5 days)
1. Document page purpose and key insights
2. Take screenshots for portfolio
3. Create user guide if needed

## Dependencies
- **Task 02 must be completed first** (DAX measures required)
- **Task 01 should be completed** (DQ dashboard content)
- Semantic model with all measures implemented
- Power BI Desktop or Fabric workspace access

## Success Metrics
- ✅ 5 report pages with clear purpose
- ✅ All 10 business questions (from Task 02) visually answered
- ✅ Professional portfolio-quality design
- ✅ Navigation intuitive for stakeholders
- ✅ Performance acceptable (<3 seconds per visual load)

## Related Files
- `/fabric/report.Report/` - Report artifact
- `/fabric/semantic_model_oeminsightbi.SemanticModel/` - Connected semantic model
- `/project_definition.md` - Lines 821-836 (Reporting section)

## Visual Inventory Template

Once designed, document visuals:
```
Page 1: Executive Overview
├── Card: Total Spend
├── Card: Supplier Count
├── Card: Avg EPI Score
├── Bar Chart: Spend by Commodity Group
├── Line Chart: Spend Trend (Monthly)
├── Map: Geographic Distribution
└── Table: Top 5 Suppliers
```

## Notes
- Prioritize clarity over complexity
- Test with actual stakeholders if possible
- Consider accessibility (color blindness, screen readers)
- Export to PDF for offline portfolio viewing
- This is a showcase piece - invest time in polish
