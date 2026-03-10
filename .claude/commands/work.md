# Work Command

The intelligent entry point for all project work. Handles spec-checking, state detection, task decomposition, task completion, and routing to specialist agents.

For workflow concepts (phases, agent synergy, checkpoints), see `.claude/support/reference/workflow.md`.

## Usage
```
/work                    # Auto-detect what needs doing
/work {task-id}          # Work on specific task
/work {request}          # Handle ad-hoc request
/work complete           # Complete current in-progress task
/work complete {id}      # Complete specific task
/work pause              # Graceful wind-down — preserve context for next session
```

## User Communication Strategy

Communication uses two tiers to keep the user informed without wasteful file I/O:

### Tier 1: Dashboard Regeneration (strategic moments)

Regenerate `dashboard.md` per `.claude/support/reference/dashboard-regeneration.md` only at moments when the user needs it current:

| Trigger | Rationale |
|---------|-----------|
| After decomposition | User needs to see the full task list |
| After parallel batch completes | Many changes at once, single regen |
| At session boundaries (before presenting final results) | User will check the dashboard |
| At project completion | Final state matters |
| When routing async work to dashboard (phase gates, decision reviews) | User will go read the dashboard |
| `/work complete` (user-initiated) | User explicitly interacting with task state |
| After decision resolution | May unblock tasks, dashboard needs to reflect new state |
| Step 1a freshness check | Catch-up on entry |

### Tier 2: Inline CLI Communication (routine status changes)

Brief, contextual messages in the CLI conversation — no file I/O, no full regen:

| Event | Inline message |
|-------|---------------|
| Task starts (In Progress) | `Starting task {id}: "{title}"` |
| Per-task verification passes | `Task {id} verified` + what's next |
| Per-task verification fails | `Task {id} verification failed: {summary}` |
| Human task becomes unblocked | `Note: Task {id} ("{title}") is now available for you — {brief description}` |
| Auto-continuation step | `Moving to task {id}: "{title}"` |

### Proactive Surfacing

When implementation work unblocks a human-owned or both-owned task, mention it inline during auto-continuation. Don't wait for the user to discover it on the dashboard — surface it conversationally.

---

## Process

### Step 0: Context Restoration and Session Recovery

#### Step 0a: Handoff Detection

Check for a context transition handoff from a previous session before anything else.

```
1. Check for .claude/tasks/.handoff.json
   IF not found → skip to Step 0b

2. Read and validate handoff file
   IF invalid JSON or missing required fields → warn, delete, skip to Step 0b

3. Check staleness
   IF timestamp > 7 days old:
     → "Handoff from {date} — project state may have changed. Reference only."
     → Delete handoff, skip to Step 0b (don't use for routing)

4. Present summary (2-4 lines):
   "Resuming from previous session ({trigger}, {relative time}):
    {task titles + progress from position/active_work}"

5. Load session_knowledge into working context
   (Available for routing and implement-agent enrichment. NOT passed to verify-agent.)

6. Delete .handoff.json

7. Proceed to Step 0b
```

**Full procedure:** `.claude/support/reference/context-transitions.md` § "Restoration"

#### Step 0b: Session Recovery Check

Check for tasks left in recoverable states by a previous session. Read `.claude/support/reference/session-recovery.md` and follow its procedure:
1. **Check session sentinel** (`.claude/tasks/.last-clean-exit.json`) — if clean exit, skip full scan
2. **If sentinel missing or stale** — run full recovery scan (6-case logic in the reference file)
3. **After recovery actions complete** — proceed to Step 1

**Malformed files during scan:** If a task file fails to parse during Step 0, skip it and continue. Report the error in Step 1.

### Step 1: Gather Context

**Version discovery:** Determine the current spec version:
```
1. Glob for .claude/spec_v*.md
2. Parse version numbers from filenames
3. Use the highest N as the current spec
4. If zero matches → no spec exists
5. If multiple matches → use highest, flag anomaly (should be exactly one)
```

Read and analyze:
- `.claude/spec_v{N}.md` - The specification (source of truth)
- `.claude/dashboard.md` - Task status and progress (read the `<!-- DASHBOARD META -->` block)

