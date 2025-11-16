# Workflow Patterns for Task Management

**Purpose:** This document defines common workflow patterns and best practices for task execution in the OEMMatInsightBI project.

---

## Core Workflows

### 1. Starting a New Task: `/complete-task`

**When to use:** Beginning work on any task

**Process:**
```
1. Run: /complete-task task-XXX
   ↓
2. System validates:
   - Task exists
   - No blocking dependencies
   - If difficulty ≥7, task is broken down
   ↓
3. System marks task as "In Progress"
   ↓
4. Work on task systematically
   ↓
5. System marks task as "Finished" when complete
```

**Example:**
```bash
# Start working on DAX Measures task
/complete-task task-002

# System response:
# ✅ Task 002: Redesign Semantic Model & DAX Measures
# Status: Broken Down (7 subtasks)
# Starting subtask 1: Setup - Create _Measures table
#
# Acceptance criteria:
# - Create _Measures table in semantic model
# - Create display folders: Procurement, Time Intelligence, etc.
#
# Begin working? (y/n)
```

---

### 2. Breaking Down Complex Tasks: `/breakdown`

**When to use:**
- Task has difficulty ≥7 (automatic)
- Task is well-defined but needs decomposition
- During planning phase

**Process:**
```
1. Run: /breakdown task-XXX
   ↓
2. System checks difficulty score
   - If ≥7: MUST break down
   - If <7: Optional breakdown
   ↓
3. Identify logical subtasks (5-10 recommended)
   ↓
4. For each subtask:
   - Clear title
   - Estimated effort
   - Acceptance criteria
   - Dependencies
   ↓
5. System creates subtask structure
   ↓
6. Update task status to "Broken Down"
```

**Example:**
```bash
# Break down Performance Optimization task
/breakdown task-012

# System response:
# Task 012: Optimize Pipeline Performance (Difficulty: 7)
# ⚠️  Breakdown required (difficulty ≥7)
#
# Suggested subtasks:
# 1. Baseline measurement (0.5d)
# 2. Implement partitioning strategy (1d)
# 3. Enable V-Order and optimize transformations (1d)
# 4. Create warehouse indexes (0.5d)
# 5. Performance testing and validation (1d)
#
# Total estimated effort: 4 days
# Create these subtasks? (y/n)
```

---

###  3. Syncing Task Progress: `/sync-tasks`

**When to use:**
- After completing subtasks
- Before starting new tasks (to check dependencies)
- Daily/weekly progress reviews
- Before creating status reports

**Process:**
```
1. Run: /sync-tasks
   ↓
2. System scans all task JSON files
   ↓
3. For each task:
   - Check subtask completion
   - Update parent task progress
   - Validate dependencies
   - Detect status inconsistencies
   ↓
4. Generate progress report:
   - Tasks completed since last sync
   - Tasks in progress
   - Tasks blocked by dependencies
   - Next recommended tasks
   ↓
5. Update task-overview.md
```

**Example Output:**
```markdown
# Task Sync Report (2025-11-16)

## Completed Since Last Sync
✅ Task 002 - Subtask 1: Setup (0.5 days)
✅ Task 002 - Subtask 2: Core Procurement Measures (1 day)

## In Progress
🚧 Task 002 - Subtask 3: Time Intelligence Measures (30% complete)

## Tasks Ready to Start
- Task 001: Enhance DQ Visibility (no blockers)
- Task 004: Design & Implement RLS (no blockers)

## Blocked Tasks
⚠️  Task 003: Power BI Report
   - Waiting on: Task 002 completion

## Overall Progress
- Completed: 1.5 / 12 tasks (12.5%)
- P1 tasks: 0 / 4 complete
- P2 tasks: 1 / 5 complete
- P3 tasks: 0 / 3 complete
```

---

## Task Lifecycle States

### State Diagram

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

### State Definitions

**Pending**
- Initial state for all tasks
- No work has started
- Can transition to: In Progress, Broken Down, Blocked

**Broken Down**
- Task has been decomposed into subtasks
- Parent task progress shown as "X/Y subtasks done"
- Can transition to: Finished (when all subtasks complete)

**In Progress**
- Active work is happening
- For simple tasks (difficulty <7)
- Can transition to: Finished, Blocked

**Blocked**
- Dependencies not met
- External blocker (e.g., awaiting Fabric workspace access)
- Can transition to: In Progress (when blocker removed)

**Finished**
- All acceptance criteria met
- Work is complete and validated
- Terminal state (no further transitions)

