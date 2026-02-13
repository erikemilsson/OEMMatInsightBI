# Extension Patterns

Patterns for structuring complex projects. Phases are implicit from spec structure; decisions are always available.

---

## Overview

The core workflow (Spec → Execute → Verify) handles most projects well. These patterns add structure for projects with additional complexity:

| Pattern | Purpose | When to Use |
|---------|---------|-------------|
| **Phases** | Sequential project stages where Phase N+1 can't begin until Phase N completes | Multi-phase projects with natural boundaries |
| **Decisions** | Tracked choices with comparison matrix, option analysis, and optional weighted scoring | Technical or methodological choices that block downstream work |

Both patterns are lightweight. Phases emerge from spec structure; decisions use the existing decision record format.

---

## Phases

Phases structure a project into sequential stages. Work in Phase N+1 cannot begin until all Phase N tasks are complete.

### Purpose

- Enforce natural project boundaries (prototype → production, data pipeline → visualization)
- Prevent premature work on later stages
- Provide clear progress tracking per stage

### How Phases Work

Phases are implicit — they come from the spec structure, not from special configuration.

1. **Spec defines phases:** Sections in the spec naturally group into phases (e.g., "## Phase 1: Data Pipeline", "## Phase 2: Visualization")
2. **Tasks get a `phase` field:** During decomposition, `/work` assigns each task a phase based on its spec section
3. **Phase ordering is enforced:** Tasks in Phase N+1 remain blocked until all Phase N tasks are "Finished"
4. **Dashboard groups by phase:** Tasks section shows tasks under phase headers with per-phase progress; Progress section shows phase breakdown table

### Task Schema

Tasks include a `phase` field:

```json
{
  "id": "11",
  "title": "Chart: enrollment timeline",
  "phase": "2",
  "dependencies": [],
  "decision_dependencies": ["DEC-002"]
}
```

Phase dependencies are checked alongside task dependencies. A task is eligible when:
- All its explicit `dependencies` are "Finished"
- All tasks in earlier phases are "Finished"
- All its `decision_dependencies` are resolved

### Phase Transitions

When all Phase N tasks complete:
- `/work` detects the transition and renders a phase gate in the dashboard
- The gate shows **enumerated conditions** — auto-computed status items plus a manual approval checkbox
- All conditions must be checked before Phase N+1 begins
- If Phase N+1 needs more detail in the spec, `/work` suggests running `/iterate` to flesh it out
- Dashboard updates to show the new active phase after approval

### Phase Gate Conditions

Phase gates display three types of conditions:

1. **Auto-conditions** (computed, pre-checked when satisfied):
   - All Phase N tasks finished (count)
   - All verifications passed (count)

2. **Custom conditions** (from spec, if defined):
   - If the spec section for Phase N contains a `### Gate Conditions` or `### Transition Criteria` sub-section with a bulleted list, each bullet becomes a checkbox in the phase gate
   - Example spec format:
     ```
     ### Gate Conditions
     - User has approved production rollout
     - Load testing results reviewed
     ```
   - Custom conditions start unchecked — the user must verify and check them manually
   - If no gate conditions sub-section exists in the spec, only auto-conditions and the approval checkbox are rendered

3. **Approval checkbox** (always last):
   - "Approve transition to Phase N+1" — the manual gate

`/work` checks all checkboxes within the gate markers. The transition is approved only when every condition is checked.

### No Special Configuration

Phases require no frontmatter config, no criteria files, and no folder blocking. Phase membership comes from task metadata, and ordering is enforced through the existing dependency system. Custom gate conditions are optional and derived from spec content.

---

## Decisions

Decisions are tracked choices that block downstream work until resolved. They use the existing decision record format with a few additions.

### Purpose

- Document choices with multiple viable options
- Block dependent tasks until a selection is made
- Distinguish between pick-and-go decisions and inflection points

### Decision Records

Decision records live in `.claude/support/decisions/decision-*.md`. They contain:

- **Comparison matrix** — criteria vs options table
- **Option details** — strengths, weaknesses, research notes per option
- **Optional weighted scoring** — for high-stakes decisions
- **Checkbox selection** — user marks their choice directly in the doc

See [decisions.md](decisions.md) for the full format.

### Pick-and-Go vs Inflection Point

| Type | What Happens After Resolution |
|------|-------------------------------|
| **Pick-and-go** | Blocked tasks unblock; `/work` continues normally |
| **Inflection point** | `/work` pauses and suggests running `/iterate` to revisit the spec, because the outcome changes what gets built |

Inflection points are flagged with `inflection_point: true` in the decision frontmatter. Examples:
- "Supervised vs unsupervised analysis" — changes what data you collect, what pipeline you build
- "REST vs GraphQL" might be pick-and-go (same features, different implementation)

### Task Dependencies on Decisions

Tasks can depend on decisions via the `decision_dependencies` field:

