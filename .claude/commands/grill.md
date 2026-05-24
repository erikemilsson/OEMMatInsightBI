# Grill Command

Interview-style interrogation. The model asks questions one at a time, walks branch-by-branch through a decision tree, resolves dependencies, and recommends an answer to each. When invoked without arguments, the model first triages — surfacing 2-4 candidate areas and recommending a starter — then drills the picked area.

Auto-detects `./CONTEXT.md` (project-owned domain glossary, if present) and runs the with-docs flow: challenges fuzzy language against the glossary, cross-references with code, updates `./CONTEXT.md` inline as terms resolve, and offers to route precedent-setting decisions through `/research`.

Adapted from `mattpocock/skills/engineering/grill-with-docs` — preserved the interrogation discipline + CONTEXT.md format; integrated with CCE's `/iterate` + `/research` routing and the DEC-016 spec/decision/vision guardrail.

## Usage

```
/grill                       # Triage: surface 2-4 candidate areas, recommend one, then drill the picked area
/grill {topic-or-question}   # Grill specifically on this topic
/grill {vision-file}         # Grill the contents of a vision doc (pre-distill enrichment)
```

## When to Use

- You have a plan or design that needs stress-testing before committing.
- You want help making implicit assumptions explicit.
- You're about to run `/iterate distill` on a vision doc and want to enrich it first.
- You want to harden domain vocabulary before the spec phase, or repair it mid-project when fuzzy language has crept in.
- Project-state triage in an unfamiliar or broad-scope context — surface where interrogation would help most before committing to a topic. (No-args invocation does this.)

## Process

This command has two invocation shapes. The no-args triage flow surfaces candidates and recommends a starter; the explicit-topic flow drills the named topic directly. Both ultimately drill a topic; the only difference is whether triage picks it or you bring it.

### Explicit-topic flow (`/grill {topic}` or `/grill {vision-file}`)

Interview relentlessly about every aspect until reaching a shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one-by-one. For each question, provide a recommended answer.

**Ask questions one at a time.** Wait for the answer before moving on. If a question can be resolved by reading the codebase or other project state (`.claude/spec_v*.md`, decisions, vision docs), explore those instead of asking.

### No-args triage flow (`/grill`)

1. **Scan project state.** Default scope: spec + decisions + recent FB items + (if present) `./CONTEXT.md`. Widen to code if those don't surface enough. Use judgment for what's worth grilling within scope — no prescribed criteria.

2. **Surface 2-4 candidates via AskUserQuestion.** Each option:
   - **Label:** short area name; append "(Recommended)" to the suggested starter (first in list, per AskUserQuestion convention).
   - **Description:** one-line rationale — what makes this area worth grilling now.

   User picks via UI or types "Other" with a custom topic.

3. **Handoff.** Acknowledge the pick, name the area, then begin drilling per the explicit-topic flow.

**Edges:**

- **Zero good candidates.** *"The project looks well-defined to me — nothing flagged. Pick a topic explicitly with `/grill {topic}` if you want a deeper look anywhere specific."*
- **Multiple in sequence.** If the user wants to drill another after the first one completes, the model can reference the original triage list (*"I had also flagged X and Y — pick one or name a different area"*).

### Auto-detected modes

**Plain grill** — `./CONTEXT.md` absent. Straight interview, no glossary integration.

**Grill with docs** — `./CONTEXT.md` present. Runs the additional behaviors below.

### Behaviors when `./CONTEXT.md` exists

**Challenge against the glossary.** When the user uses a term that conflicts with the definition in `./CONTEXT.md`, call it out immediately: *"Your glossary defines 'cancellation' as X, but you seem to mean Y — which is it?"*

**Sharpen fuzzy language.** When the user uses vague or overloaded terms, propose a precise canonical term: *"You're saying 'account' — do you mean the Customer or the User? Those are different things."*

**Discuss concrete scenarios.** Stress-test domain relationships with specific scenarios. Probe edge cases. Force precision about boundaries between concepts.

**Cross-reference with code.** When the user states how something works, check whether the code agrees. If a contradiction exists, surface it: *"The code cancels entire Orders, but you just said partial cancellation is possible — which is right?"*

**Update `./CONTEXT.md` inline.** When a term resolves, update the file immediately — don't batch. Use the format below.

**Offer decision records sparingly.** Only suggest creating a decision record via `/research` when **all three** are true:

