# /work Procedures

Deferred procedures extracted verbatim from `commands/work.md` in v4.18.0 (Plan 2 P3 — the orchestrator file had grown past reliable single-pass size; ~20 ship-log patches trace to prose procedures skipped under load). `work.md` keeps STOP-gated stubs under the same section names; this file is the canonical body. Read the section the stub names AT the moment the stub fires — once read, it stays in context for the session.

## State Persistence Protocol

After any agent (implement-agent or verify-agent) returns a structured report, the orchestrator is responsible for all state transitions, JSON persistence, and dashboard updates. Agents cannot write to `.claude/` paths — this is enforced by the Claude Code harness (see DEC-004). Follow this protocol precisely to preserve the atomic implement→verify contract.

**Schemas:** The two agent return schemas are defined in `.claude/agents/implement-agent.md` § "Step 6: Return Structured Report" and `.claude/agents/verify-agent.md` § "Step T6: Construct Verification Report" (per-task) + § "Step 7: Include Verification Result in Report" (phase-level).

**After implement-agent returns:**

1. **Status transition** based on `implementation_status`:
   - `completed`: write `{ "status": "Awaiting Verification", "completion_date": report.completion_date, "updated_date": today, "notes": report.notes }` to task JSON
   - `partial`: leave status "In Progress"; prepend `[PARTIAL]` to notes
   - `partial_resume_pending` (per DEC-010): leave status "In Progress"; write `{ "partial_completion": report.partial_completion, "updated_date": today, "notes": "[PARTIAL_RESUME_PENDING] " + report.notes }` to task JSON. Surface inline: `Task {id} returned partial — resume scheduled. Confidence: {confidence}. Run /work again to re-dispatch.` Do NOT dispatch verify-agent — verification is gated on `completed`.
   - `blocked`: write `{ "status": "Blocked", "notes": "...", "updated_date": today }`; surface `issues_discovered[]` to user
   - `misaligned`: do not advance status; route to spec-alignment flow with `issues_discovered[]` context

2. **Append friction markers (DEC-011 Option ABp + audit register).** For each marker in `report.friction_markers`, add `task_id: report.task_id` and **dual-write the marker as a JSON line to BOTH** `.claude/support/workspace/.pending-markers.jsonl` (transient buffer; survives abrupt termination) **AND** `.claude/support/workspace/.session-log.jsonl` (canonical log; consumed by PreCompact + Track 1 export). Append immediately within this step — **do NOT defer to `/work pause` or batch across multiple agent returns**. Markers between an agent return and the next sync point are at risk of permanent loss if the session terminates abruptly; the dual-write narrows that loss window to sub-second.

   - Pending-buffer write is append-only: open in append mode, write `{...}\n`, close. No read-modify-write cycle.
   - Session-log write also appends. If file doesn't exist, create it.
   - The next `/work` invocation (or PreCompact hook) will reconcile the two files via the catchup procedure in work.md § "Step 0d: Friction-Marker Catchup".
   - If `report.friction_markers` is empty, this step is a no-op — skip all writes.

   **Friction register projection (audit-eligible kinds):** For each marker whose `type` is one of `vocab_drift`, `path_drift`, `design_contradiction`, `terminology_mismatch`, or `spec_implementation_gap`, ALSO append to `.claude/support/friction.jsonl` (the audit register — see `.claude/support/reference/friction-register.md`). The register entry has additional structure beyond the session-log raw marker:
   - `id`: assigned at append time. Read existing `friction.jsonl` (create if missing), find max existing `FR-NNN`, increment by 1 (zero-padded to 3 digits, starting at FR-001).
   - `captured`: ISO timestamp from the marker.
   - `captured_in`: `{"agent": "{agent_type}", "task": "{task_id}", "command": "/work"}`.
   - `kind`: copy from marker `type`.
   - `what`: copy from marker `details`.
   - `source_anchor`: copy from marker `source_anchor` (REQUIRED — if missing on an audit-eligible kind, log a warning and skip the register write; session-log write still happens).
   - `status`: `"open"`.

   Register write is append-only at insert time. Status updates (later, by `audit-coherence` or user dismissal) use a read-modify-write of the entire file keyed by `id` — see friction-register.md § "Status update protocol".

   **Script helper (advisory, FB-098).** The orchestrator MAY compute this entire step's payload with `python3 .claude/scripts/persist-friction.py` (markers as a JSON array on stdin). It reads the existing `friction.jsonl` — and any `--scan` paths (e.g. `.claude/tasks/`, the handoff, the dashboard) — and returns the dual-write `markers`, the `register` projection with **collision-safe `FR-NNN` ids** (one past the max of register ids AND textual `FR-<n>` references, which a naive max+1 misses — the flirty-gym FR-001 / styler FR-031 collisions), the `assigned_ids` to echo into task notes, and any `warnings` (e.g. an audit-eligible marker missing `source_anchor`). It is read-only — the orchestrator still performs the appends described above. The prose here remains the source of truth; if the script is absent or fails, follow it by hand, and keep the two in lockstep (`.claude/scripts/README.md § "Dual-location risk"`).

