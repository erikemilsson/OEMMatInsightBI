# Canonical Paths Reference

> **Single source of truth for template paths.** Other documentation should reference this file rather than defining paths independently. When paths change, update this file first, then update references.

## Path Reference Table

| Purpose | Path |
|---------|------|
| Current spec | `.claude/spec_v{N}.md` |
| Archived specs | `.claude/support/previous_specifications/` |
| Decomposed spec snapshots | `.claude/support/previous_specifications/spec_v{N}_decomposed.md` |
| Tasks | `.claude/tasks/` |
| Archived tasks | `.claude/tasks/archive/` |
| Decisions | `.claude/support/decisions/` |
| Decision research archive | `.claude/support/decisions/.archive/` |
| Workspace/scratch | `.claude/support/workspace/` |
| Dashboard | `.claude/dashboard.md` |
| Dashboard state sidecar | `.claude/dashboard-state.json` |
| Session sentinel | `.claude/tasks/.last-clean-exit.json` |
| Questions | `.claude/support/questions/questions.md` |
| Feedback (active) | `.claude/support/feedback/feedback.md` |
| Feedback (archived) | `.claude/support/feedback/archive.md` |
| Documents | `.claude/support/documents/` |
| Vision documents | `.claude/vision/` |
| Reference docs | `.claude/support/reference/` (see `README.md` for index) |
| Learnings | `.claude/support/learnings/` (see `README.md` for categories) |
| Commands | `.claude/commands/` |
| Agents | `.claude/agents/` |

## Notes

- **Spec versioning**: The `{N}` in spec paths is replaced with the version number (e.g., `spec_v1.md`, `spec_v2.md`)
- **Single-spec invariant**: There must be exactly one `spec_v{N}.md` in `.claude/` at all times. Version transitions archive the old file before creating the new one. `/health-check` enforces this.
- **Version discovery**: `/work` globs for `.claude/spec_v*.md` and uses the highest N as the current version.
- **Archive convention**: Archived items retain their original filename structure within their archive directory
- **Workspace is ephemeral**: Files in workspace may be deleted between sessions; use for scratch work only