---

## Workflow Patterns by Task Type

### Pattern A: Simple Task (Difficulty 1-4)

**Example:** Task 010 - Configure Pipeline Scheduling (Difficulty: 3)

**Workflow:**
```
1. /complete-task task-010
   ↓
2. Execute directly (no breakdown needed)
   ↓
3. Complete work in single session
   ↓
4. Mark as Finished
```

**Timeline:** 0.5-1 day

---

### Pattern B: Moderate Task (Difficulty 5-6)

**Example:** Task 001 - Enhance DQ Visibility (Difficulty: 6)

**Workflow:**
```
1. /complete-task task-001
   ↓
2. Optional: Create checklist (not full subtasks)
   - [ ] Create DQ notebook
   - [ ] Query audit tables
   - [ ] Generate summary statistics
   - [ ] Create Power BI page
   - [ ] Update documentation
   ↓
3. Execute systematically through checklist
   ↓
4. Validate acceptance criteria
   ↓
5. Mark as Finished
```

**Timeline:** 2-3 days

---

### Pattern C: Complex Task (Difficulty 7-10) - **REQUIRES BREAKDOWN**

**Example:** Task 002 - DAX Measures (Difficulty: 7)

**Workflow:**
```
1. Task already broken down (7 subtasks)
   ↓
2. /complete-task task-002
   ↓
3. System starts Subtask 1: Setup
   ↓
4. Complete Subtask 1
   ↓
5. System auto-advances to Subtask 2
   ↓
6. Complete Subtasks 2-7 sequentially
   ↓
7. After final subtask: System marks parent Task 002 as Finished
   ↓
8. /sync-tasks to update progress
```

**Timeline:** 5 days (with clear milestones at each subtask)

---

## Dependency Management Patterns

### Pattern 1: Sequential Dependencies

**Example:** Task 003 depends on Task 002

**Workflow:**
```
Task 002 (DAX Measures)
   ↓ completes
   ↓
Task 003 (Power BI Report) can start
```

**Handling:**
- Task 003 remains "Pending" until Task 002 is "Finished"
- `/sync-tasks` shows Task 003 as "Blocked by: Task 002"
- Once Task 002 completes, Task 003 appears in "Ready to Start"

---

### Pattern 2: Parallel Independent Tasks

**Example:** Tasks 006, 007, 011 (all P2/P3, no dependencies)

**Workflow:**
```
Task 006 (Incremental Load)  ┐
                              ├─ Work in parallel
Task 007 (Data Quality)       │
                              ├─ All independent
Task 011 (Error Handling)     ┘
```

**Handling:**
- Can be worked on simultaneously
- Each has own progress tracking
- `/sync-tasks` shows all in "Ready to Start"

---

### Pattern 3: Partial Dependencies

**Example:** Task 001 provides content for Task 003 (but not blocking)

**Workflow:**
```
Task 003 (Power BI Report)
   ├─ Page 1-4: Can start immediately (needs Task 002)
   └─ Page 5 (DQ Dashboard): Prefers Task 001 complete
```

**Handling:**
- Task 003 can start without Task 001
- Task 001 marked as "recommended" not "required"
- If Task 001 not done, Page 5 uses placeholder data

---

## Progress Tracking Patterns

### Pattern 1: Subtask Completion Cascading

**Scenario:** Task 002 has 7 subtasks

**Progress Display:**
```
Task 002: Broken Down (3/7 done) - 43% complete
  ✅ Subtask 1: Setup (Finished)
  ✅ Subtask 2: Core Procurement (Finished)
  ✅ Subtask 3: Time Intelligence (Finished)
  🚧 Subtask 4: Sustainability (In Progress)
  ⏳ Subtask 5: Risk (Pending)
  ⏳ Subtask 6: Advanced (Pending)
  ⏳ Subtask 7: Documentation & Testing (Pending)
```

**Automatic Actions:**
- When Subtask 7 completes → Task 002 automatically transitions to "Finished"
- `/sync-tasks` updates task-overview.md progress percentages

---

### Pattern 2: Effort-Based Progress

**Scenario:** Task 006 has 5 subtasks with varying effort

**Effort Weighting:**
```
Total: 3.5 days
- Subtask 1: 0.5 days (14% of total)
- Subtask 2: 1.0 days (29%)
- Subtask 3: 1.0 days (29%)
- Subtask 4: 0.5 days (14%)
- Subtask 5: 0.5 days (14%)
```

