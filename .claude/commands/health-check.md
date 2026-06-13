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
- `—` — safe to bundle: concrete fix, nothing locally-authored is lost (regen, add missing field, move entries between files).
- `⚠ overwrites local` — applying replaces locally-modified content: ALL sync-category file applies (Part 5), `.claude/CLAUDE.md` revert (Part 2a). Excluded from bare `[A]`; explicit inclusion required. Sync rows the sidecar hash-verifies as unmodified since last sync carry the annotation `(hash-verified: no local edits)` so inclusion is an easy call — but they are still ⚠, never bundled silently.
- `⚠ unreviewed append` — adds new ledger content the user hasn't read (Part 7 proposed FB entries). Excluded from bare `[A]`; review via `[D]` or include explicitly.
- `needs-input` — the fix can't be computed without an answer (which task to keep, a path, revert-vs-keep-vs-merge). The row carries the question and choices inline; resolved only by a per-item reply (`{id}: <answer>`). Bare `[A]` skips these; unresolved rows are reported as still-open, never silently dropped.

Where an auto-fix table entry says "Ask user: …", that question becomes the row's inline question — it does not become a mid-run prompt.

**Exceptions (still interactive):**
- **Part 8** (audit dispatch) keeps its menu — it gates expensive audit runs, not fixes.
- **Sub-flows of an explicitly included fix** — e.g., Part 2d's `[V]` verify pass adjudicates per-section diffs interactively once the user has included that row; the *offer* is batched, the flow's intrinsic judgments are not.

With `--report`, skip the queue and table entirely (report only).

---

## Part 1: Task System Validation

Detects and fixes drift from task management standards.

### Validation Checks

#### 1. Task JSON Schema Validation

Validates required fields (id, title, status, difficulty) and optional fields per `.claude/support/reference/task-schema.md`. Boolean fields (`parallel_safe`, `out_of_spec`, `out_of_spec_rejected`, `cross_phase`, `user_review_pending`) must be booleans when present — flag non-boolean values as schema violations.

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

#### 4. Dashboard Consistency

**Row matching:**
- Every task JSON has a corresponding row in dashboard
- Every row in dashboard has a corresponding task JSON
- Status, title, and difficulty match between JSON and dashboard
- Summary count is accurate

**Structure validation:**
- Required sections exist: `# Dashboard`, `## 🚨 Action Required`, `## 📊 Progress`, `## 📋 Tasks`, `## 📋 Decisions`, `## 💡 Notes`
- Sections in correct order
- Sections with unchecked toggles in the section toggle checklist are allowed to be missing
- Optional section (`## 👁️ Custom Views`) may appear between Decisions and Notes when toggled on

If dashboard content or structure is inconsistent, the fix is always: regenerate.

#### 4b. Dashboard State Sidecar

- `.claude/dashboard-state.json` should exist if dashboard.md exists
- If missing: WARNING — "Dashboard state sidecar missing. Next dashboard regeneration will create it."
- If present: validate JSON structure (required keys: user_notes, section_toggles, phase_gates, inline_feedback, custom_views_instructions, updated)
- Cross-reference: section_toggles should match the dashboard's SECTION TOGGLES checklist
- Cross-reference: phase_gates entries should match PHASE GATE markers in dashboard

#### 5. Status Rules

| Status | Rules |
|--------|-------|
| `Pending` | No special requirements |
| `In Progress` | Multiple allowed only when parallel-eligible: `files_affected` don't overlap, all deps satisfied, within `max_parallel_tasks` limit. **ERROR** if parallel conditions violated. |
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
- Finished tasks with empty `notes` (possible skipped self-review)
- Tasks that appear to have jumped from `"Pending"` to `"Finished"` without passing through `"In Progress"` and `"Awaiting Verification"`

**Completion gate checks (ERRORS):**
- If dashboard shows "Project Complete" or "100%" completion:
  - `.claude/verification-result.json` MUST exist with `result` of "pass"
  - ALL finished tasks MUST have passing `task_verification`
  - If either condition fails: ERROR — "Project marked complete without verification"
- Check for status mismatch: spec says "active" but dashboard shows "Complete" (or vice versa)

