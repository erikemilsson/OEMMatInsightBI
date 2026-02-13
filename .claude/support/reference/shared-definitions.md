# Shared Definitions

Rules, vocabulary, and glossary for the environment. For task JSON field definitions, validation, and structural details, see `task-schema.md`.

## Vocabulary

Canonical terminology used across the system.

| Term | Definition |
|------|------------|
| **Phase** | A logical stage of the project (e.g., Data Pipeline, Visualization). Phase N+1 can't begin until all Phase N tasks are complete. Implicit from spec structure; tasks get a `phase` field; dashboard groups by phase. |
| **Decision** | A choice with multiple viable options, tracked as a decision record (`.claude/support/decisions/decision-*.md`). Has comparison matrix, option details, optional weighted scoring, and a checkbox for the user to mark their selection. Dependent tasks are blocked until resolved. |
| **Inflection Point** | A decision where the outcome changes what gets built, not just how. After an inflection point is resolved, `/work` pauses and suggests running `/iterate` to revisit the spec before dependent work continues. Contrast with "pick-and-go" decisions where tasks simply unblock. Flagged with `inflection_point: true` in decision frontmatter. |
| **Human Task** | A task only the user can do — external actions like configuring secrets, setting up accounts, or providing credentials. Tracked with `owner: human` in task JSON. Decisions have their own mechanism (checkbox in decision doc) and are not human tasks. |

## Difficulty Scale (1-10)

> **Calibrated for Claude Opus 4.6.** These difficulty ratings and breakdown thresholds assume Opus-level reasoning capability. Tasks rated 5-6 ("Substantial") are at the upper limit of what should be attempted without breakdown — Opus can handle the design decisions involved. Tasks at 7+ **must** be broken down regardless of model confidence.

| Level | Category | Action | Examples |
|-------|----------|--------|----------|
| 1-2 | Routine | Just do it | Fix typo, add field, update config, simple CRUD, single vendor lookup, update a contact list |
| 3-4 | Standard | May take multiple steps | OAuth integration, REST API with auth, compare 5+ vendor quotes and produce shortlist, research and summarize 3 options with pros/cons |
| 5-6 | Substantial | Design decisions needed | Full auth system (JWT + sessions + RBAC), payment integration, full vendor evaluation with site visits and scoring matrix, project timeline with dependencies and resource allocation |
| 7-8 | Large scope | **MUST break down first** | Microservice extraction from monolith, full DB migration (schema + data + rollback), complete procurement process (research + quotes + negotiation + contracts) |
| 9-10 | Multi-phase | **MUST break down into phases** | Platform migration (e.g., Rails → Next.js), architecture redesign, full project delivery (research → planning → procurement → execution → validation) |

### When to Break Down

- Difficulty 1-6 → execute directly
- Difficulty 7-8 → break into chunks
- Difficulty 9-10 → break into phases

## Status Values

| Status | Meaning | Rules |
|--------|---------|-------|
| Pending | Not started | Ready to work on |
| In Progress | Currently working | Multiple allowed when parallel-eligible (see below) |
| Awaiting Verification | Implementation done, needs verification | Must proceed to verify-agent immediately |
| Blocked | Cannot proceed due to specific blocker | Document blocker in notes |
| On Hold | Intentionally paused | Document reason in notes; not auto-routed by `/work` |
| Absorbed | Scope folded into another task | Set `absorbed_into` field; preserves audit trail |
| Broken Down | Split into subtasks | Work on subtasks, not this |
| Finished | Complete and verified | Requires `task_verification.result` of "pass" |

### Blocked vs On Hold

These statuses represent different situations:

- **Blocked** — A specific, identifiable impediment prevents progress (unresolved dependency, failed verification, missing prerequisite). The task will resume once the blocker is cleared. `/work` tracks and surfaces blockers.
- **On Hold** — The task is intentionally paused for reasons that aren't a direct blocker: user chose to defer it, waiting on an external timeline, lower priority than current focus, seasonal or calendar constraint. The task will resume when the user explicitly moves it back to Pending.

## Priority, Owner, and JSON Fields

See `task-schema.md` for priority values, owner values with examples, drift prevention fields, task verification, and all JSON field definitions.

