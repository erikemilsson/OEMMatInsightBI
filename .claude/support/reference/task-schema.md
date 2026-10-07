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
  "phase_name": "Core Infrastructure",
  "decision_dependencies": [],
  "notes": "",
  "user_feedback": "",
  "spec_fingerprint": "sha256:a1b2c3d4...",
  "spec_version": "spec_v1",
  "spec_section": "## Authentication",
  "section_fingerprint": "sha256:e5f6g7h8...",
  "section_snapshot_ref": "spec_v1_decomposed.md",
  "spec_unmapped": false,
  "verification_attempts": 1,
  "task_verification": {
    "result": "pass",
    "timestamp": "2026-01-28T15:30:00Z",
    "checks": {
      "files_exist": "pass",
      "consistency_check": "pass",
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
| notes | String | Context, warnings, or completion notes, newest first: every write prepends and never replaces - see Completion Notes Contract below |
| user_feedback | String | Feedback the user gave during `/work complete` or guided testing. History, newest first: each write prepends a `[YYYY-MM-DD]` entry and never overwrites (`work-procedures.md § "State Persistence Protocol"`) |
| spec_fingerprint | String | SHA-256 hash of the full spec at task decomposition, refreshed by drift reconciliation. The drift check doesn't use it (it compares `section_fingerprint`) |
| spec_version | String | Spec filename when task was created (e.g., "spec_v1") |
| spec_section | String | Originating section heading from spec |
| section_fingerprint | String | SHA-256 hash of the specific section content at decomposition, refreshed by drift reconciliation. The drift check compares it with the current section hash |
| section_snapshot_ref | String | Reference to snapshot file for generating diffs (e.g., "spec_v1_decomposed.md") |
| spec_subsection | String (optional) | `### ` subsection heading a task maps to, when its work is scoped to one subsection of a large `spec_section`. Enables subsection-level drift narrowing (DEC-021). Absent → drift uses `## `-level only (default). |
| subsection_fingerprint | String (optional) | SHA-256 of the `### ` subsection (from `fingerprint.py --sections --depth 3`) at decomposition. Paired with `spec_subsection`. |
| spec_unmapped | Boolean (optional) | `true` = in-spec work that belongs to no single spec section (cross-cutting infrastructure, a repo-wide sweep), so there is no section to drift from. Set instead of `spec_section` + `section_fingerprint`. Not the same as `out_of_spec` (work beyond the spec, which needs approval). See Drift Prevention Fields below |
| out_of_spec | Boolean | Task not aligned with spec (user chose "proceed anyway") |
| out_of_spec_rejected | Boolean | Task rejected during out-of-spec review (archived, preserved for audit) |
| rejection_reason | String | User's reason for rejecting an out-of-spec task (optional) |
| absorbed_into | String | Task ID this task was absorbed into (required when status is "Absorbed") |
| phase | String | Phase identifier this task belongs to (e.g., "1", "2"). Tasks in Phase N+1 are blocked until all Phase N tasks complete, unless the task has `cross_phase: true` (see below). |
| phase_name | String | Descriptive name for the phase (e.g., "Core Infrastructure", "Validation and Hardening"). Used in dashboard rendering as "Phase {phase} — {phase_name}". |
| decision_dependencies | Array | Decision IDs that block this task (e.g., ["DEC-002"]). Task remains blocked until all referenced decisions are resolved. A `recorded` (agent-recorded) decision counts as resolved, and its id is never added here. |
| decisions_pending | Array (optional) | **Transient.** Significant choices implement-agent (or the orchestrator, for inline work) made on this task, held until verification passes. Each element has the shape of an implement-agent `decisions_to_record[]` entry (`title`, `summary`, `options_considered`, `selected_option`, `rationale`, `related_task_ids`; inline work adds `decided_by: "orchestrator"`). Set by `/work` after each implement return, replacing any earlier value (removed when the set is empty); removed when `/work` writes the task's `recorded` decision record as the task becomes Finished. See `work-procedures.md § "State Persistence Protocol"` ("Hold decisions", "Persist decisions"). |
| parallel_safe | Boolean | When true, task is eligible for parallel execution even with empty `files_affected`. Use for research/analysis tasks with no file side effects. |
| cross_phase | Boolean | When true, task is exempt from the phase gate — eligible when its `dependencies`/`decision_dependencies` are met, regardless of prior phase completion. Phase membership is unchanged (task still belongs to its declared phase for verification and dashboard rendering). Use for long-lead work (procurement, recruitment, approvals) that must start before prior phase is fully done. Default: false. |
| conflict_note | String | **Transient.** Set during parallel dispatch when a task is held back due to file conflicts (e.g., `"Held: file conflict with Task 3 on src/models.py"`). Cleared when the task is dispatched or during post-parallel cleanup. Surfaced in the dashboard Status column. |
| recovery_state | String | **Transient.** Set by `/work` Step 0 when auto-recovering a stuck task. Values: `"verification_retry"` (respawning verify-agent), `"agent_retry"` (user chose to retry after timeout). Cleared after recovery completes. Prevents double-recovery if `/work` runs again before recovery finishes. |
| user_review_pending | Boolean | Set to `true` by `/work` (from verify-agent's report) when a `both`-owned task passes verification, OR when any task has a `test_protocol` (runtime validation was partial, human testing needed). Keeps the task visible for user action until the user runs `/work complete {id}` or completes guided testing. Cleared by `/work complete`. |
| verification_attempts | Number | Count of per-task verification attempts (incremented by the `/work` orchestrator when a dispatched verify-agent returns, per DEC-004; a delta re-check by a resumed verifier is recorded in `verification_history` but not counted here and never escalates). Escalates to human review at >= 3 (initial + 2 retries). Default: 0 (omit until first verification). Reset to 0, in the write that reopens it, whenever a task that had passed is sent back: by drift reconciliation's `[A]` and `[V]`, by a change after the pass or a post-verify delta (`work-procedures.md § "State Persistence Protocol"`, "Post-verify delta", "Reopening resets the counter"), and by a failed guided test (`work-user-flows.md`, "After guided testing"). A delta re-check that passes sets it back to the attempt number of the pass it follows. `verification_history` keeps the earlier record. |
| drift_reverify | Object (optional) | `{"section": "<heading>", "date": "YYYY-MM-DD"}`. Set by drift reconciliation's `[V]` on each Finished task it sends to Awaiting Verification. While present, every per-task verify dispatch for the task adds the line `Re-verification after a spec edit: the implementation is unchanged; check it against the current section text.` Removed when a per-task verification result is written for the task, pass or fail, or when the task goes back to Pending or In Progress for rework (the implementation then changes). A timeout keeps it for the retry. See `drift-reconciliation.md § "Granular Reconciliation UI"`. |
| verification_history | Array | Append-only log of all verification attempts (pass and fail). Each entry records attempt number, result, checks, issues, and notes. Coexists with `task_verification` (which stays as the latest result for quick checks). See Verification History section below. |
| task_verification | Object | Per-task verification result (verify-agent's report, recorded by `/work`) |
| test_protocol | Object | Structured testing steps for human-guided verification. Produced by verify-agent (written to the task by `/work`) when runtime validation is `"partial"` or task needs human testing. See Test Protocol section below. |
| interaction_hint | String | `"cli_direct"` or `"dashboard"`. Determines how `/work` presents the task to the user. CLI-direct tasks are presented immediately in the conversation; dashboard tasks appear in "Your Tasks". Default when absent: `"dashboard"`. |
| resolves_friction | Array | `FR-NNN` ids of the friction-register entries this task was created to fix. When the task is Finished with no user review pending, `/work` closes the listed entries that are still open. See Resolves Friction Field below |

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

These fields track spec-to-task alignment. They are set when a task is created (the creation contract below) and used by `/work` for drift detection (see `drift-reconciliation.md`).

### Creation contract

Every new task file carries one of these three from the moment it is written, whoever creates it and by whatever path (decomposition, `/breakdown`, a phase-level fix task, a follow-up from an agent report, a user request, a reconsidered decision, a friction fix, or any other):

- **Section provenance** (the task implements part of one spec section): `spec_section` + `section_fingerprint`, with `spec_version` and `spec_fingerprint`. Get all four from `python3 .claude/scripts/fingerprint.py --provenance .claude --section "<heading>"` (read-only), which prints
  ```json
  {"spec_version": "spec_v3", "spec_fingerprint": "sha256:…", "spec_section": "## Authentication", "section_fingerprint": "sha256:…"}
  ```
  and merge them into the task. `spec_section` comes back as the real current heading, so write that, not the value you passed. A `### ` heading that occurs once in the spec gives that subsection's hash. Exit 1 (`error: no current spec heading matches '<value>'`) means the value is not a real heading: pick a real one (the spec index lists them) and run it again. Never write a free-form value such as `§ 4.2 + § 4.6`; the drift check can't match it. Exit 2 is a usage error or a missing current spec. Without the script, copy the heading line from the spec and hash the section per `drift-reconciliation.md § "Spec Drift Detection"` (hash computation).
- **`spec_unmapped: true`** (in-spec work that belongs to no single section): no `spec_section` and no `section_fingerprint`. Set `spec_version` to the current spec's stem by hand.
- **`out_of_spec: true`** (work beyond the spec): `workflow.md § "Out-of-Spec Task Handling"`.

`section_snapshot_ref` is set by decomposition and copied by `/breakdown`; other paths leave it out, and reconciliation then has no snapshot to diff against (`drift-reconciliation.md` "Diff baseline" says what it shows). Each creation path names this contract and adds only what is specific to it (where the heading comes from).

### How the drift check uses the fields

The fields `spec_fingerprint`, `spec_version`, `spec_section`, `section_fingerprint`, and `section_snapshot_ref` are defined in the Field Definitions table above. Together they enable granular per-section drift detection. On every run, `/work` Step 1b runs `fingerprint.py --drift .claude`, which compares each task's `section_fingerprint` with the current hash of the section its `spec_section` names, and flags only tasks whose section changed. How the check uses each field:

- **`spec_section`** is matched against the current `## ` headings, ignoring surrounding whitespace and a missing `## ` prefix. A value starting with `### ` (subsection-level provenance) matches only a `### ` heading that occurs exactly once in the spec, and is compared with that subsection's hash. If nothing matches, an unfinished task is reported as `missing` (usually a renamed or deleted section) and goes through the `[D]` Delete / `[O]` Keep as out-of-spec / `[R]` Reassign prompt. A Finished task only adds to an `unmatched` count, because its work shipped and its provenance is historical or free-form.
- **Missing vs unmapped:** a task without `spec_section` or `section_fingerprint` is never flagged. With `spec_unmapped: true` it is counted in `unmapped`: it says it has no section, and nothing is owed. Without that flag it is counted in `no_provenance`: the provenance is missing, so no edit to its section can be detected. Tasks created before the creation contract (v5.13.0) are the usual case. `validate-tasks.py` lists them (`provenance_warnings`), and `/health-check` Part 1 check 11 offers a one-time baseline that stamps them from the spec's git history (`fingerprint.py --baseline`). `spec_unmapped: true` on a task that has both fields changes nothing: the task is checked like any other, and `validate-tasks.py` warns about the contradiction.
- **`spec_version`** naming an older spec makes a Finished task historical: it was verified against that version, Task Migration leaves its provenance unchanged by design, and the check skips it. A task in any other status on an older version is reported as `unmigrated` and goes through Task Migration. A missing `spec_version` counts as current, and so do the bare number and `v{N}` forms (`3` or `v3` for `spec_v3`).
- **`spec_fingerprint`** (whole spec) plays no part in the check. Reconciliation refreshes it along with the section fingerprints.
- **`section_snapshot_ref`** only feeds the diff shown at reconciliation. A missing snapshot doesn't affect detection; the prompt then diffs against the commit a `[BASELINE]` note names, or shows the current section text.

Absorbed, Broken Down and out-of-spec (`out_of_spec: true`) tasks are skipped and counted nowhere: a Broken Down task's subtasks carry the provenance (`/breakdown` copies it), and an out-of-spec task has no spec section to drift from. Marking a task out-of-spec (`[O]` at reconciliation) only sets that flag; its provenance fields stay. Full rules and output: `drift-reconciliation.md`.

The optional `spec_subsection` + `subsection_fingerprint` add a finer tier (DEC-021). When a task's `## ` section changed but the current hash of its own `### ` subsection (looked up within that `## ` section only) still equals its `subsection_fingerprint`, the drift check marks it `subsection_unchanged: true`. It is then shown as "likely unaffected (subsection unchanged)", never dropped, which spares tasks in untouched subsections of a large section. Tasks without both fields are flagged at `## ` level (no regression). See `drift-reconciliation.md § "Subsection-level drift narrowing"`.

The `out_of_spec` and `out_of_spec_rejected` fields mark tasks outside the spec scope. See `workflow.md` § "Out-of-Spec Task Handling" for behavior rules.

## Task Verification Field

Per-task verification result: verify-agent's report, recorded by `/work` when a task is in "Awaiting Verification" status. Upon passing, the task status transitions to "Finished". This enables Tier 1 (per-task) verification in the two-tier verification system.

```json
{
  "task_verification": {
    "result": "pass",
    "timestamp": "2026-01-28T15:30:00Z",
    "checks": {
      "files_exist": "pass",
      "consistency_check": "pass",
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
| `checks` | Object | Keys: `files_exist`, `consistency_check`, `spec_alignment`, `output_quality`, `runtime_validation`, `integration_ready`, `scope_validation` | Per-check pass/fail |
| `checks.*` | String | `"pass"`, `"fail"`, `"partial"`, `"not_applicable"`, or `"skipped"` | Individual check result. Most checks use `"pass"`/`"fail"`. `runtime_validation` additionally uses `"partial"` (some checks need human eyes), `"not_applicable"` (non-runnable output), and `"skipped"` (turn budget exceeded). |
| `checks.self_attested` | String | `"pass"` | Present only on human-owned tasks. Indicates the user attested to completion via `/work complete`. When present, the standard 7 checks are absent. |
| `issues` | Array | Issue objects `{severity, description}` | Issues found during verification |
| `notes` | String | Free text | Brief summary of verification |
| `evidence` | Array | Evidence objects (optional) | Empirical artifacts backing the result on runtime-validatable tasks — written by the orchestrator's Empirical Evidence Gate. See Evidence Sub-field below |

**Human task self-attestation:** When `/work complete` is run for an `owner: "human"` task that has no existing `task_verification`, a self-attestation record is auto-generated with `checks: { "self_attested": "pass" }`. This satisfies the structural invariant (every Finished task has `task_verification.result == "pass"`) without spawning verify-agent. The standard 7-check suite does not apply to human tasks since there is no Claude-produced implementation to verify.

### Evidence Sub-field

Optional `task_verification.evidence[]` — empirical artifacts backing a pass on tasks whose failure mode is runtime-observable. Written by the **orchestrator** (not verify-agent — subagents lack reliable browser-MCP access); verify-agent *names* the assertions to run via `empirical_assertions[]` in its report (`verify-agent.md § Step T4b` item 5). Populated by the Empirical Evidence Gate in `commands/work.md § "If Verifying (Per-Task)"`.

```json
{
  "evidence": [
    {"type": "http_status", "target": "/outfits", "assertion": "GET returns 200", "observed": "200", "result": "pass"},
    {"type": "computed_style", "target": ".score-pill", "assertion": "font-variant-numeric is tabular-nums", "observed": "tabular-nums", "result": "pass"},
    {"type": "build", "target": "npm run build", "assertion": "production build exits 0", "observed": "exit 0", "result": "pass"}
  ]
}
```

| Field | Values |
|-------|--------|
| `type` | `"http_status"` \| `"console"` \| `"computed_style"` \| `"geometry"` \| `"screenshot"` \| `"build"` |
| `target` | Route, selector, command, or artifact the assertion addresses |
| `assertion` | The falsifiable expectation — measured-value phrasing per `commands/diagnose.md § "Visual / browser-rendering bugs"` |
| `observed` | What was actually measured |
| `result` | `"pass"` \| `"fail"` |

**When expected:** web-UI tasks with `runtime_validation` `"partial"` (or `"pass"` reached without browser measurement) in projects with a web framework — a pass on such tasks without `evidence[]` is incomplete; the gate runs before `result: "pass"` is persisted. Optional everywhere else (back-compat: absent field is valid).

### State Detection

A task "needs per-task verification" when:
- It has status "Awaiting Verification", OR
- It has status "Finished" AND does NOT have a `task_verification` field (legacy edge case — human tasks auto-generate `self_attested` verification via `/work complete`, so this state is rare)

### Failure Handling

When per-task verification fails:
- `verification_attempts` is incremented (the orchestrator increments this before writing verify-agent's result)
- The attempt is appended to `verification_history` (structured record of all attempts, including passes — see Verification History section)
- Task status is set back to "In Progress"
- Verification failure notes are prepended with `[VERIFICATION FAIL #{N}]` in the task `notes` field (where N = current attempt count)
- `completion_date` is cleared
- `updated_date` is updated
- Dashboard is regenerated
- **Escalation rule:** When `verification_attempts >= 3` (initial attempt + 2 re-attempts), set status to "Blocked" with note `[VERIFICATION ESCALATED] 3 attempts exhausted — requires human review` instead of retrying

### Drift Reconciliation Notes

When the user reconciles a changed spec section (`drift-reconciliation.md § "Granular Reconciliation UI"`), these options prepend a dated note to `notes`:

- `[DRIFT RE-VERIFY {YYYY-MM-DD}] {section} changed; re-verifying against the current text` (`[V]` Re-verify), on the section's Finished tasks. A Finished task not owned by `human` goes back to Awaiting Verification with `task_verification` cleared and `verification_attempts` reset to 0 (`verification_history` keeps the earlier attempts), and is re-verified without a rebuild. `[V]` also sets `drift_reverify` on it, which tells verify-agent the implementation is unchanged and is removed once the re-verification result is written. A Finished `owner: human` task stays Finished with `user_review_pending: true`.
- `[DRIFT UPDATED {YYYY-MM-DD}] {section} changed; {what changed in the task, or "no task change needed"}` (`[A]` Apply and `[V]` Re-verify), on the section's open tasks. Claude updates the task's description or acceptance criteria where the new section text changes them; status doesn't change.
- `[DRIFT KEPT {YYYY-MM-DD}] {section} changed; user kept verification: {one-line reason}` (`[K]` Keep), on every task in the section. Status and `task_verification` don't change. For a Finished task, this note is the record that its verification predates the current section text.

The provenance baseline (`fingerprint.py --baseline --write`, `/health-check` Part 1 check 11) prepends one of:

- `[BASELINE] section_fingerprint stamped from the spec at {sha} ({commit date}); the task records no hash of its own.` Reconciliation diffs a snapshot-less task against `{sha}`.
- `[BASELINE] section_fingerprint set to the current section text on {YYYY-MM-DD}, confirmed by the user as what the task was built against.` or `…, accepted by the user as the task's baseline.` (the task is older than the spec's history for its section).

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
        "consistency_check": "pass",
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
        "consistency_check": "pass",
        "spec_alignment": "pass",
        "output_quality": "pass",
        "runtime_validation": "not_applicable",
        "integration_ready": "pass",
        "scope_validation": "pass"
      },
      "issues": [],
      "notes": "All 4 tables implemented correctly",
      "cost": {"total_tokens": 48210, "tool_uses": 17, "duration_ms": 94000}
    }
  ]
}
```

#### Sub-fields

| Sub-field | Type | Description |
|-----------|------|-------------|
| `attempt` | Number | Attempt number: the value `verification_attempts` is incremented to when the entry is recorded. A `delta` entry is the exception: it repeats the attempt number of the pass it follows (the counter itself is 0 while a delta is out). Not unique: delta entries repeat a number and numbers restart whenever the counter is reset, so identify an entry by `attempt` and `timestamp` together |
| `result` | String | `"pass"` or `"fail"` |
| `timestamp` | String | ISO 8601 timestamp of when this attempt completed |
| `checks` | Object | Per-check pass/fail (same keys as `task_verification.checks`) |
| `issues` | Array | Issues found during this attempt |
| `notes` | String | Brief summary of this attempt's findings |
| `cost` | Object | Optional. The verify-agent dispatch's usage as reported by the harness: `total_tokens` (reported as `subagent_tokens` or `total_tokens`), `tool_uses`, `duration_ms`. Omitted when the harness doesn't report it (and on entries written before v5.5.2). Measures what per-task verification costs, by difficulty. When the usage arrives after the report (in the completion notification), the orchestrator adds it then, to the entry with the same `attempt` and `timestamp` |
| `delta` | Boolean | Optional. `true` on an entry made by resuming the verifier that had just passed the task, to re-check a small follow-up edit (`work-procedures.md § "State Persistence Protocol"`, "Post-verify delta"). Absent on every fresh dispatch. A delta entry, pass or fail, does not increment `verification_attempts` (its `attempt` repeats the attempt number of the pass it follows, and a delta pass sets the counter back to that number) and never triggers escalation; a refused or unusable delta re-check writes no entry. A fresh verification that follows a delta starts from a counter reset to 0. A delta entry's `cost` covers only the resumed turn, so counts and medians of per-task verification cost (the DEC-025 recheck) exclude entries with `delta: true` |

#### Behavior Rules

- **Append-only** — never modify or remove previous entries. One exception: a late-arriving `cost` is added to the entry it belongs to
- **Includes passing result** — the final passing attempt is recorded in both `verification_history` and `task_verification`
- **Coexists with `task_verification`** — `task_verification` remains the latest result for quick status checks; `verification_history` provides the full trail
- **Created on first verification** — array is created when verify-agent runs Step T6 for the first time on a task

### Verification Debt

Tasks that bypass verification create "verification debt" — Finished tasks without `task_verification`, with a failing result, or with critical issues. Debt is tracked in the dashboard under "Action Required" → "Verification Debt", blocks project completion, and is enforced by both `/work` (routing) and `/health-check` (ERROR level).

## Test Protocol Field

Produced by verify-agent (written to the task by `/work`) when runtime validation is `"partial"` or the task needs human-guided testing. Provides structured steps for the user to walk through, typically presented via the guided testing flow in `/work` when `interaction_hint` is `"cli_direct"`.

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

### Runtime Constraints

When a test_protocol step exercises behavior not runnable under the project's primary runtime (e.g., Expo Go can't cold-launch offline because it fetches its JS bundle from Metro on every cold-launch), the step should be either substituted (background-mode / server-only-kill) or annotated as deferred. Steps can carry an optional `constraint` informational field (e.g., `"constraint": "Requires dev client (EAS); skip in Expo Go"`) that verify-agent surfaces during guided testing. See `.claude/support/reference/decomposition.md § Test-Protocol Runtime Constraints` for authoring guidance.

## Interaction Hint Field

Determines how `/work` presents human-involved tasks. Set by verify-agent during Step T7 based on the nature of the required interaction.

| Value | Behavior |
|-------|----------|
| `"cli_direct"` | Task presented immediately in the CLI conversation. Used for synchronous testing, quick confirmations, command-guided walkthroughs. |
| `"dashboard"` | Task appears in dashboard "Your Tasks" / Action Required. Used for async review, extended reading, batch decisions. |

**Default:** When absent, defaults to `"dashboard"` (preserves current behavior). Existing tasks without this field are unaffected.

**Set by:** Verify-agent Step T7, based on Step T4b runtime validation results and task characteristics.

**Overridable:** Users can always use `/work complete {id}` from the dashboard flow regardless of the hint.

## Resolves Friction Field

Optional `resolves_friction`: the entries in the friction register (`.claude/support/friction.jsonl`, `FR-NNN` ids) this task was created to fix.

```json
{ "resolves_friction": ["FR-012", "FR-013"] }
```

**Set by** whoever creates the task, when creating it or at the latest before it is verified: e.g. a task filed from an audit finding, a review, or a user request that cites FR ids. List only entries the task fixes; citing an entry in `notes`, or having raised it, closes nothing.

**Effect:** when the task is Finished with no user review pending (a per-task verify pass without `user_review_pending`; `/work complete`, which also completes a pending review; or parent auto-completion once no subtask has a review pending), `/work` closes each listed entry that is `open`: `status: "resolved"`, `resolved_by: {"kind": "task", "ref": "<task id>", "at": "<ISO timestamp>"}`, per `friction-register.md § "Status update protocol"`. Ids not in the register, and entries already `resolved` or `dismissed`, are skipped. A `both`-owned task whose guided test is still pending closes nothing until `/work complete`.

## Completion Notes Contract

The `notes` field serves as structured completion notes for context transfer between implement-agent and verify-agent.

**Purpose:** When implement-agent completes a task, it writes completion notes that verify-agent reads to understand what was done — without carrying the full implementation conversation.

**Newest first; each write prepends.** Every `notes` write (implement-agent's report, inline work, `/work complete`, `/breakdown`, verification and drift notes) is prepended to the existing `notes` and never replaces them (`work-procedures.md § "State Persistence Protocol"`), so a re-implementation keeps the `[VERIFICATION FAIL #N]` trail the verifier reads.

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
- Are set by the `/work` orchestrator after implement-agent returns its structured report with `implementation_status: "completed"` (see DEC-004)

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
├── dashboard.html        # Auto-generated summary (HTML, gitignored)
└── tasks/
    ├── task-*.json       # Active tasks
    └── archive/
        ├── task-*.json       # Archived task files
        └── archive-index.json # Lightweight summary
```

### Auto-Archive Behavior

When active task count exceeds 100, `/work` automatically:
1. Identifies finished tasks older than 7 days, excluding any with `user_review_pending: true` (an open review stays on the card)
2. Moves them to `.claude/tasks/archive/`
3. Updates archive-index.json

Archived tasks remain available for reference but don't clutter the dashboard.
