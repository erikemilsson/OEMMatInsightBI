# .claude/scripts

Deterministic helpers invoked by the `/work` orchestrator (or by the user directly) when LLM-executed computation has unacceptable drift or token cost.

## Scripts

| Script | Purpose | Mirrors |
|--------|---------|---------|
| `fingerprint.py` | Spec/section/dashboard-rollup SHA-256 hashes; `--index` (spec section index for scoped reads, DEC-021) + `--sections --depth 3` (additive `### ` subsection hashes) | `support/reference/drift-reconciliation.md`, `rules/spec-workflow.md § "Section-scoped spec reading"`, `commands/status.md` |
| `validate-tasks.py` | Task JSON schema validation + verification debt count | `support/reference/task-schema.md`, `commands/health-check.md` Part 1 |
| `persist-friction.py` | Friction-marker dual-write payload + collision-safe `FR-NNN` ids from a marker batch (read-only; orchestrator appends) | `support/reference/work-procedures.md § "State Persistence Protocol"` step 2, `support/reference/friction-register.md § "Write protocol"` |
| `dashboard-render.py` | **Family C full port (v4.22.0):** deterministic render of all structural dashboard sections (`--render`), the Tasks section alone (`--tasks-section`, archive-aware), and the canonical META `task_hash` (`--task-hash`) | `support/reference/dashboard-regeneration.md` § "Script-First Rendering" + § Regeneration Steps 3–6 + § Section Display Rules + § Critical Path Generation + § Project Overview Diagram |

**`dashboard-render.py` status:** full port WIRED into the regeneration flow (v4.22.0, user decision 2026-06-11 on the PoC evidence run). `--render` emits the complete dashboard with `<!-- CLAUDE: fill … -->` placeholders for the synthesis sections (Action Required, Custom Views content); the orchestrator writes the output and fills the placeholders per `dashboard-regeneration.md § "Script-First Rendering"`. Read-only: the orchestrator performs all file writes. Pass `--now <ISO>` for deterministic output. The prose procedure remains the complete hand-render fallback when python3 is unavailable.

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
