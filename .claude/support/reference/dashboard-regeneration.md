# Dashboard Regeneration Procedure

Every dashboard regeneration MUST follow this procedure. All commands and agents reference this file for consistency.

---

## Section Toggle Configuration

The primary source for section toggles is the **dashboard.md section toggle checklist** — a visible, editable checklist near the top of the dashboard between `<!-- SECTION TOGGLES -->` and `<!-- END SECTION TOGGLES -->` markers. The checklist is wrapped in an HTML `<details>` element so it renders collapsed by default (one line), keeping the dashboard header compact. Users expand it to change toggle settings.

**Reading logic:**
1. Parse the checklist between the markers (the `<details>` wrapper does not affect parsing)
2. `- [x] Section Name` → `build` mode (actively generate)
3. `- [ ] Section Name` → `exclude` mode (skip during regeneration)
4. Notes section: always `preserve` regardless of checkbox state (enforced)
5. Fallback: if no checklist exists, check spec frontmatter `dashboard_sections` or `.claude/CLAUDE.md`

### First Regeneration (Replacing Template Example)

Detection: the dashboard is still the template example if it contains the line `> **This is a format example**`. On first regeneration, compute toggle defaults from project state instead of using static defaults:

```
Action Required  → [x] always (core section)
Progress         → [x] always (core section)
Tasks            → [x] always (core section)
Decisions        → [x] if any decision-*.md files exist, [ ] otherwise
Notes            → [x] always (preserve mode)
Custom Views     → [ ] always (user opts in when they want custom views)
```

### On Phase Transitions

When `/work` detects a phase transition (all Phase N tasks "Finished", Phase N+1 becoming active), check whether toggle suggestions are warranted:
- If Phase N+1 introduces decision dependencies and Decisions is unchecked → suggest: "Phase {N+1} has pending decisions. Consider enabling the Decisions section in the dashboard."
- Suggestions are logged, never auto-toggled. The user's checkbox state is always authoritative.

### During Regeneration (All Subsequent)

