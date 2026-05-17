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

## Audit Tasks

When a task description says "verify whether downstream task X is needed" or similar (pre-flight audits, phase-restoration audits, scope-staleness checks), the implementer must compare target IDs **literally** — not by count, semantic name, or shape similarity.

Required behavior for any audit task with a downstream-needed question:

1. Read task X's body to extract the literal target IDs / values that X is supposed to produce or modify
2. Compare against current state **by ID**, not by count or semantic name match
3. Report `stale` / `no-op` only when the literal IDs match exactly
4. Report `scope_clarification_needed` when there's a semantic match without literal-ID match (e.g., "X adds field A but the registry already has field B with similar meaning") — do NOT report `stale`

This rule exists because semantic name-matching is a recurring source of false-positive "stale" findings. Observed in a styler Phase 20 audit that reported "T429 will be a verify-only no-op" based on a name-shape match; T429's actual 7 target IDs were entirely distinct from the 10 already present, and the task was real work.

## References

- Difficulty scale, status values: `.claude/support/reference/shared-definitions.md`
- Task JSON fields: `.claude/support/reference/task-schema.md`
