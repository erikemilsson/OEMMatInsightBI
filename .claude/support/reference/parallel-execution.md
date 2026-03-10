# Parallel Execution

Procedures for assessing parallelism eligibility, detecting file conflicts, building conflict-free batches, and dispatching/collecting parallel agents. These run inline during `/work` Steps 2c and 4.

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
  - task.phase <= active_phase (no phase dependency blocks the task)
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
| Each parallel agent | Its own `task-{id}.json` only | Any other task JSON, parent task JSON, dashboard.md, verification-result.json, dashboard-state.json |
| `/work` orchestrator | Nothing (waits for agents) | Any task JSON file owned by a running agent |

Before agents spawn (Step 2) and after they complete (Step 5), only the orchestrator writes — it sets `conflict_note` fields, performs parent auto-completion, and regenerates the dashboard. No agents are running during these windows.

**Key invariants:**
- **One writer per file:** Each agent writes only to its own task JSON file. No two agents share a task file because each is dispatched for a distinct task.
- **Parent auto-completion is orchestrator-only:** Agents are instructed "DO NOT check parent auto-completion." The orchestrator performs parent checks sequentially in the collect loop (Step 4), so concurrent writes to a parent task file cannot occur.
- **Sequential result processing:** When multiple agents complete in the same poll cycle, the orchestrator processes them one at a time (the `For each completed agent` loop is sequential), preventing race conditions on shared state like parent task files.

### 3. Spawn Parallel Agents

Use Claude Code's `Task` tool to spawn one agent per task. **Always set `model: "opus"` and `max_turns: 40`** to ensure agents run on Claude Opus 4.6 with a bounded turn limit. Each agent receives:
- The task JSON to execute
- Instructions to read `.claude/agents/implement-agent.md`
- Instructions to follow Steps 2, 4, 5, 6a, and 6b (understand, implement, self-review, mark awaiting verification, spawn verify-agent as a sub-agent for per-task verification)
- **Wind-down instruction:** "TURN BUDGET: You have 40 turns. If you reach turn 35 without completing, stop implementation, update task notes with progress so far, and return your status. Do NOT leave the task in an inconsistent state — either mark Awaiting Verification (if implementation is complete) or leave as In Progress with detailed notes (if not)."
- **Explicit instruction: "DO NOT regenerate dashboard. DO NOT select next task. DO NOT check parent auto-completion. Return results when verification completes."**
- **Note:** Each parallel implement-agent will spawn its own verify-agent sub-agent (nested Task call). This is expected — verification separation applies in parallel mode too.

All agents run concurrently via parallel `Task` tool calls with `model: "opus"`.

### 4. Collect Results with Incremental Re-Dispatch

Use `run_in_background: true` for each agent's `Task` call, then poll for completion:

```
active_agents = {task_id: {agent_id, spawned_at} for each spawned agent}
AGENT_TIMEOUT_POLLS = 60  # max poll iterations before declaring an agent timed out

WHILE active_agents is non-empty:
  Check each agent for completion (read output file or use TaskOutput with block: false)

  For each completed agent:
    1. Record result (task ID, status, verification result, files modified, issues)
    2. Remove from active_agents
    3. Check parent auto-completion for finished tasks
    4. INCREMENTAL RE-DISPATCH:
       - Re-run Step 2c eligibility assessment with current state
         (completed tasks are now "Finished", their files are released)
       - Any previously held-back tasks whose conflicts are now resolved
         become eligible
       - If new eligible tasks found AND len(active_agents) < max_parallel_tasks:
         Spawn new agents for newly-eligible tasks
         Add to active_agents
       - Clear conflict_note from newly-dispatched tasks

  For each agent that has exceeded AGENT_TIMEOUT_POLLS iterations without completing:
    1. Log: "Agent for task {id} timed out after {N} poll iterations"
    2. Read the task JSON — if still "In Progress" (agent didn't finish):
       - Set status to "Blocked"
       - Add note: "[AGENT TIMEOUT] Parallel agent did not complete within polling limit"
    3. Remove from active_agents
    4. Report to user: "Task {id} timed out — may need manual investigation or retry"

  Brief pause before next poll iteration (avoid busy-waiting)
```

This enables **incremental re-dispatch**: when Task A completes and releases its files, Task C (which was held back due to conflict with A) can start immediately — even while Tasks B and D are still running.

### 5. Post-Parallel Cleanup

After all agents complete (active_agents is empty):

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
