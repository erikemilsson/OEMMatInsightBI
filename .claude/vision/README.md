# Vision Documents

Long-lived documents capturing project intent, design philosophy, and future direction.

## What Goes Here

- **Vision documents** - High-level product thinking from ideation sessions
- **Design philosophy** - Core principles and constraints
- **Future roadmap** - Features and ideas beyond current phase
- **Technical abstractions** - Conceptual models that inform architecture

## What Does NOT Go Here

- Buildable specifications (those go to `.claude/spec_v{N}.md`)
- Implementation research (that goes to `.claude/support/decisions/.archive/`)
- Temporary notes (those go to `.claude/support/workspace/`)

## Naming Convention

```
{purpose}.md
```

Examples:
- `product-vision.md` - Core product vision
- `api-philosophy.md` - Design principles for the API
- `future-features.md` - Ideas beyond v1

## Relationship to Specs

Vision documents are inputs to specs, not replacements. The workflow:

1. Capture vision (ideation, brainstorming, philosophy)
2. Save to `.claude/vision/`
3. Run `/iterate distill`
4. Extract buildable Phase 1 spec from vision
5. Vision doc remains as reference; spec references it in frontmatter

Specs link to their source vision:
```yaml
---
vision_source: vision/product-vision.md
---
```

**Once a spec exists, the spec is the single source of truth.**

Vision docs become historical context only. Claude should NOT:
- Consult vision docs during implementation (only spec matters)
- Add features from vision that aren't in the spec
- Treat vision as authoritative once a spec exists

Vision docs remain useful for:
- Future phase planning (what was deferred)
- Understanding original intent if spec wording is ambiguous
- Re-running `/iterate distill` when planning a v2 spec

## Tips

- Don't try to make vision docs "spec-ready" - that's what distillation is for
- It's OK if vision docs have unbuildable ideas - they capture intent
- Keep the vision doc when the spec evolves; it's historical context
