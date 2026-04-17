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

#### Step 0 Preamble: Hazard Check

Before any execution decisions, check for known hazards.

```
1. Scan auto-memory for project-level warnings about dangerous operations
   (dev server crashes, resource-intensive builds, known environment issues)

2. Read .claude/support/reference/known-issues.md if it exists
   Match entries against the project's tech stack and directory layout

3. Store relevant hazards in working context as known_hazards[]
   These are consulted in Step 4 before spawning agents.
```

This is a lightweight read — negligible overhead, prevents repeating known-dangerous operations.

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

#### Step 0a2: Plan File Discovery

Check for workspace plan files from a previous session.

```
1. Glob for .claude/support/workspace/plan-*.md
   IF no matches → skip to Step 0b

2. For each plan file, check modification time
   IF older than 7 days → skip (stale)

3. Present discovered plans:
   "Found plan file(s):
    - plan-{topic}.md ({relative time ago})
   
   [E] Execute plan | [I] Inspect first | [S] Skip"

4. IF [E]: Read plan file, use as primary work directive
      (overrides auto-detect routing in Step 3)
   IF [I]: Display plan contents, then re-prompt [E] or [S]
   IF [S]: Continue to Step 0b (plan remains on disk for later)
```

**Plan files are not auto-deleted** — unlike handoff files, they persist until the user removes them. This allows re-reading and editing across multiple sessions.

#### Step 0b: Session Recovery Check

Check for tasks left in recoverable states by a previous session. Read `.claude/support/reference/session-recovery.md` and follow its procedure:
1. **Check session sentinel** (`.claude/tasks/.last-clean-exit.json`) — if clean exit, skip full scan
2. **If sentinel missing or stale** — run full recovery scan (6-case logic in the reference file)
3. **After recovery actions complete** — proceed to Step 1

**Malformed files during scan:** If a task file fails to parse during Step 0, skip it and continue. Report the error in Step 1.

#### Step 0c: Session Start Summary

When Step 0a found no handoff and Step 0b found no recovery issues (clean start), produce a brief orientation summary:

1. Read dashboard `<!-- DASHBOARD META -->` block for the `generated` timestamp
2. Scan task files for:
   - Tasks with `completion_date` within the last 48 hours → recent completions
   - Tasks with `status: "In Progress"` → active work
   - Tasks with `owner: "human"` or `"both"`, status `"Pending"`, all dependencies `"Finished"` → next human actions
3. Output (3-5 lines):
   ```
   Last session: {relative time from dashboard generated timestamp}
   Recent: {completed task titles, or "no recent completions"}
   Active: {in-progress task titles, or "none"}
   Your next actions: {human/both tasks ready with IDs, or "none — all human tasks complete"}
   ```
4. Proceed to Step 1

**First-run fallback:** If no dashboard META block exists (first `/work` invocation), skip the summary — Step 1 will handle first-run detection.

**Relationship to Step 1c:** Step 0c provides session context (temporal: "what happened recently"). Step 1c provides spec state ("Spec: v1 (active) — aligned with tasks"). They are complementary, not overlapping.

Note: This reads task files and dashboard META before Step 1, but Step 1 reads the same data. The summary re-uses data that would be loaded regardless — it's surfaced earlier for user orientation.

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

Also compare `template_version` in the META block against `template_version` in `.claude/version.json`. If they differ or the META field is absent, the dashboard was generated with older format rules and should be regenerated (see dashboard-regeneration.md § "Format Staleness").

**Full procedure:** `.claude/support/reference/drift-reconciliation.md` § "Dashboard Freshness Check"

### Step 1b: Spec Drift Detection

Compare the current spec's SHA-256 fingerprint against task fingerprints. If different, perform section-level analysis to identify which sections changed and group affected tasks.

**Script alternative:** `.claude/scripts/fingerprint.py --spec` / `--sections` for deterministic hashes when the orchestrator runs the drift check.

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

### Step 1d: Non-Actionable State Fast Path (auto-detect only)

