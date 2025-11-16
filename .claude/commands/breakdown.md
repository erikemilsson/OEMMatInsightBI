# Breakdown Task Command

Execute `/breakdown task-XXX` to decompose a complex task into manageable subtasks.

## Process

1. **Load Task**: Read task JSON from `/.claude/tasks/task-XXX.json`
2. **Validate**: Check if task can be broken down (not already broken down, preferably difficulty ≥7)
3. **Analyze Scope**: Review task description, acceptance criteria, and estimated effort
4. **Propose Subtasks**: Suggest 5-10 logical subtasks with:
   - Clear titles
   - Estimated effort (0.5-2 days each)
   - Acceptance criteria
   - Dependencies (if any)
5. **Confirm with User**: Present proposed breakdown, allow modifications
6. **Update Task JSON**: Add subtasks array, change status to "Broken Down"
7. **Save & Report**: Save updated JSON, display success summary

## Guidelines

- **Subtask Size**: 0.5-2 days each (not too small, not too large)
- **Independence**: Each subtask should be completable independently
- **Logical Grouping**: Group by feature, layer, or phase
- **Total Effort**: Sum of subtask efforts should match parent estimate

## Example

User: `/breakdown task-003`

Output:
```markdown
## Breaking Down Task 003: Redesign Power BI Report

**Current Status:** Pending
**Difficulty:** 8 (Must break down - complexity threshold)
**Estimated Effort:** 3-5 days

### Proposed Subtasks (7)

1. **Design Phase** (1-2 days)
   - Sketch page layouts and plan navigation
   - Identify required measures, select visual types
   - Create color palette and style guide

2. **Build Page 1: Executive Overview** (0.5 days)
   - Hero metrics, spend charts, geographic map, top suppliers

3. **Build Page 2: Sustainability Dashboard** (0.5 days)
   - EPI/WGI analysis, risk matrix

4. **Build Page 3: Supply Chain Risk** (0.5 days)
   - Concentration metrics, critical materials

5. **Build Page 4: Material Deep Dive** (0.3 days)
   - Drill-through page with material details

6. **Build Page 5: Data Quality Dashboard** (0.3 days)
   - Quality scorecard, unmapped values

7. **Polish & Performance Testing** (0.5 days)
   - Navigation, formatting, optimization

**Total Estimated Effort:** 4.1 days (within 3-5 day range)

Approve this breakdown? (y/n)
```

User: `y`

Output:
```markdown
✅ Task 003 successfully broken down into 7 subtasks
📊 Status updated: Pending → Broken Down
💾 Saved to: /.claude/tasks/task-003.json

You can now start this task with: `/complete-task task-003`
```
