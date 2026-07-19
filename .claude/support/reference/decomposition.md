# Spec Decomposition

Procedure for breaking a spec into granular tasks. Run as `/work` Step 4 "If Decomposing."

---

## Procedure

1. **Run setup checklist** — Read `.claude/support/reference/setup-checklist.md` and run through its checks. Report any warnings inline. Continue regardless (advisory, not blocking).

2. **Read spec thoroughly** — Understand all requirements and acceptance criteria.

3. **Flip spec status, THEN compute spec fingerprint** — First update the spec frontmatter `status: draft` → `active` (see § "Spec Status Transition" below; infrastructure edit, autonomous). Then compute the SHA-256 hash of spec content (see `drift-reconciliation.md` § "Spec Drift Detection"). **Order matters:** the status flip changes the file, so flipping after this step stamps every task JSON and the index with a stale pre-flip fingerprint — a false-drift trap observed twice downstream, each requiring manual re-stamps.

4. **Save spec snapshot** — Copy current spec to `.claude/support/previous_specifications/spec_v{N}_decomposed.md`.

5. **Parse spec into sections** — Extract `##` level headings and their content.

6. **Compute section fingerprints** — SHA-256 hash of each section (heading + content).

7. **Identify work items** — Each distinct piece of functionality per section.

8. **Create task files** — One JSON per task, difficulty <= 6, with full provenance:
   - `spec_fingerprint` — Hash of full spec computed in step 3
   - `spec_version` — Filename of spec (e.g., "spec_v1")
   - `spec_section` — Originating section heading (e.g., "## Authentication")
   - `section_fingerprint` — Hash of specific section computed in step 6
   - `section_snapshot_ref` — Snapshot filename (e.g., "spec_v1_decomposed.md")
   - `spec_subsection` + `subsection_fingerprint` *(optional, DEC-021)* — when a task's work is scoped to a single `### ` subsection of a **large** `## ` section (consult the section index `char_count` from `fingerprint.py --index`; "large" = big enough that a one-line edit elsewhere in it would needlessly re-flag this task), record the `### ` heading + its hash (`fingerprint.py --sections --depth 3`). Lets drift detection spare this task when a *different* subsection of the same `## ` section changes. Skip for tasks in small sections or tasks that span a whole section — they use `## `-level drift.
   - **Important:** Create all task JSON files before regenerating the dashboard. Every task must have a `task-*.json` file — the dashboard is generated from these files, never the other way around.
   - **Script alternative:** Capture hashes via `.claude/scripts/fingerprint.py --spec` / `--sections`; orchestrator writes the `sha256:...` strings into task JSON `spec_fingerprint` and `section_fingerprint` fields.
   - **`.claude/`-boundary split:** when a work item spans both `.claude/` paths and regular project paths, split it into separate tasks (or annotate it) — subagents cannot write `.claude/` (DEC-004), so the `.claude/` portion is orchestrator-implemented inline with a read-only verify-agent pass. Declaring this at decomposition prevents mid-dispatch correction (observed in 3 downstream sessions).
   - **After creating task JSONs:** run the Decomposition Pre-Pass Validation (below) to catch declared-path drift and under-counted `files_affected`, and the Test-Harness Awareness check (below) to propose scenario-authoring subtasks for runtime-shaped tasks — both run before tasks ship to `/work` Step 2c.

9. **Map dependencies** — What must complete before what.

10. **Regenerate dashboard** — Follow `.claude/support/reference/dashboard-regeneration.md` in full.

---

## Decomposition Pre-Pass Validation

Runs after step 8 (Create task files). Catches two recurring failure modes that surface as implementer-side friction (~3 wasted tool uses per path-correction; friction markers across ~40% of large-batch sessions).

### Leg 1: Path Resolution Check

For each task JSON just created, verify that every path in `files_affected` exists. Also scan the task `description` for path-shaped tokens (matches like `src/components/.../*.tsx`, `tests/.../*.test.py`) and verify those resolve too.

For any non-resolving path, surface inline:

```
Decomposition warning: Task {id} references non-existent path
  declared: src/components/grooming/GroomingSection.tsx
  closest match: src/components/style/GroomingSection.tsx
  → fix the task before continuing? [Y/N]
```

Use a fuzzy-match (e.g., `Glob` for the basename) to suggest the closest existing path. If no match, leave the warning and let the user correct. Do not auto-rewrite — the suggestion may be wrong.

### Leg 2: Ripple Inference

For each task, run targeted greps to surface ripple-affected files the declared `files_affected` may miss. Seven detection heuristics:

