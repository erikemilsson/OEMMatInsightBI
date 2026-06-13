# CLAUDE.md

Environment instructions for Claude Code. This file is template-owned — do not edit directly. Project-specific instructions belong in `./CLAUDE.md` (project root).

## Model Requirement

This environment targets the **current Claude Opus tier** via the floating `opus[1m]` alias (float ratified 2026-06-11 per FB-096 sub-issue B; originally designed and validated on Opus 4.7). All agents (implement-agent, verify-agent, research-agent) run on the Opus tier.

**Canonical dispatch value** (single source — dispatch sites and agent files cite this section rather than restating it): `Task` dispatches set `model: "opus[1m]"`. The alias floats with the latest Opus release by design. **Regression escape hatch:** if agent regressions appear after an Opus release, pin dispatches to the last-known-good explicit model ID via a deliberate template change (full model IDs are accepted — docs-verified 2026-06-11, see `support/reference/claude-code-authoring.md § "Agent tool model parameter granularity"`) and record the pin + reason here.

**Output token constraint:** Claude Code caps output at 32K tokens per response (thinking + text + tool arguments share this budget). Agents should avoid writing large artifacts and reasoning deeply in the same response.

**Context budget:** 1M is headroom, not license. Keep agent context minimal — fewer, more accurate tokens produce higher-quality output. Prefer targeted reads, focused plans, and subagent delegation over broad context dumps.

## Navigation

| What | Where |
|------|-------|
| Project specification | `.claude/spec_v{N}.md` (source of truth) |
| Spec section index (generated, scoped reads) | `.claude/spec_v{N}.index.json` (DEC-021; `fingerprint.py --index`) |
| Dashboard (navigation hub) | `.claude/dashboard.md` |
| Task data | `.claude/tasks/task-*.json` |
| Commands | `.claude/commands/*.md` |
| Agent definitions | `.claude/agents/*.md` |
| Decisions | `.claude/support/decisions/decision-*.md` |
| Reference docs | `.claude/support/reference/` |
| Claude Code authoring hazards | `.claude/support/reference/claude-code-authoring.md` (DEC-017) |
| Vision documents | `.claude/vision/` |
| Shakedown corpus (capability maps) | `.claude/support/shakedowns/` (DEC-019) |
| Workspace (scratch) | `.claude/support/workspace/` |
| Reference documents (inputs) | `.claude/support/documents/` |
| Feedback | `.claude/support/feedback/` |
| Project extension hooks | `.claude/support/reference/extension-hooks.md` |
| Project instructions | `./CLAUDE.md` (root) |
| Project domain glossary (lazy, optional) | `./CONTEXT.md` (created by `/grill` on first resolved term) |

## Critical Invariants

- The spec is the source of truth. All work aligns with it, or the spec is updated intentionally.
- Verification is structurally enforced. A task cannot reach "Finished" without `task_verification.result == "pass"`.
- Use the project's task system (`.claude/tasks/task-*.json`). Never use built-in TaskCreate/TaskUpdate/TaskList tools.
- verify-agent always runs as a separate agent (fresh context, no implementation memory).
- Exactly one `spec_v{N}.md` exists in `.claude/` at any time.
- Never commit credentials to tracked files.
- Never create working documents in the project root — use `.claude/support/workspace/`.
- Settings layering: `.claude/settings.json` is template-owned (base `permissions.allow` AND `permissions.ask` — the `ask` set ships template-wide guardrails for spec/decision/vision file edits per DEC-016); put hooks, env vars, theme, and any additional permissions in `.claude/settings.local.json`. Claude Code merges both at runtime. Under `--permission-mode auto`, these rules short-circuit the runtime classifier — see `.claude/README.md` § Auto Mode for composition.
- Direct edits to `.claude/spec_v*.md`, `.claude/support/decisions/decision-*.md`, and `.claude/vision/**/*.md` route through `/iterate` (or analogous flow per category) — see `.claude/rules/spec-workflow.md § "Direct edits to spec, decision, and vision files (DEC-016)"`. Structurally enforced via `permissions.ask` in template-owned `.claude/settings.json`; infrastructure operations (archiving, version transitions, frontmatter) remain autonomous.
- Phase acceptance **status** authority is `.claude/verification-result.json`'s `criteria[]` (rendered as the dashboard's `### Acceptance Criteria`), **not** inline spec `- [ ]` acceptance boxes (authored input only) — DEC-022; see `.claude/rules/spec-workflow.md § "Acceptance-criteria authority (DEC-022)"`.
- Respect prior kills: when the user halts a long-running process (dev server, watcher, batch loop), do not restart it in the same session without renewed approval. See `.claude/rules/agents.md § "Behavioral Rules"` for the full rule.

