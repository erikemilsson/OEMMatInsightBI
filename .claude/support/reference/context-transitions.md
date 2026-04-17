# Context Transitions

Procedure for proactive context preservation before Claude Code compaction or plan-mode clears the context window. Complements session-recovery.md (reactive) with proactive state capture.

---

## Philosophy

**Don't fight compaction, complement it.** Claude Code's auto-compact summarizes conversation to free space — this works well for general conversation context. But it can't know about environment-specific state: which agent step was active, what the user said that shaped approach, informal decisions not yet in records, and the strategic reasoning behind current work. The handoff file captures this reasoning layer.

**Two audiences.** The handoff file is primarily machine-read by `/work` Step 0 for routing decisions. Secondarily human-inspectable if the user wants to see what context was preserved.

**One-time use.** Written at wind-down, read at next `/work` Step 0, deleted after restoration. Not an accumulating log.

**Complements, doesn't replace, existing state.** Task JSONs, the session sentinel, and dashboard-state.json continue to be the durable state. The handoff adds the reasoning layer on top.

---

## Handoff File

**Location:** `.claude/tasks/.handoff.json`

**Lifecycle:**
```
WRITE — triggered by:
  a. User runs `/work pause` (graceful, preferred)
  b. PreCompact hook fires (automatic safety net)

READ — by `/work` Step 0, before session recovery scan
  - Present summary to user
  - Use for routing decisions
  - session_knowledge available to coordinator (NOT passed to agents)

DELETE — after successful restoration
  - Prevents stale handoffs from confusing future sessions
```

---

## Schema

```json
{
  "version": 1,
  "trigger": "user_pause | pre_compact",
  "timestamp": "2026-03-05T14:30:00Z",
  "spec_version": "spec_v2",

  "position": {
    "phase": "2",
    "recently_completed": ["5", "6"],
    "next_planned": "7",
    "phase_context": "Phase 2 builds the analysis pipeline on top of Phase 1's data ingestion layer."
  },

  "active_work": [
    {
      "task_id": "7",
      "task_title": "Build transformation engine",
      "agent": "implement",
      "agent_step": "Step 4 (implementation)",
      "partial": true,
      "partial_notes": "Completed column mapping logic and type coercion module. Aggregation pipeline not started.",
      "files_modified_this_session": ["src/transform/mapper.py", "src/transform/coerce.py"],
      "ready_for_verify": false
    }
  ],

  "parallel_state": null,

  "decisions_in_flight": [],

  "session_knowledge": "User prefers explicit error messages over silent fallbacks. The prototype audience is non-technical analysts.",

  "recovery_action": "Continue implementation of task 7. Column mapping and type coercion are complete, aggregation pipeline remains."
}
```

---

## Field Definitions

### Top-Level

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | Number | Yes | Schema version (currently `1`). |
| `trigger` | String | Yes | `"user_pause"` or `"pre_compact"`. |
| `timestamp` | String | Yes | ISO 8601 timestamp. |
| `spec_version` | String | Yes | Current spec filename (e.g., `"spec_v2"`). |

### `position`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `phase` | String | Yes | Current active phase. |
| `recently_completed` | Array | Yes | Task IDs completed this session. Empty array if none. |
| `next_planned` | String | No | Task ID next in the routing queue. Null if at a natural stopping point. |
| `phase_context` | String | No | What this phase is about and what prior phases established. One to two sentences. Only include if it adds context beyond spec and task titles. |

### `active_work`

Array of objects, one per task actively being worked on at wind-down. Usually one (sequential), potentially multiple (parallel).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `task_id` | String | Yes | The task ID. |
| `task_title` | String | Yes | Human-readable title. |
| `agent` | String | Yes | `"implement"`, `"verify"`, or `"coordinator"`. |
| `agent_step` | String | Yes | Where in the agent workflow. Reference step names from agent definitions (e.g., `"Step 4 (implementation)"`, `"Step T3 (spec alignment)"`). |
| `partial` | Boolean | Yes | Whether work is incomplete. |
| `partial_notes` | String | No | What was done and what remains. Same style as Completion Notes Contract. Only when `partial: true`. |
| `files_modified_this_session` | Array | No | Files actually touched this session. Supplements `files_affected` on task JSON. |
| `ready_for_verify` | Boolean | Yes | Whether implementation is complete enough to spawn verify-agent. |

### `parallel_state`

Null when not in parallel mode. When parallel execution was in progress:

