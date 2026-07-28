---
id: DEC-006
title: Watermark gold coordination via exclude_execution_id — one mechanism, one value per run
status: approved
category: architecture
created: 2026-07-28
decided: 2026-07-28
decided_by: implement-agent
recommended_by: implement-agent
recommendation_date: 2026-07-28
related:
  tasks: [task-029]
  decisions: []
implementation_anchors:
  - fabric/silver-to-gold2.Notebook/notebook-content.py
  - fabric/bronze-to-silver.Notebook/notebook-content.py
  - fabric/orchestrator_pipeline_bronze_to_gold.DataPipeline/pipeline-content.json
inflection_point: false
spec_revised:
spec_revised_date:
blocks: []
---

# Watermark gold coordination via exclude_execution_id

> **Why a record.** task-029 criterion 4 requires silver-to-gold to consume "the same effective
> watermark" as bronze-to-silver — "same watermark value, don't invent a second mechanism." How the
> two notebooks actually coordinate on a single watermark value per run was an open design choice
> with three real alternatives. This records the one chosen and why. It is an implementation-level
> decision (how the notebooks coordinate, not what the system does), surfaced by implement-agent
> while executing task-029.

## Select an Option

Mark your selection by checking one box:

- [x] Option C: Add `p_execution_id` pipeline parameter; gold excludes the current run's row *(recommended, implemented)*
- [ ] Option A: Both notebooks call `get_last_load_date` independently
- [ ] Option B: bronze-to-silver writes the resolved watermark to a separate location for gold to read

*Implemented ahead of ratification under task-029 (Awaiting Verification). Ratification is a formality unless you want to revisit.*

## Background

The high-water-mark system (`bronze_load_metadata`) is the single watermark source for the
incremental pipeline. `bronze-to-silver` resolves an `effective_from_date` per the precedence
(full_load → 1900-01-01; explicit `p_from_date` override; else auto-retrieve last SUCCESS), uses it
to window its silver read/merge, then writes a metadata row after load — SUCCESS with the max date
loaded, or FAILED on exception. task-024 had already added the gold-side `p_from_date` filter in
`silver-to-gold2`; task-029's job was to make `bronze_load_metadata` the *source* of that watermark
without inventing a second mechanism.

The coordination problem: both notebooks run in the same pipeline invocation. `bronze-to-silver`
runs first and writes a SUCCESS row for the current run. When `silver-to-gold2` runs next and asks
"what's the last SUCCESS watermark?", a naive read returns the row `bronze-to-silver` *just wrote
this run* — the max date just loaded into silver — not the previous run's watermark that silver
actually used as its window start. Gold would then re-read from that just-loaded max, producing an
empty/wrong window. The two layers must agree on one watermark value per run, and that value is the
*previous* run's watermark (the one silver used), not the current run's just-written row.

## Options Comparison

| Criteria | Option A (independent reads) | Option B (separate watermark location) | Option C (exclude_execution_id) |
|----------|------------------------------|------------------------------------------|----------------------------------|
| Single mechanism (criterion 4) | Yes — but wrong value | No — second store | Yes |
| Correct watermark value per run | No (gold reads current run's row) | Yes | Yes |
| Pipeline change required | No | No | Yes (new `p_execution_id` param) |
| Locally testable in pytest | Yes | Yes | Yes (empty string = no-filter sentinel) |
| Matches doc §4 design | Partially | No | Yes (`execution_id` was already a doc field) |
| Overall | Wrong behavior | Violates criterion 4 | Correct + single mechanism |

## Option Details

### Option A: Both notebooks call get_last_load_date independently

**Description:** `silver-to-gold2` calls `get_last_load_date(source_table)` with no exclusion.

**Strengths:**
- No pipeline change.
- Maximally simple.

**Weaknesses:**
- **Wrong value.** `bronze-to-silver` runs first in the pipeline and writes a SUCCESS row for the
  current run before `silver-to-gold2` runs. Gold's read returns that just-written row (the max date
  loaded into silver this run), not the previous run's watermark silver used as its window. Gold's
  window becomes empty or wrong.

### Option B: bronze-to-silver writes the resolved watermark to a separate location for gold

**Description:** A second key/store holds "the effective watermark silver used this run" for gold to read.

**Strengths:**
- Correct value.

**Weaknesses:**
- **Second mechanism** — explicitly prohibited by criterion 4 ("don't invent a second mechanism").
- Two stores to keep consistent; drift surface.