**Note:** Workflow bypass warnings are informational. Some tasks may legitimately have brief notes. The intent is to surface patterns, not block individual tasks.

**Acceptance-status authority (DEC-022):** `.claude/verification-result.json`'s `criteria[]` (rendered as the dashboard's `### Acceptance Criteria`) is the authoritative surface for "phase acceptance criteria met." If a project also renders acceptance criteria as inline `- [ ]` boxes in the spec, those are authored input, not live status — do not treat unticked spec boxes as a completion failure. `/audit-coherence`'s `acceptance-reconciliation` lens surfaces box-vs-`criteria[]` divergence advisorily.

**Script alternative:** `.claude/scripts/validate-tasks.py .claude/tasks` runs schema + verification-debt checks deterministically and prints a combined report. `--json` flag emits structured output for downstream consumption.

#### 8. Workspace Staleness

**Stale Workspace Files:**
- Files in `.claude/support/workspace/` older than 30 days
- Warning: "N workspace files are over 30 days old"

#### 9. Out-of-Spec Task Tracking

Reports tasks with `"out_of_spec": true` in a separate section of the report. Informational — out-of-spec tasks are valid but won't be verified against spec acceptance criteria.

#### 10. Dashboard Staleness

**Task state hash check:**
1. Compute: `python3 .claude/scripts/dashboard-render.py --task-hash` — the canonical convention (sha256 over sorted `id:status:difficulty:owner` rows, newline-joined + trailing newline). Hand-compute only when the script is unavailable. Do NOT use `fingerprint.py --dashboard-rollup` (different algorithm, for `/status`).
2. Read dashboard metadata block (if exists)
3. Compare hashes — if different, dashboard is stale

**Format staleness check:**
1. Read `template_version` from dashboard `<!-- DASHBOARD META -->` block
2. Read `template_version` from `.claude/version.json`
3. If they differ (or META field is absent), dashboard is format-stale
4. Report: "Dashboard generated with template {old} but current template is {new} — regenerate to apply format updates"

A dashboard can be content-stale (task hash mismatch), format-stale (template_version mismatch), or both. Either condition triggers regeneration in auto-fix.

**Stale "In Progress" tasks:**
- Tasks with status `"In Progress"` where `updated_date` (or `created_date`) is > 7 days old
- Indicates abandoned work or forgotten state updates

#### 11. Provenance Integrity

**Snapshot file existence:**
- For each task with `section_snapshot_ref`, verify the referenced file exists at `.claude/support/previous_specifications/{section_snapshot_ref}`
- Missing snapshot: WARNING — "Task {id} references snapshot `{ref}` which does not exist. Drift detection will fall back to full-spec comparison."

**Decision dependency format:**
- For each task with `decision_dependencies`, verify each entry matches pattern `DEC-\d+`
- Invalid format: ERROR — "Task {id} has malformed decision dependency `{value}`"

### Task Auto-Fixes

Per the Fix Queue Protocol: each detected issue queues one fix item; "Ask user: …" entries become `needs-input` rows with the question inline. Nothing here prompts mid-run.

| Issue | Auto-Fix |
|-------|----------|
| Dashboard inconsistent or structurally invalid | Regenerate dashboard.md |
| Dashboard stale (hash mismatch, format staleness, or missing metadata) | Regenerate dashboard.md with fresh metadata |
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
| Missing snapshot file | Informational only — drift detection degrades gracefully |
| Malformed decision dependency format | Ask user: correct or remove the entry |
| Stale workspace files (> 30 days) | List files, ask user: graduate to final location, or delete |
| Dashboard state sidecar missing | Create from current dashboard markers (or defaults if markers broken) |
| Sidecar/dashboard toggle mismatch | Update sidecar from dashboard markers (dashboard is more recent) |
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
1. If template remote is configured (Part 5), diff `.claude/CLAUDE.md` against `template/{default_branch}:.claude/CLAUDE.md`
2. If no template remote, compare against a known hash stored in `.claude/version.json` (field: `claude_md_hash`)
3. If the file has been modified locally, report the deviations and queue a `needs-input` fix item with the choices inline (reply `{id}: revert` / `{id}: keep` / `{id}: merge`):
   - **revert** — restore template version (⚠ overwrites local — explicit choice required, never bundled)
   - **keep** — acknowledge deviation (record in `version.json` as `claude_md_override: true`)
   - **merge** — show diff, decide line by line (interactive sub-flow once chosen)

