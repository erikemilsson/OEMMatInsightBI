# Changelog

All notable changes to the OEMMatInsightBI project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- JSON-based task management system with 12 tasks
- Difficulty scoring (1-10 scale) with automatic breakdown for ≥7
- Task automation: `/complete-task`, `/breakdown`, `/sync-tasks` slash commands
- CLAUDE.md central navigation router
- Comprehensive reference documentation (difficulty-guide, workflow-patterns, task-management-rules)
- Infrastructure directories: hooks/, templates/, adrs/
- CHANGELOG.md, FAQ.md, TROUBLESHOOTING.md

### Changed
- Migrated tasks from markdown-only to JSON format with subtask support
- Enhanced task-overview.md with status matrix and progress tracking

---

## [1.0.0] - 2025-11-03 - Initial Design Phase

### Added
- Project definition document (1600+ lines)
- 18 context documents (7,361 lines total)
- 12 initial tasks defined in markdown format
- 10 custom slash commands for pipeline operations
- Bronze → Silver → Gold pipeline with medallion architecture
- Semantic model with star schema (3 facts, 5 dimensions)

### Design Work Completed
- **DAX Measures Library**: 40+ measures designed across 5 categories (Task 002)
- **RLS Security Strategy**: 6 roles with DAX filters (Task 004)
- **External Data Automation**: Research complete for EPI/WGI (Task 005)
- **Incremental Load Strategy**: Comprehensive design with merge patterns (Task 006)
- **Data Quality Framework**: ISO 25012 quality dimensions (Task 007)
- **Error Handling Strategy**: Retry logic and categorization (Task 011)

### Completed
- **Task 009**: Document DAX Measures (investigation phase)
- **Task 008**: Unit Tests - Framework setup (pytest, 35+ test cases)

---

## [0.1.0] - 2025-10-15 - Project Initialization

### Added
- Microsoft Fabric workspace setup
- Initial pipeline: bronze ingestion (Azure SQL, EPI, WGI, EU CRM)
- Silver transformations: column standardization, unit normalization
- Gold layer: Star schema creation with alias resolution
- Warehouse: SQL endpoint for Power BI DirectLake

---

## Future Releases

### [2.0.0] - TBD - Task 002-003 Implementation
- Implement 40+ DAX measures in semantic model
- Redesign Power BI report with 5 portfolio-quality pages

### [2.1.0] - TBD - Data Quality & RLS
- Implement data quality dashboard (Task 001)
- Implement Row-Level Security with 6 roles (Task 004)

### [3.0.0] - TBD - Performance & Automation
- Incremental load activation (Task 006)
- External data automation (Task 005)
- Pipeline performance optimization (Task 012)
- Error handling & retry logic (Task 011)
- Automated scheduling (Task 010)

---

*For detailed task status, see `/.claude/tasks/task-overview.md`*
