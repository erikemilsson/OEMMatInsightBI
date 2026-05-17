# Friction Register

Persistent project-level register at `.claude/support/friction.jsonl` for spec-implementation friction signals — vocabulary drift, path drift, design contradictions, terminology mismatches, spec-implementation gaps. Consumed by the `audit-coherence` command (audit family Stage 3+) to surface async cleanup work the user can chew through in parallel to active `/work`.

This is **distinct from** the existing `friction_markers` field in agent return reports (which feeds `.session-log.jsonl` for template-improvement signal). The friction register is the audit-facing subset, with its own schema for status tracking. See § "Relationship to existing friction_markers" below.

---

## Why

Spec-vs-implementation friction (e.g., spec § 42.5 says "sub-tab" but `/style` uses synthetic section nav; spec § 22.2 references `foundation/coloring/` but on-disk path is `foundation/user/coloring/`) is currently captured in dashboard prose ("captured for /iterate") and lost to scrollback. The friction register is the durable, structured home for these signals — accumulates across sessions, surfaces at audit time, gets resolved through bundled-apply / [Fix it] / promote-to-FB.

The register is **write-once-by-agent**, **read-and-status-update-by-orchestrator**. Subagents return friction-marker entries in their reports; the orchestrator (`/work`) appends them with assigned IDs; later, `audit-coherence` (or user dismissal) updates the `status` field.

---

## File location

`.claude/support/friction.jsonl` — append-only JSONL with in-place status updates. One entry per line. Created on first write (does not need to ship empty).

---

## Schema

Each line is a single JSON object:

```json
{
  "id": "FR-001",
  "captured": "2026-05-15T11:35:00Z",
  "captured_in": {
    "agent": "verify-agent",
    "task": "task-654",
    "command": "/work"
  },
  "kind": "vocab_drift",
  "what": "spec § 42.5 says 'sub-tab' but /style uses synthetic section nav",
  "source_anchor": "spec_v13.md § 42.5",
  "status": "open"
}
```

### Field reference

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Monotonic `FR-NNN`. Assigned by orchestrator at append time. |
| `captured` | string | ISO 8601 timestamp. |
| `captured_in` | object | Provenance. `agent` (e.g., `implement-agent`, `verify-agent`, `iterate`); `task` (task ID, optional); `command` (slash command driving the dispatch, optional). |
| `kind` | string enum | One of: `vocab_drift`, `path_drift`, `design_contradiction`, `terminology_mismatch`, `spec_implementation_gap`, `other`. |
| `what` | string | One-sentence description. Plain English; no template jargon. |
| `source_anchor` | string | File + section reference (e.g., `spec_v13.md § 42.5`, `decision-050-*.md`, `package.json`). Used by `audit-coherence` to dedupe and to anchor the [Fix it] re-read. |
| `status` | string enum | `open`, `resolved`, `dismissed`. |
| `resolved_by` | object (optional) | When `status != open`. `kind` (`bundled_apply` / `fix_it` / `promote_fb` / `iterate` / `manual`); `ref` (audit run id, FB-NNN, commit hash, etc.); `at` (ISO timestamp). |
| `dismiss_reason` | string (optional) | Free-text reason when `status: dismissed`. |

### Kind semantics

| Kind | Meaning | Example |
|------|---------|---------|
| `vocab_drift` | Term used inconsistently between spec sections, or between spec and implementation | spec uses "sub-tab" but implementation uses "section nav" |
| `path_drift` | Spec references a path that doesn't exist on disk, or implementation uses a different path than spec specifies | spec says `foundation/coloring/`; on-disk is `foundation/user/coloring/` |
| `design_contradiction` | Spec or vision contains contradictory claims; implementation revealed the conflict | Spec § 41.4 prescribes substitute-picker but vision § "oracle thesis" rules out picker chrome |
| `terminology_mismatch` | Same concept named differently in different files (spec vs. decision vs. code comments) | spec calls it "Reference surface"; code calls it "MyStyle gallery" |
| `spec_implementation_gap` | Spec describes behavior that implementation deviates from, or implementation has behavior not described in spec | spec § 5.2 implies per-user generation; DEC-050 selected maintainer-curated, but spec text wasn't updated |
| `other` | Catch-all when no existing kind fits — describe in `what`; orchestrator may surface for re-classification |

---

## Write protocol

**Origin:** subagent return reports. Both `implement-agent` and `verify-agent` already emit a `friction_markers` array (see `.claude/agents/implement-agent.md` § "Step 6: Return Structured Report" and `.claude/agents/verify-agent.md` § "Step T6: Construct Verification Report"). The schema is extended with the audit-eligible kinds above plus the optional `source_anchor` field.

**Orchestrator routing** (in `/work` after each agent return):

For each entry in `report.friction_markers`:

