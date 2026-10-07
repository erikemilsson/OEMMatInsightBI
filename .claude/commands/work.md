---
disable-model-invocation: true
---

# Work Command

The intelligent entry point for all project work. Handles spec-checking, state detection, task decomposition, task completion, and routing to specialist agents.

For workflow concepts (phases, agent synergy, checkpoints), see `.claude/support/reference/workflow.md`.

## Usage
```
/work                    # Auto-detect what needs doing
/work {task-id}          # Work on specific task
/work {request}          # Handle ad-hoc request
/work complete           # Complete current in-progress task
/work complete {id}      # Complete specific task
/work pause              # Graceful wind-down — preserve context for next session
/work ratify             # List agent-recorded decisions awaiting ratification
/work ratify all         # Ratify every `recorded` decision
/work ratify DEC-NNN …   # Ratify the named decision(s)
/work reconsider DEC-NNN # Reopen an agent-recorded decision for a real selection
```

`ratify` and `reconsider` are sub-modes like `complete` and `pause`: when the first argument is one of them, run § "Decision Ratification" and stop — no routing.

## User Communication Strategy

**Tier 1 — full dashboard regeneration** at the strategic moments listed in `rules/dashboard.md § "Regeneration Strategy"` (decomposition, parallel batch end, session boundaries, `/work complete`, phase gates, decision resolution, Step 1a mismatch, drift reconciliation applied). **Tier 2 — inline CLI messages** for routine changes, no file I/O:

| Event | Inline message |
|-------|---------------|
| Task starts (In Progress) | `Starting task {id}: "{title}"` |
| Per-task verification passes | `Task {id} verified` + what's next |
| Per-task verification fails | `Task {id} verification failed: {summary}` |
| Human task becomes unblocked | `Note: Task {id} ("{title}") is now available for you — {brief description}` |
| Auto-continuation step | `Moving to task {id}: "{title}"` |

When implementation work unblocks a human- or both-owned task, say so inline during auto-continuation rather than leaving it for the dashboard.

---

## Process

### Step 0: Context Restoration and Session Recovery

#### Step 0 Preamble: Hazard Check

Before any execution decisions, check for known hazards.

```
1. Scan auto-memory for project-level warnings about dangerous operations
   (dev server crashes, resource-intensive builds, known environment issues)

2. Read .claude/support/reference/known-issues.md if it exists
   Match entries against the project's tech stack and directory layout

3. Store relevant hazards in working context as known_hazards[]
   These are consulted in Step 4 before spawning agents.
```

This is a lightweight read — negligible overhead, prevents repeating known-dangerous operations.

#### Step 0a: Handoff Detection

Check for a context transition handoff from a previous session before anything else.

```
1. Check for .claude/tasks/.handoff.json
   IF not found → skip to Step 0b

2. Read and validate handoff file
   IF invalid JSON or missing required fields → warn, delete, skip to Step 0b

3. Check staleness
   IF timestamp > 7 days old:
     → "Handoff from {date} — project state may have changed. Reference only."
     → Delete handoff, skip to Step 0b (don't use for routing)

4. Present summary (2-4 lines):
   "Resuming from previous session ({trigger}, {relative time}):
    {task titles + progress from position/active_work}"

5. Load session_knowledge into working context
   (Available for routing and implement-agent enrichment. NOT passed to verify-agent.)

6. Delete .handoff.json
   EXCEPTION — concurrent session (FB-104): if the handoff's active task(s)
   have CHANGED STATUS since the handoff timestamp (another session is
   progressing them), do NOT consume-and-delete. Preserve the file, use it
   read-only for orientation, flag "Handoff appears to belong to a concurrent
   session — preserved", and reconcile/merge at the next pause.

7. Proceed to Step 0b
```

**Full procedure:** `.claude/support/reference/context-transitions.md` § "Restoration"

#### Step 0a2: Plan File Discovery

Check for workspace plan files from a previous session.

```
1. Glob for .claude/support/workspace/plan-*.md
   IF no matches → skip to Step 0b

2. For each plan file, check modification time
   IF older than 7 days → skip (stale)

3. Present discovered plans:
   "Found plan file(s):
    - plan-{topic}.md ({relative time ago})
   
   [E] Execute plan | [I] Inspect first | [S] Skip"

4. IF [E]: Read plan file, use as primary work directive
      (overrides auto-detect routing in Step 3)
   IF [I]: Display plan contents, then re-prompt [E] or [S]
   IF [S]: Continue to Step 0b (plan remains on disk for later)
```

**Plan files are not auto-deleted** — unlike handoff files, they persist until the user removes them. This allows re-reading and editing across multiple sessions.

#### Step 0b: Session Recovery Check

Check for tasks left in recoverable states by a previous session. Read `.claude/support/reference/session-recovery.md` and follow its procedure:
1. **Check session sentinel** (`.claude/tasks/.last-clean-exit.json`) — if clean exit, skip full scan
2. **If sentinel missing or stale** — run full recovery scan (7-case logic in the reference file)
3. **After recovery actions complete** — proceed to Step 1

**Malformed files during scan:** If a task file fails to parse during Step 0, skip it and continue. Report the error in Step 1.

#### Step 0c: Session Start Summary

When Step 0a found no handoff and Step 0b found no recovery issues (clean start), produce a brief orientation summary:

1. Read dashboard `<!-- DASHBOARD META -->` block for the `generated` timestamp
2. Scan task files for:
   - Tasks with `completion_date` within the last 48 hours → recent completions
   - Tasks with `status: "In Progress"` → active work
   - Tasks with `owner: "human"` or `"both"`, status `"Pending"`, all dependencies `"Finished"` → next human actions
3. Output (3-5 lines):
   ```
   Last session: {relative time from dashboard generated timestamp}
   Recent: {completed task titles, or "no recent completions"}
   Active: {in-progress task titles, or "none"}
   Your next actions: {human/both tasks ready with IDs, or "none — all human tasks complete"}
   ```
4. Proceed to Step 1

**First-run fallback:** If no dashboard META block exists (first `/work` invocation), skip the summary — Step 1 will handle first-run detection.

#### Step 0d: Friction-Marker Catchup

If `.claude/support/workspace/.pending-markers.jsonl` exists and is non-empty, read `.claude/support/reference/work-recovery.md § "Friction-Marker Catchup"` and follow it before any agent dispatch (reconciles markers a prior session buffered but never wrote to the canonical log, DEC-011). Otherwise skip.

#### Step 0e: Uncommitted-Work Check (FB-088)

Detect silent drift between "tasks marked Finished" and "code committed". Runs once per `/work` invocation, before any agent dispatch.

**Procedure:**