After Step 1c, check whether the project state has any Claude-actionable work. This avoids running the full analysis pipeline (Steps 2, 2b, 2c, 3) when there's nothing for Claude to do.

**Preconditions (all must be true):**
- Auto-detect mode (no user request or task ID provided)
- Tasks exist (not first run / decomposition needed)
- Spec exists and is complete
- No tasks in `"In Progress"` status (active work exists)
- No tasks in `"Awaiting Verification"` status (verification takes priority)
- No unverified Finished tasks (verification debt takes priority)

**Remaining tasks** = spec tasks where status NOT IN (`"Finished"`, `"Absorbed"`, `"Broken Down"`, `"In Progress"`)

```
IF remaining_tasks is NOT empty
   AND every task in remaining_tasks satisfies at least one of:
     - owner == "human" (regardless of status)
     - status == "Blocked"
     - status == "On Hold"
   → FAST EXIT
```

**Before presenting fast-exit output:** Verify dashboard freshness (same check as Step 5 item 4). If stale, regenerate first — the user may check the dashboard after seeing this message.

**Fast-exit output by category:**

All human-owned:
```
No Claude-actionable work — {N} remaining tasks are human-owned.

Your next actions:
- Task {id}: "{title}" — {brief description}
- Task {id}: "{title}" — {brief description}

Run `/work complete {id}` when done with a task.
```

All Blocked:
```
No Claude-actionable work — {N} remaining tasks are blocked.

Blockers:
- Task {id}: "{title}" — {blocker from notes}
- Task {id}: "{title}" — {blocker from notes}

Resolve the blockers above, then run `/work` to continue.
```
If any blocked task has `decision_dependencies`, suggest `/research {DEC-ID}`.

All On Hold:
```
No Claude-actionable work — {N} remaining tasks are on hold.

On hold:
- Task {id}: "{title}" — {reason from notes}

Resume a task by setting its status to "Pending", then run `/work`.
```

Mixed non-actionable:
```
No Claude-actionable work — {N} remaining tasks: {X} human-owned, {Y} blocked, {Z} on hold.

{list by category, same format as above}
```

After output, append 1-2 contextual command suggestions (see Contextual Command Suggestions below), then proceed to Step 5 (post-dispatch validation) — skip Steps 2, 2b, 2c, 3, and 4.

