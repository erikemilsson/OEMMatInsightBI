# Implementation Agent

Specialist for executing tasks.

**Model: Claude Opus 4.6** (`claude-opus-4-6`). When spawning this agent via the `Task` tool, always set `model: "opus"`.

## Purpose

- Execute tasks following the spec
- Produce deliverables — create files, make changes, research, draft documents
- Document what was done
- Flag issues discovered during implementation

## When to Follow This Workflow

The `/work` command directs you to follow this workflow when:
- Tasks exist with status "Pending"
- Dependencies are satisfied
- Spec check has passed (handled by /work)

## Inputs

- Task to execute (from /work or dashboard)
- `.claude/spec_v{N}.md` - Specification for acceptance criteria
- Project context
- Any constraints from /work

## Outputs

- Completed deliverables and new files
- Updated task status ("Awaiting Verification" after implementation, then "Finished" after verification passes)
- Completion notes on task
- Issues discovered (added to questions.md or new tasks)

## How This Workflow Is Invoked

Read by `/work` during Execute phase. Follow every step in order. Each step produces a required artifact.

## Workflow

### Step 1: Select Task

If no specific task provided:
1. Read dashboard.md
2. Find tasks with status "Pending"
3. Check dependencies (all must be "Finished")
4. Select highest priority unblocked task

### Step 1b: Validate Task

Before proceeding, verify the task is workable:

| Check | Fail Action |
|-------|-------------|
| `owner` is "human" | Stop - report back that task requires human action |
| `owner` is "both" | Proceed - Claude handles implementation portion |
| `difficulty` >= 7 | Stop - report back that task needs breakdown first (use `/breakdown`) |
| `status` is "Broken Down" | Stop - work on subtasks instead, not this task |
| `status` is "On Hold" | Stop - report back that task is paused (only user can resume) |
| `status` is "Absorbed" | Stop - report back that task scope was folded into another task |

If any check fails, do not proceed to Step 2.

### Step 2: Understand Task

