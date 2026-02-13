# Frequently Asked Questions (FAQ)

## Project Overview

### Q: What is OEMMatInsightBI?
**A:** A portfolio data engineering and BI project demonstrating end-to-end analytics using Microsoft Fabric. It analyzes procurement data combined with environmental (EPI) and governance (WGI) indicators to assess supply chain sustainability.

### Q: What technologies are used?
**A:** Microsoft Fabric (Lakehouse, Pipeline, Semantic Model, Power BI), PySpark, Delta Lake, SQL Warehouse, Python, DAX.

### Q: What is the current project status?
**A:** Active development - 19 tasks defined, 13 completed (68%). See `/.claude/dashboard.md` for current status.

---

## Task Management

### Q: How do I start working on a task?
**A:** Run `/work task-XXX` where XXX is the task number.

### Q: What does "difficulty ≥7" mean?
**A:** Tasks with difficulty 7 or higher MUST be broken down into subtasks before work begins. This reduces complexity and error risk. See `/.claude/support/reference/difficulty-guide.md`.

### Q: How do I break down a complex task?
**A:** Run `/breakdown task-XXX`. The system will guide you through creating 5-10 subtasks with clear deliverables.

### Q: How do I track my progress?
**A:** Check `/.claude/dashboard.md` for current status. Run `/status` to update progress.

### Q: Can I work on multiple tasks simultaneously?
**A:** Yes, but not recommended for complex tasks (difficulty ≥7). Focus on one at a time to avoid context switching.

---

## Architecture

### Q: What is the medallion architecture?
**A:** A layered data architecture: Bronze (raw ingestion) → Silver (cleaned/standardized) → Gold (business-ready with star schema). See `/.claude/support/documents/architecture/medallion_architecture.md`.

### Q: Why use Delta Lake instead of Parquet?
**A:** Delta Lake provides ACID transactions, time travel, and MERGE support critical for incremental loads and data quality. See ADR-002.

### Q: What is DirectLake mode?
**A:** Microsoft Fabric's zero-copy semantic model mode - Power BI queries lakehouse Delta tables directly without import/refresh. Much faster than traditional import mode.

---

## Data Sources

### Q: Where does the procurement data come from?
**A:** Azure SQL Database (transactional system with procurement records, supplier info, materials).

### Q: What is EPI?
**A:** Environmental Performance Index from Yale - measures countries on 40+ environmental indicators (air quality, biodiversity, climate, etc.).

### Q: What is WGI?
**A:** World Governance Indicators from World Bank - measures governance quality across 6 dimensions (rule of law, corruption control, etc.).

### Q: Are external datasets automated?
**A:** Not yet. Task 005 completed research - EPI and WGI can be automated via HTTP/API. Implementation pending.

---

## Development

### Q: How do I run the pipeline?
**A:** Use custom slash commands:
- `/run-bronze` - Ingest data to bronze layer
- `/run-silver` - Transform to silver layer
- `/run-gold` - Create star schema in gold
- `/run-full-pipeline` - Run all stages end-to-end

### Q: Where are the transformation notebooks?
**A:** `/fabric/*.Notebook/` - `clean_columnsAndHeaders.Notebook` (silver) and `silver-to-gold2.Notebook` (gold).

### Q: How do I test my changes?
**A:** Run unit tests with `pytest tests/ -v`. Framework complete with 35+ test cases. See `/tests/README.md`.

### Q: Can I run this locally?
**A:** Partial - unit tests can run locally. Full pipeline requires Microsoft Fabric workspace access.

---

## Task-Specific Questions

### Q: Task 002 (DAX Measures) - Where is the design?
**A:** See `/.claude/support/documents/dax_measure_library.md` - 40+ measures designed across 5 categories (Procurement, Time Intelligence, Sustainability, Risk, Advanced).

### Q: Task 003 (Power BI Report) - Can I start it now?
**A:** No, it's blocked by Task 002. Complete DAX measures implementation first.

### Q: Task 006 (Incremental Load) - Is the design done?
**A:** Yes! See `/.claude/support/documents/incremental_load_strategy.md` - comprehensive strategy with merge patterns and high-water mark tracking.

### Q: Why are some tasks marked "Design Complete"?
**A:** Design/research phases are done with comprehensive documentation. Implementation is ready to start but awaits Fabric workspace access.

---

## Troubleshooting

### Q: I get "task must be broken down first" error?
**A:** The task has difficulty ≥7. Run `/breakdown task-XXX` to create subtasks, then retry `/complete-task`.

### Q: How do I unblock a task?
**A:** Complete its dependencies first. Check `/MISSION_CONTROL.md` to see what's blocking it.

### Q: Task JSON file seems corrupted?
**A:** Run `/sync-tasks` to validate all JSON files. It will report any schema errors.

---

## Portfolio & Showcase

### Q: What makes this a good portfolio project?
**A:** Demonstrates:
- **Data Engineering**: Medallion architecture, Delta Lake, incremental loads, data quality framework
- **BI Development**: Star schema, 40+ DAX measures, RLS security, report design
- **Best Practices**: Unit tests, error handling, comprehensive documentation, task management

### Q: Which tasks should I prioritize for portfolio impact?
**A:** P1 tasks (001-004) - especially Task 002 (DAX sophistication) and Task 003 (visual storytelling).

### Q: Can I showcase this without Fabric access?
**A:** Yes! Showcase the design work:
- DAX measure library (40+ measures documented)
- RLS security strategy (6 roles)
- Data quality framework (ISO 25012)
- Task management system (advanced automation)
- Comprehensive documentation (7,361 lines across 18 context docs)

---

## Getting Help

### Q: Where do I start if I'm new?
**A:** 1) Read `/.claude/dashboard.md` for current status, 2) Review `.claude/CLAUDE.md` (project instructions), 3) Run `/work task-XXX` to start a task.

### Q: I'm stuck on a task - what should I do?
**A:** 1) Check task's `relatedFiles` in JSON, 2) Review relevant `/.claude/support/documents/` docs, 3) Check `/.claude/support/reference/task-workflow.md`, 4) Run `/status` to see dependencies.

### Q: How do I report issues?
**A:** Currently a portfolio project - no formal issue tracking. Document blockers in task notes within JSON files.

---

*Last Updated: 2025-11-16*
*For more detailed troubleshooting, see TROUBLESHOOTING.md*
