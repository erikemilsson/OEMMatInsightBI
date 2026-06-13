# Shakedown Command

Acceptance-by-example. Work *backward from the built (or envisioned) product*: throw the full range of real use at it — typical paths and edge cases — one example at a time, ground each against what the system *actually* does, and map where it delivers vs. falls short. The output is a dated, snapshot-anchored corpus that is simultaneously a **gap analysis** (what's missing), a set of **acceptance probes** (what works), and a **forward-direction map** (where it should go).

`/shakedown` is the mirror of `/grill`: grill drills *down* to sharpen what you *mean*; shakedown sweeps *across* to test how the system *behaves* against how you pictured it. Where grill asks you questions, shakedown has you assert examples and adjudicates each against the system.

Domain-agnostic — software, research, procurement, renovation, any spec-driven build. The *lens* it judges against is derived per-project at Phase 0; nothing here is baked to a domain.

## Usage

```
/shakedown {what you want to test}   # state the purpose, then calibrate the lens, then run examples
/shakedown                            # no-args: establish the purpose first, then calibrate + run
```

A shakedown is a multi-turn, often multi-session activity. The corpus doc (below) is the persistence layer — it survives `/clear` and compaction, so a shakedown can span sessions.

## When to Use

- You have a built or partially-built system and want to find where it falls short of how real use will actually look — before committing more build.
- A large, long-running project has drifted into "just building" and you want to re-anchor to where it's going.
- You want a gap analysis grounded in concrete examples, not abstract review.
- You're scoping the next phase and want the boundary of what the current system can/can't express, mapped empirically.

Not for: sharpening fuzzy *vocabulary* (that's `/grill`); diagnosing a *specific bug* (that's `/diagnose`); reviewing *code quality* (that's `/review`).

## Process

The shakedown runs in two parts: **Phase 0** calibrates the lens (a directed grill — required), then the **probe loop** runs examples against it. Everything below is a standing pattern — it describes how a shakedown behaves on every invocation, not a one-time checklist.

### Phase 0 — Calibrate the lens (directed grill, REQUIRED)

Before any example, run a *directed grill* — the interrogation discipline of `/grill` (`commands/grill.md § Process`: one question at a time, recommend an answer to each, resolve dependencies, ground in the code rather than asking what you can read) — scoped to establishing **the lens**:

1. **What is this session testing for?** Pin the purpose (e.g. "can the rule engine express my real personal-style rules?"). The purpose scopes everything downstream.
2. **Which parts of the system are relevant to that?** Read the spec + the relevant code/artifacts; confirm you're looking at the parts that *matter* for the purpose — not just the parts that are easy to read. This is the step that prevents a thin or misdirected lens.
3. **Derive and state the lens back, for confirmation, before any example:**
   - the **dimensions** each example will be decomposed against — read them off the system's *actual* structure (e.g. styler's `mechanism / bite / direction / when / unless`, each mapped to a real engine field);
   - the **verdict legend** (base set below, plus any project-specific verdicts);
   - the **cleave / heuristic** the verdicts turn on (e.g. styler's "cheap *bite-modifier* vs deep *matching-shape*");
   - **what would trip a "new dimension"** finding (the edge-watch list).

Do **not** silently self-calibrate and start probing. A thin lens — one that checks the salient parts but misses the important ones — only reveals itself after sunk examples; the directed grill front-loads that correction. (A prior standalone `/grill` of the system is optional enrichment, never a substitute for Phase 0.)

When the lens is confirmed, open the corpus doc (below) and begin the loop.

### The probe loop (per example)

For each example the user brain-dumps, produce — and **write into the corpus doc immediately** (the doc, not the conversation, is the record):

1. **Plain restatement.** If it forks into two or more distinct items, flag it (`❓`) and split rather than blur.
2. **Breakdown** against the calibrated dimensions.
3. **Grounding against the actual system** — the non-negotiable that separates signal from noise. Don't say "this seems hard"; say *why*, precisely, against the real structure: *"`matchesMechanism` is a predicate over one item; this is a binary relation over two, so the mechanism can't express it."* Distinguish **expressible** / **expressible-but-flattening** (an approximation exists but loses intent) / **not-expressible** (no approximation).
4. **Verdict** from the legend.

### Maintaining the model (between examples)

The lens is **adaptive**. As findings accumulate, refine the corpus's shared sections — *Model so far*, *Parked* (dimensions seen but deferred), *Boundary criteria* (the in/out line this shakedown is drawing). New dimensions get appended; boundaries get drawn and re-drawn. This is what makes a shakedown a model-building exercise, not a checklist.

### Steering (proactive)

Don't passively intake. Track what's been tested and **request the highest-signal next input** — the example most likely to reveal a new dimension or break the model: *"Throw me a rule that relates two items — I suspect that's where the mechanism breaks."* Hypothesis-driven probing finds the boundary faster than random examples.

### Stop signal

Stop at **saturation, not exhaustion** — when new examples stop revealing new dimensions. Announce when you're close (*"the last three revealed nothing new; one or two more and the model's stable"*) so the user can decide to wrap.

### Routing onward (suggested, not automatic)

As verdicts accrue (and at the end), name the exit per verdict — but **propose, don't execute**. The user fires the command; `/shakedown` never writes spec/decision/vision text itself (DEC-016):

- **⚠ needs new capability** → `/iterate` (if spec-expressible) or `/research` (if it's a genuine design fork).
- **✗ out of scope** → an out-of-scope note, or a setting/toggle if it's a correctness-layer concern rather than the feature under test.
- **✓ expressible** → optionally seed a `test_protocol` acceptance step so the confirmed behaviour can't regress.
- **Parked** → the forward-direction backlog the next shakedown or `/iterate` consumes.

## Verdict legend

Base set (extend per project — styler added `🎨` for dose/nuance):

- **✓** — expressible by the system as-is.
- **⚠** — needs a new capability / dimension the system doesn't have (a gap to build).
- **✗** — out of scope for this system (belongs elsewhere — a setting, a different layer, or genuinely not this product's job).
- **❓** — ambiguous, or forks into multiple items; resolve or split before verdicting.

## The shakedown corpus

Lives at `.claude/support/shakedowns/{slug}-{YYYY-MM-DD}.md` — one dated doc per shakedown (the date anchors the map to a system snapshot). See `.claude/support/shakedowns/README.md` for the convention.

Structure: the confirmed **lens** (dimensions + legend + cleave) at the top; the living **Model so far / Parked / Boundary criteria** sections; then the per-example entries. The doc is the persistence layer — it survives `/clear` and compaction, which is what lets a shakedown span sessions. On resume, re-read the doc to recover the lens and model, then continue the loop.

## Out of scope

- **Does not invent examples.** The user brings the real / edge-case examples; `/shakedown` adjudicates them. (Mirrors `/grill`, which doesn't invent your domain for you.)
- **Does not write spec, decision, or vision files** (DEC-016). It proposes routes (`/iterate`, `/research`); the user drives those.
- **Not a bug hunt** (`/diagnose`), **not vocabulary-sharpening** (`/grill`), **not code review** (`/review`). It maps the *capability boundary* of a system against real use.

## Relationship to `/grill`

Inverses that compose:

| | `/grill` | `/shakedown` |
|---|---|---|
| Flow | Claude asks → you answer | you assert → Claude verdicts |
| Goal | sharpen what you *mean* | map what the system *can do* against real use |
| Emphasis | depth (drill one thing) | breadth (sweep many examples) |

`/shakedown`'s Phase 0 *uses* grill's interrogation discipline to build the lens — so a shakedown *contains* a directed grill, but is not a *mode* of grill: the probe loop is the distinct activity, and it owns a durable corpus grill never produces.

## References

- `.claude/commands/grill.md` — the interrogation discipline Phase 0 draws on; the inverse-flow sibling.
- `.claude/support/shakedowns/README.md` — corpus convention + doc structure.
- `.claude/rules/spec-workflow.md` — where the shakedown fits (working backward from the built product; ⚠ findings route to `/iterate`).
- `.claude/commands/diagnose.md`, `.claude/commands/review.md` — adjacent capabilities (bug methodology; code-quality review).
- `decisions/decision-019-shakedown-command.md` — the decision record establishing this command.
