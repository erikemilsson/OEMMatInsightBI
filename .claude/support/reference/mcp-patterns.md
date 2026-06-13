# MCP Patterns

Operational constraints for MCP servers — parallel-execution safety and result-size limits. Moved from `.claude/rules/agents.md` in v4.16.0 to keep the always-loaded rules payload lean; the rules file keeps trigger stubs under the same section names. **Read this before dispatching parallel batches that involve MCP-driving work, or before driving a browser MCP on large pages.**

## MCP and Parallel Execution

Single-session MCP servers cannot be safely fanned out across parallel subagents. Servers that expose stateful single-instance resources — Playwright MCP (one browser session), browser-automation MCPs, auth-session MCPs, connection-pooled MCPs — share their underlying state across all concurrent calls. Two parallel subagents calling the same MCP drive the **same** tab / session / connection; navigations, clicks, snapshots, and reads interleave silently. The failure mode is invisible — snapshots look fine but reflect another agent's mid-action state.

**Orchestrator pattern when a parallel batch involves MCP-driving work:**

1. **Route MCP-driving work through one agent.** Dispatch a single agent to handle all calls to the shared MCP (e.g., one Playwright agent for all UI inspection across routes).
2. **Parallelize the rest.** Other agents in the same batch do code reads, greps, test runs — anything that doesn't touch the shared MCP server.
3. **For multi-route inspection.** Dispatch sequential agents with focused scopes ("audit /coloring", then "audit /wardrobe"), not a parallel batch driving the browser.

True parallel browser inspection would require multiple MCP server instances on different ports or `user-data-dir`s — not how the template ships and not trivial to set up. Out of scope for most projects.

**Detection (lower priority):** `/work` Step 2c parallel-batch heuristic currently keys on `files_affected` only. It could be extended to check `mcp_resource_overlap` (any pair of tasks both expected to use the same single-instance MCP server) — same dispatch site as `shared_contract` detection in `parallel-execution.md`. Tracked separately if it becomes a recurring foot-gun.

## MCP and Result-Size Constraints

Playwright MCP `browser_snapshot` returns the full accessibility tree of the current page. For long-scroll pages or sites with many sections (over ~10K characters of DOM), the result can exceed the model's per-tool-call token budget and truncate silently — the snapshot appears empty or partial without an error.

For audits and verifications that only need specific elements, prefer `browser_evaluate` with targeted DOM queries (e.g., `document.querySelectorAll('h2').map(h => h.textContent)`). Reserve `browser_snapshot` for small pages or when you genuinely need the full tree.

The same pattern applies to other MCP servers that return large result objects: prefer targeted queries over full-state dumps when the task only needs specific data.

## See Also

- `.claude/support/reference/parallel-execution.md` — the full parallel-dispatch procedure these constraints bound
- `.claude/support/reference/claude-code-authoring.md § "MCP Constraints"` — capability-fact cross-links for spec/skill authors
- `.claude/commands/diagnose.md § "Visual / browser-rendering bugs"` — the measurement recipe that applies the result-size rule
