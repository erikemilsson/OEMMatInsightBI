# Agent Rules

## Separated Concerns

Three specialist agents with distinct roles:
- **implement-agent** — executes tasks and produces deliverables. Does not verify.
- **verify-agent** — validates implementation independently (separate context, no implementation memory). Does not fix.
- **research-agent** — investigates options for decisions. Populates evidence and comparison matrices but never makes selections.

## Context Separation

verify-agent always runs as a separate Task agent, never inline in the implementation conversation. This applies to both sequential and parallel execution modes.

## Tool Preferences

All agents use dedicated tools (Read, Glob, Grep, Edit, Write) for file operations. Bash is reserved for operations requiring shell execution: git commands, running tests, executing deliverables, network requests. This minimizes permission prompts when agents run as subagents.

## Model Requirement

All agents must run on Claude Opus 4.6 (`claude-opus-4-6`).

**Effort defaults:** Max/Team subscriptions default to medium reasoning effort. Use "ultrathink" in prompts when deeper reasoning is needed (phase-level verification, complex design decisions).

## References

- implement-agent: `.claude/agents/implement-agent.md`
- verify-agent: `.claude/agents/verify-agent.md`
- research-agent: `.claude/agents/research-agent.md`
