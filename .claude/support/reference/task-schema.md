# Task Schema

## Minimal Task

```json
{
  "id": "1",
  "title": "Brief description",
  "status": "Pending",
  "difficulty": 3
}
```

## Full Task

```json
{
  "id": "1",
  "title": "Brief description",
  "description": "Detailed explanation of what needs to be done",
  "status": "Pending",
  "difficulty": 3,
  "owner": "claude",
  "priority": "medium",
  "due_date": "2026-02-15",
  "estimated_hours": 4,
  "created_date": "2026-01-15",
  "updated_date": "2026-01-15",
  "completion_date": null,
  "dependencies": [],
  "subtasks": [],
  "parent_task": null,
  "files_affected": [],
  "external_dependency": null,
  "phase": "1",
  "decision_dependencies": [],
  "notes": "",
  "user_feedback": "",
  "spec_fingerprint": "sha256:a1b2c3d4...",
  "spec_version": "spec_v1",
  "spec_section": "## Authentication",
  "section_fingerprint": "sha256:e5f6g7h8...",
  "section_snapshot_ref": "spec_v1_decomposed.md",
  "verification_attempts": 1,
  "task_verification": {
    "result": "pass",
    "timestamp": "2026-01-28T15:30:00Z",
    "checks": {
      "files_exist": "pass",
      "spec_alignment": "pass",
      "output_quality": "pass",
      "runtime_validation": "partial",
      "integration_ready": "pass",
      "scope_validation": "pass"
    },
    "issues": [],
    "notes": "All files created as specified. Runtime validation passed 3/5 checks; 2 require interactive confirmation."
  },
  "test_protocol": {
    "summary": "Test the TUI navigation and visual layout",
    "steps": [
      {
        "instruction": "Run the TUI application",
        "expected": "Menu with options: Dashboard, Settings, Help",
        "type": "command",
        "command": "python src/tui.py"
      },
      {
        "instruction": "Select 'Dashboard' from the menu",
        "expected": "A table showing project status with columns: Task, Status, Owner",
        "type": "interactive"
      }
    ],
    "automated_results": "Runtime validation passed 3/5 checks. Remaining 2 require visual/interactive confirmation.",
    "estimated_time": "2 minutes"
  },
  "interaction_hint": "cli_direct"
}
```