1. **Hard to reverse** — the cost of changing your mind later is meaningful.
2. **Surprising without context** — a future reader will wonder "why did they do it this way?"
3. **The result of a real trade-off** — there were genuine alternatives and you picked one for specific reasons.

If any of the three is missing, skip the suggestion. When all three hold, route to `/research` (CCE's decision records go through research-agent → option matrix → user selection — see `.claude/rules/decisions.md`). `/grill` does **not** write to `.claude/support/decisions/` directly.

## `./CONTEXT.md` format

`./CONTEXT.md` is a project-owned, lazily-created glossary at the project root. **The template never ships a placeholder** — `/grill` creates it the first time a term resolves. Project decides whether to track in git (default: yes; not in template `.gitignore`).

**Structure:**

```markdown
# {Project / Context Name}

{One or two sentences: what this context is and why it exists.}

## Language

**Order**:
A customer's request to purchase one or more items.
_Avoid_: Purchase, transaction

**Invoice**:
A request for payment sent to a customer after delivery.
_Avoid_: Bill, payment request

**Customer**:
A person or organization that places orders.
_Avoid_: Client, buyer, account

## Relationships

- An **Order** produces one or more **Invoices**
- An **Invoice** belongs to exactly one **Customer**

## Example dialogue

> **Dev:** "When a **Customer** places an **Order**, do we create the **Invoice** immediately?"
> **Domain expert:** "No — an **Invoice** is only generated once a **Fulfillment** is confirmed."

## Flagged ambiguities

- "account" was used to mean both **Customer** and **User** — resolved: these are distinct concepts.
```

**Rules:**

- Be opinionated. When multiple words exist for the same concept, pick the best one and list the others as `_Avoid_` aliases.
- Flag conflicts explicitly in "Flagged ambiguities" with a clear resolution.
- One sentence per definition max. Define what it IS, not what it does.
- Show relationships. Use bold term names; express cardinality where obvious.
- **Only include terms specific to this project's context.** General programming concepts (timeouts, error types, utility patterns) don't belong even if used extensively. Before adding a term, ask: is this unique to this context, or a general programming concept? Only the former belongs.
- Group terms under subheadings when natural clusters emerge.
- Write an example dialogue showing the terms in use precisely.

## Out of scope

- **`/grill` does not write to `.claude/spec_v*.md`, `.claude/support/decisions/decision-*.md`, or `.claude/vision/**/*.md` directly.** The DEC-016 guardrail applies — substantive text changes to those files route through `/iterate`, `/research`, or user-paste-from-outside. `/grill` may *suggest* those routes when the conversation calls for them.
- **`/grill` does not batch-extract terms from existing spec or code.** Per Pocock's deprecation lesson (`/ubiquitous-language` was deprecated for exactly this reason): pre-populated glossaries don't get maintained, organically-grown ones do. `/grill` populates `./CONTEXT.md` as terms resolve during conversation, never via batch scan.
- **Multi-context monorepos (`CONTEXT-MAP.md`)** are deferred. CCE's single-spec model assumes one domain per project; revisit if a real multi-context project emerges.

## Layer distinction

| `./CONTEXT.md` (project) | `.claude/support/reference/shared-definitions.md` (template) |
|---|---|
| Project domain vocabulary (Customer, Order, Invoice — or your equivalent) | Environment/workflow vocabulary (Pending status, difficulty 1-10, owner enums) |
| Created lazily by `/grill` when first term resolves | Ships with the template |
| Project-owned | Template-owned |

They coexist. Don't collapse them.

## Where it fits in the pipeline

- **Before `/iterate distill`** — grill a vision doc to surface and resolve ambiguity, then distill the enriched doc into a spec.
- **Before `/research`** — grill the design until you know which decision needs formal investigation, then route through `/research`.
- **Mid-project** — when fuzzy language is creeping into the spec or code, run `/grill` to sharpen vocabulary and update `./CONTEXT.md`.

## References

- Original pattern: `mattpocock/skills/engineering/grill-with-docs/SKILL.md`
- Spec workflow: `.claude/rules/spec-workflow.md` § Vision Documents (pre-distill placement)
- Decision flow: `.claude/rules/decisions.md` (when to route through `/research`)
- Agent rule: `.claude/rules/agents.md` § Domain Glossary Awareness (how implement-agent and verify-agent consume `./CONTEXT.md`)
- Audit lens: `.claude/commands/audit-coherence.md` § "Lens 2 — vocab-drift" (consumes `./CONTEXT.md` as canonical naming reference when present)
