# Archiving and File Placement Rules

## Archive Locations

Do not create new archive locations. Use these canonical paths:

| What | Archive Location | When |
|------|------------------|------|
| Spec versions | `.claude/support/previous_specifications/spec_v{N}.md` | Before creating v{N+1} |
| Decomposed specs | `.claude/support/previous_specifications/spec_v{N}_decomposed.md` | After task decomposition |
| Completed tasks | `.claude/tasks/archive/` | When task count exceeds 100 |

## Workspace

Temporary documents go in `.claude/support/workspace/` (scratch, research, drafts). This is Claude's scratch space for intermediate analysis, research notes, and working drafts.

## User-Facing Documents

Operational documents the user needs to work with (invitation letters, consent forms, facilitation guides, reports, etc.) go in the **project root**, not in `.claude/`. The default convention is a `docs/` folder, but the user may organize further (e.g., `docs/phase-1/`, `docs/operations/`). The system respects the user's folder structure rather than overriding it.

**Principle:** `.claude/` is Claude's environment. The project root is the user's environment. Documents the user works with daily belong in the user's environment.

**During spec decomposition**, when tasks will produce user-facing documents, prompt about folder structure:
```
This project will produce operational documents (e.g., [examples from spec]).
Default location: docs/
Would you like a different structure? [D] Use docs/ | [C] Custom folder | [S] Skip (decide later)
```

**Graduation:** If intermediate workspace documents become operational (user references them daily, dashboard links to them), suggest moving them to the project root during `/health-check` or `/work complete`.

## Reference Documents

User-provided reference files (PDFs, contracts, vendor docs, etc.) go in `.claude/support/documents/`. These are inputs to Claude's work, not outputs the user needs to find. When the user provides a file path, move it there with a descriptive filename.

## Credentials and Secrets

Never commit API keys, passwords, tokens, or credentials to any tracked file. Use environment variables or a `.env` file (which must be in `.gitignore`). If a task requires secrets, set `owner: "human"` for the credential setup step.

## Feedback

Fleeting ideas and improvement thoughts go in `.claude/support/feedback/`. Quick capture with `/feedback [text]`, triage with `/feedback review`.

## References

- All canonical paths: `.claude/support/reference/paths.md`
- Workspace guide: `.claude/support/workspace/README.md`
- Documents guide: `.claude/support/documents/README.md`
- Feedback guide: `.claude/support/feedback/README.md`