## Field Definitions

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| id | String | Number for top-level ("1"), underscore for subtasks ("1_1") |
| title | String | Brief description of what needs to be done |
| status | String | Pending, In Progress, Awaiting Verification, Blocked, On Hold, Absorbed, Broken Down, Finished |
| difficulty | Number | 1-10 scale (see shared-definitions.md) |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| description | String | Detailed explanation when title isn't enough |
| owner | String | claude (default), human, or both - see Owner Values below |
| priority | String | low, medium (default), high, critical - see Priority Values below |
| due_date | String | YYYY-MM-DD deadline for the task |
| estimated_hours | Number | Rough planning estimate in hours |
| created_date | String | YYYY-MM-DD format |
| updated_date | String | YYYY-MM-DD format |
| completion_date | String | YYYY-MM-DD format, set when Finished |
| dependencies | Array | Task IDs that must finish first |
| subtasks | Array | Task IDs (only when Broken Down) |
| parent_task | String | Parent task ID if this is a subtask |
| files_affected | Array | File paths this task will modify |
| external_dependency | Object | External blocker - see External Dependencies below |
| notes | String | Context, warnings, or completion notes - see Completion Notes Contract below |
| user_feedback | String | Feedback provided by the user via dashboard inline areas or during /work complete |
| spec_fingerprint | String | SHA-256 hash of spec at task decomposition (drift detection) |
| spec_version | String | Spec filename when task was created (e.g., "spec_v1") |
| spec_section | String | Originating section heading from spec |
| section_fingerprint | String | SHA-256 hash of the specific section content at decomposition |
| section_snapshot_ref | String | Reference to snapshot file for generating diffs (e.g., "spec_v1_decomposed.md") |
| out_of_spec | Boolean | Task not aligned with spec (user chose "proceed anyway") |
| out_of_spec_rejected | Boolean | Task rejected during out-of-spec review (archived, preserved for audit) |
| rejection_reason | String | User's reason for rejecting an out-of-spec task (optional) |
| absorbed_into | String | Task ID this task was absorbed into (required when status is "Absorbed") |
| phase | String | Phase this task belongs to (e.g., "1" or "Data Pipeline"). Tasks in Phase N+1 are blocked until all Phase N tasks complete. |
| decision_dependencies | Array | Decision IDs that block this task (e.g., ["DEC-002"]). Task remains blocked until all referenced decisions are resolved. |
| parallel_safe | Boolean | When true, task is eligible for parallel execution even with empty `files_affected`. Use for research/analysis tasks with no file side effects. |
| conflict_note | String | **Transient.** Set during parallel dispatch when a task is held back due to file conflicts (e.g., `"Held: file conflict with Task 3 on src/models.py"`). Cleared when the task is dispatched or during post-parallel cleanup. Surfaced in the dashboard Status column. |
| recovery_state | String | **Transient.** Set by `/work` Step 0 when auto-recovering a stuck task. Values: `"verification_retry"` (respawning verify-agent), `"agent_retry"` (user chose to retry after timeout). Cleared after recovery completes. Prevents double-recovery if `/work` runs again before recovery finishes. |
| user_review_pending | Boolean | Set to `true` by verify-agent when a `both`-owned task passes verification, OR when any task has a `test_protocol` (runtime validation was partial, human testing needed). Keeps the task visible for user action until the user runs `/work complete {id}` or completes guided testing. Cleared by `/work complete`. |
| verification_attempts | Number | Count of per-task verification attempts (incremented by verify-agent on each run). Escalates to human review at >= 3 (initial + 2 retries). Default: 0 (omit until first verification). |
| verification_history | Array | Append-only log of all verification attempts (pass and fail). Each entry records attempt number, result, checks, issues, and notes. Coexists with `task_verification` (which stays as the latest result for quick checks). See Verification History section below. |
| task_verification | Object | Per-task verification result recorded by verify-agent |
| test_protocol | Object | Structured testing steps for human-guided verification. Written by verify-agent when runtime validation is `"partial"` or task needs human testing. See Test Protocol section below. |
| interaction_hint | String | `"cli_direct"` or `"dashboard"`. Determines how `/work` presents the task to the user. CLI-direct tasks are presented immediately in the conversation; dashboard tasks appear in "Your Tasks". Default when absent: `"dashboard"`. |

## Owner Values

The `owner` field determines who is responsible and where tasks appear in the dashboard:

| Value | Emoji | Dashboard Location | When to Use |
|-------|-------|-------------------|-------------|
| `claude` | 🤖 | Tasks section | Tasks Claude can do autonomously (default) |
| `human` | ❗ | Action Required → Your Tasks | Requires human action (config, decisions, external) |
| `both` | 👥 | Action Required + Tasks | Collaborative work (appears in both sections) |

### Examples by Owner

**`claude`** (default - omit field if this):
- Implement features, create deliverables
- Research, analysis, comparisons
- Create tests, documentation
- Refactor, fix issues

**`human`**:
- Configure API keys, secrets
- Make business decisions
- External actions (deploy, purchase, contact)
- Review and approve

**`both`**:
- Design work (human provides direction, Claude implements)
- Content requiring human judgment (Claude drafts, human refines)

## Priority Values

| Value | Emoji | Meaning |
|-------|-------|---------|
| critical | 🔴 | Blocking other work, immediate attention required |
| high | 🟠 | Important, should be done soon |
| medium | (none) | Normal priority (default when omitted) |
| low | (none) | Nice to have, do when time permits |

Priority affects display order in Ready sections - critical tasks appear first.
Only critical and high show emoji prefixes in the dashboard to reduce visual noise.

## Drift Prevention Fields

These fields track spec-to-task alignment. All are set during decomposition (see `decomposition.md`) and used by `/work` for drift detection (see `drift-reconciliation.md`).

The fields `spec_fingerprint`, `spec_version`, `spec_section`, `section_fingerprint`, and `section_snapshot_ref` are defined in the Field Definitions table above. Together they enable granular per-section drift detection: when `/work` runs, it compares current section hashes against task fingerprints and only flags tasks from changed sections.

The `out_of_spec` and `out_of_spec_rejected` fields mark tasks outside the spec scope. See `workflow.md` § "Out-of-Spec Task Handling" for behavior rules.

## Task Verification Field

Per-task verification result recorded by verify-agent when a task is in "Awaiting Verification" status. Upon passing, the task status transitions to "Finished". This enables Tier 1 (per-task) verification in the two-tier verification system.

