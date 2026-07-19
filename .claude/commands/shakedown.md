# Shakedown Command

**Acceptance-by-example — the channel for knowledge only you have.** A shakedown's value is the edge cases, real-world incidents, and hidden relationships/constraints that *you* know and the model structurally cannot see (out of training distribution, unique to your domain or experience). You assert these as concrete examples *with your reasoning*; the system grounds each against what it actually does (or what the spec says it will do), finds where it falls short, and captures your knowledge as a durable, snapshot-anchored corpus — simultaneously a **gap analysis** (what's missing), **acceptance probes** (what works), and a **forward-direction map** (where it should go).

The auto-verdict on clear cases (below) exists to **clear the deck** so the dialogue concentrates on the examples where your knowledge is load-bearing — not to race through inputs on thin information.

`/shakedown` is the mirror of `/grill`: grill drills *down* to sharpen what you *mean* (you have the meaning, it's just fuzzy); shakedown sweeps *across* to surface what you *know about reality* that the system doesn't account for. Grill asks you questions; shakedown has you assert examples and adjudicates each.

**Target-aware** (DEC-023): point it at a **vision** (probe a feature you're developing), the **spec** (probe committed scope, pre-build), or the **running build** (probe real behavior). *The target sets the altitude* — grounding shifts to match (against the spec's described model, or against actual code). Domain-agnostic — software, research, procurement, renovation, any spec-driven build; the *lens* is derived per-project at Phase 0, nothing here is baked to a domain.

## Usage

```
/shakedown {what you want to test}   # state the purpose, then calibrate the lens, then run examples
/shakedown                            # no-args: establish the purpose first, then calibrate + run
```

A shakedown is a multi-turn, often multi-session activity. The corpus doc (below) is the persistence layer — it survives `/clear` and compaction, so a shakedown can span sessions.

## When to Use

- **You have real-world knowledge the system doesn't encode** — edge cases you've hit, incidents you've seen, constraints unique to your domain — and you want to test whether the system (or the spec) accounts for them. *This is the core use: you are the source of information the model lacks.*
- You have a built or partially-built system and want to find where it falls short of how real use will actually look — before committing more build.
- **You're shaping a spec or a feature vision** and want to pressure-test it against concrete examples *before* building (spec/vision-target mode).
- A large, long-running project has drifted into "just building" and you want to re-anchor to where it's going.
- You want a gap analysis grounded in concrete examples, not abstract review; or to map the capability boundary empirically when scoping the next phase.

Not for: sharpening fuzzy *vocabulary* (that's `/grill`); diagnosing a *specific bug* (that's `/diagnose`); reviewing *code quality* (that's `/review`).

## Process

The shakedown runs in two parts: **Phase 0** calibrates the lens (a directed grill — required), then the **probe loop** runs examples against it. Everything below is a standing pattern — it describes how a shakedown behaves on every invocation, not a one-time checklist.

### Phase 0 — Calibrate the lens (directed grill, REQUIRED)

Before any example, run a *directed grill* — the interrogation discipline of `/grill` (`commands/grill.md § Process`: one question at a time, recommend an answer to each, resolve dependencies, ground in the system rather than asking what you can read) — scoped to establishing **the lens**. **Work general-first:** establish the purpose and the conceptual frame, confirm it, *then* descend into specifics — don't open by enumerating repo internals.

0. **Identify the target** (DEC-023). Are you probing a **vision** (a feature in development), the **spec** (committed scope, pre-build), or the **running build**? This sets where you *ground*: a vision/spec target grounds each example against *what the doc says the system will do* (✓ covered / ⚠ gap / ❓ ambiguous); a build target grounds against *what the code actually does*. Default: build if one exists for the purpose; else the spec/vision.
1. **What is this session testing for?** Pin the purpose at the conceptual level first (e.g. "can the rule engine express my real personal-style rules?"). The purpose scopes everything downstream.
2. **Which parts matter?** Read the relevant parts of the target — spec section(s) via the index (DEC-021) for a spec/vision target, or the relevant code for a build target. Confirm you're looking at the parts that *matter* for the purpose, not just the parts that are easy to read. This is the step that prevents a thin or misdirected lens — but state the conceptual model back before drilling into field-level detail.
3. **Derive and state the lens back, for confirmation, before any example:**
   - the **dimensions** each example will be decomposed against — read off the target's *actual* structure (the spec's described model, or the engine's real fields);
   - the **verdict legend** (base set below, plus any project-specific verdicts; for a spec/vision target the verdicts read against the doc);
   - the **cleave / heuristic** the verdicts turn on (e.g. a cheap *modifier* vs a deep *structural* change);
   - **what would trip a "new dimension"** finding (the edge-watch list).

Do **not** silently self-calibrate and start probing. A thin lens — one that checks the salient parts but misses the important ones — only reveals itself after sunk examples; the directed grill front-loads that correction. (A prior standalone `/grill` of the system is optional enrichment, never a substitute for Phase 0.)

When the lens is confirmed, open the corpus doc (below) and begin the loop.

### The probe loop (per example)

**Principle: Claude grounds and proposes; you adjudicate the judgment calls.** Clear ✓/✗ cases are auto-verdicted to keep the sweep moving; the cases where *your* knowledge is load-bearing — gaps, approximations that might flatten intent, ambiguity — stop and pull you in. That concentration is the point (see the lede).

For each example you brain-dump, produce — and **write into the corpus doc immediately** (the doc, not the conversation, is the record):

1. **Plain restatement.** If it forks into two or more distinct items, flag it (`❓`) and split rather than blur.
2. **Breakdown** against the calibrated dimensions.
3. **Ground it** — the non-negotiable that separates signal from noise. Don't say "this seems hard"; say *why*, precisely, against the target's real structure (the code for a build target; the spec's described model for a spec/vision target): *"`matchesMechanism` is a predicate over one item; this is a binary relation over two, so the mechanism can't express it."* Distinguish **expressible** / **expressible-but-flattening** (an approximation exists but loses intent) / **not-expressible**.
4. **Generalize** — name the *family* the example represents ("this is the class of rules relating two items"), so one example hardens a whole dimension, not just itself.
5. **Verdict.** For a clear **✓** (expressible) or **✗** (out of scope), verdict and move on. **Stop and involve the user when:**
   - **it flattens** (`expressible-but-flattening`) — the approximation is a *value* call only you can make: *"the spec can approximate this as X but loses Y — acceptable, or is Y essential?"*
   - **it's a gap** (`⚠`) — co-draft the spec/vision *delta* the example implies (a proposal, never written directly — DEC-016), and ask where it ranks against the gaps so far (priority feeds `/iterate`'s fold-order).
   - **it's ambiguous** (`❓`) — resolve or split *with* the user before verdicting.
   - otherwise, propose your read of the verdict and let the user override — their model stays authoritative.
6. **Capture.** Write the entry (breakdown + family + grounding + verdict + any drafted delta). For a confirmed ✓, seed an acceptance probe so it can't silently regress. Emit gaps/deltas to the merge queue per "Routing onward".

### Maintaining the model (between examples)

The lens is **adaptive**. As findings accumulate, refine the corpus's shared sections — *Model so far*, *Parked* (dimensions seen but deferred), *Boundary criteria* (the in/out line this shakedown is drawing). New dimensions get appended; boundaries get drawn and re-drawn. This is what makes a shakedown a model-building exercise, not a checklist.

### Steering (proactive)

Don't passively intake. Track what's been tested and **request the highest-signal next input** — the example most likely to reveal a new dimension or break the model: *"Throw me a rule that relates two items — I suspect that's where the mechanism breaks."* Beyond your own hypotheses, **ask for the cases the user is most worried the system won't handle** — their anxieties are high-signal and encode knowledge you can't derive. Hypothesis-driven probing (yours + theirs) finds the boundary faster than random examples.

### Stop signal

Stop at **saturation, not exhaustion** — when new examples stop revealing new dimensions. Announce when you're close (*"the last three revealed nothing new; one or two more and the model's stable"*) so the user can decide to wrap.

### Routing onward (suggested, not automatic)

As verdicts accrue (and at the end), name the exit per verdict — but **propose, don't execute**. The user fires the command; `/shakedown` never writes spec/decision/vision text itself (DEC-016):

- **⚠ needs new capability** → `/iterate` (if spec-expressible) or `/research` (if it's a genuine design fork).
- **✗ out of scope** → an out-of-scope note, or a setting/toggle if it's a correctness-layer concern rather than the feature under test.
- **✓ expressible** → optionally seed a `test_protocol` acceptance step so the confirmed behaviour can't regress.
- **Parked** → the forward-direction backlog the next shakedown or `/iterate` consumes.

**Emit to the merge queue (DEC-023).** Rather than relying on the user to remember these routes, persist them: for each `⚠` (gap) and any drafted spec/vision delta, append a `.claude/support/.spec-merge-queue.jsonl` entry (`source: shakedown`, `target: vision|spec` per what this shakedown is probing, `kind: gap|delta`, `origin_ref` = the corpus entry, plus `target_ref` / `summary`). `/iterate` (or your next vision session) then surfaces them on return — the corpus stays the full record; the queue is the *notification* that a finding hasn't been folded in yet. Exception: if you're developing a vision *in this same conversation*, fold straight into its Open-forks tracker (no queue entry). See `.claude/support/reference/merge-queue.md`.

## Verdict legend

Base set (extend per project — styler added `🎨` for dose/nuance). For a **build target** the verdict reads against actual behavior; for a **spec/vision target** it reads against what the doc specifies (a ⚠ against a spec *is* a spec delta):

- **✓** — expressible by the system as-is (build) / specified by the doc (spec/vision).
- **⚠** — needs a new capability the system doesn't have (build) / a gap the spec/vision doesn't cover, a delta to add (spec/vision).
- **✗** — out of scope for this system (belongs elsewhere — a setting, a different layer, or genuinely not this product's job).
- **❓** — ambiguous, or forks into multiple items (build) / the doc doesn't say (spec/vision ambiguity); resolve or split before verdicting.

## The shakedown corpus

Lives at `.claude/support/shakedowns/{slug}-{YYYY-MM-DD}.md` — one dated doc per shakedown (the date anchors the map to a system snapshot). See `.claude/support/shakedowns/README.md` for the convention.

Structure: the confirmed **lens** (dimensions + legend + cleave) at the top; the living **Model so far / Parked / Boundary criteria** sections; then the per-example entries. The doc is the persistence layer — it survives `/clear` and compaction, which is what lets a shakedown span sessions. On resume, re-read the doc to recover the lens and model, then continue the loop.

## Out of scope

- **Does not invent examples.** The user brings the real / edge-case examples; `/shakedown` adjudicates them. (Mirrors `/grill`, which doesn't invent your domain for you.) This is the corollary of the purpose: the value is *your* knowledge — Claude can't manufacture it.
- **Does not write spec, decision, or vision files** (DEC-016). It *drafts* deltas and proposes routes (`/iterate`, `/research`, the merge queue); the user drives those.
- **Not a bug hunt** (`/diagnose`), **not vocabulary-sharpening** (`/grill`), **not code review** (`/review`). It maps the *capability boundary* of a system against real use.

## Relationship to `/grill`

Inverses that compose:

| | `/grill` | `/shakedown` |
|---|---|---|
| Flow | Claude asks → you answer | you assert → Claude verdicts |
| Pulls from you | what you *mean* (fuzzy → precise) | what you *know about reality* the system lacks |
| Emphasis | depth (drill one thing) | breadth (sweep many examples) |

`/shakedown`'s Phase 0 *uses* grill's interrogation discipline to build the lens — so a shakedown *contains* a directed grill, but is not a *mode* of grill: the probe loop is the distinct activity, and it owns a durable corpus grill never produces.

## References

- `.claude/commands/grill.md` — the interrogation discipline Phase 0 draws on; the inverse-flow sibling.
- `.claude/support/shakedowns/README.md` — corpus convention + doc structure.
- `.claude/support/reference/merge-queue.md` — the re-entry transport ⚠/deltas emit to (DEC-023).
- `.claude/rules/spec-workflow.md` — where the shakedown fits (target-aware probing; findings route via the merge queue → `/iterate`).
- `.claude/commands/diagnose.md`, `.claude/commands/review.md` — adjacent capabilities (bug methodology; code-quality review).
- `decisions/decision-019-shakedown-command.md` (establishing) + `decisions/decision-023-vision-hub-and-spec-shaping-workflow.md` (purpose reframe + target-awareness + emit).
