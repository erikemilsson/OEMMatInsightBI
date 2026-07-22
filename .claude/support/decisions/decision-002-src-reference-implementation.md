---
id: DEC-002
title: src/transformations is the reference implementation of notebook logic, guarded by parity tests
status: approved
category: architecture
created: 2026-07-22
decided: 2026-07-22
decided_by: user
recommended_by: implement-agent
recommendation_date: 2026-07-22
related:
  tasks: [task-032, task-025, task-028]
  decisions: []
implementation_anchors:
  - src/transformations/key_generation.py
  - src/transformations/data_quality.py
  - tests/test_key_generation.py
inflection_point: false
spec_revised: false
blocks: []
---

# src/transformations is the reference implementation of notebook logic, guarded by parity tests

## Select an Option

Mark your selection by checking one box:

- [ ] Option A: Notebooks `%run` or import the src module inside Fabric
- [x] Option B: src documented as REFERENCE implementation, duplication guarded by a parity test  *(recommended — implemented under task-032)*

> **Ratified by Erik on 2026-07-22.** Option B was recommended by implement-agent under task-032's acceptance criterion 3 and implemented ahead of ratification. Erik reviewed and instructed that the box be ticked; Claude recorded the selection on his behalf. Selection authority remains the user's (`.claude/rules/decisions.md`, DEC-016) — this is a user decision transcribed, not an agent self-approval. The earlier self-approved state was caught by verify-agent during task-032 and reset to `proposed` before this ratification.

## Background

The repo convention in root `CLAUDE.md` states: *"Testable transforms: Python modules in `src/` with pytest coverage."* In practice the Fabric notebooks import nothing from `src/` — the transformation logic is duplicated inline. The green pytest suite therefore certified functions the pipeline never runs.

This was not merely cosmetic. `src/transformations/key_generation.py::generate_country_key` hashed **iso3 and name together**, while the notebook's production version is **iso3-preferred** (`when(iso3 notNull, stable_key([iso3])).otherwise(stable_key([name]))`). `tests/test_key_generation.py::test_generate_country_key_consistency` asserted the *opposite* of production semantics — that same-ISO3/different-name must produce *different* keys.

Because country keys are content hashes, adopting the tested `src` semantics in a future "let's deduplicate this" refactor would silently change every `country_key`, and every fact-dim join would stop matching **without raising an error** in DirectLake. The iso3-stability property is also load-bearing for task-025's `dim_country` dedupe.

task-032's acceptance criterion 3 required choosing a structural fix rather than only correcting the drift.

## Options Comparison

| | Option A — notebooks import src | Option B — src as reference + parity test |
|---|---|---|
| Removes duplication | Yes | No (duplication remains, but becomes enforced) |
| Detects silent divergence | Yes (one implementation) | Yes (CI fails on divergence) |
| Fabric deploy coupling | High | None |
| CI packaging stage required | Yes | No |
| Implementable locally | No | Yes |
| Cost | Wheel build + custom Fabric Environment + deploy | One test class |

## Option Details

### Option A: Notebooks `%run` or import the src module inside Fabric

Fabric notebooks cannot trivially import repo code. Two sub-routes exist, both rejected on evidence:

1. **Publish a wheel to a custom Fabric Environment.** Adds a CI packaging stage and a Fabric-side deploy, and couples every local `src/` edit to Fabric runtime state — a local refactor becomes a deployment.
2. **Add a companion notebook that `%run`s shared definitions.** That companion notebook is itself a copy of the file, which *relocates* the duplication rather than removing it.

Neither is justified for roughly ten lines of hashing logic. This route was also blocked for task-032 independently: no `fabric/` artifact could be modified while tasks 022–026 carry unvalidated in-flight changes awaiting Fabric-side validation.

### Option B: src as REFERENCE implementation, duplication guarded by a parity test *(selected)*

`src/` is explicitly documented in the module docstrings as the reference implementation of the notebook logic. The duplication is permitted but **enforced**: a parity test fails CI the moment the two diverge.

The implemented harness is stronger than the criterion's minimum. Rather than freezing a static fixture (which rots), `tests/test_key_generation.py::TestNotebookParity` **AST-parses the live notebook**, extracts its own `stable_key` / `generate_country_key` / `check_unmapped` `FunctionDef` nodes — compiling only those nodes, so no notebook side effects execute — and asserts identical output over a 9-row fixture covering every branch.

Parity alone cannot catch a change applied to *both* implementations simultaneously, so golden key constants are additionally pinned (`USA=2495174926603723698`, `TUR=5291645484684744615`, `UNK_GLOB=2182860759765913374`, null-iso3 `Kosovo=3499860001858543104`, material `Lithium=330553000305089562`).

## Decision

**Option B — selected and ratified 2026-07-22.** `src/transformations` is the reference implementation of the notebook transformation logic; the inline duplication in Fabric notebooks is retained but guarded by parity tests that extract and execute the notebook's own function definitions. The choice is recorded in both module docstrings.

## Trade-offs

**Accepted:** the logic still exists in two places, so a notebook edit and a `src/` edit are two separate acts. The parity test makes that loud rather than silent, but it does not make it single-source.

**Gained:** silent divergence becomes a CI failure; no Fabric deploy coupling; entirely local implementation; the harness cannot go stale because it reads the live notebook.

**Residual risk:** the pinned golden `country_key` values encode the *current* notebook logic. If Erik's pending Fabric validation of task-025 changes the iso3 semantics, the parity test and the golden constants must be regenerated together with a full gold rebuild. This is the residual risk task-032's dependency override already anticipated — and the parity test is precisely what will surface it.

## Impact

- **task-032** — acceptance criterion 3 satisfied; suite 70 → 87 tests.
- **task-025** — the iso3-stability property its `dim_country` dedupe relies on is now permanently pinned by test rather than by convention.
- **task-028** — its stated caveat (*"initcap behavior verified from Spark semantics, not executed"*) is resolved empirically: `find_unreachable_initcap_keys()` uses Spark's real `initcap`, and executed tests confirm the audit's predicted split exactly. task-028 can consume that function instead of an in-notebook assertion.
- **Future refactors** — a "unify toward src" refactor can no longer silently break every fact-dim join.
