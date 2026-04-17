# Specification Workflow Rules

## Source of Truth

The spec is the living source of truth. All work aligns with it, or the spec is updated intentionally. Tasks follow the spec, not the other way around.

## Spec Location

The project specification lives at `.claude/spec_v{N}.md` (exactly one file; `/work` discovers N by globbing). Exactly one spec file exists in `.claude/` at any time.

## Propose-Approve-Apply

Present spec changes as explicit declarations (what changes, where, proposed text); apply only after user approval. Every declaration must tag each change with its origin: `[requested]`, `[proposed]`, or `[assumption]`. You CAN perform infrastructure operations autonomously (archiving, version transitions, frontmatter updates). Every spec-change proposal must end with a `## Decisions in This Proposal` section enumerating each non-trivial choice tagged `[NEEDS APPROVAL]`, `[FROM EXISTING SPEC]`, or `[USER REQUESTED]`. `/iterate` does not proceed to apply until every `[NEEDS APPROVAL]` item is resolved — this makes silent Claude-inferred decisions visible before they land in the spec.

Direct edits to the spec are always safe — the decomposed snapshot preserves the before-state, and drift detection handles reconciliation.

To create or revise specifications, run `/iterate`.

## Vision Documents

Every project starts with ideation. A vision document is required before spec creation.

1. Brainstorm in Claude Desktop (or any tool)
2. Save the result to `.claude/vision/`
3. Run `/iterate distill` to extract a buildable spec

Vision docs can be added throughout the project lifecycle — the vision folder is a living input, not a one-time artifact.

## Workflow Cycle

**Spec** (define requirements) → **Execute** (implement-agent) → **Verify** (verify-agent).

Primary command: `/work` — checks spec alignment, decomposes tasks, routes to specialist agents.

Parallel execution is the default when `/work` finds multiple pending tasks with no mutual dependencies or file conflicts.

## References

- Spec checklist: `.claude/support/reference/spec-checklist.md`
- Workflow details: `.claude/support/reference/workflow.md`
- Drift reconciliation: `.claude/support/reference/drift-reconciliation.md`
