# Dashboard Rules

## Navigation Hub

The dashboard at `.claude/dashboard.html` is the primary navigation hub during the build phase — a **single read-only, offline, `file://`-openable HTML page** (DEC-024). It surfaces what needs attention with links to specific files (spec, decisions, tasks). The user reads it for overview and acts via the CLI; it is not edited in-place.

## Interaction Modes

Not everything routes through the dashboard:
- **Dashboard-mediated** (default) — async overview: progress, decisions, phase-gate readiness, what needs the user
- **CLI-direct** — synchronous tasks: testing a CLI, confirming output, quick yes/no, approving a phase gate

The dashboard remains the default read surface. Because it is read-only, every action the user takes happens via the CLI (the dashboard's "Needs you" card names the action + the command).

## Regeneration Strategy

The dashboard is regenerated whole by the script (`dashboard-render.py --html`) — there is no in-file targeted-edit path (the HTML is not hand-edited). Two tiers:
- **Tier 1 (Strategic Regen):** Decomposition complete, parallel batch end, session boundaries, `/work complete`, phase gates, decision resolution (incl. ratified or reconsidered), drift reconciliation applied (a choice wrote a task file or `drift-deferrals.json`), Step 1a freshness mismatch, format staleness
- **Tier 2 (Inline CLI Messages):** Brief contextual updates for routine changes — task starts, verification passes/fails — no regen

A full regen is cheap (a single script call), so any Tier-1 trigger runs a full regen.

**Script-first (DEC-024):** full regens render the entire HTML — structural sections + inline-SVG visualizations — via `python3 .claude/scripts/dashboard-render.py --html > .claude/dashboard.html` (the script writes to **stdout**; the redirect lands the on-disk file — omitting it silently leaves `dashboard.html` stale with no error). The orchestrator then fills Custom Views content when that section is on. See `dashboard-regeneration.md § "Script-First Rendering — HTML target"` for the division of labor and the canonical `task_hash` mode.

## Sections

Sections render from data; only four have a switch in sidecar `section_toggles` (`.claude/dashboard-state.json`; edit it or ask Claude): `action_required`, `decisions`, `notes` (default on), `custom_views` (off). Other keys are ignored. Sections:
- 🚨 Action Required ("Needs you" card) — decisions, tasks, reviews needing user input. **Script-rendered** (FB-105, FB-118): the script derives every mechanical row (task rows, unresolved decisions, the agent-decision ratify row, verification debt, changed spec sections and drift deferrals, audit findings, feedback counts, out-of-spec reviews) from state; judgment rows go in sidecar `augment_rows[]`, then regenerate (never edit the HTML). **Human-gated coverage invariant:** every item blocked on the user must appear here with the concrete question/action inline; handoff prose must never be a blocking item's only home. The script covers `owner: human` tasks with satisfied dependencies, tasks awaiting review (any owner), Blocked tasks owned by human/both or escalated (≥3 attempts), On Hold tasks and unresolved decisions; the rest (unanswered questions from a paused session, any Blocked task's open choice) needs an `augment_rows[]` entry. `/work` prints this queue at session start (Step 0g) and sweeps it at pause.
- 📊 Pulse + Phase map — completion ring, status donut, count chips, phase heatmap, active-front cards
- 🔀 Flow — inline-SVG dependency graph + critical path (auto-hidden when degenerate)
- 🗓️ Timeline — due dates / external dependencies (when present)
- 📋 Decisions — collapsed, link-out + in-file search (demoted to a stat; omitted at 0)
- 📄 Specification — link-out card listing section headings (not embedded)
- 💡 Notes — read-only card from sidecar `user_notes` (seeded with quick links on first regen)
- Optional: 👁️ Custom Views

## Scaling

The dashboard auto-adapts to project size:
- **Completed phases** collapse into the heatmap (one cell each) rather than repeated headers
- **Phase heatmap** keeps even 50+ phases scannable as a compact grid
- **Dependency graph** auto-hides when degenerate (<4 incomplete task nodes, no edges, or a cycle); >15 task nodes reduce to the critical path + immediate neighbors
- **Decisions** collapse to a single searchable stat regardless of count (styler: 141 → one line)
- **Spec** is linked-out, not embedded, so the file stays light (~25–150 KB) regardless of spec size

## Dashboard State

The dashboard is a derived, gitignored artifact, so the template ships no `dashboard.html` — a fresh project generates it on the first `/work` after spec decomposition. **First regeneration** is detected by the absence of a `dashboard-state.json` sidecar (and no legacy `dashboard.md` to migrate); on it, the orchestrator seeds the Notes Quick Links and the static section-toggle defaults.

User content lives **only** in `dashboard-state.json` (the sidecar): `section_toggles` (the four switches), `user_notes` (the Notes card) and `augment_rows` (judgment rows). The HTML has no editable markers — the sidecar is the single source of truth.

## References

- Dashboard regeneration: `.claude/support/reference/dashboard-regeneration.md`
- Interaction modes: `.claude/support/reference/workflow.md` § "Interaction Modes and Runtime Validation"