3. **Persist decisions:** for each entry in `report.decisions_to_record[]`, scan `.claude/support/decisions/decision-*.md` for the highest existing DEC-NNN, assign the next available ID (zero-padded to 3 digits), and Write a new `decision-NNN-{slug}.md` file using the template in `.claude/support/reference/decisions.md`. Populate the Selected/Rationale/Options sections from the report entry. Set frontmatter `status: approved`, `decided: today`, `decided_by: implement-agent`. Subagents cannot write under `.claude/`, so this step is the orchestrator's responsibility — implement-agent only generates content (DEC-004; `rules/agents.md § State Ownership`).

4. **Dashboard regeneration:** in sequential mode, regenerate `dashboard.html` per `.claude/support/reference/dashboard-regeneration.md` — newly persisted decisions surface in the Decisions section. In parallel mode, defer — handled at batch-end.

5. **For `completed` status:** dispatch verify-agent (see work.md § "If Verifying (Per-Task)") and then apply the "After verify-agent returns" protocol below.

**After verify-agent returns (per-task mode):**

1. **Read task's current `verification_attempts`** (default 0), compute `new_attempts = current + 1`
2. **Build `verification_history` entry** from report's `checks`, `issues`, `notes`, with `{"attempt": new_attempts, "result": report.result, "timestamp": report.timestamp}`. Append to task's `verification_history[]` array (create array if absent).
3. **Write `task_verification`** field to task JSON using report's `result`, `timestamp`, `checks`, `notes`, `issues` — plus `evidence[]` when the Empirical Evidence Gate ran (see work.md § "If Verifying (Per-Task)")
4. **Status transition** based on `result`:
   - `pass`: set `status: "Finished"`, `updated_date: today`. If `report.user_review_pending == true`, also write `user_review_pending: true`, `test_protocol: report.test_protocol`, `interaction_hint: report.interaction_hint`
   - `fail` AND `new_attempts < 3`: set `status: "In Progress"`, `updated_date: today`. Clear `completion_date`. Prepend `[VERIFICATION FAIL #{new_attempts}]` to notes with the fail summary
   - `fail` AND `new_attempts >= 3`: set `status: "Blocked"`, `updated_date: today`. Prepend `[VERIFICATION ESCALATED]` note — "3 attempts exhausted — requires human review"
5. **Timeout detection:** if verify-agent exhausted max_turns without returning a valid report, treat as fail: increment `verification_attempts`, set status to "Blocked", add `[VERIFICATION TIMEOUT]` note
6. **Append friction markers** from `report.friction_markers` (same as implement-agent)
7. **Parent auto-completion:** if task has `parent_task` and all siblings are now "Finished", set parent to "Finished"
8. **`files_affected` drift update (FB-086):** if `report.issues[]` contains a minor severity entry with the form "files_affected declared {N} files but implementation touched {M}" AND `report.friction_markers[]` includes a `verification_gap` marker with `template_area: "task-schema files_affected"`, update the task JSON's `files_affected` to match the union of declared and actually-touched files (excluding infrastructure paths filtered in verify-agent T2b step 3). This keeps Step 2c's parallel-batch heuristic accurate for future dispatches.
9. **Dashboard regeneration:** sequential mode — regenerate now; parallel mode — defer

**After verify-agent returns (phase-level mode):**

