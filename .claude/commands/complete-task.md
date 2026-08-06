# Complete Task (DEPRECATED)

> **This command has been replaced by `/work`.** Use `/work task-XXX` to work on a specific task, or `/work` to auto-detect what needs doing.
>
> This redirect will be removed in a future session.

When this command is invoked, inform the user:

```
The /complete-task command has been replaced by /work.

Usage:
  /work                  → Auto-detect what needs doing
  /work task-XXX         → Work on specific task
  /work complete         → Complete current in-progress task
  /work complete {id}    → Complete specific task
```

> **Note (2026-08-06, task-058):** this file previously pointed at
> `.claude/support/documents/complete-task-legacy.md`. That file **existed as 389 lines
> until 2026-08-04**, when it was deleted in commit `e5d9335` ("repo-only curation —
> root clutter, dead docs") along with the template-default `support/documents/README.md`.
> The pointer went stale on that date; it did not point at nothing all along. The legacy
> definition now lives in git history only — retrieve it with
> `git show e5d9335~1:.claude/support/documents/complete-task-legacy.md`, or find the
> deletion with `git log --diff-filter=D --name-only -- '*complete-task*'`.
