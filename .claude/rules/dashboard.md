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

## Sections

The dashboard has a **Sections** checklist at the top — check or uncheck items to control which sections Claude generates:
- 🚨 Action Required — decisions, tasks, reviews needing user input
- 📊 Progress — phase breakdown, critical path, timeline
- 📋 Tasks — full task list by phase
- 📋 Decisions — decision log with status
- 💡 Notes — user's preserved section
- Optional: 👁️ Custom Views (toggle via Sections checklist)

## Dashboard State

The dashboard ships as a populated format example (fictional renovation project). On first `/work` run after spec decomposition, it is replaced with actual project data.

User content is preserved via marker pairs and `dashboard-state.json` (sidecar file). Section toggles let the user control which sections are shown.

## References

- Dashboard regeneration: `.claude/support/reference/dashboard-regeneration.md`
- Interaction modes: `.claude/support/reference/workflow.md` § "Interaction Modes and Runtime Validation"
