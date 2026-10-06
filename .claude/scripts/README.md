# .claude/scripts

Deterministic helpers invoked by the `/work` orchestrator (or by the user directly) when LLM-executed computation has unacceptable drift or token cost.

## Scripts

| Script | Purpose | Mirrors |
|--------|---------|---------|
| `fingerprint.py` | Spec/section/dashboard-rollup SHA-256 hashes; `--index` (spec section index for scoped reads, DEC-021) + `--sections --depth 3` (additive `### ` subsection hashes); `--drift .claude` (per-task spec drift check as JSON: each task's section fingerprint against the current spec, grouped by section with deferrals applied; computed fresh, never cached; library function `compute_drift()`, FB-128) | `support/reference/drift-reconciliation.md § "Spec Drift Detection"`, `rules/spec-workflow.md § "Section-scoped spec reading"` |
| `validate-tasks.py` | Task JSON schema validation + verification debt count | `support/reference/task-schema.md`, `commands/health-check.md` Part 1 |
| `persist-friction.py` | Friction-marker dual-write payload + collision-safe `FR-NNN` ids from a marker batch (read-only; orchestrator appends) | `support/reference/work-procedures.md § "State Persistence Protocol"` step 2, `support/reference/friction-register.md § "Write protocol"` |
| `persist-session-export.py` | Session-export inbox copy-with-rename — writes the inbox file with a deterministic, never-dot-prefixed `{slug}-session-export-{ts}{suffix}.json` name (FB-109; the one shipped script that writes a file — the inbox path is external/user-configured, never `.claude/`) | `support/reference/context-transitions.md § "Session Export"` step 6, `commands/work.md § "Step 0f"` step 8 (pass `--suffix recovered`) |
| `sync-check.py` | Template-sync check for `/health-check` Part 5 (FB-126), JSON to stdout: the compare set (`patterns.compare` = upstream `sync` patterns + project-added ones), retired sync patterns, retired template files (shipped as sync files or byte-identical to a template version, later deleted upstream) and synced files left uncommitted. Reads template history from `--template-repo` (default: the project repo, `template` remote fetched) at `--ref` (default `template/main`). Read-only: never fetches; `git status` runs with `GIT_OPTIONAL_LOCKS=0` | `commands/health-check.md` Part 5 Step 2 |
| `dashboard-render.py` | **HTML render target (DEC-024):** deterministic render of the entire dashboard as a single read-only HTML file with inline-SVG visualizations (`--html`), and the canonical META `task_hash` (`--task-hash`: sha256 over sorted `{id}:{status}:{difficulty}:{owner}:{review}` rows, `review` = `1` when `user_review_pending` is truthy, else `0`). The Markdown modes (`--render`, `--tasks-section`) were hard-retired. | `support/reference/dashboard-regeneration.md` § "Script-First Rendering — HTML target" + § Regeneration Steps + § Section Display Rules + § Critical Path Generation |

**`dashboard-render.py` status:** the dashboard render target is HTML (DEC-024). `--html` emits the complete dashboard as a single read-only, offline, `file://`-openable HTML page — all visualizations are inline SVG rendered in Python (zero runtime/CDN deps). The Action Required "Needs you" card is fully script-rendered: mechanical rows from task JSON, decisions, `feedback.md` and the sidecar, plus judgment rows from the sidecar's `augment_rows[]` as a final "Also Needs You" sub-section. Spec drift (FB-128): the renderer loads `compute_drift()` from the sibling `fingerprint.py` by path and uses it for META `drift_sections`, the footer, the pulse "drift" number and the Needs-you "Spec Drift" rows; if `fingerprint.py` is missing or the call fails, the page reads "drift unchecked" and everything else renders normally. Only Custom Views keeps a `<!-- CLAUDE: fill … -->` placeholder, which the orchestrator fills (with HTML) per `dashboard-regeneration.md § "Script-First Rendering — HTML target"`. Sidecar (`dashboard-state.json`) fields read: `section_toggles`, `user_notes`, `custom_views_instructions`, `phase_gates`, `audit_digest`, `augment_rows`. Read-only: the script never writes the sidecar or the HTML; the orchestrator performs all file writes. Pass `--now <ISO>` for deterministic output. **The script is required — there is no Markdown fallback.**

## Invocation contract

All scripts follow these rules:

- **Stdlib only, Python 3.10+.** No `pip install` required. Below 3.10 each script exits `2` naming the interpreter it found (macOS's `/usr/bin/python3` is 3.9).
- **Keep syntax 3.10-valid:** no backslashes, comments or reused quotes inside f-string `{…}` (3.12+ only). `tests/test_python_floor.py` compiles every script with a real 3.10, skipping when none is found (FB-120).
- **Read-only by default.** None of these scripts write to `.claude/` paths. Orchestrator captures stdout and writes where needed. The single exception is `persist-session-export.py`, which performs the inbox copy itself (the copy-with-rename is the operation that keeps failing — handing the `cp` back to the orchestrator would leave the failure surface in place, per FB-109). Its destination is the user-configured external `template_inbox_path`, never a `.claude/` path, so it does not violate the DEC-004 subagent-write constraint (it is orchestrator-invoked, never from an `Agent` subagent).
- **Stdout: machine-parseable** (JSON or newline-delimited records).
- **Stderr: human-readable diagnostics.**
- **Exit codes:** `0` = success, `1` = validation failure, `2` = runtime/usage error.
- **`--help`:** every script supports `--help`.

## When to invoke

Scripts are **advisory**. Prose procedures in reference docs remain the source of truth. Use scripts when:

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
