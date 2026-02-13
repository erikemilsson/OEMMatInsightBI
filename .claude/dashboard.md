# Project Dashboard

**OEMMatInsightBI**

*Last Updated: 2026-02-13*

---

## Progress Overview

```
Tasks Complete: █████████████████████░░░░░░░░░░░ 68% (13/19)
P1 Tasks:       ████████████████████████████████ 100% (8/8)
P2 Tasks:       ██████████████████░░░░░░░░░░░░░░ 56% (5/9 — includes 017-019)
Pending:        6 tasks remaining
```

---

## Task Status

| Status | Tasks |
|--------|-------|
| **Finished** (13) | 001, 002, 003, 004, 008, 009, 013, 014, 015, 016, 017, 018, 019 |
| **In Progress** (0) | — |
| **Pending** (6) | 005, 006, 007, 010, 011, 012 |

### Pending Task Details

| Task | Title | Owner | Difficulty |
|------|-------|-------|------------|
| 005 | Automate External Data Ingestion | both | 7 |
| 006 | Implement Incremental Load Logic | both | 7 |
| 007 | Add Comprehensive Data Quality Checks | both | 6 |
| 010 | Configure Pipeline Scheduling | erik | 4 |
| 011 | Implement Error Handling & Retry Logic | both | 6 |
| 012 | Optimize Pipeline Performance | both | 5 |

### Task Ownership Matrix

| Task | Claude Does | Erik Does |
|------|-------------|-----------|
| **005** | Write Copy Activity + API notebook | Deploy & test in Fabric |
| **006** | Write MERGE logic + parameters | Deploy & test loads |
| **007** | Write DQ notebook (9 checks) | Deploy & test alerts |
| **010** | Write docs | **Configure in Fabric UI** |
| **011** | Write retry config + logging | Deploy & test failures |
| **012** | Write optimization code | **Run baselines & validate** |

**Ready for Claude now:** 005, 006, 007, 011
**Primarily Erik tasks:** 010, 012

---

## Action Required (Erik)

| # | Action | Priority |
|---|--------|----------|
| 1 | Run `sample-quality-data` notebook in Fabric (task 017 verification) | Medium |
| 2 | Configure pipeline scheduling in Fabric UI (task 010) | Low |
| 3 | Run performance baselines (task 012) | Low |

---

## Quick Links

- **Spec:** `.claude/spec_v1.md`
- **Tasks:** `.claude/tasks/task-*.json`
- **Fabric Workspace:** [Open](https://app.fabric.microsoft.com/groups/99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9)
- **Lakehouse:** [oem_lh](https://app.fabric.microsoft.com/groups/99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9/lakehouses/488fb9f8-e635-4683-90c4-ba4fee9dfadb)

---

*Next Action: Pick up task 005, 006, 007, or 011 with `/work`*
