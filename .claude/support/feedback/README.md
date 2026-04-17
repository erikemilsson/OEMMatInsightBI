# Feedback

Lightweight capture and triage system for fleeting ideas and improvement thoughts during project work.

## Purpose

Capture ideas as they arise without losing context. Triage them through a structured pipeline — grouping, refinement, impact assessment — before they reach the spec. Provides a path from "I just had an idea" to "this is assessed, approved, and ready for the spec."

## Files

| File | Purpose |
|------|---------|
| `feedback.md` | Active feedback items — inbox of actionable items |
| `archive.md` | All resolved items — promoted, absorbed, closed, and not relevant |

## Status Flow

```
new → reviewing → refined → ready → promoted (auto-archived via /iterate)
new → absorbed (combined into another, immediately archived)
new → closed (investigated, decided against, archived)
new → archived (not relevant, quick triage)
```

| Status | Location | Meaning |
|--------|----------|---------|
| `new` | feedback.md | Just captured, not yet reviewed |
| `reviewing` | feedback.md | Currently being refined |
| `refined` | feedback.md | Distilled to core insight, awaiting impact assessment |
| `ready` | feedback.md | Impact assessed and user-approved, eligible for `/iterate` |
| `promoted` | archive.md | Incorporated into spec via `/iterate` |
| `absorbed` | archive.md | Combined into another item (has `absorbed_into` pointer) |
| `closed` | archive.md | Investigated but decided against |
| `archived` | archive.md | Not relevant (quick triage) |

## Review Phases

`/feedback review` runs a 3-phase process:

| Phase | What Happens | User Controls |
|-------|-------------|---------------|
| 1. Overview & Grouping | Show all items, suggest combinations | Confirm/adjust grouping |
| 2. Refinement | Per-item: directed questions, distill insight | Refine, close, archive, skip, edit per item |
| 3. Impact Assessment | Per-item: reads spec + tasks, presents impact | Approve (→ ready), close, or skip per item |

## Entry Format

Active entries in `feedback.md`:

```markdown
## FB-NNN: [Brief title]

**Status:** new | reviewing | refined | ready
**Captured:** YYYY-MM-DD

[Original text as captured]

**Refined:** [Distilled core insight — added during Phase 2]
```

Archived entries in `archive.md` add a disposition line:

```markdown
## FB-NNN: [Brief title]

**Status:** promoted | absorbed | closed | archived
**Captured:** YYYY-MM-DD

[Original text]

**Refined:** [If refined before archival]
**Promoted:** YYYY-MM-DD — Incorporated into spec v{N} § [section]
**Absorbed:** YYYY-MM-DD — Combined into FB-NNN
**Absorbed Into:** FB-NNN
**Closed:** YYYY-MM-DD — [Reason]
**Archived:** YYYY-MM-DD — [Reason]
```

## Commands

| Command | What It Does |
|---------|-------------|
| `/feedback [text]` | Quick capture — append new entry with `new` status |
| `/feedback list` | Show summary counts by status + active item list |
| `/feedback review` | 3-phase review: grouping → refinement → impact assessment |
| `/feedback review {id}` | Single-item review (adapts to current status) |

## See Also

- `/feedback` command — `.claude/commands/feedback.md`
- `/iterate` Step 1b — Picks up `ready` items for spec incorporation
- Dashboard → Action Required — Shows count when unhandled items exist
