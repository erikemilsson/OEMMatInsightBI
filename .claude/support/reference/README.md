# Reference Files

Documentation that commands and agents read during workflow execution. Files are organized into complementary pairs and standalone references — understanding the division of responsibility prevents duplication and makes lookups faster.

## How These Files Work Together

The reference files form a layered system. Commands (`work.md`, `health-check.md`, etc.) contain the procedural logic — the steps to follow. Reference files contain the definitions, schemas, and algorithms that commands delegate to rather than inline.

**Key relationships:**

- **`shared-definitions.md` + `task-schema.md`** — Split by concern. Shared definitions owns the *rules and vocabulary*: difficulty scale, status meanings, mandatory behavioral rules, glossary of all terms. Task schema owns the *data structure*: JSON field definitions, validation rules, owner/priority values, verification fields, status flow diagram. Commands reference shared-definitions for "what does this mean?" and task-schema for "what's the correct JSON?"
- **`workflow.md` + command files** — Workflow is the narrative overview of the full Spec→Execute→Verify process. Commands contain the procedural implementation. Workflow answers "how does the system work?" while commands answer "what do I do right now?"
- **`dashboard-regeneration.md`, `drift-reconciliation.md`, `parallel-execution.md`, `session-recovery.md`, `phase-decision-gates.md`, `decomposition.md`** — Extracted algorithms that `work.md` delegates to rather than inlining. `work.md` uses "Full procedure:", "Full algorithm:", or "Follow ..." references to point into these files. This keeps `work.md` focused on orchestration while the detailed algorithms live in dedicated files.

## Core (read by commands/agents during execution)

| File | Purpose | Primary consumers |
|------|---------|-------------------|
| `shared-definitions.md` | Difficulty scale, status values, mandatory rules, vocabulary, glossary | `work.md` (difficulty scale), `health-check.md` (difficulty validation), `CLAUDE.md` (always in context) |
| `task-schema.md` | JSON field definitions, owner/priority values, verification fields, status flow, archiving | `health-check.md` (schema validation), `CLAUDE.md` (always in context) |
| `workflow.md` | Spec→Execute→Verify process, phase transitions, verification tiers, system overview | `work.md`, `health-check.md`, `CLAUDE.md` (always in context) |
| `paths.md` | Canonical file locations — prevents Claude from inventing paths | `CLAUDE.md` (always in context) |
| `dashboard-regeneration.md` | Dashboard regeneration procedure, section format, critical path, overview diagram | `work.md`, `breakdown.md`, both agents |
| `drift-reconciliation.md` | Spec drift detection, reconciliation UI, drift budget, task migration | `work.md` (pre-execution check), `iterate.md` |
| `parallel-execution.md` | Parallelism eligibility, file conflict algorithm, parallel dispatch | `work.md` (task routing) |
| `session-recovery.md` | Session sentinel, crash recovery scan, stuck task detection | `work.md` (Step 0) |
| `phase-decision-gates.md` | Phase boundary checks, decision dependencies, late decision cross-refs | `work.md` (Step 2b) |
| `decomposition.md` | Spec-to-task breakdown, task creation guidelines, stage organization | `work.md` (Step 4 decomposition) |

## Guides (read on-demand for specific situations)

| File | Purpose |
|------|---------|
| `decisions.md` | Decision record template, lifecycle, choice classification (spec vs implementation). Research-agent reads this for the template when creating/populating records. |
| `spec-checklist.md` | Spec readiness criteria, red flags, core questions |
| `extension-patterns.md` | Phases and decisions patterns for complex projects |
| `setup-checklist.md` | Template configuration checks (CLAUDE.md placeholders, version.json), run during decomposition |
| `desktop-project-prompt.md` | Instructions for Claude Desktop ideation sessions |

## Related READMEs (in sibling directories)

| File | Purpose |
|------|---------|
| `../learnings/README.md` | Categories, format, and maintenance guidelines for project-specific learnings |
| `../workspace/README.md` | Directory rules, file placement guide, and graduation process for temporary files |
