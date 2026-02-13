# Task Workflow & Management Rules

**Purpose:** Defines task management workflows, commands, and best practices for the OEMMatInsightBI project.

---

## Task Tracking: MISSION_CONTROL.md

**MISSION_CONTROL.md is the single source of truth for task status.**

- All task progress tracked in `/MISSION_CONTROL.md`
- Keep it clean and concise - remove completed session details after a few days
- Update at the end of every work session
- Individual task details remain in `.claude/tasks/task-XXX.json` files

---

## Task Lifecycle States

```
                 ┌──────────┐
                 │ Pending  │
                 └────┬─────┘
                      │
                      ↓
          ┌───────────────────────┐
          │  Difficulty Check     │
          └───┬───────────────┬───┘
              │               │
       Diff<7 │               │ Diff≥7
              │               │
              ↓               ↓
      ┌──────────────┐   ┌──────────────┐
      │ In Progress  │   │ Broken Down  │
      └───────┬──────┘   └──────┬───────┘
              │                 │
              │                 │ (All subtasks done)
              │                 ↓
              │          ┌──────────────┐
              └─────────>│   Finished   │
                         └──────────────┘
```

**State Definitions:**
- **Pending:** No work started
- **Broken Down:** Task decomposed into subtasks (required if difficulty ≥7)
- **In Progress:** Active work happening
- **Blocked:** Dependencies not met or external blocker
- **Finished:** All acceptance criteria met (terminal state)

---

## Core Commands

### `/complete-task task-XXX`

**Purpose:** Start working on a task

**Preconditions:**
- Task exists and is Pending or Blocked
- Dependencies met (all dependency tasks are Finished)
- If difficulty ≥7, must be broken down first

**Process:**
1. Validates preconditions
2. If task has subtasks, starts first pending subtask
3. Updates status to In Progress
4. Displays acceptance criteria

### `/breakdown task-XXX`

**Purpose:** Decompose task into subtasks

**When Required:** Task difficulty ≥7

**Guidelines:**
- Create 5-10 subtasks
- Each subtask: 0.5-2 days effort
- Clear acceptance criteria per subtask
- Subtasks must be independently completable

### `/sync-tasks`

**Purpose:** Update task progress and validate structure

**Actions:**
1. Scans all `task-*.json` files
2. Validates JSON schema
3. Checks for auto-completion (all subtasks done → parent done)
4. Updates MISSION_CONTROL.md

---

## Task JSON Schema

```json
{
  "id": "task-XXX",
  "title": "string (required)",
  "description": "string (required)",
  "status": "Pending|In Progress|Broken Down|Blocked|Finished",
  "priority": "P1|P2|P3",
  "difficulty": 1-10,
  "estimatedEffort": "string",
  "acceptanceCriteria": ["array of strings"],
  "dependencies": ["array of task-XXX ids"],
  "subtasks": ["array (required if difficulty ≥7)"]
}
```

**Naming:** `task-XXX.json` where XXX is zero-padded 3-digit number

---

## Automation Rules

### Rule 1: Difficulty ≥7 Requires Breakdown
Tasks with difficulty 7+ cannot be started without subtasks. `/complete-task` will refuse.

### Rule 2: Parent Auto-Completion
When all subtasks finish, parent task automatically transitions to Finished.

### Rule 3: Dependency Validation
Cannot start a task if its dependencies aren't Finished.

---

## Workflow Patterns

### Simple Task (Difficulty 1-4)
```
/complete-task task-010 → Execute directly → Mark Finished
```

### Moderate Task (Difficulty 5-6)
```
/complete-task task-001 → Create checklist → Work through → Mark Finished
```

### Complex Task (Difficulty 7-10)
```
/breakdown task-003 → Creates subtasks → /complete-task task-003 →
Work through subtasks sequentially → Auto-completes when all done
```

---

## Best Practices

### DO:
- Use `/complete-task` at the start of every task
- Break down tasks ≥7 before starting
- Run `/sync-tasks` after completing work
- Update MISSION_CONTROL.md at session end
- Keep MISSION_CONTROL.md clean (archive old session details)
- Complete subtasks fully before moving to next

### DON'T:
- Manually edit task JSON (use commands)
- Skip breakdown for difficulty ≥7
- Create circular dependencies
- Reopen finished tasks (create new tasks instead)
- Create subtasks <0.5 days or >2 days

---

## Error Handling

### Missing Breakdown
```
⚠️  Cannot start task-003 (Difficulty: 8)
Action: Run `/breakdown task-003` first
```

### Blocked by Dependency
```
⚠️  Task task-003 blocked by task-002 (In Progress)
Action: Complete task-002 first
```

### Invalid Transition
```
❌ Cannot change task-009 from Finished to In Progress
Action: Create a new task for additional work
```

---

*Consolidated from workflow-patterns.md and task-management-rules.md*
