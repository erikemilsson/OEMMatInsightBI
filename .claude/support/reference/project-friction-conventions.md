# Friction Register — Project Conventions (OEMMatInsightBI)

Local conventions layered on top of the template-owned schema in
`.claude/support/reference/friction-register.md`. **That file is template-owned — never edit it.**
This file is `project-*`-prefixed, so it sits in the sync-manifest `ignore` category and survives
template syncs. Established 2026-07-21.

The data file itself (`.claude/support/friction.jsonl`) matches no sync pattern, so it is
project-owned and free to extend.

---

## Local extension: `owned_by_task`

**Field:** `owned_by_task` (string, optional) — the task ID on the hook for closing this friction.

```json
{ "id": "FR-002", "kind": "path_drift", "status": "open", "owned_by_task": "task-033", ... }
```

### Why it exists

The canonical schema records **provenance** (`captured_in.task` — which task's dispatch *surfaced*
the friction) but has no field for **ownership** (which task will *fix* it). Those are routinely
different: FR-005 was surfaced by task-024 but owned by task-033. Before this field, ownership lived
in free text inside `what`, where nothing could route on it and a reader could easily misread
provenance as ownership.

It also harmonises an ad-hoc convention that had already emerged organically — FR-006 and FR-007
carried a `related_tasks` array serving the same purpose. That array was folded into `owned_by_task`
during the 2026-07-21 normalization; do not reintroduce it.

### Rules

- Set `owned_by_task` whenever a friction is triaged into an existing task's scope, and add a
  matching note to that task explaining what it now covers. **Both directions, or the link rots.**
- A friction that needs no work (it closes as a side effect of another task completing — e.g. FR-004
  closes when task-022's Fabric run confirms) still gets `owned_by_task`. Ownership means
  "this task's completion closes it," not "this task must do extra work."
- Do **not** create a task per friction. The register's value is that `/audit-coherence` clusters
  open entries by `kind` + `source_anchor` into themes — one `/iterate` resolved FR-005/007/008/009
  as a single WB/WGI-lineage cleanup. Converting to tasks destroys that clustering and duplicates
  state.
- Omit the field when genuinely unowned. An unowned open friction is a signal worth seeing, not a
  gap to paper over with a placeholder.

### Consumer compatibility

`owned_by_task` is an extra field. The template-owned consumers — `/audit-coherence`'s lenses and
`.claude/scripts/persist-friction.py` — ignore unknown fields, so this is additive and safe. It is
**not** written automatically: `persist-friction.py` is template-owned and does not know about it,
so the orchestrator sets it during triage.

---

## Schema conformance (2026-07-21 normalization)

Entries FR-001..FR-007 were written in a pre-canonical local shape (`type`, `details`, `timestamp`,
`task_id`, `origin`) that did **not** match the template schema (`kind`, `what`, `captured`,
`captured_in`). This mattered: `/audit-coherence` filters its lenses on `kind` (see
`commands/audit-coherence.md` lens table and Lenses 2/5) and `--since` filters on `captured`. All
three then-open entries were legacy shape, so the audit would have under-reported on the entire
register.

All 9 entries were normalized in place — keys remapped, every narrative string, `source_anchor` and
`status` preserved verbatim, ad-hoc diagnostic fields (`diagnostic_*`, `source_repo`, `updated`)
retained as-is.

**When appending new entries, use `.claude/scripts/persist-friction.py`** — it emits the canonical
shape and computes collision-safe `FR-NNN` ids. Hand-writing entries is what produced the drift.
Add `owned_by_task` afterwards during triage.

---

## Promotion candidate

`owned_by_task` looks generally useful rather than domain-specific — the provenance-vs-ownership
gap is not particular to this project. Worth bridging upstream via
`/feedback template: <text>` so it can become real schema in `friction-register.md`, at which point
this local section can be deleted. Not yet done.
