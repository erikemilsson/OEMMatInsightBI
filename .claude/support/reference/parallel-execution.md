# Parallel Execution

Procedures for assessing parallelism eligibility, detecting file conflicts, building conflict-free batches, and dispatching/collecting parallel agents. These run inline during `/work` Steps 2c and 4.

**Scope:** this doc covers *intra-session* parallelism — multiple `Task` agents coordinated by one `/work` orchestrator within a single conversation. For *inter-session* parallelism (many independent `claude` processes for batch workloads), see `.claude/support/reference/automation.md`.

---

## Parallelism Eligibility Assessment

After phase and decision checks pass, assess whether multiple tasks can be dispatched in parallel (runs as `/work` Step 2c).

### 1. Read Configuration

```
Read parallel_execution from spec frontmatter:
├─ enabled: true (default)
├─ max_parallel_tasks: 3 (default)
└─ If not present, use defaults
```

If `enabled: false`, skip to Step 3 (sequential mode).

### 2. Gather Eligible Tasks

```
eligible = tasks where ALL of:
  - status == "Pending" (excludes On Hold, Absorbed, Blocked, Broken Down)
  - owner != "human"
  - all dependencies have status "Finished"
  - task.phase <= active_phase OR task.cross_phase == true (no phase dependency blocks the task)
  - all decision_dependencies are resolved
  - difficulty < 7
```

### 3. Build Conflict-Free Batch

#### File Conflict Detection Algorithm

Two paths conflict if either could affect the other's output. The comparison uses **normalized paths** and **directory containment**:

```
FUNCTION paths_conflict(path_a, path_b) -> bool:
  # 1. Normalize both paths: resolve "." and "..", lowercase on case-insensitive
  #    filesystems (macOS), strip trailing slashes
  a = normalize(path_a)
  b = normalize(path_b)

  # 2. Exact match
  IF a == b: return true

  # 3. Directory containment: if either path is a prefix of the other
  #    (a directory contains a file, or vice versa)
  #    e.g., "src/" conflicts with "src/auth.py"
  #    e.g., "src/models/" conflicts with "src/models/user.py"
  IF a.startswith(b + "/") OR b.startswith(a + "/"): return true

  # 4. No conflict
  return false
```

**Rules:**
- Paths are relative to project root (no leading `./ `)
- `src/auth.py` vs `src/auth.py` → conflict (exact match)
- `src/` vs `src/auth.py` → conflict (directory containment)
- `src/auth.py` vs `src/models.py` → no conflict (different files)
- `.env` vs `.env.example` → no conflict (different files)
- Glob patterns in `files_affected` (e.g., `src/*.py`) are expanded before comparison

#### Batch Building

```
batch = []
held_back = []  # tracks tasks skipped due to file conflicts

For each eligible task (sorted by priority, then ID):
  conflicts = false
  conflict_with = null
  conflict_files = []
  For each task already in batch:
    For each pair (file_a from task.files_affected, file_b from batch_task.files_affected):
      IF paths_conflict(file_a, file_b):
        conflicts = true
        conflict_with = batch_task.id
        conflict_files.append(file_a + " vs " + file_b)
        break
    IF conflicts: break
  IF task has empty files_affected AND parallel_safe != true:
    skip (unknown file impact — not safe for parallel)
  ELSE IF conflicts:
    held_back.append({
      task_id: task.id,
      blocked_by: conflict_with,
      conflict_files: conflict_files
    })
  ELSE IF len(batch) < max_parallel_tasks:
    add task to batch
```

### 4. Determine Dispatch Mode

```
IF len(batch) >= 2:
  → parallel_mode = true
  → Log: "Parallel dispatch: {batch_size} tasks eligible"
  → IF held_back is non-empty:
      Log for each: "Task {id} held back — file conflict with Task {conflict_with} on: {conflict_files}"
ELSE:
  → parallel_mode = false
  → Fall back to sequential execution in Step 3
```

---

## Pre-Dispatch Confirmation

When Step 2c produces a parallel batch of **3 or more tasks**, confirm with the user before spawning. Batches of 2 skip this step — the parallel-dispatch default of 3 means a 2-batch is a partial use of the budget and the cheapest case to interrupt if wrong.

### Format

