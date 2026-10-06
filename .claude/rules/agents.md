# Agent Rules

## Separated Concerns

Three specialist agents with distinct roles:
- **implement-agent** — executes tasks and produces deliverables. Does not verify.
- **verify-agent** — validates implementation independently (separate context, no implementation memory). Does not fix.
- **research-agent** — investigates options for decisions. Populates evidence and comparison matrices but never makes selections.

## Context Separation

verify-agent always runs as a separate subagent (`Agent` tool), dispatched by the `/work` orchestrator — never inline in the implementation conversation. This applies to both sequential and parallel execution modes. "Fresh eyes" is preserved because the verifier evaluates in its own context with no implementation memory; the fact that the orchestrator (not the verify-agent itself) writes the verification result to the task JSON does not affect verification independence. See DEC-004.

## Dispatch Invariants vs Efficiency Defaults (FB-119)

The orchestrator's own work gets the same independent check as a subagent's. Two kinds of dispatch rule, and they are not interchangeable:

- **Invariant — verify-agent dispatch.** Every task reaches Finished only through a separate verify-agent, **whoever implemented it**, orchestrator included. The orchestrator never verifies its own work, writes a "rollup" pass, or skips verification because a change was small. If the harness can't dispatch a subagent (the Agent tool is unavailable or restricted), the task stays in Awaiting Verification and goes on the Needs-you card; it does not become Finished.
- **Efficiency default — implement-agent dispatch.** For a task you can finish in a handful of tool calls (typically difficulty ≤ 2, touching one or two files), the orchestrator may implement inline instead of dispatching implement-agent. Inline work follows the same contract implement-agent would: set In Progress first; run the project's existing checks; for a behaviour-changing edit, record what the behaviour was before and after (e.g. the outputs the change affects), because a regression can't be seen from the diff alone; prepend an `[INLINE]` note to `notes`, naming files touched and checks run; record any friction markers you'd expect implement-agent to emit; hold any non-trivial choice in the task's `decisions_pending` (`work-procedures.md` "Hold decisions"); then set Awaiting Verification and dispatch verify-agent. Anything larger goes to implement-agent.

## Orchestrator-Authored State Claims (FB-119)

When the orchestrator writes a claim *about* state into `.claude/` — "the build did not change since verification", a hash, a count, a timestamp, a supersession annotation in `verification-result.json` — the claim must come from a measurement made in the same step, and it names the measurement: the command and its range (e.g. `git log <verified_at>..HEAD -- <paths>`: 0 commits). A claim you can't back with a measurement is written as unverified, or not written.

The same applies when carrying a task record's description of external or live state (a deployed model, a live table, an API's behaviour) into a new task or fix task: re-measure it, or mark it as quoted-unverified. Recorded descriptions of live state go stale; the record is not evidence that the state is still true.

## State Ownership

