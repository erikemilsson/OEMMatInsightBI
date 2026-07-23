# OEMMatInsightBI - Portfolio Assets Summary
**Project:** OEMMatInsightBI - Procurement Analytics & ESG Risk Intelligence
**Date:** 2025-11-16
**Status:** Design Complete, Implementation Pending Workspace Access

---

## Portfolio-Ready Assets ✅

### 1. Case Study Document
**File:** `/docs/portfolio/CASE_STUDY.md`
**Status:** ✅ Complete and ready to publish

**Highlights:**
- **2,500 words** professional case study
- Business challenge → solution → technical implementation → results
- Key insights (sustainability gap, 4 high-risk materials identified)
- Technical skills demonstrated (DAX, PySpark, data engineering)
- Suitable for:
  - erikemilsson.com portfolio page
  - LinkedIn article
  - Resume attachment
  - Interview discussion guide

**Next Steps:**
1. Convert to PDF for professional formatting
2. Add screenshots when available
3. Publish to portfolio website

---

### 2. Report Design Documentation
**File:** `/docs/portfolio/PORTFOLIO_DESIGN.md`
**Status:** ✅ Complete and ready for implementation

**Contents:**
- **Page 1 Design:** Executive Dashboard (full visual specifications)
- **Page 2 Design:** Risk & Sustainability Analysis (layout, measures, colors)
- **Theme Specification:** Color palette, typography, grid system
- **Implementation Checklist:** Step-by-step guide for building the report

**Demonstrates:**
- Dashboard design thinking (UX, visual hierarchy, storytelling)
- Power BI best practices (measure organization, accessibility)
- Professional documentation (clear specs for handoff to developer or client)

**Use Cases:**
- Show to recruiters: "Here's how I approach BI design"
- Portfolio website: "Sample design spec from recent project"
- Interview: "Let me walk you through my design process"

---

### 3. DAX Measure Library — Two Models, One Evolution

The semantic model went through a deliberate redesign, and the two versions tell
complementary stories. **Both are worth showing — know which one you're demoing.**

| | **v2 — canonical** | **v1 — archived** |
|---|---|---|
| Path | `fabric/OEMInsightBI_v2.SemanticModel/definition/tables/*.tmdl` | `fabric/archive/…/definition/tables/_Measures.tmdl` |
| Measures | 40, across per-table files | 46, in one file |
| Emphasis | **Data-quality observability** | **Analytical BI depth** |
| Examples | `EPI Country Coverage %`, `Gap Resolution Rate`, `Threshold Breaches` | HHI Index, Spend-Weighted EPI, YoY Growth |

The redesign **foregrounded data-quality observability** — coverage tracking, gap
resolution, gate-verdict surfacing — because that became the project's centre of
gravity (a blocking DQ gate, a gap registry, quality-history trending). The v1
analytical measures were preserved in the archive rather than carried forward; the two
models share only **Total Spend EUR** and **Avg EPI Score**.

**The interview narrative:** *"I redesigned the model as the project's focus shifted from
descriptive analytics to data-quality engineering. v2 exposes the observability layer —
coverage %, gap resolution, gate verdicts — as first-class measures; the earlier
analytical set (HHI concentration, spend-weighted sustainability, time intelligence)
lives in the archived v1 model and I can walk through either."* Showing the trade is the
signal — it demonstrates judgment about what a data-engineering project should surface,
not just breadth of DAX syntax.

**Analytical showcase measures (v1 archive) — the advanced-DAX evidence:**
1. **Total Spend EUR** — Basic aggregation *(also in v2)*
2. **YoY Spend Growth %** — Time intelligence (`SAMEPERIODLASTYEAR`)
3. **Avg EPI Score** — Filtered aggregation *(also in v2)*
4. **Spend-Weighted EPI Score** — `SUMX` over `SUMMARIZE` with nested `CALCULATE`
5. **% Spend - High EPI (>60)** — Categorization with `DIVIDE`
6. **Max Supply Concentration %** — `MAXX`
7. **HHI Index** — Herfindahl-Hirschman concentration (`SUMX` of squared shares)
8. **High Risk Material Count** — Conditional distinct count

**Observability measures (v2 canonical) — the data-engineering evidence:**
coverage % by source, gap resolution rate, open/resolved gap counts, threshold breaches,
low-confidence match tracking, pipeline-run counts — i.e. *is the data trustworthy, and
where are the holes*, expressed in DAX.

**Technical highlights (both models):**
- ✅ Display folders for organization
- ✅ Safe division with `DIVIDE` (handles zero denominators)
- ✅ Variables for readability and performance
- ✅ `SUMX` iteration for weighted calculations
- ✅ DirectLake-compatible (no calculated columns)

