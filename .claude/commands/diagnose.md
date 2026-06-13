# Diagnose Command

A discipline for working hard bugs and performance regressions. Six phases: feedback loop → reproduce → hypothesise → instrument → fix → cleanup + post-mortem. **Skip phases only when explicitly justified.**

Adapted from `mattpocock/skills/engineering/diagnose`. CCE adaptations: domain-genericized (methodology applies to any "something is wrong, I don't know why" task — software, research, procurement, renovation), consumes `./CONTEXT.md` and decision records when present, routes architectural recommendations through `/research` rather than a direct write, and hands Phase-6 architectural friction to CCE's friction register (no `/improve-codebase-architecture` exists yet — that's FB-067 Wave 2).

`/diagnose` does **not** carry `disable-model-invocation: true`. Per the FB-071 selection criteria, autonomous-fire-when-stuck is a feature here, not a foot-gun: when implement-agent hits a hard bug mid-`/work`, sweeping into structured methodology is exactly the value. If this proves wrong in practice (the model fires `/diagnose` on simple "why doesn't this work?" questions), flip to gated (FB-071's medium-candidates re-evaluation pattern).

## Usage

```
/diagnose                        # Diagnose the current issue (the model picks from conversation context)
/diagnose {issue-description}    # Diagnose a specific issue
/diagnose {task-id}              # Diagnose the bug for a specific task
```

## When to Use

- A bug whose cause is not obvious from inspection.
- A non-deterministic / flaky failure mode.
- A performance regression.
- A failing test you can't immediately explain.
- Any task where you want hypothesis-led debugging instead of "try things and see."

## Pre-flight

Use the project's domain glossary (`./CONTEXT.md` if present — see `commands/grill.md`) to get a clear mental model of the relevant modules. Check decision records (`.claude/support/decisions/`) for any decisions that scoped the area you're touching — they may explain seemingly-odd choices.

## Phase 1 — Build a feedback loop

**This is the skill.** Everything else is mechanical. If you have a fast, deterministic, agent-runnable pass/fail signal for the bug, you will find the cause — bisection, hypothesis-testing, and instrumentation all just consume that signal. If you don't have one, no amount of staring at code will save you.

Spend disproportionate effort here. **Be aggressive. Be creative. Refuse to give up.**

### Ways to construct one — try them in roughly this order

1. **Failing test** at whatever seam reaches the bug — unit, integration, e2e.
2. **Curl / HTTP script** against a running dev server.
3. **CLI invocation** with a fixture input, diffing stdout against a known-good snapshot.
4. **Headless browser script** (Playwright / Puppeteer / browser MCP) — drives the UI, asserts on DOM / console / network.
5. **Replay a captured trace.** Save a real network request / payload / event log to disk; replay it through the code path in isolation.
6. **Throwaway harness.** Spin up a minimal subset of the system (one service, mocked deps) that exercises the bug code path with a single function call.
7. **Property / fuzz loop.** If the bug is "sometimes wrong output", run 1000 random inputs and look for the failure mode.
8. **Bisection harness.** If the bug appeared between two known states (commit, dataset, version), automate "boot at state X, check, repeat" so you can `git bisect run` it.
9. **Differential loop.** Run the same input through old-version vs new-version (or two configs) and diff outputs.
10. **HITL loop.** Last resort. If a human must click, structure the loop so their captured output feeds back to you — don't have them debug ad-hoc.

Build the right feedback loop, and the bug is 90% fixed.

### Iterate on the loop itself

Treat the loop as a product. Once you have *a* loop, ask:

- Can I make it faster? (Cache setup, skip unrelated init, narrow the test scope.)
- Can I make the signal sharper? (Assert on the specific symptom, not "didn't crash".)
- Can I make it more deterministic? (Pin time, seed RNG, isolate filesystem, freeze network.)

A 30-second flaky loop is barely better than no loop. A 2-second deterministic loop is a debugging superpower.

### Non-deterministic bugs

The goal is not a clean repro but a **higher reproduction rate**. Loop the trigger 100×, parallelise, add stress, narrow timing windows, inject sleeps. A 50%-flake bug is debuggable; 1% is not — keep raising the rate until it's debuggable.

### When you genuinely cannot build a loop

Stop and say so explicitly. List what you tried. Ask the user for: (a) access to whatever environment reproduces it, (b) a captured artifact (HAR file, log dump, core dump, screen recording with timestamps), or (c) permission to add temporary production instrumentation. Do **not** proceed to hypothesise without a loop.

Do not proceed to Phase 2 until you have a loop you believe in.

## Phase 2 — Reproduce

Run the loop. Watch the bug appear.

Confirm:

- [ ] The loop produces the failure mode the **user** described — not a different failure that happens to be nearby. Wrong bug = wrong fix.
- [ ] The failure is reproducible across multiple runs (or, for non-deterministic bugs, reproducible at a high enough rate to debug against).
- [ ] You have captured the exact symptom (error message, wrong output, slow timing) so later phases can verify the fix actually addresses it.

Do not proceed until you reproduce the bug.

## Phase 3 — Hypothesise

Generate **3–5 ranked hypotheses** before testing any of them. Single-hypothesis generation anchors on the first plausible idea.

Each hypothesis must be **falsifiable**: state the prediction it makes.

> Format: "If `<X>` is the cause, then `<changing Y>` will make the bug disappear / `<changing Z>` will make it worse."

If you cannot state the prediction, the hypothesis is a vibe — discard or sharpen it.

**Assert the outcome, not the mechanism.** Phrase each prediction as an *observable end-state* — "after `<X>`, `<measured value Y>` is within tolerance `<T>`" — never as a claim about *how* the system gets there ("because `<Z>` re-evaluates mid-operation"). A mechanism-shaped prediction can be rubber-stamped by anyone who shares the same wrong model of how the system works — writer and reviewer agree, and both are wrong. An outcome-shaped prediction stays falsifiable regardless of your mental model: if the mechanism belief was wrong, the outcome assertion fails on its own and forces the next hypothesis.

**Show the ranked list to the user before testing.** They often have domain knowledge that re-ranks instantly ("we just deployed a change to #3"), or know hypotheses they've already ruled out. Cheap checkpoint, big time saver. Don't block on it — proceed with your ranking if the user is AFK.

## Phase 4 — Instrument

Each probe must map to a specific prediction from Phase 3. **Change one variable at a time.**

Tool preference:

1. **Debugger / REPL inspection** if the environment supports it. One breakpoint beats ten logs.
2. **Targeted logs** at the boundaries that distinguish hypotheses.
3. Never "log everything and grep".

**Tag every debug log** with a unique prefix, e.g. `[DEBUG-a4f2]`. Cleanup at the end becomes a single grep. Untagged logs survive; tagged logs die.

**Perf branch.** For performance regressions, logs are usually wrong. Instead: establish a baseline measurement (timing harness, `performance.now()`, profiler, query plan), then bisect. Measure first, fix second.

## Phase 5 — Fix + regression test

Write the regression test **before the fix** — but only if there is a **correct seam** for it.

A correct seam is one where the test exercises the **real bug pattern** as it occurs at the call site. If the only available seam is too shallow (single-caller test when the bug needs multiple callers, unit test that can't replicate the chain that triggered the bug), a regression test there gives false confidence.

**If no correct seam exists, that itself is the finding.** Note it. The codebase architecture is preventing the bug from being locked down. Flag this for Phase 6.

If a correct seam exists:

1. Turn the minimised repro into a failing test at that seam.
2. Watch it fail.
3. Apply the fix.
4. Watch it pass.
5. Re-run the Phase 1 feedback loop against the original (un-minimised) scenario.

## Phase 6 — Cleanup + post-mortem

Required before declaring done:

- [ ] Original repro no longer reproduces (re-run the Phase 1 loop)
- [ ] Regression test passes (or absence of seam is documented in the task's notes / `issues_discovered`)
- [ ] All `[DEBUG-...]` instrumentation removed (`grep` the prefix; nothing left over)
- [ ] Throwaway prototypes deleted (or moved to a clearly-marked debug location)
- [ ] The hypothesis that turned out correct is stated in the commit / PR message — so the next debugger learns

**Then ask: what would have prevented this bug?**

If the answer involves an architectural change (no good test seam, tangled callers, hidden coupling), CCE's path:

1. **Light-touch case:** record the observation in the task's `issues_discovered` field, or as a `design_contradiction` entry in the friction register (`.claude/support/friction.jsonl` — see `.claude/rules/agents.md § Friction Register`).
2. **Substantial case:** open a `/research` flow for the architectural change. Decision record + research-agent investigation; `/iterate` applies the spec amendment if the change shapes the spec.

Make the recommendation **after** the fix is in, not before — you have more information now than when you started.

(FB-067 Wave 2 includes `/improve-codebase-architecture` as a future complement to this phase. Until that ships, the friction-register / `/research` path above is the canonical route.)

## Visual / browser-rendering bugs

For layout, geometry, scroll, computed-style, and rendering bugs — the class where a load-bearing browser-behavior assumption can be confirmed wrongly by code-reading alone (writer and reviewer share the same docs-derived model, and both are wrong; FB-085). The six phases apply unchanged; this recipe pins the visual-specific choices so they aren't re-derived per bug:

- **Run at orchestrator level** (main conversation), not in a dispatched subagent — browser MCP access is not reliably inherited by Task subagents, and a single browser session cannot fan out (`.claude/support/reference/mcp-patterns.md § "MCP and Parallel Execution"`). If Playwright tools aren't in the loaded toolset, load them via ToolSearch first. Starting a dev server for the loop is sanctioned; respect-prior-kills applies.
- **Contract (Phases 1–2):** the feedback loop is a set of falsifiable assertions on *measured values* — geometry (bounding rects, scroll positions) and computed style (`getComputedStyle`), including sampled interaction states (hover, mid-scroll). **No pixel-diffs or golden-image comparisons:** they need a baseline the broken state can't provide, carry rendering noise, and "looks different" isn't falsifiable.
- **Measure with `browser_evaluate`** using targeted queries (`.claude/support/reference/mcp-patterns.md § "MCP and Result-Size Constraints"`). `browser_take_screenshot` is reporting evidence for the user — never the pass/fail arbiter.
- **Loop (Phases 3–5):** N=3 iterations by default (configurable). Each iteration carries ONE falsifiable hypothesis with a **predicted value-effect computed before touching code** ("moving to `object-position: 50% 30%` should put the subject's bounding-box top at ~120±10px"). Phase 3's outcome-not-mechanism rule applies with full force here. Early-exit when out of distinct hypotheses — don't pad the count with tweak-and-see variants.
- **Non-convergence at the cap:** surface a report — the unmet contract, the per-iteration hypothesis → prediction → measured-result trace, and before/after screenshots. Never auto-declare success, never silently stop, never keep iterating past the cap.
- **Persistence (Phase 5):** if the project has a test harness with a correct seam, offer to persist the passing contract as a regression test; otherwise the loop is ephemeral and the final measured values go in the task's verification notes.

## Out of scope

- **Symptom-suppression fixes.** Don't. The existing `.claude/rules/agents.md § Root Cause Over Symptom` rule applies — verify-agent rejects implementations that make errors disappear without understanding why. `/diagnose` is the structured way to *not* suppress.
- **Spec / decision / vision edits.** DEC-016 guardrail applies. If a diagnosis reveals the spec is wrong, route to `/iterate`. If it reveals a decision needs to change, route to `/research`. `/diagnose` does not edit these surfaces directly.

## References

- Original pattern: `mattpocock/skills/engineering/diagnose/SKILL.md`
- Root cause discipline: `.claude/rules/agents.md § "Root Cause Over Symptom"` (mutual reference; `/diagnose` is the structured enforcement mechanism on multi-turn debugging)
- Decision flow: `.claude/rules/decisions.md` (when to open `/research`)
- Friction register: `.claude/support/reference/friction-register.md` (Phase-6 architectural findings)
- Domain glossary: `.claude/commands/grill.md` + `./CONTEXT.md` (Pre-flight vocabulary check)
- Bug-task placement: `.claude/rules/spec-workflow.md § "Workflow Cycle"` (preferred route for bug tasks)