## Environment Commands

| Command | Purpose |
|---------|---------|
| `/work` | Start or continue work (decompose, route to agents, complete tasks) |
| `/work pause` | Graceful wind-down (preserve context before compaction) |
| `/work complete` | Complete current in-progress task |
| `/iterate` | Spec review and refinement |
| `/grill` | Interview-style interrogation; no-args triages candidate areas first; auto-detects `./CONTEXT.md` |
| `/shakedown` | Acceptance-by-example: probe the built system against real-use examples to map its capability boundary (DEC-019) |
| `/diagnose` | Hard-bug / performance-regression discipline: 6 phases (feedback loop → reproduce → hypothesise → instrument → fix → cleanup + post-mortem) |
| `/zoom-out` | Go up a layer of abstraction — map the focus area's components and connections (uses `./CONTEXT.md` when present) |
| `/review` | Implementation quality review (advisory, read-only) |
| `/status` | Quick view of project state |
| `/research` | Investigate options for decisions |
| `/feedback` | Capture and manage improvement ideas |
| `/breakdown {id}` | Split complex tasks into subtasks |
| `/health-check` | Validate system health and template sync |
| `/audit-coherence` | Spec-vs-reality coherence audit (drift, vocab, paths, retired-feature markers); usually dispatched by `/health-check`; has a `triage` mode |
| `/audit-ui` | UI/UX audit — walks the running web app with Playwright across quality lenses; usually dispatched by `/health-check`; has a `triage` mode |

## Session Management

**Ending a session:** Run `/work pause` before closing a long conversation. This writes a handoff file that the next `/work` picks up automatically. Without it, the next session re-derives state from task files alone and may miss context.

**Resuming:** Use `claude --continue` (last session) or `claude --resume` (pick from list) to resume with full conversation context. A fresh `/work` in a new conversation works but relies on handoff files and auto-memory — it won't have the reasoning from the previous session.

**Mid-session context pressure:** Use `/compact focus on [what matters]` to summarize while preserving specific context. CLAUDE.md and rules files survive compaction automatically.

**Plans:** Write plans to files (`.claude/support/workspace/`), not conversation context. To explore, plan, then execute with fresh context: discuss the plan, have Claude write it to a file, `/clear`, then tell Claude to read and execute the plan file. This replaces the old "compact with plan" workflow.

## Design Philosophy

This environment is domain-agnostic — it works for software, research, procurement, renovation, or any spec-driven project. Dashboard language, task tracking, and verification adapt to the project domain.

## Workflow Rules

Rules files are loaded via explicit imports (Claude Code auto-reads `@path` references in CLAUDE.md):

@.claude/rules/task-management.md
@.claude/rules/spec-workflow.md
@.claude/rules/decisions.md
@.claude/rules/dashboard.md
@.claude/rules/agents.md
@.claude/rules/archiving.md
@.claude/rules/session-management.md

Summary of each:
- `task-management.md` — statuses, difficulty, ownership, parallel execution
- `spec-workflow.md` — spec lifecycle, propose-approve-apply, vision documents
- `decisions.md` — decision records, inflection points
- `dashboard.md` — navigation hub, interaction modes, regeneration strategy
- `agents.md` — agent separation, tool preferences, model requirement (MCP patterns + cross-project capture protocol live in lazy reference docs; the stubs inside say when to read them)
- `archiving.md` — file placement, archive locations, credentials
- `session-management.md` — ending sessions, persistence mechanisms, plans, context survival (user-facing session ops: `.claude/README.md § "Session Operations"`)
- `feature-retirement.md` — **lazy, NOT auto-loaded:** before retiring or restoring ANY feature, READ `.claude/rules/feature-retirement.md` first (snapshot, manifest, spec annotation, restore path)

## Glossary

`.claude/support/reference/shared-definitions.md` contains canonical definitions for all environment terminology.
