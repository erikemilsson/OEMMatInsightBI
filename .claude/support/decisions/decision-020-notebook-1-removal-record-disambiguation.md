---
id: DEC-020
title: Keep the 2026-08-10 Notebook_1 removal row as true and add a row for the second, later item with the same name
status: recorded
category: process
created: 2026-10-16
decided: 2026-10-16
decided_by: orchestrator
related:
  tasks: ["task-079"]
  decisions: []
implementation_anchors:
  - file: "docs/architecture/fabric-artifacts-inventory.md"
    description: "§ Previously removed: the original Notebook_1 row (removed 2026-08-10) plus new rows for 'Notebook_1 (second)' and tmp_task064_seed (both deleted 2026-10-16); dated live-measurement line under the intro"
inflection_point: false
spec_revised:
spec_revised_date:
blocks: []
---

# Keep the 2026-08-10 Notebook_1 removal row as true and add a row for the second, later item with the same name

## Background

task-079 was filed by the 2026-08-21 phase-level verification. It said the inventory's row "`Notebook_1` … Removed 2026-08-10" was a false record, because a `Notebook_1` was still live on 2026-08-20. Criterion 2 asked for that row to be "corrected to reflect measured workspace state."

While implementing the task (Erik chose to delete both orphan items via the Fabric API on 2026-10-16), the orchestrator found that the premise didn't hold. The live `Notebook_1` was a different item from the one removed on 2026-08-10:

- Commit `eddc45b` (2026-08-10) re-measured the workspace at 22 → 13 items with `Notebook_1` among those swept, and the spec records 13 items enumerated that day. If the original notebook had survived, the count would have been 14.
- Every executed output in the deleted notebook (id `c4749a34-…`) dates from after the cleanup: Delta history up to v103 on 2026-08-11, a load filter of `>= '2026-08-12'`, and `gold_quality_history` rows from 2026-08-12. The content is task-069's column-type investigation. The original held task-025 checks.
- The id first appears in repo history on 2026-08-21 (`4a0aaae`).

## Options Comparison

| Option | What it writes | Problem |
|---|---|---|
| A. Rewrite the row as false | "Notebook_1 was never removed on 2026-08-10; deleted 2026-10-16" | Contradicts the measured 13-item count. The inventory would gain the error the task set out to remove. |
| B. Keep the row and disambiguate | The original row stays "Removed 2026-08-10", and a "Notebook_1 (second)" row records the later item: found live 2026-08-20, deleted 2026-10-16 | Departs from the literal wording of criterion 2 |

## Decision

**Selected:** B, keep the row and disambiguate.

The evidence points to two items with the same name, and Fabric reuses default names like `Notebook_1`. Keeping the true row and adding the second item meets criterion 2's intent (the inventory reflects measured workspace state) without contradicting the 2026-08-10 measurement. `CHANGELOG.md` and `spec_v1.md` § naming also say `Notebook_1` was removed 2026-08-10, and they stay correct under B, so neither needed an edit.

## Trade-offs

- The verifier noted that content alone can't tell a new item from the same item with its cells overwritten. The two-items conclusion rests on `eddc45b`'s 13-item count being a real live enumeration, which the commit message ("re-measured") and the spec ("enumerated 2026-08-10") both say it was.
- The inventory now carries two rows with the same display name, distinguished by a "(second)" suffix.

## Impact

- `docs/architecture/fabric-artifacts-inventory.md` only. No spec or CHANGELOG change.
- task-079 verified (pass, attempt 1, 2026-10-16). It resolves FR-101.
- Lesson for future live-state findings: compare item ids or dated counts, not display names (a `false_positive` friction marker from this session records it).
