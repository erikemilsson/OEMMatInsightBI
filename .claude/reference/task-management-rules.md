# Task Management Rules & Automation

**Purpose:** This document defines the automated rules, policies, and conventions that govern task management in the OEMMatInsightBI project.

---

## Core Automation Rules

### Rule 1: Automatic Task Breakdown (Difficulty ≥7)

**Trigger:** Task has difficulty score ≥7

**Automatic Actions:**
1. Task MUST be broken down into subtasks before work begins
2. `/complete-task` command will refuse to start task without breakdown
3. Parent task status automatically set to "Broken Down"

**Implementation:**
```python
# In /complete-task command
if task['difficulty'] >= 7 and not task.get('subtasks'):
    print(f"⚠️  Task {task_id} has difficulty {task['difficulty']} and requires breakdown first.")
    print(f"Run: /breakdown {task_id}")
    return  # Prevent starting task
```

**Example:**
```bash
/complete-task task-003  # Power BI Report (Difficulty: 8)

# System response:
# ⚠️  Task task-003 has difficulty 8 and requires breakdown first.
# Run: /breakdown task-003
#
# This task must be decomposed into subtasks before work can begin.
```

**Rationale:** Tasks ≥7 have high error risk. Breaking down into smaller units reduces cognitive load and improves success rate.

---

### Rule 2: Parent Task Auto-Completion

**Trigger:** All subtasks transition to "Finished"

**Automatic Actions:**
1. Parent task status automatically changes from "Broken Down" to "Finished"
2. Parent task completion date set to current date
3. Progress updated to "100% (X/X subtasks done)"
4. Task-overview.md updated via `/sync-tasks`

**Implementation:**
```python
# In /sync-tasks command
def check_parent_task_completion(task):
    if task['status'] == 'Broken Down':
        subtasks = task.get('subtasks', [])
        if all(st['status'] == 'Finished' for st in subtasks):
            task['status'] = 'Finished'
            task['completionDate'] = datetime.now().isoformat()
            save_task(task)
```

**Example:**
```markdown
# Before (6/7 subtasks done)
Task 002: Broken Down (6/7 done)

# After completing Subtask 7
Task 002: Finished ✅ (7/7 done)
Completion Date: 2025-11-20
```

**Rationale:** Eliminates manual tracking overhead. Parent task completion is deterministic based on subtask status.

---

### Rule 3: Dependency Validation

**Trigger:** Attempting to start a task with dependencies

**Automatic Actions:**
1. `/complete-task` checks all dependencies in `task.dependencies[]`
2. If any dependency task is not "Finished", task is marked as "Blocked"
3. Error message lists blocking dependencies
4. Task cannot start until blockers removed

**Implementation:**
```python
# In /complete-task command
def check_dependencies(task):
    for dep_id in task.get('dependencies', []):
        dep_task = load_task(dep_id)
        if dep_task['status'] != 'Finished':
            print(f"⚠️  Task {task['id']} is blocked by:")
            print(f"    - {dep_task['id']}: {dep_task['title']} ({dep_task['status']})")
            return False
    return True  # All dependencies met
```

**Example:**
```bash
/complete-task task-003  # Power BI Report

# System response:
# ⚠️  Task task-003 is blocked by:
#     - task-002: Redesign Semantic Model & DAX Measures (In Progress)
#
# Complete task-002 first, then retry starting task-003.
```

**Rationale:** Prevents starting tasks prematurely. Ensures correct execution order for dependent work.

---

### Rule 4: Progress Cascading

**Trigger:** Subtask status changes

**Automatic Actions:**
1. Parent task progress percentage recalculated
2. Task-overview.md "Status Matrix" updated
3. Effort-weighted progress computed if subtasks have varying effort

**Implementation:**
```python
# In /sync-tasks command
def calculate_progress(task):
    if task['status'] != 'Broken Down':
        return None

    subtasks = task.get('subtasks', [])
    if not subtasks:
        return None

    # Effort-weighted progress
    total_effort = sum(parse_effort(st['estimatedEffort']) for st in subtasks)
    completed_effort = sum(
        parse_effort(st['estimatedEffort'])
        for st in subtasks
        if st['status'] == 'Finished'
    )

    progress_pct = (completed_effort / total_effort) * 100
    return f"{len([st for st in subtasks if st['status'] == 'Finished'])}/{len(subtasks)} done ({progress_pct:.0f}%)"
```

**Example:**
```markdown
Task 006: Incremental Load (Broken Down)
Progress: 2/5 subtasks done (43%)

# Breakdown:
# - Subtask 1: 0.5 days (14%) ✅ Done
# - Subtask 2: 1.0 days (29%) ✅ Done
# - Subtask 3: 1.0 days (29%) 🚧 In Progress (50% complete)
# - Subtask 4: 0.5 days (14%) ⏳ Pending
# - Subtask 5: 0.5 days (14%) ⏳ Pending
#
# Completed effort: 1.5 days / 3.5 days = 43%
```

