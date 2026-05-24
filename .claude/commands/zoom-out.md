---
disable-model-invocation: true
---

# Zoom Out

Go up a layer of abstraction. Surface a map of the area's relevant components and their connections, using the project's domain glossary vocabulary (`./CONTEXT.md` when present, otherwise domain-relevant naming inferred from spec + code).

## Usage

```
/zoom-out                       # Map the current focus area (the model picks from conversation context)
/zoom-out {area-name}           # Map a specific area
```

## When to Use

When you say "I don't know this area well" — the model should produce a high-level map rather than diving into a single component.

Adapted from `mattpocock/skills/engineering/zoom-out` (Pocock's 7-line skill). CCE adaptation: domain-genericized (works for software, research, procurement, renovation — any spec-driven project, per CCE's domain-agnostic design), and consumes `./CONTEXT.md` vocabulary when present (FB-068 integration).

## Process

1. **Identify the area.** From the user's question or the conversation focus, name the area — a module, a phase, a process, a vendor relationship; whichever fits the project domain.
2. **Produce a map.** List the relevant components and how they connect:
   - Software projects: modules, primary callers/callees, key types or contracts.
   - Research projects: stages, sources, key terms.
   - Procurement / renovation: vendors, phases, dependencies between deliverables.
3. **Use canonical vocabulary.** If `./CONTEXT.md` exists, prefer its canonical term names (avoid `_Avoid_` aliases). If absent, use domain-relevant naming inferred from spec + code.
4. **Keep it tight.** Map, not deep-dive. Bullet list or simple diagram, not a paragraph per component.

## Out of scope

- Detailed implementation walkthrough — `/work` or `/review` territory.
- Vocabulary cleanup — `/grill` and `/audit-coherence`'s `vocab-drift` lens.
- Architectural changes — `/research` (decision record) or `/iterate` (spec change).

## Frontmatter rationale

`/zoom-out` carries `disable-model-invocation: true` (per FB-071 convention; see `.claude/rules/agents.md § "Command Invocation Gates"`). Rationale: `/zoom-out` is specifically a user-asks-for-help signal — the model autonomously invoking it would be circular (the model would be invoking it for its own benefit, which doesn't match the help-the-user trigger). Pocock's `/zoom-out` carries the same frontmatter for the same reason.

## References

- Original pattern: `mattpocock/skills/engineering/zoom-out/SKILL.md`
- Glossary consumption: `.claude/commands/grill.md` + `.claude/rules/agents.md § "Domain Glossary Awareness"`
- Frontmatter convention: `.claude/rules/agents.md § "Command Invocation Gates"`