```
Parallel dispatch ready: {N} tasks

  Task {id}: "{title}" → files: [{files_affected}]
  Task {id}: "{title}" → files: [{files_affected}]
  ...

Verify strategy: per-task verify-agent dispatched as each implement-agent completes.

{If held_back is non-empty:}
Held back (file conflicts):
  Task {id}: "{title}" — conflict with Task {conflict_with} on [{conflict_files}]

[D] Dispatch  [S] Skip — review batch first  [1] Dispatch only first task
```

### Behavior

- `[D]` Dispatch → proceed to § "Parallel Dispatch" Step 1 (Log the Parallel Dispatch)
- `[S]` Skip → return to `/work` Step 2c. User can review tasks, adjust priorities, edit `files_affected`, then re-run `/work`.
- `[1]` Dispatch only first task → drop the batch, treat as sequential single-task dispatch on the highest-priority eligible task.

### Rationale

Parallel batches scale Claude's throughput but also remove the natural pause-points that sequential dispatch provides (per-call permission prompts, post-task user-visible state changes). A pre-dispatch confirmation restores a cheap human checkpoint without changing parallel-batch behavior.

Independent of permission settings or auto-mode classifier behavior — auto mode (which removes per-call permission prompts) actually makes this checkpoint *more* valuable, not less.

---

## Parallel Dispatch

When Step 2c produces a parallel batch of >= 2 tasks, execute them concurrently (runs as `/work` Step 4 "If Executing (Parallel)").

### 1. Log the Parallel Dispatch

```
Dispatching N tasks in parallel:
  - Task {id}: "{title}" → files: [{files_affected}]
  - Task {id}: "{title}" → files: [{files_affected}]
  ...
  File conflicts: none between batch members (verified in Step 2c)

Held back (file conflicts):
  - Task {id}: "{title}" — conflict with Task {conflict_with} on [{conflict_files}]
  (Or: "None" if held_back is empty)
```

### 2. Set Batch Tasks to "In Progress" and Annotate Held-Back Tasks

Before spawning agents, update every task in the batch:
```json
{
  "status": "In Progress",
  "updated_date": "YYYY-MM-DD"
}
```

For each held-back task, add a temporary `conflict_note` to the task JSON:
```json
{
  "conflict_note": "Held: file conflict with Task {id} on {files}. Auto-clears when conflict resolves."
}
```