**Rationale:** Provides accurate progress visibility. Effort-weighting ensures fair representation (not just simple count).

---

##Naming & Organization Conventions

### Task ID Format

**Pattern:** `task-XXX` where XXX is zero-padded 3-digit number

**Examples:**
- `task-001` (Enhance DQ Visibility)
- `task-012` (Optimize Performance)

**Subtask ID Format:** `task-XXX-Y` where Y is subtask number

**Examples:**
- `task-002-1` (Setup)
- `task-002-7` (Documentation & Testing)

**Rationale:** Consistent naming enables easy sorting, referencing, and tooling.

---

### File Organization

**Directory Structure:**
```
/.claude/tasks/
├── task-001.json      # JSON task files (source of truth)
├── task-002.json
├── ...
├── task-012.json
├── task-overview.md   # Master summary (auto-generated by /sync-tasks)
├── 01_enhance_data_quality_visibility.md  # Legacy markdown (archived)
├── 02_redesign_semantic_model.md
└── ... (all legacy .md files)
```

**File Naming Rules:**
- JSON files: `task-XXX.json` (lowercase, hyphenated)
- Markdown files: `task-overview.md`, legacy files use underscore
- No spaces in filenames

**Rationale:** Clear separation between active (JSON) and archived (MD) tasks. Automated tools operate on JSON files only.

---

## Task Lifecycle Policies

### Policy 1: Status Transitions

**Valid Transitions:**

```
Pending → In Progress   (via /complete-task)
Pending → Broken Down   (via /breakdown, if difficulty ≥7)
Broken Down → Finished  (automatic, when all subtasks done)
In Progress → Finished  (manual, when work complete)
In Progress → Blocked   (manual, when blocker discovered)
Blocked → In Progress   (manual, when blocker resolved)
```

