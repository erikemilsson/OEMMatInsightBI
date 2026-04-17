---
name: decomposition-heuristics
description: Procedure and guidelines for decomposing a spec into granular tasks. Use when decomposing a spec (e.g., running /work decomposition step), creating task JSON files from spec sections, setting task provenance fields (spec_fingerprint, section_fingerprint, phase, cross_phase), computing spec/section hashes for drift detection, or organizing tasks into implementation stages (Foundation, Core Features, Polish, Validation). Covers all 10 decomposition steps, task creation fields, difficulty bounds, phase/cross-phase assignment heuristics, and decomposition quality checks.
---

<!-- During Skills trial (DEC-007 Option B, 2026-04-17): this Skill mirrors `.claude/support/reference/decomposition.md`. Update both files in sync until one is retired. -->

# Spec Decomposition

Procedure for breaking a spec into granular tasks. Run as `/work` Step 4 "If Decomposing."

---

## Procedure

1. **Run setup checklist** — Read `.claude/support/reference/setup-checklist.md` and run through its checks. Report any warnings inline. Continue regardless (advisory, not blocking).

2. **Read spec thoroughly** — Understand all requirements and acceptance criteria.

3. **Compute spec fingerprint** — SHA-256 hash of spec content (see `drift-reconciliation.md` § "Spec Drift Detection").

4. **Save spec snapshot** — Copy current spec to `.claude/support/previous_specifications/spec_v{N}_decomposed.md`.

5. **Parse spec into sections** — Extract `##` level headings and their content.

6. **Compute section fingerprints** — SHA-256 hash of each section (heading + content).

7. **Identify work items** — Each distinct piece of functionality per section.

8. **Create task files** — One JSON per task, difficulty <= 6, with full provenance:
   - `spec_fingerprint` — Hash of full spec computed in step 3
   - `spec_version` — Filename of spec (e.g., "spec_v1")
   - `spec_section` — Originating section heading (e.g., "## Authentication")
   - `section_fingerprint` — Hash of specific section computed in step 6
   - `section_snapshot_ref` — Snapshot filename (e.g., "spec_v1_decomposed.md")
   - **Important:** Create all task JSON files before regenerating the dashboard. Every task must have a `task-*.json` file — the dashboard is generated from these files, never the other way around.

9. **Map dependencies** — What must complete before what.

10. **Regenerate dashboard** — Follow `.claude/support/reference/dashboard-regeneration.md` in full.

---

## Task Creation Guidelines

- Clear, actionable titles ("Add user validation" not "Backend stuff")
- Difficulty 1-6 (break down anything larger)
- Explicit dependencies
- Owner: claude/human/both
- Include all spec provenance fields (fingerprint, version, section, section_fingerprint, section_snapshot_ref)
- **Phase field:** Assign `phase` based on spec section structure (e.g., tasks from "## Phase 1: Data Pipeline" get `"phase": "1"`). Also set `phase_name` to the spec's descriptive name for the phase (e.g., `"phase_name": "Data Pipeline"`). Dashboard rendering uses the format "Phase {N} — {phase_name}" — generic labels like "Phase 1" alone are not acceptable.
- **Decision dependencies:** If a task depends on an unresolved decision, add the decision ID to `decision_dependencies` array. Note whether the decision is an inflection point in task notes.
- **Cross-phase flag:** Consider suggesting `cross_phase: true` for long-lead tasks that must start before prior phase completion. Heuristic: `owner: human` tasks whose title or notes contain recruit/procure/approve/schedule/coordinate/stakeholder/vendor/contract, OR any task with `external_dependency.expected_date` more than 14 days out. When the heuristic fires, ask the user: `"Task {id} looks like long-lead work. Mark as cross_phase: true? [Y/N]"`. Never set silently. See `task-schema.md` § `cross_phase` for semantics.

---

## Spec Status Transition

When decomposition begins, update the spec metadata `status` from `draft` to `active`:

```yaml
---
version: 1
status: active
---
```

This signals that the spec is being implemented. The transition to `complete` happens in the "If Completing" section of `/work`.

---

## Organizing Tasks Into Stages

When decomposing the spec, organize tasks into logical implementation stages:

| Stage | Focus | Examples |
|-------|-------|----------|
| **Foundation** | Setup, core infrastructure, initial research | Project structure, database schema, vendor research, requirements gathering |
| **Core Features** | Main functionality from spec | Primary user flows, API endpoints, procurement, key deliverables |
| **Polish** | Edge cases, error handling, refinement | Validation, error messages, budget reconciliation, final reviews |
| **Validation** | Testing, documentation, verification | Unit tests, integration tests, documentation, acceptance checks |

These are organizational stages for tasks within the Execute phase, not workflow phases.

---

## Decomposition Quality Checks

Each task must have:
- Clear "done" criteria
- Independent testability
- Explicit dependencies
- Difficulty <= 6

For the difficulty scale, see `.claude/support/reference/shared-definitions.md`.
