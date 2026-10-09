# Health Check

Combined system health check for tasks, decisions, instruction files, rules, and template sync.

## Usage
```
/health-check                    # Run all checks, collect fixes, one end-of-run triage prompt
/health-check --report           # Show issues only, no fix queue
```

## Purpose

Manual maintenance tool that validates tasks, decisions, instruction files (`.claude/CLAUDE.md`, `./CLAUDE.md`, `.claude/rules/`), and template sync. Operational checks for `/work` are defined inline in `work.md`.

---

## Fix Queue Protocol (collect, don't prompt)

Parts 1–7 NEVER prompt inline during the run. Every fixable issue becomes a **queued fix item**; the run ends with one consolidated triage table and a single response (see "Step 4: Batch Fix Triage"). One `/health-check` run = one fix prompt, regardless of how many parts found issues.

**Queue item shape:** `id` (sequential number in queue order) · `part` · `file` · one-line proposed fix (with diff stats where applicable) · `risk` flag.

**Risk flags:**
- `—` — safe to bundle: concrete fix, nothing locally-authored is lost (regen, add missing field, move entries between files, update a sync file that is an unchanged template copy, stamp section provenance from the spec's history).
- `⚠ overwrites local` — applying replaces locally-modified content: Part 5 "Locally modified" sync files (content that matches no template version of the path), `.claude/CLAUDE.md` revert (Part 2a). Excluded from bare `[A]`; explicit inclusion required.
- `⚠ deletes` — removes a file: Part 5 retired-template-file rows. Excluded from bare `[A]`; explicit inclusion required. The row says whether the file is an unchanged template copy (nothing local is lost) or locally modified (`[D]` shows the diff against the template's last version).
- `⚠ edits decision record` — changes the body of a decision record (Part 3 `## Selected` heading rename). Excluded from bare `[A]`; explicit inclusion required.
- `⚠ unreviewed append` — adds new ledger content the user hasn't read (Part 7 proposed FB entries). Excluded from bare `[A]`; review via `[D]` or include explicitly.
- `needs-input` — the fix can't be computed without an answer (which task to keep, a path, revert-vs-keep-vs-merge). The row carries the question and choices inline; resolved only by a per-item reply (`{id}: <answer>`). Bare `[A]` skips these; unresolved rows are reported as still-open, never silently dropped.

Where an auto-fix table entry says "Ask user: …", that question becomes the row's inline question — it does not become a mid-run prompt.

**Exceptions (still interactive):**
- **Part 8** (audit dispatch) keeps its menu — it gates expensive audit runs, not fixes.
- **Sub-flows of an explicitly included fix** — e.g., Part 2d's `[V]` verify pass adjudicates per-section diffs interactively once the user has included that row; the *offer* is batched, the flow's intrinsic judgments are not.
- **Part 5 Step 5** (commit offer) runs after the batch applies — it commits files, so it asks once.

With `--report`, skip the queue and table entirely (report only).

---

## Part 1: Task System Validation

Detects and fixes drift from task management standards.

### Validation Checks

#### 1. Task JSON Schema Validation

Validates required fields (id, title, status, difficulty) and optional fields per `.claude/support/reference/task-schema.md`. Boolean fields (`parallel_safe`, `out_of_spec`, `out_of_spec_rejected`, `spec_unmapped`, `cross_phase`, `user_review_pending`) must be booleans when present — flag non-boolean values as schema violations.

**Migration detection:** When non-conforming schemas are found (missing required fields, unknown status values, unexpected fields), provide migration guidance:
- Suggest field mappings (e.g., `"done"` → `"Finished"`, `"assignee"` → `"owner"`)
- List specific remediation steps per task
- Never auto-migrate — report issues and let the user decide

#### 2. Relationship Integrity

**Parent-subtask consistency:**
- If task has `parent_task`, parent must exist and list this task in `subtasks`
- If task has `subtasks`, each subtask must exist and reference this task as `parent_task`
- `"Broken Down"` status requires non-empty `subtasks` array
- Subtasks should not have `"Broken Down"` as status (only top-level)

**Dependency validity:**
- All task IDs in `dependencies` array must exist
- No circular dependencies

**Absorbed reference validity:**
- If task has `absorbed_into`, the referenced task ID must exist and must not itself be Absorbed (no absorption chains)

#### 3. ID Safety (Breakdown Protection)

When breaking down tasks, IDs must not collide:
- Subtask IDs use format `{parent_id}_{n}` (e.g., `5_1`, `5_2`, `5_3`)
- Check for ID uniqueness across all task files
- Verify no orphaned task files exist

#### 4. Dashboard Presence and META

The dashboard is derived and gitignored (DEC-024): `dashboard-render.py --html` renders it whole from task JSON, decision records and the sidecar, so there are no rows or sections to reconcile.

- **Presence:** with no `task-*.json` yet, `.claude/dashboard.html` may be absent (the first `/work` after decomposition generates it). Tasks exist but no file (e.g. a fresh clone): ⚠️.
- **META parses:** the `<!-- DASHBOARD META` … `-->` comment holds one `key: value` per line, with the same keys as the META of a fresh `dashboard-render.py --html` run (currently the 15 in `dashboard-regeneration.md § "4. Compute and Add Metadata Block"`). Missing or extra keys (e.g. `session_*`): ⚠️. If regenerating doesn't clear a mismatch, that list is stale. Check 10 compares the values; Part 6 check 1 covers placement in `<head>` and the offline invariant.
- **Legacy `.claude/dashboard.md`:** present → the pre-DEC-024 dashboard was never migrated: ⚠️. Regenerating migrates it first (`dashboard-regeneration.md` Step 2c), as `/work` Step 1a does.

For any of these, the fix is always: regenerate.

#### 4b. Dashboard State Sidecar

- `.claude/dashboard-state.json` should exist if dashboard.html exists
- If missing: WARNING — "Dashboard state sidecar missing. Next dashboard regeneration will create it."
- If present: validate JSON structure (required keys: user_notes, section_toggles, phase_gates, inline_feedback, custom_views_instructions, updated)
- The sidecar is the **single source** for user content (DEC-024) — the read-only HTML has no in-file markers to cross-reference. Validate the sidecar's own consistency only (e.g., `phase_gates` statuses are `active`/`approved`)
- `section_toggles` keys are among the four the renderer reads: `action_required`, `decisions`, `notes`, `custom_views`. It silently ignores any other key (e.g. `progress`, `tasks` from older first-regeneration defaults): ℹ️
- `decisions: false` while decision records exist (likely the pre-v5.7.5 first-regen default): ℹ️ — the Decisions card stays hidden until the user sets it `true`
- `augment_rows` (optional, FB-118) is a list of objects, each with a non-blank string `text` (schema: `dashboard-regeneration.md § "Dashboard State Sidecar"`). A non-list value (ignored), or an item that isn't an object or lacks such a `text` (skipped): ℹ️. A `kind` that isn't `action` or `fyi` (any case): ℹ️ — it renders as an action row
- These are report-only, with no fix row: the toggles are the user's to change, and judgment rows are the orchestrator's to rewrite

#### 5. Status Rules

| Status | Rules |
|--------|-------|
| `Pending` | No special requirements |
| `In Progress` | Multiple allowed only when parallel-eligible: `files_affected` don't overlap, all deps satisfied, within `max_parallel_tasks` limit. **ERROR** if parallel conditions violated. (The browser and the build are shared too; that rule is `parallel-execution.md § "Single-Instance Resources"` and isn't checked here.) |
| `Awaiting Verification` | Transitional only — must proceed to verification immediately. Auto-recovered by `/work` Step 0. |
| `Blocked` | Should have `notes` explaining the blocker |
| `On Hold` | Should have `notes` explaining why paused. Not auto-routed by `/work`. Warning if on hold > 30 days. |
| `Absorbed` | Must have `absorbed_into` field referencing a valid task ID that exists. |
| `Broken Down` | Must have non-empty `subtasks` array |
| `Finished` | MUST have `task_verification.result` of "pass". If has subtasks, all subtasks must also be `Finished` |

#### 6. Difficulty Range

- Must be integer 1-10
- Tasks with difficulty >= 7 should be `"Broken Down"` or have subtasks
- Subtasks should have difficulty <= 6

#### 7. Workflow Compliance

Detects tasks that may have bypassed the implement-agent or verify-agent workflows.

**Verification debt (ERRORS):**
- Finished tasks MUST have a `task_verification` field with `result` of `"pass"`
- `task_verification.checks` should have all 7 keys (`files_exist`, `consistency_check`, `spec_alignment`, `output_quality`, `runtime_validation`, `integration_ready`, `scope_validation`) with pass/fail values (or `"skipped"` only when result is `"fail"` due to timeout). Note: `runtime_validation` additionally allows `"not_applicable"` and `"partial"` as valid non-error values. **Exceptions:** (a) tasks with `owner: "human"` that have `checks.self_attested: "pass"` are exempt — human tasks use self-attestation instead of the standard checks. (b) Parent tasks (status `"Broken Down"` with non-empty `subtasks`, OR `"Finished"` with non-empty `subtasks` where every subtask is itself `"Finished"` with passing per-task verification) that have `checks.aggregate_subtask_verification: "pass"` are exempt — verification aggregates from subtasks (per FB-074).
- If any check is `"fail"`, the overall `result` must also be `"fail"` — a check-level fail with a result-level pass is invalid
- If any finished task lacks `task_verification`: **ERROR** — "Verification debt: N finished tasks missing verification"
- If any finished task has `task_verification.result == "fail"`: **ERROR**

**Verification debt calculation:**
```
verification_debt = count of tasks where:
  - status == "Finished" AND (
    - task_verification does not exist, OR
    - task_verification.result == "fail", OR
    - task_verification.result != "pass"
  )
```

**Workflow bypass detection (warnings):**
- Finished tasks with empty `notes` (no implementation report persisted — possible bypass of implement-agent)
- Tasks that appear to have jumped from `"Pending"` to `"Finished"` without passing through `"In Progress"` and `"Awaiting Verification"`

**Completion gate checks (ERRORS):**
- If every non-Absorbed task is Finished (the dashboard's completion ring at 100%):
  - `.claude/verification-result.json` MUST exist with `result` of "pass"
  - ALL finished tasks MUST have passing `task_verification`
  - If either condition fails: ERROR — "Project marked complete without verification"
- Check for status mismatch: spec says "active" but every non-Absorbed task is Finished (or vice versa)

**Note:** Workflow bypass warnings are informational. Some tasks may legitimately have brief notes. The intent is to surface patterns, not block individual tasks.

**Acceptance-status authority (DEC-022):** `.claude/verification-result.json`'s `criteria[]` (rendered as the dashboard's Acceptance-criteria section) is the authoritative surface for "phase acceptance criteria met." If a project also renders acceptance criteria as inline `- [ ]` boxes in the spec, those are authored input, not live status — do not treat unticked spec boxes as a completion failure. `/audit-coherence`'s `acceptance-reconciliation` lens surfaces box-vs-`criteria[]` divergence advisorily.

**Script alternative:** `.claude/scripts/validate-tasks.py .claude/tasks` runs schema + verification-debt checks deterministically and prints a combined report. `--json` flag emits structured output for downstream consumption. It also lists tasks without section provenance (`provenance_warnings`, never an error; check 11 acts on them).

#### 8. Workspace Staleness

**Stale Workspace Files:**
- Files in `.claude/support/workspace/` older than 30 days
- Warning: "N workspace files are over 30 days old"

#### 9. Out-of-Spec Task Tracking

Reports tasks with `"out_of_spec": true` in a separate section of the report. Informational — out-of-spec tasks are valid but won't be verified against spec acceptance criteria.

#### 10. Dashboard Staleness

**Task state hash check:**
1. Compute: `python3 .claude/scripts/dashboard-render.py --task-hash` — the canonical convention (sha256 over sorted `id:status:difficulty:owner:review` rows, `review` = `1` when `user_review_pending` is true else `0`, newline-joined + trailing newline). Hand-compute only when the script is unavailable. Do NOT use `fingerprint.py --dashboard-rollup` (different algorithm). A dashboard rendered before the `review` field (FB-118) reads stale once; regenerating clears it.
2. Read dashboard metadata block (if exists)
3. Compare hashes — if different, dashboard is stale
4. Compare META `spec_fingerprint` with the current spec hash (`python3 .claude/scripts/fingerprint.py --spec .claude/spec_v{N}.md`, which hashes the file's bytes) — if different, dashboard is stale (the same check as `/work` Step 1a)

**Format staleness check:**
1. Read `template_version` from dashboard `<!-- DASHBOARD META -->` block
2. Read `template_version` from `.claude/version.json`
3. If they differ (or META field is absent), dashboard is format-stale
4. Report: "Dashboard generated with template {old} but current template is {new} — regenerate to apply format updates"

A dashboard can be content-stale (task hash or spec hash mismatch), format-stale (template_version mismatch), or both. Either condition triggers regeneration in auto-fix.

**Stale "In Progress" tasks:**
- Tasks with status `"In Progress"` where `updated_date` (or `created_date`) is > 7 days old
- Indicates abandoned work or forgotten state updates

#### 11. Provenance Integrity

**Snapshot file existence:**
- For each task with `section_snapshot_ref`, verify the referenced file exists at `.claude/support/previous_specifications/{section_snapshot_ref}`
- Missing snapshot: WARNING — "Task {id} references snapshot `{ref}` which does not exist. Drift is still detected (that compares section fingerprints), but reconciliation can't show a diff for this task's section; it shows the current section text instead."

**Decision dependency format:**
- For each task with `decision_dependencies`, verify each entry matches pattern `DEC-\d+`
- Invalid format: ERROR — "Task {id} has malformed decision dependency `{value}`"

**Section provenance baseline (FB-135):**

Tasks created before v5.13.0 outside decomposition often carry no `section_fingerprint`, so the drift check counts them in `no_provenance` and can't see an edit to their section. Run `python3 .claude/scripts/fingerprint.py --baseline .claude` (read-only). It proposes one `action` per such task (`tasks[]`) and totals them in `counts`; tasks with `spec_unmapped: true` are not listed. Report the four counts, taken from this output and not from `validate-tasks.py`'s `provenance_warnings` (that list also holds tasks of an older spec version, which the drift check treats as historical). All zero: `✓`, nothing queued. Only `report_only` above zero: `✓` with the `ℹ️` line below, nothing queued. `spec: null` (no current spec): skip this sub-check.

The script stamps from the spec's git history, not from the current text: each task gets the hash its section had at the last spec commit dated on or before the task's reference date (for a Finished task `completion_date`, else `task_verification.timestamp`, else `created_date`; `created_date` for any other status; never `updated_date`). When the section was edited on that very date (`same_day_edit`), git evidence about the task's own file decides: a spec commit of that day that also touches the task file, on a task whose `files_affected` names the spec, is the task's own edit and is the one stamped (`reason: own spec edit`; with several, the oldest); a task file that first enters git, not yet Finished, in or after a spec commit of that day is stamped from that commit (`task filed after the edit`); with neither, the commit before the edit. For an open task (b) assumes the file was committed soon after it was written: one committed in a later bulk commit can be dated after an edit it preceded. History-dated hashes assume the spec was edited on the line the task was built on (a side-branch edit is dated by its merge, a fast-forwarded branch can't be told apart, and a commit's date is in the committer's own timezone). A task finished before a later spec edit therefore gets the old hash, the next `/work` reports that section as changed, and the user absorbs it with `[K]` or acts on it. That is the truth the missing fingerprint was hiding.

| `action` | Meaning | Queued as |
|---|---|---|
| `stamp_history` | The section resolves and the spec's history dates it | **One** row for all of them, file `.claude/tasks/ ({N} files)`, risk `—`, included in bare `[A]`: `Stamp section provenance on {N} tasks from the spec's history ({M} will then show as drift: their section changed after the task)`. `{M}` counts `changed_since: true`; drop the parenthesis when it is 0 |
| `confirm_current` | The section resolves, but nothing dates the task against the spec; each task's `reason` says why | Up to **two** `needs-input` rows, split by `reason`; `{reason summary}` groups the row's `reason` values with their counts. Reasons `the spec has no git history`, `the task has no usable date` (and `the spec can't be read at the commit for the task's date`): `{N} tasks name a section but the spec has no history to date them ({reason summary}). Stamp the current section text as what they were built against? (yes / no / list of ids)`. Reasons `no spec commit on or before the task's date`, `the section is not in the spec at the commit for the task's date`, `the task may predate this spec version` (no `spec_version`, dated on or before the spec file's first commit): `{N} tasks are older than the spec's history for their section ({reason summary}). The current text is not what they were built against; accept it as their baseline anyway? (yes / no / list of ids)` |
| `needs_section` | An open task whose `spec_section` is blank or names no current heading | One `needs-input` row **per task**: `Task {id} "{title}" names no resolvable spec section: which section, or unmapped?` |
| `report_only` | The same, on a Finished task | No row. Report line: `ℹ️ {N} finished tasks name no resolvable spec section; drift can't be checked for them` |

Applying:
- **`stamp_history` row:** `python3 .claude/scripts/fingerprint.py --baseline .claude --write --ids <ids>`. It writes `spec_section` (the real heading), `section_fingerprint`, a missing `spec_version` and a `[BASELINE]` note, and nothing else: `updated_date` stays, so a phase-level verification result remains valid. Exit 2 comes before the first write (the proposals changed since the scan, or a task file can't be rewritten safely; run `--baseline` again), except an I/O error during writing, which names the ids already written; a rerun finishes. A re-listed id that is already stamped is reported `unchanged`, not an error. When `{M}` > 0, tell the user what follows: the next `/work` lists those tasks' sections under Drift Reconciliation, where `[K]` keeps verified work, unless the section already has a deferral, which then covers these tasks too.
- **`confirm_current` rows:** `{id}: yes` → the same command with all of the row's ids plus `--confirm-current`; a list of ids → only those; `no` → nothing is written. On the first row a yes is the user's assertion that the current text is what the tasks were built against, the same one as Drift Reconciliation's `[K]`; on the "older than the spec's history" row it accepts the current text as the baseline knowing it is not. The `[BASELINE]` note the script writes says which. Neither is ever a default.
- **`needs_section` row:** a heading → `python3 .claude/scripts/fingerprint.py --provenance .claude --section "<answer>"` and write its four fields to the task (exit 1: the row stays open; list the real headings). `unmapped` → set `spec_unmapped: true`. Either way leave `updated_date` alone.
- A baseline write counts as a dashboard regen trigger in this batch: the Spec Drift rows come from fingerprints, which `task_hash` doesn't cover.

Never stamp by hand what the script declined: an unconfirmed `confirm_current` task, a `report_only` task, or a hash other than the proposed one. A current hash on a task whose section changed after it records a false "built against this text".

**`spec_unmapped` contradiction:** for each `validate-tasks.py` `provenance_warnings` entry with reason `spec_unmapped set on a task with section provenance`: WARNING — "Task {id} has `spec_unmapped: true` and a `section_fingerprint`. The drift check treats it as mapped; remove whichever is wrong."

### Task Auto-Fixes

Per the Fix Queue Protocol: each detected issue queues one fix item; "Ask user: …" entries become `needs-input` rows with the question inline. Nothing here prompts mid-run.

| Issue | Auto-Fix |
|-------|----------|
| Dashboard missing (tasks exist), META malformed, or legacy `dashboard.md` present | Regenerate dashboard.html (migrates `dashboard.md` first) |
| Dashboard stale (hash mismatch, format staleness, or missing metadata) | Regenerate dashboard.html with fresh metadata |
| Parent missing subtask in array | Add subtask ID to parent's subtasks array |
| Subtask missing parent_task field | Add parent_task field |
| "Broken Down" with empty subtasks | Change status to "Pending" |
| All subtasks Finished or Absorbed but parent not | Set parent status to "Finished" |
| Missing created_date | Add current date |
| Multiple "In Progress" (parallel-ineligible) | Check eligibility — if files overlap or deps unsatisfied, ask which to keep |
| Nested `.claude/.claude/` directory | Flag as error, recommend deletion |
| Orphan dependency reference | Remove invalid dependency ID from array |
| Stale "In Progress" (> 7 days) | Ask user: mark Pending, On Hold, Blocked, or keep |
| Stale "On Hold" (> 30 days) | Ask user: resume, absorb, or keep |
| Absorbed without `absorbed_into` | Ask user: provide absorbing task ID, or change status |
| Absorbed referencing non-existent task | Ask user: provide valid task ID, or change status |
| Absorbed referencing another Absorbed task (chain) | Suggest the non-Absorbed end of the chain; ask user to confirm or change |
| Missing snapshot file | Informational only — drift detection is unaffected; reconciliation shows the current section text instead of a diff |
| Malformed decision dependency format | Ask user: correct or remove the entry |
| Tasks without section provenance, `stamp_history` (check 11) | One row for all: stamp from the spec's history via `fingerprint.py --baseline .claude --write --ids …` |
| Tasks without section provenance, `confirm_current` (check 11) | One row per reason group (undated / older than the spec's history). Ask user: stamp the current section text (yes / no / list of ids) |
| Task without section provenance, `needs_section` (check 11) | Ask user, per task: which spec section, or unmapped |
| Finished tasks naming no resolvable section, `report_only` (check 11) | Informational only: drift can't be checked for them |
| Stale workspace files (> 30 days) | List files, ask user: graduate to final location, or delete |
| Dashboard state sidecar missing | Create with defaults (custom_views off, other toggles on, empty notes) |
| Stale "Awaiting Verification" (> 1 hour) | Auto-recovered by `/work` Step 0 on next run. If running standalone: trigger verify-agent immediately for task |

### Non-Fixable Issues (Manual Required)

| Issue | Why Manual |
|-------|------------|
| Missing required field (id, title, status, difficulty) | Need human input for values |
| Invalid JSON syntax | Need to examine file |
| Circular dependencies | Need to understand intent |
| Duplicate task IDs | Need to decide which to keep |
| Unknown status value | Need to determine correct status (valid: Pending, In Progress, Awaiting Verification, Blocked, On Hold, Absorbed, Broken Down, Finished) |

---

## Part 2: Instruction Files Audit

Two separate checks: environment CLAUDE.md template alignment, and project root CLAUDE.md bloat detection.

### Part 2a: `.claude/CLAUDE.md` Template Alignment

`.claude/CLAUDE.md` is template-owned and should not be modified by users. This check compares the local file against the template version.

**Process:**
1. If template remote is configured (Part 5), diff `.claude/CLAUDE.md` against `template/{default_branch}:.claude/CLAUDE.md` (a non-git project: against the same path in Part 5's temporary clone)
2. If no template remote, compare against a known hash stored in `.claude/version.json` (field: `claude_md_hash`)
3. If the file has been modified locally, report the deviations and queue a `needs-input` fix item with the choices inline (reply `{id}: revert` / `{id}: keep` / `{id}: merge`). The row is decided once Part 5's classification is in hand, and queued only when Part 5's `files[]` entry for `.claude/CLAUDE.md` is `modified`: for a `template_copy` (an older template version, no local edits) Part 5's `—` update row covers it, and this check reports ℹ️ "older template version; Part 5 updates it". When Part 5 can't classify the file (offline, or no script), queue the row as before:
   - **revert** — restore template version (⚠ overwrites local — explicit choice required, never bundled)
   - **keep** — acknowledge deviation (record in `version.json` as `claude_md_override: true`)
   - **merge** — show diff, decide line by line (interactive sub-flow once chosen)

**What to report:**
- ✓ if `.claude/CLAUDE.md` matches template
- ⚠️ if deviations found (with diff summary)
- ℹ️ if the file is an unchanged copy of an older template version (Part 5 updates it)
- ℹ️ if template remote not configured (skip check)

### Part 2b: Root `./CLAUDE.md` Audit

The root `./CLAUDE.md` contains project-specific instructions and is user-owned.

#### Missing File Detection

If `./CLAUDE.md` does not exist at the project root:
1. Report: ℹ️ "No root CLAUDE.md found — this file holds project-specific instructions for Claude"
2. Queue a fix item: create `./CLAUDE.md` from the template at `.claude/support/reference/root-claude-md-template.md` (risk `—`; new file, nothing overwritten)
3. If included in the triage response, copy the template to `./CLAUDE.md`; if excluded, note as informational and continue

#### Repo-type carve-out (template repo)

If a `template-maintenance/` directory exists at the project root, **skip the Bloat Thresholds, Condensation Guidance, and What Belongs Where checks below** and report `ℹ️ Part 2b bloat thresholds skipped (template repo — root CLAUDE.md is template-maintenance context, not a downstream project file)`. The thresholds (100/200 total lines, 15/25 per section) are calibrated for a *downstream project's* root `./CLAUDE.md` — project-specific instructions like tech stack, build commands, and naming conventions. The template repo's root `CLAUDE.md` is a different genre: template-maintenance context carrying live cross-session state (`## Active Follow-ups`, `## File Boundary`) that auto-loads every session by design. The `## Active Follow-ups` section exists precisely because root `CLAUDE.md` auto-loads while `template-maintenance/*` does not — extracting that state into `template-maintenance/` is indirection, not condensation, and reproduces the failure mode the section prevents. Running the thresholds here false-positives every run (2026-08-12: 104 lines, `## Active Follow-ups` at 33; prior 2026-06-11: 109 lines, flagged-and-declined as "maintenance context file, recently dieted"). Missing File Detection and reference validation (check 5) still run — they are genre-independent. Mirrors the Parts 5/5d/7 `template-maintenance/` sentinel; no behavior change for downstream projects (no sentinel → thresholds run as before).

#### Bloat Thresholds

| Metric | Warning (soft limit) | Error (hard limit) |
|--------|---------------------|-------------------|
| Total lines | 100 | 200 |
| Section lines | 15 | 25 |
| Code blocks | 10 | 20 |
| Inline schemas | 8 | Always flag |

#### Audit Checks

1. **Total lines** — compare against soft/hard limits
2. **Section sizes** — check each `##` section for line count
3. **Code blocks** — check each code block for length
4. **Inline schemas** — flag JSON schemas >8 lines
5. **Reference validation** — check that all file paths referenced in the root CLAUDE.md (links, `@` imports) actually exist and are in the correct location (`.claude/support/reference/` for extracted docs)

#### Condensation Guidance

When a section exceeds the soft limit, queue a `needs-input` fix item per section with these choices inline (reply e.g. `{id}: extract`):

1. **Extract** — Move verbose content to `.claude/support/reference/project-{section-slug}.md`, replace with a link. Project reference docs use the `project-` prefix to distinguish from template-owned reference docs.
2. **Condense** — Rewrite to fewer lines. Apply the "would removing this cause Claude to make mistakes?" test. Cut:
   - Standard conventions Claude already knows from reading code
   - Rules already enforced by linters or config files (eslintrc, prettier, tsconfig, etc.)
   - Detailed API docs (link instead)
   - Information that changes frequently
3. **Keep** — Mark as explicitly kept (acknowledge the size)
4. **Skip** — No changes

#### What Belongs Where

**Keep in root `./CLAUDE.md`:** Project overview (1-2 lines), tech stack, key build/test commands, naming conventions that differ from defaults, non-obvious gotchas.

**Extract to `.claude/support/reference/project-*.md`:** Detailed architecture docs, verbose code examples, API specifications, database schemas, deployment procedures.

**Don't put in root `./CLAUDE.md`:** Environment workflow instructions (those are in `.claude/CLAUDE.md` and `.claude/rules/`), information Claude can infer from reading code, style rules already enforced by tooling.

### Part 2c: Rules Files Validation

Validates that the expected template rule files exist in `.claude/rules/`.

**Expected files:** `task-management.md`, `spec-workflow.md`, `decisions.md`, `dashboard.md`, `agents.md`, `archiving.md`, `session-management.md`, `feature-retirement.md`

**Checks:**
- Each expected file exists
- No expected file exceeds 220 lines (raised from 200 per FB-074 — accommodates genuinely rich procedures such as `feature-retirement.md`)
- User-created rule files (`project-*.md`) are noted as informational

---

### Part 2d: Capability Doc Freshness (DEC-017)

Validates that `.claude/support/reference/claude-code-authoring.md` has been verified against Claude Code docs within the staleness threshold.

**Procedure:**

1. Check if `.claude/support/reference/claude-code-authoring.md` exists. If not present, skip Part 2d silently (the doc is shipped with template v4.9.0; older template versions don't have it).
2. Read the footer line at end of file. Expected format:
   ```
   <!-- Last verified against Claude Code docs: <URL> @ <YYYY-MM-DD>; against template_version: <X.Y.Z> -->
   ```
3. Parse the date from the footer. If parsing fails (malformed footer, missing comment), surface inline: `Part 2d: ⚠ claude-code-authoring.md footer missing or malformed. Update with: 'Last verified against Claude Code docs: <URL> @ YYYY-MM-DD; against template_version: <X.Y.Z>'`.
4. Compute days since verification date:
   ```
   days_stale = (today - parsed_date).days
   ```
5. Apply threshold:
   - If `days_stale <= 90`: silent (pass)
   - If `90 < days_stale <= 180`: surface inline `Part 2d: ⚠ Capability doc not verified in {days_stale} days (threshold: 90). Consider verifying against Claude Code docs.`
   - If `days_stale > 180`: surface inline `Part 2d: ⚠⚠ Capability doc not verified in {days_stale} days (threshold: 90, hard threshold: 180). Strongly recommended to verify before authoring spec/skill/agent content that references Claude Code primitives.`
6. Regardless of staleness (when the doc is stale or the footer is malformed), queue a fix item per the Fix Queue Protocol: `Run [V] verify-against-docs pass` (risk `—`; the row notes "reply '{id}: defer' to suppress 30 days"). Do NOT prompt inline.
7. If the row is included in the triage response (the `[V]` flow — interactive by nature, runs after the batch response):
   - WebFetch the docs URL from the footer
   - Diff the fetched content against the current doc body section by section
   - Present each diff as `[A] Accept change | [R] Reject (keep current) | [S] Skip section`
   - On any accept, update the doc body for that section, then Grep the other `.claude/` files for the old claim and list any restatements for the same fix (facts get restated outside the capability doc: `rules/agents.md` kept "no nested `Task` calls" after the doc was corrected, FB-121)
   - After all sections processed, update the footer date to today + `template_version` from `.claude/version.json`
8. If the row is excluded: leave doc unchanged, leave footer unchanged (the warning resurfaces next run).
9. If the user replies `{id}: defer`: write a sentinel in `.claude/dashboard-state.json` (`capability_doc_defer_until: YYYY-MM-DD`, 30 days from today) to suppress the Part 2d warning until that date. Next `/health-check` after the defer-until date will surface the warning again.

**Why this matters:** the capability doc encodes load-bearing facts about Claude Code (turn-scoped `model:` / `effort:`, subagent isolation, MCP constraints, Agent tool model granularity, skill content lifecycle). These facts evolve as Claude Code ships features. The footer + lens combination keeps the reference doc honest without silent auto-sync (which would risk silent contradiction with current spec) and without requiring maintainer-driven version pinning (which decouples from Claude Code's release cadence). See DEC-017 for full rationale.

---

## Part 3: Decision System Validation

Validates the decision documentation system for schema compliance and consistency.

### Repo-type branch (template repo)

Part 3's scan reads `.claude/support/decisions/decision-*.md` — the shipped decision-records directory. In the template repo that directory is the empty shipped placeholder; the real template decision records live in root `decisions/` (21 of them). When a `template-maintenance/` directory exists at the project root, scan `decisions/decision-*.md` (root) **instead of** the shipped path — otherwise schema, staleness, anchor-integrity, and cross-reference checks (1–7 below) all silently validate an empty set and every check vacuously passes. Mirrors the Parts 5/5d/7 `template-maintenance/` sentinel. No behavior change for downstream projects (no sentinel → the shipped path is scanned as before; downstream decision records do live at `.claude/support/decisions/`).

### Validation Checks

#### 1. Decision Record Schema

Each `decision-*.md` file must have valid frontmatter:

**Required fields:**
- `id` - Format: `DEC-NNN` (e.g., DEC-001, DEC-042). Must match `\d+` pattern after `DEC-`. The numeric portion must match the filename: `decision-{NNN}-*.md` → frontmatter `id: DEC-{NNN}`. Mismatch is an ERROR.
- `title` - Non-empty string
- `status` - One of: `draft`, `proposed`, `recorded`, `approved`, `implemented`, `superseded`, `partially_superseded`
- `category` - One of: `architecture`, `technology`, `process`, `scope`, `methodology`, `vendor`, `ux`, `design`, `ui-ia`, `ui-content` (UI-side categories added per FB-074 — see `.claude/support/reference/decisions.md § Categories` for definitions)
- `created` - Valid date in YYYY-MM-DD format

**Optional fields:**
- `decided` - Date when decision was finalized (for an agent-recorded decision, the date of the verify pass; after a reconsider, the date the user selected)
- `decided_by` - `implement-agent` or `orchestrator` on an agent-recorded decision (`decisions.md § "Agent-recorded decisions"`)
- `ratified` - Date the user ratified an agent-recorded decision
- `superseded_by` - `DEC-NNN` of the replacing record, on a `superseded` or `partially_superseded` record
- `superseded_date` - Date the record was superseded (YYYY-MM-DD)
- `related.tasks` - Array of task IDs
- `related.decisions` - Array of decision IDs
- `spec_revised` - Boolean, set after `/iterate` processes an inflection point
- `spec_revised_date` - Date when spec was revised

#### 2. Dashboard Derivation

There is no decisions table to keep in sync: `dashboard-render.py` derives the Decisions card, the "Needs you" Decisions rows (unresolved records, and the one ratify row for `recorded` records) and the META decision counts from `.claude/support/decisions/decision-*.md` on every regen. Its frontmatter reader is line-based and stricter than YAML:
- `---` opens the file (no BOM or leading blank line), and `id`, `title`, `status` are each one plain `key: value` line (no folded or multi-line value, no trailing `# comment`). Otherwise the renderer falls back to the filename for `id`/`title` and to `draft` for `status` (an unresolved row; dependent tasks show as blocked), or reads a garbled status the META counts miss.
- When `dashboard.html` exists, its META `decision_count`, `decisions_approved` (`approved` + `implemented`), `decisions_recorded` (`recorded`), `decisions_superseded` and `decisions_partially_superseded` match counts from the files. A mismatch means a decision changed since the last regen; Part 1 check 10's `task_hash` covers tasks only.

Template repo: skip this check — the renderer reads only `.claude/support/decisions/`.

#### 3. Staleness Detection

- Decisions with status `draft` created > 30 days ago
- Decisions with status `proposed` created > 14 days ago without resolution

#### 4. Completeness (for recorded/approved/implemented)

Decisions with status `recorded`, `approved` or `implemented` must have (headings per the template in `.claude/support/reference/decisions.md`):
- Non-empty `## Decision` section (selected option and rationale; `/work` Step 2b fills it from the box ticked under `## Select an Option`, or, for an agent-recorded decision, the "Persist decisions" step writes it)
- At least one option in the `## Options Comparison` table

`## Select an Option` is not required: an agent-recorded decision has none, before or after ratification.

A record with a `## Selected` heading and no `## Decision` heading (older agent-written records) fails the first requirement on its heading alone: queue the rename row (Decision Auto-Fixes) instead of reporting it incomplete.

#### 5. Implementation Anchor Validation

For decisions with status `implemented`:
- Must have non-empty `implementation_anchors` array
- Each anchor file path must exist in the project
- Report missing anchors as warnings

#### 6. Decision-Task Cross-Reference

Reports mismatches between decision `related.tasks` and task `decision_dependencies`:

**Decision → Task direction:**
- For each decision, check if referenced tasks have the decision ID in their `decision_dependencies`
- Skip agent-decided records (`decided_by: implement-agent` or `orchestrator`). Their `related.tasks` lists the tasks that produced the choice (and any follow-up task after a reconsider). None of them should carry the decision in `decision_dependencies`
- Report mismatches grouped by task status (Finished = most concerning). Report only: `related.tasks` doesn't say whether a task depends on the decision or produced it, so adding the dependency could block a task on its own output

**Task → Decision direction:**
- For each task with `decision_dependencies`, verify each referenced `DEC-NNN` has a corresponding `decision-{NNN}-*.md` file
- Missing decision file: ERROR — "Task {id} references non-existent decision {DEC-NNN}"

This is a reporting check. The primary enforcement and interactive resolution happens in `/work` Step 2b.

#### 7. Legacy Agent-Approved Decisions

Before v5.11.0, a choice an agent made during implementation was written straight to `approved`, which the user never gave. Find records with status `approved` or `implemented`, `decided_by: implement-agent` or `orchestrator`, and no `ratified` key. If any exist, queue **one** row for the project with the count and ids. The dashboard never surfaces these, so this row is their only route to the user.

Records with status `recorded` are not an issue here: the dashboard's ratify row covers them.

### Decision Auto-Fixes

Per the Fix Queue Protocol: each detected issue queues one fix item; "Ask user: …" entries become `needs-input` rows with the question inline. Nothing here prompts mid-run.

| Issue | Auto-Fix |
|-------|----------|
| META decision counts differ from the files | Regenerate dashboard.html |
| Frontmatter line the renderer can't read | Rewrite it as one plain `key: value` line (comment on its own line, BOM/leading blank line removed), then regenerate dashboard.html |
| Stale draft (> 30 days) | Ask user: delete, or set reminder |
| Stale proposed (> 14 days) | Ask user: approve, reject, or extend |
| Implemented without anchors | Ask user: add anchors, or revert to approved |
| Anchor file not found | Report for manual review |
| Cross-reference mismatch | Report for manual review (never auto-add: the task may be the decision's origin, not a dependent) |
| ID/filename mismatch | Ask user: rename file or update frontmatter ID |
| Legacy agent-approved decisions (check 7) | One `needs-input` row: "{N} decisions were approved by an agent, never ratified: DEC-NNN, … — reply `{id}: ratified / recorded / keep`" (`ratified / keep` only when every listed record is `implemented`; with a mix, the row adds "`recorded` skips the {M} `implemented`"). `ratified` adds `ratified: {today}` to each (status unchanged, so `implemented` stays `implemented`); `recorded` sets each `approved` one to `status: recorded` so they join the dashboard's ratify row (then regenerate dashboard.html) and never changes an `implemented` one, which ratifying would leave `approved` — those stay in the row for a later `ratified` or `keep`; `keep` (default, and what an unanswered row means) changes nothing and the row returns next run. Frontmatter only |
| `## Selected` heading, no `## Decision` (check 4) | Rename the heading line to `## Decision`, body untouched. One row per record, `⚠ edits decision record` |
| Task references non-existent decision | Ask user: remove dependency or create the decision record |

The legacy and `## Selected` rows, like every fix here that edits a decision record, trigger DEC-016's `permissions.ask` prompt when applied (once per session with "Yes, don't ask again"). That's expected: check 7's fix is frontmatter-only, and the rename changes a heading label, not the decision's text.

### Non-Fixable Issues (Manual Required)

| Issue | Why Manual |
|-------|------------|
| Invalid frontmatter syntax | Need to examine YAML |
| Invalid status/category/ID value | Need to determine correct value |
| Missing required field | Need human input |
| Incomplete recorded/approved decision | Need Decision section content |

---

## Part 4: Archive Validation

Validates spec archive consistency and detects misplaced files.

### Validation Checks

#### 1. Single-Spec Invariant

There must be exactly one `spec_v{N}.md` file in `.claude/`. Multiple spec files indicate a failed or incomplete version transition.

```
IF count == 0 → Info: "No spec file found" (valid for new projects)
IF count == 1 → ✓ Single-spec invariant holds
IF count > 1  → ERROR: "Multiple spec files found"
               Auto-fix: Archive lower versions to previous_specifications/
```

#### 2. Spec Version Continuity

For each version from 1 to N-1, check that `.claude/support/previous_specifications/spec_v{i}.md` exists.

#### 3. Misplaced Spec Files

Scan non-canonical locations for `spec_v*.md` files:
- `.claude/archive/`, `.claude/previous_specifications/`, `.archive/`, `.claude/specs/`, project root
- Report each with suggested correct path

#### 4. Decomposed Spec Validation

For archived specs where tasks reference that version, check if `spec_v{i}_decomposed.md` exists. Warning-level only.

#### 5. Untracked Source-of-Truth (informational, FB-099)

The project's authored memory under `.claude/` — the spec (`.claude/spec_v*.md`), task files (`.claude/tasks/`), and decision records (`.claude/support/decisions/`) — is the source of truth. When a project gitignores these paths (a deliberate fork convention in some projects), they are never committed: invisible to git history, `git diff`, and recovery. This check surfaces that once per run so the choice is conscious, not accidental. It never blocks and never auto-fixes.

```
For each of `.claude/spec_v*.md` (current spec), `.claude/tasks/`, `.claude/support/decisions/`:
  run `git check-ignore -q <path>` (exit 0 = ignored, 1 = not ignored, 128 = no git / error)

IF git absent (128 for all) OR none are ignored → silent (no finding)
IF any are ignored → Info (not a warning), once per run:
  "Part 4.5: Source-of-truth state is untracked — {gitignored paths} match this project's .gitignore.
   Deliberate? If so, consider a backup convention (periodic archive, a separate private remote, or export).
   If not, removing the ignore rule restores git's safety net."
```

Use `git check-ignore` (reliable exit-code semantics), not a grep against `.gitignore` text — a path can be ignored by a parent-directory or negated rule that a literal grep misses. Informational only; respects deliberate conventions. Distinct from FB-063 (worktree reads of gitignored state) and `/work` Step 0e (uncommitted *tracked* work — the inverse: tracked `.claude/` files that git *does* see).

### Archive Auto-Fixes

| Issue | Auto-Fix |
|-------|----------|
| Multiple spec files in `.claude/` | Archive lower versions, keep highest as current |
| Spec in wrong location | Move to `.claude/support/previous_specifications/` |
| Missing archived spec | Cannot auto-fix — warn user |
| Missing decomposed spec | Informational only |

---

## Part 5: Template Sync Check

Checks whether the project's `.claude/` workflow files are up to date with the template repository, by comparing their content with the template's git history. Skipped in the template repo (mirror of Parts 5d / 7: a `template-maintenance/` directory at the project root indicates the template repo, where syncing the template against itself is self-referential and meaningless — `template_repo` points to the same URL as `origin`).

### Purpose

The upstream template may improve commands, agents, and reference docs. This check compares the project's sync files against the template repo (a git remote, or a temporary clone for a project that isn't a git repository) and presents updates.

### Repo-type skip

Before running any sync step: if a `template-maintenance/` directory exists at the project root, skip Part 5 entirely and report `ℹ️ Template sync skipped (template repo — self-sync is a no-op)`. The template repo's `version.json::template_repo` points to itself; adding a `template` remote pointing to the same URL as `origin` and diffing against it produces no useful output. The template's own work uses normal git workflow (push to origin); downstream-project sync flow does not apply.

### Requirements

- `.claude/version.json` — contains `template_repo` (git URL), `template_version` and `template_release_date`
- `.claude/sync-manifest.json` — defines `sync` (updatable) vs `customize` (user-owned) vs `ignore` (project data) file categories
- `git` available (no `gh` CLI dependency). The project itself doesn't have to be a git repository (Step 1)
- `python3` for `.claude/scripts/sync-check.py` and `.claude/scripts/sync-apply.py` (optional; the prose fallbacks in Steps 2 and 4 work without it)

### Sync State Sidecar

Whether the project edited a sync file is decided from the template's own history: a file whose content equals any template version of its path is an unchanged template copy. `.claude/.sync-state.json` (the sidecar) is the fallback, read only when the template history is shallow and so can't place a file. With the whole history it is never consulted: content that no template version holds is the project's own, whatever the sidecar says. It records the content each sync file had when it last equalled the template.

**Schema** (unchanged):

```json
{
  "schema_version": "1.0",
  "last_full_sync_version": "<template_version at time of sync>",
  "last_full_sync_date": "<ISO 8601 date>",
  "files": {
    "<path>": { "synced_hash": "sha256:<full SHA-256 hex>" }
  }
}
```

`synced_hash` is the SHA-256 of the file's raw bytes, as full hex with a `sha256:` prefix.

**Lifecycle:**
- **Read** by `sync-check.py` in Step 2, and used only when `history_complete` is false, for a differing file that matches no template version of its path: when the file's hash equals its `synced_hash`, the file is an unchanged template copy (`basis: "sidecar"`). A missing sidecar gives no entries; an unreadable one is ignored with a warning.
- **Written** by `sync-apply.py` in Step 4. After a run the sidecar holds exactly the compare-set files that equal the upstream copy, each with its `synced_hash`, not only the files the run wrote. Every other entry is dropped: a path outside the compare set (a project's own file, a deleted one), or a compare-set file that differs from upstream (except the entry a shallow-history classification still rests on, when that file wasn't updated in the run). Other top-level keys are kept. The script creates the sidecar when it is missing and replaces one it can't parse.
- **Gitignored.** The sidecar describes one working copy, so it is in the manifest's `ignore` category and belongs in `.gitignore`. Step 3 queues a row when it isn't ignored.

### Process

#### 1. Setup Remote

**Git project** (`git rev-parse --is-inside-work-tree` prints `true`). Ensure the template repo is configured as a git remote named `template`:

```
IF "template" remote doesn't exist → git remote add template {template_repo}
IF "template" remote exists but URL differs from version.json → warn, ask to update
```

Fetch latest: `git fetch template` (fetch only, never merge or pull). Determine the template's default branch via `git remote show template` (typically `main`). In the steps below, `{ref}` is `template/{branch}`.

**Non-git project** (the command fails). Don't add a remote. Clone the template into a temporary directory outside the project (`mktemp -d`, or the session scratchpad): `git clone --quiet {template_repo} "$TMP/template"`. Clone the full history (no `--depth`): classification reads it. In the steps below, `{ref}` is `origin/HEAD`, both scripts take `--template-repo "$TMP/template" --ref origin/HEAD`, and every template `git` command in the fallbacks and in `[D]` takes `-C "$TMP/template"`. Skip Step 5, and delete the clone when the run ends.

If the fetch or clone fails (offline, invalid URL) → report as informational, skip remaining sync checks.

#### 2. Compare Sync Files

Run `python3 .claude/scripts/sync-check.py --ref {ref}` from the project root (read-only; JSON on stdout). The script classifies every sync file by content, against the template's history; Part 5 doesn't diff files one by one.

**Which patterns:** the script's `patterns.compare` — the **upstream** manifest's `sync` patterns plus project-added ones (local `sync` patterns the template never listed). The local manifest alone would skip every file the template added since setup. Retired patterns (`patterns.retired`: local ones the template no longer syncs, because it dropped them from `sync` or now lists them as `customize`/`ignore`) are not compared. A path matching an upstream `customize` or `ignore` pattern is never compared, even when a sync pattern also matches it, unless the upstream `sync` list names that exact path (it names `.claude/vision/README.md`, which `ignore`'s `.claude/vision/*.md` also matches).

**Glob semantics** (patterns match project-root-relative POSIX paths): `**` matches any characters including `/`; `*` matches any characters except `/`; `?` matches one character except `/`; every other character is literal.

**Per-file status.** `files[]` has one entry per upstream file in the compare set, with the keys `path`, `status`, `mode`, `mode_matches`, `version`, `basis` and `shared_lines`:
- **Up to date** — `up_to_date`.
- **Unchanged template copy** — `template_copy`: the local content equals template v{version} of this path (or, with `basis: "sidecar"`, the content recorded at the last sync; that basis occurs only when the template history is shallow). Nothing local is lost by updating. `version` is `null` when history can't name the release, and always with `basis: "sidecar"`.
- **Locally modified** — `modified`: matches no template version. User adjudicates. `shared_lines` is the share (0 to 1) of the file's non-blank lines that appear in any template version of the path. A path that is a symlink or a directory locally is also `modified`, with `shared_lines: null`; Step 4 refuses to write it.
- **New in template** — `new`: the file exists upstream but not locally.
- **Retired upstream** — the template shipped this path (as a sync file, or with exactly this content) and later deleted it (offered for removal). These are the `retired_files` entries.
- **Local only** — present locally, absent upstream, and not a retired template file (kept, never flagged). Every file the template never shipped is Local only.

`mode` is the file's mode upstream (`100644`, or `100755` for an executable); `mode_matches` is false when the local file's executable bit differs.

**Also carry into Steps 3–5:**
- `patterns.retired` and `retired_files`.
- `uncommitted_sync`: what an earlier sync changed and nobody committed. It lists changed sync files present upstream whose content equals **any** template version of their path, not only the current one (so the sync is still found after the template moves on), deletions of retired files, and `.claude/version.json` and `.claude/sync-manifest.json` alongside them.
- `history_complete`: false when the template history is shallow (a commit in the repository's `shallow` file is reachable from `{ref}`); a shallow project clone with the whole template fetched is complete. The sidecar is read only when it is false.
- `manifest.customize` and `manifest.ignore`, each with `add` (upstream entries the local list lacks), `drop` (local entries the template has retired or moved to another category) and `list` (the upstream list followed by the project-added entries).
- `sidecar`: `exists`, `gitignored`, `tracked` (the last two are `null` for a non-git project).

**Fallback** (script missing or failing):
- *Per-file status:* a file is up to date when its `git hash-object --no-filters <path>` id equals `git rev-parse {ref}:<path>`, and new when it is missing locally. A differing file is an unchanged template copy when its id is among the path's *template blob ids* (the ids in `git log {ref} --no-renames --raw --no-abbrev --format= -- <path>`), or, only when the template history is shallow, when its `sha256:` hash equals the sidecar's `synced_hash`; otherwise it is locally modified.
- *Retired patterns:* a local `sync` pattern the upstream list lacks is retired when `git log {ref} -S'"<pattern>"' --format=%h -1 -- .claude/sync-manifest.json` prints a commit (the template once listed it); otherwise it is project-added.
- *Retired files:* from `git log {ref} --no-renames --diff-filter=D --name-only --format=%H -- .claude/`, keep paths that exist locally, are absent upstream and match no `customize`/`ignore` pattern of the upstream or local manifest (unless `git show <commit>^:.claude/sync-manifest.json` names the exact path in `sync`), and that also match one of that manifest's `sync` patterns or have a `git hash-object --no-filters` id among the path's template blob ids. The `%H` line above a path's first appearance is its `<commit>` (`removed_commit`).
- *Uncommitted sync:* from `git status --porcelain -uall -- .claude` (without `-uall`, a new directory shows as one entry), list each changed file that is in the compare set and exists upstream, when its `git hash-object --no-filters <path>` id is among its template blob ids (not `git diff --quiet`, which reports an untracked file as deleted); each deleted path that passes the retired-files rule (the file is gone, so its id is `git rev-parse HEAD:<path>`); and `.claude/version.json` and `.claude/sync-manifest.json` when changed and anything else is listed.
- *Sidecar:* ignored when `git check-ignore -q --no-index -- .claude/.sync-state.json` exits 0; tracked when `git ls-files --error-unmatch -- .claude/.sync-state.json` exits 0.
- *File modes and manifest lists:* not checked without the script; the next run with it queues those rows.

#### 3. Present Changes (report) and Queue Apply Rows

Group files by the per-file status from Step 2 and present them in the report — grouped and impact-annotated for bigger changes:

```
Template updates available (v5.7.4 → v5.10.0):

  Unchanged template copies (no local edits):
    .claude/support/reference/dashboard-regeneration.md (copy of v5.4.0)
    .claude/commands/work.md (copy of v5.7.4)

  Locally modified (review before including):
    .claude/support/reference/paths.md

  New:
    .claude/support/reference/new-feature.md

  Retired upstream (the template removed these files):
    .claude/skills/dashboard-style/SKILL.md (removed in v4.12.0; unchanged template copy)
    .claude/commands/complete-task.md (removed in v1.5.0; locally modified)

  Retired sync patterns (the template no longer syncs these):
    .claude/skills/*/SKILL.md (as of v4.12.0)
```

An unchanged copy whose `version` is `null` reads `(copy of an earlier template version)`, or `(unchanged since the last sync)` with `basis: "sidecar"`.

When `uncommitted_sync` is non-empty, add `ℹ️ {N} synced files are not committed (an earlier sync was never committed)`; Step 5 offers the commit.

When `history_complete` is false, add `ℹ️ Template history is shallow: files it can't place are classified from the sync-state sidecar; "Locally modified" may include unchanged copies. git fetch --unshallow template gives the full answer.`

**Grouping heuristic** (bigger changes): group related files by workflow area (e.g., a command and the reference docs it depends on) and state the impact per group, plus the per-file classification.

**Queue one fix item per file** (per the Fix Queue Protocol) instead of prompting:

- "Unchanged template copy" files → `Update template file (unchanged copy of v5.4.0)`, risk `—`, included in bare `[A]`. With `basis: "sidecar"` the row reads `Update template file (unchanged since the last sync)`; with a `null` version on a history copy, `Update template file (unchanged copy of an earlier template version)`.
- "Locally modified" files → `Update template file (locally modified, [D] shows the diff)`, risk `⚠ overwrites local`, excluded from bare `[A]`, explicit inclusion required. When `shared_lines` is not null and below 0.25, the row reads `Update template file (local content is not a variant of the template file: {N}% of its lines appear in any template version; move it to a project-*.md file before including)`, with `{N}` = `shared_lines` × 100, rounded: the project stored its own content at a template-owned path, and updating would destroy it.
- "New in template" files → `Add new template file`, risk `—` (new file, nothing overwritten).
- An up-to-date file whose `mode_matches` is false → `Fix file mode ({mode})`, risk `—`. A file with any other status gets its mode set when its update row applies.
- "Retired upstream" files → `Remove retired template file (removed upstream in v4.12.0; unchanged template copy)` when `state` is `unmodified`, `Remove retired template file (removed upstream in v1.5.0; locally modified, [D] shows the diff)` when `modified`; risk `⚠ deletes`.
- Retired sync patterns → `Drop retired sync pattern ".claude/skills/*/SKILL.md" (the template no longer syncs it as of v4.12.0)`, file `.claude/sync-manifest.json`, risk `—`. "No longer syncs" covers both cases: the template dropped the pattern, or now lists it as `customize`/`ignore`.
- `manifest.customize` or `manifest.ignore` with a non-empty `add` or `drop` → one row for both lists: `Update local manifest lists (add .claude/dashboard.html; drop .claude/dashboard.md)`, file `.claude/sync-manifest.json`, risk `—`. Project-added entries are kept. A local entry that names a path or pattern the template syncs is not project-added: it is dropped, and it never excluded the file from sync.
- `sidecar.gitignored` false → `Add .claude/.sync-state.json to .gitignore`, file `.gitignore`, risk `—`. When `sidecar.tracked` is also true the row reads `Stop tracking .claude/.sync-state.json and add it to .gitignore`. Not queued for non-git projects.

When `removed_in` is `null`, leave the version out of the row (`(removed upstream; …)` / `(the template no longer syncs it)`) and of the report line.

An excluded row changes nothing: the file, pattern or list stays as it is, and the next run offers the row again. Full diffs are available pre-decision via the triage table's `[D]`, which prints `git show {ref}:{path} | diff -u - {path}` (for a removal row `git show {removed_commit}^:{path} | diff -u - {path}`), truncated to ~100 lines with a "...truncated" marker.

#### 4. Apply Updates

Apply the included Part 5 rows in this order.

**a. Retired files.** Remove each included retired file: `git rm -q -- {path}` when tracked, else `rm -- {path}`; then remove parent directories left empty, up to but not including `.claude/`. If `git rm` refuses because of uncommitted edits, report the row as failed (never `-f`).

**b. Sync files, modes, manifest and sidecar: one script call.** Write the paths of the included update, new-file and mode rows to a file, one project-root-relative path per line (in the session scratchpad or `.claude/support/workspace/`), then run from the project root:

```
python3 .claude/scripts/sync-apply.py --ref {ref} --paths-from {file} [--keep-pattern "{pattern}"]… [--manifest-lists]
```

- `.claude/settings.json` asks before this command runs (`permissions.ask`): it is the one script that writes template files into `.claude/`. That prompt is expected, once per call.
- `--keep-pattern` once per retired sync pattern whose drop row was **not** included (the pattern then stays in the local `sync` list).
- `--manifest-lists` when the manifest-lists row was included.
- Leave out `--paths-from` when no update, new-file or mode row was included; the script then does only its bookkeeping.

Run it whenever a Part 5 row other than the `.gitignore` row was included. The script does the following, all inside `.claude/`:
- writes each listed file with the template's content and mode (a mode row is a `chmod`);
- sets `template_version` and `template_release_date` in `.claude/version.json` to the upstream values, only when it wrote a file's content, or when every compare-set file now equals upstream and the local version differs (the re-run after an interrupted run). Removal, pattern-drop, manifest-list and mode rows alone don't bump the version unless every sync file already equals upstream, so a run that only removes files or drops patterns doesn't claim a version whose files it doesn't hold (Step 5's commit message reports the version: `Sync template vA → vB`);
- sets the local `sync` list to `patterns.compare` plus the kept retired patterns, and with `--manifest-lists` sets `customize` and `ignore` to `manifest.<cat>.list`;
- updates the sidecar as described under "Sync State Sidecar", and refreshes `last_full_sync_version` and `last_full_sync_date` when it bumped the version.

Report from its JSON output: `written` and `mode_fixed` are the applied rows, each `failed` entry (`path`, `error`) is a failed row, `version` says whether the version was bumped, `changed_paths` feeds Step 5, and `remaining` lists the sync files still not up to date. Exit `1` means some rows failed and everything else was applied. Exit `2` means the run did not complete (message on stderr): fix the cause and re-run, or use the fallback. After an exit 2 some files may already be written; after the re-run, run `sync-check.py` again and take Step 5's paths from its `uncommitted_sync` as well.

**Fallback** (script missing or failing): for each included file, `git show {ref}:{path} > {path}` (create parent directories; skip a path that is a symlink or directory locally and report the row as failed), then `chmod 755` when `git ls-tree {ref} -- {path}` shows mode `100755`, else `chmod 644`. When a file's content was written (or every compare-set file now equals upstream and the local version differs), set `template_version` and `template_release_date` in `.claude/version.json` to the values in `{ref}:.claude/version.json`. Set the manifest's `sync` list as above. In the sidecar, record `synced_hash` for every compare-set file that now equals its upstream copy, drop every other entry (when the template history is shallow, keep the entry of a file classified by it that you did not update), and refresh the two `last_full_sync_*` fields when the version was bumped (create the file with `schema_version: "1.0"` when missing).

**c. The `.gitignore` row.** When the sidecar is tracked: `git rm --cached -q -- .claude/.sync-state.json` (the file stays on disk). Then append the line `.claude/.sync-state.json` to the project root's `.gitignore`, creating it when missing.

**d. Post-sync dashboard re-check.** If any included sync row touches the renderer or a dashboard-rule file (`scripts/dashboard-render.py`, `dashboard-regeneration.md`, `rules/dashboard.md`, or `shared-definitions.md`), the dashboard was generated with older format rules — regenerate it as part of applying that row (no extra prompt; the row's one-line description notes "includes dashboard regen", so the user sees the consequence before responding). This catches the ordering issue where Part 1 ran dashboard checks before Part 5 synced the new rules, and dedupes with any Part 1 regen row — the dashboard regenerates at most once per run, last. Regeneration follows `.claude/support/reference/dashboard-regeneration.md` (which is now the updated version).

#### 5. Commit Offer

Fires when the project is a git work tree and either a Part 5 row was applied in this run or `uncommitted_sync` is non-empty; runs after the batch triage's post-apply summary (or after the report when the queue was empty). Paths = `sync-apply.py`'s `changed_paths` (fallback: the files Step 4 wrote, plus `.claude/version.json` and `.claude/sync-manifest.json` when changed), plus the retired files removed in this run, plus `.gitignore` when its row applied, plus `uncommitted_sync` paths; minus gitignored paths (`git check-ignore -q`) and paths with no change in `git status`. `.claude/.sync-state.json` is listed in one case only: as `D` when the stop-tracking row applied. With no path left, there's no offer. Each path is listed with `M`, `A` or `D`:

```
Template sync changed {N} files and they are not committed:
  M .claude/commands/work.md
  D .claude/skills/dashboard-style/SKILL.md
  M .claude/version.json
Commit them now? [C] Commit as "Sync template v{old} → v{new}" | [L] Leave uncommitted
```

`{old}` = `template_version` in `HEAD:.claude/version.json` (fallback: the local value before this run); `{new}` = the local value after this run; when they're equal, the message is `Sync template files (v{new})`. When a sync-file row was left unapplied, append ` (partial: {k} sync files not updated)`.

- `[C]`: `git add -- <paths that still exist>` (skip it when none do), then `git commit -m "<message>" -- <paths>`. The commit takes deletions itself (`git add` rejects a path `git rm` already removed) and commits only those paths, even if other changes are staged. Never pushes. When the sidecar's `D` is listed, leave it out of the `git add`, move `.claude/.sync-state.json` out of the project before the commit and move it back afterwards: `git commit -- <paths>` re-adds a listed path that exists in the working tree, which would undo the untracking.
- `[L]`: `Left uncommitted. The next /health-check will offer this commit again.`

With `--report`: no offer; the `ℹ️` line only.

### Key Rules

- **File-level comparison required** — you MUST fetch (or clone) the template and compare every sync file's content against it, with `sync-check.py` or the Step 2 fallback. Comparing `template_version` strings is NOT a substitute. Version numbers can match while files diverge (e.g., local edits, partial syncs, template patches). The version number is only used for display and for updating `version.json` after applying changes.
- **Sync category only** — never touch `customize` or `ignore` category files; upstream `customize`/`ignore` lists win over a local `sync` pattern
- **Files the template never shipped are never flagged** (e.g. a project's own skills or commands). A file the template shipped (as a sync file, or with exactly this content) and later deleted is offered for removal (`⚠ deletes`, explicit inclusion only); nothing is removed without that.
- **No silent changes** — always present changes and get confirmation before applying
- **Fetch only** — never merge, pull, or rebase from the template remote
- **Blob history decides, the sidecar is the fallback** — a file equal to any template version of its path is an unchanged copy and updates under bare [A]; only a file matching no template version needs adjudication. The sidecar is read only when the template history is shallow.

### Report Format

**Up to date (no diffs in sync files, nothing retired):**
```
### Template Sync

✓ Template up to date (v1.5.0)
```

**Up to date, but an earlier sync was never committed** (the working tree already matches the template; Step 5 offers the commit):
```
### Template Sync

✓ Template up to date (v5.10.0)
ℹ️ 36 synced files are not committed (an earlier sync was never committed)
```

**Offline / fetch or clone failed:**
```
### Template Sync

⚠️ Cannot reach template repository — skipping template sync
```

**Missing config:**
```
### Template Sync

ℹ️ Template sync not configured (missing version.json or sync-manifest.json)
```

**Remote not configured (first run):**
```
### Template Sync

ℹ️ Adding template remote: {template_repo}
```

---

## Part 5b: Command Collision Detection

Detects when custom commands in `.claude/commands/` overlap with template commands.

### Process

1. **Identify template commands** — known set: `work.md`, `iterate.md`, `breakdown.md`, `health-check.md`, `status.md`, `research.md`, `feedback.md`, `review.md`, `audit-coherence.md`, `audit-ui.md`, `diagnose.md`, `grill.md`, `zoom-out.md`, `shakedown.md`
2. **Scan `.claude/commands/`** for all `.md` files not in the template set
3. **Detect collisions:**
   - **Name collision:** custom file has same name as template command
   - **Functional overlap:** filename or content suggests overlap (e.g., `plan.md` → `/iterate`, `complete.md` → `/work complete`)
4. **Report** — list custom commands with any overlap warnings

Never delete or rename custom commands without user consent.

---

## Part 5c: Settings Boundary Validation

Validates the layered-settings contract: `.claude/settings.json` is template-owned (base `permissions.allow` + base `permissions.ask` per DEC-016); `.claude/settings.local.json` is user-owned (all user additions, hooks, env vars, theme). Enforcing the boundary prevents template sync from silently clobbering user edits.

### Process

1. **Check for presence:**
   - If `.claude/settings.json` is missing: informational only (will be created by next template sync).
   - If `.claude/settings.local.json` is missing: informational only (user has no overrides yet — fine).

2. **Validate template-owned `settings.json` scope:**
   - Parse `.claude/settings.json` as JSON.
   - If parse fails: ❌ error — "`.claude/settings.json` is not valid JSON. Sync may have been interrupted; re-run `/health-check` to re-sync."
   - Check that the file contains **only** `permissions.allow` and/or `permissions.ask`:
     - ✅ Pass: the top-level object has exactly one key (`permissions`) whose value has only the keys `allow` and/or `ask`.
     - ⚠️ Warn if any of the following are present: `permissions.deny`, `hooks`, `env`, `theme`, or any other top-level key.
     - Warning message (report):
       ```
       ⚠️ Found non-base entries in `.claude/settings.json` (template-owned file).
          Unexpected keys: {list}
          These will be overwritten on next template sync.
       ```
     - Queue a fix item: move the unexpected entries to `.claude/settings.local.json` (risk `—`; content is moved, not lost — create the local file if missing, concatenate+dedupe for array fields like `permissions.allow`, preserve existing keys for object fields like `hooks`, then strip them from `.claude/settings.json`). If excluded: leave files as-is; next sync will overwrite.

3. **Validate base-set drift (template vs. local):**
   - Read the template's `.claude/settings.json` from the template remote, or from Part 5's temporary clone in a non-git project (if configured and reachable — same fetch as Part 5). Skip this check if offline.
   - Compare the local `permissions.allow` AND `permissions.ask` arrays against the template's.
   - If entries differ: this is normal (user has not yet synced, or template has been updated). Part 5's sync flow will offer the update — no Part 5c action needed.
   - This check exists purely to reassure users that additions/removals from the template base will propagate through normal sync.

4. **Report:**
   - Pass: `✓ Settings layer valid (template-owned base + user-owned local)`
   - Warnings: emit the warning block from step 2 above.

### Rationale

Claude Code's runtime concatenates `permissions.allow[]` and `permissions.ask[]` across all settings layers, so the user's additions in `settings.local.json` combine automatically with the template's base in `settings.json`. The template-owned file exists for two jobs: shipping a conservative base allow-set (read-only git/filesystem commands) AND a base ask-set (template-wide guardrails for spec/decision/vision file edits per DEC-016). Everything else (project-specific permissions, hooks, env vars, theme) belongs in the user-owned file.

---

## Part 5d: Cross-Project Bridge Configuration (downstream projects only)

Validates the `template_inbox_path` configuration that powers the cross-project feedback bridge. Skipped in the template repo (mirror of Part 7's detection: a `template-maintenance/` directory at the project root indicates the template repo, where bridging to itself is not meaningful).

### Process

1. **Repo-type detection:** If a `template-maintenance/` directory exists at project root, skip Part 5d entirely.

2. **Read configuration:** Read `.claude/version.json` → `template_inbox_path`.

3. **If `template_inbox_path` is empty string (unconfigured):**

   This is not an error — the bridge is optional. Report once per `/health-check` run:
   ```
   Cross-project feedback bridge: not configured.

   The bridge lets `/feedback template: <text>` carry template-relevant feedback
   back to the template repo's inbox automatically. `/health-check` in the template
   repo then routes those entries into `template-maintenance/feedback.md`.
   ```

   Queue a `needs-input` fix item: configure the bridge — reply `{id}: <absolute path to the template repo's interaction-logs/inbox/>` (or exclude to keep the bridge disabled).

   - On a path reply:
     - Expand `~` and `$HOME` if present in the user's input
     - Validate that the path exists and is a directory
     - If valid: update `.claude/version.json` `template_inbox_path` field with the absolute path. Report: `✓ template_inbox_path configured: {path}`
     - If invalid: report the specific issue (not a directory / doesn't exist) in the post-apply summary; the item resurfaces next run
   - If excluded: silent pass — the bridge stays disabled

4. **If `template_inbox_path` is set and the path exists as a directory:**

   Silent pass. In the final `/health-check` report, include: `✓ Cross-project bridge: enabled ({path})`

5. **If `template_inbox_path` is set but the path doesn't exist or isn't a directory:**

   Report the issue and queue a `needs-input` fix item:
   ```
   ⚠️  template_inbox_path is set to '{path}' but that path doesn't exist (or is not a directory).
   ```

   Row choices inline: reply `{id}: <corrected absolute path>` (validated against the filesystem, same flow as step 3) · `{id}: clear` (set to empty string, disables the bridge) · exclude to leave as-is (surfaces again on next `/health-check`).

### When to Run

Runs on every `/health-check` in downstream projects. Cost is one JSON read + one directory stat — negligible compared to other parts. Surfacing the unset state once per run keeps the bridge discoverable without being noisy (Quick capture and `/work` paths are unaffected).

### Rationale

The bridge is purely opt-in (per `/feedback template:` semantics — silently no-ops when unset). Without surface area in `/health-check`, the configuration is invisible to most users — the `template_inbox_path` slot ships empty, and nothing else prompts the user to set it. Part 5d closes that discoverability gap without imposing the bridge on users who don't want it.

---

## Part 6: UX Evaluation

Assesses dashboard readability, project structure clarity, and interaction quality. Findings contribute to the overall health-check status (HEALTHY / NEEDS ATTENTION / CRITICAL ISSUES).

**Severity framework:** Nielsen's 0-4 scale mapped to health-check indicators:
- Severity 0-1 (cosmetic): `ℹ️` info — noted but doesn't affect status
- Severity 2 (minor): `⚠️` warning — contributes to NEEDS ATTENTION
- Severity 3-4 (major/catastrophic): `❌` error — contributes to CRITICAL ISSUES

### Initial Checks (targeting known issues)

The check catalog starts minimal and grows based on real usage feedback. Initial checks target three observed problems:

#### 1. Dashboard HTML Integrity (H3 — Visualization Integrity)

The dashboard is generated HTML (DEC-024); the script owns all rendering deterministically (graph scaling, heatmap, collapsing), so readability is script-guaranteed. This check instead guards the `file://` offline invariant: scan `dashboard.html`.

| Condition | Result | Severity |
|-----------|--------|----------|
| Valid HTML (starts `<!doctype html>`, ends `</html>`), `<!-- DASHBOARD META -->` in `<head>`, no `type="module"` / CDN `import`/`fetch` (only Google-Fonts `<link>` permitted as external) | Pass | — |
| Missing META in `<head>`, or malformed document | Error: "dashboard.html missing META block or malformed — regenerate via `dashboard-render.py --html`." | 3 |
| Any runtime CDN dep (`type="module"`, `import … from "http…"`, `fetch(`, non-fonts `cdn.`) | Error: "dashboard.html has a runtime network dep — breaks offline `file://` open. Regenerate." | 3 |

#### 2. Workspace Document Graduation (H6 — Project Structure Clarity)

Count files in `.claude/support/workspace/` that are either: (a) linked from dashboard content, or (b) listed in `files_affected` of tasks with `owner: human` or `owner: both`.

| Condition | Result | Severity |
|-----------|--------|----------|
| 0-2 workspace files referenced | Pass | — |
| 3+ workspace files referenced by human/both tasks | Warn per file: "'{filename}' is in workspace but referenced by human task {id}. Consider moving to project root (e.g., `docs/`)." | 2 |

#### 3. User Notes Section Utilization (H5 — User-Input Effectiveness)

Check if the sidecar's `user_notes` (rendered as the dashboard's Notes card) contains only the default placeholder text after the project has 5+ completed tasks.

| Condition | Result | Severity |
|-----------|--------|----------|
| Notes has user content, or <5 tasks completed | Pass | — |
| Notes is default placeholder, 5+ tasks completed | Info: "Notes section is still the default placeholder. Add Quick Links or project-specific notes." | 1 |

#### 4. Action Required Actionability (H4 — Navigation)

Script-owned rows are exempt from 4a and 4b: the renderer emits them (with their command, or as status lines such as Audit Findings rows and "Nothing blocked on you right now."), and its tests pin their wording. Both checks read the "Also Needs You" rows, rendered from the sidecar's `augment_rows` — the card's only LLM-written rows.

**4a. Actionability.** Every "Also Needs You" action row needs a completion command (a `code` span) or a link (`[text](path)` in the row's `text`). `fyi` rows (rendered "FYI — …") are context and are exempt.

| Condition | Result | Severity |
|-----------|--------|----------|
| Every action row has a command or link (or there are none) | Pass | — |
| Action row with neither | Error per row: "Augment row '{text}' has no command or link — add one to its `augment_rows` entry, or set `kind: \"fyi\"` if it asks nothing of the user." | 3 |

**4b. Summary-shape content (FB-015 / FB-038).** Scan the "Also Needs You" rows (both kinds) for retrospective content that violates the rule in `support/reference/dashboard-regeneration.md` § Action Item Contract ("must NOT include work summaries, completion reports, or recent-activity recaps").

Detection heuristics — flag if ANY match:

- **Past-tense completion verbs** in a row (not in the imperative form): `finished`, `completed`, `shipped`, `fixed`, `Task {N} finished/completed`, `successfully added/removed`. Watch for false positives — "Complete the form" is imperative (OK); "Form completed" is retrospective (flag).
- **Forbidden sub-section headings** anywhere in the card: `Recent Activity`, `Work Summary`, `Completed This Session`, `Recently Completed`, `Done` (as a section name, not a checkbox label). The script never emits them, so one means the HTML was hand-edited.
- **Long prose rows:** any single row with more than 2 paragraphs of prose. Legitimate actionable items rarely need that much explanation — the contract requires "just enough context to act."
- **Runs of finished work:** >2 consecutive rows starting with past-tense verbs (e.g., "✅ Task 5 added X", "✅ Task 6 fixed Y").

| Condition | Result | Severity |
|-----------|--------|----------|
| No summary-shape content | Pass | — |
| Summary-shape match found | Error per match: "Action Required contains retrospective content: '{excerpt}'. Belongs in git log / task notes / nowhere — prune it from `augment_rows`." | 3 |

When `4b` fires repeatedly across `/health-check` runs on the same project, the orchestrator keeps writing recaps into `augment_rows`: tighten `dashboard-regeneration.md § "Augment Rows"` (capture it as feedback) rather than the renderer.

#### 5. Dashboard Size (H1 — Readability)

Measure the byte size of `dashboard.html`. Curated + spec-linked-out, it should stay light (~25–150 KB) regardless of project size; a large file usually means the spec or decision text got embedded by mistake (it must be linked out, not embedded).

| Condition | Result | Severity |
|-----------|--------|----------|
| ≤200 KB | Pass | — |
| 200–500 KB | Warn: "dashboard.html is {N} KB — check that the spec/decisions are linked out, not embedded." | 2 |
| >500 KB | Warn: "dashboard.html is {N} KB — spec/decision text was likely embedded. Verify link-out and regenerate." | 2 |

### Extending the Check Catalog

New checks should be added when:
- A UX problem is observed in a real project (not hypothetical)
- The check has a clear structural signal (can be verified from file content, not rendering)
- The threshold has low false-positive risk

Add new checks to the appropriate heuristic category (H1-H6) with a severity rating. DEC-001 interaction logs will be a source of new check candidates once implemented.

---

## Part 7: Interaction Log Processing (template repo only)

Processes cross-project session exports when `/health-check` runs in the template repo. Skipped in downstream projects.

**Detection:** Check if a `template-maintenance/` directory exists at the project root (template repo indicator). If not, skip this part entirely.

### Process

1. **Check inbox:** Enumerate **every** file in `interaction-logs/inbox/`, **including dot-prefixed (hidden) names**, then filter that full listing to `.json`. Use one of these two verified commands:

   ```bash
   find interaction-logs/inbox -maxdepth 1 -type f -name '*.json'   # preferred
   ls -a interaction-logs/inbox/                                     # then filter to .json
   ```

   **Do NOT** enumerate with a bare `*.json` shell glob, plain `ls`, or the Glob tool with pattern `*.json` — all three silently exclude leading-dot filenames, and an empty result is indistinguishable from "none pending" (the `rules/agents.md § "Negative Findings Require a Positive Control"` hazard, applied to file enumeration). Exports reach the inbox dot-prefixed whenever a producer copies the workspace working file without renaming it — see `support/reference/context-transitions.md § "Session Export"` step 6, whose rename rule this step is the backstop for.

   **This has failed twice.** 19 exports accumulated unseen before 2026-06-11; four more (dated 2026-06-11 through 2026-07-02) were still in the inbox after the 2026-07-19 harvest reported it cleared, and surfaced only on 2026-08-12. Verify your enumeration is dotfile-inclusive before reporting a count.

2. **If empty:** Report "No pending interaction logs" and continue — but only after confirming the enumeration in step 1 was dotfile-inclusive.
3. **For each export file:**
   a. Validate format (`export_version` required)
   b. **Dispatch by `kind` field:**
      - `kind: "user_feedback"` → go to step 3c (user-tagged feedback bridge from `/feedback template:`)
      - Otherwise (no `kind`, or other value) → go to step 3d (session export with markers + optional assessment)
   c. **User-feedback routing:**
      - Read `template-maintenance/feedback.md` AND `template-maintenance/feedback-archive.md`
      - Parse all `## FB-NNN:` headings to find the highest `FB-NNN`; next ID is `FB-{N+1}` (zero-padded to 3 digits)
      - Construct the proposed entry:
        ```markdown
        ## FB-NNN: [feedback.title]

        **Status:** new
        **Captured:** [captured_date]
        **Source:** Bridged from {source_project} {feedback.source_fb_id} (template_version {template_version}) via /feedback template:

        [feedback.body]
        ```
      - Queue the proposed entry as a fix item (`⚠ unreviewed append` — excluded from bare `[A]`; the full entry text is viewable via the triage table's `[D]`). Never append silently — the visible row + explicit inclusion preserves the "Claude does not make decisions for the user" rule.
      - If included: append to `template-maintenance/feedback.md`; move processed file to `interaction-logs/processed/`.
      - If excluded: leave the file in `inbox/` so the user can re-run `/health-check` later.
   d. **Session-export marker parsing:**
      - Parse friction markers by template area:
        - `verify-agent` — verification failures, false positives, verification gaps
        - `implement-agent` — workflow deviations, scope creep, template gaps
        - `/work` — routing issues, session recovery problems
        - `/iterate` — spec change friction, drift issues
        - `design-guidance` — pushback opportunities, scope pivot detection
        - `user-experience` — dashboard issues, interaction mode mismatches
      - If Claude assessment is present (`export_quality: "full"`), extract design pushback opportunities and workflow friction notes
      - Move processed file to `interaction-logs/processed/`

4. **Aggregate across processed exports:**
   - Count recurring friction types (same `template_area` + similar `type` across multiple sessions/projects)
   - Flag patterns with 3+ occurrences as high-confidence insights

5. **Generate insights** for high-confidence patterns:
   - Write insight documents to `interaction-logs/insights/`
   - Format: `YYYY-MM-DD_{template-area}_{slug}.md`

6. **Route to `template-maintenance/feedback.md`:** For high-confidence patterns from step 5, construct proposed feedback items as new `FB-NNN` entries in `template-maintenance/feedback.md` (status: `new`, body references the insight document). Queue each proposed entry as a fix item (`⚠ unreviewed append` — excluded from bare `[A]`; full text via `[D]`) rather than prompting per entry.

   When `/health-check` runs in the template repo, `template-maintenance/feedback.md` is the destination per root `CLAUDE.md` — `.claude/support/feedback/feedback.md` is the *shipped* path reserved for downstream projects only. (User-feedback bridges from step 3c also land here.)

7. **Report:**
   ```
   Interaction Logs:
     Processed: {N} new exports ({M} full, {P} markers-only)
     Patterns detected: {X} ({Y} high-confidence)
     Feedback items created: {Z}
     Inbox: {remaining} pending
   ```

---

## Part 8: Audit Dispatch

Discovers and dispatches project-applicable audit commands. Audits live in `.claude/commands/audit-*.md` (template-shipped or project-local) and self-declare their applicability via `applies_when` frontmatter. This Part is the user-facing entry point for running audits — it surveys what's applicable, presents a menu, and dispatches the user's selection.

Audits complement Parts 1-7: where Parts 1-7 are automated validation/processing that runs unconditionally, Part 8 is interactive — the user picks which audits to run based on what they want to investigate. See `template-maintenance/audit-command-family-proposal.md` for the full audit family design (commands, friction register, dashboard digest, [Fix it] mechanism, bundled apply).

### Discovery

1. Glob `.claude/commands/audit-*.md`. For each, parse YAML frontmatter:
   ```yaml
   ---
   applies_when:
     any_file_exists: ["..."]               # at least one glob pattern must match a real file
     # OR
     package_json_has_dep: ["..."]          # at least one listed dep must appear in package.json
   estimated_runtime: "..."                  # informational, e.g., "2-3 min"
   prerequisites: ["..."]                    # informational, e.g., ["dev server reachable at {url}"]
   ---
   ```
2. Evaluate each `applies_when` against project state:
   - `any_file_exists`: true if at least one glob pattern matches a real file
   - `package_json_has_dep`: true if at least one listed dep appears in `dependencies` or `devDependencies` of any `package.json` in the project tree
3. Build the applicable-audits list. Audits whose `applies_when` evaluates false are silently skipped (not shown in menu).

### Menu Presentation

If 0 applicable audits: print `No audits applicable for this project shape.` and skip Part 8.

If 1+ applicable audits: present the menu inline:

```
Audits available for this project:

  [1] coherence  — spec/decision/path drift detection (~2-3 min)
  [2] ui         — web app surface walk + 7 quality lenses (~5-7 min, requires dev server)
  [A] all applicable
  [S] skip

Pick one or more (e.g., "1,2"), or skip:
```

Prompt the user. Accept comma-separated numbers, "A" / "all", or "S" / "skip" (default).

### Dispatch

For each selected audit:

1. **Pre-flight prerequisites.** If the audit's `prerequisites` list mentions "dev server reachable at {url}" or similar, attempt verification (curl the URL). If unreachable, print the audit's pre-flight error and SKIP this audit (continue with others, don't fail Part 8).
2. **Invoke the audit command.** The audit runs in the same conversation context (commands are loaded as instructions). Sequence: dispatch one at a time — audits are internally parallel via lens sub-agents; sequencing across audits keeps output legible and avoids MCP collisions (per `.claude/support/reference/mcp-patterns.md` § "MCP and Parallel Execution" — `/audit-ui` uses Playwright MCP which can't be safely fanned out across parallel command invocations either).
3. **Capture digest.** Each audit writes `findings.md` and `digest.json` to `.claude/support/audits/{audit}-{ts}/`. Record the digest path for the aggregate summary.

### Aggregate Output

After all selected audits complete, print a combined summary:

```
Audit results:

  /audit-coherence (2026-05-15 14:30Z):
    23 raw findings → 8 clustered (3 bundle-eligible, 5 promote-eligible, 2 deduped to pending tasks)
    Report: .claude/support/audits/coherence-2026-05-15-1430/findings.md

  /audit-ui (2026-05-15 14:35Z):
    47 raw findings → 18 clustered (1 bundle-eligible, 17 promote-eligible, 4 deduped to pending tasks)
    Report: .claude/support/audits/ui-2026-05-15-1435/findings.md

To act on findings:
  Promote to feedback: /audit-{name} promote {audit-ts}
  (Stages 6-7 will add [Fix it] inline + bundled-apply batch UX — see audit family proposal)
```

Stage 6 has shipped — pending digest items surface automatically as Audit Findings rows on the dashboard's "Needs you" card (id + description; the read-only HTML has no `[Fix it]` token or checkbox). Act on them via the CLI: `/audit-{name} triage` (per-finding fix/promote/dismiss), `/audit-{name} fix {ts} {id}`, `/audit-{name} promote {ts} {id},{id}`, or a natural-language dismiss. The inline summary + manual review of `findings.md` + `/audit-{name} promote {ts}` remains a complementary surface for context beyond what the dashboard digest shows.

### Skip Conditions

Part 8 is skipped entirely if:
- 0 applicable audits exist (silent — print one line, no menu)
- The user selects `[S]` from the menu
- (Future) Running with a `--no-audits` flag — not implemented yet; defer until pattern observed

### Edge Cases

- **Audit command malformed.** If `applies_when` parsing fails for a specific audit file, log a warning to chat (`Audit command audit-{name}.md has malformed applies_when — skipping.`) and continue. Don't fail the entire health-check.
- **Audit invocation fails mid-run.** If an audit errors out (capture phase fails, lens agent fails, etc.), the audit's own error handling kicks in. Part 8 captures the failure (which audits succeeded vs failed) and continues to the next selected audit.
- **Project-local audits.** A project may have its own `.claude/commands/audit-{custom}.md`. Part 8 discovers and surfaces these alongside template-shipped audits — no special treatment in the menu (just labeled by the audit name from the file). See Component 9 of the audit family proposal for the project→template graduation pattern.
- **Sub-mode invocations like `/audit-coherence promote {ts}`.** Part 8 only dispatches the audit-run mode (no positional args); it does NOT dispatch promote / fix-it / etc. Those are direct user invocations of the audit command, outside Part 8's scope.

---

## Process

### Step 1: Scan

```
READ all .claude/tasks/task-*.json files
READ .claude/dashboard.html
READ .claude/spec_v{N}.md (current spec — for completion gate checks)
READ .claude/CLAUDE.md
READ ./CLAUDE.md (root, if exists)
SCAN .claude/rules/ for rule files
READ all .claude/support/decisions/decision-*.md files
  (template repo: if template-maintenance/ exists at root, READ decisions/decision-*.md
   instead — .claude/support/decisions/ is the empty shipped placeholder here; the real
   template decision records live in root decisions/. See Part 3 § Repo-type branch.)
READ .claude/version.json (template version info)
READ .claude/sync-manifest.json (file categories)
SCAN .claude/support/previous_specifications/ for archived specs
SCAN .claude/support/workspace/ for stale files
SCAN for misplaced spec files in non-canonical locations
RUN fingerprint.py --baseline .claude (Part 1 check 11; read-only)
FETCH template remote (non-git project: temporary clone), RUN sync-check.py (skip if offline)
```

### Step 2: Run Checks

- Part 1: Task system validation (checks 1-11)
- Part 2: Instruction files audit (2a: template alignment, 2b: root bloat, 2c: rules validation)
- Part 3: Decision system validation (checks 1-7)
- Part 4: Archive validation (checks 1-4)
- Part 5: Template sync + collision + settings checks
- Part 6: UX evaluation (checks 1-5)
- Part 7: Interaction log processing (template repo only)
- Part 8: Audit dispatch (interactive — present applicable audits, dispatch user selection)

### Step 3: Report

**Report sections:**
- Task System — Schema & Integrity (checks 1-6, 11)
- Task System — Verification Debt (check 7)
- Task System — Dashboard Freshness (check 10)
- Task System — Out-of-Spec Tasks (check 9, if any exist)
- Workspace (check 8)
- Instruction Files — Template Alignment (Part 2a)
- Instruction Files — Root CLAUDE.md Bloat (Part 2b)
- Instruction Files — Rules Validation (Part 2c)
- Decision System (Part 3)
- Archive Validation (Part 4)
- Template Sync (Part 5)
- Command & Settings (Parts 5b, 5c)
- UX Evaluation (Part 6)
- Interaction Logs (Part 7, template repo only)
- Summary (overall status: HEALTHY / NEEDS ATTENTION / CRITICAL ISSUES)

Each section uses `✓` for passes, `⚠️` for warnings, `❌` for errors.

### Step 4: Batch Fix Triage (one consolidated prompt)

Render the fix queue (collected per the Fix Queue Protocol) as ONE table after the report, and take ONE response. If the queue is empty, skip silently (Part 5 Step 5 still runs when it applies). If `--report` flag is set, skip this step and show report only.

```
Proposed fixes (7):

| # | Part | File | Proposed fix | Risk |
|---|------|------|--------------|------|
| 1 | 1  | .claude/dashboard.html          | Regenerate (stale hash + format)          | — |
| 2 | 3  | decision-004-*.md               | Move trailing comment off the `status:` line | — |
| 3 | 5  | .claude/commands/work.md        | Update template file (locally modified, [D] shows the diff) | ⚠ overwrites local |
| 4 | 5  | .claude/rules/dashboard.md      | Update template file (unchanged copy of v5.4.0; includes dashboard regen) | — |
| 5 | 2d | claude-code-authoring.md        | Run [V] verify-against-docs pass ("5: defer" suppresses 30d) | — |
| 6 | 7  | template-maintenance/feedback.md | Append FB-097 "verify-agent: …"            | ⚠ unreviewed append |
| 7 | 1  | task-12.json                    | Stale In Progress (9d) — reply "7: pending / on-hold / blocked / keep" | needs-input |

One response resolves the queue:
  [A] apply all unflagged (⚠ and needs-input rows excluded — listed back as still-open)
  "A except 1,2" — exclude specific unflagged rows
  "A include 3,6" — ⚠ rows apply only on explicit inclusion by id
  [N] none
  "[D] 3,6" — show full diffs / full text for those ids first, then re-prompt (the [D] round doesn't consume the response)
  Per-item answers combine freely: "A include 3, 5: defer, 7: on-hold"
```

**Apply mechanics:**

- Apply included fixes in part order (1 → 7). Dashboard regeneration runs at most once, last — dedupe Part 1 regen rows with sync-triggered regens.
- A fix that fails to apply does not abort the batch: report it in the post-apply summary and continue.
- Part 1 baseline rows (check 11) are applied by `fingerprint.py --baseline … --write`, one call for the `stamp_history` row and one, with `--confirm-current`, for each confirmed `confirm_current` row. Never write those fingerprints by hand.
- `needs-input` rows without an answer in the response stay open — list them back ("Still open: 7 — stale In Progress task-12") so nothing silently drops.
- Interactive sub-flows of included rows (Part 2d `[V]`, Part 2a `merge`) run after the batch applies, one at a time.
- Post-apply summary: what was applied, what failed, what remains open.
- After the post-apply summary, run Part 5 Step 5 (commit offer) when it applies.

---

## Edge Cases

**Empty task list:** Reports "0 tasks — all checks pass" (healthy state for new projects)

**Large root `./CLAUDE.md` (>200 lines):** Flags as error, suggests extracting sections to `.claude/support/reference/project-*.md`

**`.claude/CLAUDE.md` deviations:** Reports diff summary; revert/keep/merge choice rides the fix queue as a `needs-input` row (only for a locally modified file; an unchanged copy of an older template version is a Part 5 update row)

**Subtask ID collisions:** Detects `5_1` already exists before creating duplicate

**No decision records:** Reports "0 decisions — all checks pass" (healthy state for new projects)

**Malformed frontmatter:** Flags as error, requires manual YAML fix

**Missing version.json or sync-manifest.json:** Template sync skipped with informational note

**Template repo unreachable:** Template sync skipped gracefully, other checks still run

**Project is not a git repository:** Template sync runs against a temporary clone of the template (Part 5 Step 1); no commit offer

---

## When to Run

- Start of a work session
- After extensive task operations
- When something feels "off"
- Before major handoffs
- Periodically (weekly recommended for tasks and template sync, monthly for instruction files audit)

## Reference

Task schema: `.claude/support/reference/task-schema.md`
Difficulty guide: `.claude/support/reference/shared-definitions.md`
Workflow guide: `.claude/support/reference/workflow.md`
Decisions reference: `.claude/support/reference/decisions.md`
Template config: `.claude/version.json`, `.claude/sync-manifest.json`
