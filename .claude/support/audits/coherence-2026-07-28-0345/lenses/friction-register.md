# Lens: friction-register

Findings: 0

(No findings on this axis. Only 1 open friction entry exists — FR-028 (path_drift, captured 2026-07-26, 2 days old), below the 3-entry clustering threshold and not stale. FR-028 is a code-level dangling table reference (`oem_lh.silver_WB` at `fabric/data_quality_analysis.Notebook/notebook-content.py:421`), not a spec/vision/decision structural contradiction, so it does not rise to the high-severity-single bar — it is routine path_drift evidence that the path-drift lens handles. The entry carries no `owned_by_task` field; `captured_in.task` is task-033 provenance only, and task-033 is Finished, so the register entry is unowned and available for the path-drift lens or a future task to consume.)
