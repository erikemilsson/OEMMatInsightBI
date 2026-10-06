# Decision Rules

Major decisions are documented in `.claude/support/decisions/`.

## When to Create a Decision Record

When facing significant choices that block downstream work, create a decision record rather than deciding inline. When encountering any ambiguity or choice point, surface it to the user — never resolve silently.

## Decision Types

- **Pick-and-go** — after resolution, dependent tasks simply unblock (default)
- **Inflection point** — the outcome changes *what* gets built. After resolution, `/work` pauses and suggests `/iterate` to revisit the spec

## Agent-Recorded Decisions

A non-trivial choice an agent makes while implementing is held on the task until verification passes, then written as one `recorded` record per task. `recorded` never blocks a task or phase gate; the user ratifies it with `/work ratify` (or reopens it with `/work reconsider DEC-NNN`).

## Where Things Live

- Records: `.claude/support/decisions/decision-*.md`
- Research archives: `.claude/support/decisions/.archive/`
- Dashboard tracks all decisions with status, pending items, and timeline

## References

- Decision format and process: `.claude/support/reference/decisions.md`
- Extension patterns: `.claude/support/reference/extension-patterns.md` § "Decisions"