**Portfolio Use:**
- Code sample for GitHub — link the specific `.tmdl` file, not a generic path
- Interview discussion: the v1→v2 evolution *is* the story ("tell me about a design
  decision you'd defend")
- Evidence of both analytical DAX depth **and** data-quality engineering judgment

---

### 4. Full DAX Measure Design Document
**File:** `/.claude/support/documents/dax_measure_library.md`
**Status:** ✅ Design complete (40+ measures designed). **Implementation is split across
two models** — see § 3: the 8 showcase measures are implemented in the *archived v1*
model, while the canonical v2 model implements a different 40-measure coverage/quality
set. This design doc describes the analytical measures, i.e. the v1 set.

**Contents:**
- Star schema overview
- Measure organization strategy
- **30+ additional measures** designed (time intelligence, sustainability, risk, advanced)
- Performance optimization patterns
- Business logic documentation

**Portfolio Use:**
- Shows ability to design comprehensive measure libraries
- Demonstrates forward-thinking (designed 40+, prioritized a focused set for build)
- Pairs with § 3's v1→v2 narrative: this doc is the *design* superset; the two shipped
  models are the *implemented* subsets, each with a deliberate emphasis

---

## Pending Assets (Require Workspace Access) ⏳

### 5. Power BI Report Implementation
**Status:** ⏳ Pending Fabric workspace access

**What's Needed:**
1. Access to Fabric workspace
2. Refresh semantic model (to load new _Measures table)
3. Build report pages following PORTFOLIO_DESIGN.md specifications
4. Apply theme and formatting

**Estimated Time:** 2-3 hours (design is complete, just implementation)

**Workaround for Portfolio:**
- Use PORTFOLIO_DESIGN.md as evidence of design skills
- Create mockups/wireframes using Figma or PowerPoint
- Explain in case study: "Design complete, implementation pending workspace access"

---

### 6. Screenshots (High-Resolution)
**Status:** ⏳ Pending report implementation

**Required Assets:**
- `oeminsight_page1_executive_dashboard.png` (1920×1080)
- `oeminsight_page2_risk_sustainability.png` (1920×1080)

**Use Cases:**
- Portfolio website hero images
- LinkedIn posts
- Case study visual aids
- Presentation decks

**Alternative:**
- Create mockups using design tools (Figma, Sketch, PowerPoint)
- Use generic Power BI screenshots with annotation: "Representative design (final implementation pending)"

---

### 7. PDF Export
**Status:** ⏳ Pending report implementation

**Requirements:**
- Export from Power BI Desktop (File → Export → PDF)
- Vector format for crisp printing
- Interactive links preserved if possible

**Use Cases:**
- Email attachment for recruiters
- Printable portfolio piece
- Archival version

---

### 8. PBIX File
**Status:** ⏳ Pending report implementation

**Requirements:**
- Save as `.pbix` from Power BI Desktop
- Include semantic model + report pages
- Test file size (should be <50 MB for easy sharing)

**Use Cases:**
- Share with recruiters who want to explore interactively
- Upload to GitHub (if data is anonymized/public)
- Demonstration during technical interviews

---

## Immediate Portfolio Showcase Options

### Option 1: Publish Case Study (Recommended)
**Effort:** 30 minutes
**Impact:** High

**Steps:**
1. Convert `CASE_STUDY.md` to PDF using Pandoc or Markdown-to-PDF tool
2. Upload to portfolio website (erikemilsson.com/projects/oeminsightbi)
3. Create LinkedIn post highlighting key findings
4. Add to resume under "Featured Projects"

**Template LinkedIn Post:**
> 📊 Just completed an end-to-end BI project: OEMMatInsightBI
>
> Built a Power BI solution to help an OEM manufacturer track procurement sustainability and supply chain risk.
>
> Key results:
> ✅ Identified 4 materials with >50% single-country supply concentration
> ✅ Revealed sustainability gap (58.7 spend-weighted EPI vs. 62.3 unweighted)
> ✅ Implemented 8 advanced DAX measures (time intelligence, weighted calcs, HHI index)
>
> Tech stack: Power BI, DAX, PySpark, Azure SQL, Microsoft Fabric
>
> Full case study: [link to PDF]
>
> #PowerBI #DataAnalytics #BusinessIntelligence #ESG #SupplyChain

---

### Option 2: Create Design Mockups
**Effort:** 2-4 hours
**Impact:** Medium-High

**Tools:**
- Figma (free, web-based, professional mockups)
- PowerPoint (quick, familiar, exportable to PDF)
- Canva (templates available, easy to use)

**Steps:**
1. Use PORTFOLIO_DESIGN.md layout specifications
2. Create 2 mockup images (Page 1 and Page 2)
3. Use realistic data labels (€12.5M, +8.3%, etc.)
4. Add to portfolio website with caption: "Design specifications (implementation pending)"

**Why This Works:**
- Shows design thinking even without implementation
- Demonstrates ability to create professional specs
- Separates "design" from "execution" (both valuable skills)

---

### Option 3: Code Portfolio on GitHub
**Effort:** 1 hour
**Impact:** Medium

**Steps:**
1. Create public repo: `erikemilsson/OEMMatInsightBI`
2. Upload key files:
   - DAX code — v2: `OEMInsightBI_v2.SemanticModel/definition/tables/*.tmdl`; v1 showcase set: the archived model under `fabric/archive/` → `definition/tables/_Measures.tmdl`
   - `CASE_STUDY.md` (project overview)
   - `PORTFOLIO_DESIGN.md` (design specs)
   - `dax_measure_library.md` (full design)
   - Sample Python transformations (`src/transformations/`)
3. Write README with project overview and "Featured Code" section
4. Add to resume: "GitHub: github.com/erikemilsson/OEMMatInsightBI"

**Why This Works:**
- Recruiters can see actual code (DAX, Python, documentation)
- Shows Git proficiency (commit messages, repo structure)
- Demonstrates willingness to share knowledge (good culture fit signal)

---

## What Recruiters Will See

### Technical Skills Validated
- ✅ **DAX:** Time intelligence, SUMX iteration, weighted calculations, safe division
- ✅ **Data Modeling:** Star schema design, DirectLake optimization
- ✅ **Dashboard Design:** UX best practices, visual hierarchy, accessibility
- ✅ **Documentation:** Professional case studies, design specs, technical writing
- ✅ **Data Engineering:** Medallion pattern, PySpark, data quality frameworks (see broader project)

### Business Acumen Demonstrated
- ✅ Translated business questions into analytics solutions
- ✅ Identified actionable insights (4 high-risk materials, sustainability gap)
- ✅ Explained technical concepts for non-technical audience (case study)
- ✅ Prioritized features for MVP (8 measures vs. 40+ designed)

### Soft Skills Evident
- ✅ **Communication:** Case study is clear, concise, compelling
- ✅ **Project Management:** Broke down complex task into deliverables
- ✅ **Problem-Solving:** Data quality challenges (name matching) documented and solved
- ✅ **Attention to Detail:** Comprehensive design specs, color palettes, typography

---

## Recommended Next Actions

### For Immediate Portfolio Use (No Workspace Needed)
1. ✅ **Publish Case Study** → erikemilsson.com + LinkedIn (30 min)
2. ✅ **Upload to GitHub** → Code samples + documentation (1 hour)
3. ⚠️ **Create Mockups** → Figma or PowerPoint (2-4 hours, optional)

### When Workspace Access Available
4. ⏳ **Implement Report** → Follow PORTFOLIO_DESIGN.md (2-3 hours)
5. ⏳ **Take Screenshots** → High-res PNG exports (15 min)
6. ⏳ **Export PDF + PBIX** → Portfolio assets (15 min)
7. ⏳ **Update Portfolio** → Add visual assets to website (30 min)

---

## File Locations Summary

| Asset | File Path | Status |
|-------|-----------|--------|
| Case Study | `/docs/portfolio/CASE_STUDY.md` | ✅ Complete |
| Design Specs | `/docs/portfolio/PORTFOLIO_DESIGN.md` | ✅ Complete |
| DAX Measures (v2, canonical) | `/fabric/OEMInsightBI_v2.SemanticModel/definition/tables/*.tmdl` | ✅ 40 measures — coverage/quality focus |
| DAX Measures (v1 showcase set) | the archived model under `/fabric/archive/` → `definition/tables/_Measures.tmdl` | ⚠️ 46 measures, ARCHIVED model |
| DAX Measures (Full Design) | `/.claude/support/documents/dax_measure_library.md` | ✅ Complete |
| Report JSON | `/fabric/report2.Report/report.json` | ⏳ Needs update |
| Screenshots | N/A | ⏳ Pending |
| PDF Export | N/A | ⏳ Pending |
| PBIX File | N/A | ⏳ Pending |

---

## Questions for Portfolio Discussion

### In Interviews, You Can Discuss:
1. **"Walk me through your design process"**
   → Show PORTFOLIO_DESIGN.md, explain how you structured pages for storytelling

2. **"What's a challenging DAX measure you've written?"**
   → Spend-Weighted EPI Score (SUMX + nested CALCULATE + weighted average)

3. **"How do you handle data quality issues?"**
   → Country name matching (fuzzy logic + confidence scoring + audit tables)

4. **"Tell me about a project where you identified business insights"**
   → Case study (4 high-risk materials, sustainability gap, procurement recommendations)

5. **"How do you prioritize features?"**
   → Designed 40+ measures, implemented 8 for MVP based on business value vs. effort

---

## Portfolio Website Structure (Suggestion)

```
erikemilsson.com/projects/oeminsightbi/
├── index.html (Overview + key highlights)
├── case-study.pdf (Full case study)
├── design-specs.pdf (PORTFOLIO_DESIGN.md converted)
├── screenshots/
│   ├── page1-dashboard.png (when available)
│   └── page2-risk.png (when available)
├── code-samples/
│   ├── measures.tmdl
│   └── fuzzy-matching.py
└── github-link (button to repo)
```

---

**Status:** Portfolio assets are ready for immediate use (case study, design docs, DAX code). Visual assets (screenshots, PDF, PBIX) pending workspace access but not blockers for showcasing the project.

**Next Step:** Publish case study to erikemilsson.com and LinkedIn for maximum visibility.