**Fast-path optimization:** If dashboard META block shows matching task_count and spec_fingerprint, skip Steps 1a/1b and jump to Step 1c. Always check drift-deferrals.json for stale deferrals even on fast-path.

**Malformed task file handling:** When reading task JSON files, if any file fails to parse:
1. Skip the file — do not abort the entire scan
2. Report the error prominently: "Task file `task-{id}.json` could not be read: {error}. Run `/health-check` for details."
3. Exclude the corrupted file from all calculations
4. If other tasks depend on the corrupted task, treat those dependencies as unresolvable (task effectively Blocked)

### Step 1a: Dashboard Freshness Check

Verify the dashboard is current before using its data. Compute a SHA-256 hash of all task IDs, statuses, difficulties, and owners, compare against the dashboard's `<!-- DASHBOARD META -->` block. If the hash differs or no metadata exists, regenerate the dashboard from task JSON files before continuing.

**Full procedure:** `.claude/support/reference/drift-reconciliation.md` § "Dashboard Freshness Check"

### Step 1b: Spec Drift Detection

Compare the current spec's SHA-256 fingerprint against task fingerprints. If different, perform section-level analysis to identify which sections changed and group affected tasks.

**Full procedure:** `.claude/support/reference/drift-reconciliation.md` § "Spec Drift Detection"

### Step 1c: Spec State Summary

After drift detection completes (or was skipped by fast-path), output a brief status line:

```
If no tasks exist:
  "Spec: v{N} (draft) — no tasks yet"

If tasks exist and spec is aligned:
  "Spec: v{N} (active) — aligned with tasks ✓"
  "Tasks: {total} total ({finished} finished, {in_progress} in progress, {pending} pending{, N on hold}{, N absorbed})"

If tasks exist and spec has changed:
  "Spec: v{N} (active) — {M} sections changed since decomposition"
  "Tasks: {total} total ({finished} finished, {in_progress} in progress, {pending} pending{, N on hold}{, N absorbed})"

If version transition detected (tasks reference older spec version):
  "Spec: v{N} (draft) — new version, tasks reference v{N-1}"
  "Tasks: {total} total — migration needed (see below)"
```

### Drift Reconciliation (if triggered)

When Step 1b detects spec drift, the following checks run in sequence. Each delegates to `drift-reconciliation.md` for the full procedure:

1. **Substantial change detection** — evaluates change magnitude, may suggest version bump. § "Substantial Change Detection"
2. **Task migration** (version transitions only) — migrates task provenance to new spec version. § "Task Migration on Version Transition"
3. **Drift budget enforcement** — checks deferred reconciliations against limits. § "Drift Budget Enforcement"
4. **Granular reconciliation UI** — per-section options: `[A]` Apply, `[R]` Review, `[S]` Skip. § "Granular Reconciliation UI"

**Post-reconciliation In Progress warning:** After reconciliation completes, check if any "In Progress" tasks had their section fingerprints updated. If so, warn:

```
⚠️ Task {id} "{title}" is In Progress but its spec section changed during reconciliation.
  Review the task's partial work against the updated requirements before continuing.
```

### Step 2: Spec Check (if request provided)

When the user provides a request or task:

```
Check request against spec:
├─ Clearly aligned → Proceed
├─ Minor/trivial addition → Proceed (doesn't need spec change)
└─ Significant but not in spec → Surface it:
   "This isn't covered in the spec. Options:
    1. Add to spec: [suggested addition]
    2. Proceed anyway (won't be verified against spec)
    3. Skip for now"
```

**If user selects "Proceed anyway":**
- Create task with `"out_of_spec": true`
- Dashboard shows ⚠️ prefix for these tasks
- Health check reports out-of-spec tasks separately

**Scope significance:** New features, architecture changes, new integrations, acceptance criteria changes = significant. Bug fixes, cleanup, small improvements = minor/trivial.

### Step 2b: Phase and Decision Gate

Check whether phases or unresolved decisions block any intended work.

Read `.claude/support/reference/phase-decision-gates.md` and follow its procedure. The reference file contains:
- Phase check (walking phases ascending, gate conditions)
- Decision dependency check (resolving checked boxes, auto-updating frontmatter)
- Late decision check (reverse cross-reference for new decisions)
- Post-decision check (inflection point handling)
- Early-exit conditions (skip when no phases or no decisions exist)