### Option C: Add p_execution_id pipeline parameter; gold excludes the current run's row *(selected)*

**Description:** The pipeline gains a `p_execution_id` parameter (default `""`) bound to
`@pipeline().RunId`, passed to both notebook activities. `silver-to-gold2` calls
`get_last_load_date(source_table, exclude_execution_id=p_execution_id)`, which filters out the row
the current run just wrote. Gold therefore reads the *previous* run's SUCCESS watermark — the same
value silver used this run. One table, one `source_table` key, one value per run.

**Strengths:**
- One mechanism (`bronze_load_metadata`), one `source_table` key, one watermark value per run.
- Implements the doc §4 design rather than inventing a new one — `execution_id` was already a field
  in the metadata schema and §4's `update_load_metadata` already assumed
  `dbutils.widgets.get("execution_id")`.
- Locally testable: `p_execution_id == ""` is the no-filter sentinel, so pytest exercises the
  exclusion path without Fabric runtime context.

**Weaknesses:**
- Requires a pipeline parameter addition (`p_execution_id`) + `@pipeline().RunId` binding on both
  notebook activities — a Fabric artifact change Erik must sync to Fabric before the test_protocol
  runs.

**Research Notes:** doc §4 metadata schema includes `execution_id` (StringType, nullable) and the
`update_load_metadata` example uses `dbutils.widgets.get("execution_id")`. This decision makes that
assumption real.

## Your Notes & Constraints

*This section is yours — Claude reads it but never overwrites it.*

**Constraints:**
- Pipeline artifact changes must sync to Fabric (`/sync-to-fabric`) before Erik can run the
  task-029 criterion-5 test_protocol.

**Questions:**
-

## Decision

**Selected:** Option C — `p_execution_id` pipeline parameter + `exclude_execution_id` filter in
gold's `get_last_load_date` call.

**Rationale:**
The decision turns on criterion 4 ("same watermark value, don't invent a second mechanism"). Option
A fails on correctness (gold reads the wrong row). Option B fails the single-mechanism requirement
outright. Option C is the only option that is both correct and single-mechanism, and it realizes a
field (`execution_id`) the doc §4 design already assumed was wired. The cost is one pipeline
parameter — small, and it makes the run identifier explicit and locally testable rather than
dependent on Fabric-only runtime context (`mssparkutils.runtimeContext`) that cannot be exercised
in pytest.

## Trade-offs

**Gaining:**
- A single watermark mechanism shared by silver and gold, with one agreed value per run.
- The `execution_id` field — already in the doc schema — actually populated and used.
- Local pytest coverage of the exclusion path (empty-string sentinel).

**Giving Up:**
- A pipeline-parameter-free implementation (Option A would have touched no pipeline artifact).
- Reliance on `@pipeline().RunId` being a stable, non-empty identifier across Fabric run modes
  (verified at Fabric-side test time per criterion 5).

## Impact

**Implementation Notes:**
Implemented under task-029 ahead of ratification. `p_execution_id` added to
`pipeline-content.json` (default `""`, bound to `@pipeline().RunId`) on both notebook activities.
`get_last_load_date` extended with an optional `exclude_execution_id` parameter in both the `src/`
mirror and the inline notebook copies. The doc `incremental_load_strategy.md` §4-5 rewritten to
describe this design. task-029 is Awaiting Verification; criterion 5 (Erik's Fabric-side
two-run advancement + forced-failure test) will exercise `@pipeline().RunId` end-to-end.

**Affected Areas:**
- `fabric/silver-to-gold2.Notebook/notebook-content.py` — gold watermark read with exclusion.
- `fabric/bronze-to-silver.Notebook/notebook-content.py` — writes `execution_id` into metadata rows.
- `fabric/orchestrator_pipeline_bronze_to_gold.DataPipeline/pipeline-content.json` — `p_execution_id`
  parameter + binding.
- `src/transformations/watermark.py` — reference implementation.
- Related task: task-029.

**Risks:**
- If `@pipeline().RunId` is empty or null in some Fabric run mode (interactive notebook execution
  outside a pipeline run), the `exclude_execution_id == ""` sentinel means "no exclusion" — gold
  would then read the current run's row. Mitigation: the notebooks are only meaningful when run via
  the orchestrator pipeline (which supplies RunId); standalone notebook execution is out of the
  tested contract. Criterion 5's test_protocol verifies RunId is populated during pipeline runs.