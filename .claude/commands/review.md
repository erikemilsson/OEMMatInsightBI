# Review Command

Implementation quality review. Assesses completed work for architecture coherence, integration quality, and pattern consistency.

## Usage

```
/review                     # Review all completed work
/review {area}              # Focus review on a specific area
```

**This is purely advisory.** Review identifies concerns and suggests improvements but does not create tasks, modify files, or change project state. The user decides what to act on.

---

## Rules

**Read-only policy:** This command reads implementation artifacts, task files, spec, decisions, and learnings. It never modifies any files or creates any tasks. All output is advisory.

---

## Process

### Step 1: Gather Review Context

Determine the current spec version: glob for `.claude/spec_v*.md`, use the highest N.

Read (all reads, no modifications):
- All task JSON files — focus on "Finished" and "In Progress" tasks
- `files_affected` from completed tasks — these are the implementation artifacts to review
- `.claude/spec_v{N}.md` — for architectural intent and acceptance criteria
- `.claude/support/decisions/decision-*.md` — for agreed-upon approaches
- `.claude/support/learnings/` — for established project patterns
- Per-task `task_verification` results — for known issues and patterns

**Scope check:**
- If fewer than 3 "Finished" tasks: "Not enough completed work for meaningful review. Continue with `/work`."
- If `/review {area}` was specified: narrow to tasks and files matching that area

### Step 2: Assess Focus Areas

Quickly assess all areas with a checkmark/warning/cross indicator (shown in the Step 3 report), then deep-dive into the worst areas (max 4 per run). Prioritize areas with the most signal (more completed tasks, more files to examine).

**Domain adaptation:** The focus areas below use software examples but apply to any project domain. Adapt the specific checks to the project type — for a procurement project, "Architecture Coherence" becomes vendor alignment; for a research project, "Pattern Consistency" becomes methodology consistency.

#### Focus Area: Architecture Coherence

- Are completed tasks following a consistent architecture?
- Do patterns established by early tasks hold in later tasks?
- Are there contradictory approaches across tasks? (e.g., one task uses callbacks, another uses async/await; one uses REST conventions, another doesn't)
- Cross-reference `files_affected` across tasks for unexpected overlap patterns

#### Focus Area: Integration Quality

- Do outputs from completed tasks connect properly to inputs of dependent tasks?
- Are shared interfaces consistent (naming, data shapes, contracts, file formats)?
- Are there orphaned outputs (Task A produces something no downstream task consumes)?
- Check dependency chains: for each finished task with dependents, verify the handoff points

**This fills the gap between per-task verification (siloed to one task) and phase-level verification (runs only after all tasks complete).** Catching integration issues mid-execution is cheaper than finding them at the end.

#### Focus Area: Pattern Consistency

- Scan completed deliverables for convention adherence
- Check `.claude/support/learnings/` for documented patterns — are tasks following them?
- Flag inconsistencies across tasks: different error handling styles, naming conventions, structural approaches, formatting

#### Focus Area: Cross-Cutting Concerns

- Error handling: Are patterns consistent? Are they comprehensive?
- Security: Input validation, auth checks, data sanitization patterns
- Logging and observability: Are events being tracked consistently?
- Configuration: Hardcoded values that should be configurable?

#### Focus Area: Technical Debt Detection

- TODOs, FIXMEs, placeholders accumulated during implementation
- Workarounds noted in task completion notes ("MVP complete, Additional work in tasks X, Y")
- Per-task verification issues marked "minor" that are accumulating into a pattern
- Scope violations recorded in `task_verification.checks.scope_validation`

#### Focus Area: Decision Implementation Audit

- For decisions with `status: implemented` and `implementation_anchors`: verify anchors are still valid (files exist, content matches)
- For decisions with `status: approved` but no anchors yet: flag that implementation may be drifting from the decision
- Check if implementation choices made during tasks align with resolved decisions

### Step 3: Present Findings

Report format:

```
Implementation Review ({phase context}, {N}/{M} tasks complete)

Architecture coherence:      [Consistent | {N} concerns | Significant issues]
Integration quality:         [Clean | {N} concerns | Gaps found]
Pattern consistency:         [Consistent | {N} inconsistencies | Divergent]
Cross-cutting concerns:      [Addressed | {N} gaps | Missing]
Technical debt:              [Minimal | {N} items | Accumulating]
Decision implementation:     [Aligned | {N} drifts | Misaligned]

Focusing on: {weakest area}
```

For each concern or issue, provide:
- **What**: Brief description of the finding
- **Where**: Specific files and tasks involved (with `file:line` references where applicable)
- **Why it matters**: Impact on quality, maintainability, or correctness
- **Suggestion**: Concrete improvement (copy-pasteable where appropriate)

### Step 4: Ask Questions (max 4)

Questions about implementation direction — not spec questions:
- "Tasks 3 and 7 use different error handling patterns. Should we standardize on the try/catch approach from Task 3?"
- "The auth middleware from Task 2 isn't referenced by Tasks 5 and 6. Is that intentional or an integration gap?"
- "I see 4 TODOs from the last 3 tasks. Should these become follow-up tasks or are they acceptable?"

**Wait for user responses before proceeding.**

### Step 5: Generate Suggestions

Based on findings and answers, suggest (all advisory, never auto-applied):

1. **Specific improvements** — with file references and copy-pasteable snippets where appropriate
2. **Pattern documentation** — suggest additions to `.claude/support/learnings/` if a pattern should be established for remaining tasks
3. **Decision record updates** — if implementation has drifted from a decision, suggest updating the decision's implementation anchors or creating a new decision record
4. **Areas to watch** — for remaining tasks, flag concerns to keep in mind

```
## Suggestions

Based on your answers, here are improvements to consider:

---

### 1. Standardize error handling (Tasks 3, 5, 7)
[Specific suggestion with code/file references]

### 2. Add integration test between auth and API modules
[Suggestion for what to verify]

### 3. Document the naming convention in learnings
[Copy-pasteable content for .claude/support/learnings/]

---

These are suggestions — apply what makes sense for your project.
```

### Step 6: Continue or Finish

```
Review complete. Options:
- Apply suggestions manually, then run /work to continue
- Run /review {area} to focus on a specific concern
- Run /iterate to refine the spec
- Run /work to continue execution
```

---

## When to Use

| Situation | Command | Why |
|-----------|---------|-----|
| Tasks in progress, want quality check | `/review` | Comprehensive implementation review |
| After parallel batch, check integration | `/review integration` | Focused integration review |
| At phase gate, assess phase quality | `/review` | Phase-level quality assessment |
| Specific concern about a subsystem | `/review {area}` | Targeted review |

---

## Principles for Good Implementation Reviews

1. **Focus on patterns, not individual lines** — Review is about systemic quality, not line-by-line code review (that's verify-agent's job)
2. **Weight findings by impact** — An architecture inconsistency affecting 5 tasks matters more than a naming convention in 1 file
3. **Consider remaining work** — If 4/12 tasks are done, flag patterns early so remaining tasks can follow them. If 11/12 tasks are done, focus on integration between what exists.
4. **Respect previous decisions** — If a pattern was chosen via a decision record, don't second-guess it. Flag only if implementation *drifts* from the decision.
5. **Stay advisory** — Never create tasks, modify files, or change state. The user decides what to act on.
