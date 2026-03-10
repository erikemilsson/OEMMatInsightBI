# Workflow Guide

The Spec → Execute → Verify workflow for autonomous multi-phase projects.

## Overview

```
┌──────────┐    ┌──────────────────────────────────────────────────┐    ┌──────────┐
│   Spec   │ -> │                    Execute                        │ -> │  Verify  │
│          │    │                                                    │    │ (phase)  │
│ Define   │    │  ┌─ Parallel batch (when eligible) ─────────────┐ │    │          │
│ what     │    │  │ ┌──────────┐  ┌──────────┐  ┌──────────┐    │ │    │ Validate │
│          │    │  │ │impl → vfy│  │impl → vfy│  │impl → vfy│    │ │    │ all ACs  │
│          │    │  │ │ task A   │  │ task B   │  │ task C   │    │ │    │          │
│          │    │  │ └──────────┘  └──────────┘  └──────────┘    │ │    │          │
│          │    │  └──────────────────────────────────────────────┘ │    │          │
│          │    │       v (collect results, single dashboard regen)  │    │          │
│          │    │  next batch or sequential task...                  │    │          │
└──────────┘    └──────────────────────────────────────────────────┘    └──────────┘
     ^                                                                        │
     └──────────── (if issues found) ────────────────────────────────────────┘
```

Each parallel lane runs the full implement → verify cycle independently. The `/work` coordinator manages batching, result collection, and a single dashboard regeneration. When tasks are not parallel-eligible, execution falls back to the sequential one-at-a-time model shown below:

```
  ┌────────────┐   ┌────────────────┐
  │ Implement  │ -> │ Verify (task)  │
  │ task N     │   │ task N         │
  └────────────┘   └────────────────┘
       ^                │
       └── (if fail) ───┘
       v (if pass)
  next task...
```

---

## Phase Details

### Spec Phase

**Goal:** Define what needs to be built

**Activities:**
- Document problem statement
- Define goals and non-goals
- List requirements (functional and non-functional)
- Create testable acceptance criteria
- Identify constraints
- Make key architecture decisions

**Exit Criteria:**
- All blocking questions answered
- Acceptance criteria are testable
- Key decisions documented
- Scope is clear
- Human approved specification

**Process:** Manual (human-guided via `/iterate`)

To create or revise the spec, run `/iterate`. Claude will guide you through iterative Q&A but you edit the spec directly.

### Execute Phase

**Goal:** Build the implementation

**Activities:**
- Decompose spec into tasks (handled by /work if no tasks exist)
- Work through tasks in dependency order
- Create deliverables and files
- Self-review changes
- Per-task verification after each task completion
- Document completion notes
- Flag discovered issues

