# Specification Workflow Rules

## Source of Truth

The spec is the living source of truth. All work aligns with it, or the spec is updated intentionally. Tasks follow the spec, not the other way around.

## Acceptance-criteria authority

The spec defines *what* the acceptance criteria are. Whether they're met *now* is owned by verify-agent's `criteria[]` in `.claude/verification-result.json`, rendered as the dashboard's Acceptance-criteria section. Inline `- [ ]` boxes in a spec are authored input, not live status: nothing ticks them on phase PASS (auto-ticking was declined — the mapping is unsafe and would trip drift detection and the spec-edit guardrail), so they may read stale. `/audit-coherence`'s `acceptance-reconciliation` lens surfaces divergence advisorily; reconciling the boxes routes through `/iterate`.

## Spec Location

The project specification lives at `.claude/spec_v{N}.md` (exactly one file; `/work` discovers N by globbing). Exactly one spec file exists in `.claude/` at any time.

## Section-scoped spec reading

Specs can outgrow a working context (one downstream spec passed 840K chars), so read them **section-scoped** by default:

1. **Consult the index first.** `.claude/spec_v{N}.index.json` lists every `## ` section with heading, 1-based `line_start`/`line_end`, `fingerprint`, and a one-line `synopsis`. Generate it with `python3 .claude/scripts/fingerprint.py --index .claude/spec_v{N}.md > .claude/spec_v{N}.index.json` (the script prints to stdout; the redirect writes the file).
2. **Read only the section(s) you need** with `Read offset=line_start limit=(line_end − line_start + 1)`.
3. **Freshness guard.** The index is stale if missing or if its `spec_fingerprint` differs from the current full-spec hash. `/work` regenerates it in Step 1b (`drift-reconciliation.md § "Spec Index Freshness"`); other consumers regenerate before trusting it, or, if they can't write `.claude/` (subagents), use it only when fresh and otherwise read the spec directly. A stale index costs performance, never correctness.

**Read the whole spec** for first decomposition, a full coherence audit, or a task that genuinely spans most sections. This is a convention, not a gate, and it keeps the single-file `spec_v{N}.md` invariant.

## Propose-Approve-Apply

Present spec changes as explicit declarations (what changes, where, proposed text); apply only after user approval. Every declaration must tag each change with its origin: `[requested]`, `[proposed]`, or `[assumption]`. You CAN perform infrastructure operations autonomously (archiving, version transitions, frontmatter updates). Every spec-change proposal must end with a `## Decisions in This Proposal` section enumerating each non-trivial choice tagged `[NEEDS APPROVAL]`, `[FROM EXISTING SPEC]`, or `[USER REQUESTED]`. `/iterate` does not proceed to apply until every `[NEEDS APPROVAL]` item is resolved — this makes silent Claude-inferred decisions visible before they land in the spec.

To create or revise specifications, run `/iterate`.

## Direct edits to spec, decision, and vision files

