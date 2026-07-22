# Feedback Log

Items are captured via `/feedback` and triaged via `/feedback review`.

---

## FB-007: dashboard-render.py mermaid edge sources skip mermaid_id() sanitization

**Status:** new
**Captured:** 2026-06-14

In `render_mermaid()`, `resolve_dep()` returns the raw `f"T{dep}"` (line ~673) without passing it through `mermaid_id()`, so task-dependency edge *sources* keep hyphens (e.g. `Ttask-012_1`) while node definitions and edge *targets* are underscore-sanitized (`Ttask_012_1`). Every dependency edge therefore points from a phantom, unstyled node and the Project Overview graph renders disconnected. Decision edges (line ~709) already sanitize via `mermaid_id('D' + d)`; only the task-dep path is affected. Fix: `return [mermaid_id(f"T{dep}")]`. Observed on OEMMatInsightBI after syncing template 4.10.0 → 4.27.0; worked around by hand-correcting the generated dashboard, but a full `/work` regen reintroduces it until the template fix lands. The 70-test script suite passes despite this — a regression test asserting edge-source IDs equal node-def IDs would close the gap. Bridged to template inbox as FB-007.

## FB-008: dashboard-render.py --html writes to stdout; docs omit the redirect step

**Status:** new
**Captured:** 2026-07-22

`dashboard-render.py --html` renders the full dashboard HTML to **stdout** (line ~1253: `print(render_full_html(claude_dir, now))`) — the on-disk `dashboard.html` only updates when the caller redirects (`--html > .claude/dashboard.html`). But `rules/dashboard.md` and `support/reference/dashboard-regeneration.md` describe regeneration as "via `python3 .claude/scripts/dashboard-render.py --html`" without noting the stdout redirect, so an orchestrator that pipes `--html` to `tail`/`head` for inspection silently leaves the dashboard stale (META `generated` timestamp and `template_version` unchanged) with no error. Observed on OEMMatInsightBI during `/health-check` 2026-07-22: the first regen was piped to `tail -15` to check output, and `dashboard.html` stayed at its old `generated 2026-07-20T18:58:33Z` / `template_version: 5.2.0` until a second pass with an explicit `> .claude/dashboard.html` redirect wrote it. The `--task-hash` mode prints a single line and is correctly stdout-only, so the asymmetry is easy to misread. Suggest the docs state explicitly that `--html` writes to stdout and must be redirected to `.claude/dashboard.html` (or add a `--write`/`-o` flag that writes the file directly). Bridged to template inbox as FB-008.