Before starting:
- Read task description fully
- Read `.claude/spec_v{N}.md` and find the relevant sections (use task's `spec_section` field if present)
- Check what files will be affected
- Understand the "done" criteria from spec acceptance criteria

### Step 3: Set In Progress

**Required artifact:** Update task JSON file to "In Progress" **before starting any implementation work.** This is the checkpoint that proves the workflow is being followed — a task that jumps directly from "Pending" to "Finished" without passing through "In Progress" indicates the workflow was bypassed.

Update task status:
```json
{
  "status": "In Progress",
  "updated_date": "YYYY-MM-DD"
}
```

**Dashboard regeneration:** After setting "In Progress", regenerate the dashboard per `.claude/support/reference/dashboard-regeneration.md`. In parallel mode, skip this (coordinator handles it).

In sequential mode: one task "In Progress" at a time. In parallel mode (dispatched by `/work`): multiple tasks allowed — `/work` manages eligibility and file conflict checks.

### Step 4: Implement

Do the work:
- Follow existing project patterns and conventions
- Keep changes focused on the task
- Don't over-engineer
- Don't add unrequested features
- Use `.claude/support/workspace/` for temporary files (see `README.md` there for placement rules)
- If `.claude/support/learnings/` contains files, check for patterns relevant to this task

### Step 5: Self-Review

**Required artifact:** Document the review in the task notes (even briefly). A task completed without any self-review note indicates this step was skipped.

Before marking complete:
- Review all changes made
- Check for errors and edge cases
- Verify against task requirements
- Run existing tests or validation checks if available


### Step 6: Document and Trigger Verification

Implementation and verification are a single atomic operation. A task only reaches "Finished" if verification passes.

#### Step 6a: Mark Ready for Verification

Update task with transitional status:
```json
{
  "status": "Awaiting Verification",
  "completion_date": "2026-01-26",
  "updated_date": "2026-01-26",
  "notes": "Implemented login flow. Updated configuration. Added validation."
}
```

**Dashboard regeneration:** After setting "Awaiting Verification", regenerate the dashboard per `.claude/support/reference/dashboard-regeneration.md`. In parallel mode, skip this (coordinator handles it).

**Separation of concerns:**
- Do NOT write `task_verification` field — that is verify-agent's exclusive responsibility
- Do NOT write `verification-result.json` — that is verify-agent's exclusive responsibility

#### Step 6b: Trigger Per-Task Verification (MANDATORY)

Immediately after setting "Awaiting Verification", **spawn a separate agent** for verification. This ensures genuine context separation — the verifier does not share the implementation conversation and cannot be biased by it.

**Spawn the verify-agent using the `Task` tool:**

```
Task tool call:
  subagent_type: "general-purpose"
  model: "opus"
  max_turns: 30
  description: "Verify task {id}"
  prompt: |
    You are the verify-agent. Read `.claude/agents/verify-agent.md` and follow
    the Per-Task Verification Workflow (Steps T1-T8) for this task.

    Task file: .claude/tasks/task-{id}.json
    Spec file: .claude/spec_v{N}.md (section: "{spec_section}")

    Verify the implementation independently. Do NOT assume correctness.
```

The verify-agent file contains the full Turn Budget Protocol, verification steps, and result handling. The spawn prompt only needs to specify mode, task, and spec context.

**Timeout handling:** If the agent exhausts `max_turns` without writing a result, treat this as verification failure:
- Increment `verification_attempts` on the task JSON (read current value, +1, write back)
- Set task status to "Blocked"
- Add note: `[VERIFICATION TIMEOUT] verify-agent did not complete within max_turns limit`
- Report to user: the task needs manual verification or a retry


**Handle the result:**

| Result | What Happens |
|--------|--------------|
| **Pass** | verify-agent sets status to "Finished" with `task_verification.result = "pass"` |
| **Fail** | verify-agent sets status to "In Progress" with `[VERIFICATION FAIL #N]` notes (N = attempt count). Return to Step 4 to fix issues, then re-verify. After 3 total attempts, verify-agent sets status to "Blocked" instead. |

**This is atomic:** implement → verify. The gap where tasks could be "Finished" without verification no longer exists.

#### Step 6c: Post-Verification Cleanup

After verification completes (pass or fail):

**Parallel Mode Detection:** If your Task instructions include "DO NOT regenerate dashboard", you are running as a parallel agent dispatched by `/work`. In parallel mode:
- Do NOT regenerate dashboard (coordinator handles it)
- Do NOT check parent auto-completion (coordinator handles it)
- Do NOT select next task
- Return your results immediately to the coordinator

**If running in sequential mode (normal):**

**If verification passed:**
- Check parent auto-completion:
  - If this task has a `parent_task` field
  - And all sibling subtasks are now "Finished"
  - Set the parent task status to "Finished"

**Always (pass or fail):**
- Update dashboard.md in place from source data per `.claude/support/reference/dashboard-regeneration.md`
  - Source of truth: only tasks with corresponding task-*.json files
  - Preserve Notes section between `<!-- USER SECTION -->` markers

**MANDATORY: Return control to `/work` after completing this step.**
- Do NOT proceed to the next task
- `/work` will select the next task or route to phase-level verification if all tasks done

## Implementation Guidelines

### Scope Discipline

Stay within task boundaries:
- If you discover needed changes outside scope, note them for new tasks
- If a task reveals bigger issues, flag for human review
- Don't gold-plate (add unrequested polish)

### Progress Tracking

For larger tasks, update notes with progress:
```json
{
  "notes": "Phase 1/3: Database schema created. Starting API routes next."
}
```

## Handling Issues

### Blocking Issues

If you cannot proceed:
1. Set status to "Blocked"
2. Document blocker in notes
3. Add question to questions.md with today's date prefix: `- [YYYY-MM-DD] Question text`
4. Report back to /work

### Non-Blocking Issues

If you discover problems that don't block current task:
1. Complete current task
2. Create new task for discovered issue
3. Note in completion: "Discovered: [issue], see task X"

### Scope Creep

If task grows larger than expected:
1. Implement minimum viable version
2. Create follow-up tasks for extras
3. Note: "MVP complete. Additional work in tasks X, Y"

### Decisions Made During Implementation

If you make a significant choice during implementation:
1. Read `.claude/support/reference/decisions.md` for the format and example
2. Create a `decision-*.md` file in `.claude/support/decisions/` using that template
3. Add the decision to the dashboard's Decisions section
4. **Rule:** Never reference a decision ID on the dashboard without a corresponding file

### Spec Misalignment Discovered

If during implementation you realize something doesn't align with spec:
1. Stop and note the misalignment
2. Report back - /work will handle the spec check conversation
3. Don't proceed with misaligned work

## Handoff Criteria

Task is complete when:
- All task requirements met
- Work passes self-review
- Tests pass (if applicable)
- Notes document what was done
- Status set to "Finished" (after passing verification)
- Per-task verification passes (Step 6b triggers verify-agent as part of this workflow)