**Substantive text edits to `.claude/spec_v*.md` and `.claude/support/decisions/decision-*.md` MUST route through `/iterate` (or, for decisions, `/research` + the decision record's `## Select an Option` checkbox)**, however small the change and whatever its source: audit findings whose `iterate_routing` names `/iterate`, drift-sweep cleanups from `/work` or `/audit-coherence`, and direct user requests that touch spec language. Routing through `/iterate` keeps the intent on record; fingerprint drift detection alone misses subtle semantic shifts.

**Vision files (`.claude/vision/**/*.md`)** are editable in place **while developing** (maturity 🟡/🔵, `status: vision`) — `/grill`/`/shakedown` findings, fork resolutions, amendment-log entries; the vision's amendments log and fork tracker are its audit trail. **After graduation** (🟢 / `status: distilled-to-spec`) a section is frozen: changes route through `/iterate` against the spec.

**Infrastructure operations stay autonomous:** archiving (`spec_v{N}.md` → `previous_specifications/`), version transitions (creating `spec_v{N+1}.md`), and frontmatter updates (e.g. `decided:` after the user selects; `status` and `ratified` on an agent-recorded decision after the user says to ratify or reconsider it, plus unticking a box the agent ticked when one is reconsidered). They don't change substantive text.

**Enforcement (the spec-edit guardrail):** `.claude/settings.json` `permissions.ask` on `Edit`/`Write` to these three path patterns prompts before any such edit lands; "Yes, don't ask again" makes it one click per session.

## Vision Documents

A vision document is the **development hub for a larger feature** — and the required ideation artifact before *initial* spec creation. It is not a one-time pre-spec brainstorm: it's a recurring per-feature workspace where a larger feature is developed broadly — repeated `/grill` and `/shakedown` passes folding findings *into the vision* — until it's tight enough to graduate to the spec.

**Structure.** Start from the scaffold `.claude/vision/_feature-vision-template.md` (copy it to `.claude/vision/<feature-slug>.md`). It formalizes the feature-vision shape: an immutable header (`status` / `supersedes` / scope), a thesis, `§`-sections each carrying a **maturity banner** (🟡 DRAFTED → 🔵 RESEARCHED → 🟢 SHIPPED) with citable evidence, one canonical **Open-forks tracker** (each fork → its probe tool + resolution/pending), a **status map**, an **evidence index** (cite corpora, never copy), and a structured **amendments** log. `_`-prefixed files are scaffolds, not visions — consumers skip them.

**Lifecycle.**
1. Capture the vision (copy the scaffold; ideation in Claude Desktop or in-session).
2. **Develop it** — `/grill` (sharpen meaning) and `/shakedown` (capture edge-cases / world-knowledge) targeting the vision; findings fold into the structured vision; sections mature 🟡→🔵.
3. **Graduate** — when a section is tight (🔵), `/iterate distill` (initial spec) or `/iterate` (amend an existing spec) lands it in the spec; flip the banner to 🟢 and move `status:` toward `distilled-to-spec`.

**Editability:** see § "Direct edits…" above (in place while developing, frozen after graduation).

**Target-awareness.** `/grill` and `/shakedown` are target-aware: point them at a vision (develop a larger feature), a spec section (refine committed scope directly — the lighter path, no vision needed), or the running build (behavior probe). *The target you choose sets the altitude.* `/grill` also updates `./CONTEXT.md` inline as domain terms resolve, in any mode.

## Workflow Cycle

**Spec** (define requirements) → **Execute** (implement-agent) → **Verify** (verify-agent).

Primary command: `/work` — checks spec alignment, decomposes tasks, routes to specialist agents.

**Bug tasks:** when a task's failure mode isn't obvious from inspection (hard bugs, non-deterministic failures, performance regressions), prefer `/diagnose` (`.claude/commands/diagnose.md`) — its 6-phase methodology produces a falsifiable hypothesis + regression test before the fix lands, which is what verify-agent expects under `.claude/rules/agents.md § "Root Cause Over Symptom"`.

**Working backward from the built product (or the spec/vision):** `/shakedown` (`.claude/commands/shakedown.md`) is *acceptance-by-example* — the channel for the edge-cases and real-world knowledge only you have. It's **target-aware**: probe a vision, the spec (pre-build), or the running build; a directed-grill Phase 0 calibrates the lens (general-first), then each example is grounded against the target and verdicted into a snapshot-anchored capability-boundary corpus. `⚠` gaps + drafted deltas emit to the merge queue (`.claude/support/reference/merge-queue.md`) and surface on the next `/iterate`; genuine design forks route to `/research`. The mirror of `/grill` (which sharpens *meaning*).

Parallel execution is the default when `/work` finds multiple pending tasks with no mutual dependencies or file conflicts.

## References

- Spec checklist: `.claude/support/reference/spec-checklist.md`
- Workflow details: `.claude/support/reference/workflow.md`
- Drift reconciliation: `.claude/support/reference/drift-reconciliation.md`
