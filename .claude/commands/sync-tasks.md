# Sync Tasks Command

Execute `/sync-tasks` to update all task progress, validate structure, and update MISSION_CONTROL.md.

## Process

1. **Scan Tasks**: Read all `/.claude/tasks/task-*.json` files
2. **Validate Each Task**:
   - JSON schema correctness
   - Status transition validity
   - Dependency graph (no cycles)
   - Subtask ID consistency
3. **Calculate Progress**:
   - For broken-down tasks: Count completed subtasks, compute effort-weighted progress
   - Check for parent task auto-completion (all subtasks finished)
4. **Update Dependencies**:
   - Mark tasks as unblocked if dependencies now finished
   - Detect newly blocked tasks
5. **Update MISSION_CONTROL.md**:
   - Update progress bars and percentages
   - Update task status lists
   - Keep it clean and concise
6. **Generate Sync Report** (displayed in output):
   - Tasks completed since last sync
   - Tasks in progress
   - Tasks ready to start
   - Blocked tasks

## Output Example

```markdown
# Task Sync Report

## Validation Results
All 18 tasks validated successfully
No circular dependencies detected

## Progress Summary
**Completed:** 8 tasks (44%)
**In Progress:** 2 tasks (11%)
**Pending:** 8 tasks (44%)

## Currently In Progress
- Task 001: Data Gaps Visibility (Erik: build page)
- Task 018: Quality Observability (Erik: test in Fabric)

## Ready to Start (No Blockers)
- Task 005: Automate External Data (P2)
- Task 006: Incremental Load (P2) - Needs breakdown
- Task 017: Sample Data (P2) - Depends on 018

## Updates Applied
MISSION_CONTROL.md updated
Progress percentages recalculated

**Next Action:** Check MISSION_CONTROL.md for current action items
```

## Automation

This command can be run:
- **Manually**: User runs `/sync-tasks` anytime
- **At session end**: Update MISSION_CONTROL.md before ending work
