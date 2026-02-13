# Learnings

Project-specific patterns, strategies, and insights accumulated over time.

## Purpose

This folder stores learnings that help Claude work more effectively on your specific project. Unlike core reference docs, these are discovered through experience rather than defined upfront.

**The implement-agent checks this directory during Step 4 (Implement).** If learnings files exist, they're consulted for relevant patterns before implementation begins. You can also reference them explicitly:
- "Check learnings for patterns on X"
- "Look at the API patterns before implementing"
- "What strategies have worked for task breakdown?"

## Usage

Add files as you discover useful patterns. Common categories:

| Category | What to capture |
|----------|-----------------|
| `task-strategies.md` | Effective task decomposition approaches, sequencing patterns |
| `api-patterns.md` | API design conventions, error handling patterns |
| `testing-patterns.md` | Test strategies, mock patterns, coverage approaches |
| `architecture-notes.md` | Structural decisions, module boundaries |
| `gotchas.md` | Non-obvious issues, edge cases, things that broke |

## Format

Keep entries concise and actionable:

```markdown
## [Pattern Name]

**Context:** When this applies
**Pattern:** What to do
**Example:** Brief code/command example (optional)
**Why:** Reasoning (optional)
```

## Guidelines

- **Be specific** - "Use retry with exponential backoff for external APIs" beats "handle errors well"
- **Include context** - When does this pattern apply? What triggers it?
- **Update over time** - Remove outdated learnings, refine patterns that evolve
- **Project-specific** - These aren't synced from template; each project accumulates its own

## Maintenance

**When to review:** At phase completions, or quarterly.

**What to check:**
- Remove learnings now captured in the spec (they've graduated)
- Remove learnings that no longer apply (project changed)
- Consolidate duplicate or overlapping entries
- Update examples if APIs or patterns have evolved

**Tracking staleness:** Add a date header to each learning entry:
```markdown
## [Pattern Name]
*Added: 2026-01-15*

**Context:** When this applies
...
```

Learnings without dates or older than 6 months should be reviewed for relevance.
