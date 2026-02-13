# Architecture Decision Records (ADRs)

This directory contains Architecture Decision Records documenting significant architectural decisions made in the OEMMatInsightBI project.

## ADR Format

Each ADR follows this structure:
- **Title**: ADR-XXX: Decision title
- **Status**: Proposed | Accepted | Deprecated | Superseded
- **Context**: What is the issue we're addressing?
- **Decision**: What did we decide?
- **Consequences**: What are the trade-offs?
- **Alternatives Considered**: What other options were evaluated?

## Existing ADRs

### ADR-001: Adopt Medallion Architecture Pattern
Status: Accepted
- Decided to use bronze → silver → gold layering
- Rationale: Clear data quality progression, aligns with Microsoft Fabric best practices

### ADR-002: Use Delta Lake Format for All Lakehouse Tables
Status: Accepted
- Decided to use Delta Lake exclusively (not Parquet)
- Rationale: ACID transactions, time travel, MERGE support for incremental loads

### ADR-003: Implement JSON-Based Task Management System
Status: Accepted (2025-11-16)
- Migrated from markdown-only to JSON format with difficulty scoring
- Rationale: Enables automation, structured workflows, progress tracking

## Creating New ADRs

Use template: `/.claude/templates/adr-template.md`
Number sequentially: ADR-004, ADR-005, etc.
Save to this directory with format: `ADR-XXX-short-title.md`