**Invalid Transitions:**
- Finished → Any other state (terminal state)
- Broken Down → In Progress (parent tasks don't work directly)

**Enforcement:**
- `/complete-task` command validates transitions
- `/sync-tasks` detects and reports invalid states

---

### Policy 2: Subtask Independence

**Rule:** Each subtask must be independently completable

**Requirements:**
- Subtask has clear acceptance criteria
- Subtask can be validated without other subtasks
- Subtask effort estimate is accurate (0.5-2 days recommended)

**Anti-Pattern (Too Dependent):**
```json
{
  "subtasks": [
    {"title": "Write DAX measures part 1"},  // ❌ Vague, not independent
    {"title": "Write DAX measures part 2"},  // ❌ Depends on part 1 definition
    {"title": "Write remaining measures"}    // ❌ Unclear scope
  ]
}
```

**Good Pattern (Independent):**
```json
{
  "subtasks": [
    {"title": "Implement 10 Core Procurement Measures", "estimatedEffort": "1 day"},  // ✅ Clear scope
    {"title": "Implement 9 Time Intelligence Measures", "estimatedEffort": "1 day"},  // ✅ Independent
    {"title": "Implement 8 Sustainability Measures", "estimatedEffort": "1 day"}      // ✅ Specific count
  ]
}
```

---

### Policy 3: Effort Estimation Rules

**Guidelines:**
- **Minimum subtask effort:** 0.5 days (4 hours)
- **Maximum subtask effort:** 2 days (16 hours)
- **Parent task effort:** Sum of subtask efforts
- **Buffer:** Add 10-20% buffer for integration/testing

**Effort Formats:**
- "0.5 days", "1 day", "2 days" (preferred)
- "4 hours", "8 hours" (acceptable)
- "2-3 days" (range, for tasks without breakdown)

**Updating Estimates:**
- If actual effort differs significantly (>50%), update estimate
- Document reason in task notes
- Use for future estimation calibration

---

## Automation Triggers

### Trigger 1: Daily Sync

**Schedule:** Run `/sync-tasks` once per day (automated via cron/scheduler)

**Actions:**
1. Scan all `task-XXX.json` files
2. Validate JSON schema
3. Compute progress percentages
4. Check for completion cascading
5. Update `task-overview.md`
6. Generate daily progress report

**Output:** Markdown report saved to `/.claude/reports/sync-YYYY-MM-DD.md`

---

### Trigger 2: Task Completion

**Event:** Task transitions to "Finished"

**Actions:**
1. Update task JSON with completion date
2. Check if parent task can auto-complete
3. Unblock any tasks dependent on this task
4. Add entry to CHANGELOG.md
5. Trigger `/sync-tasks` to update overview

---

### Trigger 3: Difficulty Threshold

**Event:** Task difficulty is set or updated

**Actions:**
1. If `difficulty >= 7` and `subtasks` is empty:
   - Set status to "Broken Down" (pending breakdown)
   - Add warning to task notes
   - Prevent `/complete-task` from starting
2. If `difficulty < 7` and `subtasks` exists:
   - Flag for review (may not need breakdown)

---

## Quality Checks & Validations

### Validation 1: Task JSON Schema

**Required Fields:**
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

**Validation Rules:**
- `id` must match filename (`task-001.json` → `"id": "task-001"`)
- `difficulty` must be integer 1-10
- `status` must be one of valid values
- `priority` must be P1, P2, or P3
- `subtasks` required if `difficulty >= 7`

**Enforcement:** `/sync-tasks` validates all task files and reports errors

---

### Validation 2: Dependency Graph

**Check:** No circular dependencies

**Example of Invalid Dependency:**
```
task-001 depends on task-002
task-002 depends on task-003
task-003 depends on task-001  ❌ Circular dependency!
```

**Detection:** `/sync-tasks` builds dependency graph and detects cycles

**Resolution:** Remove one dependency to break the cycle

---

### Validation 3: Orphaned Subtasks

**Check:** Every subtask belongs to a valid parent

**Example of Orphaned Subtask:**
```json
// In task-002.json
{
  "subtasks": [
    {"id": "task-002-1", ...},
    {"id": "task-999-1", ...}  // ❌ Orphan! Parent is task-999, not task-002
  ]
}
```

**Detection:** `/sync-tasks` validates subtask IDs match parent

**Resolution:** Fix subtask ID or move to correct parent

---

## Command Reference

### `/complete-task task-XXX`

**Purpose:** Start working on a task

**Preconditions:**
- Task exists
- Task status is "Pending" or "Blocked"
- Dependencies are met (all dependency tasks are "Finished")
- If difficulty ≥7, task must be broken down

**Actions:**
1. Validate preconditions
2. If task has subtasks, start first pending subtask
3. Update status: "Pending" → "In Progress" (or first subtask → "In Progress")
4. Save task JSON
5. Display acceptance criteria and next steps

**Post conditions:**
- Task (or first subtask) status is "In Progress"
- User is ready to begin work

---

### `/breakdown task-XXX`

**Purpose:** Decompose task into subtasks

**Preconditions:**
- Task exists
- Task does not already have subtasks
- Preferably difficulty ≥7 (mandatory) or user discretion (optional)

**Actions:**
1. Load task JSON
2. Prompt user for subtasks (title, effort, criteria)
3. Generate subtask IDs (`task-XXX-1`, `task-XXX-2`, ...)
4. Add subtasks array to task JSON
5. Update status: "Pending" → "Broken Down"
6. Save task JSON

**Postconditions:**
- Task has `subtasks` array populated
- Task status is "Broken Down"
- Task can now be started via `/complete-task`

---

### `/sync-tasks`

**Purpose:** Update all task progress and validate structure

**Preconditions:** None (can run anytime)

**Actions:**
1. Scan `/.claude/tasks/task-*.json` files
2. For each task:
   - Validate JSON schema
   - Check dependency graph
   - Calculate progress
   - Check for auto-completion
3. Update `task-overview.md`
4. Generate sync report
5. Save report to `/.claude/reports/sync-YYYY-MM-DD.md`

**Postconditions:**
- All task progress is current
- `task-overview.md` reflects latest state
- Sync report available for review

---

## Error Handling

### Error 1: Missing Breakdown for Difficulty ≥7

**Error Message:**
```
⚠️  Cannot start task-003 (Difficulty: 8)
Reason: Task must be broken down first (difficulty ≥7)
Action: Run `/breakdown task-003` to create subtasks
```

**Resolution:** Run `/breakdown` command, create subtasks, then retry `/complete-task`

---

### Error 2: Circular Dependency Detected

**Error Message:**
```
❌ Dependency cycle detected:
task-001 → task-002 → task-003 → task-001

This creates an impossible dependency chain.
Action: Remove one dependency to break the cycle.
```

**Resolution:** Edit task JSON files to remove circular reference

---

### Error 3: Invalid Task Status Transition

**Error Message:**
```
❌ Invalid status transition:
Cannot change task-009 from "Finished" to "In Progress"
Reason: Finished is a terminal state

If work is needed, create a new task.
```

**Resolution:** Create new task for additional work, don't reopen finished tasks

---

## Best Practices Summary

### ✅ DO:
1. **Always use commands** (`/complete-task`, `/breakdown`, `/sync-tasks`) instead of manual JSON edits
2. **Break down tasks ≥7** before starting (enforced by automation)
3. **Run `/sync-tasks` daily** during active development
4. **Update task notes** with blockers, decisions, context
5. **Validate acceptance criteria** before marking tasks complete
6. **Keep subtasks focused** (0.5-2 days each)
7. **Document dependencies** explicitly in task JSON

### ❌ DON'T:
1. **Don't manually edit task JSON** (use commands to maintain consistency)
2. **Don't skip breakdown** for difficulty ≥7 (automation prevents this anyway)
3. **Don't create circular dependencies** (breaks task ordering)
4. **Don't reopen finished tasks** (create new tasks instead)
5. **Don't create subtasks <0.5 days** (too granular, overhead)
6. **Don't create subtasks >2 days** (too large, break down further)

---

*These task management rules are based on the framework from the claude_code_environment reference repository and customized for the OEMMatInsightBI project.*
