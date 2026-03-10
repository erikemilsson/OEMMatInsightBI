# Health Check

Combined system health check for tasks, decisions, instruction files, rules, and template sync.

## Usage
```
/health-check                    # Run all checks, offer fixes
/health-check --report           # Show issues only, no fix prompts
```

## Purpose

Manual maintenance tool that validates tasks, decisions, instruction files (`.claude/CLAUDE.md`, `./CLAUDE.md`, `.claude/rules/`), and template sync. Operational checks for `/work` are defined inline in `work.md`.

---

## Part 1: Task System Validation

Detects and fixes drift from task management standards.

### Validation Checks

#### 1. Task JSON Schema Validation

Validates required fields (id, title, status, difficulty) and optional fields per `.claude/support/reference/task-schema.md`.

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
- `task_verification.checks` should have all 6 keys (`files_exist`, `spec_alignment`, `output_quality`, `runtime_validation`, `integration_ready`, `scope_validation`) with pass/fail values (or `"skipped"` only when result is `"fail"` due to timeout). Note: `runtime_validation` additionally allows `"not_applicable"` and `"partial"` as valid non-error values.
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

#### 8. Workspace Staleness

**Stale Workspace Files:**
- Files in `.claude/support/workspace/` older than 30 days
- Warning: "N workspace files are over 30 days old"

#### 9. Out-of-Spec Task Tracking

Reports tasks with `"out_of_spec": true` in a separate section of the report. Informational — out-of-spec tasks are valid but won't be verified against spec acceptance criteria.

#### 10. Dashboard Staleness

**Task state hash check:**
1. Compute: `SHA-256(sorted list of task_id + ":" + status + ":" + difficulty + ":" + owner)`
2. Read dashboard metadata block (if exists)
3. Compare hashes — if different, dashboard is stale

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

| Issue | Auto-Fix |
|-------|----------|
| Dashboard inconsistent or structurally invalid | Regenerate dashboard.md |
| Dashboard stale (hash mismatch or missing metadata) | Regenerate dashboard.md with fresh metadata |
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
3. If the file has been modified locally, present the deviations and ask the user:
   - **Revert** — restore template version
   - **Keep** — acknowledge deviation (record in `version.json` as `claude_md_override: true`)
   - **Merge** — show diff, let user decide line by line

**What to report:**
- ✓ if `.claude/CLAUDE.md` matches template
- ⚠️ if deviations found (with diff summary)
- ℹ️ if template remote not configured (skip check)

### Part 2b: Root `./CLAUDE.md` Audit

The root `./CLAUDE.md` contains project-specific instructions and is user-owned.

#### Missing File Detection

If `./CLAUDE.md` does not exist at the project root:
1. Report: ℹ️ "No root CLAUDE.md found — this file holds project-specific instructions for Claude"
2. Offer to create one from the template at `.claude/support/reference/root-claude-md-template.md`
3. If the user accepts, copy the template to `./CLAUDE.md`
4. If the user declines, note as informational and continue

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

When a section exceeds the soft limit, offer these options:

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

**Expected files:** `task-management.md`, `spec-workflow.md`, `decisions.md`, `dashboard.md`, `agents.md`, `archiving.md`

**Checks:**
- Each expected file exists
- No expected file exceeds 200 lines
- User-created rule files (`project-*.md`) are noted as informational

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
- `category` - One of: `architecture`, `technology`, `process`, `scope`, `methodology`, `vendor`
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

### Archive Auto-Fixes

| Issue | Auto-Fix |
|-------|----------|
| Multiple spec files in `.claude/` | Archive lower versions, keep highest as current |
| Spec in wrong location | Move to `.claude/support/previous_specifications/` |
| Missing archived spec | Cannot auto-fix — warn user |
| Missing decomposed spec | Informational only |

---

## Part 5: Template Sync Check

Checks whether the project's `.claude/` workflow files are up to date with the template repository using git-based comparison.

### Purpose

The upstream template may improve commands, agents, and reference docs. This check uses the template repo as a git remote to compare sync files and present updates.