**When a decision blocks work**, present options including research:
```
Decision {DEC-NNN}: "{title}" is unresolved and blocks Task {id}.
  [R] Research options (spawns research-agent to investigate and populate the decision record)
  [S] Skip (you'll research manually — non-blocked tasks still dispatch normally)
```

If user selects `[R]`: Gather context (decision record, spec, related tasks/decisions), then spawn research-agent. See `.claude/commands/research.md` Steps 2-4 for the delegation flow. After research completes, re-present the decision for user selection. If user selects via checkbox, auto-update frontmatter per the phase-decision-gates procedure and continue.

If all checks pass → proceed to Step 2c.

### Step 2c: Parallelism Eligibility Assessment

After phase and decision checks, assess whether multiple tasks can be dispatched in parallel.

**Full procedure:** `.claude/support/reference/parallel-execution.md` § "Parallelism Eligibility Assessment"

**Summary:** Read `parallel_execution` from spec frontmatter (defaults: `enabled: true`, `max_parallel_tasks: 3`). Eligible tasks must be Pending, not human-owned, all deps Finished, in active phase, all decision deps resolved, difficulty < 7. Build conflict-free batch by pairwise-comparing `files_affected`. If batch >= 2, set `parallel_mode = true`.

### Step 3: Determine Action

**If a specific request was provided** (and passed spec check):
1. Create a task for the request (or find existing matching task)
2. Route to the "If Executing" section in Step 4
3. Continue to Step 5 (validation)

**If no request provided** (auto-detect mode):

| Condition | Action |
|-----------|--------|
| No spec exists, no tasks | Stop — direct user to create a vision document in `.claude/vision/` and run `/iterate distill` |
| No spec exists, tasks exist | **Stop and warn** — tasks without a spec cannot be verified. Options: `[S]` Create spec, `[M]` Mark all out-of-spec, `[X]` Stop. |
| Spec incomplete | Stop — prompt user to complete spec |
| Spec complete, no tasks | **Decompose** — read and follow `decomposition.md` |
| Phase transition pending approval | **Stop** — direct user to approve phase gate in dashboard *(enforced by Step 2b)* |
| Any spec task in "Awaiting Verification" | **Verify (per-task)** — see Step 4 |
| Spec tasks pending, parallel batch >= 2 | **Execute (Parallel)** — see Step 4 |
| Spec tasks pending, no parallel batch | **Execute** — see Step 4 |
| All spec tasks "Finished" with passing verification, no valid phase verification result | **Verify (phase-level)** — see Step 4 |
| Phase-level verification `"fail"` (fix tasks exist) | **Execute** — fix tasks need implementation |
| All spec tasks finished, valid phase verification result | **Complete** — see Step 4 |

**Priority order matters.** Per-task verification takes priority over executing the next task.

**CRITICAL: Verification enforcement.** Before routing to phase-level verification or completion, EVERY "Finished" spec task must have `task_verification.result == "pass"`. Never skip this check. This is structurally enforced — `/work`, `/health-check`, and the task schema all check this invariant. There is no way to bypass verification by marking tasks Finished directly.

**Explicit routing algorithm:**
```
1. Get all spec tasks (exclude out_of_spec: true, exclude status "Absorbed")
2. awaiting_verification = tasks where status == "Awaiting Verification"
3. IF awaiting_verification is not empty:
   → Route to verify-agent (per-task) for first task
   → Do NOT proceed to phase-level or completion
4. finished_tasks = tasks where status == "Finished"
5. unverified_finished = finished_tasks where task_verification does not exist
6. IF unverified_finished is not empty:
   → Route to verify-agent (per-task) for first unverified task
7. ELSE IF all spec tasks are "Finished" AND all have passing verification:
   → Check verification-result.json
   → IF file missing → Route to verify-agent (phase-level)
   → IF result == "fail" → Route to implement-agent (fix tasks)
   → IF spec_fingerprint mismatch OR tasks updated after timestamp → Re-verify
   → IF result == "pass" → Route to completion
8. ELSE IF parallel_mode (from Step 2c):
   → Route to parallel execution
9. ELSE:
   → Route to implement-agent for next pending task
```

