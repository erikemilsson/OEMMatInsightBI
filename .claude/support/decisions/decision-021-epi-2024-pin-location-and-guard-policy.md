---
id: DEC-021
title: Pin the EPI 2024 CSVs in the repo (raw.githubusercontent.com on main) behind a fail-closed content guard
status: recorded
category: architecture
created: 2026-10-16
decided: 2026-10-16
decided_by: implement-agent
related:
  tasks: ["task-082"]
  decisions: []
implementation_anchors:
  - file: "fabric/bronze_ingest_epi.Notebook/notebook-content.py"
    description: "EPI_SOURCE_BASE_URL -> raw.githubusercontent.com/erikemilsson/OEMMatInsightBI/main/reference_data/epi; guard cell CSV_CONTENT_TYPES, EpiSourceNotCsvError, assert_csv_response() called before each pd.read_csv"
  - file: "reference_data/epi/"
    description: "Yale's original epi2024results.csv and epi2024weights.csv, byte-identical to the Wayback Machine copies, plus a README with provenance and the license notice"
  - file: "tests/test_epi_source_guard.py"
    description: "26 tests: guard behaviour per content type, HTML body check, sha256 pins on both files"
inflection_point: false
spec_revised:
spec_revised_date:
blocks: []
---

# Pin the EPI 2024 CSVs in the repo (raw.githubusercontent.com on main) behind a fail-closed content guard

## Background

Yale released EPI 2026 in September 2026 and retired the `https://epi.yale.edu/downloads/epi2024*.csv` paths. They now return HTTP 200 `text/html`, and `bronze_ingest_epi` passed that page straight to pandas. Every scheduled run failed from 2026-09-25 to 2026-10-16 (task-082, from phase-level verification).

Erik decided the approach: keep the 2024 vintage, store the original files somewhere we control, and add a pre-parse guard. Two implementation choices were left to the agent and are recorded here: where to pin the files, and which content types the guard accepts.

## Options Comparison

| Option | Pin location | Needs a live step? | Notes |
|---|---|---|---|
| **A** | Repo `reference_data/epi/`, fetched from raw.githubusercontent.com on `main` | No: Erik's normal push deploys the notebook and publishes the files | Versioned with the code; same HTTPS + retry code path; needs the repo to stay public |
| B | OneLake lakehouse `Files/` | Yes: an upload | Not versioned |
| C | Wayback Machine snapshot URLs directly | No | A third-party dependency, which is what Erik asked to avoid |
| D | As A, but pinned to a commit SHA | No | Can't be done in one commit (the SHA doesn't exist yet); possible later hardening |
| E | GitHub Release asset | Yes: a release step | |
| F | As A, but under `data/` | No | `data/` is gitignored, so a plain `git add .` would silently leave the files out |

Guard policy options: allow `text/csv` only; **allow `text/csv`, `application/csv` and `text/plain`, plus an HTML body check**; or block `text/html` only.

## Decision

**Selected:** A. Pin in the repo, fetched from raw.githubusercontent.com on `main`. It needs no live write beyond the push that already deploys the notebook, it keeps the data versioned next to the code, and sha256 tests fail on any edit to the files.

**Selected:** guard allowlist `text/csv`, `application/csv` and `text/plain`, plus an HTML check on the body whatever the header says. A missing Content-Type or an empty body fails closed with `EpiSourceNotCsvError(ValueError)`. `text/plain` is required because raw.githubusercontent.com serves text files as `text/plain; charset=utf-8` (measured). The body check catches an HTML page under any allowed type (verified under all three).

## Trade-offs

- The EPI source now depends on the repo staying public and the files staying on `main`. Either failure shows up as a named 404 error that states both constraints.
- `main` can move. The sha256 tests catch edits, but a SHA-pinned URL (option D) would be stricter.
- The HTML check matches `<!doctype html` or `<html` in the first 2 KB. An HTML fragment without either would get past it and fail at the notebook's own schema check instead.
- The public MIT-licensed repo now redistributes Yale's data. The README states CC BY-NC-SA 4.0 with attribution, taken from the project's own docs; nobody has re-checked it against Yale's current terms.

## Impact

- Files: the notebook, `reference_data/epi/` (3 files), `tests/test_epi_source_guard.py`, `tests/_notebook_loader.py` (also extracts top-level classes), and 5 docs.
- task-082 verified (pass, attempt 1, 2026-10-16). Live confirmation (AC4) waits for Erik's push and a pipeline run.
- Spec text (L216, L261, L860, L1497, L1501) still names `epi.yale.edu` and routes through `/iterate` (FR-106).