```json
{
  "task_verification": {
    "result": "pass",
    "timestamp": "2026-01-28T15:30:00Z",
    "checks": {
      "files_exist": "pass",
      "spec_alignment": "pass",
      "output_quality": "pass",
      "runtime_validation": "not_applicable",
      "integration_ready": "pass",
      "scope_validation": "pass"
    },
    "issues": [],
    "notes": "All files created as specified."
  }
}
```

### Sub-fields

| Sub-field | Type | Values | Description |
|-----------|------|--------|-------------|
| `result` | String | `"pass"`, `"fail"` | Overall per-task verification outcome |
| `timestamp` | String | ISO 8601 | When verification completed |
| `checks` | Object | Keys: `files_exist`, `spec_alignment`, `output_quality`, `runtime_validation`, `integration_ready`, `scope_validation` | Per-check pass/fail |
| `checks.*` | String | `"pass"`, `"fail"`, `"partial"`, `"not_applicable"`, or `"skipped"` | Individual check result. Most checks use `"pass"`/`"fail"`. `runtime_validation` additionally uses `"partial"` (some checks need human eyes), `"not_applicable"` (non-runnable output), and `"skipped"` (turn budget exceeded). |
| `issues` | Array | Issue objects `{severity, description}` | Issues found during verification |
| `notes` | String | Free text | Brief summary of verification |

### State Detection

A task "needs per-task verification" when:
- It has status "Awaiting Verification", OR
- It has status "Finished" AND does NOT have a `task_verification` field (legacy edge case)

### Failure Handling

When per-task verification fails:
- `verification_attempts` is incremented (verify-agent increments this before writing the result)
- The attempt is appended to `verification_history` (structured record of all attempts, including passes — see Verification History section)
- Task status is set back to "In Progress"
- Verification failure notes are prepended with `[VERIFICATION FAIL #{N}]` in the task `notes` field (where N = current attempt count)
- `completion_date` is cleared
- `updated_date` is updated
- Dashboard is regenerated
- **Escalation rule:** When `verification_attempts >= 3` (initial attempt + 2 re-attempts), set status to "Blocked" with note `[VERIFICATION ESCALATED] 3 attempts exhausted — requires human review` instead of retrying

### Verification History

Append-only log of every verification attempt (pass and fail). Provides a full repair trail when tasks require multiple verification cycles.

```json
{
  "verification_history": [
    {
      "attempt": 1,
      "result": "fail",
      "timestamp": "2026-01-28T14:00:00Z",
      "checks": {
        "files_exist": "pass",
        "spec_alignment": "fail",
        "output_quality": "pass",
        "runtime_validation": "not_applicable",
        "integration_ready": "pass",
        "scope_validation": "pass"
      },
      "issues": [{"severity": "major", "description": "Missing upsert for raw_game_designers table"}],
      "notes": "3 of 4 tables implemented"
    },
    {
      "attempt": 2,
      "result": "pass",
      "timestamp": "2026-01-28T15:30:00Z",
      "checks": {
        "files_exist": "pass",
        "spec_alignment": "pass",
        "output_quality": "pass",
        "runtime_validation": "not_applicable",
        "integration_ready": "pass",
        "scope_validation": "pass"
      },
      "issues": [],
      "notes": "All 4 tables implemented correctly"
    }
  ]
}
```

#### Sub-fields

| Sub-field | Type | Description |
|-----------|------|-------------|
| `attempt` | Number | Attempt number (matches `verification_attempts` at time of recording) |
| `result` | String | `"pass"` or `"fail"` |
| `timestamp` | String | ISO 8601 timestamp of when this attempt completed |
| `checks` | Object | Per-check pass/fail (same keys as `task_verification.checks`) |
| `issues` | Array | Issues found during this attempt |
| `notes` | String | Brief summary of this attempt's findings |

#### Behavior Rules

- **Append-only** — never modify or remove previous entries
- **Includes passing result** — the final passing attempt is recorded in both `verification_history` and `task_verification`
- **Coexists with `task_verification`** — `task_verification` remains the latest result for quick status checks; `verification_history` provides the full trail
- **Created on first verification** — array is created when verify-agent runs Step T6 for the first time on a task

### Verification Debt

