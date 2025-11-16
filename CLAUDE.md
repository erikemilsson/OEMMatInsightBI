# OEMMatInsightBI - Claude Code Navigation

**Welcome to the OEMMatInsightBI Project!**

This document serves as a central router to help you navigate the project structure and find relevant information quickly.

---

## 🎯 Quick Start

**New to this project?** Start here:

1. **Project Overview**: See `/project_definition.md` (comprehensive 1600-line project spec)
2. **Task Management**: See `/.claude/tasks/task-overview.md` (12 tasks with progress tracking)
3. **Working on Tasks**: Use `/complete-task task-XXX` to start a task
4. **Syncing Progress**: Use `/sync-tasks` to update task status

---

## 📁 Project Structure

```
OEMMatInsightBI/
├── fabric/                    # Microsoft Fabric artifacts
│   ├── *.DataPipeline/        # Orchestrator pipeline (bronze → silver → gold)
│   ├── *.Notebook/            # PySpark transformation notebooks
│   ├── *.Dataflow/            # Power Query dataflows (bronze ingestion)
│   ├── *.SemanticModel/       # Power BI semantic model (star schema)
│   ├── *.Report/              # Power BI report (to be redesigned)
│   └── oem_wh.Warehouse/      # SQL warehouse for serving layer
│
├── .claude/                   # Claude Code environment (task management & context)
│   ├── commands/              # Slash commands (/complete-task, /breakdown, /sync-tasks)
│   ├── context/               # Project knowledge base (18 comprehensive docs)
│   ├── tasks/                 # 12 tasks in JSON format + task-overview.md
│   └── reference/             # Reference materials (glossary, schemas, guides)
│
├── tests/                     # pytest unit tests (framework complete)
├── src/transformations/       # Extracted testable modules (key_generation, data_quality)
├── project_definition.md      # 📌 START HERE - Complete project specification
├── CLAUDE.md                  # This file - Navigation router
└── README.md                  # User-facing project documentation
```

---

## 🔍 Finding Information

### By Topic

**Architecture & Design:**
- 📐 Overall architecture: `/project_definition.md` (lines 113-181)
- 🎨 Semantic model: `/.claude/context/semantic_model_design.md`
- 📊 DAX measures library: `/.claude/context/dax_measure_library.md` (40+ measures designed)
- 🔐 RLS security strategy: `/.claude/context/rls_security_strategy.md` (6 roles)

**Data Engineering:**
- 🔄 Pipeline orchestration: `/project_definition.md` (lines 589-720)
- 📦 Incremental load strategy: `/.claude/context/incremental_load_strategy.md`
- ✅ Data quality framework: `/.claude/context/data_quality_framework.md` (ISO 25012)
- 🔌 External data automation: `/.claude/context/external_data_automation.md` (EPI, WGI)

**Operational Excellence:**
- 🚨 Error handling strategy: `/.claude/context/error_handling_strategy.md`
- ⚙️  Pipeline configuration: `/project_definition.md` (lines 588-720)

**Business Context:**
- 🎯 Business requirements: `/.claude/context/business_requirements.md`
- 📚 Glossary: `/.claude/reference/glossary.md` (98 terms)
- 🏗️ Architecture decisions: `/.claude/context/architecture_overview.md`

**Development Standards:**
- 📝 Naming conventions: `/.claude/context/naming_conventions.md`
- 🐍 Python coding standards: `/.claude/context/python_coding_standards.md`
- 💾 SQL coding standards: `/.claude/context/sql_coding_standards.md`
- 📊 Git workflow: `/.claude/context/git_workflow.md`

### By Task Priority

**P1 Tasks (Portfolio Showcase):**
- Task 001: Data Quality Visibility → `/.claude/tasks/task-001.json`
- Task 002: DAX Measures Implementation → `/.claude/tasks/task-002.json` (Broken Down - 7 subtasks)
- Task 003: Power BI Report Redesign → `/.claude/tasks/task-003.json` (Depends on Task 002)
- Task 004: RLS Security → `/.claude/tasks/task-004.json` (Design complete)

**P2 Tasks (Technical Depth):**
- Task 005-009: See `/.claude/tasks/task-overview.md`

**P3 Tasks (Infrastructure):**
- Task 010-012: See `/.claude/tasks/task-overview.md`

---

## 🎮 Common Commands

### Task Management
```bash
# Start working on a task
/complete-task task-002

# Break down complex task into subtasks
/breakdown task-003

# Sync all task progress and update overview
/sync-tasks
```

### Pipeline Execution (Fabric Workspace)
```bash
# View bronze to gold pipeline definition
# Location: /fabric/orchestrator_pipeline_bronze_to_gold.DataPipeline/

# Custom slash commands for pipeline operations:
/run-bronze          # Run bronze layer ingestion
/run-silver          # Run silver transformations
/run-gold            # Run gold layer creation
/run-full-pipeline   # Run complete bronze → gold → warehouse
```

### Data Validation
```bash
/check-quality           # Run data quality checks
/validate-schema         # Validate table schemas
/view-unmapped           # View unmapped country/material values
/review-transformations  # Review transformation logic
```

### Fabric Integration
```bash
/sync-from-fabric    # Pull latest artifacts from Fabric workspace
/sync-to-fabric      # Push local changes to Fabric workspace
```

---

## 📚 Context Documents (18 Files)

**Business & Requirements:**
1. `business_requirements.md` - Stakeholder needs and success criteria
2. `data_sources.md` - 5 data sources (Azure SQL, EPI, WGI, EU CRM)

