# Breakdown Task

Split a complex task into smaller subtasks.

## Usage
```
/breakdown {id}
```

## When to Use
- Task difficulty >= 7
- Task feels too big to complete in one session
- Multiple distinct pieces of work

## Process

1. Identify logical components (aim for 3-6 subtasks)
3. Create subtask files (inheriting spec provenance from parent):
   ```json
   {
     "id": "{parent_id}_{n}",
     "title": "Specific subtask title",
     "status": "Pending",
     "difficulty": 4,
     "parent_task": "{parent_id}",
     "spec_fingerprint": "{copy from parent}",
     "spec_version": "{copy from parent}",
     "spec_section": "{copy from parent}",
     "section_fingerprint": "{copy from parent}",
     "section_snapshot_ref": "{copy from parent}"
   }
   ```

   **Important:** Copy all spec provenance fields from the parent task. This ensures subtasks are tracked for spec drift detection.
4. Update parent task:
   ```json
   {
     "status": "Broken Down",
     "subtasks": ["1_1", "1_2", "1_3"],
     "notes": "Broken down into 3 subtasks"
   }
   ```
5. **Regenerate dashboard** - Follow `.claude/support/reference/dashboard-regeneration.md`
   - This ensures metadata block, footer, user section backup, and section toggles are handled consistently

## Examples

**Software — Before:** Task 5 "Build auth system" (difficulty 8)

**After:**
- Task 5: status = "Broken Down", subtasks = ["5_1", "5_2", "5_3"]
- Task 5_1: "Setup OAuth providers" (difficulty 5)
- Task 5_2: "Create login/logout flows" (difficulty 4)
- Task 5_3: "Add session management" (difficulty 5)

**Project management — Before:** Task 3 "Complete bathroom renovation procurement" (difficulty 8)

**After:**
- Task 3: status = "Broken Down", subtasks = ["3_1", "3_2", "3_3", "3_4"]
- Task 3_1: "Research and shortlist tile vendors" (difficulty 4, owner: both)
- Task 3_2: "Get plumber quotes from 3+ contractors" (difficulty 3, owner: human)
- Task 3_3: "Compare countertop materials and pricing" (difficulty 4, owner: claude)
- Task 3_4: "Produce final procurement recommendation" (difficulty 5, dependencies: [3_1, 3_2, 3_3])

## Creating Parallel-Friendly Subtasks

Maximize parallelism by minimizing file overlaps and setting `files_affected` explicitly:
- Use `N_Ma` convention (e.g., `5_1a`, `5_1b`) to signal parallel intent
- Mark research tasks `parallel_safe: true` if no file side effects

**Example — Parallel breakdown with file assignments:**

```
Task 5: "Build auth system" (difficulty 8) → Broken Down

  Task 5_1a: "Setup OAuth providers"
    files_affected: ["src/auth/oauth.ts", "src/config/oauth.json"]
    difficulty: 5

  Task 5_1b: "Create session management"
    files_affected: ["src/auth/session.ts", "src/db/sessions.sql"]
    difficulty: 5

  Task 5_1c: "Research auth best practices"
    files_affected: []
    parallel_safe: true
    difficulty: 3

  Task 5_2: "Create login/logout flows" (depends on 5_1a, 5_1b)
    files_affected: ["src/routes/auth.ts", "src/views/login.html"]
    difficulty: 4
```

In this example, tasks 5_1a, 5_1b, and 5_1c can all run in parallel (no file overlaps, 5_1c is `parallel_safe`). Task 5_2 runs after them (has dependencies).

## Rules
- Keep subtask difficulty <= 6
- Subtasks should be independently completable
- Parent auto-completes when all non-Absorbed subtasks finish