### Requirements

- `.claude/version.json` — contains `template_repo` (git URL) and `template_version`
- `.claude/sync-manifest.json` — defines `sync` (updatable) vs `customize` (user-owned) vs `ignore` (project data) file categories
- `git` available (no `gh` CLI dependency)

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

Determine the template's default branch via `git remote show template` (typically `main`). For each file matching `sync` category patterns in `sync-manifest.json`, use `git diff` to compare the local version against `template/{default_branch}:.claude/...`.

Per-file status:
- **Up to date** — no diff
- **Modified upstream** — template has changes the local copy doesn't
- **New in template** — file exists upstream but not locally
- **Local only** — exists locally but not in template (kept, never flagged)

Never compare `customize` or `ignore` category files.

#### 3. Present Changes

**Small changes** (few files, minor edits) — simple list with diff stats:

```
Template updates available (v1.5.0 → v1.6.0):

  Modified:
    .claude/commands/work.md (+15 -8 lines)
    .claude/support/reference/paths.md (+3 -1 lines)

  New:
    .claude/support/reference/new-feature.md

Apply these changes? [Y/N]
```

**Bigger changes** (structural, multi-file) — group related changes and explain impact:

```
Template updates available (v1.5.0 → v1.6.0):

1. Verification workflow update (3 files)
   - .claude/commands/work.md — new verification step
   - .claude/agents/verify-agent.md — updated check criteria
   - .claude/support/reference/workflow.md — updated process docs

   Impact: Adds scope validation to the verification process.

2. New reference file
   - .claude/support/reference/new-feature.md

   Impact: Documentation only. No effect on existing workflow.

Apply all / Select individually / Skip?
```

**Grouping heuristic:** Changes are "related" when they touch the same workflow area (e.g., a command and the reference docs it depends on, or multiple files in the verification pipeline).

#### 4. Apply Updates

Read the upstream `template_version` from `template/{default_branch}:.claude/version.json`.

For accepted changes:
- Check out the accepted files from `template/{default_branch}` into the working tree
- Update `template_version` in local `.claude/version.json` to match the upstream version
- Report what was changed

### Key Rules

- **Sync category only** — never touch `customize` or `ignore` category files
- **Local-only files are kept** — never suggest removing files that aren't in the template
- **No silent changes** — always present changes and get confirmation before applying
- **Fetch only** — never merge, pull, or rebase from the template remote

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

1. **Identify template commands** — known set: `work.md`, `iterate.md`, `breakdown.md`, `health-check.md`, `status.md`, `research.md`, `feedback.md`, `review.md`
2. **Scan `.claude/commands/`** for all `.md` files not in the template set
3. **Detect collisions:**
   - **Name collision:** custom file has same name as template command
   - **Functional overlap:** filename or content suggests overlap (e.g., `plan.md` → `/iterate`, `complete.md` → `/work complete`)
4. **Report** — list custom commands with any overlap warnings

Never delete or rename custom commands without user consent.

---

## Part 5c: Settings Conflict Detection

Checks for existing user settings files and confirms the template doesn't interfere.

### Process

1. Check for `.claude/settings.local.json` and `.claude/settings.json`
2. If found: report presence, confirm template doesn't ship settings files, note any restrictions that might affect agent workflows (e.g., restricted `Bash` may prevent test execution)
3. If not found: report as informational

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
- Summary (overall status: HEALTHY / NEEDS ATTENTION / CRITICAL ISSUES)

Each section uses `✓` for passes, `⚠️` for warnings, `❌` for errors.

### Step 4: Offer Fixes

For each fixable issue, present options and apply immediately before moving to next.

If `--report` flag is set, skip this step and show report only.

---

## Edge Cases

**Empty task list:** Reports "0 tasks — all checks pass" (healthy state for new projects)

**Large root `./CLAUDE.md` (>200 lines):** Flags as error, suggests extracting sections to `.claude/support/reference/project-*.md`

**`.claude/CLAUDE.md` deviations:** Presents diff and asks user to revert, keep, or merge

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
