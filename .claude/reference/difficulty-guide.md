# Task Difficulty Scoring Guide

**Purpose:** This guide defines the 1-10 difficulty scale used for task classification in the OEMMatInsightBI project. Difficulty scores help determine whether tasks require breakdown before execution and guide effort estimation.

---

## Difficulty Scale Overview

**Range:** 1-10
**Breakdown Threshold:** ≥7 (tasks scoring 7 or higher MUST be broken down into subtasks before starting)

### Scale Philosophy
Difficulty scoring reflects the **LLM error risk potential** and **complexity** of task execution. Higher scores indicate:
- Greater chance of implementation errors
- More moving parts and dependencies
- Need for careful planning and systematic approach
- Higher cognitive load and decision points

---

## Difficulty Levels Defined

### **Level 1-2: Trivial**
**Characteristics:**
- Single, straightforward action
- Well-defined with no ambiguity
- Minimal risk of errors
- Can be completed in <2 hours
- No dependencies or complex logic

**Examples:**
- Task 009: Document DAX Measures (Difficulty: 2)
  - Simple investigation and documentation
  - No code changes required
  - Clear success criteria

**Execution:** Direct execution, no planning needed

---

### **Level 3-4: Simple**
**Characteristics:**
- 2-3 straightforward steps
- Clear process, minimal decisions
- Low error risk with well-documented procedures
- Can be completed in 0.5-1 day
- Few dependencies

**Examples:**
- Task 008: Create Unit Tests (Difficulty: 4)
  - Framework setup is straightforward
  - pytest patterns are well-established
  - Some complexity in test case design

- Task 010: Configure Pipeline Scheduling (Difficulty: 3)
  - Simple Fabric configuration
  - Well-documented process
  - Minimal risk

**Execution:** Direct execution, light planning helpful

---

### **Level 5-6: Moderate**
**Characteristics:**
- Multiple coordinated steps (4-6)
- Some decision points and trade-offs
- Moderate error risk requiring validation
- Can be completed in 1-3 days
- Several dependencies to manage

**Examples:**
- Task 001: Enhance DQ Visibility (Difficulty: 6)
  - Notebook creation + Power BI page
  - Well-defined scope but needs coordination
  - Multiple deliverables

- Task 004: Design & Implement RLS (Difficulty: 6)
  - 6 roles to implement
  - Design complete, systematic implementation
  - Testing required for each role

- Task 005: Automate External Data Ingestion (Difficulty: 5)
  - Research phase complete
  - Implementation is straightforward HTTP/API calls
  - Two data sources to handle

- Task 007: Add Data Quality Checks (Difficulty: 6)
  - 9 check functions to implement
  - Framework designed, systematic execution
  - Integration with pipeline

- Task 011: Implement Error Handling (Difficulty: 6)
  - 7 activities to configure
  - Design complete with clear strategy
  - Systematic implementation across pipeline

**Execution:** Direct execution recommended, but planning/checklist helpful for tracking

---

### **Level 7-8: Complex ⚠️ BREAKDOWN REQUIRED**
**Characteristics:**
- Many interdependent steps (7+)
- Significant decision points and architectural choices
- High error risk without careful planning
- Requires 3-7 days of focused work
- Multiple dependencies and integration points
- Benefits significantly from task decomposition

**Examples:**
- Task 002: Redesign Semantic Model & DAX Measures (Difficulty: 7)
  - 40+ DAX measures to implement
  - 5 measure groups (Procurement, Time Intelligence, Sustainability, Risk, Advanced)
  - **MUST break down** into implementation phases
  - ✅ Already broken down into 7 subtasks

- Task 003: Redesign Power BI Report (Difficulty: 8)
  - 5 report pages from scratch
  - Complex design + implementation
  - Depends on Task 002 completion
  - **MUST break down** by page
  - Subtasks planned: 7 phases (design + 5 pages + polish)

- Task 006: Implement Incremental Load (Difficulty: 7)
  - Spans bronze, silver, gold layers
  - Complex coordination and merge logic
  - **MUST break down** by layer
  - Subtasks planned: 5 phases (bronze, silver, gold, wiring, testing)

- Task 012: Optimize Performance (Difficulty: 7)
  - Multiple optimization techniques
  - Requires baseline measurement first
  - Systematic approach needed
  - **MUST break down** by technique
  - Subtasks planned: 5 phases (baseline, partitioning, V-Order, indexing, testing)

