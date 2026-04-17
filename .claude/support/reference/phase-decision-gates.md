# Phase and Decision Gates

Procedure for checking phase boundaries, decision dependencies, and late decision cross-references. Run as `/work` Step 2b.

---

## Phase Check

Determine the current active phase by walking phases in ascending order:

```
1. Group tasks by `phase` field
2. Sort phases numerically (ascending)

   FOR each phase P (ascending):
     IF all tasks in phase P are "Finished":
       IF tasks exist in a higher phase (next_phase exists):
         1. Read dashboard for approved marker: <!-- PHASE GATE:{P}→{next_phase} APPROVED -->
         2. IF APPROVED marker exists:
              → Already approved. Continue to next phase.
         3. Read dashboard for phase gate marker: <!-- PHASE GATE:{P}→{next_phase} -->
         4. IF marker exists, check ALL checkboxes within the gate:
              - Parse all `- [x]` and `- [ ]` lines between gate markers
              - **Normalize checkboxes before evaluation:**
                - Treat `[x]`, `[X]`, `[✓]`, `[✔]` all as checked
                - Treat `[ ]`, `[]` as unchecked
                - Any other content inside brackets → treat as unchecked (safe default)
              - IF ALL checkboxes are checked [x]:
                → Phase transition approved.
                → Replace gate content with: <!-- PHASE GATE:{P}→{next_phase} APPROVED -->
                → Log: "Phase {P} → {next_phase} approved"
                → Learning capture (lightweight, skippable):
                    "Phase {P} complete. Any patterns or learnings to capture? [L] Share  [S] Skip"
                    If [L]: append to .claude/support/learnings/phase-learnings.md
                    If [S]: continue silently
                → Execute Version Transition Procedure (see iterate.md § "Version Transition Procedure")
                → Suggest running /iterate to flesh out Phase {next_phase} sections
                → Continue to next phase
              - IF any checkbox is unchecked [ ]:
                → Log: "Phase gate {P}→{next_phase}: {N} of {M} conditions met. Waiting for remaining approvals."
                → STOP — do not dispatch any tasks
         5. IF marker absent:
              → Regenerate dashboard with phase gate in Action Required (see `dashboard-regeneration.md` § "Regeneration Steps" Step 3)
              → Log: "Phase {P} complete. Review conditions and approve transition in dashboard, then run /work."
              → STOP — do not dispatch any tasks
       ELSE (final phase, all tasks Finished):
         → Fall through to Step 3 routing (phase-level verification → completion)
     ELSE (phase P has non-Finished tasks):
       → This is the active phase

   For target task(s):
   IF task.phase > active_phase AND task.cross_phase != true:
     "Task {id} is in Phase {task.phase}, but Phase {active_phase} is still in progress.
      {N} tasks remaining in Phase {active_phase}."
     → Skip this task, work on active-phase tasks instead

   IF task.phase > active_phase AND task.cross_phase == true:
     → Cross-phase task — bypass gate. Proceed to task-level dependency/decision checks.
     → Log: "Task {id} is cross-phase (Phase {task.phase}) — eligible despite active Phase {active_phase}."
```

### Cross-Phase Tasks

Tasks with `cross_phase: true` (see `task-schema.md`) are exempt from the phase gate on eligibility checks only. They still belong to their declared phase for verification and dashboard rendering. Typical use: long-lead human work (recruitment, procurement, approvals) that must start before the prior phase is fully done.

---

## Decision Dependency Check

For target task(s), check `decision_dependencies`:

```
1. Read each referenced decision record
2. Check if decision has a checked box in "## Select an Option"

   IF any decision is unresolved (no checked box):
     📋 Decision {DEC-NNN}: "{title}" is unresolved and blocks {N} task(s).
       [R] Research options (spawns research-agent to populate the decision record — see `.claude/commands/research.md`)
       [S] Skip (you'll research manually — open the decision doc and check your selection, then run /work)

     IF user selects [R]:
       → Gather context (decision record, spec, related tasks/decisions)
       → Spawn research-agent (see research.md Steps 2-4)
       → After research completes, re-present the decision for user selection
       → If user selects via checkbox, fall through to the auto-update logic below

     IF user selects [S]:
       → Skip this decision for now
       → Continue checking remaining decisions
       → Non-blocked tasks still dispatch normally

   IF decision has a checked box AND frontmatter status is NOT "approved"/"implemented":
     → AUTO-UPDATE FRONTMATTER:
       1. Extract selected option name from the checked line (text after `[x] `)
       2. Update frontmatter fields:
          - status: approved
          - decided: [today's date, YYYY-MM-DD]
       3. Log: "Decision {id} resolved → status updated to 'approved' (selected: {option_name})"
     → Run post-decision check (see below)

   IF decision has a checked box AND frontmatter status is already "approved"/"implemented":
     → Already processed. Run post-decision check if dependent tasks are still blocked.
```

---

## Late Decision Check (Reverse Cross-Reference)

Catches decisions that reference tasks which don't know about the decision yet:

```
For each decision-*.md file, read `related.tasks` array:
  For each referenced task ID:
    Read task JSON
    Check if decision ID is in task's `decision_dependencies`

    IF NOT (task doesn't know about this decision):
      Check task status:
      ├─ "Finished" or "In Progress":
      │    ⚠️ Decision {id} ({title}) was created after task {task_id} began.
      │
      │    Status:
      │    - Task {id}: "{status}" — {impact description}
      │
      │    Options:
      │    [1] Add {DEC-ID} as dependency + pause/flag affected tasks
      │    [2] Proceed as-is (risk: rework if decision contradicts implementation)
      │    [3] Review affected task(s) before deciding
      │
      │    IF user picks [1]:
      │      - Add decision ID to task's decision_dependencies
      │      - "In Progress" tasks → set to "Pending" (now blocked)
      │      - "Finished" tasks → add note: "Review after {DEC-ID} resolved — may need rework"
      │      - Regenerate dashboard
      │
      └─ "Pending":
           Silently fixable — add decision_dependencies and continue

    IF YES: task already tracks this decision → no issue
```

---

## Post-Decision Check

When `/work` detects a resolved decision (status `approved` or `implemented`) that has dependent tasks:

```
1. Read the decision record
2. Check `inflection_point` field in frontmatter

IF inflection_point: false (or absent):
  → Pick-and-go: unblock dependent tasks, continue to Step 2c
  → Log: "Decision {id} resolved → {N} tasks unblocked"

IF inflection_point: true:
  → Check `spec_revised` field in frontmatter
  │
  │  IF spec_revised: true
  │    → Spec already updated for this decision. Unblock dependent tasks.
  │    → Log: "Decision {id} (inflection point) resolved and spec revised → {N} tasks unblocked"
  │    → Continue to Step 2c
  │
  │  IF spec_revised is false OR absent:
  │    → Pause execution
  │    │
  │    │  ⚠️ Decision {id} ({title}) was an inflection point.
  │    │  The outcome may change what needs to be built.
  │    │
  │    │  Run `/iterate` to review affected spec sections,
  │    │  then `/work` to continue.
  │    │
  │    └─ Do NOT proceed. Wait for user to run `/iterate`.
```

**Session resilience:** The `spec_revised` field is the durable checkpoint. Across session boundaries, `/work` re-reads the decision record and checks this field — no conversation state needed.

---

## Early-Exit Conditions

To avoid unnecessary work, check these before running the full procedure:

```
IF no tasks have a `phase` field → skip Phase Check entirely
IF no decision-*.md files exist → skip Decision Check and Late Decision Check
IF both skipped → proceed directly to Step 2c
```