1. **Write `.claude/verification-result.json`** using the report's payload: `result`, `timestamp`, `spec_version`, `spec_fingerprint`, `summary`, `criteria_passed`, `criteria_failed`, `criteria`, `issues`, plus a `tasks_created[]` array populated with the IDs of task files you create in the next step
2. **Create fix task files:** for each entry in `report.fix_tasks_to_create[]`, write `task_{id}.json` with the entry's `task_json` payload plus `out_of_spec` flag
3. **Append friction markers**
4. **Regenerate dashboard** — include Verification Debt sub-section if debt exists; show out-of-spec tasks with ⚠️ prefix
5. **If result is `fail`:** loop back to Execute phase for fix tasks. If `pass`: proceed to "If Completing"

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
   - If the task has `owner: "both"` → close each half on its own track (FB-100):
     - **Claude's half** is verified the normal way. If `user_review_pending: true` (verify-agent already passed Claude's contribution and set the flag, per the State Persistence Protocol § "After verify-agent returns"), proceed — the user's completion attests their half.
     - If there is no `task_verification` yet and Claude's contribution was a **mechanical deliverable**, spawn verify-agent first (as in the next bullet), then let the user attest their half on the pass.
     - If Claude's contribution was a **lived/conversational gate** with nothing mechanical to verify, auto-generate the same `self_attested` block as `owner: "human"` above, with `"notes": "Both-owned task — Claude's contribution delivered in-session; user attested completion"`. This is the clean close for "lived gates where Claude's half is done" — no verify-agent round-trip needed. (Distinguish the two sub-cases from the task's deliverable expectations; when ambiguous, ask the user which applies rather than defaulting to verify-agent.)
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

   Ask for two clearly-separated kinds of notes so the user does not have to context-switch between project-focused and template-focused thinking. The two prompts run in sequence; each is independently skippable with Enter.

   **First prompt — Project notes (always shown):**

   ```
   Task {id}: "{title}" — any notes about the work itself? (Enter to skip)
   (decisions made, follow-ups, gotchas, anything worth remembering for this task)
   >
   ```

   - If non-empty: store in the task's `user_feedback` field
   - If empty: proceed without setting `user_feedback`

   **Second prompt — Template notes (shown only if `template_inbox_path` is configured in `.claude/version.json`):**

   ```
   Any notes about how Claude or the workflow handled this? (Enter to skip — bridges to template repo)
   (e.g. a step that felt off, an instruction that was unclear, something the template could do better)
   >
   ```

   - If non-empty: invoke the `/feedback template:` Mode 1 procedure with these notes as the capture body. Prepend a source line to the body so the template-side FB entry carries task context:
     ```
     Captured during /work complete on Task {id}: "{title}".

     [user's template notes]
     ```
     Mode 1 writes the local `FB-NNN` entry and, since `template_inbox_path` is set, writes the bridge export to the template inbox.
   - If empty: proceed without creating a template feedback item.

   **Why the conditional second prompt:** When `template_inbox_path` is unset, capturing template notes would create local-only FB entries in the downstream project that the user then has to carry over manually — the same friction the bridge was built to eliminate. Skipping the prompt when the bridge is disabled keeps the UX honest: we only ask the user to write template feedback when there is a destination for it.

   **Language principles for both prompts:**
   - Plain English only. Do not use template-internal terminology in user-facing prompt text (no "spec drift", "friction signal", "scope creep", "user_feedback signal", etc.).
   - Each label states what the prompt is for AND where the input lands. The user should not have to guess.
   - The two prompts are visually adjacent but clearly labeled — the user can tell at a glance which slot they are filling in.

   This is the PRIMARY feedback path for `/work complete`. Dashboard FEEDBACK markers remain as an ASYNC alternative for project notes — if the user wrote feedback in the dashboard before running `/work complete`, Step 4b captures it as fallback. (A template-side dashboard marker is not yet implemented; the second prompt is currently the only path for template notes during `/work complete`.)
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
9. **Auto-archive check** - If active task count > 100, archive old tasks (§ "Auto-Archive" below)
10. **Post-dispatch validation** - Run main `/work` Step 5 checks (task file integrity, dashboard exists, session sentinel)

### Rules

- Never work on "Broken Down", "On Hold", or "Absorbed" tasks directly
- Parent tasks auto-complete when all non-Absorbed subtasks finish
- Always add notes about what was actually done

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