- Preserve the toggle checklist between its markers (never overwrite user's checkbox state)
- Only generate sections that are checked (`[x]`)
- The Notes section is always preserved regardless of toggle state

| Mode | Behavior |
|------|----------|
| `build` | Actively generate from source data on every regeneration (default, `[x]`) |
| `maintain` | Keep existing content, only update if data changes significantly (via spec frontmatter override only) |
| `exclude` | Skip this section entirely during regeneration (`[ ]`) |
| `preserve` | Never modify (Notes always uses this) |

The checkbox UI maps to `build`/`exclude`. Users who need `maintain` mode can set it via spec frontmatter `dashboard_sections` override, which takes precedence over the checklist for that section.

---

## Dashboard State Sidecar

User-authored content is persisted in `.claude/dashboard-state.json` as a durable backup. This file survives dashboard corruption and serves as the fallback source of truth when markers are damaged.

### Schema

```json
{
  "user_notes": "",
  "section_toggles": {
    "action_required": true,
    "progress": true,
    "tasks": true,
    "decisions": true,
    "notes": true,
    "custom_views": false
  },
  "phase_gates": {},
  "inline_feedback": {},
  "custom_views_instructions": "",
  "updated": "2026-01-28T14:30:00Z"
}
```

**Field definitions:**

| Field | Type | Content |
|-------|------|---------|
| `user_notes` | String | Content between `<!-- USER SECTION -->` markers |
| `section_toggles` | Object | Boolean per section name (lowercase, underscored) |
| `phase_gates` | Object | Keyed by transition (e.g., `"1→2"`). Value: `{ "status": "active"\|"approved", "content": "full markdown between markers" }` |
| `inline_feedback` | Object | Keyed by task ID. Value: string content between `<!-- FEEDBACK:{id} -->` markers |
| `custom_views_instructions` | String | Content between `<!-- CUSTOM VIEWS INSTRUCTIONS -->` markers |
| `updated` | String | ISO 8601 timestamp of last write |

**Lifecycle:**
- Created on first dashboard regeneration (populated from marker extraction or defaults)
- Updated on every regeneration (merged with any user edits from markers)
- Read as fallback when markers are damaged
- Never deleted by any command

---

## When to Regenerate

The dashboard is regenerated automatically after every task change. This ensures the user always sees current state.

| State Change | Regenerate? | Rationale |
|-------------|:-----------:|-----------|
| Task: Pending → In Progress | **Yes** | Reflects work starting |
| Task: In Progress → Awaiting Verification | **Yes** | Reflects implementation complete |
| Task: Awaiting Verification → Finished (pass) | **Yes** | User-visible completion event |
| Task: Awaiting Verification → In Progress (fail) | **Yes** | User may need to see verification failure |
| Task: any → Blocked | **Yes** | User may need to act on blocker |
| Task: any → On Hold | **Yes** | User-initiated status change |
| Decomposition complete (new tasks created) | **Yes** | New tasks to display |
| Phase transition | **Yes** | Major state change, gate conditions to show |
| Phase-level verification complete | **Yes** | Verification results to display |
| Parallel batch complete (post-cleanup) | **Yes** | Single regen for all parallel results |
| `/work complete` | **Yes** | User-initiated completion |
| Decision resolved | **Yes** | Decision status changed, tasks may unblock |

**In parallel mode:** Individual agents never regenerate. The `/work` coordinator regenerates once after all agents complete.

---

## Regeneration Steps

### 1. Read Source Data

- All `task-*.json` files (tasks)
- All `decision-*.md` files in `.claude/support/decisions/` (decisions)
- `drift-deferrals.json` (if exists)
- `verification-result.json` (if exists)
- `.claude/support/questions/questions.md` (scan for blocking questions)
- `.claude/support/feedback/feedback.md` (scan for unhandled feedback items)

### 2. Extract and Persist User Content

**2a. Validate markers in current dashboard.md:**

For each marker type, check that both open and close markers exist:

| Marker Type | Open | Close |
|-------------|------|-------|
| User notes | `<!-- USER SECTION -->` | `<!-- END USER SECTION -->` |
| Feedback | `<!-- FEEDBACK:{id} -->` | `<!-- END FEEDBACK:{id} -->` |
| Phase gates | `<!-- PHASE GATE:{X}→{Y} -->` | `<!-- END PHASE GATE:{X}→{Y} -->` |
| Phase gate approved | `<!-- PHASE GATE:{X}→{Y} APPROVED -->` | *(single marker, no close)* |
| Custom views | `<!-- CUSTOM VIEWS INSTRUCTIONS -->` | `<!-- END CUSTOM VIEWS INSTRUCTIONS -->` |
| Section toggles | `<!-- SECTION TOGGLES -->` | `<!-- END SECTION TOGGLES -->` |

For each type:
- If both markers present → extract content (marker is intact)
- If neither marker present → skip extraction for this type (section not present, which is normal)
- **Single-marker types** (Phase gate approved) are exempt — they have no close marker by design
- **If only ONE marker of a paired type is present** (open without close, or close without open):
  - **Critical markers** (User notes, Section toggles, Custom views instructions): **ABORT regeneration.** Log: `"⚠️ Dashboard regeneration aborted: incomplete marker pair for {type}. Found {open|close} marker but not its counterpart. Fix the markers in dashboard.md or run /health-check."` Do NOT proceed to Step 3. Do NOT overwrite dashboard.md or dashboard-state.json. The existing dashboard remains as-is until the user fixes the unpaired marker.
  - **Per-instance markers** (Feedback, Phase gates): Log warning `"⚠️ Incomplete marker pair for {type} — skipping extraction, using sidecar fallback."` Skip extraction for this instance only and continue. Content for this instance falls back to dashboard-state.json (Step 2c).

**2b. Read `.claude/dashboard-state.json`** (if it exists). This is the previous known-good state.

**2c. Merge:**

For each content type:
- If marker extraction succeeded: use extracted content (user may have edited the dashboard since last regen)
- If marker extraction was skipped (neither marker): use dashboard-state.json value if available, otherwise use defaults
- If dashboard-state.json doesn't exist: use extracted content or defaults

**2d. Write merged state to `.claude/dashboard-state.json`.**

This ensures user content is always persisted in a structured file before the dashboard is regenerated.

### 3. Generate Dashboard

- Follow the Section Format Reference below for all formatting rules
- Use exact section headings: `# Dashboard`, `## 🚨 Action Required`, `## 📊 Progress`, `## 📋 Tasks`, `## 📋 Decisions`, `## 💡 Notes`
- **Freshness line:** After the completion % line, add a visible timestamp: `*Updated [YYYY-MM-DD HH:MM] — may not reflect changes made outside `/work`*`. This warns users who view the dashboard without running a command that data could be stale.
- Optional section heading (when enabled, placed between Decisions and Notes): `## 👁️ Custom Views`
- **Timeline sub-section** in Progress: render when any task has `due_date` or `external_dependency.expected_date`
- **Project Overview sub-section** in Progress: render inline Mermaid diagram when 4+ tasks remain (see § "Project Overview Diagram")
- Read section toggles from dashboard checklist (between `<!-- SECTION TOGGLES -->` markers) and respect modes
- Preserve the section toggle checklist between its markers during regeneration (keep the `<details>` wrapper around the markers)
- Enforce atomicity: only tasks with JSON files, only decisions with MD files
- On first regeneration (detected by `> **This is a format example**` line): replace the template example with actual project data and compute toggle defaults per the "First Regeneration" section above
- **User review gate for `both` tasks:** When generating "Your Tasks", include `both`-owned tasks that have `user_review_pending: true` — even if their status is "Finished". These tasks passed verification but still need user review. Show them with status `✅ Verified — awaiting your review` and include a `/work complete {id}` prompt. Remove them from "Your Tasks" only after the user runs `/work complete`.
- **Inline feedback areas:** When generating "Your Tasks", add feedback markers for each `human`/`both`-owned task:
  ```
  <!-- FEEDBACK:{id} -->
  **Task {id} — Feedback:**
  [Leave feedback here, then run /work complete {id}]
  <!-- END FEEDBACK:{id} -->
  ```
- **Phase Transitions sub-section:** When all tasks in Phase N are "Finished" AND Phase N+1 tasks exist AND no `<!-- PHASE GATE:{N}→{N+1} APPROVED -->` marker exists in the dashboard, render a phase gate with enumerated conditions between markers:
  ```
  <!-- PHASE GATE:{N}→{N+1} -->
  **Phase {N} → Phase {N+1} Transition**

  Conditions:
  - [x] All Phase {N} tasks finished ({M}/{M})
  - [x] All verifications passed ({V}/{V})
  - [ ] Approve transition to Phase {N+1}

  <!-- END PHASE GATE:{N}→{N+1} -->
  ```
  **Enumerated condition rules:**
  - Auto-conditions (task completion, verification status) are computed and rendered as pre-checked `[x]` items — the user cannot uncheck these, they reflect actual state
  - The final "Approve transition" checkbox is the manual gate — the user must check this
  - If any auto-condition is NOT met (e.g., a task has verification debt), render it as `[ ]` with detail: `- [ ] All verifications passed (8/10 — 2 tasks have verification debt)`
  - Custom gate conditions from the spec: if the Phase N spec section contains a `### Gate Conditions` or `### Transition Criteria` sub-section with bullets, each bullet becomes an additional checkbox between auto-conditions and the approval checkbox. If no such sub-section exists, skip custom conditions.
  - The gate is approved only when ALL checkboxes are checked (both auto and manual)
- **Verification Pending sub-section:** When all spec tasks are "Finished" with passing per-task verification AND no valid `verification-result.json` exists, render:
  ```
  All tasks complete — phase-level verification will run on next `/work`
  ```
- **Spec Drift sub-section:** When `drift-deferrals.json` exists with active deferrals, render each deferred section:
  ```
  - ⚠️ **{section}** — {N} tasks affected, deferred {M} days ago
  ```

### 4. Compute and Add Metadata Block

Add after `# Dashboard` title:
```markdown
<!-- DASHBOARD META
generated: [ISO timestamp]
task_hash: sha256:[hash of sorted task_id:status:difficulty:owner tuples]
task_count: [number]
spec_fingerprint: sha256:[hash of spec file content]
verification_debt: [count of tasks needing verification]
drift_deferrals: [count from drift-deferrals.json]
-->
```

### 5. Inject User Content from Sidecar

Read `.claude/dashboard-state.json` and inject content into the generated dashboard:

**5a. User notes:** Insert `user_notes` value between `<!-- USER SECTION -->` markers. If the value is empty, insert the default placeholder: `[Your notes here — ideas, questions, reminders]`

**5b. Custom views instructions:** Insert `custom_views_instructions` value between `<!-- CUSTOM VIEWS INSTRUCTIONS -->` markers. Then generate rendered content below the end marker. If the section toggle is unchecked, skip entirely.

**5c. Inline feedback:** For each entry in `inline_feedback`:
- If the task still appears in "Your Tasks": insert content between `<!-- FEEDBACK:{id} -->` markers
- If the task is no longer in "Your Tasks": write the feedback content to the task JSON `user_feedback` field (preserves feedback that would otherwise be lost), then remove from dashboard-state.json

**5d. Phase gates:** For each entry in `phase_gates`:
- If `status` is `"active"` and the gate condition still applies: insert `content` between `<!-- PHASE GATE:{X}→{Y} -->` markers
- If `status` is `"approved"`: insert the `<!-- PHASE GATE:{X}→{Y} APPROVED -->` single marker
- If the gate no longer applies: remove from dashboard-state.json

**5e. Section toggles:** The toggle checklist is generated from `section_toggles` in the sidecar. The `<details>` wrapper and marker format remain unchanged.

### 6. Add Footer Line

At very end:
```
---
*[timestamp] · N tasks · [status indicator]*
```
- Healthy: `[Spec aligned](# "0 drift deferrals, 0 verification debt")`
- Issues: `⚠️ N drift deferrals, M verification debt`

### 7. Post-Regeneration Validation

After writing the new dashboard.md, verify structural integrity:

1. **Marker pair check:** For each expected marker type, confirm both open and close markers exist in the output
2. **Section order check:** Verify required headings appear in correct order (same as health-check Part 1 Check 5)
3. **Metadata check:** Confirm `<!-- DASHBOARD META -->` block was written with valid task_hash

If any check fails:
- Log: "Dashboard regeneration produced invalid output — {specific issue}"
- Do NOT overwrite dashboard-state.json (it has the pre-regen good state)
- The dashboard may be structurally broken but user content is safe in the sidecar

---

## Section Format Reference

All dashboard formatting rules are documented here. This is the single authoritative source — do not add format comments to the regenerated dashboard.

### Action Item Contract

Every item in "Action Required" must be:
1. Actionable — the user can see what to do without guessing
2. Linked — if the action involves a file, include a relative path link
3. Completable — include a checkbox, command, or clear completion signal
4. Contextual — if feedback is needed, provide a feedback area or link

### Review Item Derivation

Review items are derived, not stored. During regeneration:
1. Scan for unresolved items — out_of_spec without approval, draft/proposed decisions, blocking questions from `questions.md`
2. Populate Reviews sub-section from current data
3. Never carry forward stale entries — resolved items disappear on next regeneration
4. No dangling references — every item must link to a concrete file
5. Blocking questions: scan `questions.md` for `[BLOCKING]` entries, render each as a review item linking to [questions.md](support/questions/questions.md)
6. Non-blocking unanswered questions: if count > 0, add summary line to Reviews: `- [ ] **N pending questions** → [questions.md](support/questions/questions.md)

### Out-of-Spec Task Approval UI

Out-of-spec tasks (`out_of_spec: true`) require explicit user approval before execution. The approval UI appears in **Action Required → Reviews**:

**Presentation format:**
```markdown
- [ ] **Task {id}: {title}** — Review and approve out-of-spec task → [task-{id}.json](../tasks/task-{id}.json)
```

**User actions:** When `/work` detects pending out-of-spec tasks, it presents them with these options (see work.md Step 3 § "Out-of-spec task handling"):
- `[A]` Accept → Sets `out_of_spec_approved: true`, task becomes eligible for execution
- `[R]` Reject → Sets `out_of_spec_rejected: true`, prompts for optional `rejection_reason`, archives task to `.claude/tasks/archive/`
- `[D]` Defer → Task remains in pending state, continues to appear in Reviews on next regeneration
- `[AA]` Accept all → Batch-approves all pending out-of-spec tasks

The user selects an option when prompted, and `/work` updates the task accordingly.

**Where out-of-spec tasks come from:**
1. User requests that don't align with spec (user chose "Proceed anyway" during `/work` Step 2 spec check)
2. verify-agent recommendations (improvement suggestions beyond spec acceptance criteria, created with `out_of_spec: true` + `source: "verify-agent"`)

**Dashboard visibility:**
- Unapproved out-of-spec tasks appear in both "Action Required → Reviews" (for approval) and "Tasks" section (with ⚠️ prefix)
- Approved out-of-spec tasks appear only in "Tasks" section (with ⚠️ prefix)
- Rejected out-of-spec tasks are archived and removed from dashboard

### Section Display Rules

- Action Required sub-sections: only render when they have content (omit empty categories entirely)
- Action Required sub-section order: Phase Transitions, Verification Pending, Verification Debt, Spec Drift, Feedback, Decisions, Your Tasks, Reviews
- Phase Transitions: only render when a phase boundary has been reached (all Phase N tasks Finished, Phase N+1 exists) AND no APPROVED marker exists for that transition
- Verification Pending: only render when all spec tasks are Finished with passing per-task verification but no valid verification-result.json
- Spec Drift: only render when drift-deferrals.json has active entries
- Feedback: only render when `feedback.md` has entries with status `new` or `refined` — render as: `- 📝 **{N} feedback items** awaiting attention ({X} new, {Y} refined) → /feedback review`
- Reviews sub-section format: `- [ ] **Item title** — what to do → [link to file](path)`
- Reviews appear for: out_of_spec tasks without approval, draft/proposed decisions, blocking questions from `questions.md` (each linked to the file)
- Timeline sub-section in Progress: only render when tasks have `due_date` or `external_dependency.expected_date` (part of Progress, not an independent toggle)
- Phase table in Progress: always show ALL phases (including blocked/future)
- Critical path owners: ❗ (human), 🤖 (Claude), 👥 (both)
- Critical path parallel branches: `[step A | step B]` notation for fork/join points; max 3 branches per group
- Critical path >5 steps (after collapsing parallel branches): show first 3 + "... N more → Done"
- "This week" line: omit when all counts are zero
- Tasks grouped by phase with per-phase progress lines
- **Completed task summarization (scale):** When a phase has more than 10 finished tasks, render a summary line (`✅ {N} tasks finished`) instead of listing each individually. Only list active tasks (Pending, In Progress, Awaiting Verification, Blocked, On Hold) with full detail rows. This keeps the dashboard navigable for large projects (50+ tasks).
- Tasks with `conflict_note`: show status as `Pending (held: conflict with Task {id})` during parallel dispatch
- Decisions: status display mapping: `approved`/`implemented` → "Decided", `draft`/`proposed` → "Pending". Selected column always links to the decision document regardless of status — Decided shows the selected option name as link text; Pending shows "Pending" as link text
- Out-of-spec tasks: prefix title with ⚠️
- On Hold tasks: show status as `⏸️ On Hold` in Tasks section; exclude from Progress phase "Done" counts but include in "Total"; exclude from critical path (paused work isn't on the path)
- Absorbed tasks: show status as `Absorbed → Task {id}` in Tasks section (dimmed/collapsed style); exclude from both "Done" and "Total" in Progress phase counts; exclude from critical path
- Notes generated content: minimal — a single inline link to [questions.md](support/questions/questions.md) when unresolved questions exist, placed before the `<!-- USER SECTION -->` markers. No "Quick links" header, no decisions link (decisions have their own section with persistent links). When no unresolved questions exist, the Notes section contains only the user section markers.
- Footer: healthy = spec aligned tooltip; issues = ⚠️ with counts
- Custom Views section: user-defined instructions (preserved between markers) followed by Claude-generated content based on those instructions (when enabled). Multiple views are rendered as `###` sub-sections, one per bold-labeled instruction.

### Per-Section Format

| Section | Columns / Format |
|---------|-----------------|
| Action Required → Phase Transitions | Enumerated conditions (`[x]`/`[ ]` checkboxes) between `<!-- PHASE GATE -->` markers — auto-conditions + manual approval |
| Action Required → Verification Pending | Plain text status message |
| Action Required → Verification Debt | `Task \| Title \| Issue` |
| Action Required → Spec Drift | `- ⚠️ **{section}** — {N} tasks affected, deferred {M} days ago` |
| Action Required → Feedback | `- 📝 **{N} feedback items** awaiting attention ({X} new, {Y} refined) → /feedback review` |
| Action Required → Decisions | `Decision \| Question \| Doc` |
| Action Required → Your Tasks | `Task \| What To Do \| Where` |
| Action Required → Reviews | `- [ ] **Item title** — what to do → [link](path)` — derived, not stored |
| Progress → Phase table | `Phase \| Done \| Total \| Status` — status: Complete, Active, Blocked (reason) |
| Progress → Timeline | `Date \| Item \| Status \| Notes` — sorted chronologically, overdue: strikethrough date + ⚠️ OVERDUE prefix, external deps with contact info, human tasks marked with ❗ |
| Tasks → Per phase | `ID \| Title \| Status \| Diff \| Owner \| Deps` — grouped by phase headers |
| Decisions | `ID \| Decision \| Status \| Selected` |
| Progress → Project Overview | Inline Mermaid `graph LR` diagram — see Project Overview Diagram rules below |
| Custom Views | Preserved instruction block between `<!-- CUSTOM VIEWS INSTRUCTIONS -->` markers + rendered `###` sub-sections generated from those instructions (one per bold-labeled view) |

### Domain Agnosticism

This format works for any project type — software, research, procurement, renovation, event planning. Use language appropriate to the project domain. No code-specific assumptions are built in.

---

## Critical Path Generation

The critical path is rendered as a single line in the **Progress** section: owner-tagged steps joined by `→`, with parallel branches shown in `[ | ]` notation.

1. **Build dependency graph** — include all incomplete tasks and their dependencies (both task deps and decision deps). Unresolved decisions appear as nodes (e.g., `❗ Resolve DEC-001`)
2. **Compute longest path** — walk the graph to find the longest chain from any current entry point to "Done". This is the critical path (determines project duration)
3. **Detect parallel branches** — find fork/join points along the critical path:
   - A **fork** is a node whose completion enables 2+ independent successors
   - A **join** is a node with 2+ predecessors that must all complete before it starts
   - Show parallel branches when they share the same fork and join nodes (the branches reconverge)
   - Branches that don't reconverge are separate sequential paths — pick the longest
4. **Format as one-liner:**
   - Sequential: `❗ Resolve DEC-001 → 🤖 Build API → Done`
   - Parallel branches: `[🤖 Rough plumbing | ❗ Resolve DEC-002] → [❗ Inspection | 🤖 Install] → 👥 Walkthrough → Done`
   - Owners: `❗` (human), `🤖` (Claude), `👥` (both)
   - **Step count** = total unique nodes in the rendered path (each branch member counts as 1): `*(N steps)*`
   - For complex paths (>5 steps after collapsing parallel branches), show first 3 + "... N more → Done"
5. **Prioritize human-owned steps** — surfaces blockers the user can act on

**Decision dependencies as path nodes:** Unresolved decisions appear on the critical path as `❗ Resolve {DEC-ID}` steps. Once resolved, they are removed and their successor tasks become direct successors of the decision's predecessors.

**Parallel branch rules:**
- Max 3 branches in a single `[ | ]` group (more than 3 → collapse to `[🤖 3 parallel tasks]`)
- Nested parallelism: don't nest `[ ]` — flatten to separate `[ | ]` groups joined by `→`
- If parallel branches have different owners, show each: `[❗ Review | 🤖 Build]`
- Branches of unequal length: show each by its first step (the branch content is what matters, not padding)

**Edge cases:** No dependencies → "All tasks can start now". No incomplete AND no valid verification-result.json → "🤖 Phase verification → Done" *(1 step)*. No incomplete AND valid passing verification-result.json → "All tasks complete! ✓". Single task → just that task → Done. No parallelism detected → pure sequential format (no brackets).

---

## Project Overview Diagram

An inline Mermaid diagram in the Progress section showing the project's dependency structure at a glance. Placed after the critical path one-liner, before the "This week" activity line, under a `### Project Overview` sub-heading.

**Generation rules:**

1. **Completed phases** → Collapse into a single node: `["✅ Phase Name (N/N)"]`
2. **Completed tasks in active phases** → Fold away. Reroute their connections: connect their predecessors directly to their incomplete successors. This keeps the diagram focused on remaining work.
3. **Active/pending tasks** → Show individually with ownership prefix: `🤖` (claude), `❗` (human), `👥` (both)
4. **Decisions** → Diamond nodes: `{"❓ Decision title"}`
5. **Dependencies** → Arrows between nodes following task dependency data
6. **Date constraints** → Annotate nodes with deadlines when present: `["🤖 Task title<br/><small>Due: 2026-02-15</small>"]`
7. **Clumping** → When >15 active nodes would result, group related tasks into subgraph clusters by phase or functional area to reduce visual noise
8. **Direction** → Always `graph LR` (left to right)
9. **Labels** → Keep short: ownership emoji + task title. No status text in labels.
10. **Gates** → Phase gates as hexagon nodes: `{{❗ Phase N Review}}` — visually distinct from tasks (rectangles) and decisions (diamonds)
11. **Styling** → Include `classDef` declarations and apply to each node. Priority: `done` first, then `human` (ownership overrides status), then `active`, then `blocked` as default for remaining nodes:
    - `classDef done fill:#c8e6c9,stroke:#2e7d32` — completed phases/tasks
    - `classDef active fill:#bbdefb,stroke:#1565c0` — in-progress tasks (claude/both-owned)
    - `classDef human fill:#fff9c4,stroke:#f57f17` — human-owned tasks and phase gates
    - `classDef blocked fill:#f5f5f5,stroke:#9e9e9e` — pending/blocked tasks (claude/both-owned)

**Edge cases:** No tasks → omit diagram. All tasks complete → omit diagram (project done). Single task → omit diagram (one-liner is sufficient). Fewer than 4 remaining tasks → omit diagram (one-liner covers it).
