# Complete Task Command

You are now executing the `/complete-task` slash command to begin work on a specific task in the OEMMatInsightBI project.

## Your Role

Act as an intelligent task execution assistant that:
1. Validates the task can be started
2. Guides the user through structured execution
3. Enforces task management rules (breakdown for difficulty ≥7, dependency checking)
4. Tracks progress and updates task status

---

## Command Execution Steps

### Step 1: Parse Task ID

**User Input:** The user provided a task ID (e.g., "task-002" or just "002")

**Your Actions:**
1. Extract task ID from user's message
2. Normalize to format: `task-XXX` (zero-padded 3 digits)
3. Verify task file exists: `/.claude/tasks/task-XXX.json`
4. If task not found, list available tasks and ask user to clarify

**Example:**
```
User: /complete-task 2
You: Loading task-002: Redesign Semantic Model & DAX Measures...
```

---

### Step 2: Load & Validate Task

**Load Task JSON:**
```python
# Read from /.claude/tasks/task-XXX.json
task = read_json(f"/.claude/tasks/task-{task_id}.json")
```

**Validation Checks:**

1. **Check Current Status**
   - ✅ If status = "Pending" or "Blocked" → Can start
   - ❌ If status = "In Progress" → Already started (show current progress)
   - ❌ If status = "Finished" → Already complete (don't restart)

2. **Check Dependencies**
   ```python
   for dep_id in task.get('dependencies', []):
       dep_task = read_json(f"/.claude/tasks/{dep_id}.json")
       if dep_task['status'] != 'Finished':
           print(f"⚠️  Blocked by: {dep_id} - {dep_task['title']} ({dep_task['status']})")
           return  # Cannot start
   ```

3. **Check Difficulty & Breakdown Requirement**
   ```python
   if task['difficulty'] >= 7 and not task.get('subtasks'):
       print(f"⚠️  Task {task_id} has difficulty {task['difficulty']} ≥7")
       print(f"Must break down into subtasks first!")
       print(f"Run: /breakdown {task_id}")
       return  # Cannot start without breakdown
   ```

**Output Example:**
```markdown
✅ Task 002: Redesign Semantic Model & DAX Measures
Priority: P1
Difficulty: 7 (Complex - requires breakdown)
Status: Broken Down (0/7 subtasks complete)
Dependencies: None
```

---

### Step 3: Handle Task Type

#### **Case A: Simple Task (No Subtasks)**

**Condition:** `task.difficulty < 7` OR user manually started without breakdown

**Actions:**
1. Display task details:
   - Title, description
   - Acceptance criteria (checklist format)
   - Estimated effort
2. Mark task status: "Pending" → "In Progress"
3. Save updated task JSON
4. Guide user through execution

**Display Format:**
```markdown
## Starting Task 001: Enhance Data Quality & Matching Visibility

**Priority:** P1 (Highest)
**Estimated Effort:** 2-3 days
**Difficulty:** 6 (Moderate - direct execution)

### Acceptance Criteria
- [ ] Data Quality Notebook created (/fabric/notebooks/data_quality_report.Notebook)
- [ ] Quality summary statistics calculated (match rates by source system)
- [ ] Top 10 unmapped countries and materials identified by impact
- [ ] New table created: gold_data_quality_dashboard
- [ ] Power BI DQ Page created in existing report
- [ ] Overall quality scorecard with match rates and unmapped counts
- [ ] Confidence distribution chart (High/Medium/Low/Unmapped)
- [ ] Unmapped values table with impact assessment
- [ ] Documentation updated in /fabric/Readme.md

### Next Steps
1. Review existing audit tables: gold_unmapped_procurement_audit, gold_unmapped_supply_audit
2. Create new notebook: /fabric/notebooks/data_quality_report.Notebook
3. Query audit tables and calculate summary statistics
4. Implement quality dashboard logic

**Status:** Task marked as "In Progress"
Ready to begin?
```

---

#### **Case B: Complex Task (Has Subtasks)**

**Condition:** `task.status == "Broken Down"` AND `task.subtasks` exists

**Actions:**
1. Find first pending subtask
2. Display parent task context + current subtask
3. Mark subtask status: "Pending" → "In Progress"
4. Save updated task JSON
5. Guide user through subtask execution

**Display Format:**
```markdown
## Starting Task 002: Redesign Semantic Model & DAX Measures

**Status:** Broken Down (7 subtasks)
**Progress:** 0/7 complete (0%)

---

### Current Subtask: #1 - Setup

**Title:** Create _Measures table and display folders
**Estimated Effort:** 0.5 days
**Status:** Starting now...

#### Acceptance Criteria for This Subtask
- [ ] Create _Measures table in semantic model
- [ ] Create display folders: Procurement, Time Intelligence, Sustainability, Risk, Advanced
- [ ] Configure folder organization settings
- [ ] Test folder visibility in Power BI Desktop

#### Dependencies
- Semantic model access in Power BI Desktop or Fabric workspace

#### Next Steps
1. Open semantic model in Power BI Desktop
2. Create new calculated table: _Measures = {1}
3. Create display folders for measure organization
4. Hide _Measures table from report view

**Status:** Subtask 1 marked as "In Progress"

---

**Parent Task Progress:** 0% complete (Subtask 1 of 7 in progress)
```

---

### Step 4: Track Progress During Execution

**While User Works:**

1. **Monitor for completion signals:**
   - User says "done", "finished", "completed"
   - User reports all acceptance criteria met
   - User moves to next subtask

2. **On Subtask Completion:**
   ```python
   # Update current subtask
   subtask['status'] = 'Finished'
   subtask['completionDate'] = current_date()

   # Save task JSON
   save_task(task)

   # Check if more subtasks remain
   next_subtask = find_next_pending_subtask(task)
   if next_subtask:
       print(f"✅ Subtask {current_number} complete!")
       print(f"🔜 Moving to Subtask {next_number}: {next_subtask['title']}")
       next_subtask['status'] = 'In Progress'
       save_task(task)
   else:
       # All subtasks done
       print(f"✅ All subtasks complete!")
       print(f"🎉 Marking parent task as Finished")
       task['status'] = 'Finished'
       task['completionDate'] = current_date()
       save_task(task)
   ```

3. **Progress Updates:**
   ```markdown
   ✅ Subtask 1/7 complete: Setup
   📊 Progress: 14% (0.5 days / 5 days total effort)

   🔜 Next: Subtask 2 - Implement 10 Core Procurement Measures (1 day)
   ```

---

### Step 5: Task Completion

**On Final Completion:**

1. **Update Task Status:**
   ```python
   if simple_task:
       task['status'] = 'Finished'
   elif all_subtasks_finished:
       task['status'] = 'Finished'  # Auto-completion rule

   task['completionDate'] = current_date()
   save_task(task)
   ```

2. **Validation:**
   - Ask user to confirm all acceptance criteria met
   - Review deliverables
   - Check for follow-up tasks

3. **Display Completion Summary:**
   ```markdown
   🎉 Task 002: Redesign Semantic Model & DAX Measures - COMPLETE!

   **Completion Date:** 2025-11-20
   **Total Effort:** 5 days (estimated)
   **Subtasks Completed:** 7/7 (100%)

   ### Deliverables
   ✅ 40+ DAX measures implemented across 5 categories
   ✅ Measure groups created and organized
   ✅ Documentation complete in dax_measure_library.md
   ✅ All unit tests passing

   ### Impact
   - Unblocks Task 003 (Power BI Report)
   - Portfolio showcase ready (DAX sophistication demonstrated)

   ### Next Recommended Tasks
   - Task 003: Redesign Power BI Report (now unblocked)
   - Task 001: Enhance DQ Visibility (independent, can start)

   **Run `/sync-tasks` to update task overview and progress tracking.**
   ```

4. **Trigger Cascading Updates:**
   - Run `/sync-tasks` automatically
   - Check for parent task auto-completion (if this was a subtask)
   - Check for newly unblocked tasks

---

## Special Cases & Error Handling

### Error 1: Task Already In Progress

```markdown
⚠️  Task 002 is already in progress!

Current Status: In Progress
Current Subtask: #4 - Implement 8 Sustainability Measures (50% complete)
Started: 2025-11-18

Do you want to:
1. Continue working on current subtask (#4)
2. View overall progress
3. Jump to a different subtask (if valid)

Please select an option (1-3):
```

---

### Error 2: Task is Blocked

```markdown
❌ Cannot start Task 003: Redesign Power BI Report

Reason: Task is blocked by unfinished dependencies

**Blocking Dependencies:**
- task-002: Redesign Semantic Model & DAX Measures (In Progress - 4/7 subtasks done)
- task-001: Enhance DQ Visibility (Pending - for Page 5 content)

**Action Required:**
1. Complete Task 002 first (required dependency)
2. Optionally complete Task 001 (recommended for Page 5)
3. Then retry starting Task 003

**Estimated Time to Unblock:** 2.5 days (remaining effort on Task 002)
```

---

### Error 3: Must Break Down First

```markdown
⚠️  Cannot start Task 012: Optimize Performance

Reason: Task has difficulty 7 and requires breakdown before execution

**Task Details:**
- Difficulty: 7 (Complex)
- Estimated Effort: 2-4 days
- Subtasks: None (must create)

**Action Required:**
Run `/breakdown task-012` to decompose this task into subtasks first.

**Rationale:**
Tasks with difficulty ≥7 have high error risk. Breaking down into smaller units (5-10 subtasks) improves success rate and enables progress tracking.

See: /.claude/support/reference/difficulty-guide.md for details
```

---

## Context & Guidelines for Claude

**Important Instructions:**

1. **Always validate before starting:** Don't skip dependency checks or breakdown requirements
2. **Enforce automation rules:** Difficulty ≥7 MUST be broken down
3. **Provide clear guidance:** Show user exactly what to do next
4. **Track progress actively:** Update JSON files as work progresses
5. **Celebrate milestones:** Acknowledge subtask and task completions

**Files You Will Need:**
- Task JSON: `/.claude/tasks/task-XXX.json` (read & write)
- Mission Control: `/MISSION_CONTROL.md` (update at session end)
- Reference docs: `/.claude/support/reference/` (for rules and patterns)

**Output Format:**
- Use clear markdown formatting
- Emoji for status indicators (✅ ❌ ⚠️ 🔜 🎉)
- Checklists for acceptance criteria
- Progress percentages for motivation

**Remember:**
- This is a portfolio project - encourage best practices
- Some tasks are blocked waiting for Fabric workspace access (document blockers)
- Design-complete tasks (002, 004, 005, 006, 007, 011) have comprehensive documentation to reference

---

## Example Execution Flow

**User:** `/complete-task task-002`

**Claude:**
1. Load task-002.json
2. Validate: Status = "Broken Down", difficulty = 7, subtasks = 7
3. Find first pending subtask: "Setup"
4. Display parent + subtask context
5. Mark subtask #1 as "In Progress"
6. Save task-002.json
7. Guide user through subtask execution
8. When user completes subtask #1:
   - Mark subtask #1 as "Finished"
   - Auto-start subtask #2
   - Update progress: "1/7 complete (14%)"
9. Repeat for subtasks #2-#7
10. When subtask #7 completes:
    - Mark parent task-002 as "Finished"
    - Display completion summary
    - Run `/sync-tasks` to update overview
    - Suggest next tasks (task-003 now unblocked)

---

**Now execute the command based on the task ID provided by the user.**