**Execution:** **AUTOMATIC BREAKDOWN REQUIRED** - Do not start without breaking into subtasks first

---

### **Level 9-10: Highly Complex ⚠️ BREAKDOWN ESSENTIAL**
**Characteristics:**
- Extremely complex with 10+ interconnected steps
- Major architectural decisions
- Very high error risk
- Requires 1-2 weeks of focused work
- Many dependencies and unknowns
- Critical path dependencies

**Examples in OEMMatInsightBI:**
- None currently (highest is Difficulty 8)

**Hypothetical Example:**
- "Migrate entire pipeline from Fabric to AWS Glue"
  - Would require complete replatforming
  - Architectural redesign
  - Data migration strategy
  - Would score Difficulty: 9-10

**Execution:** **MANDATORY BREAKDOWN** - Requires detailed project plan before starting

---

## Scoring Criteria Matrix

Use this matrix to evaluate task difficulty:

| Criterion | Weight | 1-2 (Trivial) | 3-4 (Simple) | 5-6 (Moderate) | 7-8 (Complex) | 9-10 (Highly Complex) |
|-----------|--------|---------------|--------------|----------------|---------------|-----------------------|
| **Number of steps** | 25% | 1-2 | 2-3 | 4-6 | 7-12 | 13+ |
| **Decision points** | 20% | None | 1-2 | 3-5 | 6-10 | 11+ |
| **Dependencies** | 20% | None | 1 | 2-3 | 4-6 | 7+ |
| **Error risk** | 20% | Minimal | Low | Moderate | High | Very High |
| **Time estimate** | 15% | <2 hours | 0.5-1 day | 1-3 days | 3-7 days | 1-2 weeks |

**Calculation Example (Task 003 - Power BI Report):**
- Steps: 7+ (design + 5 pages + polish) = **7 points**
- Decision points: 6+ (page layouts, visual types, interactions) = **7 points**
- Dependencies: 2 (Task 002, Task 001) = **5 points**
- Error risk: High (design complexity, visual polish) = **7 points**
- Time: 3-5 days = **7 points**

**Weighted Average:** (7×0.25) + (7×0.20) + (5×0.20) + (7×0.20) + (7×0.15) = **6.8** → **Round to 7-8**

Given the design complexity and portfolio showcase importance, assigned **Difficulty: 8**

---

## When to Break Down Tasks

### Automatic Breakdown Triggers

**Rule:** Tasks with Difficulty ≥7 **MUST** be broken down before starting.

**Rationale:**
- Reduces cognitive load by focusing on one subtask at a time
- Improves error detection (easier to validate smaller units)
- Enables better progress tracking
- Allows for parallel work opportunities
- Reduces risk of getting stuck mid-task

**How to break down:**
1. Identify natural phases or logical groupings
2. Create 5-10 subtasks (avoid over-decomposition)
3. Ensure each subtask is independently completable
4. Assign effort estimates to each subtask
5. Order subtasks by dependencies

---

## Breakdown Examples

### Good Breakdown: Task 002 (DAX Measures, Difficulty 7)

**Parent Task:** Implement 40+ DAX measures

**Subtasks (7):**
1. **Setup** (0.5d) - Create _Measures table and display folders
2. **Core Procurement** (1d) - 10 measures: Total Spend, Quantity, Count, etc.
3. **Time Intelligence** (1d) - 9 measures: YoY, MoM, YTD, etc.
4. **Sustainability** (1d) - 8 measures: EPI, WGI, weighted scores
5. **Risk** (0.5d) - 7 measures: HHI, concentration, composite risk
6. **Advanced** (0.5d) - 6 measures: Rank, volatility, what-if parameters
7. **Documentation & Testing** (0.5d) - Descriptions, unit tests, performance

**Why this is good:**
- ✅ Logical grouping by measure category
- ✅ Each subtask is independently completable
- ✅ Clear deliverables for each phase
- ✅ Effort estimates sum to total (5 days)
- ✅ Natural dependency order (setup → measures → testing)

---

### Poor Breakdown (Anti-Pattern)

**Parent Task:** Implement 40+ DAX measures

**Bad Subtasks:**
1. "Write some measures" (too vague)
2. "Test everything" (too late, should test iteratively)
3. "Fix any issues" (reactive, not proactive)

**Why this is bad:**
- ❌ No clear deliverables
- ❌ No logical grouping
- ❌ Can't track progress effectively
- ❌ Testing deferred to end (risky)

---