**Auto-continuation within phases:** After a task finishes (passes per-task verification), `/work` loops back to Step 3 to determine the next action — no user prompt, no pause. Each iteration starts with an inline announcement: `Moving to task {id}: "{title}"`. Before dispatching the next task, check if any human-owned or both-owned tasks just became unblocked — if so, mention them inline: `Note: Task {id} ("{title}") is now available for you — {brief description}`. This continues automatically until a natural stopping point: phase boundary (gate approval needed), blocking decision, or verification failure requiring human escalation. The value of front-loaded decomposition and structured verification is that work flows autonomously between these stops.

**Important — spec tasks vs out-of-spec tasks:** Phase routing is based on spec tasks only (excluding `out_of_spec: true`). Out-of-spec tasks are excluded from **phase detection** (determining whether a phase is complete, triggering phase-level verification, or reaching project completion) to prevent a verify → execute → verify infinite loop. However, out-of-spec tasks still run the **full implement → verify cycle** — they are not exempt from per-task verification. The structural invariant applies universally: no task (spec or out-of-spec) can reach "Finished" without `task_verification.result == "pass"`.

**Out-of-spec task handling:** After phase routing completes (or at phase boundaries), check for pending out-of-spec tasks: `[A]` Accept (sets `out_of_spec_approved: true`), `[R]` Reject, `[D]` Defer, `[AA]` Accept all. Never auto-execute out-of-spec tasks. Accepted out-of-spec tasks are routed to implement-agent → verify-agent like any other task.

**Reject behavior (`[R]`):**
1. Prompt for optional rejection reason
2. Set `out_of_spec_rejected: true` and `rejection_reason` (if provided) on task JSON
3. Move task file to `.claude/tasks/archive/`
4. Task preserved for audit trail but excluded from active processing and dashboard

### Interaction Mode Selection

When a task involves human action (owner `"human"` or `"both"`, or `user_review_pending`), Claude should select the interaction channel that minimizes friction. This is a judgment call, not a rigid rule.

| Factor | Dashboard-mediated | CLI-direct |
|--------|-------------------|------------|
| Timing | User will do it later (async) | User should do it now (synchronous) |
| Duration | Extended (reading docs, thinking through decisions) | Quick (run a command, confirm output, yes/no) |
| Terminal needed? | No | Yes — commands to run, output to check |
| Multiple items | Batch of unrelated items | Single focused task |
| Interaction type | Passive review (read, think, decide) | Active testing (run, observe, respond) |

**Scenario examples:**
- Test a CLI/TUI → `cli_direct` (run commands, observe output)
- Test a web UI → `cli_direct` (Playwright screenshots, visual confirmation)
- Review a long document → `dashboard` (user needs reading time)
- Make a design decision → `dashboard` (user weighs options)
- Configure API keys → `cli_direct` (Claude guides step by step)
- Phase gate approval → `dashboard` (user reviews overall progress)
- Quick confirmation → `cli_direct` (2-second yes/no)

The `interaction_hint` is set by verify-agent during Step T4b/T7. `/work` respects the hint but users can always override by using `/work complete {id}` from the dashboard flow.

### Step 4: Execute Action

#### If Decomposing (spec → tasks)

Read `.claude/support/reference/decomposition.md` and follow its 10-step procedure to break the spec into granular tasks with full provenance fields.

#### If Executing

Read `.claude/agents/implement-agent.md` and follow Steps 1-6. Required artifacts:
   - Step 1: Task selected (logged)
   - Step 1b: Validation checks passed
   - Step 3: Task JSON updated to `"In Progress"` **before any implementation begins**
   - Step 4: Implementation done
   - Step 5: Self-review completed
   - Step 6a: Task JSON updated to `"Awaiting Verification"`
   - Step 6b: verify-agent **spawned as a separate Task agent** (fresh context)
   - Step 6c: Inline status update (tier 2) — e.g., `Starting task {id}: "{title}"` when beginning, status announcement after verify-agent completes. Dashboard regen deferred to next strategic moment (session boundary, parallel batch end, or async routing to dashboard).
3. **Context to provide:** Current task, relevant spec sections, constraints/notes

#### If Executing (Parallel)

When Step 2c produces a parallel batch of >= 2 tasks, execute them concurrently.