This note is surfaced in the dashboard Tasks section (appended to the task's Status column as a tooltip or parenthetical) and removed when the task is dispatched.

### Write Ownership Rules

During parallel execution, strict write ownership prevents file corruption. The rules apply **while agents are running** (between spawning in Step 3 and result collection in Step 4):

| Writer | May write to | Must NOT write to |
|--------|-------------|-------------------|
| Each parallel agent | Nothing — agents return structured reports only (harness prohibits subagent writes to `.claude/`, per DEC-004) | Any `.claude/` path |
| `/work` orchestrator | All task JSONs, parent task JSONs, dashboard.md, verification-result.json, dashboard-state.json, session-log.jsonl, fix-task JSON files | Nothing — orchestrator is the sole writer in this architecture |

The orchestrator performs all writes: it sets `conflict_note` fields before dispatch, consumes each agent's return report to persist task-JSON state, performs parent auto-completion, and regenerates the dashboard at batch end.

**Key invariants:**
- **Single writer:** The orchestrator is the only writer for all `.claude/` state (task JSON, dashboard, verification-result.json, session-log.jsonl). Agents return structured reports; all persistence is mediated.
- **Sequential result processing:** When multiple agents complete in the same poll cycle, the orchestrator processes them one at a time (the `For each completed agent` loop is sequential). This naturally serializes task-JSON writes, parent auto-completion, and friction-marker appends — no race conditions possible since there's only one writer.
- **Verify-agent dispatch per implement-agent:** After each implement-agent report is processed, the orchestrator dispatches that task's verify-agent. Verify-agents can run concurrent with subsequent implement-agents, preserving pipeline throughput.

### 3. Spawn Parallel Agents

Use Claude Code's `Task` tool to spawn one agent per task. **Always set `model: "opus[1m]"` and `max_turns: 40`** to ensure agents run on Claude Opus 4.7 (1M context) with a bounded turn limit. Each agent receives:
- The task JSON to execute
- Instructions to read `.claude/agents/implement-agent.md`
- Instructions to follow Steps 1-6 (understand, implement, self-review, return structured report)
- **Wind-down instruction:** "TURN BUDGET: You have 40 turns. If you reach turn 35 without completing, stop implementation and return your report with `implementation_status: 'partial'` and detailed notes. Do NOT attempt writes to `.claude/` — subagents cannot write there; orchestrator handles all persistence from your report."
- **Explicit instruction:** "Return a structured implementation report per `.claude/agents/implement-agent.md` § Step 6. Do NOT write to task JSON, do NOT spawn verify-agent, do NOT regenerate dashboard — orchestrator owns all state persistence."

All agents run concurrently via parallel `Task` tool calls with `model: "opus[1m]"`.

### 4. Collect Results with Incremental Re-Dispatch

Use `run_in_background: true` for each agent's `Task` call, then poll for completion:

```
active_agents = {task_id: {agent_id, spawned_at} for each spawned implement-agent}
active_verifiers = {task_id: {agent_id, spawned_at} for each spawned verify-agent}
AGENT_TIMEOUT_POLLS = 60  # max poll iterations before declaring an agent timed out

WHILE active_agents or active_verifiers is non-empty:
  Check each agent for completion (read output file or use TaskOutput with block: false)

  For each completed implement-agent:
    1. Read implement-agent's return report (structured schema per implement-agent.md § Step 6)
    2. Apply "After implement-agent returns" protocol from work.md § State Persistence Protocol:
       - Status transition on task JSON per implementation_status
       - Append friction_markers to .claude/support/workspace/.session-log.jsonl
    3. If implementation_status == "completed":
       Dispatch verify-agent for this task (Task tool, model: "opus[1m]", max_turns: 30)
       Add to active_verifiers. Verify-agent dispatch is individual — one per completed
       implement-agent, runs concurrent with remaining implement-agents.
    4. Remove implement-agent from active_agents
    5. INCREMENTAL RE-DISPATCH:
       - Re-run Step 2c eligibility assessment with current state
         (completed tasks are now "Awaiting Verification" or "Finished", their files are released)
       - Any previously held-back tasks whose conflicts are now resolved
         become eligible
       - If new eligible tasks found AND len(active_agents) < max_parallel_tasks:
         Spawn new implement-agents for newly-eligible tasks
         Add to active_agents
       - Clear conflict_note from newly-dispatched tasks

  For each completed verify-agent:
    1. Read verify-agent's return report (structured schema per verify-agent.md § Step T6)
    2. Apply "After verify-agent returns (per-task mode)" protocol from work.md § State Persistence Protocol:
       - Write task_verification, append verification_history, increment verification_attempts
       - Transition status (Finished / In Progress retry / Blocked escalate)
       - Append friction_markers
       - Check parent auto-completion
    3. Remove verify-agent from active_verifiers

  For each agent (implement or verify) that has exceeded AGENT_TIMEOUT_POLLS iterations:
    1. Log: "Agent for task {id} timed out after {N} poll iterations"
    2. Apply protocol:
       - Implement-agent timeout: if task still "In Progress", set to "Blocked" with
         "[AGENT TIMEOUT] Parallel agent did not complete within polling limit"
       - Verify-agent timeout: increment verification_attempts, set status to "Blocked",
         add "[VERIFICATION TIMEOUT]" note
    3. Remove from active_agents / active_verifiers
    4. Report to user: "Task {id} timed out — may need manual investigation or retry"

  Brief pause before next poll iteration (avoid busy-waiting)
```

This enables **incremental re-dispatch**: when Task A completes and releases its files, Task C (which was held back due to conflict with A) can start immediately — even while Tasks B and D are still running.

### 5. Post-Parallel Cleanup

After all agents complete (active_agents AND active_verifiers are empty):

```
1. Final parent auto-completion check

2. Single dashboard regeneration:
   Regenerate dashboard.md per the Dashboard Regeneration Procedure
   - Remove all conflict_note fields from task JSONs (cleanup)

3. Operational checks (Step 5)

4. Loop back to Step 2c:
   Reassess remaining tasks for next parallel batch or phase transition
```

### 6. Handling Mixed Results

When some tasks pass and others fail verification:
- Passed tasks remain "Finished" — they are done
- Failed tasks are set back to "In Progress" by verify-agent within their thread
- On the next loop iteration, failed tasks are re-eligible for dispatch (potentially in a new parallel batch)