Tasks that bypass verification create "verification debt" — Finished tasks without `task_verification`, with a failing result, or with critical issues. Debt is tracked in the dashboard under "Action Required" → "Verification Debt", blocks project completion, and is enforced by both `/work` (routing) and `/health-check` (ERROR level).

## Test Protocol Field

Written by verify-agent when runtime validation is `"partial"` or the task needs human-guided testing. Provides structured steps for the user to walk through, typically presented via the guided testing flow in `/work` when `interaction_hint` is `"cli_direct"`.

```json
{
  "test_protocol": {
    "summary": "Brief description of what needs testing",
    "steps": [
      {
        "instruction": "What to do",
        "expected": "What should happen",
        "type": "command",
        "command": "python src/app.py"
      },
      {
        "instruction": "Verify the output table",
        "expected": "Table with 3 columns: Name, Status, Date",
        "type": "visual"
      }
    ],
    "automated_results": "What runtime validation already confirmed",
    "estimated_time": "2 minutes"
  }
}
```

### Sub-fields

| Sub-field | Type | Description |
|-----------|------|-------------|
| `summary` | String | Brief description of what needs testing |
| `steps` | Array | Ordered list of test step objects |
| `steps[].instruction` | String | What the user should do |
| `steps[].expected` | String | What correct behavior looks like |
| `steps[].type` | String | `"command"` (Claude runs it), `"interactive"` (user interacts), or `"visual"` (user inspects output) |
| `steps[].command` | String | Optional. The command to execute (only for `"command"` type steps) |
| `automated_results` | String | Summary of what runtime validation already confirmed automatically |
| `estimated_time` | String | Human-readable time estimate for completing the test protocol |

### When Present

- Runtime validation returned `"partial"` — some checks passed, others need human confirmation
- Task is `owner: "both"` with runnable output — human review is part of the workflow
- Verify-agent determined the output needs visual or interactive confirmation

### When Absent

- Runtime validation returned `"pass"`, `"fail"`, or `"not_applicable"` — no human testing needed
- Task produces non-runnable output (documents, config, research)
- Existing tasks without this field follow the current flow unchanged

## Interaction Hint Field

Determines how `/work` presents human-involved tasks. Set by verify-agent during Step T7 based on the nature of the required interaction.

| Value | Behavior |
|-------|----------|
| `"cli_direct"` | Task presented immediately in the CLI conversation. Used for synchronous testing, quick confirmations, command-guided walkthroughs. |
| `"dashboard"` | Task appears in dashboard "Your Tasks" / Action Required. Used for async review, extended reading, batch decisions. |

**Default:** When absent, defaults to `"dashboard"` (preserves current behavior). Existing tasks without this field are unaffected.

**Set by:** Verify-agent Step T7, based on Step T4b runtime validation results and task characteristics.

**Overridable:** Users can always use `/work complete {id}` from the dashboard flow regardless of the hint.

## Completion Notes Contract

The `notes` field serves as structured completion notes for context transfer between implement-agent and verify-agent.

**Purpose:** When implement-agent completes a task, it writes completion notes that verify-agent reads to understand what was done — without carrying the full implementation conversation.

**Expected format:**
```json
{
  "notes": "Implemented login flow with JWT tokens. Updated auth middleware. Added input validation for email format. Known limitation: password reset deferred to Phase 2."
}
```

**Note:** Multi-line notes should be written as a single JSON string with natural sentence breaks. Use periods to separate distinct items rather than newlines or structured formatting.

**What to include:**
- **Deliverables summary** — what was built/changed (high-level, 1-3 sentences)
- **Key decisions** — choices made that affect verification (e.g., "Used bcrypt for password hashing", "Deferred error logging to Phase 2")
- **Known limitations** — edge cases not handled, deferred work, assumptions made
- **Integration notes** — how this task connects to others (e.g., "Outputs JSON format expected by Task 5")

**What NOT to include:**
- Implementation details (line-by-line changes, code snippets)
- Full reasoning or alternatives considered
- Temporary debugging notes
- Conversation history or context from the implementation session

**Verification context transfer:**
verify-agent receives:
1. Task JSON (including `notes` field with completion notes)
2. Relevant spec section (`spec_section` field)
3. Files affected (`files_affected` list)

This gives verify-agent useful signal without implementation conversation baggage, enabling genuine "fresh eyes" verification.

## External Dependencies

For tasks blocked by external factors (not other tasks):