| Pattern in task description | Grep target | Add to candidates |
|----------------------------|-------------|-------------------|
| `remove X` / `retire X` / `deprecate X` (where X is a field, type, or constant) | `grep -r "X"` across `**/__tests__/**`, `**/*.test.{ts,py,js}`, paths matching `*fixture*` / `*mock*` | Test/fixture files containing the value |
| `.max(N)` → `.max(M)` or any threshold change | `grep -r "{old_threshold}"` in fixture files | Fixtures with hard-coded values that share the schema-constant's name |
| New test files under `__tests__` / sibling-test convention | Read `package.json` `scripts.test` — if it chains explicit paths (vs glob), suggest `package.json` | `package.json` for chain-style test runners |
| Validator-walk extension (Zod/Pydantic `superRefine`, strict-parse) | `grep -r "{ParserSchemaName}\.parse\|\.{ParserSchemaName}\.safeParse"` | Downstream callers |
| New enum / literal-union / `as const` member (e.g., `add 'foo' to CriterionId`, extending `type Kind = 'a' \| 'b'`, extending `const X = [...] as const`) | `grep -rln "{EnumName}" src/ tests/` to find importers; inspect each for `switch(...)` over the enum or `Record<EnumName, ...>` maps | Files that switch / map over the enum (parsers, formatters, header maps); barrel re-exports; test factories that build instances per enum case |
| Any implementation task on code with a testable surface | Convention check: does a sibling test file exist (`X.test.ts`, `test_x.py`) or will the implementer create one? | The sibling test file — **declare it by default**; the dominant downstream `files_affected` drift (19 markers across 2 projects) is an undeclared test-file edit |
| `extract X into a new component/module`, or acceptance implies a new file | — (prediction, not grep) | The **new** file: edits land in the extracted component, not the declared shared ones; declare the new path + the importer that mounts it (2 downstream mispredictions from declaring the shared components instead) |

For each candidate, surface:

```
Decomposition note: Task {id} may be under-counting files_affected
  declared: [field-definitions.json]
  candidates from ripple grep: registry-loader.test.ts (matches "life_stage" in fixture)
  → add to files_affected? [Y/N]
```

Like Leg 1, do not auto-add — present and ask. Both legs are advisory: they reduce implementer friction without blocking decomposition if the user disagrees.

### When to Run

- Always after step 8 of the standard procedure
- Optionally as a standalone check on existing task files (via `/health-check` integration — see future scope)
- Skip for trivial decompositions (≤3 tasks, all touching disjoint single files)

### Limits

The heuristics are deliberately narrow — they catch the dominant friction patterns (verified across styler Phase 20: 12+ tasks, ~40% with files_affected under-counts) without trying to be exhaustive. Function-name drift, deep import-graph ripples, and runtime-only dependencies remain implementer-side discovery work; that's acceptable given the alternative (full static analysis at decomposition time) is much more expensive.

---

## Test-Harness Awareness

When decomposing tasks for projects with a programmatic test harness (Playwright-driven scenarios, CLI-driven simulations, etc.), prefer authoring scenario scripts over manual user verification of runtime/UI behavior. Catches the pattern echothread surfaced: a reusable harness gets re-discovered each cycle because decomposition doesn't reach for it automatically.

### Detection

A task is **harness-eligible** if ANY of these hold:

- `interaction_hint` is `cli_direct`
- `files_affected` includes paths matching a runtime-surface glob — defaults: `src/engine/**`, `src/audio/**`, `src/renderer/**`, `src/ui/**`, `src/components/**`, `src/game/**`. Projects can extend the glob list via a one-line declaration in root `./CLAUDE.md` (e.g., `**Runtime-surface paths:** src/engine/**, src/audio/**, src/headless/**`).
- `test_protocol` describes runtime/UI behavior (e.g., "drive the runtime through state X and observe Y", "click button Z and confirm UI", any interactive verification step)

If none hold, skip the check — the task is not runtime-shaped.

### Harness-directory scan

Look for a project-conventional harness directory at project root:

1. First, read root `./CLAUDE.md` for an explicit declaration (e.g., a one-line `**Harness directory:** path/to/scenarios/`). If present, use it.
2. Otherwise, scan for conventional names in order: `tooling/test-scenarios/`, `tooling/scenarios/`, `tests/scenarios/`, `e2e/scenarios/`. The first one that exists wins.
3. If none exist, the project hasn't adopted a harness convention — see fallback below.

### Decomposition action

**If harness directory exists AND no scenario covers this task's surface** — check for `<harness-dir>/{task-id}.{ts,py,js,mjs}` or any file containing `{task-id}` in its basename — propose a scenario-authoring subtask:

```
Task {id}_h: Author <harness-dir>/{id}.{ext}
  description: "Author a programmatic scenario script so task {id}'s runtime
                check can be re-run via the harness. The scenario should drive
                the runtime surface to the state {id} verifies. See root
                ./CLAUDE.md for the harness API."
  difficulty: 3
  owner: claude
  dependencies: [{id}]
  files_affected: [<harness-dir>/{id}.{ext}]
```