**Full procedure:** `.claude/support/reference/parallel-execution.md` § "Parallel Dispatch"

**Key rules:**
- Each parallel agent reads `implement-agent.md` and runs Steps 2/4/5/6a/6b independently
- Agents must NOT regenerate dashboard, select next task, or check parent auto-completion
- After all agents complete: final parent auto-completion, single dashboard regeneration, Step 5

#### If Verifying (Per-Task)

**You must spawn verify-agent as a separate agent. Do not verify inline.**

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

**Timeout handling:** If verify-agent exhausts `max_turns` without completing, treat as verification failure — increment `verification_attempts`, set task to "Blocked" with `[VERIFICATION TIMEOUT]` note, report to user.

**After per-task verification completes:**
- **Pass**: Announce inline: `Task {id} verified`. If `owner: "both"` or task has `test_protocol`, verify `user_review_pending: true` was set. Check for interaction mode routing (see below). Before looping, check if any human-owned or both-owned tasks just became unblocked by this completion — if so, surface them inline: `Note: Task {id} ("{title}") is now available for you — {brief description}`. Then loop back to Step 3 (auto-continuation). Dashboard regen deferred to next strategic moment.
- **Fail**: Announce inline: `Task {id} verification failed: {summary}`. Task set to "In Progress". Route to implement-agent to fix, then re-verify. No dashboard regen needed (Claude is fixing it immediately).

**Interaction mode routing (after per-task verification pass):**

When a task passes verification and has `user_review_pending: true` (set for `owner: "both"` tasks AND any task with a `test_protocol`), check for an `interaction_hint` field:

| `interaction_hint` | Routing |
|--------------------|---------|
| `"cli_direct"` | Present the task for guided testing or confirmation directly in the CLI conversation (see Guided Testing Flow below). Do NOT wait for the user to discover it in the dashboard. |
| `"dashboard"` or absent | Existing flow — task appears in dashboard "Your Tasks" / "Action Required". User reviews asynchronously. |

**Guided Testing Flow (CLI-direct with test_protocol):**

When a task has `interaction_hint: "cli_direct"` AND a `test_protocol`, present the testing flow immediately:

```
Task {id}: "{title}" — guided testing ({estimated_time})

{automated_results}

Step 1/{N}: {instruction}
  Expected: {expected}
  [R] Run command  [S] Skip  [P] Pass  [F] Fail
  (Available options depend on step type — "command" shows [R], others show [P]/[F])

Step 2/{N}: {instruction}
  Expected: {expected}
  [P] Pass  [S] Skip  [F] Fail

Guided testing complete: {passed}/{total} passed
```

**Step type handling:**
- `"command"` steps: Offer `[R]` Run — execute the command via Bash and show output. Then ask `[P]` Pass / `[F]` Fail based on the output.
- `"interactive"` steps: Show instruction and expected result. User tests manually, then signals `[P]` Pass / `[F]` Fail.
- `"visual"` steps: If a screenshot is available (e.g., from Playwright), show it. Otherwise, show instruction. User confirms `[P]` Pass / `[F]` Fail.

**After guided testing:**
- All steps passed or skipped → clear `user_review_pending`, continue auto-continuation
- Any step failed → record failure in task's `user_feedback` field, set task back to "In Progress" for fixes, route to implement-agent
- User can also provide freeform feedback at the end of the guided testing flow

**CLI-direct without test_protocol:**

When a task has `interaction_hint: "cli_direct"` but NO `test_protocol` (e.g., a quick confirmation), present the task inline:

```
Task {id}: "{title}" — ready for your review

{task description / notes summary}

[C] Complete  [F] Needs fixes (provide feedback)
```

#### If Verifying (Phase-Level)

**You must use the verify-agent phase-level workflow. Do not verify directly.**

**MANDATORY: Reconciliation Gate** — Before starting phase-level verification, ALL drift must be reconciled. Check `drift-deferrals.json`; if any deferrals exist, block verification until reconciled.

```
Task tool call:
  subagent_type: "general-purpose"
  model: "opus"
  max_turns: 50
  description: "Phase-level verification"
  prompt: |
    ultrathink

    You are the verify-agent. Read `.claude/agents/verify-agent.md` and follow
    the Phase-Level Verification Workflow (Steps 1-8).

    Spec file: .claude/spec_v{N}.md
    Task directory: .claude/tasks/

    Validate the full implementation against spec acceptance criteria.
    Create fix tasks for any issues found. Do NOT implement fixes yourself.
```

