# Lens: path-drift

Findings: 2

## F-pat-01
- **Title:** Stale template-era .claude paths in spec header
- **Severity:** low
- **Source anchor:** `.claude/spec_v1.md § Project Overview` (lines 18, 20, 22 — the "Instructions for Claude Code" preamble)
- **Files affected (read-only):** `.claude/spec_v1.md`
- **Files to touch (potential fix):** `.claude/spec_v1.md` — synthesizer will classify as `kind: decision`
- **Evidence:**
  ```
  > -   Context documentation (`.claude/context/`)
  > -   Reference files (`.claude/reference/`)
  > -   Standards and conventions (`.claude/context/standards/`)
  ```
- **What:** The spec's "Instructions for Claude Code" preamble references three paths that do not exist on disk (`.claude/context/`, `.claude/reference/`, `.claude/context/standards/`).
- **Why:** The actual canonical locations are `.claude/support/documents/` (context docs), `.claude/support/reference/` (reference docs), and `.claude/support/documents/standards/` (standards) — verified by `ls .claude/support/documents/` and `ls .claude/support/reference/`. The `.claude/context/` directory does not exist at all. These stale paths are template-era boilerplate that was never updated when the project adopted the `.claude/support/` layout (documented in root `CLAUDE.md` and `.claude/CLAUDE.md`).
- **Suggested fix:** Spec amendment via `/iterate`: replace `.claude/context/` with `.claude/support/documents/`, `.claude/reference/` with `.claude/support/reference/`, and `.claude/context/standards/` with `.claude/support/documents/standards/` in § Project Overview (lines 18, 20, 22).
- **Suggested kind:** decision

## F-pat-02
- **Title:** CI/CD paths described as existing, never created
- **Severity:** med
- **Source anchor:** `.claude/spec_v1.md § Infrastructure & Deployment` (lines 1197, 1200, 1205, 1210)
- **Files affected (read-only):** `.claude/spec_v1.md`
- **Files to touch (potential fix):** `.claude/spec_v1.md` — synthesizer will classify as `kind: decision`
- **Evidence:**
  ```
  -   **Parameterization:** `parameter.yml` for environment-specific config (lakehouse IDs, connection strings)
  ...
  **GitHub Actions Workflow:** `.github/workflows/fabric-deploy.yml`
  ...
  -   Environment-specific find-and-replace via `parameter.yml`
  ...
  -   Notebook-to-Lakehouse bindings don't auto-update across environments — `parameter.yml` handles this
  ```
- **What:** The spec's "CI/CD Deployment" subsection describes `parameter.yml` and `.github/workflows/fabric-deploy.yml` as if they currently exist, but neither file exists on disk — `find` returns no matches and `.github/workflows/` contains only `test.yml` (an unrelated "Tests & Quality Checks" workflow).
- **Why:** The spec is internally inconsistent: § Next Steps & Priorities (line 1536) marks "Phase 4 | CI/CD Deployment | Planned", but § Infrastructure & Deployment describes the same CI/CD artifacts in the present tense with specific file paths. A reader following the spec would expect on-disk files that were never created. This is path-drift because the spec mentions concrete paths (`parameter.yml`, `.github/workflows/fabric-deploy.yml`) that have no on-disk counterpart and no renamed-equivalent nearby (the only sibling in `.github/workflows/` is `test.yml`, which has a different function entirely). No open friction-register entry covers this — FR-028 is a code-path drift (`oem_lh.silver_WGI` in `data_quality_analysis.Notebook`), not a spec-path drift.
- **Suggested fix:** Spec amendment via `/iterate` in § Infrastructure & Deployment: either (a) reframe the CI/CD Deployment subsection as "Planned approach" with explicit "not yet implemented" markers on `parameter.yml` and `.github/workflows/fabric-deploy.yml`, or (b) move the file-path specifics into the Phase 4 deliverables list (§ Next Steps & Priorities line 1545 already lists `parameter.yml` correctly as a future deliverable) and keep only the approach description in Infrastructure & Deployment.
- **Suggested kind:** decision