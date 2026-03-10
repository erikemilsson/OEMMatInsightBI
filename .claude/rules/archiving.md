# Archiving and File Placement Rules

## Archive Locations

Do not create new archive locations. Use these canonical paths:

| What | Archive Location | When |
|------|------------------|------|
| Spec versions | `.claude/support/previous_specifications/spec_v{N}.md` | Before creating v{N+1} |
| Decomposed specs | `.claude/support/previous_specifications/spec_v{N}_decomposed.md` | After task decomposition |
| Completed tasks | `.claude/tasks/archive/` | When task count exceeds 100 |

## Workspace

Temporary documents go in `.claude/support/workspace/` (scratch, research, drafts). Never create working documents in the project root.

## Documents

User-provided reference files (PDFs, contracts, vendor docs, etc.) go in `.claude/support/documents/`. When the user provides a file path, move it there with a descriptive filename.

## Credentials and Secrets

Never commit API keys, passwords, tokens, or credentials to any tracked file. Use environment variables or a `.env` file (which must be in `.gitignore`). If a task requires secrets, set `owner: "human"` for the credential setup step.

## Feedback

Fleeting ideas and improvement thoughts go in `.claude/support/feedback/`. Quick capture with `/feedback [text]`, triage with `/feedback review`.

## References

- All canonical paths: `.claude/support/reference/paths.md`
- Workspace guide: `.claude/support/workspace/README.md`
- Documents guide: `.claude/support/documents/README.md`
- Feedback guide: `.claude/support/feedback/README.md`
