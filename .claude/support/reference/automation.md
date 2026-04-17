# Automation

Reference for users who want to automate template workflows or run Claude Code non-interactively. Covers two complementary tools: the `claude -p` primitive (a single prompt, no session) and the fan-out pattern (many `claude -p` calls in parallel for batch workloads).

**Scaling axes.** The template's parallel execution is *intra-session*: one `/work` orchestrator dispatches multiple `Task` agents in the same conversation, with file-conflict detection and verification gating. Automation is *inter-session*: many independent `claude` processes run outside any `/work` orchestrator. The two axes are complementary — use intra-session parallelism for spec-driven task batches (the default); use inter-session fan-out for very large or schedule-based workloads.

---

## `claude -p` — the automation primitive

Non-interactive mode runs a single prompt and exits. No session state, no dashboard, no `/work` — just prompt in, output out. It's the building block for CI checks, pre-commit hooks, scheduled jobs, and shell-driven batch pipelines.

**Basic form:**

```bash
claude -p "Summarize the changes in the last three commits."
```

**Structured output:**

```bash
claude -p "List all tasks with status Blocked." --output-format json
claude -p "Explain this code." --output-format stream-json
```

- `--output-format json` — single JSON response. Good for pipelines parsing a final answer.
- `--output-format stream-json` — newline-delimited events. Good for watching tool use in real time.

**Scoping tool permissions:**

```bash
claude -p "Regenerate the dashboard." --allowedTools "Read,Write,Grep"
claude -p "Commit the staged changes with a useful message." --allowedTools "Bash(git *)"
```

- `--allowedTools` restricts which tools the run may use. Use it aggressively for automation — an unattended run should not be able to touch tools you didn't intend.
- Tool patterns support globs (e.g., `Bash(git *)` allows any `git` subcommand via Bash but nothing else).

**Working-directory and model:**

```bash
claude -p "..." --cwd /path/to/project --model claude-opus-4-7
```

### When to reach for `claude -p`

| Scenario | Fits `claude -p`? |
|----------|-------------------|
| Nightly `/health-check` run in CI | Yes — scheduled, no user sitting there |
| Pre-commit hook that checks for TODOs in staged files | Yes — one-shot, structured response |
| Batch dashboard regen across many projects | Yes — use fan-out (below) |
| Interactive spec iteration with user | No — use `claude` / `/work` / `/iterate` |
| Anything that needs the handoff file or session history | No — `claude -p` has no session |

### When NOT to reach for `claude -p`

- The task requires conversational back-and-forth. `claude -p` is a single turn.
- The task must read the dashboard or task state AS IT EVOLVES. `claude -p` has no awareness of in-progress `/work` sessions.
- The task needs user approval. Non-interactive runs cannot prompt.

---

## Fan-out — parallel batch execution

When a workload is "same operation, many inputs," spawn many `claude -p` processes in parallel. This is how you scale past what one session (intra-session Task dispatch) can coordinate.

**Minimal pattern:**

```bash
for file in $(git ls-files '*.py'); do
  claude -p "Refactor $file to use the new logger API. Make one commit." \
    --allowedTools "Read,Edit,Bash(git add *),Bash(git commit *)" &
done
wait
```

**With a concurrency cap (prevents CPU/memory exhaustion):**

```bash
ls src/**/*.py | xargs -n 1 -P 4 -I {} \
  claude -p "Migrate {} to the new schema. Commit the change." \
  --allowedTools "Read,Edit,Bash(git add *),Bash(git commit *)"
```

- `-P 4` — four concurrent processes. Tune to your machine; 4–8 is a reasonable starting range.
- Each process runs independently — no shared session state.

### When fan-out fits

- **Large migrations** — "change every file like this" across hundreds of files.
- **Report generation** — "produce a summary for each row in this dataset."
- **Scheduled sweeps** — nightly validation across many project directories.

### When fan-out does NOT fit

- Tasks that interact with each other (one's output is another's input). Serial execution or intra-session `/work` is the right tool.
- Tasks that write to the same file. Concurrent writes without coordination corrupt state. Partition the work so each process owns its files.
- Tasks that require `.claude/` task-JSON updates or dashboard regeneration. `.claude/` writes in a fan-out are uncoordinated and will race.

### Coordination at the boundary

Fan-out workers should each produce an artifact (a commit, a file, an output line). The main process collects artifacts after `wait`. Do NOT have workers update shared state mid-run.

**Good pattern:**
```bash
for file in $(...); do
  claude -p "Process $file. Write result to out/$(basename $file).json." ... &
done
wait
# Now collect results
cat out/*.json | jq -s '.' > summary.json
```

**Bad pattern:**
```bash
for file in $(...); do
  claude -p "Process $file and append to shared.log." ... &  # race: concurrent writes to shared.log
done
```

---

## Interaction with the template

- **Intra-session parallel execution** (`parallel-execution.md`) is the default for spec tasks. Use it when tasks are in the spec, file-conflict detection matters, and verification should happen per task.
- **Fan-out** is for ad-hoc or scheduled work outside the spec. Use it when the coordination overhead of `/work` is more than the job requires.
- **`claude -p`** is the building block for both ad-hoc automation and fan-out.

The template does NOT ship any fan-out scripts. This doc is reference for users who want to build their own.

## Related

- `.claude/support/reference/parallel-execution.md` — intra-session parallel Task dispatch (the `/work` orchestrator's path).
- `.claude/commands/health-check.md` — candidate for nightly `claude -p` automation.
- Claude Code docs — full `claude -p` CLI flag reference.