If none of the fast-path conditions are met, proceed to Drift Reconciliation / Step 2 as normal.

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
├─ Minor/trivial addition → Proceed (no spec change, no formal planning)
└─ Significant but not in spec → Surface it:
   "This isn't covered in the spec. Options:
    1. Add to spec: [suggested addition]
    2. Proceed anyway (won't be verified against spec)
    3. Skip for now"
```

**Skip formal planning for trivial requests:** If the diff for the request fits in one sentence (typo fix, log line addition, variable rename, single import update), dispatch implement-agent directly — do not route through `/research`, decision records, or task decomposition. The "Minor/trivial addition" branch above is the entry point. The principle: planning overhead should be proportional to scope.

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

**Required inline trigger — checkbox detection on every entry:**

For every `decision-*.md` file with frontmatter `status: proposed`:

1. Read the file's `## Select an Option` section
2. Scan for checked boxes — match `[x]`, `[X]`, `[✓]`, `[✔]` (per the normalization in `phase-decision-gates.md` § "Phase Check")
3. If a checked box is found AND frontmatter `status` is still `proposed`:
   - Extract the selected option name (text after `[x] ` on the matched line)
   - Update frontmatter: `status: approved`, `decided: <today's YYYY-MM-DD>`
   - Populate the Decision section using the option name and the matching Option Details rationale
   - Run the Post-Decision Check (`phase-decision-gates.md` § "Post-Decision Check") — handles inflection-point pause if applicable
   - Log: `Decision {DEC-ID} resolved → status updated to 'approved' (selected: {option_name})`
4. If no checked boxes are found across all proposed decisions, proceed to the rest of Step 2b without changes.

This step MUST run on every Step 2b invocation. It is the caller's responsibility — `phase-decision-gates.md` defines the algorithm, but `/work` Step 2b is what fires it. Do not skip this scan even if other Step 2b checks suggest no new decisions.

**When a decision blocks work**, present options including research:
```
Decision {DEC-NNN}: "{title}" is unresolved and blocks Task {id}.
  [R] Research options (spawns research-agent to investigate and populate the decision record)
  [S] Skip (you'll research manually — non-blocked tasks still dispatch normally)
```

**When Claude encounters an ambiguity or choice point** (not covered by an existing decision record), it must surface it to the user rather than deciding silently:
```
Ambiguity detected: {description of the choice point}
  [D] Create decision record (formal tracking)
  [I] Resolve inline (quick resolution, no formal record)
  [S] Skip for now
```
Claude must never resolve ambiguities autonomously. This applies during routing, spec checking, task dispatch, and any other step where Claude faces a choice the user hasn't explicitly decided.

If user selects `[R]`: Gather context (decision record, spec, related tasks/decisions), then spawn research-agent. See `.claude/commands/research.md` Steps 2-4 for the delegation flow. After research completes, re-present the decision for user selection. If user selects via checkbox, auto-update frontmatter per the phase-decision-gates procedure and continue.

If all checks pass → proceed to Step 2c.

### Step 2c: Parallelism Eligibility Assessment

After phase and decision checks, assess whether multiple tasks can be dispatched in parallel.

**Full procedure:** `.claude/support/reference/parallel-execution.md` § "Parallelism Eligibility Assessment"

**Summary:** Read `parallel_execution` from spec frontmatter (defaults: `enabled: true`, `max_parallel_tasks: 3`). Eligible tasks must be Pending, not human-owned, all deps Finished, in active phase (or `cross_phase: true`), all decision deps resolved, difficulty < 7. Build conflict-free batch by pairwise-comparing `files_affected`. If batch >= 2, set `parallel_mode = true`.

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
8. ELSE IF remaining pending tasks exist (status "Pending", all deps "Finished")
      AND all of them have owner == "human":
      → (Fallback for cases not caught by Step 1d fast path — e.g., when
         some tasks are Pending with unmet deps alongside human-ready tasks)
      → Do NOT dispatch an agent
      → Output: summary of human tasks ready + contextual command suggestions (see Contextual Command Suggestions below)
      → Proceed to Step 5 (post-dispatch validation) — skip Step 4
9. ELSE IF parallel_mode (from Step 2c):
   → Route to parallel execution
10. ELSE IF a pending task exists with owner != "human" AND all deps "Finished":
   → Route to implement-agent for that task
11. ELSE:
   → No eligible tasks — all remaining Claude-owned tasks have unmet dependencies.
   → Output: "No dispatchable tasks — {N} tasks remain but their dependencies aren't met yet."
   → List each blocked-by-dependency task with its unmet deps.
   → Proceed to Step 5 (post-dispatch validation) — skip Step 4
```

**Auto-continuation within phases:** After a task finishes (passes per-task verification), `/work` loops back to Step 3 to determine the next action — no user prompt, no pause. Each iteration starts with an inline announcement: `Moving to task {id}: "{title}"`. Before dispatching the next task, check if any human-owned or both-owned tasks just became unblocked — if so, mention them inline: `Note: Task {id} ("{title}") is now available for you — {brief description}`. This continues automatically until a natural stopping point: phase boundary (gate approval needed), blocking decision, verification failure requiring human escalation, or all remaining tasks non-actionable (human-owned, blocked, or on hold — see Step 1d). The value of front-loaded decomposition and structured verification is that work flows autonomously between these stops.

**Important — spec tasks vs out-of-spec tasks:** Phase routing is based on spec tasks only (excluding `out_of_spec: true`). Out-of-spec tasks are excluded from **phase detection** (determining whether a phase is complete, triggering phase-level verification, or reaching project completion) to prevent a verify → execute → verify infinite loop. However, out-of-spec tasks still run the **full implement → verify cycle** — they are not exempt from per-task verification. The structural invariant applies universally: no task (spec or out-of-spec) can reach "Finished" without `task_verification.result == "pass"`.

**Out-of-spec task handling:** After phase routing completes (or at phase boundaries), check for pending out-of-spec tasks: `[A]` Accept (sets `out_of_spec_approved: true`), `[R]` Reject, `[D]` Defer, `[AA]` Accept all. Never auto-execute out-of-spec tasks. Accepted out-of-spec tasks are routed to implement-agent → verify-agent like any other task.

**Reject behavior (`[R]`):**
1. Prompt for optional rejection reason
2. Set `out_of_spec_rejected: true` and `rejection_reason` (if provided) on task JSON
3. Move task file to `.claude/tasks/archive/`
4. Task preserved for audit trail but excluded from active processing and dashboard

### Contextual Command Suggestions

When Step 3 reaches a stopping point (no agent dispatch), append 1-3 relevant command suggestions to the output:

| Condition | Suggestion |
|-----------|------------|
| All remaining tasks are `owner: human` | "Your next actions: {task list with IDs}. Run `/work complete {id}` when done." |
| All remaining tasks are `Blocked` | "Resolve blockers above, then run `/work` to continue." |
| All remaining tasks are `Blocked` with decision deps | "Run `/research {DEC-ID}` to investigate, or resolve blockers manually." |
| All remaining tasks are `On Hold` | "Resume a task: update its status to Pending, then run `/work`." |
| Mixed non-actionable (human + blocked + on hold) | "Run `/work complete {id}` for human tasks, resolve blockers, or resume held tasks." |
| No eligible tasks (deps unmet) | "Waiting on dependencies. Check blocked/human tasks that other tasks depend on." |
| Phase gate pending approval | "Review the phase gate in the dashboard, then run `/work` to continue." |
| Unresolved decision blocks work | "Run `/research {DEC-ID}` to investigate, or resolve it in the dashboard." |
| Spec incomplete | "Run `/iterate` to refine the specification." |
| No spec exists | "Create a vision document in `.claude/vision/` and run `/iterate distill`." |
| Feedback items exist (new/refined) | "You have {N} feedback items. Run `/feedback review` to triage." |

Rules:
- Maximum 3 suggestions per stopping point
- Prioritize by actionability: human tasks ready > decisions > feedback
- Always include the specific command with arguments, not just a description
- Only suggest commands relevant to the current state

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

#### Safety Gate (all execution paths)

Before spawning any agent, check `known_hazards[]` (from Step 0 Preamble):

```
IF the task involves operations matching a known hazard:
  "⚠️ Known issue: {hazard description}
   This task involves {matching operation}.
   [P] Proceed | [S] Skip task | [W] Use workaround: {specific fix}"
```

The safety gate applies to implement-agent dispatch, verify-agent runtime validation, and phase-level verification — any path that may launch processes.

#### If Decomposing (spec → tasks)

Read `.claude/support/reference/decomposition.md` and follow its 10-step procedure to break the spec into granular tasks with full provenance fields.

#### State Persistence Protocol

After any agent (implement-agent or verify-agent) returns a structured report, the orchestrator is responsible for all state transitions, JSON persistence, and dashboard updates. Agents cannot write to `.claude/` paths — this is enforced by the Claude Code harness (see DEC-004). Follow this protocol precisely to preserve the atomic implement→verify contract.

**Schemas:** The two agent return schemas are defined in `.claude/agents/implement-agent.md` § "Step 6: Return Structured Report" and `.claude/agents/verify-agent.md` § "Step T6: Construct Verification Report" (per-task) + § "Step 7: Include Verification Result in Report" (phase-level).

**After implement-agent returns:**

1. **Status transition** based on `implementation_status`:
   - `completed`: write `{ "status": "Awaiting Verification", "completion_date": report.completion_date, "updated_date": today, "notes": report.notes }` to task JSON
   - `partial`: leave status "In Progress"; prepend `[PARTIAL]` to notes
   - `blocked`: write `{ "status": "Blocked", "notes": "...", "updated_date": today }`; surface `issues_discovered[]` to user
   - `misaligned`: do not advance status; route to spec-alignment flow with `issues_discovered[]` context

2. **Append friction markers:** for each marker in `report.friction_markers`, add `task_id: report.task_id` and append as a JSON line to `.claude/support/workspace/.session-log.jsonl` (Read existing content, then Write with appended line; if file doesn't exist, create it)

3. **Dashboard regeneration:** in sequential mode, regenerate `dashboard.md` per `.claude/support/reference/dashboard-regeneration.md`. In parallel mode, defer — handled at batch-end.

4. **For `completed` status:** dispatch verify-agent (see "If Verifying (Per-Task)" section) and then apply the "After verify-agent returns" protocol below.

**After verify-agent returns (per-task mode):**

1. **Read task's current `verification_attempts`** (default 0), compute `new_attempts = current + 1`
2. **Build `verification_history` entry** from report's `checks`, `issues`, `notes`, with `{"attempt": new_attempts, "result": report.result, "timestamp": report.timestamp}`. Append to task's `verification_history[]` array (create array if absent).
3. **Write `task_verification`** field to task JSON using report's `result`, `timestamp`, `checks`, `notes`, `issues`
4. **Status transition** based on `result`:
   - `pass`: set `status: "Finished"`, `updated_date: today`. If `report.user_review_pending == true`, also write `user_review_pending: true`, `test_protocol: report.test_protocol`, `interaction_hint: report.interaction_hint`
   - `fail` AND `new_attempts < 3`: set `status: "In Progress"`, `updated_date: today`. Clear `completion_date`. Prepend `[VERIFICATION FAIL #{new_attempts}]` to notes with the fail summary
   - `fail` AND `new_attempts >= 3`: set `status: "Blocked"`, `updated_date: today`. Prepend `[VERIFICATION ESCALATED]` note — "3 attempts exhausted — requires human review"
5. **Timeout detection:** if verify-agent exhausted max_turns without returning a valid report, treat as fail: increment `verification_attempts`, set status to "Blocked", add `[VERIFICATION TIMEOUT]` note
6. **Append friction markers** from `report.friction_markers` (same as implement-agent)
7. **Parent auto-completion:** if task has `parent_task` and all siblings are now "Finished", set parent to "Finished"
8. **Dashboard regeneration:** sequential mode — regenerate now; parallel mode — defer

**After verify-agent returns (phase-level mode):**

1. **Write `.claude/verification-result.json`** using the report's payload: `result`, `timestamp`, `spec_version`, `spec_fingerprint`, `summary`, `criteria_passed`, `criteria_failed`, `criteria`, `issues`, plus a `tasks_created[]` array populated with the IDs of task files you create in the next step
2. **Create fix task files:** for each entry in `report.fix_tasks_to_create[]`, write `task_{id}.json` with the entry's `task_json` payload plus `out_of_spec` flag
3. **Append friction markers**
4. **Regenerate dashboard** — include Verification Debt sub-section if debt exists; show out-of-spec tasks with ⚠️ prefix
5. **If result is `fail`:** loop back to Execute phase for fix tasks. If `pass`: proceed to "If Completing"

#### If Executing

**Before dispatch:** orchestrator sets task JSON to `{"status": "In Progress", "updated_date": today}`.

Dispatch implement-agent (Task tool with `model: "opus[1m]"`) instructing it to read `.claude/agents/implement-agent.md` and follow Steps 1-6. Agent returns a structured report.

**After agent returns:** apply "After implement-agent returns" from State Persistence Protocol. Then, if `implementation_status == "completed"`, dispatch verify-agent per "If Verifying (Per-Task)" and apply "After verify-agent returns" protocol.

**Context to provide:** Current task, relevant spec sections, constraints/notes, and an explicit instruction that the agent must not attempt writes to `.claude/` — return the structured report only.

**Inline status update (tier 2):** announce `Starting task {id}: "{title}"` when dispatching and a pass/fail summary after verify-agent completes. Dashboard regen deferred to next strategic moment (session boundary, parallel batch end, or async routing to dashboard).

#### If Executing (Parallel)

When Step 2c produces a parallel batch of >= 2 tasks, execute them concurrently.

**Full procedure:** `.claude/support/reference/parallel-execution.md` § "Parallel Dispatch"

**Key rules:**
- **Pre-dispatch confirmation (batch ≥ 3):** Before spawning, present the dispatch plan to the user — task IDs, titles, files affected, verify strategy — and await explicit confirmation. Skip for batches of 2 (low surprise; partial budget). See parallel-execution.md § "Pre-Dispatch Confirmation" for the prompt format and `[D]`/`[S]`/`[1]` behavior.
- Orchestrator sets all batch tasks to "In Progress" before dispatch (see parallel-execution.md § 2)
- Each parallel implement-agent reads `implement-agent.md` and follows Steps 1-6; returns a structured report
- As each implement-agent report arrives, orchestrator applies "After implement-agent returns" protocol AND dispatches that task's verify-agent (see parallel-execution.md § 4)
- As each verify-agent report arrives, orchestrator applies "After verify-agent returns" protocol
- After all reports processed: final parent auto-completion, single dashboard regeneration, post-dispatch validation (Step 5)

#### If Verifying (Per-Task)

**You must spawn verify-agent as a separate agent. Do not verify inline.**

```
Task tool call:
  subagent_type: "general-purpose"
  model: "opus[1m]"
  max_turns: 30
  description: "Verify task {id}"
  prompt: |
    You are the verify-agent. Read `.claude/agents/verify-agent.md` and follow
    the Per-Task Verification Workflow (Steps T1-T8) for this task.

    Task file: .claude/tasks/task-{id}.json
    Spec file: .claude/spec_v{N}.md (section: "{spec_section}")

    Verify the implementation independently. Do NOT assume correctness.
```

**Timeout handling:** If verify-agent exhausts `max_turns` without returning a valid report, treat as verification failure — per State Persistence Protocol, increment `verification_attempts`, set task to "Blocked" with `[VERIFICATION TIMEOUT]` note, report to user.

**After per-task verification completes:** verify-agent returns a structured per-task report. Apply "After verify-agent returns (per-task mode)" from State Persistence Protocol.

**Auto-continuation:** after the orchestrator persists verification state:
- **Pass**: announce inline `Task {id} verified`. If `report.user_review_pending == true`, check `interaction_hint` for routing (see below). Before looping, check if any human-owned or both-owned tasks just became unblocked by this completion — if so, surface them inline: `Note: Task {id} ("{title}") is now available for you — {brief description}`. Then loop back to Step 3 (auto-continuation). Dashboard regen deferred to next strategic moment.
- **Fail (retry)**: announce inline `Task {id} verification failed: {summary} — routing back to implement-agent`. Task was set back to "In Progress" by the protocol. Route to implement-agent to fix, then re-verify. No dashboard regen needed (Claude is fixing it immediately).
- **Fail (escalated)**: announce inline `Task {id} verification escalated after 3 attempts`. Stop auto-continuation; report to user.

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
  model: "opus[1m]"
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

**After phase-level verification completes:** verify-agent returns a structured phase-level report. Apply "After verify-agent returns (phase-level mode)" from State Persistence Protocol.

| Result | Action |
|--------|--------|
| `pass` | Proceed to "If Completing". Present any out-of-spec recommendations for user approval. |
| `fail` | Fix tasks created by the orchestrator. Loop back to Execute, then re-verify when all spec tasks finished. |

#### If Completing

When all tasks are finished and verification conditions are met:

**MANDATORY GATE — Check before proceeding:**

1. **Verify per-task completeness:** Every "Finished" spec task must have `task_verification.result == "pass"`. If any fails, route to verify-agent per-task.
2. **Verify phase-level result:** `.claude/verification-result.json` must exist with passing result, matching `spec_fingerprint`, no tasks modified after `timestamp`. If any fails, route to verify-agent phase-level.

**Once both gates pass:**

1. **Update spec status** to `complete` (set `status: complete`, `updated: YYYY-MM-DD` in frontmatter)
2. **Regenerate dashboard** to reflect completion state (Action Required clears; Progress shows final phase complete; Tasks section collapses fully-finished phases)
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
   - If the task has `owner: "human"` AND no `task_verification` → auto-generate self-attestation:
     ```json
     {
       "task_verification": {
         "result": "pass",
         "timestamp": "ISO 8601",
         "checks": { "self_attested": "pass" },
         "notes": "Human task — completed by user",
         "issues": []
       }
     }
     ```
     Write to task JSON and proceed. Human tasks are verified by the user's attestation of completion, not by verify-agent.
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
   - If deliverables pass validation: proceed silently to step 3c
3c. **Collect completion notes (interactive):**
   Ask the user for feedback inline in the CLI conversation:

   ```
   Task {id}: "{title}" — any notes on how this went?
   (Type your notes, or press Enter to skip)
   ```

   - If the user provides feedback → store in `user_feedback` field
   - If the user skips → proceed without feedback
   - This is the PRIMARY feedback path for `/work complete`
   - Dashboard FEEDBACK markers remain as an ASYNC alternative — if the user wrote feedback in the dashboard before running `/work complete`, Step 4b captures it as fallback
4. **Check work** - Review all changes made for this task
   - Look for bugs, edge cases, inefficiencies
   - If issues found, fix them before proceeding
4b. **Capture dashboard feedback (fallback)** - Read dashboard for `<!-- FEEDBACK:{id} -->` markers matching the completing task
   - If non-empty content found AND no inline feedback was captured in Step 3c, save to task JSON `user_feedback` field
   - If both inline (Step 3c) and marker feedback exist, concatenate: inline first, then marker content (newline-separated)
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

### Interaction Assessment (Track 2 — Cross-Project Logging)

After writing the handoff file but before ending the session, generate an interaction assessment. This is the nuanced "why" layer that automated friction markers (Track 1) cannot capture — insights about design pushback opportunities, workflow friction patterns, and observations that only Claude with conversation context can identify.

**Write to:** `.claude/support/workspace/.interaction-assessment.json`

```json
{
  "session_date": "YYYY-MM-DD",
  "template_version": "[from version.json]",
  "design_pushback_opportunities": [
    "Description of a moment where Claude should have suggested a different approach"
  ],
  "workflow_friction_notes": [
    "Description of template workflow friction observed during the session"
  ],
  "unstructured_observations": "Free-form text about anything else relevant to template improvement"
}
```

**Guidelines:**
- Focus on template-improvement signals, not project-specific details
- `design_pushback_opportunities` captures the "styler scenario" — moments where a different approach would have been better
- `workflow_friction_notes` captures repeated user workarounds or skipped steps
- Keep it concise — this supplements Track 1 markers, not replaces them
- If the session had no template-relevant observations, write the file with empty arrays

### Session Export

After writing both the handoff file and interaction assessment, compile the session export:

1. Read `.claude/support/workspace/.session-log.jsonl` (Track 1 friction markers, if any exist)
2. Read `.claude/support/workspace/.interaction-assessment.json` (Track 2, just written above)
3. Read `.claude/version.json` for template version
4. Compile into a unified export:

```json
{
  "export_version": 1,
  "source_project": "[project name from git remote or root CLAUDE.md]",
  "template_version": "[from version.json]",
  "session_date": "YYYY-MM-DD",
  "automated_markers": [ /* Track 1 markers from session log */ ],
  "session_metrics": {
    "tasks_completed": 0,
    "verification_pass_rate": 0.0,
    "recovery_events": 0
  },
  "claude_assessment": { /* Track 2 assessment */ },
  "export_quality": "full"
}
```

5. Write to `.claude/support/workspace/.session-export-YYYY-MM-DD.json`
6. If `template_inbox_path` is configured in `.claude/version.json`, copy the export there
7. Clean up: delete `.session-log.jsonl` and `.interaction-assessment.json` (data is now in the export)

**If `/work pause` is not run** (PreCompact hook fires instead): The hook compiles a markers-only export (`"export_quality": "markers_only"`, `"claude_assessment": null`) from whatever Track 1 markers exist on disk. See the updated hook in `context-transitions.md`.