1. If `git rev-parse --is-inside-work-tree` doesn't print `true` (the project isn't in a git work tree), this step is a no-op — proceed to Step 0f. Don't test for `.git` in the project root: a project nested in a larger repository has none, and Step 4's commands still work there, relative to the project root.
2. Run `git log -1 --format=%ct HEAD` to get last-commit Unix timestamp. If the command fails (no commits in repo), skip Step 0e — proceed to Step 0f.
3. Convert timestamp to YYYY-MM-DD format (last-commit date).
4. Compute working-copy state from the project root, so both commands list paths relative to it (git's native gitignore handling does the `.claude/` scoping — see note below):
   - `MODIFIED = git diff --name-only --relative HEAD` (tracked files only — gitignored `.claude/` state never appears here)
   - `UNTRACKED = git ls-files --others --exclude-standard` (`--exclude-standard` omits gitignored paths)
5. Count `finished_uncommitted`: tasks with `status == "Finished"`, `completion_date >= last-commit-date`, and at least one `files_affected` entry matching a path in MODIFIED ∪ UNTRACKED. An entry matches a path when it is that path, a directory entry ending `/` that contains it, or a glob that matches it (`**` crosses `/`; `*` and `?` don't; every other character, `[` included, is literal).
6. If `finished_uncommitted < 3` OR MODIFIED and UNTRACKED are both empty: silent, proceed to Step 0f.
7. Else surface inline, with `{N}` = `finished_uncommitted`, `{M}` = len(MODIFIED), `{K}` = len(UNTRACKED):
   - Default form: `Step 0e: {N} finished tasks have uncommitted changes in their files ({M} files modified, {K} untracked). Consider committing before continuing. Use \`git status\` to inspect.`
   - Post-handoff form (when Step 0a just deleted a handoff): `Step 0e: {N} finished tasks have uncommitted changes in their files (prior session paused without committing). Consider committing before resuming work.`
8. Always proceed to Step 0f (never block).

The file match is needed because `completion_date` is only a date: tasks finished and committed earlier the same day have clean files, so they no longer count.

Rely on git's own gitignore handling for `.claude/` — don't add a blanket `.claude/` filter (projects that track `.claude/` files should see them counted; FB-099).

#### Step 0f: Track 2 Stale-File Recovery

If `.claude/support/workspace/.interaction-assessment.json` exists (a prior `/work pause` was interrupted), read `.claude/support/reference/work-recovery.md § "Stale Track 2 Recovery"` and follow it before continuing: it compiles a recovered session export and removes the stale file, which would otherwise make the next Write to that path fail. Otherwise skip.

#### Step 0g: Waiting-on-You Queue (always runs)

Enumerate every item currently gated on the user and surface it before routing. This is the session-start half of the **human-gated coverage invariant** (`rules/dashboard.md § Sections`): nothing blocked on the user may live only in handoff prose.

1. Scan task files for the card's Your Tasks set (`dashboard-regeneration.md § "Section Display Rules"`): status `"On Hold"`; Finished with `user_review_pending: true` (any owner); `"Blocked"` with owner `human`/`both` or `verification_attempts` ≥ 3; unfinished `owner: "human"` (not Broken Down) with all dependencies `"Finished"`. This scan reads every task file on every run, so also: a Finished task with a non-empty `decisions_pending` had its record write interrupted — run "Persist decisions" for it now (`work-procedures.md § "State Persistence Protocol"`).
2. Scan `.claude/support/decisions/decision-*.md` for unresolved records (status `proposed`/`draft` — a selection is awaited). Records with status `recorded` are resolved but unratified: list them together as one item (`{N} agent decision(s) await ratification: {ids} → /work ratify all`); the script derives their card row, so no augment row is needed. A `draft`/`proposed` record whose `## Select an Option` box is already ticked is listed as "ticked — approved this run" instead; Step 1d's checkbox scan approves it.
3. Read sidecar `augment_rows[]` in `.claude/dashboard-state.json`: each unexpired action row is an item (expiry: `dashboard-regeneration.md § "Augment Rows"`), folded into its task's line when its `task_id` names a task from step 1. If a handoff was consumed in Step 0a, also extract any questions asked of the user last session that were never answered (mid-decision pauses) and no row already carries.
4. Output, merged into Step 0c's summary when both fire (skip the block entirely when N == 0):
   ```
   Waiting on you ({N}):
   1. {item} — {concrete question or action} → {file link}
   ...
   ```
5. **Dashboard cross-check:** every item found must have a 🚨 Action Required ("Needs you") item with the question/action inline. If any are missing, regenerate `dashboard.html` (a full regen is cheap, and the script re-derives every mechanical row) so the queue is complete. Unanswered questions from a paused session are judgment rows: make sure each is in sidecar `augment_rows[]` (add missing ones, prune answered ones) before that regen — never edit the HTML (`dashboard-regeneration.md § "Augment Rows"`).

### Step 1: Gather Context

**Version discovery:** Determine the current spec version:
```
1. Glob for .claude/spec_v*.md
2. Parse version numbers from filenames
3. Use the highest N as the current spec
4. If zero matches → no spec exists
5. If multiple matches → use highest, flag anomaly (should be exactly one)
```

Read and analyze:
- `.claude/spec_v{N}.md` - The specification (source of truth)
- `.claude/dashboard.html` - Task status and progress (read the `<!-- DASHBOARD META -->` comment in the `<head>`)

**Steps 1a and 1b run on every `/work`;** each is one script call, and nothing skips them (FB-128). Always check `drift-deferrals.json` too: an over-budget or expired deferral triggers Drift Reconciliation even when Step 1b finds no new drift.

**Malformed task file handling:** When reading task JSON files, if any file fails to parse:
1. Skip the file — do not abort the entire scan
2. Report the error prominently: "Task file `task-{id}.json` could not be read: {error}. Run `/health-check` for details."
3. Exclude the corrupted file from all calculations
4. If other tasks depend on the corrupted task, treat those dependencies as unresolvable (task effectively Blocked)

### Step 1a: Dashboard Freshness Check

**Pending-decomposition check first (FB-106).** Before the freshness checks, read `pending_decomposition[]` from `.claude/dashboard-state.json`. For each listed `## ` heading, check whether any task references it (`spec_section`). If a section has **zero** referencing tasks, surface it and offer decomposition:

```
Spec section "{heading}" was added by /iterate and has no tasks yet.
[D] Decompose it now | [S] Skip this session | [X] Drop it from the queue (not buildable yet)
```

Remove a heading from the array once it has referencing tasks or the user picks `[X]`. This check comes first because the drift check (Step 1b) can't see a new section: no task references it, so nothing in it can drift, and `/work` would route to an unrelated pending task. (This marker supersedes the interim pause carve-out in § "Context Transition" — with `pending_decomposition[]` present, regenerating at pause is safe again.)

Verify the dashboard is current before using its data. Compute the canonical `task_hash` (`python3 .claude/scripts/dashboard-render.py --task-hash`; its rows include each task's review flag) and compare against the dashboard's `<!-- DASHBOARD META -->` block. Regenerate the dashboard from task JSON files before continuing if the hash differs, if META `spec_fingerprint` ≠ the current spec hash (`python3 .claude/scripts/fingerprint.py --spec .claude/spec_v{N}.md`), or if no metadata exists. META `spec_fingerprint` records the spec the dashboard was rendered from; it is not evidence that drift was checked.

Also compare `template_version` in the META block against `template_version` in `.claude/version.json`. If they differ or the META field is absent, the dashboard was generated with older format rules and should be regenerated (see dashboard-regeneration.md § "Format Staleness"). **Migration (DEC-024):** if a legacy Markdown `.claude/dashboard.md` is present, migrate its `<!-- USER SECTION -->` / `<!-- SECTION TOGGLES -->` / `<!-- CUSTOM VIEWS INSTRUCTIONS -->` content into the sidecar, delete it, and regenerate `dashboard.html`. Likewise, before regenerating over hand-inserted rows at an old `<!-- CLAUDE: augment -->` comment (pre-FB-118), move the still-relevant ones into sidecar `augment_rows[]`.

**Full procedure:** `.claude/support/reference/drift-reconciliation.md` § "Dashboard Freshness Check"

### Step 1b: Spec Drift Detection

Run `python3 .claude/scripts/fingerprint.py --drift .claude` (read-only; JSON on stdout). It compares each task's `section_fingerprint` with the current hash of the section it names:
- `unreconciled_sections` > 0 → Drift Reconciliation (after Step 1c). Tasks marked `subsection_unchanged` are shown as "likely unaffected", never dropped (DEC-021; `drift-reconciliation.md § "Subsection-level drift narrowing"`).
- `unmigrated` non-empty → Task Migration (Drift Reconciliation step 2).
- `unreadable` → report each file per the malformed-file rule above.
- A non-zero `no_provenance` for a task created this session → that task was written without provenance: add it now per the creation contract (`task-schema.md § "Drift Prevention Fields"`). Older ones are `/health-check` Part 1 check 11's.
- No script → apply the prose rules in `drift-reconciliation.md § "Spec Drift Detection"` (this reads every task JSON).

**Spec index refresh (DEC-021):** if `.claude/spec_v{N}.index.json` is missing or its `spec_fingerprint` ≠ the drift JSON's `spec_fingerprint` (the current full-spec hash), regenerate it: `python3 .claude/scripts/fingerprint.py --index .claude/spec_v{N}.md > .claude/spec_v{N}.index.json`. The index powers section-scoped spec reads (`rules/spec-workflow.md § "Section-scoped spec reading"`); it carries no task provenance, so this never affects drift reconciliation. Full rule: `drift-reconciliation.md § "Spec Index Freshness"`.

**Full procedure:** `.claude/support/reference/drift-reconciliation.md` § "Spec Drift Detection"

### Step 1c: Spec State Summary

After drift detection completes, output a brief status line (`u` = the drift JSON's `unreconciled_sections`, `d` = active drift deferrals):

```
If no tasks exist:
  "Spec: v{N} (draft) — no tasks yet"

If tasks exist, u == 0 and d == 0:
  "Spec: v{N} (active) — aligned with tasks ✓"
  "Tasks: {total} total ({finished} finished, {in_progress} in progress, {pending} pending{, N on hold}{, N absorbed})"

If tasks exist and u > 0 or d > 0:
  "Spec: v{N} (active) — ⚠️ {u} changed spec section(s), {d} drift deferral(s)"
  "Tasks: {total} total ({finished} finished, {in_progress} in progress, {pending} pending{, N on hold}{, N absorbed})"

If the drift JSON's `unmigrated` list is non-empty (open tasks on an older spec version):
  "Spec: v{N} (draft) — new version, tasks reference v{N-1}"
  "Tasks: {total} total — migration needed (see below)"
```

### Drift Reconciliation (if triggered)

Runs after Step 1c and before Step 1d when Step 1b reports unreconciled drift or `unmigrated` tasks, or a deferral is over budget or expired. It can create actionable work (reset or re-verify), so Step 1d waits for it. Each check delegates to `drift-reconciliation.md`:

1. **Substantial change detection** — evaluates change magnitude, may suggest version bump. § "Substantial Change Detection"
2. **Task migration** (version transitions only) — migrates task provenance to new spec version, then re-runs `--drift`. § "Task Migration on Version Transition"
3. **Drift budget enforcement** — checks deferred reconciliations against limits. § "Drift Budget Enforcement"
4. **Granular reconciliation UI** — with 2+ drifted sections, a batch prompt first: `[E]` Go through each section | `[K]` Keep all (all-Finished sections only; a section with open tasks is marked and always gets its own prompt). Per section, Claude recommends one option and the user picks: `[A]` Apply (reset Finished tasks to Pending), `[V]` Re-verify (no rebuild), `[K]` Keep verification, `[R]` Review individually, `[S]` Skip (defer); `[A]` and `[V]` also update open tasks. Open tasks whose section left the spec go through `[D]`/`[O]`/`[R]` per task. § "Granular Reconciliation UI"

**Post-reconciliation In Progress warning:** After reconciliation completes, check if any "In Progress" tasks had their section fingerprints updated. If so, warn:

```
⚠️ Task {id} "{title}" is In Progress but its spec section changed during reconciliation.
  Review the task's partial work against the updated requirements before continuing.
```

**Then regenerate the dashboard** if any choice wrote a task file or `drift-deferrals.json` (Tier-1 trigger: drift reconciliation applied). `task_hash` covers neither fingerprints nor deferrals, so Step 1a can't catch it.

### Step 1d: Non-Actionable State Fast Path (auto-detect only)

After Step 1c and Drift Reconciliation, check whether the project state has any Claude-actionable work. This avoids running the full analysis pipeline (Steps 2, 2b, 2c, 3) when there's nothing for Claude to do.

First run Step 2b's checkbox detection (§ "Required inline trigger — checkbox detection on every entry"), so a decision the user ticked since the last run is approved before the decision clause below counts it as unresolved. Step 2b's own scan still runs; it's idempotent.

**Preconditions (all must be true):**
- Auto-detect mode (no user request or task ID provided)
- Tasks exist (not first run / decomposition needed)
- Spec exists and is complete
- No tasks in `"In Progress"` status (active work exists)
- No tasks in `"Awaiting Verification"` status (verification takes priority)
- No unverified Finished tasks (verification debt takes priority)
- No unreconciled spec drift (Drift Reconciliation, which now runs before Step 1d, leaves `unreconciled_sections` at 0)

**Remaining tasks** = spec tasks where status NOT IN (`"Finished"`, `"Absorbed"`, `"Broken Down"`, `"In Progress"`)

```
IF remaining_tasks is NOT empty
   AND every task in remaining_tasks satisfies at least one of:
     - owner == "human" (regardless of status)
     - status == "Blocked"
     - status == "On Hold"
     - an unresolved decision dependency (a `decision_dependencies` entry
       whose record is missing or has status `draft`/`proposed`; `recorded`
       is resolved and never makes a task wait)
   → FAST EXIT
```

A both-owned task counts as non-actionable only when Blocked, On Hold or waiting on a decision: once Claude's half is delivered it is Finished with `user_review_pending` and out of `remaining_tasks` (a stale flag on unfinished work doesn't count). One waiting on a physical-world prerequisite should be `Blocked` or `On Hold`, not `Pending` (FB-100).

**Before presenting fast-exit output:** Verify dashboard freshness (same check as Step 5 item 4). If stale, regenerate first — the user may check the dashboard after seeing this message.

**Fast-exit output:**
```
No Claude-actionable work — {N} remaining tasks{: X human-owned, Y blocked, Z on hold, W waiting on decisions}.

{For each category present, a heading and one line per task:}
Your next actions:            - Task {id}: "{title}" — {brief description}
Blockers:                     - Task {id}: "{title}" — {blocker from notes}
On hold:                      - Task {id}: "{title}" — {reason from notes}
Waiting on decisions:         - Task {id}: "{title}" — waiting on {DEC-ID} → /research {DEC-ID}
```
A task waiting on a decision is listed only under `Waiting on decisions:`. This matches Step 2c, which already keeps such tasks out of batches.

After output, append 1-2 contextual command suggestions (see Contextual Command Suggestions below), then proceed to Step 5 (post-dispatch validation) — skip Steps 2, 2b, 2c, 3, and 4.

If the fast-exit conditions aren't met, proceed to Step 2.

### Step 2: Spec Check (if request provided)

When the user provides a request or task:

```
Check request against spec:
├─ Clearly aligned → Proceed
├─ Minor/trivial addition → Proceed (no spec change, no formal planning)
└─ Significant but not in spec → Surface it:
   "This isn't covered in the spec. Options:
    1. Add to spec: [suggested addition]
    2. Proceed anyway (won't be verified against spec)
    3. Skip for now"
```

**Skip formal planning for trivial requests:** If the diff for the request fits in one sentence (typo fix, log line addition, variable rename, single import update), dispatch implement-agent directly — do not route through `/research`, decision records, or task decomposition. The "Minor/trivial addition" branch above is the entry point. The principle: planning overhead should be proportional to scope.

**If user selects "Proceed anyway":**
- Create task with `"out_of_spec": true` (it needs no section provenance; creation contract: `task-schema.md § "Drift Prevention Fields"`)
- Dashboard shows ⚠️ prefix for these tasks
- Health check reports out-of-spec tasks separately

**Scope significance:** New features, architecture changes, new integrations, acceptance criteria changes = significant. Bug fixes, cleanup, small improvements = minor/trivial.

### Step 2b: Phase and Decision Gate

Check whether phases or unresolved decisions block any intended work.

Read `.claude/support/reference/phase-decision-gates.md` and follow its procedure. The reference file contains:
- Phase check (walking phases ascending, gate conditions)
- Decision dependency check (resolving checked boxes, auto-updating frontmatter)
- Late decision check (reverse cross-reference for new decisions)
- Post-decision check (inflection point handling)
- Early-exit conditions (skip when no phases or no decisions exist)

**Required inline trigger — checkbox detection on every entry:**

For every `decision-*.md` file with frontmatter `status: draft` or `proposed`:

1. Read the file's `## Select an Option` section
2. Scan for checked boxes — match `[x]`, `[X]`, `[✓]`, `[✔]` (per the normalization in `phase-decision-gates.md` § "Phase Check")
3. If a checked box is found AND frontmatter `status` is still `draft`/`proposed`:
   - Extract the selected option name (text after `[x] ` on the matched line)
   - Update frontmatter: `status: approved`, `decided: <today's YYYY-MM-DD>`. When the record has `decided_by: implement-agent` or `orchestrator` (a reconsidered agent decision), also add `ratified: <today>`: the tick is the user's confirmation; `decided_by` stays
   - For a reconsidered agent decision (`decided_by` set), first note the existing `**Selected:**` choice (the Post-Decision Check compares against it); then populate the Decision section using the option name and the matching Option Details rationale
   - Run the Post-Decision Check (`phase-decision-gates.md` § "Post-Decision Check") — handles inflection-point pause if applicable, and the follow-up-task offer for a reconsidered agent decision
   - Log: `Decision {DEC-ID} resolved → status updated to 'approved' (selected: {option_name})`
4. If no checked boxes are found across all `draft`/`proposed` decisions, proceed to the rest of Step 2b without changes.

This step MUST run on every Step 2b invocation. It is the caller's responsibility — `phase-decision-gates.md` defines the algorithm, but `/work` Step 2b is what fires it. Do not skip this scan even if other Step 2b checks suggest no new decisions.

**When a decision blocks work**, present options including research:
```
Decision {DEC-NNN}: "{title}" is unresolved and blocks Task {id}.
  [R] Research options (spawns research-agent to investigate; its findings populate the decision record)
  [S] Skip (you'll research manually — non-blocked tasks still dispatch normally)
```

**When Claude encounters an ambiguity or choice point** (not covered by an existing decision record), it must surface it to the user rather than deciding silently:
```
Ambiguity detected: {description of the choice point}
  [D] Create decision record (formal tracking)
  [I] Resolve inline (quick resolution, no formal record)
  [S] Skip for now
```
Claude must never resolve ambiguities autonomously. This applies during routing, spec checking, task dispatch, and any other step where Claude faces a choice the user hasn't explicitly decided.

If user selects `[R]`: if no decision record exists yet (e.g. a task's `decision_dependencies` names a DEC-NNN with no record file), first create one via `.claude/commands/research.md` Step 1's topic branch ("If a topic was provided"). Gather context (decision record, spec, related tasks/decisions), then spawn research-agent. See `.claude/commands/research.md` Steps 2-4 for the delegation flow. After research completes, re-present the decision for user selection. If user selects via checkbox, auto-update frontmatter per the phase-decision-gates procedure and continue.

If all checks pass → proceed to Step 2c.

### Step 2c: Parallelism Eligibility Assessment

After phase and decision checks, assess whether multiple tasks can be dispatched in parallel.

**Full procedure:** `.claude/support/reference/parallel-execution.md` § "Parallelism Eligibility Assessment"

**Summary:** Read `parallel_execution` from spec frontmatter (defaults: `enabled: true`, `max_parallel_tasks: 3`). Eligible tasks must be Pending, not human-owned, all deps Finished, in active phase (or `cross_phase: true`), all decision deps resolved, difficulty < 7. Build conflict-free batch by pairwise-comparing `files_affected`. If batch >= 2, set `parallel_mode = true`. After batch is built, scan for shared-scaffolding pairs and compose `shared_contract` payloads where applicable (see `parallel-execution.md` § "Shared Scaffolding Contracts") — prevents contradicting per-agent briefs when tasks share allowlists/fixtures.

### Step 3: Determine Action

**If a specific request was provided** (and passed spec check):
1. Create a task for the request (or find existing matching task). A new task gets provenance as it is written (creation contract: `task-schema.md § "Drift Prevention Fields"`): the fields from `python3 .claude/scripts/fingerprint.py --provenance .claude --section "<heading>"` for the spec section the request falls under, or `spec_unmapped: true` when it belongs to no single section
2. Route to the "If Executing" section in Step 4
3. Continue to Step 5 (validation)

**If no request provided** (auto-detect mode), stop early for these states first:

- No spec, no tasks → direct the user to create a vision in `.claude/vision/` and run `/iterate distill`
- No spec, tasks exist → **stop and warn** (tasks without a spec can't be verified): `[S]` Create spec | `[M]` Mark all out-of-spec | `[X]` Stop
- Spec incomplete → prompt the user to complete it
- Spec complete, no tasks → **Decompose** (Step 4)
- Phase transition pending approval → stop; approve the gate (enforced by Step 2b)

Otherwise route with the algorithm below. Per-task verification always outranks starting the next task, and no Finished task without a passing `task_verification` may reach phase-level verification or completion.

**Explicit routing algorithm:**
```
1. Get all spec tasks (exclude out_of_spec: true, exclude status "Absorbed")
2. awaiting_verification = tasks where status == "Awaiting Verification"
3. IF awaiting_verification is not empty:
   → Route to verify-agent (per-task) for first task
   → Do NOT proceed to phase-level or completion
4. finished_tasks = tasks where status == "Finished"
5. unverified_finished = finished_tasks where task_verification does not exist
6. IF unverified_finished is not empty:
   → Route to verify-agent (per-task) for first unverified task
7. ELSE IF all spec tasks are "Finished" AND all have passing verification:
   → Check verification-result.json
   → IF file missing → Route to verify-agent (phase-level)
   → IF result == "fail" → Route to implement-agent (fix tasks)
   → IF spec_fingerprint mismatch OR tasks updated after timestamp → Re-verify
   → IF result == "pass" → Route to completion
8. ELSE IF remaining pending tasks exist (status "Pending", all deps "Finished")
      AND all of them have owner == "human":
      → (Fallback for cases not caught by Step 1d fast path — e.g., when
         some tasks are Pending with unmet deps alongside human-ready tasks)
      → Do NOT dispatch an agent
      → Output: summary of human tasks ready + contextual command suggestions (see Contextual Command Suggestions below)
      → Proceed to Step 5 (post-dispatch validation) — skip Step 4
9. ELSE IF parallel_mode (from Step 2c):
   → Route to parallel execution
10. ELSE IF a pending task exists with owner != "human" AND all deps "Finished":
   → Route to implement-agent for that task
11. ELSE:
   → No eligible tasks — all remaining Claude-owned tasks have unmet dependencies.
   → Output: "No dispatchable tasks — {N} tasks remain but their dependencies aren't met yet."
   → List each blocked-by-dependency task with its unmet deps.
   → Proceed to Step 5 (post-dispatch validation) — skip Step 4
```

**Auto-continuation within phases:** After a task finishes (passes per-task verification), `/work` loops back to Step 3 to determine the next action — no user prompt, no pause. Each iteration starts with an inline announcement: `Moving to task {id}: "{title}"`. Before dispatching the next task, check if any human-owned or both-owned tasks just became unblocked — if so, mention them inline: `Note: Task {id} ("{title}") is now available for you — {brief description}`. This continues automatically until a natural stopping point: phase boundary (gate approval needed), blocking decision, verification failure requiring human escalation, or all remaining tasks non-actionable (human-owned, blocked, on hold, or waiting on a decision — see Step 1d). The value of front-loaded decomposition and structured verification is that work flows autonomously between these stops.

**Autonomous batch heartbeat (FB-081):** keep an in-memory `autonomous_batch_position`, +1 per sequential auto-continuation (parallel dispatches don't count); reset to 0 at any natural stopping point, any user message, or `/work` exit. At `>= 3`, replace the `Moving to task` line with `[Auto-batch: task {position} of {batch_total} — {task_id}: "{title}"]` (`batch_total` = sequential tasks projected for this batch). Heartbeats are inline only, never dashboard entries. For user messages mid-batch see `rules/agents.md § "Behavioral Rules"`.

**Important — spec tasks vs out-of-spec tasks:** Phase routing is based on spec tasks only (excluding `out_of_spec: true`). Out-of-spec tasks are excluded from **phase detection** (determining whether a phase is complete, triggering phase-level verification, or reaching project completion) to prevent a verify → execute → verify infinite loop. However, out-of-spec tasks still run the **full implement → verify cycle** — they are not exempt from per-task verification. The structural invariant applies universally: no task (spec or out-of-spec) can reach "Finished" without `task_verification.result == "pass"`.

**Out-of-spec tasks:** after phase routing (or at phase boundaries), if out-of-spec tasks are pending approval, read `.claude/support/reference/work-user-flows.md § "Out-of-Spec Task Approval"` and follow it. Never auto-execute them.

### Contextual Command Suggestions

When Step 3 reaches a stopping point (no agent dispatch), append 1-3 relevant command suggestions to the output:

| Condition | Suggestion |
|-----------|------------|
| All remaining tasks are `owner: human` | "Your next actions: {task list with IDs}. Run `/work complete {id}` when done." |
| All remaining tasks are `Blocked` | "Resolve blockers above, then run `/work` to continue." |
| All remaining tasks are `Blocked` with decision deps | "Run `/research {DEC-ID}` to investigate, or resolve blockers manually." |
| All remaining tasks are `On Hold` | "Resume a task: update its status to Pending, then run `/work`." |
| Mixed non-actionable (human + blocked + on hold) | "Run `/work complete {id}` for human tasks, resolve blockers, or resume held tasks." |
| No eligible tasks (deps unmet) | "Waiting on dependencies. Check blocked/human tasks that other tasks depend on." |
| Phase gate pending approval | "Review the phase gate in the dashboard, then run `/work` to continue." |
| Unresolved decision blocks work | "Run `/research {DEC-ID}` to investigate, or resolve it in the dashboard." |
| Spec incomplete | "Run `/iterate` to refine the specification." |
| No spec exists | "Create a vision document in `.claude/vision/` and run `/iterate distill`." |
| Decisions with status `recorded` exist | "{N} agent decision(s) await ratification. Run `/work ratify all`, or `/work reconsider {DEC-ID}` to reopen one." |
| Feedback items exist (new/refined) | "You have {N} feedback items. Run `/feedback review` to triage." |

Rules:
- Maximum 3 suggestions per stopping point
- Prioritize by actionability: human tasks ready > decisions > ratification > feedback
- Always include the specific command with arguments, not just a description
- Only suggest commands relevant to the current state

### Interaction Mode Selection

When a task needs the user (owner `human`/`both`, or `user_review_pending`), choose the channel: dashboard for async, extended, or passive review; CLI-direct for quick, synchronous, hands-on testing. Criteria and the guided-testing flows: `.claude/support/reference/work-user-flows.md`.

### Step 4: Execute Action

#### Safety Gate (all execution paths)

Before spawning any agent, check `known_hazards[]` (from Step 0 Preamble):

```
IF the task involves operations matching a known hazard:
  "⚠️ Known issue: {hazard description}
   This task involves {matching operation}.
   [P] Proceed | [S] Skip task | [W] Use workaround: {specific fix}"
```

The safety gate applies to implement-agent dispatch, verify-agent runtime validation, and phase-level verification — any path that may launch processes.

#### If Decomposing (spec → tasks)

Read `.claude/support/reference/decomposition.md` and follow its 10-step procedure to break the spec into granular tasks with full provenance fields. (First decomposition legitimately reads the whole spec — the "whole when warranted" case in `rules/spec-workflow.md § "Section-scoped spec reading"`. Afterward, generate the section index so downstream per-task agents scope-read: `python3 .claude/scripts/fingerprint.py --index .claude/spec_v{N}.md > .claude/spec_v{N}.index.json`.)

**Capability-claim cross-check (DEC-017):** when decomposing spec sections that reference Claude Code primitives (skill `model:`/`effort:` frontmatter, subagent dispatch, MCP fan-out, `Agent` tool model granularity, parallel execution boundaries), cross-reference `.claude/support/reference/claude-code-authoring.md` before generating task JSON. The reference doc surfaces load-bearing platform facts that aren't obvious from spec text alone (e.g., `model:` is turn-scoped, not session-scoped — multi-turn chat skills cannot use it for cross-turn model continuity). Task descriptions that depend on unsupported platform behavior produce wasted-iteration cycles at implementation time.

#### State Persistence Protocol

**STOP — read `.claude/support/reference/work-procedures.md § "State Persistence Protocol"` NOW (once per session, before processing any agent return).** It is the canonical body for the three after-return protocols this file references by name: **"After implement-agent returns"** (status transitions for completed/partial/partial_resume_pending/blocked/misaligned; DEC-011 dual-write friction-marker append — immediate, never deferred — plus audit-register projection; holding the agent's decisions in the task's `decisions_pending` — no decision file before verification; dashboard regen; verify dispatch on `completed`), **"After verify-agent returns (per-task mode)"** (attempts + history; `task_verification` write incl. `evidence[]` from the Empirical Evidence Gate; pass/fail/escalate transitions; on pass, one `status: recorded` decision record from `decisions_pending`; timeout detection; parent auto-completion; FB-086 `files_affected` drift update), and **"After verify-agent returns (phase-level mode)"** (`verification-result.json`; fix-task creation; loop-or-complete).

The orchestrator owns ALL `.claude/` state transitions — agents cannot write there (DEC-004). Do not improvise any after-return step from this summary; the procedure file is the contract.

#### If Executing

**Before dispatch:** orchestrator sets task JSON to `{"status": "In Progress", "updated_date": today}`.

**Resume-pending check (DEC-010):** if the task JSON has a `partial_completion` field, read `.claude/support/reference/work-recovery.md § "Resume-Pending Dispatch"` and follow it (git-diff audit, envelope injection, clearing the field afterwards) as part of this dispatch.

Dispatch implement-agent (Agent tool; set `model` per `.claude/CLAUDE.md § Model Requirement`) instructing it to read `.claude/agents/implement-agent.md` and follow Steps 1-6. Agent returns a structured report. **The dispatch prompt must state the envelope contract explicitly** — include: *"Return ONLY the structured JSON report envelope from `implement-agent.md § Step 6` — raw JSON, no prose summary, no markdown fences."* (Persona-via-prompt alone does not reliably transmit the output contract; a prose return was observed downstream.)

**After agent returns:** apply "After implement-agent returns" from State Persistence Protocol. Then, if `implementation_status == "completed"`, dispatch verify-agent per "If Verifying (Per-Task)" and apply "After verify-agent returns" protocol.

**Inline implementation (small tasks):** for a task you can finish in a handful of tool calls, you may implement it yourself instead of dispatching implement-agent, following the inline contract in `.claude/rules/agents.md § "Dispatch Invariants vs Efficiency Defaults"` (`[INLINE]` notes, existing checks, before/after behaviour for behaviour-changing edits). Hold your own significant choices in `decisions_pending` exactly as for an agent return ("After implement-agent returns" step 3, with `decided_by: "orchestrator"`); they become a record only when verification passes. Verify-agent dispatch is **not** optional for inline work — set Awaiting Verification and continue with "If Verifying (Per-Task)".

**Context to provide:** Current task, relevant spec sections, constraints/notes, and an explicit instruction that the agent must not attempt writes to `.claude/` — return the structured report only. If the task's notes contain a scope note newer than its `files_affected`, pass the scope note as the authority and say so. If the task has `decisions_pending` (a fix round or resume), pass the entries: the agent restates the set, amended as needed, in its report. Present `files_affected` as the expected scope, not a write limit: the agent searches for what the change invalidates and may edit other files it requires, reporting them (FB-113; `implement-agent.md` Step 2).

**Inline status update (tier 2):** announce `Starting task {id}: "{title}"` when dispatching and a pass/fail summary after verify-agent completes. Dashboard regen deferred to next strategic moment (session boundary, parallel batch end, or async routing to dashboard).

#### If Executing (Parallel)

When Step 2c produces a parallel batch of >= 2 tasks, execute them concurrently.

**Full procedure:** `.claude/support/reference/parallel-execution.md` § "Parallel Dispatch"

**Key rules:**
- **Pre-dispatch confirmation (batch ≥ 3):** Before spawning, present the dispatch plan to the user — task IDs, titles, files affected, verify strategy — and await explicit confirmation. Skip for batches of 2 (low surprise; partial budget). See parallel-execution.md § "Pre-Dispatch Confirmation" for the prompt format and `[D]`/`[S]`/`[1]` behavior.
- Orchestrator sets all batch tasks to "In Progress" before dispatch (see parallel-execution.md § 2)
- Each parallel implement-agent reads `implement-agent.md` and follows Steps 1-6; returns a structured report (each dispatch prompt states the envelope contract explicitly — same clause as sequential dispatch above)
- As each implement-agent report arrives, orchestrator applies "After implement-agent returns" protocol AND dispatches that task's verify-agent (see parallel-execution.md § 4)
- As each verify-agent report arrives, orchestrator applies "After verify-agent returns" protocol
- After all reports processed: final parent auto-completion, single dashboard regeneration, post-dispatch validation (Step 5)

#### If Verifying (Per-Task)

**You must spawn verify-agent as a separate agent. Do not verify inline.** This holds for tasks you implemented inline too, and if you cannot dispatch a subagent, the task stays in Awaiting Verification (`rules/agents.md § "Dispatch Invariants vs Efficiency Defaults"`).

```
Agent tool call:
  subagent_type: "general-purpose"
  model: "opus"  # canonical value: .claude/CLAUDE.md § Model Requirement
  description: "Verify task {id}"
  prompt: |
    You are the verify-agent. Read `.claude/agents/verify-agent.md` and follow
    the Per-Task Verification Workflow (Steps T1-T8) for this task.

    Task file: .claude/tasks/task-{id}.json
    Spec file: .claude/spec_v{N}.md (section: "{spec_section}")

    Verify the implementation independently. Do NOT assume correctness.
    {If the task carries `drift_reverify`: "Re-verification after a spec edit: the
     implementation is unchanged; check it against the current section text."}
    Turn budget: about 30 tool calls. If you get close, follow verify-agent.md § Turn Budget Protocol (result "fail", unfinished checks "skipped").
    Return ONLY the structured JSON verification report (verify-agent.md
    per-task report schema) — raw JSON, no prose summary, no markdown fences.
```

**Timeout handling:** If verify-agent returns without a valid report (prose instead of the report schema, malformed JSON, or nothing usable), ask it once for the report — resume it with SendMessage, or re-dispatch — without incrementing `verification_attempts`. Only a second invalid return is a timeout: treat as verification failure — per State Persistence Protocol, increment `verification_attempts`, set task to "Blocked" with `[VERIFICATION TIMEOUT]` note, report to user. **Infrastructure terminations are interruptions, not timeouts (FB-120):** after a zero-token return, a usage-limit/HTTP 429 kill, an API or harness error, or a stop the user asked for, do NOT increment `verification_attempts` (same rule as an interrupted verifier at `/work pause`); the task stays Awaiting Verification. Per `work-procedures.md § "State Persistence Protocol"` → "After implement-agent returns" step 1, "Zero-token return — platform limit cutoff (FB-103)", report the interruption to the user and apply its post-limit dispatch rule before re-dispatching a fresh verify-agent.

**Empirical Evidence Gate:** if `report.result == "pass"` and the task's output is a web-UI route/component in a web-framework project, and `checks.runtime_validation` is `"partial"` (or `"pass"` without browser measurement), read `.claude/support/reference/work-web-evidence.md § "Empirical Evidence Gate"` and run it **before** persisting the pass. Non-web tasks skip it.

**After per-task verification completes:** verify-agent returns a structured per-task report. Run the Empirical Evidence Gate above when it applies, then apply "After verify-agent returns (per-task mode)" from State Persistence Protocol.

**Auto-continuation:** after the orchestrator persists verification state:
- **Pass**: announce inline `Task {id} verified`. If `report.user_review_pending == true`, route per `work-user-flows.md § "After a Per-Task Pass with user_review_pending"`. Before looping, check if any human-owned or both-owned tasks just became unblocked by this completion — if so, surface them inline: `Note: Task {id} ("{title}") is now available for you — {brief description}`. Then loop back to Step 3 (auto-continuation). Dashboard regen deferred to next strategic moment.
- **Fail (retry)**: announce inline `Task {id} verification failed: {summary} — routing back to implement-agent`. Task was set back to "In Progress" by the protocol. Route to implement-agent to fix, then re-verify. No dashboard regen needed (Claude is fixing it immediately).
- **Fail (escalated)**: announce inline `Task {id} verification escalated after 3 attempts`. Stop auto-continuation; report to user.

#### If Verifying (Phase-Level)

**You must use the verify-agent phase-level workflow. Do not verify directly.**

**MANDATORY: Reconciliation Gate** — Before starting phase-level verification, ALL drift must be reconciled. Re-run `python3 .claude/scripts/fingerprint.py --drift .claude` (a spec edited mid-session would otherwise slip past) and check `drift-deferrals.json`; if `unreconciled_sections` > 0 or any deferral exists, block verification until reconciled (§ "Drift Reconciliation").

```
Agent tool call:
  subagent_type: "general-purpose"
  model: "opus"  # canonical value: .claude/CLAUDE.md § Model Requirement
  description: "Phase-level verification"
  prompt: |
    ultrathink

    You are the verify-agent. Read `.claude/agents/verify-agent.md` and follow
    the Phase-Level Verification Workflow (Steps 1-8).

    Spec file: .claude/spec_v{N}.md
    Task directory: .claude/tasks/

    Validate the full implementation against spec acceptance criteria.
    Create fix tasks for any issues found. Do NOT implement fixes yourself.
    Turn budget: about 50 tool calls. If you get close, follow verify-agent.md § Turn Budget Protocol (result "fail", plus one "Complete phase-level verification" fix task).
    Return ONLY the structured JSON phase-level report (verify-agent.md
    phase-level schema) — raw JSON, no prose summary, no markdown fences.
```

**After phase-level verification completes:** verify-agent returns a structured phase-level report. Apply "After verify-agent returns (phase-level mode)" from State Persistence Protocol.

**Phase UI smoke:** before acting on a phase-level `pass`, if any task in the phase touched web-UI routes/components, read `.claude/support/reference/work-web-evidence.md § "Phase UI Smoke"` and run it; failures create fix tasks. Non-web projects skip.

| Result | Action |
|--------|--------|
| `pass` | Proceed to "If Completing". Present any out-of-spec recommendations for user approval. |
| `fail` | Fix tasks created by the orchestrator. Loop back to Execute, then re-verify when all spec tasks finished. |

#### If Completing

When all tasks are finished and verification conditions are met:

**MANDATORY GATE — Check before proceeding:**

1. **Verify per-task completeness:** Every "Finished" spec task must have `task_verification.result == "pass"`. If any fails, route to verify-agent per-task.
2. **Verify phase-level result:** `.claude/verification-result.json` must exist with passing result, matching `spec_fingerprint`, no tasks modified after `timestamp`. If any fails, route to verify-agent phase-level.

**Once both gates pass:**

1. **Update spec status** to `complete` (set `status: complete`, `updated: YYYY-MM-DD` in frontmatter)
2. **Regenerate dashboard** to reflect completion state (Action Required clears; Progress shows final phase complete; Tasks section collapses fully-finished phases)
3. **Present final checkpoint** — report completion with verification summary, plus the count and ids of any decisions still `recorded` (`/work ratify all`); they don't block completion
4. **Learning capture prompt** — "Project complete. Any patterns or learnings to capture? [L] Share  [S] Skip". If [L]: append to `.claude/support/learnings/project-learnings.md`. If [S]: continue silently.
5. **Stop** — do not route to any agent. The project is done.

### Step 5: Post-Dispatch Validation

Run quick validation after task dispatch to catch issues early:

1. **Task file integrity** — Verify the task JSON that was just modified is valid JSON and parseable
2. **Dashboard exists** — Confirm `.claude/dashboard.html` exists and has a `<!-- DASHBOARD META -->` comment in its `<head>`
3. **Session sentinel** — Write `.claude/tasks/.last-clean-exit.json` with current timestamp and in-progress task list (enables fast-path recovery check on next `/work` run)
4. **Session boundary dashboard freshness** — When the main work loop has reached a natural stopping point (phase boundary, blocking decision, verification failure needing human escalation, or no more eligible tasks), verify dashboard freshness against actual task state: recompute `task_hash` (`dashboard-render.py --task-hash`) and compare against the `<!-- DASHBOARD META -->` block; META `spec_fingerprint` ≠ the current spec hash also means stale (Step 1a). If stale, regenerate now — the user should never see a stale dashboard as the final state of a work session.

For full maintenance validation (schema checks, decision integrity, template sync), use `/health-check`.

---

## Spec Alignment Examples

- **Aligned:** "Add password validation" when spec says "User authentication with email and password" → proceed
- **Minor:** "Fix typo in login error" when spec doesn't mention errors → proceed (within scope)
- **Misaligned:** "Add Google login" when spec says only email/password → surface options (add to spec, proceed anyway, skip)

---

## Output

Report the current phase and what was done, any spec misalignments surfaced, and next steps or blockers.

---

## Task Completion (`/work complete`)

Manual task completion outside implement-agent's workflow — human-owned tasks, work done outside the normal flow, quick tasks. (implement-agent handles its own completion internally; `/work complete` is not needed after it finishes.)

**STOP — read `.claude/support/reference/work-procedures.md § "Task Completion (/work complete)"` NOW and follow its 10-step Process + Rules.** Hard invariants enforced there: no task reaches "Finished" without `task_verification.result == "pass"` (human tasks auto-generate `self_attested`; unverified tasks get verify-agent dispatched first); deliverable validation for `human`/`both` tasks (`[A]/[P]/[W]`); the two-prompt completion-notes collection (project notes always; template notes only when `template_inbox_path` is configured); dashboard-marker fallback capture; writing the task's held `decisions_pending` as a `recorded` decision record; parent auto-completion; dashboard regen + unblocked-task surfacing; auto-archive check; Step 5 post-dispatch validation. Do not improvise the flow from this summary.

---

## Decision Ratification (`/work ratify`, `/work reconsider`)

Agent-recorded decisions (status `recorded`: an agent chose during implementation, the work passed verification, you haven't confirmed the choice) never block tasks or phase gates. These two sub-modes are how the user closes them. Shape and lifecycle: `.claude/support/reference/decisions.md`.

Both edit **frontmatter only**, with one exception: reconsider unticks a box the agent ticked on an older record (its step 2). They are infrastructure operations under DEC-016 (`rules/spec-workflow.md § "Direct edits to spec, decision, and vision files (DEC-016)"`), so they don't route through `/iterate` or `/research`. The `permissions.ask` prompt on decision files still fires (once per session with "Yes, don't ask again"). Otherwise never touch the record body here.

### `/work ratify [all | DEC-NNN …]`

1. **Resolve targets.** `all` → every `decision-*.md` with `status: recorded`. Ids → those records. If none are `recorded` (`all` or no argument): `No agent decisions await ratification.` and stop. No argument → list the `recorded` records (id, title, related task, each `**Selected:**` line) and ask:
   ```
   {N} agent decision(s) await ratification.
   [A] Ratify all | [DEC-NNN …] Ratify these | [N] None now
   ```
   To change one instead of ratifying it: `/work reconsider DEC-NNN`.
2. **For each target:** if the record is missing or its status isn't `recorded`, report `DEC-NNN is {status} — skipped` and leave it alone. Otherwise set `status: approved` and add `ratified: <today's YYYY-MM-DD>`. Leave `decided` and `decided_by` as they are (provenance).
3. **Regenerate the dashboard** (Tier 1: decision resolution).
4. **Report:** `Ratified: DEC-…` and, if any, `Skipped: DEC-… ({status})`. Then stop.

### `/work reconsider DEC-NNN`

1. The record must have `status: recorded`; for any other status report it and point to `decisions.md § "Revisiting Decisions"`.
2. Set `status: proposed` (no other frontmatter change). If the record has a `## Select an Option` section with a ticked box (older agent-written records), untick it in the same edit and say so: the agent ticked it, and a ticked box on a `proposed` record is approved by the next `/work` or `/iterate`. That is the only body edit this sub-mode makes.
3. Regenerate the dashboard — the record now shows as an unresolved decision.
4. Output:
   ```
   DEC-NNN reopened. Run /research DEC-NNN to compare the options and select one.
   Task {id} stays Finished. If your selection differs from what was built, the change becomes a new task.
   ```

Never reset or re-open the related task here, and never add the record to its `decision_dependencies`. The follow-up task is offered when the selection lands (`phase-decision-gates.md § "Post-Decision Check"`, run from Step 2b or `/iterate` Step 1a).

---

## Auto-Archive

When active task count exceeds 100 (checked after dashboard regen), archive finished tasks older than 7 days to `.claude/tasks/archive/` — full task JSON preserved, `archive-index.json` updated with lightweight summaries, dashboard regenerated again. Archived tasks are read-only reference material (check the archive when a referenced task ID isn't in active tasks). **Procedure: read `work-procedures.md § "Auto-Archive"` before archiving.**

---

## Context Transition (`/work pause`)

Graceful wind-down that preserves reasoning context before compaction clears the context window. Use when a session is getting long and you want to ensure continuity. Pause is also a valid **mid-session checkpoint** — pausing, continuing to work, and pausing again in one session is normal use (each pause overwrites the handoff with the newest state); pause does not imply session end.

Read `.claude/support/reference/context-transitions.md` and follow the Path A (User-Initiated) procedure. Key rules:

- Do NOT change task status to Blocked or On Hold — pause is not a failure state
- Do NOT increment `verification_attempts` if verify-agent was interrupted
- Do NOT skip the handoff file — that's the whole point
- `session_knowledge` captures what would otherwise be lost: user preferences, informal decisions, discovered patterns
- **Open-question sweep (human-gated coverage):** before writing the handoff, enumerate every question asked of the user this session that went unanswered, plus any newly user-gated items (tasks put On Hold, Blocked on the user or flagged for review, unblocked `owner: "human"` tasks, unresolved decisions). Each MUST land in the dashboard's 🚨 Action Required ("Needs you") card with the concrete question inline: the script derives task and decision rows; write each unanswered question (and any Blocked task's open choice) to sidecar `augment_rows[]`, prune answered ones, then regenerate `dashboard.html` — never edit the HTML (`dashboard-regeneration.md § "Augment Rows"`). The handoff may point at those items; it must never be a blocking question's only home. (Counterpart: Step 0g prints this queue at the next session start.)
- **New spec sections (FB-106):** if `/iterate` added a new `## ` section this session that no task references, confirm its heading is in `pending_decomposition[]` in `.claude/dashboard-state.json` (`/iterate`'s post-apply step writes it). Regenerating at pause is then safe: Step 1a reads the marker before anything else, so the decomposition offer survives the regen. If the marker is somehow absent and you cannot add it, fall back to the pre-v5.4.0 rule: skip the regen, print blocking items inline, and flag the undecomposed section in the handoff.

### Interaction Assessment + Session Export (Track 2 — Cross-Project Logging)

After the handoff file is written, complete the pause: generate the interaction assessment (`.interaction-assessment.json`), compile the session export (`.session-export-YYYY-MM-DD-HHMM.json`; copy to `template_inbox_path` when configured), then clean up the working files. **Procedure + schemas: `context-transitions.md § "Pause Follow-Through (Track 2 — Cross-Project Logging)"`** — the same file the pause procedure above already directs you to read; do not improvise the export shape from memory. **The inbox copy (Session Export step 6) is mechanized (FB-109): invoke `python3 .claude/scripts/persist-session-export.py --source <export-path>` — never `cp` the dot-prefixed working filename to the inbox verbatim; the script enforces the never-dot-prefixed rename structurally.** Interrupted-pause recovery is Step 0f's job (FB-089); if the PreCompact hook fires instead of `/work pause`, it compiles a markers-only export on its own.