The subtask is dispatched after the parent finishes — its job is to convert the verification path from "manual user playthrough" to "re-runnable scenario." Surface the subtask inline:

```
Decomposition note: Task {id} is harness-eligible (interaction_hint: cli_direct)
  → propose subtask: Author <harness-dir>/{id}.ts
  Accept? [Y/N]
```

**If harness directory does NOT exist**, surface inline:

```
Decomposition note: Task {id} is harness-eligible but no harness directory found.
  Consider authoring `tooling/test-scenarios/` (or equivalent) + documenting the
  harness API in root ./CLAUDE.md. Capture via /feedback if worth pursuing.
  (Continuing with manual-verification path for now.)
```

Do not force the convention — the absence of a harness directory is a legitimate project state; the note is a soft signal, not a blocker.

### When to Run

- Always after step 8 of the standard procedure, alongside the Pre-Pass Validation
- Skip for trivial decompositions (≤3 tasks, all touching disjoint single files)
- Skip when the user explicitly opts out via task notes (e.g., `notes: "no harness scenario needed — pure refactor"`)

### Limits

The heuristic proposes the subtask but does not author the scenario itself. The scenario author (implement-agent dispatched to the `_h` subtask) needs to know the harness API — projects with a harness directory should document their API in root `./CLAUDE.md` (entry-point function, available globals, scenario-script conventions) so the implement-agent can find it. Without that documentation, the subtask is harder to execute — the heuristic ships the suggestion but project-side documentation closes the loop.

---

## Test-Protocol Runtime Constraints

When authoring `test_protocol` steps for phone-side or mobile-runtime surfaces, pre-tag steps that exercise behavior not testable under the project's primary runtime (e.g., Expo Go). Eliminates mid-attestation reframings where the user discovers a step is unrunnable.

### Detection patterns

A test_protocol step is **runtime-constrained** if it combines any of these (when project runs on Expo Go):

- **Force-quit + airplane mode + cold-launch** — Expo Go fetches its JS bundle from Metro on every cold-launch; airplane-mode cold-launch freezes Expo Go itself, regardless of in-app cache correctness.
- **Native modules outside Expo Go's fixed set** — modules requiring a dev-client install.

### Substitution patterns

For cache-path verification without a dev client, substitute one of:

1. **Background mode** (lock screen → unlock, no force-quit): JS stays in memory; tests the cache resume path without cold-launch.
2. **Server-only kill** (stop dev server, keep WiFi, force-quit + relaunch): Expo Go bundle loads, app starts, foundation fetch fails, cache fallback fires.
3. **Defer to dev client** (post-EAS): the only path that mirrors a production install.

### Annotation pattern

When no substitution is suitable, annotate the step with a `constraint` informational field:

```json
{
  "instruction": "Force-quit, enable airplane mode, relaunch — verify cache renders",
  "expected": "App paints from cache without server",
  "type": "interactive",
  "constraint": "Requires dev client (EAS); skip in Expo Go"
}
```

The `constraint` field is informational; verify-agent surfaces it during guided testing so the user defers the step until the dev client lands.

### Project-side declaration

Projects can declare their primary phone runtime in root `./CLAUDE.md`:

```markdown
**Primary phone runtime:** Expo Go (dev client planned post-EAS)
```

When absent, verify-agent infers from `package.json` (presence of `expo` + absence of dev-client convention). Inference failures degrade to "no pre-tag" — the constraint surfaces at attestation time as today.

### When to Apply

- Authoring test_protocol for any `owner: "both"` phone task
- Skip for purely-static verification (lint, type-check, snapshot tests)
- Skip if the project declares a dev-client runtime (no Expo Go limitation)

---

## Task Creation Guidelines

- Clear, actionable titles ("Add user validation" not "Backend stuff")
- Difficulty 1-6 (break down anything larger)
- Explicit dependencies
- Owner: claude/human/both
- Include all spec provenance fields (fingerprint, version, section, section_fingerprint, section_snapshot_ref)
- **Phase field:** Assign `phase` based on spec section structure (e.g., tasks from "## Phase 1: Data Pipeline" get `"phase": "1"`). Also set `phase_name` to the spec's descriptive name for the phase (e.g., `"phase_name": "Data Pipeline"`). Dashboard rendering uses the format "Phase {N} — {phase_name}" — generic labels like "Phase 1" alone are not acceptable.
- **Decision dependencies:** If a task depends on an unresolved decision, add the decision ID to `decision_dependencies` array. Note whether the decision is an inflection point in task notes.
- **Cross-phase flag:** Consider suggesting `cross_phase: true` for long-lead tasks that must start before prior phase completion. Heuristic: `owner: human` tasks whose title or notes contain recruit/procure/approve/schedule/coordinate/stakeholder/vendor/contract, OR any task with `external_dependency.expected_date` more than 14 days out. When the heuristic fires, ask the user: `"Task {id} looks like long-lead work. Mark as cross_phase: true? [Y/N]"`. Never set silently. See `task-schema.md` § `cross_phase` for semantics.

