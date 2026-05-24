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

**Capability grounding:** the subagent boundaries above (no `.claude/` writes, no nested `Task` calls, no `permissions.allow` inheritance, Explore/Plan agents skip CLAUDE.md + git status) are documented in `.claude/support/reference/claude-code-authoring.md § "Subagent Boundaries"` as load-bearing constraints for spec/skill/agent authors who would otherwise design workflows that violate them. The reference doc is the canonical home for "facts about Claude Code that authors trip over" (DEC-017).

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

Slash commands that perform substantive or irreversible work carry `disable-model-invocation: true` in YAML frontmatter to prevent autonomous invocation by the model. User-typed slash invocation continues to work; the model can still *suggest* the command in conversation. The gate only blocks the model's autonomous decision to fire the command via the `Skill` tool.

**Gated commands (template-shipped):** `/breakdown`, `/research`, `/iterate`, `/work`, `/feedback`.

**Selection criteria:**
- **Gate**: substantive writes, irreversible state transitions, ledger changes, expensive/long-running flows where autonomous fire is a foot-gun.
- **Leave open**: read-only audits (`/status`, `/health-check`, `/review`, `/audit-coherence` / `/audit-ui` non-triage modes) and conversational entry points where the model legitimately benefits from being able to ambient-invoke.

**Sub-mode coupling.** `disable-model-invocation` is per-file. Multi-mode commands (`/iterate`, `/work`, `/feedback`) gate as a whole — the model can no longer ambient-invoke their read-only sub-modes (`/work` no-args, `/iterate` no-args, `/feedback [text]` capture, `/feedback list`) either. Acceptable because user-typed slash invocation continues to work for all sub-modes, and the model can still surface suggestions in conversation. Future refactor option: split multi-mode files (e.g., `work-complete.md` separate from `work.md`) if the coupling produces observed friction.

**Defense-in-depth.** Upstream of DEC-005 (permission-layer auto mode) and DEC-016 (spec/decision/vision Edit/Write ask). DEC-005 catches tool calls the model shouldn't make; DEC-016 catches writes to protected paths; this gate prevents the model's *decision* to fire the command in the first place. All three layers compound.

**Authoring hazards.** Skill frontmatter scoping (`disable-model-invocation`, turn-scoped `model:` / `effort:`, `context: fork` + `agent:` pattern, `allowed-tools`) is documented in `.claude/support/reference/claude-code-authoring.md § "Skill Frontmatter Scope"` (DEC-017). Spec authors writing flows that depend on these primitives should consult that reference to avoid the "design pattern only obvious after hitting a wall" failure mode.

## Cross-Project Capture Protocol

When a session is about to recommend the **template→sync flow** — typically after surfacing a generally-useful rule, command, agent, skill, or reference doc in the current project that could ship to the template — run a boundary check FIRST. The template→sync flow can silently lose local additions to template-owned files if those additions weren't reconciled before the sync.

**Template-owned file globs** (sync-manifest `sync` category — projects should NOT modify these directly):

- `.claude/CLAUDE.md`
- `.claude/rules/*.md` (template-shipped names — not `project-*.md` which is project-owned)
- `.claude/skills/*/SKILL.md`
- `.claude/support/reference/*.md` (template-shipped names — not `project-*.md`)
- `.claude/agents/*.md`
- `.claude/commands/*.md` (template-shipped names — project commands like `audit-{name}.md` are project-owned)

Before recommending the sync, enumerate the project's local additions to any of the above (diff against last-synced template state, OR explicitly walk each known-template-owned file looking for project-specific content).

**Routing the findings:**