## Section Parsing Algorithm

Spec files are parsed into sections for fingerprinting: each `##` heading starts a new section that includes all content until the next `##` or EOF (including `###` subsections). YAML frontmatter is stripped first, and H1 headings are ignored. Fingerprint: `sha256(heading + "\n" + content)`.

## Mandatory Rules

**ALWAYS:**
1. Break down tasks with difficulty >= 7 before starting
2. Dashboard regenerates automatically after task changes
3. Parent tasks auto-complete when all subtasks finish (Absorbed subtasks are excluded from this check — they don't block parent completion)

**Parallel Execution Rules:**
Multiple "In Progress" tasks are allowed when ALL of these conditions are met:
- All dependencies for each task are "Finished"
- `files_affected` arrays do not overlap between any tasks in the batch
- All tasks in the batch belong to the current active phase (no phase dependency blocks any task)
- Batch size does not exceed `max_parallel_tasks` (default: 3)
- Each task has difficulty < 7

When conditions are not met, fall back to sequential execution (one "In Progress" at a time).

**NEVER:**
- Work on "Broken Down", "On Hold", or "Absorbed" tasks directly
- Skip status updates
- Dispatch parallel tasks without checking file conflicts
- Move "On Hold" tasks back to "Pending" without user approval

## Task ID Conventions

| Pattern | Meaning | Example |
|---------|---------|---------|
| `N` | Top-level task | `1`, `2`, `3` |
| `N_M` | Sequential subtask | `1_1`, `1_2` (must do in order) |
| `N_Ma` | Parallel subtask | `1_1a`, `1_1b` (can do simultaneously) |

Use underscores for sequential dependencies, letters for parallel work within a sequence. Tasks using the `N_Ma` convention are natural candidates for parallel dispatch — they were designed to run concurrently. `/work` checks these alongside all other eligible tasks when building parallel batches.

---

## Glossary

Canonical definitions for terms used across the environment. Terms already defined in the tables above are not repeated.

### Workflow Phases

| Term | Definition |
|------|------------|
| **Spec** | The project specification at `.claude/spec_v{N}.md`. Single source of truth for what gets built. Frontmatter status: `draft`, `active`, or `complete`. |
| **Spec Phase** | First workflow phase. Define what needs to be built via `/iterate`. Exit: all blocking questions answered, acceptance criteria testable, human approved. |
| **Execute Phase** | Second workflow phase. Spec decomposed into tasks, worked in dependency order by implement-agent. Each task goes through per-task verification. Exit: all tasks Finished. |
| **Verify Phase** | Third workflow phase. Two tiers: **Tier 1** (per-task, runs during Execute after each implementation) and **Tier 2** (phase-level, runs once when all tasks Finished, validates full implementation against spec). |
| **Implementation Stage** | Organizational groupings within Execute: Foundation (setup), Core Features (main functionality), Polish (edge cases), Validation (testing). Not workflow phases. |

### Task Concepts

| Term | Definition |
|------|------------|
| **Subtask** | Child task from breakdown. ID `N_M` = sequential (do in order), `N_Ma` = parallel (do simultaneously). Parent auto-completes when all subtasks finish. |
| **Out-of-Spec Task** | Task not aligned with spec, created when user proceeds despite misalignment or verify-agent suggests improvements beyond acceptance criteria. Marked `out_of_spec: true`. Excluded from phase routing and completion conditions. |
| **Parallel-Safe Task** | Task with `parallel_safe: true`, eligible for parallel execution even with empty `files_affected`. Used for research/analysis with no file side effects. |

### Decision Concepts

| Term | Definition |
|------|------------|
| **Pick-and-Go Decision** | Default decision type. After resolution, blocked tasks simply unblock and `/work` continues. Any decision without `inflection_point: true`. |
| **Comparison Matrix** | Core of a decision record. Criteria-vs-options table forcing structured evaluation. Common criteria: Performance, Complexity, Cost, Ecosystem, Fit, Risk. |
| **Weighted Scoring** | Optional addition for high-stakes decisions. Each criterion gets a percentage weight, options scored 1–5. Makes evaluation explicit. |
| **Implementation Anchor** | Reference linking a decision to where it was realized. Added at `implemented` status. Fields: `file`, `line` (optional), `description`. Validated by `/health-check`. |
| **Spec-Level Choice** | Choice defining requirements or user-visible behavior (the "what"). Changes require spec revision. |
| **Implementation-Level Choice** | Choice defining tools or technical details (the "how"). Changes don't require spec revision. |

### Spec Drift

| Term | Definition |
|------|------------|
| **Spec Drift** | When spec changes after tasks were decomposed from it. Detected by comparing current spec hash against task fingerprints. |
| **Drift Deferral** | When user selects "Skip section" during reconciliation. Recorded in `.claude/drift-deferrals.json` with timestamp. |
| **Drift Budget** | Limit on unreconciled drift. Configured via `drift_policy` in spec frontmatter: `max_deferred_sections` (default: 3), `max_deferral_age_days` (default: 14). Enforced by `/work`. |
| **Reconciliation** | Updating tasks to match a changed spec. Options per section: apply suggestions, review individually, skip (creates deferral), mark out-of-spec. |

### Verification

| Term | Definition |
|------|------------|
| **Per-Task Verification (Tier 1)** | Runs after each task implementation. Checks: files exist, spec alignment, output quality, runtime validation, integration readiness, scope validation. Pass → Finished. Fail → back to In Progress (max 2 retries). |
| **Phase-Level Verification (Tier 2)** | Runs once when all tasks Finished. Validates full implementation against spec acceptance criteria. Result: `pass` or `fail`. Written to `.claude/verification-result.json`. |
| **Verification Debt** | Tasks that bypassed or failed verification: status "Awaiting Verification", "Finished" without `task_verification`, or `task_verification.result` is "fail". Blocks project completion. |

### Runtime Validation & Interaction

| Term | Definition |
|------|------------|
| **Runtime Validation** | Self-testing step (T4b) where verify-agent executes the built output to check correctness before involving a human. Applies to CLIs, TUIs, web UIs, APIs, and data pipelines. Result: `"pass"`, `"fail"`, `"partial"`, or `"not_applicable"`. |
| **Test Protocol** | Structured testing steps written to the task JSON when runtime validation is partial or human testing is needed. Contains step-by-step instructions with expected outcomes, step types (`command`, `interactive`, `visual`), and an estimated time. |
| **Interaction Mode** | Channel selection for human-involved tasks. `"dashboard"` (default) routes to dashboard "Your Tasks" for async review. `"cli_direct"` presents the task immediately in the CLI conversation for synchronous testing or confirmation. Set via `interaction_hint` field in task JSON. |
| **Guided Testing** | Interactive in-CLI testing flow where `/work` walks the user through test protocol steps one at a time. For `command` steps, Claude runs the command and shows output. For `interactive` and `visual` steps, the user tests and signals pass/fail. |

### Agents & Infrastructure

| Term | Definition |
|------|------------|
| **Implement-Agent** | Builder agent. Executes tasks, produces deliverables, self-reviews, marks "Awaiting Verification". Defined in `.claude/agents/implement-agent.md`. |
| **Verify-Agent** | Validator agent. Tests against spec, finds issues, handles both Tier 1 and Tier 2 verification. Defined in `.claude/agents/verify-agent.md`. |
| **Dashboard** | Project dashboard at `.claude/dashboard.md`. Primary communication channel during build phase. Regenerated after task changes. |
| **Dashboard Freshness** | Whether dashboard reflects current state. Detected by comparing `task_hash` (SHA-256 of sorted task_id:status pairs) against current computed hash. |
| **Workspace** | Temporary documents at `.claude/support/workspace/`. Subdirs: scratch, research, drafts. May be deleted between sessions. |
| **Vision Document** | Ideation document in `.claude/vision/`. Captures intent and philosophy. Run `/iterate distill` to extract a buildable spec. |
| **Feedback** | Project-level ideas and improvement thoughts captured via `/feedback` and stored in `.claude/support/feedback/`. Items flow through statuses: `new` → `refined` → `promoted` (into spec via `/iterate`) or `new` → `archived` (not relevant). Uses `FB-NNN` IDs. Distinct from per-task inline `FEEDBACK:{id}` markers in the dashboard. |
