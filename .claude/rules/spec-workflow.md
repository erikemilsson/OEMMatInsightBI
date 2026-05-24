# Specification Workflow Rules

## Source of Truth

The spec is the living source of truth. All work aligns with it, or the spec is updated intentionally. Tasks follow the spec, not the other way around.

## Spec Location

The project specification lives at `.claude/spec_v{N}.md` (exactly one file; `/work` discovers N by globbing). Exactly one spec file exists in `.claude/` at any time.

## Propose-Approve-Apply

Present spec changes as explicit declarations (what changes, where, proposed text); apply only after user approval. Every declaration must tag each change with its origin: `[requested]`, `[proposed]`, or `[assumption]`. You CAN perform infrastructure operations autonomously (archiving, version transitions, frontmatter updates). Every spec-change proposal must end with a `## Decisions in This Proposal` section enumerating each non-trivial choice tagged `[NEEDS APPROVAL]`, `[FROM EXISTING SPEC]`, or `[USER REQUESTED]`. `/iterate` does not proceed to apply until every `[NEEDS APPROVAL]` item is resolved — this makes silent Claude-inferred decisions visible before they land in the spec.

To create or revise specifications, run `/iterate`.

## Direct edits to spec, decision, and vision files (DEC-016)

**Substantive text edits to `.claude/spec_v*.md`, `.claude/support/decisions/decision-*.md`, and `.claude/vision/**/*.md` MUST route through `/iterate` (or, for decisions, `/research` + the decision record's `## Select an Option` checkbox; for vision, the user pastes from outside Claude Code).** This applies regardless of how small the change appears and regardless of context — including audit findings whose `iterate_routing` field already names `/iterate` as the route, drift-sweep cleanups inferred from `/work` or `/audit-coherence` output, and direct user requests that touch spec language without being formally framed as an `/iterate` proposal.

**Infrastructure operations remain autonomous** under Propose-Approve-Apply's existing carveout — archiving (e.g., moving `spec_v{N}.md` to `previous_specifications/` on version bump), version transitions (creating `spec_v{N+1}.md`), and frontmatter updates (e.g., setting `decided:` on a decision record after user selection). These don't require `/iterate` because they don't change substantive text.

**Structural enforcement** at `.claude/settings.json` (`permissions.ask` on `Edit` / `Write` against the three path patterns): the runtime prompts before any Edit/Write to these paths lands, regardless of provenance. Platform-native "Yes don't ask again" makes the per-`/iterate apply` cost one click per session.

**Why this matters:** drift detection's fingerprint-based reconciliation catches gross changes but can miss subtle semantic shifts (e.g., word-count-preserving substitutions). Routing through `/iterate` preserves the audit trail of *intent* alongside the state change. DEC-013 already secured this property on the audit `[Fix it]` surface; DEC-016 extends it to the broader behavioral surface across all Claude `Edit`/`Write` usage.

## Vision Documents

Every project starts with ideation. A vision document is required before spec creation.

1. Brainstorm in Claude Desktop (or any tool)
2. Save the result to `.claude/vision/`
3. *(Optional pre-distill enrichment)* Run `/grill {vision-file}` to surface fuzzy language, sharpen domain vocabulary against `./CONTEXT.md` (created lazily on first resolved term), and resolve ambiguity branch-by-branch before distilling. See `.claude/commands/grill.md`.
4. Run `/iterate distill` to extract a buildable spec

Vision docs can be added throughout the project lifecycle — the vision folder is a living input, not a one-time artifact. `/grill` can be re-run mid-project when fuzzy language creeps into the spec or codebase; it updates `./CONTEXT.md` inline as terms resolve.

## Workflow Cycle

**Spec** (define requirements) → **Execute** (implement-agent) → **Verify** (verify-agent).

Primary command: `/work` — checks spec alignment, decomposes tasks, routes to specialist agents.

**Bug tasks:** when a task's failure mode isn't obvious from inspection (hard bugs, non-deterministic failures, performance regressions), prefer `/diagnose` (`.claude/commands/diagnose.md`) — its 6-phase methodology produces a falsifiable hypothesis + regression test before the fix lands, which is what verify-agent expects under `.claude/rules/agents.md § "Root Cause Over Symptom"`.

Parallel execution is the default when `/work` finds multiple pending tasks with no mutual dependencies or file conflicts.

## References

- Spec checklist: `.claude/support/reference/spec-checklist.md`
- Workflow details: `.claude/support/reference/workflow.md`
- Drift reconciliation: `.claude/support/reference/drift-reconciliation.md`