**After phase-level verification completes:** Check `.claude/verification-result.json`:

| Result | Action |
|--------|--------|
| `pass` | Proceed to "If Completing". Present any out-of-spec recommendations for user approval. |
| `fail` | Fix tasks created. Loop back to Execute, then re-verify when all spec tasks finished. |

#### If Completing

When all tasks are finished and verification conditions are met:

**MANDATORY GATE — Check before proceeding:**

1. **Verify per-task completeness:** Every "Finished" spec task must have `task_verification.result == "pass"`. If any fails, route to verify-agent per-task.
2. **Verify phase-level result:** `.claude/verification-result.json` must exist with passing result, matching `spec_fingerprint`, no tasks modified after `timestamp`. If any fails, route to verify-agent phase-level.

**Once both gates pass:**

1. **Update spec status** to `complete` (set `status: complete`, `updated: YYYY-MM-DD` in frontmatter)
2. **Regenerate dashboard** with completion summary
3. **Present final checkpoint** — report completion with verification summary
4. **Learning capture prompt** — "Project complete. Any patterns or learnings to capture? [L] Share  [S] Skip". If [L]: append to `.claude/support/learnings/project-learnings.md`. If [S]: continue silently.
5. **Stop** — do not route to any agent. The project is done.

### Step 5: Post-Dispatch Validation

Run quick validation after task dispatch to catch issues early:

1. **Task file integrity** — Verify the task JSON that was just modified is valid JSON and parseable
2. **Dashboard exists** — Confirm `.claude/dashboard.md` exists and has a `<!-- DASHBOARD META -->` block
3. **Session sentinel** — Write `.claude/tasks/.last-clean-exit.json` with current timestamp and in-progress task list (enables fast-path recovery check on next `/work` run)
4. **Session boundary dashboard freshness** — When the main work loop has reached a natural stopping point (phase boundary, blocking decision, verification failure needing human escalation, or no more eligible tasks), verify dashboard freshness against actual task state. Compute a hash of all task IDs/statuses/owners and compare against the `<!-- DASHBOARD META -->` block. If stale, regenerate now — the user should never see a stale dashboard as the final state of a work session.

For full maintenance validation (schema checks, decision integrity, template sync), use `/health-check`.

---

## Spec Alignment Examples

- **Aligned:** "Add password validation" when spec says "User authentication with email and password" → proceed
- **Minor:** "Fix typo in login error" when spec doesn't mention errors → proceed (within scope)
- **Misaligned:** "Add Google login" when spec says only email/password → surface options (add to spec, proceed anyway, skip)

---

## Output

Reports:
- Current phase and what was done
- Any spec misalignments surfaced
- Next steps or blockers

## Examples

```
# Auto-detect and continue work
/work

# Work on specific task
/work 5

# Handle ad-hoc request (gets spec-checked)
/work "Add rate limiting to the API"

# Complete the current in-progress task
/work complete

# Complete a specific task
/work complete 5

```

---

## Task Completion (`/work complete`)

Use `/work complete` for manual task completion outside of implement-agent's workflow. This is useful when:
- Completing human-owned tasks
- Marking tasks done that were worked on outside the normal flow
- Quick tasks that don't need the full implement-agent process

**Note:** When implement-agent executes tasks, it handles completion internally (Steps 3-6 of its workflow). You don't need to run `/work complete` after implement-agent finishes.

### Process

1. **Identify task** - If no ID provided, use current "In Progress" task
2. **Validate task is completable:**
   - Status must be "In Progress", OR "Finished" with `user_review_pending: true`
   - Reject: "Pending", "Broken Down", "On Hold", "Absorbed", or "Finished" without `user_review_pending`
   - For quick tasks, first set status to "In Progress", then complete
   - Dependencies must all be "Finished"
3. **Verification enforcement:**
   - If the task has `task_verification.result == "pass"` → proceed (already verified)
   - If the task has `user_review_pending: true` → proceed (verification already passed, user is completing their review)
   - If the task has NO `task_verification` or `task_verification.result != "pass"` → **spawn verify-agent (per-task)** before allowing completion. Do not mark Finished without passing verification.
   - This ensures the structural invariant: no task reaches "Finished" without `task_verification.result == "pass"`.
