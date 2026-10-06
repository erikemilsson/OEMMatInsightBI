# .claude/scripts

Deterministic helpers invoked by the `/work` orchestrator (or by the user directly) when LLM-executed computation has unacceptable drift or token cost.

## Scripts

| Script | Purpose | Mirrors |
|--------|---------|---------|
| `fingerprint.py` | Spec/section/dashboard-rollup SHA-256 hashes; `--index` (spec section index for scoped reads, DEC-021) + `--sections --depth 3` (additive `### ` subsection hashes); `--drift .claude` (per-task spec drift check as JSON: each task's section fingerprint against the current spec, grouped by section with deferrals applied; computed fresh, never cached; library function `compute_drift()`, FB-128) | `support/reference/drift-reconciliation.md § "Spec Drift Detection"`, `rules/spec-workflow.md § "Section-scoped spec reading"` |
| `validate-tasks.py` | Task JSON schema validation + verification debt count | `support/reference/task-schema.md`, `commands/health-check.md` Part 1 |
| `persist-friction.py` | Friction-marker dual-write payload + collision-safe `FR-NNN` ids from a marker batch (read-only; orchestrator appends) | `support/reference/work-procedures.md § "State Persistence Protocol"` step 2, `support/reference/friction-register.md § "Write protocol"` |
| `persist-session-export.py` | Session-export inbox copy-with-rename — writes the inbox file with a deterministic, never-dot-prefixed `{slug}-session-export-{ts}{suffix}.json` name (FB-109; writes a file — the inbox path is external/user-configured, never `.claude/`) | `support/reference/context-transitions.md § "Session Export"` step 6, `commands/work.md § "Step 0f"` step 8 (pass `--suffix recovered`) |
| `sync-check.py` | Template-sync check for `/health-check` Part 5 (FB-126, FB-136), JSON to stdout. `files[]` classifies every compare-set file against the template's own blob history: `up_to_date`, `template_copy` (equal to an older template version of its path, with the `version` that introduced it; or, only when the template history is shallow and can't place it, to the content the sync-state sidecar recorded: `basis` `history`/`sidecar`), `modified` (matches no template version; `shared_lines` says how much of it appears in any template version) or `new`, plus the file's mode at the ref and whether the local mode agrees. Also: the compare set (`patterns.compare` = upstream `sync` patterns + project-added ones), retired sync patterns, retired template files (shipped as sync files or byte-identical to a template version, later deleted upstream), stale local `customize`/`ignore` lists (`manifest`: add / drop / resulting list, project-added entries kept), the sidecar's git state (`sidecar`: exists / gitignored / tracked), `history_complete` (false when a commit in the repository's `shallow` file is reachable from the ref; the sidecar is read only then) and synced files left uncommitted. Reads template history from `--template-repo` (default: the project repo, `template` remote fetched) at `--ref` (default `template/main`). Read-only: never fetches; `git status` runs with `GIT_OPTIONAL_LOCKS=0` | `commands/health-check.md` Part 5 Step 2 |
| `sync-apply.py` | Template-sync writer for `/health-check` Part 5 Step 4 (FB-136): **writes into the project's `.claude/`**. Takes its classification from `sync-check.py` (loaded from the same directory), then writes the selected compare-set files at `--ref` (`--status new,template_copy` and/or `--paths-from FILE`, the only way to include a locally modified file) with the template's file mode, sets `template_version` + `template_release_date` in `version.json` (only when a file's content was written, or when every compare-set file now equals the template and the local version differs; other bytes kept), rewrites the manifest's `sync` list (`--keep-pattern` keeps a retired pattern; `--manifest-lists` also updates `customize`/`ignore`), and leaves `.sync-state.json` holding exactly a `synced_hash` for every compare-set file that now equals the template (every other entry is dropped; other top-level keys are kept). Refuses a path that is not a regular file or whose parent directory resolves outside the project's `.claude/` (`failed`, exit `1`); a path outside the compare set is a usage error (exit `2`, nothing written), and so is a project root that has a `template-maintenance/` directory (the template repository itself), except with `--dry-run`. `--dry-run` prints the same JSON and writes nothing; a second run changes nothing. Does not remove retired files, edit `.gitignore`, stage, commit or fetch | `commands/health-check.md` Part 5 Step 4 |
| `dashboard-render.py` | **HTML render target (DEC-024):** deterministic render of the entire dashboard as a single read-only HTML file with inline-SVG visualizations (`--html`), and the canonical META `task_hash` (`--task-hash`: sha256 over sorted `{id}:{status}:{difficulty}:{owner}:{review}` rows, `review` = `1` when `user_review_pending` is truthy, else `0`). The Markdown modes (`--render`, `--tasks-section`) were hard-retired. | `support/reference/dashboard-regeneration.md` § "Script-First Rendering — HTML target" + § Regeneration Steps + § Section Display Rules + § Critical Path Generation |

**`dashboard-render.py` status:** the dashboard render target is HTML (DEC-024). `--html` emits the complete dashboard as a single read-only, offline, `file://`-openable HTML page — all visualizations are inline SVG rendered in Python (zero runtime/CDN deps). The Action Required "Needs you" card is fully script-rendered: mechanical rows from task JSON, decisions (one row per unresolved record, plus a single row naming every `recorded` agent decision awaiting ratification; META `decisions_recorded`), `feedback.md` and the sidecar, plus judgment rows from the sidecar's `augment_rows[]` as a final "Also Needs You" sub-section. Spec drift (FB-128): the renderer loads `compute_drift()` from the sibling `fingerprint.py` by path and uses it for META `drift_sections`, the footer, the pulse "drift" number and the Needs-you "Spec Drift" rows; if `fingerprint.py` is missing or the call fails, the page reads "drift unchecked" and everything else renders normally. Only Custom Views keeps a `<!-- CLAUDE: fill … -->` placeholder, which the orchestrator fills (with HTML) per `dashboard-regeneration.md § "Script-First Rendering — HTML target"`. Sidecar (`dashboard-state.json`) fields read: `section_toggles`, `user_notes`, `custom_views_instructions`, `phase_gates`, `audit_digest`, `augment_rows`. Read-only: the script never writes the sidecar or the HTML; the orchestrator performs all file writes. Pass `--now <ISO>` for deterministic output. **The script is required — there is no Markdown fallback.**

## Invocation contract

All scripts follow these rules:

- **Stdlib only, Python 3.10+.** No `pip install` required. Below 3.10 each script exits `2` naming the interpreter it found (macOS's `/usr/bin/python3` is 3.9).
- **Keep syntax 3.10-valid:** no backslashes, comments or reused quotes inside f-string `{…}` (3.12+ only). `tests/test_python_floor.py` compiles every script with a real 3.10, skipping when none is found (FB-120).
- **Read-only by default.** A script prints its result and the orchestrator writes where needed. Two scripts write, and each says so in its table row:
  - `persist-session-export.py` performs the inbox copy itself (the copy-with-rename is the operation that keeps failing — handing the `cp` back to the orchestrator would leave the failure surface in place, per FB-109). Its destination is the user-configured external `template_inbox_path`, never a `.claude/` path.
  - `sync-apply.py` is the one script that writes to `.claude/` paths: the template files the user included in a `/health-check` Part 5 sync, plus `version.json`, `sync-manifest.json` and `.sync-state.json` (FB-136: a sync is dozens of byte-exact file writes plus bookkeeping in three files, which is work for a script, not for prose steps). It writes only compare-set paths that `sync-check.py` lists, never follows a symlink out of `.claude/`, and `--dry-run` shows the result first.

  Both are orchestrator-invoked, never run from an `Agent` subagent, so neither conflicts with the DEC-004 subagent-write constraint.
- **Stdout: machine-parseable** (JSON or newline-delimited records).
- **Stderr: human-readable diagnostics.**
- **Exit codes:** `0` = success, `1` = validation failure (for `sync-apply.py`: some selected files could not be written, listed in `failed`; everything else was applied), `2` = runtime/usage error (for `sync-apply.py`, nothing is written, with one exception: an I/O error writing `version.json`, the manifest or the sidecar exits `2` after file writes may have landed; a re-run finishes the bookkeeping).
- **`--help`:** every script supports `--help`.

## When to invoke

Scripts are **advisory**. Prose procedures in reference docs remain the source of truth (`sync-apply.py` included: Part 5 Step 4 keeps a prose fallback). Use scripts when:

- Running inside the orchestrator (not a subagent — subagents lack `.claude/` write capability; the prose procedure works without the script).
- Token cost of LLM-executed computation matters (many calls per session).
- Output consistency matters (drift detection depends on deterministic hashes).

If a script is absent or fails, fall back to the prose procedure.

## Agent invocation

- **Orchestrator (main `/work` loop):** invoke freely via the Bash tool.
- **Subagents:** do not invoke. Subagents cannot write to `.claude/`, so the output has nowhere to go; the orchestrator is the right caller.
- **`claude -p`:** suitable for CI-style use. Use `--allowedTools "Bash(.claude/scripts/* *)"` to scope.

## Dual-location risk

Each script mirrors a reference doc. When a reference doc changes, the matching script must change in lockstep — otherwise the script's output diverges from what the prose promises. Before editing the recipe in a reference doc, search for script call sites and update both.

Candidate follow-up: `task-schema.json` as a single machine-readable source of truth, eliminating the dual-edit risk for `validate-tasks.py`. Deferred pending user decision.

## Testing

Tests live in `.claude/scripts/tests/`. Run from the repo root:

```bash
python3 -m unittest discover .claude/scripts/tests/
```

Coverage is intentionally lightweight — happy-path + key error modes per script. The intent is to catch field-name drift (the FB-039 class of bug) and obvious regressions in CLI behavior. Not a substitute for the dual-edit discipline in § "Dual-location risk".