**Exit Criteria:**
- All tasks have status "Finished" with passing per-task verification (Absorbed tasks are excluded — they don't count as incomplete)
- No blocked tasks remain
- No "On Hold" tasks remain (user must resume, absorb, or remove them before phase exit)
- Deliverables follow project conventions
- Ready for phase-level verification

**Agent:** implement-agent

### Verify Phase

Verification operates in two tiers:

#### Tier 1: Per-Task Verification (during Execute phase)

**Goal:** Catch issues in each task immediately after completion

**When it triggers:** After implement-agent sets a task to "Awaiting Verification" status. Verification is triggered automatically as part of Step 6 in implement-agent, making implementation and verification atomic.

**Activities:**
- Verify file artifacts exist and match task description
- Check for undeclared modifications (scope validation)
- Check spec alignment against task description and spec section
- Validate output quality (no incomplete items, follows patterns)
- Runtime validation — self-test runnable outputs (CLIs, APIs, web UIs) before involving humans
- Check integration boundaries (dependencies consumed correctly, outputs match downstream expectations)

**Output:** `task_verification` field written to task JSON with per-check pass/fail. When runtime validation is partial, also writes `test_protocol` and `interaction_hint` for guided testing.

**What happens after per-task verification:**
- **Pass:** Task status set to "Finished" (from "Awaiting Verification"). `/work` proceeds to next pending task.
- **Fail:** Task set back to "In Progress". implement-agent fixes, then re-verification. The `verification_attempts` counter tracks attempts; after 3 total (initial + 2 retries), the task is escalated to human review as "Blocked".

#### Tier 2: Phase-Level Verification

**Goal:** Confirm the full implementation matches the spec's acceptance criteria

**When it triggers:** Automatically when `/work` detects all spec tasks are finished AND all have passing per-task verification (auto-detect mode), or manually when the user runs `/work` after completing all tasks.

**Activities:**
- Run existing test suite (if available)
- Validate each spec acceptance criterion individually
- Check quality, completeness, and integration
- Identify and categorize issues (critical/major/minor)
- Create fix tasks for issues found (in-spec bugs as regular tasks; recommendations as `out_of_spec: true`)
- Write verification result to `.claude/verification-result.json`
- Generate verification report for the user
- Reference per-task verification results as evidence for individual checks

**Output:** A structured report showing:
- Pass/fail status for each acceptance criterion
- Issues found, categorized by severity
- Tasks created for fixes (if any)
- Overall result: `pass` or `fail`

**What happens after phase-level verification:**
- **Pass:** `/work` transitions to Complete phase. Spec status updates to `complete`. Any out-of-spec recommendation tasks are presented to the user for approval at the phase boundary.
- **Fail:** Critical/major issues found where spec requirements aren't met. In-spec fix tasks are created (regular tasks, not out-of-spec). `/work` automatically routes them to implement-agent. Once fixes are done and all spec tasks pass per-task verification again, phase-level verification re-runs.

**Feedback loop — bug fixes (in-spec):**
1. verify-agent identifies issues where spec requirements aren't met
2. Fix tasks are created as **regular tasks** (not out-of-spec)
3. Verification result is set to `"fail"`
4. `/work` routes fix tasks to implement-agent automatically
5. When all spec tasks are finished again, phase-level verification re-runs

**Feedback loop — recommendations (out-of-spec):**
1. verify-agent identifies improvements beyond spec acceptance criteria
2. Recommendation tasks are created with `out_of_spec: true`
3. Verification result is `"pass"` (spec criteria met)
4. `/work` presents recommendations to user for Accept/Reject/Defer
5. Accepted tasks are executed independently; they don't block project completion

**Exit Criteria:**
- All acceptance criteria pass (or failures are documented and accepted)
- No critical issues remain
- Verification result persisted to `.claude/verification-result.json`
- Human approved final state

**Agent:** verify-agent (see `.claude/agents/verify-agent.md` for detailed workflow)

---

## Agent Synergy: Implement + Verify + Research

This project uses three specialist agents:

| Agent | Role | Focus |
|-------|------|-------|
| **implement-agent** | Builder | Executes tasks, produces deliverables, marks tasks finished |
| **verify-agent** | Validator | Tests against spec, finds issues, ensures quality |
| **research-agent** | Investigator | Gathers evidence for decisions, populates comparison matrices |

**Why three agents?**
A single agent implementing and validating its own work has blind spots.
By separating concerns:
- implement-agent focuses purely on building (no self-validation bias)
- verify-agent validates against the spec with fresh perspective
- research-agent investigates options without implementation or compliance bias
- Issues caught by verify-agent become new tasks for implement-agent
- Evidence gathered by research-agent feeds into decision records for human selection

**Architectural separation:** verify-agent and research-agent always run as **separate `Task` agents** (spawned via the Task tool), never inline in the implementation context. This ensures genuine independence — the verifier has no memory of implementation decisions, only the artifacts (task JSON, spec section, and files); the researcher has no implementation or compliance bias, only the decision record and project context. This applies to both sequential and parallel execution modes.

**The build workflow:**
1. `/work` reads and follows implement-agent workflow for the next pending task
2. implement-agent: build, self-review, update status to "Awaiting Verification"
3. implement-agent Step 6b: **spawn** verify-agent as a separate Task agent (fresh context)
4. verify-agent (separate context): verify files, spec alignment, quality, integration boundaries
5. If verification passes: status → "Finished", regenerate dashboard, back to step 1 for next task
6. If verification fails: status → "In Progress", back to step 1 (implement-agent fixes)
7. When all tasks have "Finished" status with passing verification, `/work` spawns verify-agent for phase-level workflow
8. verify-agent: test against spec acceptance criteria
9. Issues found become new tasks, back to implement-agent

**The research workflow:**
1. `/work` encounters an unresolved decision blocking a task (or `/research` is invoked directly)
2. research-agent is spawned with decision record and project context
3. research-agent: gathers options, evaluates against criteria, checks compatibility with existing decisions
4. research-agent: populates decision record comparison matrix and option details, writes research archive
5. research-agent: updates decision status to `proposed` (ready for user selection)
6. User selects option via checkbox → `/work` auto-updates status to `approved` → dependent tasks unblock

**The review workflow** (via `/review`):
1. User runs `/review` (or `/review {area}`) to assess implementation quality
2. Reviews implementation artifacts across completed tasks for quality patterns
3. Assesses: architecture coherence, integration quality, pattern consistency, cross-cutting concerns, technical debt, decision alignment
4. Presents findings and suggestions — purely advisory, no state changes
5. User applies suggestions manually, then continues with `/work`

This separation — both logical and contextual — produces higher quality output than a single agent could achieve alone.

---

## Parallel Execution

By default, `/work` dispatches multiple tasks concurrently when they are independent. Each parallel task still runs the full atomic implement → verify cycle. The coordinator manages batching, result collection, and a single dashboard regeneration.

Key constraints: verification remains per-task, dashboard regeneration is coordinator-only (parallel agents never regenerate), parent auto-completion is deferred, and phase-level verification stays sequential. Configure via `parallel_execution` in spec frontmatter (default: enabled, max 3 tasks).

**Full procedure:** `.claude/support/reference/parallel-execution.md` (eligibility criteria, file conflict algorithm, batch building, dispatch, incremental re-dispatch, and post-parallel cleanup).

---

## The `/work` Command as Coordinator

The `/work` command handles coordination (no separate orchestrator agent):

```
User → /work → Specialist Agent → /work → User
         ↓            ↓              ↓
    Analyze state  Do focused    Report results
    Check spec     work
```

**What `/work` handles:**
- Analyze current state
- Check requests against spec
- Decompose spec into tasks (when needed)
- Complete tasks (`/work complete`)
- Select appropriate agent
- Pass context to agent
- Trigger checkpoints
- Report progress
- Auto-sync dashboard after changes

---

## Handoff Protocol

### /work → Specialist

Provides: current phase, spec summary, recent activity, task to do, constraints (scope limits, prior decisions).

### Specialist → /work

Returns: what was completed, files modified, status updates, recommendations, issues encountered.

---

## Phase Transitions

### Spec → Execute

**Trigger:** Spec exists at `.claude/spec_v{N}.md` and is complete

**Handoff includes:**
- Specification document
- Acceptance criteria
- Constraints and requirements

**What /work does:**
- Verify spec exists and has content
- Update spec `status` from `draft` to `active`
- Decompose spec into tasks (if no tasks exist)
- Present checkpoint to human
- Read and follow implement-agent workflow for first available task

### Execute → Verify (Phase-Level)

**Trigger:** All execute tasks finished AND all passed per-task verification

**Handoff includes:**
- List of completed tasks with per-task verification results
- Files modified
- Any discovered issues
- Self-review notes and verification notes

**What /work does:**
- Present checkpoint to human
- Read and follow verify-agent phase-level workflow with implementation summary

### Verify → Complete

**Trigger:** Verify agent reports verification passed and writes a valid result to `.claude/verification-result.json`

**Handoff includes:**
- Test results
- Acceptance criteria validation
- Issues found (if any)
- Recommendations
- Persisted verification result (`.claude/verification-result.json`)

**What /work does:**
- Check `.claude/verification-result.json` for a valid passing result
- Update spec `status` from `active` to `complete`
- Update dashboard with completion summary
- Present final checkpoint to human
- Offer project-level learning capture prompt (skippable) — if shared, append to `.claude/support/learnings/project-learnings.md`
- Project complete (or loop back if issues)

**Verification result validity:** The result is valid when `result` is `"pass"`, `spec_fingerprint` matches the current spec, and no tasks changed since the verification `timestamp`. If the spec changes or new tasks appear, the result is automatically invalidated and `/work` re-routes to verification.

---

## Spec Status Transitions

The spec metadata `status` field tracks the project lifecycle:

| Status | Meaning | Trigger |
|--------|---------|---------|
| `draft` | Spec is being written | Initial creation |
| `active` | Spec is being implemented | Decomposition begins (Spec → Execute) |
| `complete` | All work done and verified | Verification passes (Verify → Complete) |

**Rules:**
- Only `/work` updates the spec status (not manual edits)
- Transitioning back from `complete` to `active` happens automatically when the spec is modified and new tasks are created
- The status is in the YAML frontmatter of `.claude/spec_v{N}.md`

---

## Human Checkpoints

Humans are involved at specific points, with the interaction channel chosen per-task to minimize friction. See **Interaction Modes and Runtime Validation** below for how `/work` selects between dashboard-mediated and CLI-direct interaction.

Checkpoint types:

### Phase Boundaries
When transitioning between phases:
- Spec → Execute: "Specification complete. Ready to implement?"
- **Phase N → Phase N+1** (within Execute): Surfaced as a dashboard Action Required item with a checkbox in a `<!-- PHASE GATE:{N}→{N+1} -->` marker. `/work` blocks until the user checks the box and re-runs. Once approved, the marker becomes `<!-- PHASE GATE:{N}→{N+1} APPROVED -->` so it won't re-trigger on subsequent runs. After approval, a lightweight learning capture prompt is offered (skippable).
- **Execute → Verify**: When all tasks are complete, the dashboard shows a "Verification Pending" item in Action Required, and the critical path displays "🤖 Phase verification → Done" instead of "All tasks complete!". Phase-level verification runs automatically on the next `/work`.
- Verify → Complete: "Verification passed. Ready to ship?"

### Spec Misalignment
When requests don't align with spec:
- /work surfaces the misalignment
- Options: add to spec, proceed anyway, or skip
- Keeps spec as source of truth

### Spec Drift (Granular Reconciliation)
When spec changes after tasks were decomposed:
- /work detects which specific sections changed
- Shows diff of changed content
- Groups affected tasks by section
- Options per section: apply suggestions, review individually, or skip
- Enables targeted updates without re-decomposing all tasks

### Quality Gate Failures
When something goes wrong:
- Tests fail
- Specification violations found
- Critical issues discovered

---

## Interaction Modes and Runtime Validation

Not all human involvement benefits from the dashboard. When a task needs human input, Claude selects the interaction channel that minimizes friction — sometimes the dashboard, sometimes direct CLI conversation.

### Interaction Mode Selection

| Mode | Channel | Best For |
|------|---------|----------|
| **Dashboard-mediated** | Dashboard "Your Tasks" / Action Required | Async tasks, extended reading, batch review, decisions needing think-time |
| **CLI-direct** | Claude Code conversation | Real-time testing, quick confirmations, command-guided walkthroughs, interactive feedback |

**Decision guidelines:**

| Factor | Dashboard-mediated | CLI-direct |
|--------|-------------------|------------|
| Timing | User will do it later (async) | User should do it now (synchronous) |
| Duration | Extended (reading docs, thinking through decisions) | Quick (run a command, confirm output, yes/no) |
| Terminal needed? | No | Yes — commands to run, output to check |
| User's current context | Not necessarily in CLI | Already in CLI conversation |
| Multiple items | Batch of unrelated items → dashboard | Single focused task → CLI |
| Interaction type | Passive review (read, think, decide) | Active testing (run, observe, respond) |

**How it integrates:**
- Verify-agent writes an `interaction_hint` field (`"cli_direct"` or `"dashboard"`) to the task JSON when it determines human involvement is needed
- `/work` respects the hint when routing human tasks — CLI-direct tasks are presented immediately in the conversation rather than only appearing in dashboard "Your Tasks"
- The hint is a suggestion, not a gate — users can always override by running `/work complete {id}` from the dashboard flow
- When absent, defaults to `"dashboard"` (preserves current behavior)

### Runtime Validation

Verify-agent can self-test runnable outputs before escalating to human testing. This happens in per-task verification Step T4b (between Output Quality and Integration Boundaries).

**What it tests:**

| Output Type | Approach |
|-------------|----------|
| CLI/script | Run via Bash, validate stdout/stderr |
| TUI | Run with `--help`/non-interactive flags, validate output |
| Web UI | Playwright (`browser_navigate`, `browser_snapshot`) to check structure |
| API | HTTP requests via curl, validate response status/body |
| Data pipeline | Run pipeline, check output structure |

**Results:** `"pass"`, `"fail"`, `"partial"` (some need human eyes), or `"not_applicable"` (non-runnable output).

**Key principle:** Runtime validation is best-effort and additive. A `"not_applicable"` result doesn't affect verification. Only `"fail"` contributes to verification failure.

### Guided Testing

When runtime validation is `"partial"`, or when an `owner: "both"` task has runnable output, verify-agent writes a **test protocol** — a structured set of testing steps. Combined with `interaction_hint: "cli_direct"`, this enables guided testing directly in the CLI conversation.

**Test protocol schema:**

```json
{
  "test_protocol": {
    "summary": "Brief description of what to test",
    "steps": [
      {
        "instruction": "What to do",
        "expected": "What should happen",
        "type": "command|interactive|visual",
        "command": "optional — the command to run (for 'command' type)"
      }
    ],
    "automated_results": "What runtime validation already confirmed",
    "estimated_time": "Human-readable estimate"
  }
}
```

**Step types:**
- `"command"` — Claude runs it and shows output; user confirms pass/fail
- `"interactive"` — User interacts with the running application; signals pass/fail
- `"visual"` — User inspects a screenshot or visual output; confirms appearance

**The flow in `/work`:**
1. Task passes per-task verification with `runtime_validation: "partial"`
2. Verify-agent writes `test_protocol` + `interaction_hint: "cli_direct"`
3. `/work` presents guided testing immediately in the CLI conversation
4. User walks through steps, signaling pass/fail for each
5. All passed → task complete, auto-continuation resumes
6. Any failed → task back to "In Progress" for fixes

### UX Principles for Human Involvement

- **Choose the right channel**: Dashboard for async review, CLI for synchronous interaction. Don't force everything through the dashboard.
- **Self-test first**: Always attempt runtime validation before escalating to human testing. Only ask humans for what Claude genuinely can't evaluate.
- **Provide exact commands**: Never say "test the application" — say "run `python src/tui.py` and verify the menu appears."
- **Consider switching cost**: Each additional app/tab/screen the user must open adds friction. The best interaction keeps the user in one place.
- **Batch async, stream sync**: Group dashboard items together. Walk through CLI-direct items one at a time with immediate feedback.

---

## Error Handling

### Agent Failure

If an agent fails:
1. /work logs error
2. Preserves partial progress
3. Presents error to human
4. Awaits human direction

### Conflicting State

If state is inconsistent:
1. Document the conflict
2. Ask human to clarify
3. Do not proceed until resolved

### Infinite Loops

If work isn't progressing:
1. After 3 iterations, checkpoint
2. Present situation to human
3. Get explicit direction

### Context Window Exhaustion

When a long session approaches compaction:
- **Proactive (preferred):** User runs `/work pause` — graceful wind-down, writes handoff file with reasoning context, task JSON updated with partial notes
- **Automatic (safety net):** PreCompact hook writes handoff file before compaction clears context
- **Reactive (fallback):** Session recovery (Step 0) detects stuck tasks and recovers from task file state alone

The handoff file (`.claude/tasks/.handoff.json`) captures environment-specific context that compaction can't preserve: agent step position, session knowledge, strategic reasoning. `/work` Step 0 detects and restores it before the session recovery scan.

**Full reference:** `.claude/support/reference/context-transitions.md`

---

## Spec Change and Feature Addition

Direct spec edits are always safe — the decomposed snapshot preserves the before-state, and `/work` detects drift automatically. The workflow: user edits spec → runs `/work` → drift detection shows granular section diffs → user confirms per-section (apply, review individually, or skip) → only affected tasks are updated. Completed work is preserved.

**Versioning:** Exactly one `spec_v{N}.md` exists at a time. Version bumps are for major transitions (phase completion, inflection points), not routine edits. `/work` suggests a bump when edits are substantial enough.

**Full procedure:** `.claude/support/reference/drift-reconciliation.md` (detection, reconciliation UI, drift budget, task migration, substantial change detection, version transition).

---

## Out-of-Spec Task Handling

Tasks can be marked `out_of_spec: true` in two ways:
1. **User request** — `/work` spec check offers "Proceed anyway" for requests not in spec
2. **Verify-agent recommendations** — verify-agent creates recommendation tasks for improvements beyond acceptance criteria

### Key Rules

- **Out-of-spec tasks are excluded from phase routing.** The auto-detect table in `/work` only considers spec tasks when determining phase (Execute vs Verify vs Complete). This prevents the verify → execute → verify infinite loop.
- **Out-of-spec tasks require user approval before execution.** `/work` presents pending out-of-spec tasks at phase boundaries with Accept/Reject/Defer options.
- **Accepted tasks** get `out_of_spec_approved: true` and can be executed by `/work`.
- **The completion condition** is "all spec tasks finished + verification passed," regardless of out-of-spec task status.

### Dashboard Display

Out-of-spec tasks appear in the Tasks section with a ⚠️ prefix:

```
| ID | Title | Status | Owner |
|----|-------|--------|-------|
| 13 | ⚠️ Add unit tests for CI | Pending | claude |
```

Unapproved out-of-spec tasks also appear in "Action Required" → "Reviews" to prompt user action.

---

## System Overview

Reference documentation for the environment builder system.

### Roles

**What you do:**
- Review the dashboard for your next action
- Click through to linked files when needed (review a document, configure something, test a feature)
- Signal completion back through the dashboard (checkboxes, feedback sections)
- Update the spec when requirements change
- Make decisions when Claude surfaces options

**What Claude does:**
- Tracks tasks and progress (in `.claude/tasks/`)
- Implements according to spec
- Surfaces everything user-facing through the dashboard — action items with links, not buried in internal files
- Validates work against acceptance criteria
- Regenerates the dashboard at strategic moments (see tiered communication strategy in `commands/work.md`)

### Workspace

When you need to create temporary documents (research, analysis, drafts), use `.claude/support/workspace/`:

- **scratch/** - Throwaway notes, quick analysis, temporary thinking
- **research/** - Web search results, reference material, gathered context
- **drafts/** - Work-in-progress documents before they move to their final location

**Rules:**
- Never create working documents in the project root or other locations
- Use simple descriptive names (`api-comparison.md`, not `task-5-research.md`)
- When a draft is ready to become permanent, discuss where it should go

### Template Configuration Files

Two files control template behavior:

**sync-manifest.json** — Defines which files sync during `/health-check` template sync vs stay project-specific:

| Category | Purpose | Examples |
|----------|---------|----------|
| `sync` | Updated from template | Commands, agents, reference docs |
| `customize` | User-editable, template provides defaults | `.claude/CLAUDE.md`, README.md, documents/README.md |
| `ignore` | Project-specific data, never synced | Tasks, dashboard, decision records, learnings |

**settings.local.json** — Pre-approved permissions for consistent Claude Code behavior. Ensures the template works the same way for everyone using it.

### Project Structure

```
.claude/
├── CLAUDE.md                  # Instructions for Claude Code
├── dashboard.md               # Project Dashboard (auto-generated)
├── verification-result.json   # Latest verification outcome (written by verify-agent)
├── spec_v{N}.md               # Project specification (source of truth)
├── vision/                    # Vision documents from ideation
│   └── {project}-vision.md   # Design philosophy, future roadmap
├── tasks/                     # Task data
│   ├── task-*.json           # Individual task files
│   └── archive/              # Completed tasks (when count exceeds 100)
├── commands/                  # /work and task commands
├── agents/                    # Specialist agents
│   ├── implement-agent.md    # Task execution
│   ├── verify-agent.md       # Validation against spec
│   └── research-agent.md     # Decision investigation
├── support/                   # Supporting documentation
│   ├── reference/            # Schemas, guides, definitions
│   │   ├── README.md          # Index of all reference files
│   │   ├── shared-definitions.md
│   │   ├── task-schema.md
│   │   ├── workflow.md
│   │   ├── paths.md
│   │   ├── decisions.md
│   │   ├── spec-checklist.md
│   │   ├── extension-patterns.md
│   │   ├── dashboard-regeneration.md
│   │   ├── drift-reconciliation.md
│   │   ├── parallel-execution.md
│   │   └── desktop-project-prompt.md
│   ├── decisions/            # Decision documentation
│   │   ├── decision-*.md     # Individual decision records
│   │   └── .archive/         # Research documents
│   ├── learnings/            # Project-specific patterns (see README.md)
│   │   └── README.md         # Categories, format, maintenance guidelines
│   ├── previous_specifications/  # Spec snapshots at decomposition (for drift detection)
│   ├── workspace/            # Claude's working area (gitignored, see README.md)
│   │   ├── README.md         # Directory rules, file placement guide
│   │   ├── scratch/          # Temporary notes, quick analysis
│   │   ├── research/         # Web search results, reference material
│   │   └── drafts/           # WIP docs before final location
│   └── documents/            # User-provided reference files (PDFs, contracts, etc.)
│       └── README.md         # Conventions and file placement
├── sync-manifest.json
├── settings.local.json
└── version.json
```