```json
{
  "batch_tasks": ["7", "9", "11"],
  "completed_in_batch": ["9"],
  "held_back": [
    {"task_id": "10", "conflict_with": "7", "shared_files": ["src/config.py"]}
  ]
}
```

### `decisions_in_flight`

Array of decision IDs actively being researched or awaiting user input during this session. Empty array if none.

### `session_knowledge`

Free-form string capturing insights from conversation not persisted elsewhere:
- User preferences stated in conversation (not in CLAUDE.md or spec)
- Informal decisions not yet in decision records
- Patterns discovered during implementation
- Warnings or gotchas encountered

**Guidelines:**
- Include things the next session's Claude would benefit from knowing
- Don't repeat what's already in task JSONs, spec, or decision records
- Favor "why" over "what" — files have the "what"; conversation has the "why"
- Keep it concise — a paragraph, not an essay
- May be empty if the session was purely mechanical

**Boundary:** `session_knowledge` is available to the `/work` coordinator for routing decisions and implement-agent context enrichment. It is NOT passed to verify-agent — context separation is preserved.

### `recovery_action`

Free-form string giving the next session explicit instructions for how to resume. A note from current-Claude to future-Claude.

**Guidelines:**
- Be specific: "Continue task 7, aggregation pipeline remains" not "Continue working"
- Call out special handling: "Task 7 has partial files — don't restart from scratch"
- Mention if normal `/work` routing will handle it or if something unusual is needed

---

## Two Trigger Paths

### Path A: `/work pause` (User-Initiated)

The graceful, preferred path. Claude has full conversation context and can wind down properly.

**Behavior:**
1. Stop accepting new work after the pause signal
2. Reach the nearest clean boundary in the current agent step:
   - If mid-Step 4 (implementation): finish the current logical unit if close, otherwise stop
   - If at Step 5 (self-review): complete the review and return the structured report with `implementation_status: "partial"`
   - If at Step 6 (return report): complete the report — orchestrator writes state from it
   - If verify-agent is running: let it reach its own turn budget wind-down, or return an empty report with `result: null`
3. Update task JSON with `[PARTIAL]` notes (prefix existing notes or write new):
   ```
   [PARTIAL] Completed column mapping and type coercion. Aggregation pipeline not started.
   ```
4. Keep task status as "In Progress" (do not change to Blocked, On Hold, etc.)
5. Write `.claude/tasks/.handoff.json`
6. Write `.claude/tasks/.last-clean-exit.json` (this is a clean exit)

### Path B: PreCompact Hook (Automatic Safety Net)

Fires when auto-compaction or manual `/compact` triggers. Runs as a shell script (`.claude/hooks/pre-compact-handoff.sh`) — no access to conversation context, only filesystem.

**What the hook receives (via stdin JSON):**
- `session_id` — current session identifier
- `cwd` — working directory
- `trigger` — `"auto"` or `"manual"`
- `custom_instructions` — text from `/compact` command (empty for auto)

