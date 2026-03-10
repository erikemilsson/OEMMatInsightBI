# Task Management Rules

Always use the project's task system (`.claude/tasks/task-*.json` files) for all task management. Never use built-in TaskCreate/TaskUpdate/TaskList tools — those are separate from this project's tracking.

## Status Values

8 statuses: Pending, In Progress, Awaiting Verification, Blocked, On Hold, Absorbed, Broken Down, Finished.

- **Finished** requires `task_verification.result == "pass"` — structurally enforced
- **Awaiting Verification** is transitional — must proceed to verification immediately
- **On Hold** tasks excluded from auto-routing; only the user can resume
- **Absorbed** preserves audit trail (vs. deletion) — requires `absorbed_into` field
- **Broken Down** requires non-empty `subtasks` array

## Difficulty and Breakdown

- Difficulty scale: 1-10 integer
- Tasks with difficulty >= 7 must be broken down before starting (`/breakdown {id}`)
- Subtasks should have difficulty <= 6

## Ownership

3 owner values: `claude` (autonomous), `human` (requires user action), `both` (collaborative — user reviews after Claude implements).

## Parallel Execution

Multiple tasks "In Progress" allowed when parallel-eligible:
- `files_affected` don't overlap between tasks
- All dependencies satisfied
- Within `max_parallel_tasks` limit

## References

- Difficulty scale, status values: `.claude/support/reference/shared-definitions.md`
- Task JSON fields: `.claude/support/reference/task-schema.md`