All `.claude/` state transitions (task JSON writes, dashboard regeneration, verification-result.json, session-log.jsonl) are owned by the orchestrator (the main session running `/work`, or `/research` for decision records). Subagents (implement-agent, verify-agent, research-agent) return structured reports; they do not write to `.claude/` paths. This is a hard constraint of the Claude Code harness (subagents are sandboxed from `.claude/` writes per Anthropic issue #38806) and is not expected to change. See DEC-004 for the full rationale.

**Capability grounding:** the subagent boundaries above (no `.claude/` writes, no `permissions.allow` inheritance, Explore/Plan agents skip CLAUDE.md + git status; nested dispatch is platform-supported but not used by the template) are documented in `.claude/support/reference/claude-code-authoring.md § "Subagent Boundaries"` as load-bearing constraints for spec/skill/agent authors who would otherwise design workflows that violate them. The reference doc is the canonical home for "facts about Claude Code that authors trip over" (DEC-017).

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

**For hard bugs where the root cause isn't obvious from inspection** — non-deterministic failures, performance regressions, tests that fail in unclear ways — route through `/diagnose` (`.claude/commands/diagnose.md`). The 6-phase methodology (feedback loop → reproduce → falsifiable hypotheses → instrument → fix + regression test → cleanup + post-mortem) is the structural enforcement mechanism for this rule on multi-turn debugging. The Phase 3 falsifiable-hypothesis discipline is what prevents the "swap-and-see" pattern that produces symptom-only fixes.

## Domain Glossary Awareness

Projects may keep `./CONTEXT.md` at the project root — a project-owned domain glossary populated by `/grill`. **Lazily-created**: the template never ships a placeholder; `/grill` creates it on the first resolved term. Absent in projects that haven't run `/grill` (fine — agents fall back to spec/code vocabulary).

**implement-agent:** when `./CONTEXT.md` is present, read it before producing deliverables; match its terminology in code, comments, task descriptions, and user-facing artifacts. If the user's request uses an alias listed in CONTEXT.md's `_Avoid:` field, surface the mismatch (`scope_clarification_needed` in the return report) rather than silently translating.

**verify-agent:** when `./CONTEXT.md` is present, treat its glossary as authoritative for vocabulary checks during `spec_alignment` / `consistency_check`. A load-bearing domain noun absent from CONTEXT.md (appears 3+ times across implementation) signals either glossary drift or a missing entry — emit a `vocab_drift` friction marker rather than failing verification.

**Maintenance.** `/grill` grows and refines CONTEXT.md inline as terms resolve in conversation. Agents do **not** batch-extract terms or autogenerate placeholder glossaries (per Pocock's deprecation lesson — pre-populated glossaries don't get maintained, organically-grown ones do).

**Layer distinction.** `./CONTEXT.md` is project domain vocabulary (your Customer/Order/Invoice or equivalent). `.claude/support/reference/shared-definitions.md` is environment vocabulary (Pending/In Progress statuses, difficulty 1-10, owner enums). Both coexist; never collapse.

`/audit-coherence`'s `vocab-drift` lens consumes CONTEXT.md when present (see `commands/audit-coherence.md § "Lens 2 — vocab-drift"`).

## Behavioral Rules

**Respect prior kills.** When the user kills a long-running process (dev server, file watcher, batch loop, mass-file processor, external-API scan), do not restart it in the same session without renewed approval. "Kill" signals: explicit user message ("kill it", "stop the server", "cancel"), pressing Ctrl+C in a captured terminal, `/work pause`, or any explicit halt instruction.

The rule applies to the killed process AND to semantically equivalent replacements (killing `npm run dev` then starting `pnpm dev` on the same port IS a restart). Before re-initiating any halted long-running process, confirm with the user.

This complements DEC-005's permission-layer gate (which stops unauthorized tool calls): that gate catches unapproved starts; this rule catches authorized-but-destructive re-starts after an explicit halt. Behavioral rule, not a permission — auto mode (which approves tool calls by classifier) does not absorb it.

Note: starting a dev server for UI verification is a feature (per root `CLAUDE.md` guidance on UI testing), not a violation. The rule applies to *restarting after a kill*, not to initial starts.

**Acknowledge mid-batch user messages.** When the user sends any message during an active autonomous batch (`autonomous_batch_position >= 3` per `commands/work.md § "Autonomous batch heartbeat"`), default to: (a) acknowledge receipt of the message, (b) summarize current batch state (which task is in progress, position N of M, what was verified so far), and (c) offer the user `[C] Continue batch | [P] Pause here | [reply with instructions to redirect]`. Do NOT treat the message as a green light to auto-continue — even seemingly-incidental remarks during long autonomous stretches are likely check-in signals.

The rule applies regardless of message intent (question, observation, instruction). The user can override by replying `C`, `continue`, or `keep going` — the explicit override is the green light. Below `autonomous_batch_position < 3`, the orchestrator's normal message-interpretation flow applies.

This complements the heartbeat (which reduces ping frequency) by catching the pings that still happen. Both rules share the same `autonomous_batch_position >= 3` threshold — one configuration knob, one set of reset rules, one mental model.

## Command Invocation Gates

`/breakdown`, `/research`, `/iterate`, `/work`, `/feedback` and `/zoom-out` carry `disable-model-invocation: true`: you can't fire them yourself via the `Skill` tool, but the user can type them and you can suggest them. Selection criteria, sub-mode coupling, and authoring hazards: `.claude/support/reference/claude-code-authoring.md § "disable-model-invocation: true"` (lazy).

## Cross-Project Capture Protocol

**Moved to `.claude/support/reference/extension-hooks.md § "Cross-Project Capture Protocol"` (lazy — not auto-loaded).** READ it BEFORE recommending the template→sync flow or a project→template promotion — its pre-sync boundary check prevents silently losing local additions to template-owned files.

## MCP and Parallel Execution

**Moved to `.claude/support/reference/mcp-patterns.md` (lazy — not auto-loaded).** READ it before dispatching any parallel batch that involves MCP-driving work. The one-line rule: single-session MCPs (Playwright/browser, auth-session, connection-pooled) cannot fan out across parallel subagents — route all calls to a shared MCP through ONE agent, sequentially.

## MCP and Result-Size Constraints

**Moved to `.claude/support/reference/mcp-patterns.md`.** The one-line rule: `browser_snapshot` on long pages silently truncates past the per-call token budget — prefer `browser_evaluate` with targeted queries; the same applies to any MCP returning large result objects.

## Tool Preferences

Prefer the harness's dedicated file tools (Read, Edit, Write; Glob and Grep where present) over `cat`/`sed`/`echo >` and Bash search (fewer permission prompts in subagents). Without a Grep/Glob tool, search via Bash (`rg`, `find`); instructions naming Grep or Glob then mean that. Plain `rg` skips hidden paths like `.claude/` and gitignored files (`--hidden` adds the first, `-uu` both). Bash is otherwise for git, tests, running deliverables, and network calls. Each agent's own `## Tool Preferences` covers its Bash and editing specifics.

Subagents cannot write to `.claude/` paths and don't inherit parent `permissions.allow` rules; when an agent's workflow describes a state transition, it means "include in the return report", and the orchestrator writes it. Nested dispatch is platform-supported (three levels by default) but the template doesn't use it: the orchestrator performs all dispatch, for portability and because state writes still flow through the orchestrator.

**Scripts under `.claude/scripts/`** are deterministic, read-only-by-default helpers the orchestrator runs via Bash (contract: `.claude/scripts/README.md`; `settings.json` allows `python3 .claude/scripts/*.py` without prompting, except `sync-apply.py`, the template-sync writer, which asks). Subagents don't run them. A script is an advisory alternative to its matching prose procedure; without it, the prose still works. Tests: `python3 -m unittest discover .claude/scripts/tests/`.

## Negative Findings Require a Positive Control

An absence claim ("X is absent / dormant / unused / has no consumer / never fires") may be persisted to durable state (friction register, handoff, dashboard, verification result, memory, retirement proposal), or used to close a finding, only with a **positive control that returns a hit**: the same probe (tool, flags, root, filters) finding a known-present target, whatever the tool. Otherwise report "unverified absence" and write nothing. Trust a new guard or check only after seeing it fail on the regression it targets. Read `.claude/support/reference/negative-findings.md` before persisting an absence claim, closing a finding with a sweep, or mutation-testing a guard.

Why: probes fail silently, and an empty result reads as "not found" (styler FR-040: a silent grep failure became a false "engine dormant" finding that cost a session).

## Dispatch Convention

Dispatch implement-agent, verify-agent and research-agent via the `Agent` tool with `subagent_type: "general-purpose"`, directing the persona in the prompt ("You are the verify-agent. Read `.claude/agents/verify-agent.md`..."). Keep all dispatch sites uniform on this; the portability rationale and the migration gate to named types live in `.claude/support/reference/claude-code-authoring.md § "subagent_type: \"general-purpose\" portability convention"` (lazy).

## Model Requirement

All agents run on the model pinned in `.claude/CLAUDE.md § Model Requirement` — the canonical source for both the design pin and the `Agent` dispatch value.

**Effort defaults:** Opus 5.5 defaults to `medium` effort on every plan, which matches or beats Opus 5 at `high` on coding and knowledge work. Don't add "ultrathink" or "think carefully" instructions by default. The standing exception is phase-level verification, whose dispatch includes "ultrathink" (it requests deeper reasoning for that turn; the effort level sent to the API is unchanged). To lower thinking, lower effort rather than instructing it in the prompt. Per-agent effort is possible via `effort:` frontmatter in a named agent definition, which the `general-purpose` Dispatch Convention doesn't use yet.

## Friction Register

Both `implement-agent` and `verify-agent` emit a `friction_markers[]` array in their return reports. The orchestrator (`/work`) routes markers based on `type`:

- **Template-improvement kinds** (`workflow_deviation`, `informal_decision`, `scope_creep`, `user_feedback_signal`, `template_gap`, `verification_failure`, `false_positive`, `verification_gap`, `spec_ambiguity`) → appended to `.claude/support/workspace/.session-log.jsonl` only.
- **Audit-eligible kinds** (`vocab_drift`, `path_drift`, `design_contradiction`, `terminology_mismatch`, `spec_implementation_gap`) → appended to `.session-log.jsonl` AND to `.claude/support/friction.jsonl` with an assigned `FR-NNN` id and `status: open`. Consumed by the future `audit-coherence` command (audit family Stage 3+).

Audit-eligible markers REQUIRE a `source_anchor` field (file + section reference, e.g. `spec_v13.md § 42.5`) so the audit's [Fix it] mechanism can re-read the cited source at apply time.

See `.claude/support/reference/friction-register.md` for the full schema, write protocol, status update protocol, and relationship between the two persistence stores.

## References

- implement-agent: `.claude/agents/implement-agent.md`
- verify-agent: `.claude/agents/verify-agent.md`
- research-agent: `.claude/agents/research-agent.md`
- friction-register: `.claude/support/reference/friction-register.md`
