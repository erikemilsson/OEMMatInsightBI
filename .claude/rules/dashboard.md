# Dashboard Rules

## Navigation Hub

The dashboard at `.claude/dashboard.md` is the primary navigation hub during the build phase. It surfaces what needs attention with links to specific files. The user follows these links to inspect files directly.

## Interaction Modes

Not everything routes through the dashboard:
- **Dashboard-mediated** (default) — async tasks: document review, design decisions, phase gates
- **CLI-direct** — synchronous tasks: testing a CLI, confirming output, quick yes/no

The dashboard remains the default. CLI-direct is the escape hatch for tasks where the dashboard adds unnecessary intermediation.

## Regeneration Strategy

Dashboard does NOT regenerate on every task change. Two tiers:
- **Tier 1 (Strategic Regen):** Decomposition complete, parallel batch end, session boundaries, `/work complete`, phase gates, decision resolution
- **Tier 2 (Inline CLI Messages):** Brief contextual updates for routine changes — task starts, verification passes/fails

For single-section changes that would otherwise trigger Tier 1, the orchestrator may apply a **targeted `Edit`** to the affected section instead and set a `pending_full_regen` sentinel in `.claude/dashboard-state.json` so the next Step 1a still runs full regen. See `.claude/support/reference/dashboard-regeneration.md § "Targeted Edits (mid-session lite path)"` for the decision table and procedure.

**Script-first (v4.22.0):** full regens render the structural sections via `python3 .claude/scripts/dashboard-render.py --render` — the LLM writes the output, then fills only the synthesis placeholders (Action Required, Custom Views content). See `dashboard-regeneration.md § "Script-First Rendering"` for the division of labor and the canonical `task_hash` mode.

## Sections

The dashboard has a **Sections** checklist at the top — check or uncheck items to control which sections Claude generates:
- 🚨 Action Required — decisions, tasks, reviews needing user input. **Human-gated coverage invariant:** every item blocked on the user — `owner: human` tasks with satisfied dependencies, `owner: both` tasks awaiting review, On Hold tasks, unresolved decisions, and unanswered questions from a paused session — must have a row here with the concrete question/action inline; handoff prose must never be a blocking item's only home. `/work` prints this queue at session start (Step 0g) and sweeps it at pause.
- 📊 Progress — phase breakdown, critical path, timeline, status summary (>20 tasks)
- 📋 Tasks — task list by phase (auto-collapses completed and fully-blocked phases)
- 📋 Decisions — decision log with status
- 💡 Notes — user's preserved section (seeded with quick links on first regen)
- Optional: 👁️ Custom Views (toggle via Sections checklist)

## Scaling

The dashboard auto-adapts to project size:
- **Completed phases** always collapse to a single summary line
- **Fully-blocked phases** (>5 non-actionable tasks, no pending/in-progress tasks) collapse with blocker summary
- **Status summary table** renders in Progress when task_count > 20
- **Mermaid diagrams** switch to critical-path-only mode when >15 active nodes
- **Phase naming** uses "Phase N — Descriptive Name" format for scannability

## Dashboard State

The dashboard ships as a populated format example (fictional renovation project). On first `/work` run after spec decomposition, it is replaced with actual project data.

User content is preserved via marker pairs and `dashboard-state.json` (sidecar file). Section toggles let the user control which sections are shown.

## References

- Dashboard regeneration: `.claude/support/reference/dashboard-regeneration.md`
- Interaction modes: `.claude/support/reference/workflow.md` § "Interaction Modes and Runtime Validation"
