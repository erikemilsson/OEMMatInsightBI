# Claude Code Authoring Hazards

Load-bearing facts about the Claude Code platform that spec, skill, agent, and command authors need to know — and that aren't obvious without hitting a wall during implementation.

This doc is **additive and cross-referencing**: it consolidates facts not currently surfaced elsewhere (turn-scoped frontmatter, skill-content lifecycle, etc.) and cross-links to facts already canonically placed (subagent isolation in `agents.md`, MCP constraints, etc.).

**Last verified:** see footer at bottom of file.

---

## YAML Frontmatter Hazards

### Colon-space in `description:` field

The `description:` field in YAML frontmatter rejects unquoted `: ` (colon-space) under strict YAML 1.2 / PyYAML — the parser treats the second colon as an ambiguous mapping-value token and fails. Claude Code's deployment parser is permissive (silently loads the skill anyway), so the failure mode is silent at runtime but `verify-agent`'s strict YAML check rejects.

**Convention:** use em-dash (` — `) or quote the entire description value.

**Examples:**

```yaml
# BAD — strict YAML rejects
---
description: My skill: does the thing
---

# GOOD — em-dash separator
---
description: My skill — does the thing
---

# ALSO GOOD — quoted value
---
description: "My skill: does the thing"
---
```

The em-dash convention is the empirically-converged pattern across the template's 5+ SKILL.md files. Source: FB-082 (flirty-gym 2026-05-20, surfaced when verify-agent's PyYAML check failed on initial skill authoring; convergence on em-dash documented after T12 retry).

### Other ambiguous-mapping-value tokens

