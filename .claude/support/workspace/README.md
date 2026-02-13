# Workspace

Claude's working area for temporary and in-progress documents.

## Directories

- **scratch/** - Throwaway notes, quick analysis, temporary thinking
- **research/** - Web search results, reference material, gathered context
- **drafts/** - Work-in-progress documents before they move to their final location

## Rules

- Never create working documents in project root
- Use descriptive filenames (`api-comparison.md`, not `task-5-research.md`)
- When a draft becomes permanent, discuss where it should go and move it
- Delete scratch files when no longer needed
- Files older than 30 days trigger `/health-check` warning

## What goes where

| Type | Workspace Location | Final Destination (when graduated) |
|------|-------------------|-------------------------------------|
| Quick notes | `scratch/` | Delete when done |
| Web search summaries | `research/` | Delete or → `.archive/` |
| API docs, reference | `research/` | Project's docs folder |
| Design docs in progress | `drafts/` | Project's docs folder |
| Spec sections being drafted | `drafts/` | `.claude/spec_v{N}.md` |
| Decision research | `drafts/` | `.claude/support/decisions/.archive/` |
