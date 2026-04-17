# Agent Rules

## Separated Concerns

Three specialist agents with distinct roles:
- **implement-agent** — executes tasks and produces deliverables. Does not verify.
- **verify-agent** — validates implementation independently (separate context, no implementation memory). Does not fix.
- **research-agent** — investigates options for decisions. Populates evidence and comparison matrices but never makes selections.

**Writer/Reviewer scales further with parallel sessions.** Within a single session, implement-agent and verify-agent already provide the writer/reviewer separation. For higher-rigor review — security audit, architectural review, independent quality pass — you can run two separate `claude` instances: Session A implements; Session B (fresh context, no implementation memory) reviews the finished code. This is optional and external to the template; the existing implement-agent / verify-agent split is sufficient for most work.

## Context Separation

verify-agent always runs as a separate Task agent, dispatched by the `/work` orchestrator — never inline in the implementation conversation. This applies to both sequential and parallel execution modes. "Fresh eyes" is preserved because the verifier evaluates in its own context with no implementation memory; the fact that the orchestrator (not the verify-agent itself) writes the verification result to the task JSON does not affect verification independence. See DEC-004.

## State Ownership

All `.claude/` state transitions (task JSON writes, dashboard regeneration, verification-result.json, session-log.jsonl) are owned by the `/work` orchestrator. Subagents (implement-agent, verify-agent, research-agent) return structured reports; they do not write to `.claude/` paths. This is a hard constraint of the Claude Code harness (subagents are sandboxed from `.claude/` writes per Anthropic issue #38806) and is not expected to change. See DEC-004 for the full rationale.

## Root Cause Over Symptom

When a test fails, a build breaks, a type error surfaces, or a runtime error occurs: fix the underlying cause, not the symptom.

**Symptom-only fixes that verify-agent rejects:**
- `try/except` (or equivalent) that silently swallows the error without handling it
- Suppressed linter/compiler warnings (e.g., `# type: ignore`, `@ts-ignore` without explanation)
- Skipped or deleted failing tests
- Magic-number overrides that work around a computed value rather than fixing the computation
- Mocks that paper over a real integration problem
- Catch-all error handlers that hide the specific failure

**The rule:** An implementation that makes an error disappear without understanding why the error occurred is not a completed task. If the root cause can't be fixed in the current task's scope, return `implementation_status: "blocked"` (not `completed`) with an `issues_discovered` entry explaining the underlying cause. Verify-agent rejects `completed` reports that suppress symptoms.

**When suppression IS acceptable:**
- The "error" is a spec-level design choice (e.g., the spec says "ignore malformed rows")
- A third-party library bug with a documented workaround (include a comment linking to the issue)
- Time-boxed mitigation with an explicit `issues_discovered` follow-up task

In those cases, the suppression is the fix — not a symptom hiding a bug.

## Behavioral Rules

**Respect prior kills.** When the user kills a long-running process (dev server, file watcher, batch loop, mass-file processor, external-API scan), do not restart it in the same session without renewed approval. "Kill" signals: explicit user message ("kill it", "stop the server", "cancel"), pressing Ctrl+C in a captured terminal, `/work pause`, or any explicit halt instruction.

The rule applies to the killed process AND to semantically equivalent replacements (killing `npm run dev` then starting `pnpm dev` on the same port IS a restart). Before re-initiating any halted long-running process, confirm with the user.

This complements DEC-005's permission-layer gate (which stops unauthorized tool calls): that gate catches unapproved starts; this rule catches authorized-but-destructive re-starts after an explicit halt. Behavioral rule, not a permission — auto mode (which approves tool calls by classifier) does not absorb it.

Note: starting a dev server for UI verification is a feature (per root `CLAUDE.md` guidance on UI testing), not a violation. The rule applies to *restarting after a kill*, not to initial starts.

## Tool Preferences

All agents use dedicated tools (Read, Glob, Grep, Edit, Write) for file operations. Bash is reserved for operations requiring shell execution: git commands, running tests, executing deliverables, network requests. This minimizes permission prompts when agents run as subagents.

Subagents cannot write to `.claude/` paths, cannot spawn nested `Task` tool calls, and do not inherit parent `permissions.allow` rules. When an agent's documented workflow describes a state transition, it means "include in return report"; the orchestrator performs the actual write.

**Scripts under `.claude/scripts/`** are deterministic helpers that ship with the template and are intended to be invoked by the orchestrator via the Bash tool. They have their own invocation contract (see `.claude/scripts/README.md`): stdlib only, read-only, structured stdout, clear exit codes. Subagents should not invoke them — the scripts return computed values for the orchestrator to write to `.claude/` state, which subagents cannot do. When a script is present, it is an advisory alternative to the matching prose procedure; when absent, the prose procedure still works.

## Model Requirement

All agents must run on Claude Opus 4.7 (`claude-opus-4-7[1m]`).

**Effort defaults:** Max/Team subscriptions default to medium reasoning effort. Use "ultrathink" in prompts when deeper reasoning is needed (phase-level verification, complex design decisions).

## References

- implement-agent: `.claude/agents/implement-agent.md`
- verify-agent: `.claude/agents/verify-agent.md`
- research-agent: `.claude/agents/research-agent.md`