- **Generically-applicable additions** (rule clarifications, agent guidance, command refinements that any project could benefit from) → recommend **project→template promotion first** (FB-002/FB-003-style: capture as feedback in the template repo, ship via `/feedback review`, then sync). The promoted content lands in the template; the subsequent sync becomes a no-op convergence rather than a conflict.
- **Project-specific additions** (domain-specific rules, vocabulary, behaviors that don't generalize) → recommend **migration to a project-owned location first**. See `.claude/support/reference/extension-hooks.md` for the canonical map of extension need → project-owned location (rule imports → root `./CLAUDE.md`; project rules → `.claude/rules/project-*.md` gitignored; etc.).

Either way, surface the boundary check at suggestion time, not at sync time. Catching the violation at sync exit (after the user has already integrated local additions into a template-owned file) means manual reconciliation is the only path forward. Catching it upstream means clean ship paths.

**Why behavioral, not permission-layer:** the sync layer can structurally detect "local additions to template-owned file" at sync time (FB-059 / FB-060 structural fix, not yet shipped — see `template-maintenance/feedback.md` § FB-059 + FB-060). This rule reduces the *frequency* of the violation by preventing the upstream condition. Both layers compound.

## MCP and Parallel Execution

Single-session MCP servers cannot be safely fanned out across parallel subagents. Servers that expose stateful single-instance resources — Playwright MCP (one browser session), browser-automation MCPs, auth-session MCPs, connection-pooled MCPs — share their underlying state across all concurrent calls. Two parallel subagents calling the same MCP drive the **same** tab / session / connection; navigations, clicks, snapshots, and reads interleave silently. The failure mode is invisible — snapshots look fine but reflect another agent's mid-action state.

**Orchestrator pattern when a parallel batch involves MCP-driving work:**

1. **Route MCP-driving work through one agent.** Dispatch a single agent to handle all calls to the shared MCP (e.g., one Playwright agent for all UI inspection across routes).
2. **Parallelize the rest.** Other agents in the same batch do code reads, greps, test runs — anything that doesn't touch the shared MCP server.
3. **For multi-route inspection.** Dispatch sequential agents with focused scopes ("audit /coloring", then "audit /wardrobe"), not a parallel batch driving the browser.

True parallel browser inspection would require multiple MCP server instances on different ports or `user-data-dir`s — not how the template ships and not trivial to set up. Out of scope for most projects.

**Detection (lower priority):** `/work` Step 2c parallel-batch heuristic currently keys on `files_affected` only. It could be extended to check `mcp_resource_overlap` (any pair of tasks both expected to use the same single-instance MCP server) — same dispatch site as `shared_contract` detection in `parallel-execution.md`. Tracked separately if it becomes a recurring foot-gun.

## MCP and Result-Size Constraints

Playwright MCP `browser_snapshot` returns the full accessibility tree of the current page. For long-scroll pages or sites with many sections (over ~10K characters of DOM), the result can exceed the model's per-tool-call token budget and truncate silently — the snapshot appears empty or partial without an error.

For audits and verifications that only need specific elements, prefer `browser_evaluate` with targeted DOM queries (e.g., `document.querySelectorAll('h2').map(h => h.textContent)`). Reserve `browser_snapshot` for small pages or when you genuinely need the full tree.

The same pattern applies to other MCP servers that return large result objects: prefer targeted queries over full-state dumps when the task only needs specific data.

## Tool Preferences

All agents use dedicated tools (Read, Glob, Grep, Edit, Write) for file operations. Bash is reserved for operations requiring shell execution: git commands, running tests, executing deliverables, network requests. This minimizes permission prompts when agents run as subagents.

| Operation | Use | NOT |
|-----------|-----|-----|
| Read files | `Read` tool | `cat`, `head`, `tail` |
| Search by filename | `Glob` tool | `find`, `ls` |
| Search file content | `Grep` tool | `grep`, `rg` |
| Edit files | `Edit` tool | `sed`, `awk` |
| Write files | `Write` tool | `echo >`, heredoc |

Per-agent files reference this canonical mapping rather than restating it; bash-usage specifics, editing strategy, and large-file strategy live in each agent's own `## Tool Preferences` section.

Subagents cannot write to `.claude/` paths, cannot spawn nested `Task` tool calls, and do not inherit parent `permissions.allow` rules. When an agent's documented workflow describes a state transition, it means "include in return report"; the orchestrator performs the actual write.

**Scripts under `.claude/scripts/`** are deterministic helpers that ship with the template and are intended to be invoked by the orchestrator via the Bash tool. They have their own invocation contract (see `.claude/scripts/README.md`): stdlib only, read-only by default, structured stdout, clear exit codes. Subagents should not invoke them — the scripts return computed values for the orchestrator to write to `.claude/` state, which subagents cannot do. When a script is present, it is an advisory alternative to the matching prose procedure; when absent, the prose procedure still works.

Template-owned `.claude/settings.json` includes `Bash(python3 .claude/scripts/*.py:*)` in `permissions.allow` so orchestrator script invocations don't prompt. Tests for the scripts live in `.claude/scripts/tests/`; run with `python3 -m unittest discover .claude/scripts/tests/`.

## Dispatch Convention

When dispatching implement-agent, verify-agent, or research-agent via the `Task` tool, set `subagent_type: "general-purpose"` and direct the agent persona via prompt content ("You are the verify-agent. Read `.claude/agents/verify-agent.md`..."). The three current dispatch sites — `commands/work.md` (per-task verify, line ~605; phase-level verify, line ~688) and `commands/research.md` (research-agent, line ~74) — follow this convention.

**Why not named subagent_types?** Claude Code can auto-discover `.claude/agents/*.md` and expose each definition file as a named subagent_type (`implement-agent`, `verify-agent`, etc.), which would align dispatch shape with definition shape. As of 2026-05-13, the runtime availability of named-from-disk subagent types is not uniform across Claude Code harness versions — relying on auto-discovery risks dispatch failures in harnesses where it's absent. The persona-via-prompt-content pattern is portable across all current harness versions.

**Future migration:** When Claude Code's `.claude/agents/*.md` auto-discovery is stable across all supported harness versions, switch the three dispatch sites to named types. Validation gate: smoke-test by dispatching a single task with `subagent_type: "verify-agent"` and confirming the agent returns a per-task verification report (vs an error). Once validated, sweep all three sites and remove this rationale.

Until then, keep all three call sites uniform on `subagent_type: "general-purpose"` — the rule exists to prevent the previous state where the choice was neither documented nor uniformly applied.

## Model Requirement

All agents must run on Claude Opus 4.7 (`claude-opus-4-7[1m]`).

**Effort defaults:** Max/Team subscriptions default to medium reasoning effort. Use "ultrathink" in prompts when deeper reasoning is needed (phase-level verification, complex design decisions).

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