1. **Append to `.session-log.jsonl`** (existing behavior, unchanged — see `commands/work.md` § "Append friction markers"). All friction_markers go here as the canonical session log.
2. **If `kind` is one of {`vocab_drift`, `path_drift`, `design_contradiction`, `terminology_mismatch`, `spec_implementation_gap`}:** ALSO append to `.claude/support/friction.jsonl` as the audit register. Assign a new `FR-NNN` id (max existing id + 1, starting at FR-001), set `status: open`, set `captured` to current ISO timestamp, set `captured_in.agent` from the report context.

**Atomicity:** Both writes happen synchronously in the same orchestrator step. If `friction.jsonl` doesn't exist, create it on first write. Use the same dual-write reliability pattern that DEC-011 Option ABp established for `.session-log.jsonl` (write to `.pending-markers.jsonl` first, then canonical, both before next sync point).

**Existing template-only kinds** (`workflow_deviation`, `informal_decision`, `scope_creep`, `user_feedback_signal`, `template_gap`) continue to write only to `.session-log.jsonl`. They are not audit-coherence signal — they're for orchestrator self-improvement.

---

## Read protocol

**Audit-coherence consumer (Stage 3+):** the `lens-friction-register` lens reads the entire `friction.jsonl`, filters for `status: open`, clusters by `kind` and `source_anchor`, and returns thematic groupings as audit findings. Resolved/dismissed entries are excluded from new audits but retained in the file for audit-trail purposes.

**Health-check / direct inspection:** any tool can read `friction.jsonl` directly. No special parsing — standard JSONL.

---

## Status update protocol

The orchestrator (or `audit-coherence` via the orchestrator) updates entries in-place by id:

1. Read entire `friction.jsonl`
2. Find line by `id`
3. Update `status`, `resolved_by`, `resolved_at` fields
4. Rewrite file (entire contents, atomic)

Triggered by:
- **Bundled-apply** (audit family Stage 7): when an audit cleanup applies, mark all friction entries cited by the cleanup as `resolved` with `resolved_by.kind: bundled_apply` and `ref: audit-{ts}`.
- **[Fix it]** (audit family Stage 6): same, with `resolved_by.kind: fix_it`.
- **Promote to FB**: mark `resolved` with `resolved_by.kind: promote_fb`, `ref: FB-NNN`.
- **`/iterate` resolution**: when `/iterate` amends spec to resolve a captured friction, the iterate command marks the entry `resolved` with `resolved_by.kind: iterate`, `ref: spec_vN+1`. (Convention: include the FR-id in the spec change commit message; iterate detects and updates.)
- **User dismissal during audit review**: mark `dismissed` with `dismiss_reason`.

---

## Relationship to existing `friction_markers` field

The agent return-report `friction_markers` field (existing, see `.claude/agents/implement-agent.md` § "Step 6") is the **single source** of friction signal from agents. The friction register (`friction.jsonl`) is a **subset projection** of those markers — only audit-eligible kinds, with additional structure (`id`, `status`, `source_anchor`).

| | `friction_markers` field (in agent reports) | `.session-log.jsonl` | `.claude/support/friction.jsonl` |
|---|---|---|---|
| **Producer** | implement-agent, verify-agent | orchestrator | orchestrator (filtered subset) |
| **Consumer** | orchestrator | template-improvement, PreCompact export | `audit-coherence` |
| **Schema** | full (all kinds) | full (all entries, append-only) | audit subset (5 kinds), with `id` + `status` |
| **Mutability** | n/a (transient, in report) | append-only | append + in-place status update |
| **Lifetime** | single agent dispatch | session/project | project (across sessions) |

In short: agents emit one stream; the orchestrator splits it into two persistence stores depending on consumer needs.

---

## Migration

The register starts empty. No backfill from existing dashboard prose, session logs, or task notes — too messy to do correctly, and the next several `/work` cycles will populate organically as agents emit audit-eligible markers under the extended schema.

When `audit-coherence` first runs against an empty register, the `lens-friction-register` lens returns 0 findings gracefully. Other lenses (auto-grep against decisions, spec, file paths) continue to surface findings. Over time, the register accumulates and the friction-register lens becomes a richer signal source.

---

## Open considerations

- **Pruning policy.** Resolved/dismissed entries accumulate in `friction.jsonl` for audit trail. If the file grows unwieldy (>1000 entries?), consider an archive policy similar to `.claude/tasks/archive/`. Defer until observed.
- **Backward-compat for orchestrator versions.** Older orchestrator versions that don't recognize the new audit-eligible kinds will write them to `.session-log.jsonl` only (no friction.jsonl projection). Acceptable degradation — `audit-coherence` reads what's there.
- **Agent education on `source_anchor`.** Agents need to know to populate `source_anchor` for audit-eligible kinds. Documented in agent files; tune via dry-runs.