```json
{
  "external_dependency": {
    "type": "permit|vendor|approval|delivery",
    "contact": "who to follow up with",
    "requested_date": "2026-01-20",
    "expected_date": "2026-01-28",
    "notes": "Awaiting production API keys"
  }
}
```

| Type | When to Use |
|------|-------------|
| permit | Legal, regulatory, compliance approvals |
| vendor | Third-party service, API access, contracts |
| approval | Internal stakeholder sign-off |
| delivery | Physical items, hardware, materials |

## Status Rules

1. Only work on tasks with status "Pending" or "In Progress"
2. Never work directly on "Broken Down", "On Hold", or "Absorbed" tasks
3. "Broken Down" tasks auto-complete when all subtasks are "Finished"
4. Document blockers when setting status to "Blocked"
5. Document reason when setting status to "On Hold"
6. "Awaiting Verification" is a transitional status — tasks must proceed to verification immediately
7. "Absorbed" requires the `absorbed_into` field referencing the absorbing task
8. "On Hold" tasks are excluded from auto-routing — only a user can move them back to "Pending"

### Status Flow

```
Pending → In Progress → Awaiting Verification → [verify-agent] → Finished
  ↕             ↓                                  ↓ (fail)       ↓ (owner: both)
On Hold      Blocked                          In Progress    Finished + user_review_pending
                                              (fix & retry)  → /work complete clears flag

Any non-Finished status → Absorbed (when scope is folded into another task)
```

**"Awaiting Verification"** is the transitional status between implementation completion and verification. Tasks in this status:
- Have completed implementation but not yet been verified
- Must proceed to verify-agent immediately (cannot remain in this status)
- Are set automatically by implement-agent Step 6a

### On Hold

Tasks placed on hold are excluded from all routing. Only a user can resume them.

```json
{
  "id": "7",
  "status": "On Hold",
  "notes": "Deferring until Q2 budget approval"
}
```

- `/work` skips On Hold tasks entirely (not counted as pending, blocked, or actionable)
- On Hold tasks still appear in the dashboard Tasks section with ⏸️ prefix
- Health check warns if On Hold > 30 days (may be forgotten)
- To resume: user sets status back to "Pending" (or "In Progress" if partially done)

### Absorbed

When a task's scope is folded into another task (discovered during breakdown, overlap found, or reorganization):

```json
{
  "id": "4",
  "status": "Absorbed",
  "absorbed_into": "3",
  "notes": "Scope covered by task 3 after breakdown"
}
```

- Requires `absorbed_into` field with the absorbing task's ID
- Absorbed tasks are excluded from routing, completion checks, and phase progress
- Absorbed subtasks don't block parent auto-completion
- Preserves audit trail (vs deletion, which loses history)
- Dashboard shows absorbed tasks in a collapsed/dimmed style or omits them from active counts

### Verification Requirement for Finished Status

**CRITICAL:** A task can only have `status: "Finished"` if it has a valid `task_verification` field with `result: "pass"`.

| Status | Verification Requirement |
|--------|-------------------------|
| Pending | None |
| In Progress | None |
| Awaiting Verification | Must proceed to verification immediately |
| Blocked | None |
| On Hold | None (paused — verification not applicable until resumed) |
| Absorbed | None (scope folded into another task — that task carries verification) |
| Broken Down | None (subtasks are verified individually) |
| **Finished** | **REQUIRED:** `task_verification.result` must be `"pass"` |

**Enforcement:**
- `/health-check` treats missing or failed verification on Finished tasks as an **ERROR** (not warning)
- `/work` will not route to completion phase if any Finished task lacks valid verification
- The "verification debt" metric tracks tasks that violate this rule

**Why this matters:** Without structural enforcement, verification can be bypassed by marking tasks Finished directly. This rule makes the verification artifact mandatory, not just detected post-facto.

## Task Archiving

For large projects (100+ tasks), finished tasks are automatically archived.

### Archive Structure

```
.claude/
├── dashboard.md          # Auto-generated summary
└── tasks/
    ├── task-*.json       # Active tasks
    └── archive/
        ├── task-*.json       # Archived task files
        └── archive-index.json # Lightweight summary
```

### Auto-Archive Behavior

When active task count exceeds 100, `/work` automatically:
1. Identifies finished tasks older than 7 days
2. Moves them to `.claude/tasks/archive/`
3. Updates archive-index.json

Archived tasks remain available for reference but don't clutter the dashboard.