3b. **Human deliverable validation** (for `human` and `both`-owned tasks):
   When the user completes a task that required them to provide deliverables (files, documents, configuration, credentials setup, etc.), validate before continuing:
   - **Check quantity:** Does what was provided match what the task expected? (e.g., task said "provide 2-3 CSV files" but user provided 1, or 5)
   - **Check usability:** Are the deliverables in a usable state? (e.g., files parse correctly, headers contain expected fields, format matches what downstream tasks need)
   - **Check plan validity:** Given what was actually provided, do dependent tasks still make sense as written, or do they need adjustment?
   - If any mismatch: surface the discrepancy and assess impact on dependent tasks. Options:
     ```
     Deliverable check for Task {id}:
     [issue description — e.g., "Expected 2-3 CSV files, received 1"]

     [A] Adjust — update dependent tasks to work with what was provided
     [P] Proceed — continue as-is (deliverables are sufficient despite the difference)
     [W] Wait — task stays in progress until deliverables are corrected
     ```
   - If deliverables pass validation: proceed silently to step 4
4. **Check work** - Review all changes made for this task
   - Look for bugs, edge cases, inefficiencies
   - If issues found, fix them before proceeding
4b. **Capture inline feedback** - Read dashboard for `<!-- FEEDBACK:{id} -->` markers matching the completing task
   - If non-empty content found, save to task JSON `user_feedback` field
5. **Update task file:**
   ```json
   {
     "status": "Finished",
     "completion_date": "YYYY-MM-DD",
     "updated_date": "YYYY-MM-DD",
     "notes": "What was done, any follow-ups needed",
     "user_feedback": "Use OAuth2 instead of JWT. The client requires SSO support."
   }
   ```
   - If `user_review_pending` is `true`, clear it.
   - If `test_protocol` exists and guided testing was completed, record results in `user_feedback`.
6. **Check parent auto-completion:**
   - If parent_task exists and all non-Absorbed sibling subtasks are "Finished"
   - Set parent status to "Finished"
7. **Regenerate dashboard** - Follow `.claude/support/reference/dashboard-regeneration.md` (this is user-initiated, so the dashboard should be current when they're done)
8. **Surface unblocked tasks** - After regen, check if this completion unblocked any human-owned or both-owned tasks. If so, announce inline: `Note: Task {id} ("{title}") is now available for you — {brief description}`.
9. **Auto-archive check** - If active task count > 100, archive old tasks
10. **Post-dispatch validation** - Run main `/work` Step 5 checks (task file integrity, dashboard exists, session sentinel)

### Rules

- Never work on "Broken Down", "On Hold", or "Absorbed" tasks directly
- Parent tasks auto-complete when all non-Absorbed subtasks finish
- Always add notes about what was actually done

---

## Auto-Archive

After regenerating the dashboard, check if archiving is needed:

1. **Count active tasks** - All non-archived task-*.json files
2. **If count > 100:**
   - Identify finished tasks older than 7 days
   - Move to `.claude/tasks/archive/`
   - Update archive-index.json with lightweight summaries
   - Regenerate dashboard again

### Archive Structure

```
.claude/tasks/archive/
├── task-1.json           # Full task data (preserved)
├── task-2.json
└── archive-index.json    # Lightweight summary
```

### Referencing Archived Tasks

When a task ID is referenced but not found in active tasks:
- Check `.claude/tasks/archive/` for context
- Read archived task for reference (provides historical context)
- Archived tasks are read-only reference material

---

## Context Transition (`/work pause`)

Graceful wind-down that preserves reasoning context before compaction clears the context window. Use when a session is getting long and you want to ensure continuity.

Read `.claude/support/reference/context-transitions.md` and follow the Path A (User-Initiated) procedure. Key rules:

- Do NOT change task status to Blocked or On Hold — pause is not a failure state
- Do NOT increment `verification_attempts` if verify-agent was interrupted
- Do NOT skip the handoff file — that's the whole point
- `session_knowledge` captures what would otherwise be lost: user preferences, informal decisions, discovered patterns
