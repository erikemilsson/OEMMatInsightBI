# Shakedowns

Capability-boundary maps produced by `/shakedown` (DEC-019). Each file is one *acceptance-by-example* session: real and edge-case usage thrown at the built/envisioned system, each example grounded against what the system actually does and verdicted, accumulated into a snapshot-anchored corpus.

## What lives here

One file per shakedown: `{slug}-{YYYY-MM-DD}.md`. The date anchors the map to a system snapshot — a shakedown is "where the system is, and where I want it, as of that date."

These are **project-generated outputs**, not template content. The directory + this README ship with the template; the shakedown docs themselves are created per-project and are gitignored (like `.claude/support/audits/`).

## Doc structure

- **Lens** (top) — the dimensions each example is judged against, the verdict legend, and the cleave/heuristic, established in the shakedown's Phase 0 directed grill.
- **Model so far / Parked / Boundary criteria** — the living model, refined between examples.
- **Entries** — one per example: restatement → breakdown → grounding-against-the-system → verdict.

## Verdict legend (base; extend per project)

- **✓** expressible as-is · **⚠** needs a new capability (gap to build) · **✗** out of scope · **❓** ambiguous / forks.

## How findings flow onward

`/shakedown` proposes routes; you fire them. ⚠ → `/iterate` or `/research`; ✗ → out-of-scope / setting note; ✓ → optional `test_protocol` seed; Parked → forward backlog. The corpus is triple-duty: gap analysis (⚠/✗), acceptance probes (✓), and a forward-direction map (Parked + boundary).

See `.claude/commands/shakedown.md` for the full workflow.