**What the hook does:**
1. Reads task JSON files from `.claude/tasks/` to discover in-flight work
2. Builds a structural handoff from disk state (task statuses, phases, recent completions)
3. Writes `.claude/tasks/.handoff.json`
4. Does NOT modify task JSON files
5. Skips if a handoff already exists (user already ran `/work pause` — don't overwrite the richer handoff)

**What the hook cannot capture** (conversation-only context):
- `session_knowledge` — left empty (user preferences, informal decisions only exist in conversation)
- `recovery_action` — left empty (requires Claude's reasoning about next steps)
- `agent_step` — set to "Unknown (captured from disk state)" (task JSON doesn't record which step the agent was on)
- `phase_context` — not included (requires narrative understanding of phase relationships)

**The hook is lighter-touch by design.** `/work pause` produces a rich handoff (full conversation context). The hook produces a structural handoff (disk state only). The restoration path is identical for both — `/work` Step 0a reads the same file format regardless of trigger. The `trigger` field lets the coordinator know which quality level to expect.

**Configuration:** Defined in `.claude/settings.local.json` under `hooks.PreCompact`. The matcher `""` catches both auto and manual compaction. Script at `.claude/hooks/pre-compact-handoff.sh`.

---

## Restoration: `/work` Step 0 Enhancement

When `/work` runs, Step 0 checks for a handoff file **before** the existing session recovery scan.

### Procedure

```
1. Check for .claude/tasks/.handoff.json
   IF not found → proceed to existing session recovery (sentinel check, 6-case scan)

2. Read and validate handoff file
   IF invalid JSON or missing required fields → warn, delete, proceed to session recovery

3. Check staleness
   IF timestamp > 7 days old:
     → Present: "Handoff from {date} — project state may have changed significantly. Using for reference only."
     → Do NOT use for routing decisions — rely on task file state
     → Delete handoff
     → Proceed to session recovery

4. Present summary to user:
   "Resuming from previous session ({trigger}, {timestamp}):
    {brief summary from position + active_work}"
   Keep it to 2-4 lines. Include task titles and progress indication.

5. Load session_knowledge into working context
   (Available for routing decisions and implement-agent context enrichment.
    NOT passed to verify-agent.)

6. Delete .handoff.json

7. Proceed to session recovery scan
   (Handoff informs context; session recovery handles mechanics.
    E.g., if handoff says verify was interrupted, session recovery Case 1
    handles the actual verify-agent re-spawn.)
```

### Handoff + Session Recovery Interaction

The handoff and session recovery are complementary, not competing:

| Handoff says | Session recovery detects | Combined behavior |
|-------------|------------------------|-------------------|
| Task 7 implement was partial | Task 7 "In Progress" | Route to implement-agent with enriched context from handoff |
| Task 7 verify was interrupted | Task 7 "Awaiting Verification" | Case 1: spawn verify-agent (recovery handles mechanics, handoff informs summary) |
| No active work (phase boundary) | No stuck tasks | Normal routing with phase context from handoff |
| Parallel batch was in progress | Multiple tasks in various states | Re-assess parallelism fresh from actual state; handoff provides batch context |

**Key rule:** If handoff state conflicts with actual task file state (user may have modified files between sessions), task file state wins. The handoff's `session_knowledge` and `recovery_action` may still be useful.

---

## Agent Wind-Down Behavior

When `/work pause` is triggered, the current agent needs to wind down gracefully.

### Implement-Agent Wind-Down

When implement-agent receives a wind-down signal (via `/work pause`):

1. **Stop new implementation work** — don't start a new file or logical unit
2. **Finish the current logical unit if close** — if you're a few lines from completing a function, finish it; if you're starting a major new component, stop
3. **Write partial completion notes** — same format as the Completion Notes Contract, but covering partial work:
   - What was completed so far
   - Key decisions made during this partial implementation
   - What remains to be done
   - Any gotchas or context the next session needs
4. **Update task JSON**: add `[PARTIAL]` prefix to notes, update `updated_date`, keep status "In Progress"
5. **Return control** to `/work` coordinator for handoff file creation

### Verify-Agent Wind-Down

When verify-agent receives a wind-down signal:

1. **Do NOT write partial `task_verification`** — verification is binary (pass/fail). A partial result could be mistaken for a real result.
2. **Do NOT increment `verification_attempts`** — an intentional pause is not a failed attempt
3. **Leave task status as "Awaiting Verification"** — session recovery Case 1 will handle re-spawn
4. **Return control** to `/work` coordinator for handoff file creation

This differs from the Turn Budget Protocol, which writes partial results on turn exhaustion. Wind-down is intentional and clean; turn exhaustion is a resource limit.

### Coordinator Wind-Down (Parallel Mode)

When `/work` coordinator receives pause during parallel execution:

1. **Signal running agents to wind down** — each follows its own wind-down behavior above
2. **Wait for agents to complete wind-down** (not full completion — just clean stop)
3. **Write single handoff file** with `parallel_state` capturing full batch context
4. **Process any already-completed agent results** normally (don't lose finished work)

---

## Edge Cases

### Handoff exists but task state has changed
User modified task files between sessions. Compare handoff task IDs/statuses against actual files. If divergent, warn and prefer actual file state. `session_knowledge` and `recovery_action` may still be useful.

### Multiple handoffs
Should never happen (lifecycle is write-read-delete). If a handoff file already exists when a new wind-down triggers, overwrite — newer context is more relevant.

### Handoff is stale (> 7 days)
Flag: "Handoff from {date} — project state may have changed significantly since then. Using for reference only." Don't use for routing decisions; rely on task file state.

### Wind-down during phase-level verification
Turn Budget Protocol already handles writing partial `verification-result.json`. Handoff should note that phase-level verification was in progress and is incomplete.

### Empty session (no work done)
If `/work pause` is triggered but no work was in flight, write a minimal handoff with only `position` and empty `active_work`. Or skip the handoff entirely — if nothing is in flight, session recovery handles everything.