---

## Spec Status Transition

When decomposition begins — **at Procedure step 3, BEFORE the fingerprint compute** (flipping later invalidates the hashes just stamped into task JSONs and the index) — update the spec metadata `status` from `draft` to `active`:

```yaml
---
version: 1
status: active
---
```

This signals that the spec is being implemented. The transition to `complete` happens in the "If Completing" section of `/work`.

---

## Organizing Tasks Into Stages

When decomposing the spec, organize tasks into logical implementation stages:

| Stage | Focus | Examples |
|-------|-------|----------|
| **Foundation** | Setup, core infrastructure, initial research | Project structure, database schema, vendor research, requirements gathering |
| **Core Features** | Main functionality from spec | Primary user flows, API endpoints, procurement, key deliverables |
| **Polish** | Edge cases, error handling, refinement | Validation, error messages, budget reconciliation, final reviews |
| **Validation** | Testing, documentation, verification | Unit tests, integration tests, documentation, acceptance checks |

These are organizational stages for tasks within the Execute phase, not workflow phases.

---

## Research-spike Pattern

Some tasks have the shape **methodology → empirical loop → analysis**: research spikes investigating a library's behavior, perceptual A/Bs (pick design A vs B), onboarding sniff tests, dogfood cycles. The empirical step requires a human-only sensor (taste, perception, paste-an-image, run-and-observe) that Claude cannot substitute for; the surrounding methodology and analysis are Claude work. Filing the whole spike as `owner: claude` leaves the human loop invisible to dispatch and the dashboard; `owner: both` is documented for review-shaped work (Claude drafts → human refines), not for empirical apparatus.

### Trigger

The task shape combines (a) a methodology Claude can author, (b) an empirical loop only the human can run, and (c) an analysis Claude can synthesize once results come back. If any leg is absent (e.g., pure code change, pure design review), this pattern doesn't apply.

### Decomposition

For spikes where the empirical loop is independently worth tracking on the dashboard, use `/breakdown` to split into 2–3 sub-tasks:

```
TXXXa (owner: claude)                       — authors methodology, drafts empirical-prompt, stubs analysis shell
   ↓ blocks
TXXXb (owner: human, deps: [TXXXa])         — runs empirical loop, reports inline, self-attests via /work complete
   ↓ blocks
TXXXc (owner: claude, deps: [TXXXa, TXXXb]) — synthesizes results into the final report  ← optional
```

### Collapse rule

If the empirical step is a single user action with no iteration (e.g., "paste one image", "click one button"), collapse to a single `owner: claude` task with an in-prose hand-off. The paired structure is for spikes whose human loop is independently worth tracking — multi-step protocols, multiple trials, or branching observation paths.

### Description discipline

- **TXXXb's description** must include the empirical-prompt template TXXXa drafted, so the user knows exactly what to test without re-reading TXXXa.
- **TXXXc's description** must include the analysis shell TXXXa stubbed, so the synthesis step has its scaffold ready when its deps unblock.

### Verification convention

- **TXXXa / TXXXc** — verified normally by verify-agent. TXXXa's acceptance question is *"did Claude produce a methodology that matches the spike's directional question?"* — NOT *"did the empirical loop produce a specific answer?"* The empirical outcome is TXXXb's content; TXXXa is judged on methodology quality alone.
- **TXXXb** — self-attests via `/work complete` (the standard `owner: human` path; see `.claude/agents/verify-agent.md` § "Human-owned tasks"). The user IS the experimental apparatus; verify-agent has no surface to evaluate beyond the human's report.

### Why this shape

The 3-value `owner` enum conflates "who is responsible" with "who executes." For most tasks these match. Research spikes split them: methodology is Claude-shaped (author + self-verify), the empirical loop is human-shaped (only the human can run it), the analysis is Claude-shaped again. Decomposing surfaces the human loop as a first-class dashboard artifact (TXXXb appears in "Your Tasks") instead of hiding it inside a Claude-owned umbrella, and routes each sub-task to its native verification path. Pattern origin: styler `DEC-082` Option ε.

---

## Decomposition Quality Checks

Each task must have:
- Clear "done" criteria
- Independent testability
- Explicit dependencies
- Difficulty <= 6

For the difficulty scale, see `.claude/support/reference/shared-definitions.md`.
