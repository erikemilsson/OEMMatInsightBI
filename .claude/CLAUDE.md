# OEMMatInsightBI - Project Instructions

## Model Requirement

This project requires **Claude Opus 4.6** (claude-opus-4-6) for all implementation, verification, and planning work.

## Project Overview

**OEMMatInsightBI** is a Microsoft Fabric-based BI solution for OEM procurement material sourcing analysis. It uses a medallion architecture (Bronze/Silver/Gold) with PySpark notebooks, Delta Lake tables, a Power BI semantic model (TMDL), and DAX measures.

**Technology Stack:** Microsoft Fabric, PySpark, Delta Lake, Power BI, DAX, TMDL

**Spec:** `.claude/spec_v1.md` (comprehensive project specification)

---

## Project Structure

```
OEMMatInsightBI/
├── .claude/
│   ├── CLAUDE.md              # This file (project instructions)
│   ├── dashboard.md           # Auto-generated project status
│   ├── spec_v1.md             # Project specification (versioned)
│   ├── agents/                # Specialist agent definitions
│   │   ├── implement-agent.md
│   │   ├── verify-agent.md
│   │   └── research-agent.md
│   ├── tasks/                 # Task JSON files (task-001 to task-019)
│   │   └── archive/           # Archived completed tasks
│   ├── commands/              # Slash command definitions (19 commands)
│   └── support/
│       ├── documents/         # Domain knowledge (architecture, schemas, standards)
│       ├── reference/         # Template workflow docs
│       ├── decisions/         # Architecture Decision Records
│       ├── feedback/          # User feedback capture
│       ├── learnings/         # Lessons learned
│       ├── questions/         # Open questions
│       ├── workspace/         # Scratch/drafts (gitignored)
│       └── previous_specifications/
├── fabric/                    # Microsoft Fabric artifacts
│   ├── *.Notebook/            # PySpark transformation notebooks
│   ├── *.SemanticModel/       # Power BI semantic model (TMDL)
│   ├── *.DataPipeline/        # Orchestrator pipeline
│   └── *.Lakehouse/           # Lakehouse metadata
├── src/transformations/       # Testable Python modules
└── tests/                     # pytest unit tests
```

---

## Workflow

### Starting Work

1. Check `.claude/dashboard.md` for current status and priorities
2. Use `/work` to start the next task (auto-routes to highest priority)
3. Or use `/work task-XXX` for a specific task

### Commands

**Task Management:**
- `/work` - Start or continue work on tasks (primary workflow command)
- `/work task-XXX` - Work on a specific task
- `/iterate` - Refine current implementation based on feedback
- `/status` - Regenerate dashboard and show progress
- `/breakdown task-XXX` - Decompose complex tasks (difficulty >= 7)
- `/research` - Research a topic before implementation
- `/feedback` - Capture user feedback
- `/health-check` - Validate project integrity

**Pipeline Operations (domain-specific):**
- `/run-bronze` - Run bronze layer ingestion
- `/run-silver` - Run silver transformations
- `/run-gold` - Run gold layer creation
- `/run-full-pipeline` - Run complete pipeline (Bronze to Gold)

**Data Quality (domain-specific):**
- `/check-quality` - Run data quality checks
- `/validate-schema` - Validate table schemas
- `/view-unmapped` - View unmapped values
- `/review-transformations` - Review transformation logic

**Fabric Sync (domain-specific):**
- `/sync-from-fabric` - Pull changes from Fabric workspace
- `/sync-to-fabric` - Push changes to Fabric workspace

**Deprecated (redirects):**
- `/complete-task` - Use `/work` instead
- `/sync-tasks` - Use `/status` instead

### Task Rules

1. Only work on tasks with status "Pending" or "In Progress"
2. Never skip verification - all finished tasks need `task_verification`
3. Update `dashboard.md` at the end of every work session
4. Use `notes` field for completion context transfer
5. Tasks with `owner: "erik"` require Erik's action in Fabric

### Dashboard Updates

**Update `.claude/dashboard.md` at the end of every work session:**
- Progress bars and percentages
- Task status table
- Erik's action items
- Last session date and next action

---

## Domain Knowledge

Located in `.claude/support/documents/`:

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

**Schemas:**
- `schemas/bronze_tables.md` - Bronze layer schema
- `schemas/gold_tables.md` - Gold layer schema

**Reference:**
- `glossary.md` - 98 terms defined

---

## Design Philosophy

- **Medallion architecture**: Bronze (raw) -> Silver (cleaned) -> Gold (business logic)
- **Delta Lake**: All gold tables use Delta format for MERGE support
- **TMDL**: Semantic model defined as code (not .pbix)
- **Quality observability**: Three tables track data quality trends over time
- **Testable transforms**: Python modules in `src/` with pytest coverage

## Quick Links

**Fabric Workspace:**
- [Open Workspace](https://app.fabric.microsoft.com/groups/99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9)
- [Lakehouse (oem_lh)](https://app.fabric.microsoft.com/groups/99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9/lakehouses/488fb9f8-e635-4683-90c4-ba4fee9dfadb)

---

*Last Updated: 2026-02-13*