**Architecture & Design:**
3. `architecture_overview.md` - Medallion pattern, orchestration, semantic model
4. `semantic_model_design.md` - Star schema with 3 facts + 5 dimensions
5. `dax_measure_library.md` - 40+ measures designed across 5 categories
6. `rls_security_strategy.md` - 6 security roles with DAX filters

**Data Engineering Strategies:**
7. `incremental_load_strategy.md` - High-water mark, Delta MERGE patterns
8. `data_quality_framework.md` - ISO 25012 quality dimensions, 9 check functions
9. `external_data_automation.md` - EPI/WGI automation research

**Operational Excellence:**
10. `error_handling_strategy.md` - Retry logic, error categorization, alerting
11. `orchestration_strategy.md` - Pipeline design patterns

**Standards & Guidelines:**
12. `naming_conventions.md` - File, table, column naming standards
13. `sql_coding_standards.md` - SQL style guide
14. `python_coding_standards.md` - PySpark best practices
15. `git_workflow.md` - Branching strategy, commit conventions

**Advanced Topics:**
16. `medallion_pattern.md` - Bronze → Silver → Gold layering
17. `alias_resolution_logic.md` - Country/material name matching with confidence scoring
18. `row_level_security.md` - (See rls_security_strategy.md)

**Total Context:** ~7,361 lines of comprehensive documentation

---

## 🎯 Tasks Overview (12 Tasks)

| Status | Count | % |
|--------|-------|---|
| ✅ Finished | 1 | 8% |
| 🚧 In Progress | 1 | 8% |
| 📋 Design Complete | 5 | 42% |
| ⏳ Pending | 5 | 42% |

**See:** `/.claude/tasks/task-overview.md` for full breakdown

---

## 🔧 Reference Materials

**Glossary:** `/.claude/reference/glossary.md` (98 terms)
- OEM, EPI, WGI, CRM, RLS, DirectLake, V-Order, etc.

**Schema References:**
- Bronze schema: `/.claude/reference/bronze_schema_reference.md`
- Gold schema: `/.claude/reference/gold_schema_reference.md`
- DAX measures: `/.claude/reference/dax_measures.md` (legacy, see context/dax_measure_library.md)

**Alias Mappings:**
- Country aliases: `/.claude/reference/country_alias_mapping.md`
- Material aliases: `/.claude/reference/material_alias_mapping.md`

**Task Management:**
- Difficulty scoring: `/.claude/reference/difficulty-guide.md` (1-10 scale, breakdown at ≥7)
- Workflow patterns: `/.claude/reference/workflow-patterns.md` (task lifecycle, best practices)
- Management rules: `/.claude/reference/task-management-rules.md` (automation rules)

---

## 🚀 Getting Started with Development

### 1. **Understand the Project**
   - Read `/project_definition.md` (comprehensive spec)
   - Review `/.claude/context/architecture_overview.md`
   - Check `/.claude/tasks/task-overview.md` for current priorities

### 2. **Pick a Task**
   - See `/.claude/tasks/task-overview.md` for available tasks
   - P1 tasks are highest priority (portfolio showcase)
   - Design-complete tasks (002, 004, 005, 006, 007, 011) are ready to implement

### 3. **Start Work**
   ```bash
   # Example: Start DAX Measures task
   /complete-task task-002
   ```

### 4. **Track Progress**
   ```bash
   # Daily sync to update progress
   /sync-tasks
   ```

---

## 🎨 Portfolio Highlights

This project demonstrates:

**Data Engineering:**
- ✅ Medallion architecture (bronze → silver → gold)
- ✅ Delta Lake with MERGE operations (incremental load)
- ✅ PySpark transformations with unit tests
- ✅ Data quality framework (ISO 25012)

**BI Development:**
- ✅ Star schema semantic model (DirectLake)
- ✅ 40+ DAX measures (time intelligence, sustainability, risk)
- ✅ Row-level security (6 roles)
- ✅ Report design (5 pages planned)

**Operational Excellence:**
- ✅ Error handling & retry logic
- ✅ Pipeline orchestration
- ✅ Automated testing (pytest framework)
- ✅ Comprehensive documentation

---

## 📞 Navigation Tips

**Looking for a specific file?**
- Use Glob tool: `**/*.ipynb` for notebooks, `**/*.tmdl` for semantic model
- Check `/project_definition.md` for file locations (lines 183-584)

**Need to understand a concept?**
- Check `/.claude/reference/glossary.md` first
- Then relevant context doc in `/.claude/context/`

**Starting a task?**
- Always use `/complete-task task-XXX` (enforces validation rules)
- Check `/.claude/tasks/task-XXX.json` for details
- Review related context docs before starting

**Blocked or confused?**
- Run `/sync-tasks` to see overall project status
- Check `/.claude/reference/workflow-patterns.md` for guidance
- Review task dependencies in task-overview.md

---

## 🆘 Need Help?

- **Task management questions**: See `/.claude/reference/workflow-patterns.md`
- **Technical questions**: See relevant `/.claude/context/` docs
- **Project scope questions**: See `/project_definition.md`
- **Terminology questions**: See `/.claude/reference/glossary.md`

---

*Last Updated: 2025-11-16*
*Project Status: Active Development (12 tasks, 8% complete)*
*Next Priority: Complete Task 002 (DAX Measures) to unblock Task 003 (Power BI Report)*