**Progress Calculation:**
```
Completed: Subtasks 1, 2
Progress: 14% + 29% = 43% complete (1.5 days done)
```

---

## Error Handling Patterns

### Pattern 1: Task Blocked Mid-Execution

**Scenario:** Start Task 002, discover semantic model access needed

**Workflow:**
```
1. Task 002: In Progress → Subtask 4
   ↓
2. Discover blocker: "Need Power BI Desktop access"
   ↓
3. Update task status:
   - Subtask 4: Blocked
   - Add blocker note to task JSON
   ↓
4. Document blocker in task notes:
   "Blocked waiting on Fabric workspace access"
   ↓
5. /sync-tasks shows Task 002 as "Blocked (3/7 done)"
   ↓
6. When blocker resolved:
   - Update subtask status: Blocked → In Progress
   - Resume work
```

---

### Pattern 2: Discovering Task Needs Breakdown

**Scenario:** Start Task 001, realize it's more complex than expected

**Workflow:**
```
1. Task 001: In Progress (Difficulty 6, thought it was simple)
   ↓
2. After 1 day, realize scope is larger
   ↓
3. Stop work, reassess difficulty
   ↓
4. Update difficulty: 6 → 7 (now requires breakdown)
   ↓
5. /breakdown task-001
   ↓
6. Create 5 subtasks
   ↓
7. Resume work with subtask structure
```

---

## Daily/Weekly Workflow Routines

### Daily Workflow (When Actively Working)

**Morning (5 minutes):**
```bash
# 1. Sync tasks to get current state
/sync-tasks

# 2. Review what's in progress
# Check: What did I work on yesterday?
# Check: Any blockers appeared overnight?

# 3. Plan today's focus
# Pick 1-2 subtasks to complete today
```

**End of Day (5 minutes):**
```bash
# 1. Update progress on current subtask
# (done via commit messages or task notes)

# 2. Sync tasks to save progress
/sync-tasks

# 3. Prepare tomorrow's plan
# Identify next subtask to start
```

---

### Weekly Workflow (Progress Review)

**Weekly Review (15-30 minutes):**
```bash
# 1. Run comprehensive sync
/sync-tasks

# 2. Review progress
- Tasks completed this week
- Tasks started but not finished
- Blockers identified

# 3. Update priorities if needed
- Re-evaluate P1/P2/P3 based on progress
- Adjust effort estimates if tasks taking longer

# 4. Plan next week
- Select 2-3 tasks to focus on
- Identify dependencies to unblock
```

**Weekly Report Format:**
```markdown
# Week of 2025-11-11

## Completed
✅ Task 009: Document DAX Measures
✅ Task 002 - Subtasks 1-3 (Setup, Core, Time Intelligence)

## In Progress
🚧 Task 002 - Subtask 4: Sustainability Measures (50%)
🚧 Task 008: Unit Tests - Framework complete

## Planned for Next Week
📋 Task 002 - Complete remaining subtasks (4-7)
📋 Task 001: Start DQ Visibility work

## Blockers
⚠️  Tasks 002, 003, 004 waiting on Fabric workspace access
   - Workaround: Continue with design/documentation tasks
```

---

## Best Practices

### ✅ DO:
- **Use `/complete-task`** at the start of every task (enforces discipline)
- **Break down tasks ≥7** before starting (mandatory rule)
- **Run `/sync-tasks` daily** during active work (keeps progress current)
- **Update task notes** with blockers, decisions, and learnings
- **Complete subtasks fully** before moving to next (avoid context switching)
- **Celebrate milestones** (completing subtasks, finishing complex tasks)

### ❌ DON'T:
- **Don't skip breakdown** for difficulty ≥7 tasks (high error risk)
- **Don't work on multiple complex tasks** simultaneously (cognitive overload)
- **Don't forget dependencies** (check task JSON before starting)
- **Don't update task JSON manually** (use commands to maintain consistency)
- **Don't ignore blockers** (document them immediately)

---

## Quick Reference: Command Summary

| Command | Purpose | When to Use |
|---------|---------|-------------|
| `/complete-task task-XXX` | Start working on a task | Beginning any task |
| `/breakdown task-XXX` | Decompose task into subtasks | Task has difficulty ≥7 |
| `/sync-tasks` | Update all task progress | Daily/weekly, before status reports |

---

*These workflow patterns are based on the task management framework from the claude_code_environment reference repository and adapted for the OEMMatInsightBI project.*