Beyond colon-space, avoid unquoted YAML values that begin with `[`, `{`, `&`, `*`, `!`, `|`, `>`, `'`, `"`, `%`, `@`, `` ` ``. These are also strict-YAML special-meaning tokens. If a description must start with one of these, quote the entire value.

---

## Skill Frontmatter Scope

### `model:` and `effort:` are turn-scoped, not session-scoped

Per `code.claude.com/docs/en/skills`: *"The override applies for the rest of the current turn and is not saved to settings; the session model resumes on your next prompt."*

This means:

- A skill that sets `model: opus` in its frontmatter overrides the model **for the rest of the current turn only**
- On the next user prompt, the session model (whatever was active before the skill) resumes
- **A multi-turn chat skill cannot rely on `model:` for cross-turn model continuity** — the override does not persist across turns

Same scope applies to `effort:` frontmatter.

**Implications for spec authoring:**
- Don't write spec text describing runtime model-switching as a feature of a multi-turn skill (this premise survived flirty-gym's spec authoring + task decomposition and only failed at implementation — see FB-083)
- For multi-turn flows requiring a specific model, the session model must be set by the user (CLI flag, `/model` slash command, settings file) — not by skill frontmatter

### `disable-model-invocation: true`

Prevents the model from autonomously invoking the skill via the `Skill` tool. User-typed slash invocation continues to work; the model can still suggest the skill in conversation. The gate only blocks the model's autonomous decision to fire.

**Template-shipped gated commands** (FB-071): `/breakdown`, `/research`, `/iterate`, `/work`, `/feedback`. Selection criteria + sub-mode coupling trade-offs in `rules/agents.md § "Command Invocation Gates"`.

### `context: fork` + `agent:` pattern

A skill can declare `context: fork` to execute in a forked context (separate from the parent conversation's context). Combined with `agent: <name>`, the forked context runs under that agent's persona. The forked context inherits the SKILL.md body + the agent's system prompt — but NOT the parent's full conversation history.

**Authoring guidance:** if a skill's instructions must reference parent-conversation state, do NOT use `context: fork`. Forked skills are best for self-contained workflows where the SKILL.md body fully specifies the work.

### `allowed-tools` and `permissions.allow` interaction

A skill's `allowed-tools` frontmatter declares which tools it expects to use. This pre-approves those tools for the skill's invocation (subject to project-level `permissions.allow` settings). Skills should declare only the tools they actually need — over-declaration grants unnecessary access; under-declaration triggers permission prompts mid-execution.

### Skill listing budget: 1,536 character cap on `description + when_to_use`

The skill listing context window has a budget for each skill's metadata. `description` + `when_to_use` combined must fit within ~1,536 characters or the listing truncates. Authors should keep `when_to_use` focused — usage criteria, not feature catalog.

### Auto-compaction re-attachment budget: 25K tokens

When auto-compaction fires during a skill invocation, the harness re-attaches the skill's content into the compacted context with a budget of ~25,000 tokens. Skills with bodies larger than this risk partial re-attachment after compaction. Keep SKILL.md bodies focused; offload large reference content to separate files under the skill's directory (referenced from SKILL.md but loaded only when needed).

### Skill content lifecycle: one-message-and-stays-for-session

The rendered SKILL.md content enters the conversation as one message and remains in the context for the rest of the session. This changes the spec/skill authoring model in two ways:

1. **Written guidance must be standing instructions, not one-time steps.** If the SKILL.md says "first do X, then do Y", the message persists — when the same skill is invoked again later in the session, the same "first do X" instruction is still in context. Authors should write skill bodies as *patterns* that apply to every invocation, not as *procedures* that fire once.

2. **Token cost accumulates per skill, not per invocation.** Each skill loaded into the conversation costs its full SKILL.md body in tokens — once, at first load. Subsequent invocations cost nothing additional. Optimize for first-load cost.

---

## Subagent Boundaries

Load-bearing constraints for spec and task authors. Full rules in `rules/agents.md § "State Ownership"` and `§ "Tool Preferences"`. The facts here are the ones spec/skill/agent authors most frequently violate.

### No `.claude/` writes (DEC-004)

Subagents are sandboxed from writing to `.claude/` paths. This is a hard Claude Code harness constraint, not a template convention. Spec authors must NOT specify subagent workflows that include writing task JSON, dashboard, decision records, friction.jsonl, or any other `.claude/` state. Subagents return structured reports; the orchestrator performs the writes.

### No nested `Task` tool calls

Subagents cannot spawn other subagents via the `Task` tool. Spec authors must NOT specify nested-dispatch workflows. If multi-level dispatch is needed, the orchestrator (`/work` or a top-level slash command) handles it.

### No `permissions.allow` inheritance from parent

Subagents do not inherit the parent conversation's `permissions.allow` rules. Each subagent dispatch operates under the template-shipped `permissions.allow` set only. Spec authors must NOT assume tools approved in the parent are auto-available in subagents.

### Explore / Plan agents skip CLAUDE.md + git status

Built-in `Explore` and `Plan` subagent types do NOT auto-read CLAUDE.md or run git status before working. Spec authors expecting agent-side context-awareness must either (a) include the context in the dispatch prompt, OR (b) use a different subagent type (e.g., `general-purpose`).

### Forked-skill context inheritance

Skills declared with `context: fork` inherit SKILL.md body + agent system prompt only. They do NOT inherit the parent's conversation history. Spec authors must NOT design forked-skill workflows that depend on parent-conversation state.

---

## Tool & Dispatch Surface

### `Agent` tool `model` parameter granularity

The `Agent` tool's `model` parameter exposes only `sonnet | opus | haiku`. There is no per-call effort control, no model-version specificity (no `claude-opus-4-7[1m]` granularity), no per-call thinking-budget setting. Effort selection is conversation-level (set at session start), not call-level.

**Implication:** spec authors cannot write task descriptions that vary effort per subagent dispatch. If a spec needs different effort levels for different tasks, the orchestrator (`/work`) must handle that through prompt-engineering ("ultrathink" inclusion), not through `model` parameters.

### `subagent_type: "general-purpose"` portability convention

Per `rules/agents.md § "Dispatch Convention"`: the three dispatch sites (`commands/work.md` per-task verify, phase-level verify; `commands/research.md` research-agent) use `subagent_type: "general-purpose"` and direct the agent persona via prompt content. This is portable across all current Claude Code harness versions. Future migration to named subagent types is gated on `.claude/agents/*.md` auto-discovery stability.

**Spec authors:** do not write tasks that reference named subagent types directly. Reference the orchestrator's dispatch behavior or the agent's prompt body instead.

---

## MCP Constraints

(Pointers — do NOT consolidate. Full rules live with the surrounding agent dispatch context.)

- **`rules/agents.md § "MCP and Parallel Execution"`** — single-session MCPs (Playwright, browser automation) cannot be safely fanned out across parallel subagents. Orchestrator pattern: route MCP-driving work through one agent; parallelize the rest.
- **`rules/agents.md § "MCP and Result-Size Constraints"`** — Playwright MCP `browser_snapshot` returns full accessibility tree; on long-scroll pages (~10K+ char DOM) the result truncates silently. Prefer `browser_evaluate` with targeted DOM queries.

---

<!-- Last verified against Claude Code docs: https://code.claude.com/docs @ 2026-05-24; against template_version: 4.9.0 -->
