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

**Start new feature visions from the scaffold** `_feature-vision-template.md` (copy it to `<feature-slug>.md`). `_`-prefixed files are scaffolds, not visions — consumers (`/iterate distill`, etc.) skip them.

## Relationship to Specs — vision as a development hub (DEC-023)

A vision is the **development hub for a larger feature**, not a one-time pre-spec brainstorm. Start from the scaffold `_feature-vision-template.md`. Develop the feature broadly in the vision — repeated `/grill` (sharpen meaning) and `/shakedown` (capture edge-cases / world-knowledge) passes fold findings *into* the structured vision — until a section is tight, then graduate it to the spec.

**Lifecycle (per section, tracked by the maturity banner):**
1. 🟡 DRAFTED — sketched in the vision.
2. 🔵 RESEARCHED — grilled / shaken-down, scope settled, evidence cited; not yet specced.
3. 🟢 SHIPPED — graduated to the spec via `/iterate distill` (initial spec) or `/iterate` (amend an existing spec), then built.

**Editability (DEC-023, amending DEC-016):** a vision is **editable in-place while developing** (🟡/🔵) — co-refinement is the whole point. Once a section graduates (🟢) it is **frozen**: the spec is the source of truth for it, and further changes route through `/iterate`, not vision edits. Specs link their source vision in frontmatter (`vision_source: vision/<slug>.md`).

**During implementation, Claude works off the spec, not the vision** — don't pull features from the vision that aren't in the spec. The vision is where you *develop* what will become spec; the spec is what gets *built*.

Vision docs remain useful for:
- Future phase planning (what was deferred)
- Understanding original intent if spec wording is ambiguous
- Re-running `/iterate distill` when planning a v2 spec

## Tips

- Don't try to make vision docs "spec-ready" - that's what distillation is for
- It's OK if vision docs have unbuildable ideas - they capture intent
- Keep the vision doc when the spec evolves; it's historical context