```json
{
  "id": "11",
  "title": "Chart: enrollment timeline",
  "decision_dependencies": ["DEC-002"],
  "notes": "Blocked until visualization library is chosen"
}
```

When `/work` detects a task blocked by an unresolved decision:
1. Surfaces the decision: "Decision DEC-002 blocks N tasks. Open the decision doc to make your selection, then run `/work` again."
2. Provides a link to the decision doc
3. Continues with unblocked tasks

### Post-Decision Behavior in `/work`

When `/work` detects a checked box in "## Select an Option" and the decision's frontmatter status is not yet `approved`/`implemented`:

1. **Auto-update frontmatter** — set `status: approved` and `decided: [today's date]`, extract selected option name
2. **Check `inflection_point` field** in the decision record
3. **If pick-and-go** (`inflection_point: false` or absent):
   - Unblock dependent tasks
   - Continue executing
4. **If inflection point** (`inflection_point: true`):
   - Pause execution
   - Inform user: "Decision DEC-002 was an inflection point. The spec may need updating. Run `/iterate` to review affected sections, then `/work` to continue."
   - Do not proceed until `/iterate` has run

### Dashboard Integration

Decisions appear in the dashboard:

- **Decisions section:** `ID | Decision | Status | Selected` — decided entries show selected option name, pending entries link to doc
- **Action Required → Decisions:** Pending decisions that block tasks appear here with links
- **Blocked tasks:** Show decision IDs in their dependency column (in Tasks section)

---

## Custom Views

User-defined inline views rendered directly in the dashboard. Instead of linking to external files, you write instructions describing what content Claude should generate, and it appears right in the dashboard.

**Enabling:** Check `Custom Views` in the **Sections** checklist at the top of `dashboard.md`. When enabled, a `## 👁️ Custom Views` section appears in the dashboard.

**How it works:**

The section has two parts:

1. **Instructions area** (between `<!-- CUSTOM VIEWS INSTRUCTIONS -->` and `<!-- END CUSTOM VIEWS INSTRUCTIONS -->` markers): You write what you want Claude to render — tables, summaries, tracking views, whatever fits your project. This area is preserved across dashboard regenerations, just like the Notes user section.

2. **Rendered content** (everything after `<!-- END CUSTOM VIEWS INSTRUCTIONS -->` until the next section separator): Claude reads your instructions and generates this content fresh each `/work` cycle. This part is regenerated, not preserved.

**When to use:**
- The main dashboard's Tasks/Progress sections don't capture domain-specific tracking needs
- You want custom tables, summaries, or views without navigating to separate files
- Examples: materials procurement tracker, experiment status summary, vendor contact sheet, budget breakdown

**Multiple views:** Define as many views as you want in the instructions area. Label each with a bold name (e.g., `**Materials:**`, `**Budget:**`). Claude renders each as a separate `### Heading` sub-section in the output. Views are independent — add, remove, or reword them anytime.

**Example instructions:**
```
**Materials Procurement:** Track materials as a table with columns: Material, Vendor, Ordered, Delivered, Cost.

**Inspection Schedule:** Show inspections as a table with columns: Inspection, Inspector, Date, Status.
```

**Marker structure:**
```markdown
## 👁️ Custom Views

<!-- CUSTOM VIEWS INSTRUCTIONS -->

**View Name:** Description of what to render, format, data sources.

**Another View:** Description of the second view.

<!-- END CUSTOM VIEWS INSTRUCTIONS -->

### View Name

[Claude-generated content for first view]

### Another View

[Claude-generated content for second view]
```

---

## Project Overview Diagram

The dashboard includes an inline Mermaid diagram in the Progress section that provides a bird's-eye view of the project's dependency structure.

**When it appears:** Generated during dashboard regeneration when there are 4+ remaining tasks. For smaller projects, the critical path one-liner is sufficient.

**What it shows:**
- Completed phases collapsed into single nodes
- Active/pending tasks with ownership indicators (🤖/❗/👥)
- Decision gates as diamond nodes, phase gates as hexagon nodes
- Dependency arrows between tasks
- Date constraints when present

**Design principles:**
- Focus on relationships, not detail — clump completed work, show remaining structure
- Ownership at a glance — immediately see what's Claude vs human vs collaborative
- Compact — when >15 nodes would result, group by phase or functional area
- Color-coded — done (green), active (blue), human-owned (yellow), blocked (grey) via `classDef` styles. Human ownership overrides status.

**Generation rules:** See `.claude/support/reference/dashboard-regeneration.md` § "Project Overview Diagram" for the full algorithm.

---

## Related Files

- [decisions.md](decisions.md) — Decision record format and selection mechanism
- [dashboard.md](../../dashboard.md) — Dashboard template with section toggle checklist and populated example
- [shared-definitions.md](shared-definitions.md) — Vocabulary (Phase, Decision, Inflection Point, Human Task)
- [workflow.md](workflow.md) — Core workflow documentation
