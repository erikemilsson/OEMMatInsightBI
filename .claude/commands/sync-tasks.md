# Sync Tasks Command

Execute `/sync-tasks` to update all task progress, validate structure, and regenerate task-overview.md.

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
5. **Regenerate task-overview.md**:
   - Update status matrix
   - Recalculate priority breakdown
   - Update progress tracking section
6. **Generate Sync Report**:
   - Tasks completed since last sync
   - Tasks in progress
   - Tasks ready to start
   - Blocked tasks
7. **Save Report**: Write to `/.claude/reports/sync-YYYY-MM-DD.md` (if reports directory exists)

## Output Example

```markdown
# Task Sync Report (2025-11-16 14:30)

## Validation Results
✅ All 12 tasks validated successfully
✅ No circular dependencies detected
✅ No orphaned subtasks found

## Progress Summary
**Completed:** 1 task (8%)
**In Progress:** 1 task (8%)
**Broken Down:** 1 task (8%)
**Pending:** 9 tasks (75%)

## Completed Since Last Sync
✅ Task 002 - Subtask 1: Setup (completed 2025-11-16)

## Currently In Progress
🚧 Task 002: Redesign Semantic Model & DAX Measures
   - Subtask 2/7: Core Procurement Measures (In Progress)
   - Progress: 14% (0.5/5 days complete)

🚧 Task 008: Create Unit Tests
   - Framework complete, optional enhancements remain

## Ready to Start (No Blockers)
📋 Task 001: Enhance DQ Visibility (P1, Difficulty: 6)
📋 Task 004: Design & Implement RLS (P1, Difficulty: 6)
📋 Task 005: Automate External Data (P2, Difficulty: 5)
📋 Task 006: Implement Incremental Load (P2, Difficulty: 7) ⚠️ Needs breakdown
📋 Task 007: Add Data Quality Checks (P2, Difficulty: 6)
📋 Task 010: Configure Pipeline Scheduling (P3, Difficulty: 3)
📋 Task 011: Implement Error Handling (P3, Difficulty: 6)
📋 Task 012: Optimize Performance (P3, Difficulty: 7) ⚠️ Needs breakdown

## Blocked Tasks
⚠️  Task 003: Redesign Power BI Report
   - Blocked by: task-002 (In Progress - 14% complete)
   - Estimated time to unblock: 4.5 days

## Auto-Completion Checks
- Task 002: 1/7 subtasks complete (not ready for auto-completion)

## Updates Applied
✅ task-overview.md regenerated
✅ Progress percentages recalculated
✅ Dependency status updated

**Next Action:** Run `/complete-task task-002` to continue DAX measures implementation
```

## Automation

This command can be run:
- **Manually**: User runs `/sync-tasks` anytime
- **Scheduled**: Daily cron job (if configured)
- **Triggered**: After task completion (automatic)
