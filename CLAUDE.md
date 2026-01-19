# OEMMatInsightBI - Claude Code Navigation

**Welcome to the OEMMatInsightBI Project!**

This document helps Claude navigate the project structure and find relevant information.

---

## Quick Start

1. **Current Status**: Check `/MISSION_CONTROL.md` first (single source of truth for tasks)
2. **Project Overview**: See `/project_definition.md` (comprehensive spec)
3. **Working on Tasks**: Use `/complete-task task-XXX` to start

---

## MISSION_CONTROL.md (Primary Dashboard)

**IMPORTANT: Claude must update `/MISSION_CONTROL.md` at the end of every work session.**

### What to Update
- Progress bars and percentages
- Task status lists (Finished/In Progress/Pending)
- "Your Action Items" section for Erik
- "Last Session" date and "Next Action" summary

### Keep It Clean
- Remove completed session details after a few days
- Keep action items current (remove done items)
- Focus on what matters now, not history

### Format
```markdown
*Last Session: YYYY-MM-DD*
*Next Action: [Brief description of what Erik should do next]*
```

---

## Project Structure

```
OEMMatInsightBI/
├── MISSION_CONTROL.md         # Task status dashboard (update this!)
├── project_definition.md      # Complete project specification
├── fabric/                    # Microsoft Fabric artifacts
│   ├── *.Notebook/            # PySpark transformation notebooks
│   ├── *.SemanticModel/       # Power BI semantic model
│   └── *.DataPipeline/        # Orchestrator pipeline
├── .claude/
│   ├── tasks/                 # Task JSON files (task-001.json to task-018.json)
│   ├── context/               # Project knowledge base
│   ├── reference/             # Reference materials
│   └── commands/              # Slash command definitions
├── src/transformations/       # Testable Python modules
└── tests/                     # pytest unit tests
```

---

## Context Documents

Located in `/.claude/context/`:

**Architecture:**
- `architecture/medallion_architecture.md` - Bronze/Silver/Gold layers
- `architecture/semantic_model.md` - Star schema design
- `architecture/data_sources.md` - 5 data sources
- `architecture/orchestration.md` - Pipeline design

**Data Engineering:**
- `incremental_load_strategy.md` - Delta MERGE patterns
- `data_quality_framework.md` - ISO 25012 quality checks
- `data_quality_architecture.md` - Quality observability tables
- `external_data_automation.md` - EPI/WGI automation

**BI & Security:**
- `dax_measure_library.md` - 40+ DAX measures
- `rls_security_strategy.md` - 6 security roles

**Standards:**
- `standards/coding_standards.md` - Python best practices
- `standards/sql_standards.md` - SQL style guide
- `standards/naming_standards.md` - Naming conventions

---

## Reference Materials

Located in `/.claude/reference/`:

- `glossary.md` - 98 terms defined
- `task-workflow.md` - Task management workflow
- `difficulty-guide.md` - Difficulty scoring (1-10)
- `schemas/bronze_tables.md` - Bronze layer schema
- `schemas/gold_tables.md` - Gold layer schema

---

## Common Commands

### Task Management
```bash
/complete-task task-XXX   # Start working on a task
/breakdown task-XXX       # Decompose complex task (difficulty ≥7)
/sync-tasks               # Update progress and validate
```

### Pipeline Operations
```bash
/run-bronze              # Run bronze layer ingestion
/run-silver              # Run silver transformations
/run-gold                # Run gold layer creation
/run-full-pipeline       # Run complete pipeline
```

### Data Quality
```bash
/check-quality           # Run data quality checks
/validate-schema         # Validate table schemas
/view-unmapped           # View unmapped values
```

---

## Getting Started with a Task

1. Check `/MISSION_CONTROL.md` for current priorities
2. Read the task JSON: `/.claude/tasks/task-XXX.json`
3. Review related context docs (listed in task's `relatedFiles`)
4. Use `/complete-task task-XXX` to begin
5. Update MISSION_CONTROL.md when done

---

## Navigation Tips

**Looking for a specific file?**
- Use Glob tool with patterns like `**/*.ipynb` or `**/*.tmdl`

**Need to understand a concept?**
- Check `/.claude/reference/glossary.md` first
- Then relevant context doc in `/.claude/context/`

**Blocked or confused?**
- Check MISSION_CONTROL.md for current status
- Review `/.claude/reference/task-workflow.md` for guidance

---

*Last Updated: 2026-01-19*
