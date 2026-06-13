# Project Extension Hooks

A canonical map of **where project-specific content goes** when extending the template environment. The template ships a shared core; projects add domain-specific rules, reference docs, decisions, commands, and operational documents — but where those additions land matters for both `/health-check` Part 5 sync hygiene and the cross-project capture protocol (§ "Cross-Project Capture Protocol" below).

The rule: **never modify template-owned files** (`.claude/CLAUDE.md`, `.claude/rules/*.md` template-shipped names, `.claude/support/reference/*.md` template-shipped names, `.claude/agents/*.md`, `.claude/commands/*.md` template-shipped names). Project additions go to one of the project-owned locations below.

## Extension need → canonical home

| Extension need | Canonical home | Synced? |
|---|---|---|
| Project-specific instructions / context for Claude | `./CLAUDE.md` (project root) | No — user-owned |
| Rule imports (load additional rule files) | `./CLAUDE.md` (project root) | No — user-owned |
| Project-specific rule files | `.claude/rules/project-*.md` (e.g., `project-domain-vocabulary.md`) | No — `project-*.md` is in sync-manifest `ignore` |
| Project-specific reference docs (extracted from CLAUDE.md or new) | `.claude/support/reference/project-*.md` | No — `project-*.md` is in sync-manifest `ignore` |
| Project-specific slash commands (audit family or custom) | `.claude/commands/audit-{name}.md` or other non-template name | Custom names not in sync-manifest `sync` are untouched by sync |
| Project-specific skills | `.claude/skills/{name}/SKILL.md` (the template ships no skills — any skill dir here is project-owned) | Custom skill dirs untouched by sync |
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

- **Boundary protocol:** § "Cross-Project Capture Protocol" (below in this document) — what Claude should do BEFORE recommending a sync if the project has local additions to template-owned files.
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

See § "Cross-Project Capture Protocol" below for the boundary check that should run before recommending this flow.

## Cross-Project Capture Protocol

When a session is about to recommend the **template→sync flow** — typically after surfacing a generally-useful rule, command, agent, skill, or reference doc in the current project that could ship to the template — run a boundary check FIRST. The template→sync flow can silently lose local additions to template-owned files if those additions weren't reconciled before the sync.

**Template-owned file globs** (sync-manifest `sync` category — projects should NOT modify these directly):

- `.claude/CLAUDE.md`
- `.claude/rules/*.md` (template-shipped names — not `project-*.md` which is project-owned)
- `.claude/support/reference/*.md` (template-shipped names — not `project-*.md`)
- `.claude/agents/*.md`
- `.claude/commands/*.md` (template-shipped names — project commands like `audit-{name}.md` are project-owned)

Before recommending the sync, enumerate the project's local additions to any of the above (diff against last-synced template state, OR explicitly walk each known-template-owned file looking for project-specific content).

**Routing the findings:**

- **Generically-applicable additions** (rule clarifications, agent guidance, command refinements that any project could benefit from) → recommend **project→template promotion first** (FB-002/FB-003-style: capture as feedback in the template repo, ship via `/feedback review`, then sync). The promoted content lands in the template; the subsequent sync becomes a no-op convergence rather than a conflict.
- **Project-specific additions** (domain-specific rules, vocabulary, behaviors that don't generalize) → recommend **migration to a project-owned location first** — per the canonical map at the top of this document (rule imports → root `./CLAUDE.md`; project rules → `.claude/rules/project-*.md` gitignored; etc.).

Either way, surface the boundary check at suggestion time, not at sync time. Catching the violation at sync exit (after the user has already integrated local additions into a template-owned file) means manual reconciliation is the only path forward. Catching it upstream means clean ship paths.

**Why behavioral, not permission-layer:** the sync layer can structurally detect "local additions to template-owned file" at sync time (FB-059 / FB-060 structural fix, not yet shipped — see `template-maintenance/feedback.md` § FB-059 + FB-060). This rule reduces the *frequency* of the violation by preventing the upstream condition. Both layers compound.

*(Moved from `.claude/rules/agents.md` in v4.16.0; the rules file keeps a trigger stub under the same section name.)*