## Difficulty Adjustment Factors

### Factors that INCREASE difficulty (+1 to +2):
- **No design document:** Architectural decisions needed during implementation
- **External dependencies:** Waiting on third-party APIs, services, or approvals
- **New technology:** Learning curve for unfamiliar tools or frameworks
- **High portfolio visibility:** Extra polish and documentation required
- **Cross-cutting changes:** Affects multiple systems or layers

### Factors that DECREASE difficulty (-1 to -2):
- **Design phase complete:** Clear implementation roadmap already exists
- **Well-documented patterns:** Examples and best practices available
- **Isolated scope:** Changes contained to single component
- **Automated testing:** Safety net for catching errors
- **Prior experience:** Team has done similar work before

**Example:** Task 006 (Incremental Load)
- **Base difficulty:** 8 (spans multiple layers, complex merge logic)
- **Design complete:** -1 (comprehensive strategy document exists)
- **Delta Lake MERGE support:** -1 (proven technology, clear patterns)
- **Final difficulty:** 8 - 2 = **6-7** → Assigned **7** (still requires breakdown due to multi-layer span)

---

## Difficulty vs. Priority

**Important:** Difficulty and Priority are independent dimensions.

| Scenario | Difficulty | Priority | Example |
|----------|------------|----------|---------|
| Quick win | Low (1-4) | High (P1) | Task 010: Pipeline Scheduling (Diff 3, P3 actually) |
| Foundation work | High (7-10) | High (P1) | Task 002: DAX Measures (Diff 7, P1) |
| Technical debt | Moderate (5-6) | Medium (P2) | Task 007: Data Quality Checks (Diff 6, P2) |
| Infrastructure | Low-Moderate (3-6) | Low (P3) | Task 011: Error Handling (Diff 6, P3) |

**Priority Guidance:**
- **P1 (High):** Portfolio showcase, business value, foundational
- **P2 (Medium):** Technical depth, engineering best practices
- **P3 (Infrastructure):** Production readiness, operational excellence

---

## Reassessing Difficulty

Difficulty scores can be adjusted based on:

1. **New information discovered:** During investigation, scope may expand or simplify
2. **Design completion:** Design phase can reduce implementation difficulty
3. **Technology changes:** New tools or capabilities may simplify execution
4. **Team learning:** Increased familiarity reduces difficulty over time

**Process for reassessment:**
1. Document reason for change in task notes
2. Update difficulty score in task JSON
3. Re-evaluate whether breakdown is needed (if crossing ≥7 threshold)
4. Update task-overview.md to reflect new score

---

## Summary: Difficulty Assignment Flowchart

```
Start: Evaluate task
  ↓
Count steps, decision points, dependencies
  ↓
Estimate time and error risk
  ↓
Apply scoring criteria matrix
  ↓
Adjust for context factors (+/-1 to +/-2)
  ↓
Assign difficulty score (1-10)
  ↓
Is difficulty ≥7?
  ├─ YES → MUST break down into subtasks
  └─ NO → Can execute directly (planning optional)
  ↓
Document score and rationale in task JSON
```

---

## Reference: All Task Difficulty Scores

| Task ID | Task Name | Difficulty | Breakdown? |
|---------|-----------|------------|------------|
| 001 | Enhance DQ Visibility | 6 | No (direct execution) |
| 002 | Redesign Semantic Model & DAX | **7** | **Yes** (✅ broken down) |
| 003 | Redesign Power BI Report | **8** | **Yes** (subtasks planned) |
| 004 | Design & Implement RLS | 6 | No (design complete) |
| 005 | Automate External Data | 5 | No (research complete) |
| 006 | Implement Incremental Load | **7** | **Yes** (subtasks planned) |
| 007 | Add Data Quality Checks | 6 | No (framework designed) |
| 008 | Create Unit Tests | 4 | No (framework complete) |
| 009 | Document DAX Measures | 2 | No (completed) |
| 010 | Configure Pipeline Scheduling | 3 | No (simple config) |
| 011 | Implement Error Handling | 6 | No (design complete) |
| 012 | Optimize Performance | **7** | **Yes** (subtasks planned) |

**Breakdown Summary:**
- **4 tasks require breakdown** (Tasks 002, 003, 006, 012)
- **8 tasks can be executed directly** (Tasks 001, 004, 005, 007, 008, 009, 010, 011)

---

*This difficulty guide is based on the task management framework from the claude_code_environment reference repository.*
