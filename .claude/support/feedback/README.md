# Feedback

Lightweight capture and triage system for fleeting ideas and improvement thoughts during project work.

## Purpose

Capture ideas as they arise without losing context. Triage them later into actionable spec improvements or archive them with reasons. Provides a structured path from "I just had an idea" to "this is now in the spec."

## Files

| File | Purpose |
|------|---------|
| `feedback.md` | Active feedback items — new, reviewing, and refined |
| `archive.md` | Items triaged as not relevant, preserved with reasons |

## Status Flow

```
new → refined → promoted (incorporated into spec via /iterate)
new → archived (not relevant, moved to archive.md with reason)
```

| Status | Meaning |
|--------|---------|
| `new` | Just captured, not yet reviewed |
| `reviewing` | Currently being triaged |
| `refined` | Relevant, distilled to core insight, ready for spec integration |
| `promoted` | Incorporated into spec via `/iterate` |
| `archived` | Not relevant, moved to `archive.md` |

## Entry Format

Each entry in `feedback.md` uses this format:

```markdown
## FB-NNN: [Brief title]

**Status:** new | reviewing | refined | promoted
**Captured:** YYYY-MM-DD

[Original text as captured]

**Refined:** [Distilled core insight — added during /feedback review]
**Promoted:** YYYY-MM-DD [Added when incorporated via /iterate]
```

## Commands

| Command | What It Does |
|---------|-------------|
| `/feedback [text]` | Quick capture — append new entry with `new` status |
| `/feedback list` | Show summary counts by status + item list |
| `/feedback review` | Batch triage all `new`/`reviewing` items |
| `/feedback review {id}` | Triage a single item (e.g., `/feedback review FB-003`) |

## See Also

- `/feedback` command — `.claude/commands/feedback.md`
- `/iterate` Step 1b — Surfaces refined feedback during spec review
- Dashboard → Action Required — Shows count when unhandled items exist
