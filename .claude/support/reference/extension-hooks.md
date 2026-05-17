# Project Extension Hooks

A canonical map of **where project-specific content goes** when extending the template environment. The template ships a shared core; projects add domain-specific rules, reference docs, decisions, commands, and operational documents — but where those additions land matters for both `/health-check` Part 5 sync hygiene and the cross-project capture protocol (`.claude/rules/agents.md § "Cross-Project Capture Protocol"`).

The rule: **never modify template-owned files** (`.claude/CLAUDE.md`, `.claude/rules/*.md` template-shipped names, `.claude/skills/*/SKILL.md`, `.claude/support/reference/*.md` template-shipped names, `.claude/agents/*.md`, `.claude/commands/*.md` template-shipped names). Project additions go to one of the project-owned locations below.

## Extension need → canonical home

| Extension need | Canonical home | Synced? |
|---|---|---|
| Project-specific instructions / context for Claude | `./CLAUDE.md` (project root) | No — user-owned |
| Rule imports (load additional rule files) | `./CLAUDE.md` (project root) | No — user-owned |
| Project-specific rule files | `.claude/rules/project-*.md` (e.g., `project-domain-vocabulary.md`) | No — `project-*.md` is in sync-manifest `ignore` |
| Project-specific reference docs (extracted from CLAUDE.md or new) | `.claude/support/reference/project-*.md` | No — `project-*.md` is in sync-manifest `ignore` |
| Project-specific slash commands (audit family or custom) | `.claude/commands/audit-{name}.md` or other non-template name | Custom names not in sync-manifest `sync` are untouched by sync |
| Project-specific skills | `.claude/skills/{name}/SKILL.md` (custom name; template-shipped `dashboard-style/`, etc. are template-owned) | Custom skill dirs untouched by sync |
| Project decisions (architectural choices, /research outcomes) | `.claude/support/decisions/decision-*.md` | No — `decision-*.md` is in sync-manifest `ignore` |
| Decision research archives | `.claude/support/decisions/.archive/*` | No — in sync-manifest `ignore` |
| Captured feedback (ideas, friction, deferred work) | `.claude/support/feedback/feedback.md` | No — in sync-manifest `ignore`. `/feedback` writes here, `/feedback review` triages |
| Vision documents (pre-spec ideation) | `.claude/vision/*.md` | No — in sync-manifest `ignore` |
| Workspace scratch (Claude's working drafts, plans, intermediate analysis) | `.claude/support/workspace/*` | No — in sync-manifest `ignore` |
| Reference documents (PDFs, contracts, vendor docs — inputs to Claude's work) | `.claude/support/documents/*` | Customize-category README, user-owned content |
| Project specification (source of truth for what gets built) | `.claude/spec_v{N}.md` (singular per project, version-bumped) | No — in sync-manifest `ignore` |
| Task data (what /work tracks) | `.claude/tasks/*.json` | No — in sync-manifest `ignore` |
| Operational documents (invitation letters, consent forms, facilitation guides, reports — anything the user works with daily) | Project root `docs/` (or user-chosen folder structure) | Outside `.claude/` entirely |
| Project-level settings (hooks, env vars, theme, additional permissions) | `.claude/settings.local.json` | No — in sync-manifest `ignore` |

## Cross-references

- **Boundary protocol:** `.claude/rules/agents.md § "Cross-Project Capture Protocol"` — what Claude should do BEFORE recommending a sync if the project has local additions to template-owned files.
- **Archive locations:** `.claude/rules/archiving.md` — where resolved work goes (decisions to `.archive/`, feedback to `archive.md`, etc.).
- **Workspace conventions:** `.claude/rules/archiving.md § "User-Facing Documents"` — how `docs/` vs `.claude/support/workspace/` differ.
- **Sync category source of truth:** `.claude/sync-manifest.json` — the file-level enumeration of `sync` / `customize` / `ignore` categories.
- **Settings layering:** `.claude/CLAUDE.md § "Critical Invariants"` — `.claude/settings.json` is template-owned (base `permissions.allow` + base `permissions.ask` per DEC-016); user additions go in `.claude/settings.local.json`.

## Examples — right vs wrong placement

**Adding a project-specific naming convention rule:**
- ✅ Append to `./CLAUDE.md` (project root) under a heading.
- ✅ Create `.claude/rules/project-naming-conventions.md` and `@`-import it from `./CLAUDE.md`.
- ❌ Add a section to `.claude/CLAUDE.md` (template-owned).
- ❌ Add a section to `.claude/rules/task-management.md` (template-owned).

**Adding a project-specific audit lens:**
- ✅ Create `.claude/commands/audit-{domain}.md` with the lens definition.
- ✅ Add it to `applies_when` so `/health-check` Part 8 discovers it automatically.
- ❌ Modify `.claude/commands/audit-coherence.md` (template-owned).

**Adding a domain glossary:**
- ✅ Create `.claude/support/reference/project-glossary.md`.
- ❌ Modify `.claude/support/reference/shared-definitions.md` (template-owned).

**Capturing an idea for later triage:**
- ✅ Run `/feedback "..."` (writes to `.claude/support/feedback/feedback.md`).
- ✅ Append manually to `.claude/support/feedback/feedback.md` if `/feedback` isn't appropriate.
- ❌ Drop it into `.claude/CLAUDE.md` or a rule file ("I'll deal with this later").

**Project-specific dev-server-block hook:**
- ✅ Add to `.claude/settings.local.json` (per `setup-checklist.md § "Optional Hooks"`).
- ❌ Add to `.claude/settings.json` (template-owned base; user additions belong in `settings.local.json`).

## When a project addition is generally-useful

If a project-specific addition turns out to apply to other projects too (clarifies a rule, fixes a documentation gap, formalizes a pattern that's not domain-specific), consider promoting it to the template via the cross-project capture pattern:

1. Capture as feedback in the template repo (`claude_code_environment/.claude/support/feedback/feedback.md`).
2. Template-side `/feedback review` triages.
3. Promotion: edit the template file, bump `template_version`.
4. Downstream projects pick up via `/health-check` Part 5 sync on next run.

See `.claude/rules/agents.md § "Cross-Project Capture Protocol"` for the boundary check that should run before recommending this flow.
