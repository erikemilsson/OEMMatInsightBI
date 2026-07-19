# .claude/scripts

Deterministic helpers invoked by the `/work` orchestrator (or by the user directly) when LLM-executed computation has unacceptable drift or token cost.

## Scripts

| Script | Purpose | Mirrors |
|--------|---------|---------|
| `fingerprint.py` | Spec/section/dashboard-rollup SHA-256 hashes; `--index` (spec section index for scoped reads, DEC-021) + `--sections --depth 3` (additive `### ` subsection hashes) | `support/reference/drift-reconciliation.md`, `rules/spec-workflow.md § "Section-scoped spec reading"`, `commands/status.md` |
| `validate-tasks.py` | Task JSON schema validation + verification debt count | `support/reference/task-schema.md`, `commands/health-check.md` Part 1 |
| `persist-friction.py` | Friction-marker dual-write payload + collision-safe `FR-NNN` ids from a marker batch (read-only; orchestrator appends) | `support/reference/work-procedures.md § "State Persistence Protocol"` step 2, `support/reference/friction-register.md § "Write protocol"` |
| `dashboard-render.py` | **HTML render target (DEC-024):** deterministic render of the entire dashboard as a single read-only HTML file with inline-SVG visualizations (`--html`), and the canonical META `task_hash` (`--task-hash`). The Markdown modes (`--render`, `--tasks-section`) were hard-retired. | `support/reference/dashboard-regeneration.md` § "Script-First Rendering — HTML target" + § Regeneration Steps + § Section Display Rules + § Critical Path Generation |

**`dashboard-render.py` status:** the dashboard render target is HTML (DEC-024). `--html` emits the complete dashboard as a single read-only, offline, `file://`-openable HTML page — all visualizations are inline SVG rendered in Python (zero runtime/CDN deps) — with `<!-- CLAUDE: fill … -->` HTML-comment placeholders for the synthesis sections (Action Required "Needs you" card, Custom Views content); the orchestrator writes the output and fills the placeholders (with HTML) per `dashboard-regeneration.md § "Script-First Rendering — HTML target"`. Read-only: the orchestrator performs all file writes. Pass `--now <ISO>` for deterministic output. **The script is required — there is no Markdown fallback.**

## Invocation contract

All scripts follow these rules:

- **Stdlib only.** Python 3.10+ assumed. No `pip install` required.
- **Read-only by default.** None of these scripts write to `.claude/` paths. Orchestrator captures stdout and writes where needed.
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