**What to report:**
- ✓ if `.claude/CLAUDE.md` matches template
- ⚠️ if deviations found (with diff summary)
- ℹ️ if template remote not configured (skip check)

### Part 2b: Root `./CLAUDE.md` Audit

The root `./CLAUDE.md` contains project-specific instructions and is user-owned.

#### Missing File Detection

If `./CLAUDE.md` does not exist at the project root:
1. Report: ℹ️ "No root CLAUDE.md found — this file holds project-specific instructions for Claude"
2. Queue a fix item: create `./CLAUDE.md` from the template at `.claude/support/reference/root-claude-md-template.md` (risk `—`; new file, nothing overwritten)
3. If included in the triage response, copy the template to `./CLAUDE.md`; if excluded, note as informational and continue

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
   - On any accept, update the doc body for that section
   - After all sections processed, update the footer date to today + `template_version` from `.claude/version.json`
8. If the row is excluded: leave doc unchanged, leave footer unchanged (the warning resurfaces next run).
9. If the user replies `{id}: defer`: write a sentinel in `.claude/dashboard-state.json` (`capability_doc_defer_until: YYYY-MM-DD`, 30 days from today) to suppress the Part 2d warning until that date. Next `/health-check` after the defer-until date will surface the warning again.

**Why this matters:** the capability doc encodes load-bearing facts about Claude Code (turn-scoped `model:` / `effort:`, subagent isolation, MCP constraints, Agent tool model granularity, skill content lifecycle). These facts evolve as Claude Code ships features. The footer + lens combination keeps the reference doc honest without silent auto-sync (which would risk silent contradiction with current spec) and without requiring maintainer-driven version pinning (which decouples from Claude Code's release cadence). See DEC-017 for full rationale.

---

## Part 3: Decision System Validation

Validates the decision documentation system for schema compliance and consistency.

### Validation Checks

#### 1. Decision Record Schema

Each `decision-*.md` file must have valid frontmatter:

**Required fields:**
- `id` - Format: `DEC-NNN` (e.g., DEC-001, DEC-042). Must match `\d+` pattern after `DEC-`. The numeric portion must match the filename: `decision-{NNN}-*.md` → frontmatter `id: DEC-{NNN}`. Mismatch is an ERROR.
- `title` - Non-empty string
- `status` - One of: `draft`, `proposed`, `approved`, `implemented`, `superseded`
- `category` - One of: `architecture`, `technology`, `process`, `scope`, `methodology`, `vendor`, `ux`, `design`, `ui-ia`, `ui-content` (UI-side categories added per FB-074 — see `.claude/support/reference/decisions.md § Categories` for definitions)
- `created` - Valid date in YYYY-MM-DD format

**Optional fields:**
- `decided` - Date when decision was finalized
- `related.tasks` - Array of task IDs
- `related.decisions` - Array of decision IDs
- `spec_revised` - Boolean, set after `/iterate` processes an inflection point
- `spec_revised_date` - Date when spec was revised

#### 2. Dashboard Consistency

- Every decision file has a corresponding entry in the dashboard's Decisions table
- Every dashboard entry has a corresponding `decision-{NNN}-*.md` file
- Status in file frontmatter matches status in dashboard table

#### 3. Staleness Detection

- Decisions with status `draft` created > 30 days ago
- Decisions with status `proposed` created > 14 days ago without resolution

#### 4. Completeness (for approved/implemented)

Decisions with status `approved` or `implemented` must have:
- Non-empty Decision section (selected option and rationale)
- At least one option in the comparison table

#### 5. Implementation Anchor Validation

For decisions with status `implemented`:
- Must have non-empty `implementation_anchors` array
- Each anchor file path must exist in the project
- Report missing anchors as warnings

#### 6. Decision-Task Cross-Reference

Reports mismatches between decision `related.tasks` and task `decision_dependencies`:

**Decision → Task direction:**
- For each decision, check if referenced tasks have the decision ID in their `decision_dependencies`
- Report mismatches grouped by task status (Finished = most concerning, Pending = auto-fixable)

**Task → Decision direction:**
- For each task with `decision_dependencies`, verify each referenced `DEC-NNN` has a corresponding `decision-{NNN}-*.md` file
- Missing decision file: ERROR — "Task {id} references non-existent decision {DEC-NNN}"

This is a reporting check. The primary enforcement and interactive resolution happens in `/work` Step 2b.

### Decision Auto-Fixes

Per the Fix Queue Protocol: each detected issue queues one fix item; "Ask user: …" entries become `needs-input` rows with the question inline. Nothing here prompts mid-run.

| Issue | Auto-Fix |
|-------|----------|
| File missing from dashboard | Add entry to dashboard's Decisions table |
| Dashboard entry missing file | Remove orphan entry from dashboard |
| Status mismatch | Ask user which is correct, update the other |
| Stale draft (> 30 days) | Ask user: delete, or set reminder |
| Stale proposed (> 14 days) | Ask user: approve, reject, or extend |
| Implemented without anchors | Ask user: add anchors, or revert to approved |
| Anchor file not found | Report for manual review |
| Cross-reference mismatch (Pending task) | Add decision ID to task's `decision_dependencies` |
| Cross-reference mismatch (other status) | Report for manual review |
| ID/filename mismatch | Ask user: rename file or update frontmatter ID |
| Task references non-existent decision | Ask user: remove dependency or create the decision record |

### Non-Fixable Issues (Manual Required)

| Issue | Why Manual |
|-------|------------|
| Invalid frontmatter syntax | Need to examine YAML |
| Invalid status/category/ID value | Need to determine correct value |
| Missing required field | Need human input |
| Incomplete approved decision | Need Decision section content |

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

Checks whether the project's `.claude/` workflow files are up to date with the template repository using git-based comparison. Skipped in the template repo (mirror of Parts 5d / 7: `system-overview.md` at project root indicates the template repo, where syncing the template against itself is self-referential and meaningless — `template_repo` points to the same URL as `origin`).

### Purpose

The upstream template may improve commands, agents, and reference docs. This check uses the template repo as a git remote to compare sync files and present updates.

### Repo-type skip

Before running any sync step: if `system-overview.md` exists at the project root, skip Part 5 entirely and report `ℹ️ Template sync skipped (template repo — self-sync is a no-op)`. The template repo's `version.json::template_repo` points to itself; adding a `template` remote pointing to the same URL as `origin` and diffing against it produces no useful output. The template's own work uses normal git workflow (push to origin); downstream-project sync flow does not apply.

### Requirements

- `.claude/version.json` — contains `template_repo` (git URL) and `template_version`
- `.claude/sync-manifest.json` — defines `sync` (updatable) vs `customize` (user-owned) vs `ignore` (project data) file categories
- `git` available (no `gh` CLI dependency)

### Sync State Sidecar

Per-file last-synced state lives in `.claude/.sync-state.json` (gitignored, in `ignore` category). The sidecar lets Part 5 distinguish two diff shapes that look identical to a naive `git diff`:

- **Template content not yet applied** — local is byte-for-byte identical to the last-synced state; the diff is pure template movement. Default action: APPLY.
- **Modified upstream** — local differs from the last-synced state (user edited it post-sync, or the file has never been synced). User adjudicates.

**Schema:**

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

**Hash format:** full SHA-256 hex with `sha256:` prefix. Aligns with `fingerprint.py`, `task_hash`, `spec_fingerprint`, dashboard META — one hash convention across the template. Computed over the file's raw bytes via `shasum -a 256 <path>` (macOS) or `sha256sum <path>` (Linux).

**Lifecycle:**
- **Read** in Step 2 to classify per-file diffs.
- **Written/updated** in Step 4 after each successful sync — only files the user actually accepted get their `synced_hash` recorded/refreshed. Files the user skipped retain their prior entry (or remain absent if never synced).
- **Missing entries** (file not in sidecar) fall through to "Modified upstream" — graceful migration for pre-3.15.0 projects without a sidecar, and for files newly added to the `sync` manifest that haven't been synced yet.

**First-run population:** the sidecar appears silently the first time Part 5 applies updates after 3.15.0 ships. No user-facing announcement. The file is gitignored (in `sync-manifest.json` `ignore` array), so it doesn't surface in `git status`.

**Recovery:** if the sidecar is deleted or corrupted, Part 5 falls through to current behavior on the next run. The next successful sync repopulates it from the post-checkout file hashes.

### Process

#### 1. Setup Remote

Ensure the template repo is configured as a git remote named `template`:

```
IF "template" remote doesn't exist → git remote add template {template_repo}
IF "template" remote exists but URL differs from version.json → warn, ask to update
```

Fetch latest: `git fetch template` (fetch only, never merge or pull).

If fetch fails (offline, invalid URL) → report as informational, skip remaining sync checks.

#### 2. Compare Sync Files

Determine the template's default branch via `git remote show template` (typically `main`). Read `.claude/.sync-state.json` (see "Sync State Sidecar" above) if present; absence triggers fallback (every diff classifies as "Modified upstream"). For each file matching `sync` category patterns in `sync-manifest.json`, use `git diff` to compare the local version against `template/{default_branch}:.claude/...`.

Per-file status:
- **Up to date** — no diff
- **Template content not yet applied** — template differs from local AND `local_hash == sidecar.files[path].synced_hash`. The local file is byte-for-byte identical to the last-synced state; the diff is pure template movement. Default action in Step 3: APPLY.
- **Modified upstream** — template differs from local AND (sidecar entry is missing OR `local_hash != sidecar.files[path].synced_hash`). Local was modified post-sync, or has never been synced. Default action in Step 3: present diff for user adjudication (Apply / Keep / Show diff).
- **New in template** — file exists upstream but not locally
- **Local only** — exists locally but not in template (kept, never flagged)

Never compare `customize` or `ignore` category files.

**Compute `local_hash`:** `shasum -a 256 <path>` (macOS) or `sha256sum <path>` (Linux); prefix `sha256:` to the bare hex. Compare string-equal against the sidecar's `synced_hash`. The hash is over raw bytes — line-ending differences DO produce different hashes (intentional: a CRLF/LF normalization at sync time is a real change, not a no-op).

#### 3. Present Changes (report) and Queue Apply Rows

Group files by the per-file status from Step 2 and present them in the report — grouped and impact-annotated for bigger changes:

```
Template updates available (v1.5.0 → v1.6.0):

  Template content not yet applied (hash-verified: no local edits):
    .claude/support/reference/dashboard-regeneration.md (+12 -0 lines)

  Modified upstream (local edits — review before including):
    .claude/commands/work.md (+15 -8 lines)
    .claude/support/reference/paths.md (+3 -1 lines)

  New:
    .claude/support/reference/new-feature.md
```

**Grouping heuristic** (bigger changes): group related files by workflow area (e.g., a command and the reference docs it depends on) and state the impact per group, plus the per-file classification.

**Queue one fix item per file** (per the Fix Queue Protocol) instead of prompting:

- Sync-category file applies (both classifications) → `⚠ overwrites local`, excluded from bare `[A]`, explicit inclusion required. "Template content not yet applied" rows carry the `(hash-verified: no local edits)` annotation so inclusion is an easy call; "Modified upstream" rows carry the diff stats.
- "New in template" files → risk `—` (new file, nothing overwritten).

Exclusion = the old "Keep current": the sidecar entry is NOT updated, so the file resurfaces on the next sync. Full diffs are available pre-decision via the triage table's `[D]` (prints `git diff template/{branch}:<path> <path>`, truncated to ~100 lines with a "...truncated" marker) — the route for adjudicating ambiguous classifications, e.g. pre-3.15.0 projects without a sidecar (every diff falls into "Modified upstream"), or files genuinely modified locally where the user has forgotten what they changed.

#### 4. Apply Updates

Read the upstream `template_version` from `template/{default_branch}:.claude/version.json`.

For accepted changes:
- Check out the accepted files from `template/{default_branch}` into the working tree
- Update `template_version` in local `.claude/version.json` to match the upstream version
- **Update the sync-state sidecar** — for each file the user accepted, compute the new local SHA-256 (post-checkout) and write/update its entry in `.claude/.sync-state.json` under `files["<path>"].synced_hash`. Refresh top-level `last_full_sync_version` (to the upstream version just synced) and `last_full_sync_date` (current date, ISO 8601). If the sidecar doesn't exist yet, create it with `schema_version: "1.0"`. Files the user skipped retain their prior sidecar entries (or remain absent if never synced).
- Report what was changed

**Post-sync dashboard re-check:** If any included sync row touches a dashboard-rule file (`dashboard-regeneration.md`, `rules/dashboard.md`, or `shared-definitions.md`), the dashboard was generated with older format rules — regenerate it as part of applying that row (no extra prompt; the row's one-line description notes "includes dashboard regen", so the user sees the consequence before responding). This catches the ordering issue where Part 1 ran dashboard checks before Part 5 synced the new rules, and dedupes with any Part 1 regen row — the dashboard regenerates at most once per run, last. Regeneration follows `.claude/support/reference/dashboard-regeneration.md` (which is now the updated version).

### Key Rules

- **Actual file diffs required** — you MUST `git fetch template` and diff each sync file against the remote. Comparing `template_version` strings is NOT a substitute for file-level comparison. Version numbers can match while files diverge (e.g., local edits, partial syncs, template patches). The version number is only used for display and for updating `version.json` after applying changes.
- **Sync category only** — never touch `customize` or `ignore` category files
- **Local-only files are kept** — never suggest removing files that aren't in the template
- **No silent changes** — always present changes and get confirmation before applying
- **Fetch only** — never merge, pull, or rebase from the template remote
- **Sidecar populates silently on first sync** — `.claude/.sync-state.json` appears the first time Step 4 applies updates after 3.15.0. No user-facing announcement; the file is gitignored.
- **Sidecar absence is fine** — pre-3.15.0 projects (no sidecar) fall through to "Modified upstream" classification for every diff. Behavior matches pre-3.15.0; sidecar populates on the first successful sync.

### Report Format

**Up to date (no diffs in sync files):**
```
### Template Sync

✓ Template up to date (v1.5.0)
```

**Offline / fetch failed:**
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
   - Read the template's `.claude/settings.json` from the template remote (if configured and reachable — same fetch as Part 5). Skip this check if offline.
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

Validates the `template_inbox_path` configuration that powers the cross-project feedback bridge. Skipped in the template repo (mirror of Part 7's detection: `system-overview.md` at project root indicates the template repo, where bridging to itself is not meaningful).

### Process

1. **Repo-type detection:** If `system-overview.md` exists at project root, skip Part 5d entirely.

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

#### 1. Mermaid Diagram Readability (H3 — Visualization Integrity)

Parse Mermaid code blocks in `dashboard.md`. Count nodes in each diagram.

| Condition | Result | Severity |
|-----------|--------|----------|
| ≤15 nodes | Pass | — |
| 16-50 nodes without `%%critical-path-only` comment | Warn: "Mermaid diagram has {N} nodes — may be unreadable. Consider critical-path-only mode." | 2 |
| >50 nodes | Error: "Mermaid diagram has {N} nodes — will render unreadably small." | 3 |

#### 2. Workspace Document Graduation (H6 — Project Structure Clarity)

Count files in `.claude/support/workspace/` that are either: (a) linked from dashboard content, or (b) listed in `files_affected` of tasks with `owner: human` or `owner: both`.

| Condition | Result | Severity |
|-----------|--------|----------|
| 0-2 workspace files referenced | Pass | — |
| 3+ workspace files referenced by human/both tasks | Warn per file: "'{filename}' is in workspace but referenced by human task {id}. Consider moving to project root (e.g., `docs/`)." | 2 |

#### 3. User Notes Section Utilization (H5 — User-Input Effectiveness)

Check if the Notes section in `dashboard.md` contains only the default placeholder text after the project has 5+ completed tasks.

| Condition | Result | Severity |
|-----------|--------|----------|
| Notes has user content, or <5 tasks completed | Pass | — |
| Notes is default placeholder, 5+ tasks completed | Info: "Notes section is still the default placeholder. Add Quick Links or project-specific notes." | 1 |

#### 4. Action Required Actionability (H4 — Navigation)

**4a. Actionability.** Every item in the Action Required section should have a file link and a completion command or checkbox.

| Condition | Result | Severity |
|-----------|--------|----------|
| All items have links | Pass | — |
| Item missing link or action | Error per item: "Action Required item '{title}' has no link or completion command." | 3 |

**4b. Summary-shape content (FB-015 / FB-038).** Scan the Action Required section for retrospective content that violates the rule in `support/reference/dashboard-regeneration.md` § Action Item Contract ("must NOT include work summaries, completion reports, or recent-activity recaps").

Detection heuristics — flag if ANY match within the Action Required section:

- **Past-tense completion verbs** in item title or body (not in the imperative form): `finished`, `completed`, `shipped`, `fixed`, `Task {N} finished/completed`, `successfully added/removed`. Watch for false positives — "Complete the form" is imperative (OK); "Form completed" is retrospective (flag).
- **Forbidden sub-section headings:** `Recent Activity`, `Work Summary`, `Completed This Session`, `Recently Completed`, `Done` (as a section name, not a checkbox label).
- **Long prose items:** any single item with more than 2 paragraphs of prose. Legitimate actionable items rarely need that much explanation — the contract requires "just enough context to act."
- **Bulleted lists of finished work:** any bulleted list inside Action Required where >2 consecutive items start with past-tense verbs (e.g., "✅ Task 5 added X", "✅ Task 6 fixed Y").

| Condition | Result | Severity |
|-----------|--------|----------|
| No summary-shape content | Pass | — |
| Summary-shape match found | Error per match: "Action Required contains retrospective content: '{excerpt}'. Belongs in git log / task notes / nowhere — not the dashboard." | 3 |

When `4b` fires repeatedly across `/health-check` runs on the same project, the root cause is likely LLM emitter compliance rather than a documentation gap — escalate to FB-011 Family C (extract dashboard regeneration into a deterministic script, tracked in `template-maintenance/scripts-candidates.md`).

#### 5. Dashboard Length (H1 — Readability)

Count total lines in `dashboard.md`.

| Condition | Result | Severity |
|-----------|--------|----------|
| ≤300 lines | Pass | — |
| 301-500 lines | Warn: "Dashboard is {N} lines. Check that completed phases are collapsed." | 2 |
| >500 lines | Warn: "Dashboard is {N} lines — may be hard to scan. Review section toggles and phase collapsing." | 2 |

#### 6. Phase Collapsing Compliance (H2 — Information Density)

Check completed phases (all tasks Finished with passing verification) — they should be collapsed to a single summary line, not list individual tasks.

| Condition | Result | Severity |
|-----------|--------|----------|
| All completed phases collapsed | Pass | — |
| Completed phase lists >3 individual tasks | Warn per phase: "Phase {N} is complete but lists {X} individual tasks. Should be collapsed to summary line." | 2 |

### Extending the Check Catalog

New checks should be added when:
- A UX problem is observed in a real project (not hypothetical)
- The check has a clear structural signal (can be verified from file content, not rendering)
- The threshold has low false-positive risk

Add new checks to the appropriate heuristic category (H1-H6) with a severity rating. DEC-001 interaction logs will be a source of new check candidates once implemented.

---

## Part 7: Interaction Log Processing (template repo only)

Processes cross-project session exports when `/health-check` runs in the template repo. Skipped in downstream projects.

**Detection:** Check if `system-overview.md` exists at the project root (template repo indicator). If not, skip this part entirely.

### Process

1. **Check inbox:** Read `interaction-logs/inbox/` for `.json` files
2. **If empty:** Report "No pending interaction logs" and continue
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

Stage 6 has shipped — `bundle-eligible` digest items surface automatically on the dashboard's `🔍 Audit Findings` section with the inline `[Fix it]` token; other kinds render with an italicized kind annotation. Promote/Dismiss invocation patterns are documented in `dashboard-regeneration.md` § "Audit Findings sub-section" (tick + bulk CLI for promote; natural-language for dismiss). The inline summary + manual review of `findings.md` + `/audit-{name} promote {ts}` remains a complementary surface for context beyond what the dashboard digest shows.

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
READ .claude/dashboard.md
READ .claude/spec_v{N}.md (current spec — for completion gate checks)
READ .claude/CLAUDE.md
READ ./CLAUDE.md (root, if exists)
SCAN .claude/rules/ for rule files
READ all .claude/support/decisions/decision-*.md files
READ .claude/version.json (template version info)
READ .claude/sync-manifest.json (file categories)
SCAN .claude/support/previous_specifications/ for archived specs
SCAN .claude/support/workspace/ for stale files
SCAN for misplaced spec files in non-canonical locations
FETCH template remote and diff sync files (skip if offline)
```

### Step 2: Run Checks

- Part 1: Task system validation (checks 1-11)
- Part 2: Instruction files audit (2a: template alignment, 2b: root bloat, 2c: rules validation)
- Part 3: Decision system validation (checks 1-6)
- Part 4: Archive validation (checks 1-4)
- Part 5: Template sync + collision + settings checks
- Part 6: UX evaluation (checks 1-6)
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

Render the fix queue (collected per the Fix Queue Protocol) as ONE table after the report, and take ONE response. If the queue is empty, skip silently. If `--report` flag is set, skip this step and show report only.

```
Proposed fixes (7):

| # | Part | File | Proposed fix | Risk |
|---|------|------|--------------|------|
| 1 | 1  | .claude/dashboard.md            | Regenerate (stale hash + format)          | — |
| 2 | 3  | decision-004-*.md               | Add missing dashboard Decisions entry      | — |
| 3 | 5  | .claude/commands/work.md        | Apply template version (+15 -8)            | ⚠ overwrites local |
| 4 | 5  | .claude/rules/dashboard.md      | Apply template version (+4 -1; includes dashboard regen) | ⚠ overwrites local (hash-verified: no local edits) |
| 5 | 2d | claude-code-authoring.md        | Run [V] verify-against-docs pass ("5: defer" suppresses 30d) | — |
| 6 | 7  | template-maintenance/feedback.md | Append FB-097 "verify-agent: …"            | ⚠ unreviewed append |
| 7 | 1  | task-12.json                    | Stale In Progress (9d) — reply "7: pending / on-hold / blocked / keep" | needs-input |

One response resolves the queue:
  [A] apply all unflagged (⚠ and needs-input rows excluded — listed back as still-open)
  "A except 1,2" — exclude specific unflagged rows
  "A include 3,4" — ⚠ rows apply only on explicit inclusion by id
  [N] none
  "[D] 3,6" — show full diffs / full text for those ids first, then re-prompt (the [D] round doesn't consume the response)
  Per-item answers combine freely: "A include 4, 5: defer, 7: on-hold"
```

**Apply mechanics:**

- Apply included fixes in part order (1 → 7). Dashboard regeneration runs at most once, last — dedupe Part 1 regen rows with sync-triggered regens.
- A fix that fails to apply does not abort the batch: report it in the post-apply summary and continue.
- `needs-input` rows without an answer in the response stay open — list them back ("Still open: 7 — stale In Progress task-12") so nothing silently drops.
- Interactive sub-flows of included rows (Part 2d `[V]`, Part 2a `merge`) run after the batch applies, one at a time.
- Post-apply summary: what was applied, what failed, what remains open.

---

## Edge Cases

**Empty task list:** Reports "0 tasks — all checks pass" (healthy state for new projects)

**Large root `./CLAUDE.md` (>200 lines):** Flags as error, suggests extracting sections to `.claude/support/reference/project-*.md`

**`.claude/CLAUDE.md` deviations:** Reports diff summary; revert/keep/merge choice rides the fix queue as a `needs-input` row

**Subtask ID collisions:** Detects `5_1` already exists before creating duplicate

**No decision records:** Reports "0 decisions — all checks pass" (healthy state for new projects)

**Malformed frontmatter:** Flags as error, requires manual YAML fix

**Missing version.json or sync-manifest.json:** Template sync skipped with informational note

**Template repo unreachable:** Template sync skipped gracefully, other checks still run

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
