# CLAUDE.md

Environment instructions for Claude Code. This file is template-owned — do not edit directly. Project-specific instructions belong in `./CLAUDE.md` (project root).

## Model Requirement

This environment is designed for **Claude Opus 4.6** (`claude-opus-4-6`). All agents (implement-agent, verify-agent, research-agent) must run on Opus 4.6.

**Output token constraint:** Claude Code caps output at 32K tokens per response (thinking + text + tool arguments share this budget). Agents should avoid writing large artifacts and reasoning deeply in the same response.

## Navigation

| What | Where |
|------|-------|
| Project specification | `.claude/spec_v{N}.md` (source of truth) |
| Dashboard (navigation hub) | `.claude/dashboard.md` |
| Task data | `.claude/tasks/task-*.json` |
| Commands | `.claude/commands/*.md` |
| Agent definitions | `.claude/agents/*.md` |
| Decisions | `.claude/support/decisions/decision-*.md` |
| Reference docs | `.claude/support/reference/` |
| Vision documents | `.claude/vision/` |
| Workspace (scratch) | `.claude/support/workspace/` |
| User documents | `.claude/support/documents/` |
| Feedback | `.claude/support/feedback/` |
| Project instructions | `./CLAUDE.md` (root) |

## Critical Invariants

- The spec is the source of truth. All work aligns with it, or the spec is updated intentionally.
- Verification is structurally enforced. A task cannot reach "Finished" without `task_verification.result == "pass"`.
- Use the project's task system (`.claude/tasks/task-*.json`). Never use built-in TaskCreate/TaskUpdate/TaskList tools.
- verify-agent always runs as a separate agent (fresh context, no implementation memory).
- Exactly one `spec_v{N}.md` exists in `.claude/` at any time.
- Never commit credentials to tracked files.
- Never create working documents in the project root — use `.claude/support/workspace/`.

## Environment Commands

| Command | Purpose |
|---------|---------|
| `/work` | Start or continue work (decompose, route to agents, complete tasks) |
| `/work pause` | Graceful wind-down (preserve context before compaction) |
| `/work complete` | Complete current in-progress task |
| `/iterate` | Spec review and refinement |
| `/review` | Implementation quality review (advisory, read-only) |
| `/status` | Quick view of project state |
| `/research` | Investigate options for decisions |
| `/feedback` | Capture and manage improvement ideas |
| `/breakdown {id}` | Split complex tasks into subtasks |
| `/health-check` | Validate system health and template sync |

## Design Philosophy

This environment is domain-agnostic — it works for software, research, procurement, renovation, or any spec-driven project. Dashboard language, task tracking, and verification adapt to the project domain.

## Workflow Rules

Detailed workflow rules are in `.claude/rules/`:
- `task-management.md` — statuses, difficulty, ownership, parallel execution
- `spec-workflow.md` — spec lifecycle, propose-approve-apply, vision documents
- `decisions.md` — decision records, inflection points
- `dashboard.md` — navigation hub, interaction modes, regeneration strategy
- `agents.md` — agent separation, tool preferences, model requirement
- `archiving.md` — file placement, archive locations, credentials

## Glossary

`.claude/support/reference/shared-definitions.md` contains canonical definitions for all environment terminology.
