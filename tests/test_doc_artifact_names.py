"""Regression guard for the Fabric artifact-rename sweep (audit C-01 / task-021, 2026-06-21).

Three Fabric artifacts were renamed on disk, the spec was corrected each time, but the
surrounding docs kept the OLD names — most visibly the portfolio front door (README) and
the artifacts inventory, which even tagged non-existent artifacts "Active". task-021 swept
them. This test prevents recurrence on the recruiter-facing surfaces.

Renames (old -> new; new is canonical on disk):
  semantic_model_oeminsightbi      -> OEMInsightBI_v2
  clean_columnsAndHeaders.Notebook -> bronze-to-silver.Notebook
  report.Report                    -> report2.Report

Scope note: this guard only covers surfaces that have NO legitimate historical/example
occurrence of the old names. It deliberately does NOT cover:
  - .claude/support/documents/standards/naming_standards.md   (naming-convention examples)
  - .claude/support/documents/error_handling_strategy.md      (pipeline activity identifiers; see FR-003)
  - .claude/support/documents/incremental_load_strategy.md    (L540/543 activity-config; see FR-003)
  - docs/architecture/fabric-artifacts-inventory.md           (L64 "Consider renaming" discussion)
  - project_definition.md                                     (L1031 naming-convention example)
  - fabric/archive/**, .claude/tasks/**, .claude/support/{audits,friction.jsonl,feedback/archive.md}
Adding a broad allowlist for those would make the guard fragile; keeping it to clean
surfaces keeps it robust.
"""
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent

# Old names that must never reappear on a clean surface.
# "report.Report" does not match "report2.Report" (the new name) as a substring.
OLD_NAMES = (
    "semantic_model_oeminsightbi",
    "clean_columnsAndHeaders",
    "report.Report",
)

# Recruiter-facing / guide surfaces with no legitimate old-name occurrence.
CLEAN_SURFACES = (
    "README.md",
    "docs/README.md",
    "docs/portfolio/PORTFOLIO_ASSETS_README.md",
    "docs/guides/FAQ.md",
    "docs/setup/TROUBLESHOOTING.md",
    "docs/architecture/data-flow-diagram.md",
)


def _stale_hits(rel):
    path = REPO / rel
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    return [name for name in OLD_NAMES if name in text]


@pytest.mark.parametrize("rel", CLEAN_SURFACES)
def test_no_stale_fabric_artifact_names(rel):
    hits = _stale_hits(rel)
    if hits is None:
        pytest.skip(f"{rel} not present")
    assert not hits, (
        f"{rel} reintroduced pre-rename Fabric artifact name(s): {hits}. "
        "Use OEMInsightBI_v2 / bronze-to-silver.Notebook / report2.Report "
        "(audit C-01, task-021)."
    )


if __name__ == "__main__":
    # Standalone runner (no pytest dependency) for quick verification.
    failures = []
    for rel in CLEAN_SURFACES:
        hits = _stale_hits(rel)
        if hits is None:
            print(f"SKIP {rel} (not present)")
        elif hits:
            failures.append((rel, hits))
            print(f"FAIL {rel}: {hits}")
        else:
            print(f"PASS {rel}")
    raise SystemExit(1 if failures else 0)
