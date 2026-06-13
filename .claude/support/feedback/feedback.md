# Feedback Log

Items are captured via `/feedback` and triaged via `/feedback review`.

---

## FB-007: dashboard-render.py mermaid edge sources skip mermaid_id() sanitization

**Status:** new
**Captured:** 2026-06-14

In `render_mermaid()`, `resolve_dep()` returns the raw `f"T{dep}"` (line ~673) without passing it through `mermaid_id()`, so task-dependency edge *sources* keep hyphens (e.g. `Ttask-012_1`) while node definitions and edge *targets* are underscore-sanitized (`Ttask_012_1`). Every dependency edge therefore points from a phantom, unstyled node and the Project Overview graph renders disconnected. Decision edges (line ~709) already sanitize via `mermaid_id('D' + d)`; only the task-dep path is affected. Fix: `return [mermaid_id(f"T{dep}")]`. Observed on OEMMatInsightBI after syncing template 4.10.0 → 4.27.0; worked around by hand-correcting the generated dashboard, but a full `/work` regen reintroduces it until the template fix lands. The 70-test script suite passes despite this — a regression test asserting edge-source IDs equal node-def IDs would close the gap. Bridged to template inbox as FB-007.
