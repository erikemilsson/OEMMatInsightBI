# MISSION CONTROL

**OEMMatInsightBI Project Dashboard**

*Last Updated: 2026-01-15*

---

## Progress Overview

```
Tasks Complete: ██████░░░░░░░░░░░░░░ 13% (2/16)
P1 Tasks:       ██████░░░░░░░░░░░░░░ 13% (1/8)
Claude Work:    ████████████░░░░░░░░ 60%
Erik Work:      ██░░░░░░░░░░░░░░░░░░ 10%
```

| Status | Tasks |
|--------|-------|
| Finished | 009, 013 |
| In Progress | 008, 014 |
| **Waiting for Erik** | **015**, 014 |
| Ready | 016 (after 015) |

---

## Your Action Items

| # | Task | Action | Time |
|---|------|--------|------|
| 1 | **015** | [Sync to Fabric](https://app.fabric.microsoft.com/groups/99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9) | 5 min |
| 2 | **015** | Verify relationships (Model view → arrows go dim→fact) | 5 min |
| 3 | **015** | Test cross-table visual (Total Spend EUR by material_name_std) | 10 min |
| 4 | **014** | Verify 18 measures appear in _Measures table | 5 min |
| 5 | **016** | Build Executive Dashboard per [MEASURE_GUIDE.md](./docs/guides/MEASURE_GUIDE.md) | 30 min |
| 6 | **016** | Build Risk & Sustainability page | 30 min |

---

## Claude's Work Queue

**Next Up:**
1. Task 001 - Data quality notebook + DQ page visuals
2. Task 004 - RLS role definitions in TMDL
3. Task 002 - Remaining DAX measures (subtasks 002-2 through 002-7)
4. Task 005 - EPI/WGI automation notebooks
5. Task 006 - Incremental load logic

---

## Task Summary

| Task | Priority | Status | Owner | Next Step |
|------|----------|--------|-------|-----------|
| 001 | P1 | Pending | Claude | Create data_quality_report.Notebook |
| 002 | P1 | Partial | Claude | Implement remaining DAX measures |
| 003 | P1 | Blocked | - | Needs Task 002 complete |
| 004 | P1 | Design Done | Claude | Implement roles in TMDL |
| 005 | P2 | Research Done | Claude | Create EPI/WGI notebooks |
| 006 | P2 | Design Done | Claude | Implement merge logic |
| 007 | P2 | Design Done | Claude | Implement check functions |
| 008 | P2 | In Progress | Erik | Run pytest locally |
| 009 | P2 | **Finished** | - | - |
| 010 | P3 | Pending | Claude | Write scheduling instructions |
| 011 | P3 | Design Done | Claude | Update pipeline JSON |
| 012 | P3 | Pending | Erik | Run baseline pipeline |
| 013 | P1 | **Finished** | - | - |
| 014 | P1 | In Progress | Erik | Sync TMDL to Fabric |
| 015 | P1 | **Waiting** | Erik | Sync + verify relationships |
| 016 | P1 | Ready | Erik | Build visuals (after 015) |

---

## Active Task Details

### Task 014: Deploy Enhanced Semantic Model & Build Visuals
**Status:** In Progress (Waiting for Erik)

| Step | Owner | Status |
|------|-------|--------|
| Add 10 new DAX measures | Claude | Done |
| Create MEASURE_GUIDE.md | Claude | Done |
| Verify TMDL syntax | Claude | Done |
| Git commit and push | Erik | **Ready** |
| [Sync in Fabric portal](https://app.fabric.microsoft.com/groups/99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9) | Erik | **Ready** |
| Verify 18 measures appear | Erik | Pending |
| Build Executive Dashboard | Erik | Pending |
| Build Risk & Sustainability page | Erik | Pending |
| Export PNG + PDF | Erik | Pending |

---

### Task 015: Fix Semantic Model Relationships
**Status:** Waiting for Erik (Claude done)

| Step | Owner | Status |
|------|-------|--------|
| Diagnose relationship issues | Claude | **Done** |
| Fix relationships.tmdl | Claude | **Done** |
| Sync updated TMDL to Fabric | Erik | **Ready** |
| Verify relationships in Fabric | Erik | **Ready** |
| Test cross-table visuals | Erik | **Ready** |

**Fix Applied:** Reversed all relationships to go dim→fact, added toCardinality: many, added supplier_hq_country_key relationship.

---

### Task 016: Guided Power BI Dashboard Building
**Status:** Ready (Depends on Task 015)

| Step | Owner | Status |
|------|-------|--------|
| Provide step-by-step visual instructions | Claude | Pending |
| Build visuals following guidance | Erik | Pending |
| Review via screenshot, provide feedback | Claude | Pending |
| Apply feedback and build Page 2 | Erik | Pending |
| Export PNG + PDF screenshots | Erik | Pending |

---

## Automation Capabilities

| MCP Server | Status | What It Automates |
|------------|--------|-------------------|
| **Git** | Configured | Commit, push, status, diff |
| **GitHub** | Configured | PRs, issues, repo management |
| **Playwright** | Configured | Browser automation with persistent auth |
| **Gemini** | Configured | AI text/image analysis |

**Playwright Auth (One-Time Setup):**
1. Claude opens Fabric URL via Playwright
2. Erik manually logs in (browser window appears)
3. Session saved to `~/.claude/playwright-auth/fabric-state.json`
4. Future automation works without login

---

## Quick Links

**Fabric Workspace:**
- [Open Workspace](https://app.fabric.microsoft.com/groups/99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9)
- [Lakehouse (oem_lh)](https://app.fabric.microsoft.com/groups/99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9/lakehouses/488fb9f8-e635-4683-90c4-ba4fee9dfadb)
- [Warehouse (oem_wh)](https://app.fabric.microsoft.com/groups/99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9/warehouses/b1cb7506-8d2d-4e4a-97cc-2b580da8eda0)

**Key Files:**
- [MEASURE_GUIDE.md](./docs/guides/MEASURE_GUIDE.md)
- [PORTFOLIO_DESIGN.md](./docs/portfolio/PORTFOLIO_DESIGN.md)
- [DAX Library](./.claude/context/dax_measure_library.md)

**Commands:**
```bash
git add . && git commit -m "Update" && git push   # Sync to Fabric
pytest tests/ -v                                   # Run tests
```

---
*Auto-updated by Claude after each work session*
